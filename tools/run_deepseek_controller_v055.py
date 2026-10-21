"""One trusted v055 SDK controller; model HTTPS never passes through a proxy."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import time
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    config = json.loads(parser.parse_args().config.read_text())
    output = Path(config["output"])
    os.environ["OH_PERSISTENCE_DIR"] = str(output / "empty-user-config")
    from proworksim.software_benchmark_candidates_v054 import write_new
    from proworksim.software_benchmark_deepseek_api_v055 import DeepSeekClient, load_api_key
    from proworksim.software_benchmark_deepseek_interfaces_v055 import (
        DeepSeekAdapter, NATIVE_TOOLS, build_native_llm, unwrap_boundary,
    )
    from proworksim.software_benchmark_native_binding_v054 import NativeToolRPC
    from proworksim.storage import atomic_write, json_bytes
    write_new(output / "controller-ready.json", {
        "version": "v055-deepseek-controller-ready-r1", "model_calls": 0,
        "trusted_SDK_imports_complete": True, "network": "official_direct_HTTPS"})
    while not Path(config["start"]).exists():
        time.sleep(0.05)
    start = json.loads(Path(config["start"]).read_text())
    rpc = NativeToolRPC(ready=json.loads(Path(config["ready"]).read_text()),
                        reader=sys.stdin, writer=sys.stdout)
    result = {"version": "v055-deepseek-controller-result-r1", "arm": config["arm"],
        "slot_id": config["slot_id"], "condition_id": config["condition_id"],
        "thinking": config["thinking"], "status": "running", "entered_model": False,
        "hidden_grader_calls": 0, "hidden_feedback_received": False,
        "web_search_tool_available": False, "seed_supported_by_provider": False,
        "local_planned_seed": config["seed"]}
    conversation = runtime = adapter = None
    try:
        prepared = None
        public_number = 0
        if config["arm"] == "PROJECT":
            from proworksim.repository_sources_v054 import RepositorySources
            from proworksim.software_benchmark_world_v054 import build_software_collaboration_case
            from proworksim.software_benchmark_managed_v054 import managed_port
            from proworksim.software_benchmark_owner_ipc_v054 import OwnerClient
            from proworksim.model_policy import CONTROL_TOOLS
            public_client = OwnerClient(config["public_test_socket"], config["public_test_identity"], timeout=1860)

            def public_tests(*, files, entry_metadata, task, run_root):
                nonlocal public_number
                public_number += 1
                bundle = write_new(output / f"public-test-input-{public_number}.json",
                                   {"files": files, "entry_metadata": entry_metadata})
                return public_client.call("run_public_tests", bundle=bundle)

            provider = RepositorySources(config["source_manifest"], runner=public_tests)
            prepared = build_software_collaboration_case(config["public_task"]["instance_id"],
                                                       output / "managed-world", provider=provider)
            names = {row["name"] for row in managed_port(prepared).tools()} | {row["name"] for row in CONTROL_TOOLS}
        else:
            names = NATIVE_TOOLS
        counter_config = config.get("context_counter")
        if counter_config is None:
            raise ValueError("Freeze an explicit remote context counter before formal execution")
        counter = importlib.import_module(counter_config["module"]).build_counter(counter_config)
        client = DeepSeekClient(ledger_path=config["ledger_path"],
            api_key=load_api_key(config["api_key_file"]), allowed_tool_names=names,
            max_concurrency=config.get("max_api_concurrency", 64),
            timeout_seconds=1800 if config["arm"] == "REF" else 600)
        adapter = DeepSeekAdapter(client=client, arm=config["arm"], thinking=config["thinking"],
            slot_id=config["slot_id"], condition_id=config["condition_id"],
            folder=output / "deepseek-ledger", allowed_tool_names=names, counter=counter,
            soft_at=start["soft_at"], hard_at=start["hard_at"])
        if config["arm"] in {"REF", "MATCH"}:
            from proworksim.software_benchmark_native_binding_v054 import build_isolated_conversation
            conversation = build_isolated_conversation(build_native_llm(adapter), rpc=rpc,
                                                       persistence_dir=output / "native-conversation")
            conversation.send_message(config["public_task"]["problem_statement"])
            try:
                conversation.run()
            except BaseException as error:
                boundary = unwrap_boundary(error)
                if boundary is None:
                    raise
                result["terminal_boundary"] = str(boundary)
            result.update(actual_SDK_conversation_run=True, native_interface_unchanged=True,
                          common_agent_condenser_ledger=True, tool_calls=len(rpc.transcript))
            conversation.close()
            conversation = None
        else:
            from proworksim.software_benchmark_deepseek_managed_v055 import RemoteProjectOwner, build_runtime
            from proworksim.software_calibration_collector_v051 import (
                DispatchDeadline, budget_snapshot, close_runtime, run_fragment,
            )
            owner = RemoteProjectOwner(adapter, window_id=config["slot_id"])
            deadline = DispatchDeadline()
            deadline.started = deadline.last_clock = start["started"]
            deadline.soft_at, deadline.hard_at = start["soft_at"], start["hard_at"]
            runtime, _, _ = build_runtime(owner, prepared, output / "managed-runtime", deadline=deadline)
            boundary = run_fragment(prepared, runtime, on_opportunity=lambda outcome: atomic_write(
                output / "managed-live-ledger.json", json_bytes(budget_snapshot(runtime, prepared))))
            write_new(output / "managed-boundary.json", boundary)
            result.update(actual_managed_S1_runtime=True, actual_SDK_worker=True,
                Gamma1_information_transform_retained=True,
                remote_usage_evidence_replaces_unavailable_token_trace=True,
                managed_ledger=budget_snapshot(runtime, prepared), actions=runtime.actions,
                opportunities=runtime.opportunities, closure_reason=boundary["closure_reason"],
                execution_integrity_failure=boundary["execution_integrity_failure"],
                public_test_calls=public_number)
            close_runtime(runtime)
            runtime = None
            if boundary["execution_integrity_failure"]:
                raise RuntimeError("Managed execution integrity failed; no replay")
        rpc.close(timeout_seconds=min(10, max(.01, start["hard_at"] - time.monotonic())))
        write_new(output / "native-rpc-transcript.json", rpc.transcript)
        result.update(status="budget_exhausted" if adapter.halted == "global_cny_budget_pre_dispatch_stop"
                      else "closed", candidate_selected=False, writer_shutdown_requested=True,
                      process_tree_quiescence_proven=False)
    except BaseException as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      traceback=traceback.format_exc(), automatic_retry=False)
    finally:
        if conversation is not None:
            conversation.close()
        if runtime is not None:
            from proworksim.software_calibration_collector_v051 import close_runtime
            close_runtime(runtime)
        if adapter is not None:
            result["ledger"] = adapter.ledger.snapshot()
            result["entered_model"] = adapter.ledger.attempts > 0
            result["actual_model_calls"] = adapter.ledger.attempts
        write_new(output / "controller-result.json", result)
    return 0 if result["status"] in {"closed", "budget_exhausted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
