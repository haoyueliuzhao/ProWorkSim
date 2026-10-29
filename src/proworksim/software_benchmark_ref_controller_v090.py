"""Explicit v090 REF session factory, currently admitted for scripted CPU only.

This owns the real SDK call path and controller result, but not a Docker PID1,
worker process tree, candidate export or scorer. Those production paths remain
uninstalled. A closed session is not a solved task or proven writer quiescence.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import time
import traceback

from . import software_benchmark_native_control_v090 as control
from . import software_benchmark_public_feedback_v090 as feedback
from .software_benchmark_candidates_v054 import write_new
from .software_benchmark_exact_transport_v057 import assert_response_projection_healthy
from .software_benchmark_normal_boundary_v064 import GuardedModelAdapter, unwrap_normal_boundary
from .software_benchmark_qwen_truncation_v090 import ReasoningTruncationAdapter, unwrap_local_boundary
from .software_benchmark_ref_budget_v064 import validate_condition
from .software_benchmark_runner_transport_v054 import HostDeadline
from .storage import json_bytes

VERSION = "v090-scripted-ref-controller-session-r1"


def run_scripted_session(*, delegate, native_rpc_type, native_rpc_kwargs, condition,
                         public_task, public_context, public_python, output, workspace, started):
    """Run a real native conversation using only explicitly scripted dependencies.

    The command entrypoint additionally blocks network, GPU, weights and process
    execution. These fixture labels are not production authorization tokens.
    """
    output, workspace = Path(output).resolve(), Path(workspace).resolve()
    limits = validate_condition(condition)
    if (getattr(delegate, "scripted_cpu_only", False) is not True
            or getattr(native_rpc_type, "scripted_cpu_only", False) is not True
            or condition.get("model_key") != "QWEN" or condition.get("arm") != "REF"
            or getattr(delegate, "condition", None) != condition
            or not isinstance(public_task, str) or not public_task.strip()
            or not isinstance(public_context, str) or not workspace.is_dir()
            or Path(started.get("guard_path", "")).resolve() != output / "guard.json"):
        raise ValueError("This controller factory currently admits only an identified scripted Qwen REF control")
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "guard.json", {"stop_requested": False, "request_deadline": None})
    result = {
        "version": VERSION, "measurement_kind": "scripted_cpu_control",
        "slot_id": delegate.slot_id, "source_slot_id": delegate.slot_id,
        "condition_id": condition["condition_id"], "arm": "REF", "model_key": "QWEN",
        "status": "running", "preparation_only": True,
        "production_dispatch_authorized": False, "native_finished": False,
        "normal_completion": False, "code_resolved": None,
        "candidate_exported": False, "official_scoring_performed": False,
        "writer_shutdown_requested": False, "process_tree_quiescence_proven": False,
        "requires_external_writer_quiescence_and_original_export": True,
        "inference_recipe_and_budget_configuration_changed": False,
        "execution_and_response_projection_changed": True,
        "automatic_retry": False,
        "execution_revisions": {"controller": VERSION, "guidance": control.VERSION,
                                "feedback": feedback.VERSION},
    }
    events, conversation, adapter, rpc = [], None, None, None

    def durable(name, value):
        with (output / name).open("ab") as stream:
            stream.write(json_bytes(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def policy_event(value):
        events.append(copy.deepcopy(value))
        durable("execution-policy-events.jsonl", value)

    try:
        rpc = feedback.feedback_rpc_class(native_rpc_type)(**native_rpc_kwargs)
        rpc.public_python = public_python
        rpc.raw_sink = lambda event: durable("native-rpc-raw.jsonl", event)
        rpc.feedback_sink = lambda event: durable("public-feedback-projections.jsonl", event)
        guarded = GuardedModelAdapter(delegate, HostDeadline(started), started["started"])
        adapter = ReasoningTruncationAdapter(guarded, folder=output / "qwen-truncation",
            workspace_id=delegate.slot_id,
            progress_snapshot=lambda: {"tool_rpc_count": len(rpc.transcript)})
        result["execution_revisions"]["truncation"] = adapter.policy_reference
        conversation = control.create_conversation(adapter, rpc, output, limits, workspace=workspace)
        conversation.send_message(control.initial_message(public_task, public_context=public_context))
        try:
            result["execution_policy"] = control.run_controlled_conversation(
                conversation, adapter=adapter, started=started, limits=limits, event_sink=policy_event)
        except BaseException as error:
            boundary = unwrap_local_boundary(error, adapter)
            if boundary is not None:
                result["terminal_boundary"] = boundary
            else:
                original = unwrap_normal_boundary(error)
                if original is None:
                    raise
                result["terminal_boundary"] = {"reason": str(original), "known_usage": True,
                                               "kind": "original_resource_boundary"}
        assert_response_projection_healthy(adapter)
        # Reuse exactly the host's pure accounting gate; this does not run Docker.
        from .software_benchmark_episode_v066 import validate_closed_usage
        result["ledger"] = validate_closed_usage(adapter.ledger.snapshot(), limits)
        status = conversation.state.execution_status
        state = {"execution_status": getattr(status, "value", str(status)),
                 "max_iterations": limits["agent_decisions"],
                 "full_event_history": str(output / "native-conversation")}
        write_new(output / "sdk-terminal-state.json", state)
        result.update(actual_SDK_conversation_run=True, common_agent_condenser_ledger=True,
            sdk_execution_status=state["execution_status"], tool_calls=len(rpc.transcript),
            native_finished=state["execution_status"] == "finished",
            normal_completion=state["execution_status"] == "finished" and "terminal_boundary" not in result)
        # A new truncation stop is neither native finish nor a success label.
        if result.get("terminal_boundary", {}).get("kind") == "settled_output_truncation":
            result.update(native_finished=False, normal_completion=False)
        conversation.close()
        conversation = None
        rpc.close(timeout_seconds=min(10, max(.01, started["hard_at"] - time.monotonic())))
        result.update(status="closed", writer_shutdown_requested=True)
    except BaseException as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      traceback=traceback.format_exc())
    finally:
        if conversation is not None:
            try:
                conversation.close()
            except BaseException as error:
                result.update(status="technical_unknown", conversation_cleanup_error={
                    "type": type(error).__name__, "message": str(error)})
        if rpc is not None:
            if not result["writer_shutdown_requested"]:
                try:
                    rpc.close(timeout_seconds=10)
                    result["writer_shutdown_requested"] = True
                except BaseException as error:
                    result.update(status="technical_unknown", rpc_cleanup_error={
                        "type": type(error).__name__, "message": str(error)})
            write_new(output / "native-rpc-transcript.json", rpc.transcript)
            write_new(output / "public-feedback-events.json", rpc.feedback_events)
        if adapter is not None:
            result["ledger"] = adapter.ledger.snapshot()
            result["truncation_policy"] = adapter.truncation_snapshot()
        write_new(output / "execution-policy-events.json", events)
        result["execution_policy_observed_counts"] = {
            phase: sum(e["kind"] == "policy_message_sent" and e["phase"] == phase for e in events)
            for phase in ("stuck_correction", "finish_review")}
        write_new(output / "controller-result.json", result)
    return result
