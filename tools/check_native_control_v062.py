"""Exercise the v062 protocol through the pinned SDK with scripted CPU replies."""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def control(output):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("This CPU control must run as an ordinary user")
    output = Path(output).resolve()
    if not (output.is_relative_to(ROOT / "runs/software-benchmark-v062")
            or output.is_relative_to(Path("/tmp"))):
        raise ValueError("Use a new v062 control directory or temporary test directory")
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(output / "empty-user-config"),
                      LITELLM_LOCAL_MODEL_COST_MAP="True", CUDA_VISIBLE_DEVICES="",
                      NVIDIA_VISIBLE_DEVICES="void")
    counters = {"network_attempts": 0, "weight_opens": 0, "gpu_opens": 0}

    def audit(event, values):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            counters["network_attempts"] += 1
            raise AssertionError("The programmed CPU control cannot use the network")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                counters["weight_opens"] += 1
                raise AssertionError("The programmed CPU control cannot open weights")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                counters["gpu_opens"] += 1
                raise AssertionError("The programmed CPU control cannot open a GPU")

    sys.addaudithook(audit)
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    from proworksim.software_benchmark_exact_transport_v054 import REF_MODEL, exact_measure
    from proworksim.software_benchmark_exact_transport_v057 import assert_response_projection_healthy
    from proworksim.software_benchmark_native_control_v062 import (
        FINISH_REVIEW,
        STUCK_CORRECTION,
        VERSION,
        create_conversation,
        initial_message,
        run_controlled_conversation,
    )
    from proworksim.software_benchmark_ref_budget_v056 import BudgetLedger
    from proworksim.storage import digest, json_bytes

    condition = json.loads((ROOT / "config/v056-condition-REF_B5000K.json").read_bytes())
    ready_path = ROOT / ("runs/software-benchmark-v056/episodes/"
                        "6d3849656aa3d6c683050ae41d11d5c607a7ea89713cb16bfc5f5d40d4fab15f/worker-ready.json")
    original_ready = json.loads(ready_path.read_bytes())
    ready = {key: original_ready[key] for key in ("vision_enabled", "tool_definitions")}
    result = {"version": VERSION, "passed": False, "model_calls": 0, "remote_tool_calls": 0,
              "official_scoring_calls": 0, "synthetic_token_units_not_actual_model_usage": True,
              "cases": [], "sdk_version": importlib.metadata.version("openhands-sdk")}

    class ForbiddenRPC:
        def __init__(self, index):
            self._bound = False
            self.session_id = "v062_cpu_control_" + str(index)
            self.ready = ready

        def request(self, *_args, **_kwargs):
            result["remote_tool_calls"] += 1
            raise AssertionError("Scripted Think/Finish responses cannot invoke repository tools")

    class ScriptedAdapter:
        maximum_input_tokens, maximum_output_tokens, temperature = 98304, 32768, .6
        request_defaults = {"model": REF_MODEL, "max_tokens": 32768, "temperature": .6,
                            "top_p": .95, "top_k": 20, "stream": False,
                            "chat_template_kwargs": {"enable_thinking": True}}

        def __init__(self, actions, folder):
            self.ledger = BudgetLedger(condition)
            self.actions, self.requests, self.folder = list(actions), [], folder

        def count(self, request):
            # Synthetic units depend on the entire serialized input, including
            # every continuation message. No actual tokenizer is claimed.
            ids = list(range(32 + len(json_bytes(request)) // 16))
            return exact_measure(request, ids, context_limit=131072,
                                 backend="synthetic_cpu_programmed_counter")

        def complete(self, request, usage_id):
            if not self.actions or usage_id != "agent":
                raise AssertionError("SDK attempted an undeclared fixture response")
            self.requests.append(copy.deepcopy(request))
            name = self.actions.pop(0)
            measure, n = self.count(request), len(self.requests)
            request_reference = write_new(self.folder / f"request-{n:02d}.json", request)
            self.ledger.reserve(measure, usage_id, request_reference)
            arguments = {"message": "Synthetic finish"} if name == "finish" else {"thought": "same thought"}
            body = {"id": f"cpu-{self.folder.name}-{n}", "object": "chat.completion", "created": 0,
                    "model": REF_MODEL, "choices": [{"index": 0, "finish_reason": "tool_calls",
                    "message": {"role": "assistant", "content": None, "reasoning": "literal CPU reasoning",
                                "tool_calls": [{"id": f"call-{n}", "type": "function", "function": {
                                    "name": name, "arguments": json.dumps(arguments)}}]}}],
                    "usage": {"prompt_tokens": measure["prompt_tokens"], "completion_tokens": 8,
                              "total_tokens": measure["prompt_tokens"] + 8,
                              "completion_tokens_details": {"reasoning_tokens": 2}}}
            self.ledger.settle(body, write_new(self.folder / f"response-{n:02d}.json", body))
            return body

    try:
        for index, (label, sequence, expected_status, expected_starts) in enumerate((
            ("two_stuck_then_finish_and_review", ["think"] * 8 + ["finish", "finish"], "finished", [0, 4, 8, 9]),
            ("finish_review_then_two_stuck_recoveries", ["finish"] + ["think"] * 12, "stuck", [0, 1, 5, 9]),
        )):
            folder = output / label
            workspace = folder / "workspace"
            workspace.mkdir(parents=True)
            adapter = ScriptedAdapter(sequence, folder)
            conversation = create_conversation(adapter, ForbiddenRPC(index), folder,
                                               condition["episode_limits"], workspace=workspace)
            try:
                conversation.send_message(initial_message("Synthetic CPU protocol task. No repository issue."))
                agent, detector = conversation.agent, conversation.stuck_detector
                guard = adapter._v057_projection_guard
                assert agent.llm._adapter is agent.condenser.llm._adapter is guard
                started = time.monotonic()
                summary = run_controlled_conversation(conversation, adapter=adapter,
                    started={"started": started, "soft_at": started + 120, "hard_at": started + 180},
                    limits=condition["episode_limits"])
                assert_response_projection_healthy(adapter)
                assert summary["stuck_corrections"] == 2 and summary["finish_reviews"] == 1
                assert summary["final_sdk_status"] == expected_status
                assert conversation.agent is agent and conversation.stuck_detector is detector
                assert len(adapter.requests) == adapter.ledger.attempts == adapter.ledger.decisions == len(sequence)
                assert not adapter.actions and adapter.ledger.inflight is None
                starts = [event for event in summary["events"] if event["kind"] == "sdk_run_started"]
                assert [event["attempts_before"] for event in starts] == expected_starts
                assert [event["segment_max_iterations"] for event in starts] == [512 - n for n in expected_starts]
                for event, request in zip(starts[1:], (adapter.requests[n] for n in expected_starts[1:]), strict=True):
                    expected = STUCK_CORRECTION if event["phase"] == "stuck_correction" else FINISH_REVIEW
                    texts = [part["text"] for message in request["messages"]
                             for part in message.get("content", [])
                             if isinstance(part, dict) and part.get("type") == "text"]
                    assert expected in texts
                    assert adapter.count(request)["prompt_tokens"] == adapter.ledger.calls[event["attempts_before"]]["usage"]["prompt_tokens"]
                assert set(agent.tools_map) == {"terminal", "file_editor", "task_tracker", "think", "finish"}
                projections = [json.loads(path.read_bytes()) for path in (folder / "sdk-response-projections").glob("*.json")]
                assert len(projections) == len(sequence)
                assert all(row["reasoning_alias_added"] and row["reasoning_sha256"] == digest(b"literal CPU reasoning")
                           for row in projections)
                write_new(folder / "ledger.json", adapter.ledger.snapshot())
                write_new(folder / "policy-events.json", summary)
                result["cases"].append({"case": label, "programmed_responses": len(sequence),
                    "sdk_runs": summary["sdk_runs"], "final_sdk_status": expected_status,
                    "stuck_corrections": 2, "finish_reviews": 1, "same_agent_detector_ledger": True,
                    "all_policy_messages_counted": True, "reasoning_alias_preserved": True,
                    "events": reference(folder / "policy-events.json")})
            finally:
                conversation.close()
        assert not any(counters.values())
        result.update(passed=True, same_agent_condenser_guard=True,
                      production_factory_source=reference(ROOT / "src/proworksim/software_benchmark_native_control_v062.py"),
                      recorded_public_wire_schema=reference(ready_path), control_source=reference(__file__))
    except BaseException as error:
        result.update(error={"type": type(error).__name__, "message": str(error)}, traceback=traceback.format_exc())
    result["forbidden_operations"] = counters
    receipt = write_new(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "result": receipt, "error": result.get("error")}))
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    return control(parser.parse_args().output)


if __name__ == "__main__":
    raise SystemExit(main())
