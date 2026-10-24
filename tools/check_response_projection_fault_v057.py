"""Real SDK soft-condenser projection fault, with one programmed CPU response."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]


def control(output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "runs/software-benchmark-v057"):
        raise ValueError("Use an independent v057 control output")
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(output / "empty-user-config"),
        LITELLM_LOCAL_MODEL_COST_MAP="True", CUDA_VISIBLE_DEVICES="", NVIDIA_VISIBLE_DEVICES="void")
    counters = {"network": 0, "gpu": 0, "weights": 0}

    def audit(event, values):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            counters["network"] += 1
            raise AssertionError("Projection control cannot contact a network")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                counters["gpu"] += 1
                raise AssertionError("Projection control cannot open a GPU")
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                counters["weights"] += 1
                raise AssertionError("Projection control cannot read model weights")

    sys.addaudithook(audit)
    from openhands.sdk import Agent, Conversation
    from openhands.sdk.context.condenser import LLMSummarizingCondenser
    from openhands.sdk.conversation.exceptions import ConversationRunError
    from openhands.sdk.llm import Message, TextContent
    from pydantic import PrivateAttr
    from proworksim import software_benchmark_exact_transport_v057 as revised
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    from proworksim.software_benchmark_exact_transport_v054 import REF_MODEL, exact_measure
    from proworksim.software_benchmark_ref_budget_v056 import BudgetLedger

    condition = json.loads((ROOT / "config/v056-condition-REF_B0500K.json").read_bytes())

    class Adapter:
        maximum_input_tokens, maximum_output_tokens, temperature = 98304, 32768, .6
        request_defaults = {"model": REF_MODEL, "max_tokens": 32768, "temperature": .6, "stream": False}

        def __init__(self):
            self.ledger = BudgetLedger(condition)
            self.calls, self.count_calls = [], 0
            self.body = None

        def count(self, request):
            self.count_calls += 1
            return exact_measure(request, list(range(32)), context_limit=131072,
                                 backend="synthetic_cpu_programmed_counter")

        def complete(self, request, usage_id):
            self.calls.append(usage_id)
            assert self.calls == ["condenser"]
            measure = self.count(request)
            self.ledger.reserve(measure, usage_id, {"fixture_request": 1})
            body = {"id": "cpu-conflicting-condenser", "object": "chat.completion", "created": 0,
                "model": REF_MODEL, "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "fixture summary",
                        "reasoning": "provider thinking", "reasoning_content": "conflicting thinking"}}],
                "usage": {"prompt_tokens": 32, "completion_tokens": 8, "total_tokens": 40,
                          "completion_tokens_details": {"reasoning_tokens": 2}}}
            self.body = copy.deepcopy(body)
            raw = write_new(output / "raw-response.json", body)
            self.ledger.settle(body, raw)
            return body

    adapter = Adapter()
    llm = revised.build_llm(adapter, normalization_folder=output / "projections")
    condenser_llm = llm.model_copy(update={"usage_id": "condenser"})
    assert condenser_llm._adapter is llm._adapter

    class ObservedSoftCondenser(LLMSummarizingCondenser):
        _returned_original_view_after_fault: bool = PrivateAttr(default=False)

        def condense(self, view, agent_llm=None):
            result = super().condense(view, agent_llm=agent_llm)
            if revised.response_projection_fault(adapter) is not None:
                self._returned_original_view_after_fault = result is view
            return result

    condenser = ObservedSoftCondenser(llm=condenser_llm, max_size=80, keep_first=4,
        max_tokens=None, hard_context_reset_max_retries=1)
    workspace = output / "workspace"
    workspace.mkdir()
    conversation = Conversation(agent=Agent(llm=llm, tools=[], include_default_tools=["FinishTool"],
            condenser=condenser), workspace=workspace, persistence_dir=output / "conversation",
        plugins=[], max_iteration_per_run=512, stuck_detection=True, visualizer=None, delete_on_close=False)
    result = {"version": revised.VERSION, "passed": False, "model_calls": 0, "official_scoring_calls": 0,
              "synthetic_token_units_not_actual_model_usage": True}
    try:
        for i in range(90):
            conversation.send_message(f"Synthetic CPU history item {i}; no benchmark or reference solution.")
        caught = None
        try:
            conversation.run()
        except ConversationRunError as error:
            caught = error
        assert caught is not None
        assert conversation.agent.condenser._returned_original_view_after_fault is True
        assert conversation.state.execution_status.value == "error"
        assert adapter.calls == ["condenser"]
        assert adapter.ledger.attempts == 1 and adapter.ledger.decisions == 0
        assert adapter.ledger.actual == 40 and adapter.ledger.inflight is None
        snapshot = adapter.ledger.snapshot()
        assert snapshot["complete_actual_tokens"] == 40 and snapshot["uncertain_reserved_tokens"] == 0
        counts = (len(adapter.calls), adapter.count_calls)
        message = Message(role="user", content=[TextContent(text="Must never dispatch this fixture message")])
        blocked = []
        for operation in (lambda: llm.get_token_count([message]), lambda: llm.completion([message]),
                          lambda: revised.assert_response_projection_healthy(adapter)):
            try:
                operation()
                raise AssertionError("Faulted projection was admitted")
            except revised.ResponseProjectionFault:
                blocked.append(True)
        assert counts == (len(adapter.calls), adapter.count_calls)
        assert json.loads((output / "raw-response.json").read_text()) == adapter.body
        assert not any(counters.values())
        write_new(output / "fixture-ledger.json", snapshot)
        result.update(passed=True, sdk_soft_condenser_returned_original_view=True,
            shared_agent_condenser_guard=True, conversation_run_raised=type(caught).__name__,
            final_sdk_status="error", blocked_count_completion_and_closure=blocked,
            only_programmed_response_usage_id="condenser", fixture_attempts=1, fixture_decisions=0,
            settled_fixture_tokens_retained=40, additional_model_requests_after_fault=0,
            raw_response_preserved=True, sticky_fault=revised.response_projection_fault(adapter),
            fault_receipt=reference(output / "projections/projection-fault.json"),
            forbidden_operations=counters, source=reference(__file__),
            normalizer_source=reference(revised.__file__),
            controller_source=reference(ROOT / "tools/run_ref_budget_controller_v057.py"))
    except BaseException as error:
        result.update(error={"type": type(error).__name__, "message": str(error)}, traceback=traceback.format_exc())
    finally:
        conversation.close()
    receipt = write_new(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "result": receipt, "error": result.get("error")}))
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/software-benchmark-v057/projection-fault-guard-r2")
    args = parser.parse_args()
    return control(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
