"""Exercise the new local stop through the pinned SDK with one scripted reply."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def control(output):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Run this scripted CPU control as an ordinary user")
    output = Path(output).resolve()
    if not (output.is_relative_to(Path('/tmp')) or output.is_relative_to(ROOT / 'runs/software-benchmark-v090')):
        raise ValueError("Use a new task-local or temporary CPU control directory")
    output.mkdir(parents=True, exist_ok=False)
    counters = {"network": 0, "weights": 0, "gpu": 0}

    def audit(event, values):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.bind"}:
            counters["network"] += 1
            raise AssertionError("No network in scripted CPU control")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                counters["weights"] += 1
                raise AssertionError("No weight loading in scripted CPU control")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                counters["gpu"] += 1
                raise AssertionError("No GPU access in scripted CPU control")
    sys.addaudithook(audit)
    from proworksim.software_benchmark_candidates_v054 import write_new
    from proworksim.software_benchmark_exact_transport_v054 import REF_MODEL, exact_measure
    from proworksim.software_benchmark_exact_transport_v057 import assert_response_projection_healthy
    from proworksim.software_benchmark_native_control_v062 import create_conversation, run_controlled_conversation
    from proworksim.software_benchmark_qwen_truncation_v090 import ReasoningTruncationAdapter, unwrap_local_boundary
    from proworksim.software_benchmark_ref_budget_v064 import BudgetLedger

    condition = json.loads((ROOT / 'runs/software-benchmark-v064/full-verified-r1/conditions/QWEN_REF_B5000K.json').read_bytes())
    ready = json.loads((ROOT / 'runs/software-benchmark-v066/sdk-bundle-r1/probe-native-interface.json').read_bytes())
    result = {"passed": False, "model_calls": 0, "remote_tool_calls": 0,
              "scripted_responses": 0, "generic_nudges": None,
              "known_boundary": False, "synthetic_usage_not_model_measurement": True}

    class ForbiddenRPC:
        _bound, session_id = False, "v090_scripted_truncation"

        def __init__(self):
            self.ready = ready

        def request(self, *_args, **_kwargs):
            result["remote_tool_calls"] += 1
            raise AssertionError("The scripted response must never dispatch a repository tool")

    class ScriptedAdapter:
        slot_id = 'v064:scripted-v090-cpu:0'
        maximum_input_tokens, maximum_output_tokens, temperature = 98304, 32768, .6
        request_defaults = {"model": REF_MODEL, "max_tokens": 32768, "temperature": .6,
                            "stream": False, "chat_template_kwargs": {"enable_thinking": True}}

        def __init__(self):
            self.condition, self.ledger = condition, BudgetLedger(condition)

        def count(self, request):
            return exact_measure(request, list(range(256)), context_limit=131072,
                                 backend="scripted_cpu_units_not_actual_tokenizer")

        def complete(self, request, usage_id):
            if result["scripted_responses"] or usage_id != "agent":
                raise AssertionError("Only the declared first CPU response is allowed")
            result["scripted_responses"] += 1
            self.ledger.reserve(self.count(request), usage_id, write_new(output / 'request.json', request))
            body = {"id": "scripted-cpu-v090", "object": "chat.completion", "created": 0,
                    "model": REF_MODEL, "choices": [{"index": 0, "finish_reason": "length",
                    "message": {"role": "assistant", "content": None,
                                "reasoning": "Synthetic non-model reasoning", "tool_calls": []}}],
                    "usage": {"prompt_tokens": 256, "completion_tokens": 32768,
                              "total_tokens": 33024,
                              "completion_tokens_details": {"reasoning_tokens": 32768}}}
            self.ledger.settle(body, write_new(output / 'response.json', body))
            return body

    conversation = None
    try:
        adapter = ReasoningTruncationAdapter(ScriptedAdapter(), folder=output / 'truncation',
            workspace_id=ScriptedAdapter.slot_id, progress_snapshot=lambda: {"tool_rpc_count": 0})
        workspace = output / 'workspace'
        workspace.mkdir()
        conversation = create_conversation(adapter, ForbiddenRPC(), output,
                                            condition['episode_limits'], workspace=workspace)
        conversation.send_message('Scripted CPU control; do not execute repository tools.')
        started, caught = time.monotonic(), None
        try:
            run_controlled_conversation(conversation, adapter=adapter,
                started={"started": started, "soft_at": started + 120, "hard_at": started + 180},
                limits=condition['episode_limits'])
        except Exception as error:
            caught = error
        assert caught is not None
        boundary = unwrap_local_boundary(caught, adapter)
        assert boundary is not None and not boundary['native_finished']
        assert_response_projection_healthy(adapter)
        conversation.close()
        conversation = None
        nudge = 'Your last response did not include a function call or a message.'
        result['generic_nudges'] = sum(nudge in p.read_text() for p in (output / 'native-conversation').rglob('*.json'))
        assert result['generic_nudges'] == 0
        assert adapter.ledger.snapshot()['complete_actual_tokens'] == 33024
        result.update(passed=True, known_boundary=True, boundary=boundary,
                      sdk_wrapper_type=type(caught).__name__)
    except BaseException as error:
        result.update(error={"type": type(error).__name__, "message": str(error)}, traceback=traceback.format_exc())
    finally:
        if conversation is not None:
            conversation.close()
    result['forbidden_operations'] = counters
    if any(counters.values()):
        result['passed'] = False
    write_new(output / 'result.json', result)
    print(json.dumps({"passed": result['passed'], "error": result.get('error')}))
    return 0 if result['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    return control(parser.parse_args().output)


if __name__ == '__main__':
    raise SystemExit(main())
