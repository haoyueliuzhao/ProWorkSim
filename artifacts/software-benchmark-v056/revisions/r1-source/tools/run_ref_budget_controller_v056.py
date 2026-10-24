"""One native OpenHands Qwen REF episode under its predeclared budget condition."""
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
    parser.add_argument("--config", required=True, type=Path)
    config = json.loads(parser.parse_args().config.read_bytes())
    output = Path(config["output"])
    os.environ["OH_PERSISTENCE_DIR"] = str(output / "empty-user-config")
    from openhands.sdk import Conversation
    from proworksim.software_benchmark_candidates_v054 import checked, write_new
    from proworksim.software_benchmark_exact_transport_v054 import build_llm
    from proworksim.software_benchmark_native_binding_v054 import NativeToolRPC, build_isolated_agent
    from proworksim.software_benchmark_normal_boundary_v054 import unwrap_normal_boundary
    from proworksim.software_benchmark_ref_budget_v056 import BudgetRefAdapter, validate_condition
    from proworksim.software_benchmark_ref_deployment_v054 import AuthenticatedLoopbackHTTP
    from proworksim.software_benchmark_runner_transport_v054 import GuardedRefAdapter, HostDeadline
    condition = json.loads(checked(config["configuration"]).read_bytes())
    limits = validate_condition(condition)
    if not Path("/testbed").is_dir():
        raise ValueError("The SDK must view the actual isolated actor checkout")
    write_new(output / "controller-ready.json", {"trusted_SDK_imports_complete": True,
              "model_calls": 0, "tool_calls": 0})
    while not Path(config["start"]).exists():
        time.sleep(.05)
    start = json.loads(Path(config["start"]).read_bytes())
    result = {"version": "v056-ref-budget-controller-r1", "arm": "REF",
              "condition_id": condition["condition_id"], "slot_id": config["slot_id"],
              "status": "running", "preparation_only": False,
              "hidden_feedback_received": False, "automatic_retry": False}
    conversation = adapter = None
    rpc = NativeToolRPC(ready=json.loads(Path(config["ready"]).read_bytes()), reader=sys.stdin,
                        writer=sys.stdout, response_timeout_seconds=limits["hard_seconds"])
    try:
        original = BudgetRefAdapter(
            transport=AuthenticatedLoopbackHTTP(config["ref_endpoint"], config["ref_api_key_file"]),
            folder=output / "ref-ledger", slot_id=config["slot_id"], seed=config["seed"],
            service_identity=config["model_identity_value"], condition=condition)
        adapter = GuardedRefAdapter(original, HostDeadline(start), start["started"])
        llm = build_llm(adapter)
        conversation = Conversation(
            agent=build_isolated_agent(llm, rpc=rpc), workspace="/testbed",
            persistence_dir=output / "native-conversation", plugins=[],
            max_iteration_per_run=limits["agent_decisions"], stuck_detection=True,
            visualizer=None, delete_on_close=False)
        conversation.send_message(config["public_task"]["problem_statement"])
        try:
            conversation.run()
        except BaseException as error:
            boundary = unwrap_normal_boundary(error)
            if boundary is None:
                raise
            ledger = adapter.ledger.snapshot()
            if (ledger["complete_actual_tokens"] is None or ledger["inflight"] is not None
                    or ledger["uncertain_reserved_tokens"]):
                raise RuntimeError("A limit boundary cannot conceal uncertain usage") from error
            result["terminal_boundary"] = {"reason": str(boundary), "known_usage": True}
        ledger = adapter.ledger.snapshot()
        if ledger["complete_actual_tokens"] is None or ledger["inflight"] or ledger["uncertain_reserved_tokens"]:
            raise RuntimeError("SDK return cannot conceal uncertain model usage")
        result.update(actual_SDK_conversation_run=True, common_agent_condenser_ledger=True,
                      tool_calls=len(rpc.transcript), ledger=ledger)
        status = conversation.state.execution_status
        state = {"execution_status": getattr(status, "value", str(status)),
                 "max_iterations": limits["agent_decisions"],
                 "actual_iteration_count": None,
                 "full_event_history": str(output / "native-conversation")}
        write_new(output / "sdk-terminal-state.json", state)
        result["sdk_execution_status"] = state.get("execution_status")
        result["sdk_iteration_limit"] = state["max_iterations"]
        result["native_finished"] = state["execution_status"] == "finished"
        result["normal_completion"] = result["native_finished"] and "terminal_boundary" not in result
        # Preserve SDK state even when no transport exception crosses conversation.run().
        result["termination_requires_sdk_event_classification"] = "terminal_boundary" not in result
        conversation.close()
        conversation = None
        rpc.close(timeout_seconds=min(10, max(.01, start["hard_at"] - time.monotonic())))
        write_new(output / "native-rpc-transcript.json", rpc.transcript)
        result.update(status="closed", writer_shutdown_requested=True,
                      process_tree_quiescence_proven=False)
    except BaseException as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      traceback=traceback.format_exc())
        if adapter is not None:
            result["ledger"] = adapter.ledger.snapshot()
    finally:
        if conversation is not None:
            conversation.close()
        write_new(output / "controller-result.json", result)
    return 0 if result["status"] == "closed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
