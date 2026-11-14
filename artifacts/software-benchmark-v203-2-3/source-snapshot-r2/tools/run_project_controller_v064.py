"""Real S1 managed OpenHands controller in the network-disabled task pair."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import selectors
import signal
import sys
import time
import traceback


def validate_config(config):
    allowed = {"version", "slot_id", "source_slot_id", "seed", "condition_id", "execution_arm", "model_key",
               "configuration", "public_task", "ref_endpoint", "model_identity_value", "output", "start", "ready",
               "diagnostic", "measurement_kind", "public_context", "public_environment", "lifecycle_deadline",
               "maximum_lifecycle_seconds", "file_policy", "dataset_revision", "gitlinks", "public_test_entry"}
    if (config.get("version") != "v064-private-project-controller-r1" or set(config) - allowed
            or not str(config.get("slot_id", "")).startswith("v064:") or config.get("execution_arm") != "PROJECT"
            or config.get("model_key") not in {"QWEN", "DEEPSEEK"}
            or config.get("output") != "/pws/output" or config.get("start") != "/pws/control/start.json"
            or config.get("ready") != "/pws/control/actor-ready.json"
            or config.get("configuration", {}).get("path") != "/pws/control/condition.json"
            or type(config.get("diagnostic")) is not bool
            or config.get("measurement_kind") != ("zero_model_diagnostic" if config["diagnostic"] else "full_verified_comparison")
            or set(config.get("public_task", {})) != {"instance_id", "repo", "base_commit", "problem_statement"}
            or set(config.get("public_context", {})) != {"version", "visible_text", "visible_facts"}
            or not isinstance(config.get("dataset_revision"), str)):
        raise ValueError("PROJECT must receive only its bound public task, model route and exact private layout")
    return config


def install_deadline(config):
    maximum, deadline = config.get("maximum_lifecycle_seconds"), config.get("lifecycle_deadline")
    if (type(maximum) is not int or maximum != (180 if config["diagnostic"] else 24000)
            or type(deadline) not in (int, float) or not 0 < deadline - time.monotonic() <= maximum):
        raise ValueError("PROJECT controller lacks its owned finite lifecycle deadline")
    signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
    signal.setitimer(signal.ITIMER_REAL, deadline - time.monotonic())


class ManagedRPC:
    def __init__(self, ready, *, reader, writer, directory, hard_at):
        from proworksim.software_benchmark_managed_actor_v064 import VERSION, upload_protocol
        if (ready.get("version") != VERSION or ready.get("implementation") != "v064-private-docker-managed-worker-r1"
                or ready.get("managed_operations") != ["managed_public_test", "sync_terminal"]
                or ready.get("managed_upload_protocol") != upload_protocol()
                or ready.get("isolation", {}).get("pid") != 1
                or ready["isolation"].get("capabilities_all_zero") is not True
                or ready["isolation"].get("no_new_privileges") is not True
                or ready["isolation"].get("dumpable") is not False):
            raise ValueError("The actual managed actor did not prove its isolated RPC boundary")
        self.reader, self.writer, self.directory = reader, writer, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.hard_at, self.sequence, self.failed, self.closed = hard_at, 0, False, False
        self.buffer = bytearray()

    def receive(self):
        from proworksim.software_benchmark_managed_actor_v064 import MAX_RPC_BYTES, ManagedInterfaceLimit
        with selectors.DefaultSelector() as selector:
            selector.register(self.reader.fileno(), selectors.EVENT_READ)
            while True:
                separator = self.buffer.find(b"\n")
                if separator >= 0:
                    if separator + 1 > MAX_RPC_BYTES:
                        raise ManagedInterfaceLimit("Exact actor response exceeded the RPC frame bound")
                    raw = bytes(self.buffer[:separator])
                    del self.buffer[:separator + 1]
                    return json.loads(raw)
                if len(self.buffer) > MAX_RPC_BYTES:
                    raise ManagedInterfaceLimit("Exact actor response exceeded the RPC frame bound")
                remaining = self.hard_at - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("Managed actor response exceeded the episode hard deadline")
                chunk = os.read(self.reader.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("Managed actor closed without its exact response")
                self.buffer.extend(chunk)

    def exchange(self, value, expected):
        from proworksim.software_benchmark_candidates_v054 import write_new
        from proworksim.software_benchmark_managed_actor_v064 import (
            MAX_RPC_BYTES, ManagedInterfaceLimit, ManagedTransferError, UPLOAD_CHUNK,
        )
        from proworksim.storage import digest
        if self.failed or self.closed or not time.monotonic() < self.hard_at:
            raise RuntimeError("The failed, closed or expired managed RPC cannot replay work")
        self.sequence += 1
        value = {"id": self.sequence, **value}
        raw = (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        if len(raw) > MAX_RPC_BYTES:
            raise ManagedInterfaceLimit("Managed transfer exceeds the exact RPC frame bound")
        recorded = value
        if value.get("tool") == UPLOAD_CHUNK:
            # Full source versions remain in the World archive. Record exact
            # transport identities without duplicating every large file as base64.
            recorded = {**value, "action": {key: item for key, item in value["action"].items()
                                            if key != "data_base64"},
                        "chunk_bytes_in_log": False, "wire_sha256": digest(raw), "wire_bytes": len(raw)}
        write_new(self.directory / f"{self.sequence:04d}-request.json", recorded)
        try:
            self.writer.write(raw.decode("utf-8"))
            self.writer.flush()
            result = self.receive()
            write_new(self.directory / f"{self.sequence:04d}-response.json", result)
            if result.get("id") != self.sequence or result.get("type") != expected:
                if result.get("classification") == "interface_coverage_limit":
                    raise ManagedInterfaceLimit(result.get("error", "Managed actor coverage limit"))
                if result.get("classification") == "interface_unknown":
                    raise ManagedTransferError(result.get("error", "Managed internal transfer is unknown"))
                raise RuntimeError("Managed actor operation failed: " + str(result))
            return result
        except BaseException:
            self.failed = True
            raise

    def request(self, tool, action):
        from proworksim.software_benchmark_managed_actor_v064 import (
            ManagedTransferError, UPLOAD_BEGIN, UPLOAD_CHUNK, UPLOAD_COMMIT,
            prepare_payload_upload, upload_chunks,
        )
        try:
            if self.failed or self.closed:
                raise ManagedTransferError("A failed or closed internal transfer cannot be replayed")
            with prepare_payload_upload(action, tool, directory=self.directory / "upload-staging",
                                        hard_at=self.hard_at) as (manifest, stream):
                response = self.exchange({"tool": UPLOAD_BEGIN, "action": manifest}, "observation")
                ack = response.get("result", {})
                if (response.get("tool") != UPLOAD_BEGIN or ack.get("upload_id") != manifest["upload_id"]
                        or ack.get("accepted") is not True or ack.get("received_bytes") != 0
                        or ack.get("next_index") != 0 or ack.get("operation_executed") is not False):
                    raise ManagedTransferError("Actor did not acknowledge the unique empty upload")
                for chunk in upload_chunks(manifest, stream):
                    response = self.exchange({"tool": UPLOAD_CHUNK, "action": chunk}, "observation")
                    ack = response.get("result", {})
                    if (response.get("tool") != UPLOAD_CHUNK or ack.get("upload_id") != manifest["upload_id"]
                            or ack.get("received_bytes") != chunk["offset"] + chunk["bytes"]
                            or ack.get("next_index") != chunk["index"] + 1
                            or ack.get("operation_executed") is not False):
                        raise ManagedTransferError("Actor chunk acknowledgement changed its sequence or byte count")
                commit = {key: manifest[key] for key in ("version", "upload_id", "payload_bytes", "payload_sha256")}
                response = self.exchange({"tool": UPLOAD_COMMIT, "action": commit}, "observation")
                receipt = response.get("upload_receipt", {})
                if (response.get("tool") != tool
                        or any(receipt.get(key) != manifest[key] for key in
                               ("version", "upload_id", "operation", "payload_bytes", "payload_sha256", "chunks"))
                        or receipt.get("complete_payload_verified") is not True
                        or receipt.get("operation_executed") is not True):
                    raise ManagedTransferError("Managed operation lacks its fully verified upload receipt")
                return response["result"]
        except Exception as error:
            self.failed = True
            if isinstance(error, ManagedTransferError):
                raise
            raise ManagedTransferError("Managed internal payload exchange failed: " + str(error)) from error

    def close(self):
        result = self.exchange({"op": "close"}, "closed")
        if result.get("owned_children_quiescent") is not True:
            raise RuntimeError("Managed actor did not prove public-test child cleanup")
        self.closed = True
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    config = validate_config(json.loads(parser.parse_args().config.read_bytes()))
    if os.getpid() != 1 or not Path("/testbed").is_dir():
        raise ValueError("Managed controller must be PID1 with the read-only actual actor checkout")
    install_deadline(config)
    output = Path(config["output"])
    os.environ.update(OH_PERSISTENCE_DIR=str(output / "empty-user-config"),
                      OPENHANDS_SUPPRESS_BANNER="1", LITELLM_LOCAL_MODEL_COST_MAP="True")
    from proworksim import software_benchmark_managed_v064 as managed
    from proworksim import software_benchmark_world_v064 as world
    from proworksim.software_benchmark_candidates_v054 import checked, write_new
    from proworksim.software_benchmark_managed_actor_v064 import make_delta, validate_public_entry
    from proworksim.software_benchmark_project_closure_v064 import export_managed_closure
    from proworksim.software_benchmark_ref_budget_v064 import PairedQwenAdapter, validate_condition
    from proworksim.software_benchmark_deepseek_adapter_v064 import DeepSeekEpisodeAdapter
    from proworksim.software_benchmark_model_fifo_v064 import FifoModelTransport
    from proworksim.software_benchmark_native_control_v062 import initial_message
    from proworksim.software_calibration_collector_v051 import run_fragment, close_runtime, budget_snapshot
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.repository_sources_v054 import capture_repository, normalize_policy
    from proworksim.harness_port import HarnessPort
    from proworksim.model_policy import CONTROL_TOOLS
    from proworksim.storage import atomic_write, digest, json_bytes

    condition = json.loads(checked(config["configuration"]).read_bytes())
    limits = validate_condition(condition)
    if condition["arm"] != "PROJECT" or condition["model_key"] != config["model_key"]:
        raise ValueError("Managed condition identity changed")
    ready = json.loads(Path(config["ready"]).read_bytes())
    entry = validate_public_entry(config["public_test_entry"], instance_id=config["public_task"]["instance_id"],
        public_python=config["public_environment"]["public_python"])
    if ready.get("public_test_entry_sha256") != digest(json_bytes(entry)):
        raise ValueError("Actor and controller must use the identical public test entrypoint")
    write_new(output / "controller-ready.json", {"trusted_SDK_imports_complete": True,
              "version": config["version"], "model_calls": 0, "tool_calls": 0})
    until = time.monotonic() + 120
    while not Path(config["start"]).exists():
        if time.monotonic() >= until:
            raise TimeoutError("Host did not admit the new controller before startup timeout")
        time.sleep(.05)
    start = json.loads(Path(config["start"]).read_bytes())
    if (start.get("guard_path") != "/pws/output/guard.json"
            or any(not isinstance(start.get(key), (int, float)) or not math.isfinite(start[key])
                   for key in ("started", "soft_at", "hard_at"))):
        raise ValueError("Controller start lacks the exact private guard and finite deadlines")
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    deadline.started = deadline.last_clock = start["started"]
    deadline.soft_at, deadline.hard_at = start["soft_at"], start["hard_at"]
    result = {"version": config["version"], "arm": "PROJECT", "model_key": config["model_key"],
              "condition_id": condition["condition_id"], "slot_id": config["slot_id"],
              "source_slot_id": config["source_slot_id"], "execution_arm": "PROJECT",
              "measurement_kind": config["measurement_kind"], "status": "running",
              "preparation_only": config["diagnostic"], "hidden_feedback_received": False,
              "automatic_retry": False, "model_key_present": False}
    runtime = adapter = rpc = transport = None
    try:
        rpc = ManagedRPC(ready, reader=sys.stdin, writer=sys.stdout,
                         directory=output / "managed-actor-rpc", hard_at=start["hard_at"])
        policy = normalize_policy(config.get("file_policy"))
        if ready.get("file_policy") != policy:
            raise ValueError("Actor and controller baseline access policy differs")
        manifest = capture_repository("/testbed", output / "source-snapshot",
            task_id=config["public_task"]["instance_id"], problem_statement=config["public_task"]["problem_statement"],
            source_identity={**{key: config["public_task"][key] for key in ("instance_id", "repo", "base_commit")},
                             "dataset_revision": config["dataset_revision"]},
            file_policy=policy, gitlinks=config.get("gitlinks", []))
        baseline = json.loads((manifest.parent / "initial-tree.json").read_bytes())
        if baseline["tree"]["tree_sha256"] != ready.get("initial_tree_sha256"):
            raise ValueError("The read-only controller view is not the complete actual actor baseline")
        def public_test(**payload):
            return rpc.request("managed_public_test", make_delta(baseline, payload["files"],
                payload["entry_metadata"], request=payload["request"]))
        prepared = managed.prepare_case(manifest, output / "managed-world",
            max_total_tokens=limits["input_plus_output_tokens"], public_test_callback=public_test, deadline=deadline)
        gateway = HarnessPort(world.SoftwareCollaborationPort(prepared.world.session("member_001", world.PROJECT),
            "member_001"), "member_001", project_id=world.PROJECT, public_sink=lambda *_: None,
            world_sink=lambda *_: None, harness_sink=lambda *_: None)
        allowed = {tool["name"] for tool in [*gateway.tools(), *CONTROL_TOOLS]}
        if config["diagnostic"]:
            class NeverGenerate:
                limits = {"context_limit": 131072}
                maximum_input_tokens, maximum_output_tokens = 98304, 32768
                model, thinking = "v064-no-model-diagnostic", True
                def count(self, *_args, **_kwargs):
                    raise RuntimeError("No generation or model count is allowed in the managed deployment diagnostic")
                complete = request = count
            adapter = NeverGenerate()
        else:
            transport = FifoModelTransport(config["ref_endpoint"])
            if config["model_key"] == "QWEN":
                adapter = PairedQwenAdapter(transport=transport, folder=output / "model-ledger",
                    slot_id=config["slot_id"], seed=config["seed"], service_identity=config["model_identity_value"],
                    condition=condition, allowed_tools=allowed)
                adapter.started = start["started"]
            else:
                adapter = DeepSeekEpisodeAdapter(post=transport.post, arm="PROJECT", slot_id=config["slot_id"],
                    condition_id=condition["condition_id"], token_budget=limits["input_plus_output_tokens"],
                    folder=output / "model-ledger", allowed_tool_names=allowed,
                    soft_at=start["soft_at"], hard_at=start["hard_at"])
        owner = managed.ProjectOwner(adapter, window_id=config["slot_id"], identity={
            "policy_version": "v064-project-broker-model", "model_key": config["model_key"],
            "model_identity": config["model_identity_value"], "trained_adapter_loaded": False})
        runtime, _, _ = managed.build_runtime(owner, prepared, output / "managed-runtime", deadline=deadline,
            public_initial_message=initial_message(config["public_task"]["problem_statement"],
                public_context=config["public_context"]["visible_text"]))
        actual_tools = {tool["name"] for tool in runtime.policies["member_001"].definitions}
        if actual_tools != allowed:
            raise ValueError("The actual SDK tools differ from the model broker admission")
        if config["diagnostic"]:
            probe = ".pws-v064-managed-probe"
            if probe in baseline["files"]:
                raise ValueError("The predetermined diagnostic path belongs to the original task")
            for i, (name, args) in enumerate((
                ("create_file", {"path": probe, "text": "managed-private-roundtrip\n"}),
                ("search_repository", {"text": "managed-private-roundtrip"}),
                ("delete_file", {"path": probe}),
                ("delivery_status", {}),
            )):
                value = gateway.call(name, request_key=f"diagnostic-{i}", association={}, **args)
                if value.get("ok") is not True:
                    raise RuntimeError("Managed deployment control failed: " + name)
            result.update(diagnostic=True, diagnostic_passed=True, model_calls=0,
                          actual_SDK_initialized=True, initialized_managed_tools=sorted(actual_tools))
        else:
            boundary = run_fragment(prepared, runtime, on_opportunity=lambda _: atomic_write(
                output / "managed-live-ledger.json", json_bytes(budget_snapshot(runtime, prepared))))
            write_new(output / "managed-boundary.json", boundary)
            result.update(managed_boundary=boundary, managed_budget=budget_snapshot(runtime, prepared),
                          closure_reason=boundary["closure_reason"], actions=runtime.actions,
                          opportunities=runtime.opportunities, ledger=adapter.ledger.snapshot())
            if boundary["execution_integrity_failure"] is not None:
                raise RuntimeError("Managed execution integrity failed; no replay")
            if (result["ledger"]["complete_actual_tokens"] is None or result["ledger"].get("inflight")
                    or result["ledger"].get("uncertain_reserved_tokens")):
                raise RuntimeError("A closed managed controller cannot conceal uncertain provider usage")
        close_runtime(runtime)
        runtime = None
        closure = export_managed_closure(prepared, output, slot_id=config["slot_id"], sdk_closed=True)
        bundle = closure.pop("terminal_bundle")
        synced = rpc.request("sync_terminal", make_delta(baseline, bundle["files"], bundle["entry_metadata"], request={
            "instance_id": config["public_task"]["instance_id"], "source_reference": closure["terminal_source_reference"],
            "tree_sha256": closure["terminal_tree_sha256"], "hard_deadline_monotonic": start["hard_at"],
            "hidden_evaluation": False, "arbitrary_command": False}))
        if synced.get("tree_sha256") != closure["terminal_tree_sha256"] or synced.get("terminal_locked") is not True:
            raise ValueError("Stopped actor code does not equal the uniquely locked managed terminal tree")
        result.update(project_closure=closure, terminal_sync=synced, actor_close=rpc.close(),
                      status="closed", actual_managed_S1_runtime=True, original_Gamma1_permissions=True,
                      full_history_before_capacity=True, actual_SDK_worker=True,
                      model_can_resume=False, process_tree_quiescence_proven=False)
    except BaseException as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      failure_classification=getattr(error, "classification", "technical_unknown"),
                      traceback=traceback.format_exc(), automatic_retry=False)
    finally:
        if runtime is not None:
            close_runtime(runtime)
        if transport is not None:
            close = getattr(transport, "close", None)
            if close is not None:
                close()
        write_new(output / "controller-result.json", result)
    if result["status"] != "closed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
