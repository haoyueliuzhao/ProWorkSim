"""Read retained SDK Message provenance and validate r3 serialization offline."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    folder = parser.parse_args().output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    from openhands.sdk.event import Event, LLMConvertibleEvent
    from openhands.sdk.context.view import View
    from openhands.sdk.llm import Message
    import proworksim.software_benchmark_native_binding_v054  # noqa: F401
    import openhands.tools.terminal.definition  # noqa: F401
    import openhands.tools.file_editor.definition  # noqa: F401
    import openhands.tools.task_tracker.definition  # noqa: F401
    from proworksim.software_benchmark_deepseek_interfaces_v055 import DeepSeekAdapter, NATIVE_TOOLS
    from proworksim.software_benchmark_deepseek_prefix_v055_r2 import (
        build_native_llm as old_llm, prefix_llm_type,
    )
    from proworksim.software_benchmark_deepseek_reasoning_v055_r3 import build_native_llm
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import build_counter
    from proworksim.software_benchmark_deepseek_api_v055 import validate_payload
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    from proworksim.storage import digest, json_bytes

    root = Path(__file__).resolve().parents[1]
    run = root / "runs/software-benchmark-v055"
    selected = {"v055-MATCH-thinking-django__django-15814",
                "v055-MATCH-thinking-matplotlib__matplotlib-24970"}
    state = json.loads((run / "queue-r1/state.json").read_text())
    sources = [{"slot": row["slot"], "generation": row["generation"]}
               for row in state["rows"] if row["slot"]["slot_id"] in selected]
    assert len(sources) == 2
    receipt = {"version": "v055-native-original-reasoning-control-r3", "passed": False,
        "actual_model_requests": 0, "network_requests": 0, "tool_executions": 0,
        "official_score_artifacts_opened": False, "original_tasks_resumed": False,
        "model_reasoning_text_recorded": False, "cases": []}

    class NeverClient:
        def complete(self, *args, **kwargs):
            raise AssertionError("This offline control cannot call a provider")

    try:
        for source in sources:
            slot = source["slot"]
            episode = Path(source["generation"]["directory"]) / "episode"
            config = json.loads((episode / "controller-config.json").read_text())
            ledger = json.loads((episode / "deepseek-ledger/ledger.json").read_text())
            adapter = DeepSeekAdapter(client=NeverClient(), arm="MATCH", thinking=True,
                slot_id=slot["slot_id"], condition_id=slot["condition_id"],
                folder=folder / slot["instance_id"], allowed_tool_names=NATIVE_TOOLS,
                counter=build_counter(config["context_counter"]))
            for call in ledger["calls"]:
                body = json.loads(Path(call["response"]["path"]).read_text())
                adapter.history.remember(body["choices"][0]["message"])
            event_dir = next((episode / "native-conversation").iterdir()) / "events"
            event_paths = sorted(event_dir.glob("*.json"))
            raw_events = [json.loads(path.read_text()) for path in event_paths]
            before = digest(json_bytes(raw_events))
            events = [Event.model_validate(event) for event in raw_events]
            view = View.from_events(events)
            messages = LLMConvertibleEvent.events_to_messages(view.events)
            tools = view.events[0].tools
            old, new = old_llm(adapter), build_native_llm(adapter)
            old_request = old._request(messages, tools, {"add_security_risk_prediction": True})
            new_request = new._request(messages, tools, {"add_security_risk_prediction": True})
            try:
                validate_payload(old_request, NATIVE_TOOLS)
            except ValueError as error:
                assert "preserve reasoning_content" in str(error)
                old_error = {"type": type(error).__name__, "message": str(error)}
            else:
                raise AssertionError("Retained failed SDK view did not reproduce the original local rejection")
            validate_payload(new_request, NATIVE_TOOLS)
            measure = adapter.count(new_request)
            assert new.get_token_count.__func__ is prefix_llm_type().get_token_count
            expected = copy.deepcopy(old_request)
            recovered = []
            # _prepare_chat_messages preserves order and the original SDK
            # reasoning field; equality is positional, never a text match.
            detached = old._prepare_chat_messages(messages)
            for index, original in enumerate(detached):
                if original.role == "assistant" and isinstance(original.reasoning_content, str):
                    current = expected["messages"][index]
                    if current.get("reasoning_content") != original.reasoning_content:
                        assert not current.get("tool_calls")
                        recovered.append({"message_index": index, "tool_call_count": 0,
                            "reasoning_characters": len(original.reasoning_content),
                            "reasoning_sha256": digest(original.reasoning_content.encode())})
                        current["reasoning_content"] = original.reasoning_content
            assert recovered and new_request == expected
            final_body = json.loads(Path(ledger["calls"][-1]["response"]["path"]).read_text())
            final_message = final_body["choices"][0]["message"]
            assert final_body["choices"][0]["finish_reason"] == "length"
            assert not final_message.get("tool_calls")
            assert recovered[-1]["reasoning_sha256"] == digest(final_message["reasoning_content"].encode())
            # Missing is still missing. Empty is kept only when the original
            # SDK Message explicitly contains that exact empty string.
            empty = Message(role="assistant", content="", reasoning_content="")
            absent = Message(role="assistant", content="", reasoning_content=None)
            assert new.format_messages_for_llm([empty])[0]["reasoning_content"] == ""
            assert "reasoning_content" not in new.format_messages_for_llm([absent])[0]
            invalid = copy.deepcopy(new_request)
            invalid["messages"][recovered[-1]["message_index"]].pop("reasoning_content")
            try:
                validate_payload(invalid, NATIVE_TOOLS)
            except ValueError as error:
                assert "preserve reasoning_content" in str(error)
            else:
                raise AssertionError("Actually missing reasoning must remain a strict rejection")
            adapter.thinking = False
            assert old.format_messages_for_llm(messages) == new.format_messages_for_llm(messages)
            adapter.thinking = True
            assert before == digest(json_bytes([json.loads(path.read_text()) for path in event_paths]))
            receipt["cases"].append({"slot_id": slot["slot_id"],
                "original_controller_result": reference(episode / "controller-result.json"),
                "original_ledger": reference(episode / "deepseek-ledger/ledger.json"),
                "original_length_response": ledger["calls"][-1]["response"],
                "event_files": [reference(path) for path in event_paths],
                "r2_model_features_send_reasoning_content": old._model_features().send_reasoning_content,
                "old_error_reproduced": old_error, "recovered_original_messages": recovered,
                "only_original_assistant_reasoning_fields_added": True,
                "strict_missing_reasoning_rejected": True, "explicit_empty_string_preserved": True,
                "nonthinking_serialization_unchanged": True, "r2_prefix_count_method_inherited": True,
                "strict_counter_measurement": measure,
                "input_reservation_fits": measure["prompt_tokens"] <= adapter.maximum_input_tokens,
                "events_unchanged": True, "new_provider_requests": adapter.ledger.attempts})
        receipt["passed"] = True
    except BaseException as error:
        receipt.update(error={"type": type(error).__name__, "message": str(error)}, traceback=traceback.format_exc())
    write_new(folder / "receipt.json", receipt)
    print(json.dumps({"passed": receipt["passed"], "cases": len(receipt["cases"]),
                      "error": receipt.get("error"), "new_provider_requests": 0}, ensure_ascii=False))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
