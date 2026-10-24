"""Read recorded model ledgers to separate per-call and cumulative limits."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs/software-benchmark-v056"
STATE = RUNS / "score-encoding-repair-r1/analysis-r2/source-state.json"
OUT = ROOT / "artifacts/software-benchmark-v056/failure-analysis-r1/call-limits.json"


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def aggregate(rows):
    settled = [call for row in rows for call in row["settled_calls"]]
    length = [call for call in settled if call["finish_reason"] == "length"]
    return {
        "episodes": len(rows), "settled_response_count": len(settled),
        "finish_reasons": dict(Counter(call["finish_reason"] for call in settled)),
        "usage_ids": dict(Counter(call["usage_id"] for call in settled)),
        "maximum_prompt_tokens": max((call["prompt_tokens"] for call in settled), default=0),
        "maximum_completion_tokens": max((call["completion_tokens"] for call in settled), default=0),
        "maximum_actual_prompt_plus_completion": max(
            (call["prompt_tokens"] + call["completion_tokens"] for call in settled), default=0),
        "length_limited_calls": len(length),
        "calls_at_32768_output_cap": sum(call["completion_tokens"] == 32768 for call in settled),
        "episodes_with_output_at_cap": sum(
            any(call["completion_tokens"] == 32768 for call in row["settled_calls"]) for row in rows),
        "length_limited_agent_calls": sum(call["usage_id"] == "agent" for call in length),
        "length_limited_condenser_calls": sum(call["usage_id"] == "condenser" for call in length),
        "episodes_with_length_limited_response": sum(row["length_limited_calls"] > 0 for row in rows),
        "episodes_with_condenser": sum(row["condenser_calls"] > 0 for row in rows),
    }


def analyze(state_path, output):
    state = json.loads(state_path.read_bytes())
    rows, length_cases, cap_cases = [], [], []
    for entry in state["rows"]:
        slot = entry["slot"]
        folder = RUNS / "episodes" / hashlib.sha256(slot["slot_id"].encode()).hexdigest()
        ledger_path = folder / "ref-ledger/ledger.json"
        ledger = json.loads(ledger_path.read_bytes())
        assert ledger["slot_id"] == slot["slot_id"]
        settled = []
        for call in ledger["calls"]:
            usage = call.get("usage")
            if usage is None:
                continue
            item = {"attempt": call["attempt"], "usage_id": call["usage_id"],
                    "finish_reason": call.get("finish_reason"),
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                    "response": call["response"]}
            assert item["prompt_tokens"] <= 98304 and item["completion_tokens"] <= 32768
            settled.append(item)
            if item["finish_reason"] == "length":
                length_cases.append({"slot_id": slot["slot_id"], "instance_id": slot["instance_id"],
                    "condition_id": slot["condition_id"], "generation_status": entry["generation"]["status"],
                    "official_resolved": entry["score"].get("resolved"), **item})
            if item["completion_tokens"] == 32768:
                cap_cases.append({"slot_id": slot["slot_id"], "instance_id": slot["instance_id"],
                    "condition_id": slot["condition_id"], "official_resolved": entry["score"].get("resolved"),
                    **item})
        row = {"slot_id": slot["slot_id"], "condition_id": slot["condition_id"],
            "generation_status": entry["generation"]["status"],
            "official_resolved": entry["score"].get("resolved"), "ledger": ref(ledger_path),
            "model_attempts": ledger["attempts"], "agent_decisions": ledger["decisions"],
            "length_limited_calls": sum(call["finish_reason"] == "length" for call in settled),
            "condenser_calls": sum(call["usage_id"] == "condenser" for call in settled),
            "settled_calls": settled}
        rows.append(row)
    assert len(rows) == 200
    groups = {}
    for condition in sorted({row["condition_id"] for row in rows}):
        subset = [row for row in rows if row["condition_id"] == condition]
        groups[condition] = {"all": aggregate(subset),
            "official_false": aggregate([row for row in subset if row["official_resolved"] is False]),
            "official_true": aggregate([row for row in subset if row["official_resolved"] is True])}
    value = {"version": "v056-recorded-call-limit-analysis-r1", "script": ref(__file__),
        "source_state": ref(state_path), "all_200": aggregate(rows), "groups": groups,
        "length_limited_cases": length_cases,
        "output_at_cap_cases": cap_cases,
        "per_slot": [{key: value for key, value in row.items() if key != "settled_calls"} for row in rows],
        "interpretation": {
            "completed_response_metadata_only": True,
            "length_is_per_response_not_whole_episode_budget": True,
            "output_at_cap_reported_separately_from_finish_reason": True,
            "no_context_rejection_does_not_prove_history_information_preserved": True,
            "length_association_is_not_a_causal_score_loss_estimate": True},
        "model_calls": 0, "scoring_calls": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"all_200": value["all_200"], "groups": groups}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    analyze(args.state, args.output)


if __name__ == "__main__":
    main()
