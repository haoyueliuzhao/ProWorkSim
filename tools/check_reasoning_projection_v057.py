"""Replay saved provider responses through the real v057 SDK factory on CPU.

No provider, counter, model, workspace, tools, or scorer is called. The fixture
adapter supplies immutable historical response bytes only after constructing
the same SDK Message/LLMResponse path used by the new controller.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import importlib.metadata
import json
from pathlib import Path

from proworksim import software_benchmark_exact_transport_v054 as original
from proworksim import software_benchmark_exact_transport_v057 as revised
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "runs/software-benchmark-v057/reasoning-projection-control-r1"
SOURCE = ROOT / "artifacts/software-benchmark-v056/failure-analysis-r1/reasoning-mapping-control.json"


def control(output):
    from litellm.types.utils import ModelResponse
    from openhands.sdk.agent.response_dispatch import classify_response
    from openhands.sdk.llm import Message, TextContent

    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "runs/software-benchmark-v057"):
        raise ValueError("Use a new v057 control output")
    output.mkdir(parents=True, exist_ok=False)
    old_control = json.loads(SOURCE.read_bytes())
    thinking_source = old_control["saved_response"]
    thinking_path = checked(thinking_source)
    tool_source = reference(thinking_path.parent / "response-0001.json")
    cases = []
    for label, source, asynchronous in (("recorded_reasoning_only", thinking_source, False),
                                         ("recorded_tool_response", tool_source, True)):
        raw_bytes = checked(source).read_bytes()
        body = json.loads(raw_bytes)
        original_message = Message.from_llm_chat_message(ModelResponse(**body).choices[0].message)
        counters = {"fixture_response_reads": 0, "count_calls": 0, "http_calls": 0}

        class FixtureAdapter:
            maximum_input_tokens, maximum_output_tokens, temperature = 98304, 32768, .6
            request_defaults = {"model": original.REF_MODEL, "max_tokens": 32768,
                                "temperature": .6, "stream": False}

            def __init__(self):
                self.ledger = self

            def count(self, request):
                counters["count_calls"] += 1
                raise AssertionError("Historical conversion must not count a new prompt")

            def complete(self, request, usage_id):
                assert usage_id == "agent" and request["max_tokens"] == 32768
                counters["fixture_response_reads"] += 1
                assert counters["fixture_response_reads"] == 1
                return copy.deepcopy(body)

            def snapshot(self):
                return {"per_usage_id": {"agent": {key: body["usage"][key]
                        for key in ("prompt_tokens", "completion_tokens")}}}

        adapter = FixtureAdapter()
        audit_folder = output / label
        llm = revised.build_llm(adapter, normalization_folder=audit_folder)
        message = Message(role="user", content=[TextContent(text="Historical conversion fixture; do not generate.")])
        if asynchronous:
            converted = asyncio.run(llm.acompletion([message]))
        else:
            converted = llm.completion([message])
        expected_reasoning = body["choices"][0]["message"].get("reasoning")
        assert converted.message.reasoning_content == expected_reasoning
        assert converted.message.content == original_message.content
        assert converted.message.tool_calls == original_message.tool_calls
        assert converted.raw_response.usage.model_dump() == ModelResponse(**body).usage.model_dump()
        assert getattr(converted.raw_response.choices[0].message, "reasoning", None) == expected_reasoning
        assert getattr(converted.raw_response.choices[0].message, "reasoning_content", None) is None
        assert checked(source).read_bytes() == raw_bytes
        totals = converted.metrics.accumulated_token_usage
        assert totals.prompt_tokens == body["usage"]["prompt_tokens"]
        assert totals.completion_tokens == body["usage"]["completion_tokens"]
        assert (llm.max_input_tokens, llm.max_output_tokens, llm.temperature, llm.num_retries) == (98304, 32768, .6, 0)
        projection_files = list(audit_folder.glob("*.json"))
        assert len(projection_files) == 1
        cases.append({"case": label, "saved_response": source,
            "source_reasoning_characters": len(expected_reasoning or ""),
            "old_sdk_reasoning_characters": len(original_message.reasoning_content or ""),
            "new_sdk_reasoning_characters": len(converted.message.reasoning_content or ""),
            "old_classification": str(classify_response(original_message)),
            "new_classification": str(classify_response(converted.message)),
            "content_equal": converted.message.content == original_message.content,
            "tool_calls_equal": converted.message.tool_calls == original_message.tool_calls,
            "usage_equal": True, "metrics_equal_recorded_usage": True,
            "raw_response_keeps_original_provider_fields": True,
            "wire_file_unchanged": True, "asynchronous_factory_path": asynchronous,
            "projection_receipt": reference(projection_files[0]), "fixture_counts": counters})
    result = {"version": revised.VERSION, "passed": True,
        "adapter_source": reference(revised.__file__), "control_source": reference(__file__),
        "original_mapping_evidence": reference(SOURCE),
        "installed_versions": {name: importlib.metadata.version(name)
                               for name in ("openhands-sdk", "litellm")},
        "sdk_conversion_source": reference(__import__(Message.__module__, fromlist=["Message"]).__file__),
        "cases": cases, "fixed_input_limit": 98304, "fixed_output_limit": 32768,
        "model_retries": 0, "model_calls": 0, "counter_calls": 0,
        "tool_calls": 0, "scoring_calls": 0, "formal_ledger_changed": False,
        "score_improvement_measured": False}
    receipt = write_new(output / "result.json", result)
    print(json.dumps({"passed": True, "result": receipt,
                      "case_reasoning_characters": [case["new_sdk_reasoning_characters"] for case in cases],
                      "model_calls": 0}, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    control(args.output)


if __name__ == "__main__":
    main()
