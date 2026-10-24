"""One real SDK construction control; never send a prompt or count/generate tokens."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def inside(config_path):
    config = json.loads(Path(config_path).read_bytes())
    output = Path(config["output"])
    os.environ["OH_PERSISTENCE_DIR"] = str(output / "empty-user-config")
    from openhands.sdk import Conversation
    import run_ref_budget_controller_v056
    from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
    from proworksim.software_benchmark_exact_transport_v054 import build_llm
    from proworksim.software_benchmark_native_binding_v054 import NativeToolRPC, build_isolated_agent
    from proworksim.software_benchmark_native_v054 import initialized_interface_manifest
    from proworksim.software_benchmark_ref_budget_v056 import BudgetRefAdapter, validate_condition
    from proworksim.software_benchmark_ref_deployment_v054 import AuthenticatedLoopbackHTTP
    from proworksim.software_benchmark_runner_transport_v054 import GuardedRefAdapter, HostDeadline

    condition = json.loads(checked(config["condition"]).read_bytes())
    limits = validate_condition(condition)
    ready = json.loads(checked(config["resident_ready"]).read_bytes())
    expected = json.loads(checked(config["native_interface"]).read_bytes())
    wire_ready = json.loads(Path(config["worker_ready"]).read_bytes())
    calls = {"http": 0, "count": 0, "complete": 0}
    rpc = NativeToolRPC(ready=wire_ready, reader=sys.stdin, writer=sys.stdout)
    conversation = adapter = None
    result = {"version": "v056-ref-sdk-construction-r1", "passed": False,
              "model_calls": 0, "tokens": 0, "formal_slot_claims": 0,
              "conversation_send_message_called": False, "conversation_run_called": False}

    class ForbiddenHTTP(AuthenticatedLoopbackHTTP):
        def post(self, *_):
            calls["http"] += 1
            raise AssertionError("This construction control forbids every model HTTP request")

    def forbidden_count(*_):
        calls["count"] += 1
        raise AssertionError("This construction control must not count model input")

    def forbidden_complete(*_):
        calls["complete"] += 1
        raise AssertionError("This construction control must not generate model output")

    try:
        adapter = BudgetRefAdapter(
            transport=ForbiddenHTTP(ready["endpoint"], ready["api_key_file"]),
            folder=output / "adapter-ledger", slot_id="synthetic-v056-sdk-construction",
            seed=config["seed"], service_identity=ready["identity_value"], condition=condition)
        adapter.count, adapter.complete = forbidden_count, forbidden_complete
        started = time.monotonic()
        deadline = {"started": started, "soft_at": started + limits["soft_seconds"],
                    "hard_at": started + limits["hard_seconds"],
                    "guard_path": str(output / "unused-guard.json")}
        guarded = GuardedRefAdapter(adapter, HostDeadline(deadline), started)
        llm = build_llm(guarded)
        conversation = Conversation(agent=build_isolated_agent(llm, rpc=rpc),
            workspace="/testbed", persistence_dir=output / "conversation", plugins=[],
            max_iteration_per_run=limits["agent_decisions"], stuck_detection=True,
            visualizer=None, delete_on_close=False)
        # This is the constructor's actual lazy initialization, without send_message/run.
        conversation._ensure_agent_ready()
        actual = initialized_interface_manifest(conversation.agent)
        actual_ref = write_new(output / "actual-native-interface.json", actual)
        # The old synthetic manifest contains its original working directory.
        # Formal workers always bind /testbed; only this exact runtime field differs.
        expected_tools = copy.deepcopy(expected["tool_schemas"])
        original_cwd = "/data1/zhuxinrui/projects/ProWorkSim/runs/software-benchmark-v054/native-sdk-control/r2/synthetic-workspace"
        description = expected_tools["file_editor"]["function"]["description"]
        marker = "Your current working directory is: " + original_cwd
        if description.count(marker) != 1:
            raise ValueError("Unknown original synthetic workspace field in the tool manifest")
        expected_tools["file_editor"]["function"]["description"] = description.replace(
            marker, "Your current working directory is: /testbed", 1)
        if actual["tool_schemas"] != expected_tools:
            raise ValueError("Actual five SDK tools differ from the frozen native schemas")
        if (llm.max_input_tokens != 98304 or llm.max_output_tokens != 32768
                or llm.temperature != .6 or llm.num_retries != 0
                or conversation.max_iteration_per_run != 512
                or conversation.state.max_iterations != 512
                or adapter.request_defaults["seed"] != config["seed"]
                or adapter.request_defaults["chat_template_kwargs"] != {"enable_thinking": True}
                or any(calls.values()) or adapter.counter.requests != 0):
            raise ValueError("Actual SDK budget, inference defaults or zero-request boundary differ")
        snapshot = adapter.ledger.snapshot()
        if snapshot["attempts"] != 0 or snapshot["known_actual_tokens"] != 0 or snapshot["inflight"]:
            raise ValueError("SDK construction unexpectedly entered model accounting")
        result.update(passed=True, actual_interface=actual_ref,
            tools=sorted(actual["tool_schemas"]), five_native_schemas_match=True,
            schema_comparison_runtime_binding={"field": "file_editor.function.description.cwd",
                "original_synthetic_directory": original_cwd, "actual_formal_directory": "/testbed",
                "all_other_schema_fields_compared_exactly": True},
            max_input_tokens=llm.max_input_tokens, max_output_tokens=llm.max_output_tokens,
            temperature=llm.temperature, model_retries=llm.num_retries,
            max_iteration_per_run=conversation.max_iteration_per_run,
            state_max_iterations=conversation.state.max_iterations,
            condition=config["condition"], token_limit=snapshot["token_limit"],
            attempt_limit=snapshot["all_model_attempt_limit"],
            decision_limit=snapshot["agent_decision_limit"],
            seed=config["seed"], request_defaults=adapter.request_defaults,
            resident_ready=config["resident_ready"], network_calls_blocked_by_guard=True,
            production_controller_imported=reference(run_ref_budget_controller_v056.__file__))
    except BaseException as error:
        result.update(error={"type": type(error).__name__, "message": str(error)},
                      traceback=traceback.format_exc())
    finally:
        if conversation is not None:
            conversation.close()
        try:
            rpc.close(timeout_seconds=10)
            result["RPC_close_acknowledged"] = True
        except BaseException as error:
            result.update(passed=False, RPC_close_error=str(error))
        if adapter is not None:
            result["ledger"] = adapter.ledger.snapshot()
        result["guarded_invocations"] = calls
        result["tool_requests"] = len([row for row in rpc.transcript if "request" in row])
        write_new(output / "sdk-result.json", result)
    return 0 if result["passed"] else 1


def host(args):
    from proworksim import software_benchmark_runner_v054 as old
    from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
    from proworksim.software_benchmark_network_v055 import direct_environment_command, validate_actor_ready
    from proworksim.software_benchmark_resources_v054 import create_episode_resources, release_episode_resources
    from proworksim.software_benchmark_rootfs_v056 import clone_prepared_rootfs
    from proworksim.software_benchmark_rootfs_io_v056 import cleanup_episode_rootfs
    from proworksim.software_benchmark_supervision_v054 import (
        assert_outer_launcher_exited, claim_nonce, launch_owned, stop_owned,
    )

    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "runs/software-benchmark-v056"):
        raise ValueError("SDK control must use a new v056 namespace")
    output.mkdir(parents=True, exist_ok=False)
    plan_ref, resident_ref = reference(args.plan), reference(args.resident_ready)
    if plan_ref["sha256"] != args.plan_sha256:
        raise ValueError("Fixed plan changed before SDK construction control")
    plan = json.loads(checked(plan_ref).read_bytes())
    prior = reference(ROOT / "runs/software-benchmark-v056/runtime-cpu-control-r1/result.json")
    if json.loads(checked(prior).read_bytes()).get("passed") is not True:
        raise ValueError("New SDK control reuses the completed Actor namespace qualification")
    preparation_ref = reference(args.prepared_receipt)
    preparation = json.loads(checked(preparation_ref).read_bytes())
    condition = plan["conditions"]["REF_B10000K"]
    slots = json.loads(checked(plan["slots"]).read_bytes())["slots"]
    seed = next(row["seed"] for row in slots if row["condition_id"] == "REF_B10000K"
                and row["instance_id"] == plan["task_ids"][0])
    result = {"version": "v056-real-sdk-construction-control-r1", "passed": False,
        "plan": plan_ref, "inherited_actor_qualification": prior,
        "preparation": preparation_ref, "resident_ready": resident_ref,
        "model_calls": 0, "tokens": 0, "GPU_loads": 0, "formal_slot_claims": 0,
        "test_executions": 0, "grading_calls": 0}
    processes, resources, clone = [], None, None
    try:
        clone = clone_prepared_rootfs(checked(preparation["rootfs_environment"]), output / "actor")
        claim = claim_nonce()
        resources = create_episode_resources(claim, output)
        worker, scope = launch_owned([str(ROOT / "tools/run_native_worker_mapped_v056.sh"),
            "--rootfs", clone["rootfs"], "--stdlib", plan["stdlib"],
            "--environment-manifest", clone["environment_manifest"]],
            claim_id=claim, role="actor", resources=resources, runtime_seconds=300,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=(output / "worker.stderr").open("xb"))
        processes.append((worker, scope))
        ready = old.read_frame(worker.stdout, timeout=60)
        validate_actor_ready(ready)
        ready_ref = write_new(output / "worker-ready.json", ready)
        config = write_new(output / "sdk-config.json", {"output": str(output),
            "worker_ready": ready_ref["path"], "resident_ready": resident_ref,
            "native_interface": reference(ROOT / "artifacts/software-benchmark-v054/manifests/native-interface.json"),
            "condition": condition, "seed": seed})
        command = direct_environment_command([str(ROOT / "tools/run_native_sdk_controller_v054.sh"),
            plan["sdk_runtime"], clone["rootfs"], str(Path(__file__).resolve()),
            "--inside", config["path"]])
        controller, scope = launch_owned(command, claim_id=claim, role="controller", resources=resources,
            runtime_seconds=180, stdin=worker.stdout, stdout=worker.stdin,
            stderr=(output / "controller.stderr").open("xb"))
        processes.append((controller, scope))
        code = controller.wait(timeout=150)
        worker.wait(timeout=30)
        sdk = json.loads((output / "sdk-result.json").read_bytes())
        result["SDK_result"] = reference(output / "sdk-result.json")
        if code != 0 or sdk.get("passed") is not True:
            raise RuntimeError("Actual SDK construction control failed; retain its evidence")
        result.update(passed=True)
    except BaseException as error:
        result.update(error={"type": type(error).__name__, "message": str(error)}, traceback=traceback.format_exc())
    finally:
        quiet = []
        for process, scope in reversed(processes):
            try:
                quiet.append(stop_owned(scope))
                process.wait(timeout=20)
                assert_outer_launcher_exited(scope)
            except BaseException as error:
                result.update(passed=False, final_stop_error=str(error))
        if processes and len(quiet) == len(processes) and "final_stop_error" not in result:
            proof = write_new(output / "quiescence.json", {"all_quiet": True,
                "stopped": quiet, "outer_launcher_reaped": True})
            result["quiescence"] = proof
            try:
                if clone is not None:
                    retained = [preparation_ref, reference(output / "worker-ready.json")]
                    if result.get("SDK_result"):
                        retained.append(result["SDK_result"])
                    result["cleanup"] = cleanup_episode_rootfs(clone["rootfs"], output,
                        reference(clone["rootfs_manifest"]), proof, retained)
            except BaseException as error:
                result.update(passed=False, cleanup_error=str(error))
        if resources is not None:
            try:
                result["resource_release"] = release_episode_resources(resources)
            except BaseException as error:
                result.update(passed=False, resource_release_error=str(error))
        write_new(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "output": str(output),
                      **({"error": result["error"]} if "error" in result else {})}))
    return 0 if result["passed"] else 1


def main():
    if sys.argv[1:2] == ["--inside"]:
        return inside(sys.argv[2])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--resident-ready", required=True, type=Path)
    parser.add_argument("--prepared-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return host(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
