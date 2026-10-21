"""SDK controller for one already claimed slot; stdin/stdout belong to isolated tools."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    output = Path(config["output"])
    os.environ["OH_PERSISTENCE_DIR"] = str(output / "empty-user-config")
    from proworksim.software_benchmark_candidates_v054 import write_new
    from proworksim.software_benchmark_owner_ipc_v054 import OwnerClient
    from proworksim.software_benchmark_runner_transport_v054 import (
        GuardedRefAdapter, HostDeadline, RemoteMatchAdapter, RemoteProjectOwner,
    )
    from proworksim.software_benchmark_native_binding_v054 import NativeToolRPC
    from proworksim.storage import atomic_write, json_bytes
    write_new(output / "controller-ready.json", {"trusted_SDK_imports_complete": True,
              "model_calls": 0, "tool_calls": 0})
    while not Path(config["start"]).exists():
        time.sleep(0.05)
    start = json.loads(Path(config["start"]).read_text())
    from proworksim.software_benchmark_interleaved_transport_v054 import (
        interleaved, owner_client, InterleavedHostDeadline, InterleavedMatchAdapter,
        InterleavedProjectOwner, unwrap_interleave_boundary, context_transport as interleaved_context,
    )
    concurrent = interleaved(config["model_identity_value"])
    gate = InterleavedHostDeadline(start) if concurrent else HostDeadline(start)
    rpc = NativeToolRPC(ready=json.loads(Path(config["ready"]).read_text()),
                        reader=sys.stdin, writer=sys.stdout)
    result = {"version": "v054-single-slot-controller-v1", "arm": config["arm"],
              "status": "running", "preparation_only": config["preparation_only"],
              "actual_model_calls": 0 if config["preparation_only"] else None,
              "hidden_grader_calls": 0, "hidden_feedback_received": False}
    conversation = runtime = None
    try:
        if config["arm"] in {"REF", "MATCH"}:
            from proworksim.software_benchmark_exact_transport_v054 import (
                LoopbackHTTP, RefExactAdapter, build_llm,
            )
            from proworksim.software_benchmark_native_binding_v054 import build_isolated_conversation
            if config["arm"] == "REF":
                transport = LoopbackHTTP(config["ref_endpoint"])
                if not config["preparation_only"]:
                    if config.get("ref_session_token"):
                        from proworksim.software_benchmark_ref_resident_v054 import SessionAuthenticatedLoopbackHTTP
                        transport = SessionAuthenticatedLoopbackHTTP(
                            config["ref_endpoint"], config["ref_api_key_file"], config["ref_session_token"])
                    else:
                        from proworksim.software_benchmark_ref_deployment_v054 import AuthenticatedLoopbackHTTP
                        transport = AuthenticatedLoopbackHTTP(config["ref_endpoint"], config["ref_api_key_file"])
                original = RefExactAdapter(
                    transport=transport, folder=output / "ref-ledger",
                    slot_id=config["slot_id"], seed=config["seed"],
                    service_identity=config["model_identity_value"],
                    execution_authorized=not config["preparation_only"],
                    programmed_http_fixture=config["preparation_only"])
                adapter = GuardedRefAdapter(original, gate, start["started"])
            else:
                adapter_type = InterleavedMatchAdapter if concurrent else RemoteMatchAdapter
                adapter = adapter_type(
                    owner_client(config["model_socket"], config["model_identity_value"],
                                 guard_path=start["guard_path"], hard_deadline=start["hard_at"]),
                    gate, output / "match-ledger-copy")
            llm = build_llm(adapter)
            conversation = build_isolated_conversation(
                llm, rpc=rpc, persistence_dir=output / "native-conversation")
            conversation.send_message(config["public_task"]["problem_statement"])
            from proworksim.software_benchmark_normal_boundary_v054 import unwrap_normal_boundary
            try:
                conversation.run()
            except BaseException as error:
                queue_boundary = unwrap_interleave_boundary(error) if concurrent else None
                boundary = queue_boundary or unwrap_normal_boundary(error)
                if boundary is None:
                    raise
                snapshot = adapter.ledger.snapshot()
                if (snapshot.get("complete_actual_tokens") is None
                        or snapshot.get("inflight") is not None
                        or snapshot.get("uncertain_reserved_tokens", 0)
                        or snapshot["complete_actual_tokens"] != snapshot["known_actual_tokens"]):
                    raise RuntimeError("A normal boundary cannot conceal uncertain model usage")
                if queue_boundary is not None:
                    result["scheduler_boundary"] = queue_boundary.evidence
                result["terminal_boundary"] = {"reason": str(boundary),
                    "known_usage": True, "generation_retried": False}
            result.update(
                actual_SDK_conversation_run=True, tool_calls=len(rpc.transcript),
                native_interface_unchanged=True, ledger=adapter.ledger.snapshot(),
                common_agent_condenser_ledger=True)
            conversation.close()
            conversation = None
        else:
            from transformers import AutoTokenizer
            from proworksim.repository_sources_v054 import RepositorySources
            from proworksim.software_benchmark_world_v054 import build_software_collaboration_case
            from proworksim.software_benchmark_managed_v054 import build_runtime
            from proworksim.software_calibration_collector_v051 import (
                DispatchDeadline, SoftwareContextTransport, _CollectionOwner,
                budget_snapshot, close_runtime, context_transport, run_fragment,
            )
            client = owner_client(config["model_socket"], config["model_identity_value"],
                                  guard_path=start["guard_path"], hard_deadline=start["hard_at"])
            tokenizer = AutoTokenizer.from_pretrained(config["model_local"], local_files_only=True)
            owner_type = InterleavedProjectOwner if concurrent else RemoteProjectOwner
            owner = owner_type(client, tokenizer, gate, window_id=start["window_id"])
            public_client = OwnerClient(config["public_test_socket"], config["public_test_identity"], timeout=1860)
            public_number = 0

            def public_tests(*, files, entry_metadata, task, run_root):
                nonlocal public_number
                public_number += 1
                path = output / ("public-test-input-" + str(public_number) + ".json")
                bundle = write_new(path, {"files": files, "entry_metadata": entry_metadata})
                return public_client.call("run_public_tests", bundle=bundle)

            provider = RepositorySources(config["source_manifest"], runner=public_tests)
            prepared = build_software_collaboration_case(
                config["public_task"]["instance_id"], output / "managed-world", provider=provider)
            deadline = DispatchDeadline()
            deadline.started = deadline.last_clock = start["started"]
            deadline.soft_at, deadline.hard_at = start["soft_at"], start["hard_at"]
            context = (interleaved_context(owner, output / "managed-transport", deadline)
                       if concurrent else context_transport(owner, output / "managed-transport", deadline,
                                                           transport_factory=SoftwareContextTransport))
            facade = _CollectionOwner(owner, context)
            runtime, _, _ = build_runtime(facade, prepared, output / "managed-runtime", deadline=deadline)
            boundary = run_fragment(prepared, runtime, on_opportunity=lambda outcome: atomic_write(
                output / "managed-live-ledger.json", json_bytes(budget_snapshot(runtime, prepared))))
            if concurrent and context.native_dispatch_gate.scheduler_boundaries:
                boundary["administrative_framework_closure_reason"] = boundary["closure_reason"]
                boundary["scheduler_boundaries"] = context.native_dispatch_gate.scheduler_boundaries
                boundary["closure_reason"] = "interleaved_request_queue_deadline_before_dispatch"
                result["scheduler_boundaries"] = boundary["scheduler_boundaries"]
            write_new(output / "managed-boundary.json", boundary)
            ledger = budget_snapshot(runtime, prepared)
            result.update(actual_managed_S1_runtime=True, original_Gamma1_transport=True,
                          actual_SDK_worker=True, ledger=ledger,
                          actions=runtime.actions, opportunities=runtime.opportunities,
                          closure_reason=boundary["closure_reason"],
                          execution_integrity_failure=boundary["execution_integrity_failure"],
                          public_test_calls=public_number)
            close_runtime(runtime)
            runtime = None
            if boundary["execution_integrity_failure"]:
                raise RuntimeError("Managed execution integrity failed; no replay")
        rpc.close(timeout_seconds=min(10, max(.01, start["hard_at"] - time.monotonic())))
        write_new(output / "native-rpc-transcript.json", rpc.transcript)
        result.update(status="closed", candidate_selected=False,
                      writer_shutdown_requested=True, process_tree_quiescence_proven=False)
    except BaseException as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      traceback=traceback.format_exc(), automatic_retry=False)
    finally:
        if conversation is not None:
            conversation.close()
        if runtime is not None:
            from proworksim.software_calibration_collector_v051 import close_runtime
            close_runtime(runtime)
        write_new(output / "controller-result.json", result)
    return 0 if result["status"] == "closed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
