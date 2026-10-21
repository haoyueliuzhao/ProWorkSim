"""Read-only reproduction of two retained failed SDK views; no model/API/tool."""
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
    from openhands.sdk.context.condenser import LLMSummarizingCondenser
    # Register the original persisted action/observation classes, without
    # instantiating any executable tool or reading an Actor filesystem.
    import proworksim.software_benchmark_native_binding_v054  # noqa: F401
    import openhands.tools.terminal.definition  # noqa: F401
    import openhands.tools.file_editor.definition  # noqa: F401
    import openhands.tools.task_tracker.definition  # noqa: F401
    from proworksim.software_benchmark_deepseek_interfaces_v055 import (
        DeepSeekAdapter, NATIVE_TOOLS, build_native_llm as old_llm,
    )
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import build_counter
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    from software_benchmark_deepseek_prefix_v055_r2 import build_native_llm, pending_tail_tool_ids
    from proworksim.storage import digest, json_bytes

    root = Path(__file__).resolve().parents[4]
    run = root / "runs/software-benchmark-v055"
    rows = []
    receipt = {"version": "v055-native-prefix-replay-control-r2", "passed": False,
        "actual_model_requests": 0, "network_requests": 0, "tool_executions": 0,
        "hidden_grader_reads": 0, "old_task_resumed_or_retried": False}

    class NeverClient:
        def complete(self, *args, **kwargs):
            raise AssertionError("This control cannot dispatch any model request")

    try:
        for name in ("generation-1fc074acc542bb548fd44a48", "generation-819f1e1974dff08da0952784"):
            episode = run / "queue-r1/workers" / name / "episode"
            config = json.loads((episode / "controller-config.json").read_text())
            ledger = json.loads((episode / "deepseek-ledger/ledger.json").read_text())
            counter = build_counter(config["context_counter"])
            adapter = DeepSeekAdapter(client=NeverClient(), arm="MATCH", thinking=config["thinking"],
                slot_id="synthetic-prefix-replay-" + name, condition_id=config["condition_id"],
                folder=folder / name, allowed_tool_names=NATIVE_TOOLS, counter=counter)
            for call in ledger["calls"]:
                body = json.loads(Path(call["response"]["path"]).read_text())
                adapter.history.remember(body["choices"][0]["message"])
            event_dir = next((episode / "native-conversation").iterdir()) / "events"
            event_paths = sorted(event_dir.glob("*.json"))
            event_dicts = [json.loads(p.read_text()) for p in event_paths]
            before = digest(json_bytes(event_dicts))
            events = [Event.model_validate(item) for item in event_dicts]
            view = View.from_events(events)
            old, new = old_llm(adapter), build_native_llm(adapter)

            def condenser(llm):
                return LLMSummarizingCondenser(llm=llm.model_copy(update={"usage_id": "condenser"}),
                    max_size=80, keep_first=4, max_tokens=None, hard_context_reset_max_retries=1)

            try:
                condenser(old)._get_forgotten_events(view, agent_llm=old)
            except Exception as error:
                if "insufficient tool messages following tool_calls" not in str(error):
                    raise
                prior_error = {"type": type(error).__name__, "message": str(error)}
            else:
                raise AssertionError("Retained failed view did not reproduce the original count failure")
            forgotten, offset = condenser(new)._get_forgotten_events(view, agent_llm=new)
            assert forgotten and offset in view.manipulation_indices
            assert all(isinstance(e, LLMConvertibleEvent) for e in forgotten)
            all_messages = LLMConvertibleEvent.events_to_messages(view.events)
            base_messages = LLMConvertibleEvent.events_to_messages(view.events[:4])
            tools = view.events[0].tools
            # Complete request counting remains the old strict path.
            old_full = old.get_token_count(all_messages, tools, add_security_risk_prediction=True)
            new_full = new.get_token_count(all_messages, tools, add_security_risk_prediction=True)
            assert old_full == new_full
            prefix_wire = new.format_messages_for_llm(base_messages)
            pending = pending_tail_tool_ids(prefix_wire)
            assert len(pending) == 2
            prefix_count = new.get_token_count(base_messages, tools, add_security_risk_prediction=True)
            # The official complete-request counter still rejects the same
            # prefix. The permissive count-only seam cannot reach dispatch.
            invalid_dispatch = new._request(base_messages, tools, {"add_security_risk_prediction": True})
            try:
                adapter.count(invalid_dispatch)
            except Exception as error:
                assert "insufficient tool messages following tool_calls" in str(error)
            else:
                raise AssertionError("Actual dispatch input must still be strict")
            # Exercise a prefix ending inside the first multi-call batch.
            smaller = LLMConvertibleEvent.events_to_messages(view.events[:3])
            subset_count = new.get_token_count(smaller, tools, add_security_risk_prediction=True)
            assert subset_count > 0
            orphan = copy.deepcopy(prefix_wire)
            orphan.append({"role": "tool", "tool_call_id": "not-an-original-call", "content": ""})
            try:
                pending_tail_tool_ids(orphan)
            except ValueError:
                pass
            else:
                raise AssertionError("Orphan results cannot use the prefix path")
            assert before == digest(json_bytes([json.loads(p.read_text()) for p in event_paths]))
            rows.append({"episode": str(episode), "controller_result": reference(episode / "controller-result.json"),
                "original_ledger": reference(episode / "deepseek-ledger/ledger.json"),
                "events": [reference(p) for p in event_paths], "old_failure_reproduced": prior_error,
                "old_complete_count": old_full, "new_complete_count": new_full,
                "prefix_count": prefix_count, "partial_batch_prefix_count": subset_count,
                "pending_tail_tool_ids": list(pending), "forgotten_event_ids": [e.id for e in forgotten],
                "summary_offset": offset, "events_unchanged": True,
                "strict_actual_dispatch_retained": True, "original_all_calls_settled": ledger["inflight"] is None,
                "new_model_requests": adapter.ledger.attempts})
        receipt.update(passed=True, cases=rows)
    except BaseException as error:
        receipt.update(error={"type": type(error).__name__, "message": str(error)}, traceback=traceback.format_exc(), cases=rows)
    write_new(folder / "receipt.json", receipt)
    print(json.dumps({"passed": receipt["passed"], "cases": len(rows), "error": receipt.get("error"),
                      "actual_model_requests": 0}, ensure_ascii=False))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
