"""Exercise the actual SDK loop with programmed CPU replies, not a model."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def control(output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "runs/software-benchmark-v057"):
        raise ValueError("Use an independent v057 control directory")
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(output / "empty-user-config"),
        LITELLM_LOCAL_MODEL_COST_MAP="True", CUDA_VISIBLE_DEVICES="", NVIDIA_VISIBLE_DEVICES="void")
    counters = {"network_attempts": 0, "weight_opens": 0, "gpu_opens": 0}

    def audit(event, values):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            counters["network_attempts"] += 1
            raise AssertionError("Programmed CPU control cannot contact any network")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                counters["weight_opens"] += 1
                raise AssertionError("Programmed CPU control cannot load a model")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                counters["gpu_opens"] += 1
                raise AssertionError("Programmed CPU control cannot open a GPU")

    sys.addaudithook(audit)
    from openhands.sdk import Agent, Conversation
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    from proworksim.software_benchmark_exact_transport_v054 import REF_MODEL, exact_measure
    from proworksim.software_benchmark_exact_transport_v057 import build_llm
    from proworksim.software_benchmark_native_execution_v057 import (
        VERSION, STUCK_CORRECTION, run_conversation_once_or_recover,
    )
    from proworksim.software_benchmark_ref_budget_v056 import BudgetLedger
    from proworksim.storage import digest, json_bytes

    condition = json.loads((ROOT / "config/v056-condition-REF_B0500K.json").read_bytes())
    result = {"version": VERSION, "passed": False, "model_calls": 0, "official_scoring_calls": 0,
              "test_scope": "actual SDK, two built-in tools, programmed response/usage; not inference quality",
              "synthetic_token_units_not_actual_model_usage": True, "cases": []}

    class ScriptedAdapter:
        maximum_input_tokens, maximum_output_tokens, temperature = 98304, 32768, .6
        request_defaults = {"model": REF_MODEL, "max_tokens": 32768, "temperature": .6, "stream": False}

        def __init__(self, actions):
            self.ledger = BudgetLedger(condition)
            self.actions = list(actions)
            self.requests = []

        def count(self, request):
            # This control deliberately uses deterministic synthetic token units;
            # real tokenization and model capacity were admitted separately.
            ids = list(range(32 + len(request["messages"])))
            return exact_measure(request, ids, context_limit=131072,
                                 backend="synthetic_cpu_programmed_counter")

        def complete(self, request, usage_id):
            if not self.actions:
                raise AssertionError("SDK attempted an undeclared additional fixture response")
            self.requests.append(copy.deepcopy(request))
            action = self.actions.pop(0)
            measure = self.count(request)
            n = len(self.requests)
            self.ledger.reserve(measure, usage_id, {"fixture_request": n})
            name = "finish" if action == "finish" else "think"
            arguments = {"message": "CPU fixture finished"} if name == "finish" else {"thought": "same thought"}
            body = {"id": f"cpu-{id(self)}-{n}", "object": "chat.completion", "created": 0,
                "model": REF_MODEL, "choices": [{"index": 0, "finish_reason": "tool_calls",
                    "message": {"role": "assistant", "content": None, "reasoning": "fixture reasoning",
                        "tool_calls": [{"id": f"fixture-call-{n}", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)}}]}}],
                "usage": {"prompt_tokens": measure["prompt_tokens"], "completion_tokens": 8,
                          "total_tokens": measure["prompt_tokens"] + 8,
                          "completion_tokens_details": {"reasoning_tokens": 2}}}
            self.ledger.settle(body, {"fixture_response": n, "sha256": digest(json_bytes(body))})
            return body

    try:
        for label, sequence, expected_status, expected_calls in (
                ("stuck_then_finish", ["think"] * 4 + ["finish"], "finished", 5),
                ("second_stuck_not_resumed", ["think"] * 8, "stuck", 8),
                ("production_five_tool_factory", ["think"] * 4 + ["finish"], "finished", 5)):
            folder = output / label
            workspace = folder / "workspace"
            workspace.mkdir(parents=True)
            adapter = ScriptedAdapter(sequence)
            rpc = None
            if label == "production_five_tool_factory":
                spec = importlib.util.spec_from_file_location("v057_controller_control",
                    ROOT / "tools/run_ref_budget_controller_v057.py")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                ready_path = ROOT / ("runs/software-benchmark-v056/episodes/"
                    "6d3849656aa3d6c683050ae41d11d5c607a7ea89713cb16bfc5f5d40d4fab15f/worker-ready.json")

                class ForbiddenRPC:
                    _bound = False
                    session_id = "v057_native_execution_cpu"
                    ready = json.loads(ready_path.read_bytes())
                    calls = 0

                    def request(self, *_args, **_kwargs):
                        self.calls += 1
                        raise AssertionError("CPU built-in control cannot execute repository tools")

                rpc = ForbiddenRPC()
                conversation = module.create_conversation(adapter, rpc, folder,
                    condition["episode_limits"], workspace=workspace)
            else:
                llm = build_llm(adapter, normalization_folder=folder / "normalization")
                conversation = Conversation(agent=Agent(llm=llm, tools=[],
                        include_default_tools=["ThinkTool", "FinishTool"], condenser=None),
                    workspace=workspace, persistence_dir=folder / "conversation",
                    plugins=[], max_iteration_per_run=512, stuck_detection=True,
                    visualizer=None, delete_on_close=False)
            try:
                conversation.send_message("Synthetic CPU state-machine fixture. No repository task.")
                detector = conversation.stuck_detector
                agent = conversation.agent
                began = time.monotonic()
                summary = run_conversation_once_or_recover(conversation, ledger=adapter.ledger,
                    started={"started": began, "soft_at": began + 120, "hard_at": began + 180},
                    limits=condition["episode_limits"])
                assert summary["stuck_corrections"] == 1 and summary["final_sdk_status"] == expected_status
                assert conversation.stuck_detector is detector and conversation.agent is agent
                assert len(adapter.requests) == adapter.ledger.attempts == adapter.ledger.decisions == expected_calls
                assert not adapter.actions and adapter.ledger.inflight is None
                def text_values(value):
                    if isinstance(value, str):
                        yield value
                    elif isinstance(value, dict):
                        for child in value.values():
                            yield from text_values(child)
                    elif isinstance(value, list):
                        for child in value:
                            yield from text_values(child)

                assert STUCK_CORRECTION in list(text_values(adapter.requests[4]))
                sdk_segments = [event for event in summary["events"] if event["kind"] == "sdk_run_returned"]
                assert [row["segment_max_iterations"] for row in sdk_segments] == [512, 508]
                assert sdk_segments[1]["attempts_before"] == sdk_segments[0]["attempts_after"] == 4
                try:
                    run_conversation_once_or_recover(conversation, ledger=adapter.ledger,
                        started={"started": began, "soft_at": began + 120, "hard_at": began + 180},
                        limits=condition["episode_limits"])
                    raise AssertionError("A used execution policy was admitted again")
                except ValueError as error:
                    assert "fresh idle" in str(error)
                write_new(folder / "fixture-ledger.json", adapter.ledger.snapshot())
                write_new(folder / "policy-events.json", summary)
                result["cases"].append({"case": label, "final_sdk_status": expected_status,
                    "programmed_responses": expected_calls, "same_agent_and_detector": True,
                    "total_attempts": adapter.ledger.attempts, "total_decisions": adapter.ledger.decisions,
                    "correction_enters_next_counted_request": True, "ledger_never_reset": True,
                    "repeat_policy_entry_rejected": True, "events": reference(folder / "policy-events.json")})
                if rpc is not None:
                    assert rpc.calls == 0
                    assert set(conversation.agent.tools_map) == {"terminal", "file_editor", "task_tracker", "think", "finish"}
                    result["cases"][-1].update(
                        production_factory_source=reference(module.__file__),
                        recorded_wire_schema=reference(ready_path),
                        tool_names=sorted(conversation.agent.tools_map), remote_tool_calls=0,
                        original_native_five_tools_retained=True)
            finally:
                conversation.close()
        assert not any(counters.values())
        result.update(passed=True, forbidden_operations=counters,
            policy_source=reference(ROOT / "src/proworksim/software_benchmark_native_execution_v057.py"),
            control_source=reference(__file__))
    except BaseException as error:
        result.update(error={"type": type(error).__name__, "message": str(error)}, traceback=traceback.format_exc(),
                      forbidden_operations=counters)
    receipt = write_new(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "result": receipt, "model_calls": 0,
                      "error": result.get("error")}))
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/software-benchmark-v057/native-execution-control-r2")
    args = parser.parse_args()
    return control(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
