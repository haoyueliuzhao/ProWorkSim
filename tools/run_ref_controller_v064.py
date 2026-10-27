"""Repaired native REF controller for either fixed v064 model backend."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback


def validate_config(config):
    allowed = {"version", "slot_id", "source_slot_id", "seed", "condition_id", "execution_arm",
               "configuration", "public_task", "ref_endpoint", "model_identity_value", "output",
               "start", "ready", "diagnostic", "measurement_kind", "public_context",
               "public_environment", "lifecycle_deadline", "maximum_lifecycle_seconds", "model_key"}
    if (config.get("version") != "v064-private-native-controller-r1"
            or set(config) - allowed or not str(config.get("slot_id", "")).startswith("v064:")
            or config.get("output") != "/pws/output" or config.get("start") != "/pws/control/start.json"
            or config.get("ready") != "/pws/control/actor-ready.json"
            or config.get("configuration", {}).get("path") != "/pws/control/condition.json"
            or config.get("ref_api_key_file") is not None
            or config.get("measurement_kind") not in {"full_verified_comparison", "zero_model_diagnostic"}
            or type(config.get("diagnostic")) is not bool
            or config["diagnostic"] != (config["measurement_kind"] == "zero_model_diagnostic")
            or config.get("execution_arm") != "REF" or config.get("model_key") not in {"QWEN", "DEEPSEEK"}
            or set(config.get("public_task", {})) != {"instance_id", "repo", "base_commit", "problem_statement"}):
        raise ValueError("Private controller configuration changes the fixed layout or exposes a model key")
    if (set(config.get("public_context", {})) != {"version", "visible_text", "visible_facts"}
            or not isinstance(config["public_context"]["visible_text"], str)):
        raise ValueError("FIX requires only the admitted public projection, without source references")
    return config


def feedback_rpc_class(base):
    """The frozen base class archives raw wire observations before projection."""
    from proworksim.software_benchmark_public_context_v062 import project_terminal_feedback

    class FeedbackRPC(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.feedback_events, self.feedback_projections = [], []

        def request(self, tool, action, *, timeout_seconds=None):
            raw = super().request(tool, action, timeout_seconds=timeout_seconds)
            if getattr(self, "raw_sink", None) is not None:
                self.raw_sink(self.transcript[-1])
            projected = project_terminal_feedback(raw, public_python=self.public_python)
            self.feedback_events.extend(projected["events"])
            if projected["events"]:
                evidence = {"request_id": raw.get("id"), "events": projected["events"],
                            "model_visible_llm_content": projected["response"]["llm_content"]}
                self.feedback_projections.append(evidence)
                if getattr(self, "feedback_sink", None) is not None:
                    self.feedback_sink(evidence)
            return projected["response"]
    return FeedbackRPC


def create_conversation(config, adapter, rpc, output, limits, *, workspace="/testbed"):
    if config["model_key"] == "QWEN":
        from proworksim.software_benchmark_native_control_v062 import create_conversation as fixed
        return fixed(adapter, rpc, output, limits, workspace=workspace)
    from openhands.sdk import Conversation
    from proworksim.software_benchmark_deepseek_adapter_v064 import build_native_llm
    from proworksim.software_benchmark_native_binding_v054 import build_isolated_agent
    llm = build_native_llm(adapter, normalization_folder=output / "sdk-response-projections")
    return Conversation(agent=build_isolated_agent(llm, rpc=rpc), workspace=workspace,
        persistence_dir=output / "native-conversation", plugins=[],
        max_iteration_per_run=limits["agent_decisions"], stuck_detection=True,
        visualizer=None, delete_on_close=False)


def install_lifecycle_deadline(config):
    maximum, deadline = config.get("maximum_lifecycle_seconds"), config.get("lifecycle_deadline")
    if (type(maximum) is not int or maximum != (180 if config["diagnostic"] else 24000)
            or type(deadline) not in (int, float)):
        raise ValueError("A fixed internal controller lifetime is required")
    remaining = deadline - time.monotonic()
    if not 0 < remaining <= maximum:
        raise ValueError("Controller lifetime is expired or exceeds its reviewed bound")
    signal.signal(signal.SIGALRM, lambda _signum, _frame: os._exit(124))
    signal.setitimer(signal.ITIMER_REAL, remaining)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    config = validate_config(json.loads(parser.parse_args().config.read_bytes()))
    if os.getpid() != 1 or not Path("/testbed").is_dir():
        raise ValueError("Controller must be PID1 with the actual private actor checkout at /testbed")
    install_lifecycle_deadline(config)
    output = Path(config["output"])
    os.environ["OH_PERSISTENCE_DIR"] = str(output / "empty-user-config")
    from proworksim.software_benchmark_candidates_v054 import checked, write_new
    from proworksim.software_benchmark_native_binding_v054 import NativeToolRPC
    from proworksim.software_benchmark_native_v054 import initialized_interface_manifest
    from proworksim.software_benchmark_normal_boundary_v064 import unwrap_normal_boundary, GuardedModelAdapter
    from proworksim.software_benchmark_ref_budget_v064 import validate_condition, PairedQwenAdapter
    from proworksim.software_benchmark_model_fifo_v064 import FifoModelTransport
    from proworksim.software_benchmark_runner_transport_v054 import HostDeadline
    from proworksim.software_benchmark_public_context_v062 import (
        terminal_initialization_action, validate_terminal_initialization,
    )
    from proworksim.software_benchmark_native_control_v062 import initial_message, run_controlled_conversation
    from proworksim.software_benchmark_exact_transport_v057 import assert_response_projection_healthy

    condition = json.loads(checked(config["configuration"]).read_bytes())
    limits = validate_condition(condition)
    write_new(output / "controller-ready.json", {"trusted_SDK_imports_complete": True,
              "version": config["version"], "model_calls": 0, "tool_calls": 0})
    wait_until = time.monotonic() + 120
    while not Path(config["start"]).exists():
        if time.monotonic() >= wait_until:
            raise TimeoutError("Host did not admit controller start within the startup boundary")
        time.sleep(.05)
    start = json.loads(Path(config["start"]).read_bytes())
    if start.get("guard_path") != "/pws/output/guard.json":
        raise ValueError("Controller guard must stay inside its private output")
    result = {"version": config["version"], "arm": "REF", "condition_id": condition["condition_id"],
              "slot_id": config["slot_id"], "source_slot_id": config["source_slot_id"],
              "execution_arm": config["execution_arm"], "model_key": config["model_key"],
              "measurement_kind": config["measurement_kind"], "status": "running",
              "preparation_only": config["diagnostic"], "hidden_feedback_received": False,
              "automatic_retry": False, "model_key_present": False,
              "inference_recipe_and_budget_configuration_changed": False,
              "execution_and_response_projection_changed": True}
    conversation = adapter = transport = None
    fixed = True
    protocol_events = []
    rpc_class = feedback_rpc_class(NativeToolRPC) if fixed else NativeToolRPC
    rpc = rpc_class(ready=json.loads(Path(config["ready"]).read_bytes()), reader=sys.stdin,
                        writer=sys.stdout, response_timeout_seconds=limits["hard_seconds"])
    if fixed:
        rpc.public_python = config["public_environment"]["public_python"]
        for name in ("execution-policy-events.jsonl", "public-feedback-projections.jsonl", "native-rpc-raw.jsonl"):
            (output / name).touch(exist_ok=False)

    def durable_event(name, event):
        with (output / name).open("a") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def policy_event(event):
        protocol_events.append(event)
        durable_event("execution-policy-events.jsonl", event)

    if fixed:
        rpc.feedback_sink = lambda event: durable_event("public-feedback-projections.jsonl", event)
        rpc.raw_sink = lambda event: durable_event("native-rpc-raw.jsonl", event)

    def termination(signum, frame):
        raise InterruptedError("Controller received termination signal " + str(signum))
    signal.signal(signal.SIGTERM, termination)
    signal.signal(signal.SIGINT, termination)

    try:
        if config["diagnostic"]:
            class NeverGenerate:
                maximum_input_tokens = 98304
                maximum_output_tokens = 32768
                temperature = .6

                def count(self, *args, **kwargs):
                    raise RuntimeError("No model call is permitted in the deployment control")

                complete = count
            conversation_adapter = NeverGenerate()
        else:
            transport = FifoModelTransport(config["ref_endpoint"])
            names = {"file_editor", "finish", "task_tracker", "terminal", "think"}
            if config["model_key"] == "QWEN":
                original = PairedQwenAdapter(transport=transport,
                    folder=output / "ref-ledger", slot_id=config["slot_id"], seed=config["seed"],
                    service_identity=config["model_identity_value"], condition=condition,
                    allowed_tools=names)
                adapter = GuardedModelAdapter(original, HostDeadline(start), start["started"])
            else:
                from proworksim.software_benchmark_deepseek_adapter_v064 import DeepSeekEpisodeAdapter
                adapter = DeepSeekEpisodeAdapter(post=transport.post, arm="REF",
                    folder=output / "ref-ledger", slot_id=config["slot_id"],
                    condition_id=config["condition_id"], token_budget=limits["input_plus_output_tokens"],
                    allowed_tool_names=names, soft_at=start["soft_at"], hard_at=start["hard_at"])
            conversation_adapter = adapter
        conversation = create_conversation(config, conversation_adapter, rpc, output, limits)
        if fixed:
            action = terminal_initialization_action(config["public_environment"])
            response = rpc.request("terminal", action, timeout_seconds=20)
            receipt = validate_terminal_initialization(response, public_environment=config["public_environment"])
            result["interpreter_initialization"] = write_new(output / "interpreter-initialization.json", receipt)
        if config["diagnostic"]:
            conversation.send_message("Zero-model deployment control; do not run inference.")
            interface = initialized_interface_manifest(conversation.agent)
            write_new(output / "initialized-interface.json", interface)
            expected_tools = ["file_editor", "finish", "task_tracker", "terminal", "think"]
            if sorted(interface["tool_schemas"]) != expected_tools:
                raise RuntimeError("Native five-tool interface changed")
            probe = Path("/testbed/.pws-v064-probe")
            if probe.exists():
                raise ValueError("The deployment probe path already belongs to the original repository")
            calls = [
                ("terminal", {"command": "printf 'v064-native-rpc-ok\\n'", "timeout": 10}),
                ("file_editor", {"command": "create", "path": str(probe), "file_text": "v064-private-metadata-view\n"}),
                ("file_editor", {"command": "view", "path": str(probe)}),
                ("task_tracker", {"command": "view"}),
            ]
            for name, action in calls:
                response = rpc.request(name, action, timeout_seconds=20)
                if response.get("observation", {}).get("is_error") is not False:
                    raise RuntimeError("Native deployment tool failed: " + name)
            if probe.read_text() != "v064-private-metadata-view\n":
                raise RuntimeError("Controller read-only view did not observe the real actor write")
            response = rpc.request("terminal", {"command": "rm -- /testbed/.pws-v064-probe", "timeout": 10},
                                   timeout_seconds=20)
            if response.get("observation", {}).get("is_error") is not False or probe.exists():
                raise RuntimeError("Deployment probe cleanup did not return the shared checkout")
            result.update(model_calls=0, diagnostic=True, diagnostic_rpc_calls=len(calls) + 1,
                          initialized_interface_sha256=interface["interface_sha256"],
                          actual_SDK_initialized=True, diagnostic_passed=True,
                          checks={"five_native_tools": True, "worker_controller_schema_match": True,
                                  "terminal": True, "file_editor": True, "task_tracker": True,
                                  "live_readonly_metadata_view": True, "temporary_probe_removed": True})
            if fixed:
                refusal = rpc.request("terminal", {"command": "pwd\npwd", "timeout": 10}, timeout_seconds=20)
                if (refusal["observation"]["is_error"] is not True
                        or not any(e["kind"] == "native_multiple_commands_feedback" for e in rpc.feedback_events)):
                    raise RuntimeError("FIX native format-refusal feedback did not preserve the original refusal")
                result["checks"].update(public_interpreter_verified=True, native_format_feedback_verified=True)
                result["diagnostic_rpc_calls"] += 2
        else:
            problem = config["public_task"]["problem_statement"]
            conversation.send_message(initial_message(problem,
                public_context=config["public_context"]["visible_text"]) if fixed else problem)
            try:
                if fixed:
                    result["execution_policy"] = run_controlled_conversation(conversation,
                        adapter=adapter, started=start, limits=limits, event_sink=policy_event)
                else:
                    conversation.run()
            except BaseException as error:
                boundary = unwrap_normal_boundary(error)
                if boundary is None:
                    raise
                ledger = adapter.ledger.snapshot()
                if ledger["complete_actual_tokens"] is None or ledger["inflight"] is not None or ledger["uncertain_reserved_tokens"]:
                    raise RuntimeError("A normal boundary cannot conceal uncertain usage") from error
                result["terminal_boundary"] = {"reason": str(boundary), "known_usage": True}
            if fixed:
                assert_response_projection_healthy(adapter)
            ledger = adapter.ledger.snapshot()
            if ledger["complete_actual_tokens"] is None or ledger["inflight"] or ledger["uncertain_reserved_tokens"]:
                raise RuntimeError("SDK return cannot conceal uncertain model usage")
            result.update(actual_SDK_conversation_run=True, common_agent_condenser_ledger=True,
                          tool_calls=len(rpc.transcript), ledger=ledger)
            status = conversation.state.execution_status
            state = {"execution_status": getattr(status, "value", str(status)),
                "max_iterations": limits["agent_decisions"], "actual_iteration_count": None,
                "full_event_history": str(output / "native-conversation")}
            write_new(output / "sdk-terminal-state.json", state)
            result.update(sdk_execution_status=state["execution_status"], sdk_iteration_limit=state["max_iterations"],
                native_finished=state["execution_status"] == "finished",
                normal_completion=state["execution_status"] == "finished" and "terminal_boundary" not in result,
                termination_requires_sdk_event_classification="terminal_boundary" not in result)
        conversation.close()
        conversation = None
        rpc.close(timeout_seconds=min(10, max(.01, start["hard_at"] - time.monotonic())))
        if config["diagnostic"]:
            result["checks"]["native_close_acknowledged"] = True
        result.update(status="closed", writer_shutdown_requested=True, process_tree_quiescence_proven=False)
    except BaseException as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      traceback=traceback.format_exc())
        if adapter is not None:
            result["ledger"] = adapter.ledger.snapshot()
    finally:
        if conversation is not None:
            try:
                conversation.close()
            except BaseException as error:
                result["conversation_cleanup_error"] = {"type": type(error).__name__, "message": str(error)}
                result["status"] = "technical_unknown"
        # Retain every observed request/response even if the SDK exits abnormally.
        write_new(output / "native-rpc-transcript.json", rpc.transcript)
        if fixed:
            write_new(output / "public-feedback-events.json", rpc.feedback_events)
            write_new(output / "execution-policy-events.json", protocol_events)
            result["execution_policy_observed_counts"] = {
                "stuck_corrections": sum(e["kind"] == "policy_message_sent" and e["phase"] == "stuck_correction"
                                         for e in protocol_events),
                "finish_reviews": sum(e["kind"] == "policy_message_sent" and e["phase"] == "finish_review"
                                      for e in protocol_events),
                "counted_from_durable_events_even_if_run_raised": True}
        if transport is not None:
            transport.close()
        write_new(output / "controller-result.json", result)
    return 0 if result["status"] == "closed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
