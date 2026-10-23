"""Join retained compact stop metadata to final scores; never run inference or tests."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/software-benchmark-v055/budget-constraint-audit-r1"
META = ROOT / "runs/software-benchmark-v055/score-gap-evidence-r1/normal-closed-slot-metadata.json"
SCORES = ROOT / "artifacts/software-benchmark-v055/final-result-analysis-r1/slot-results.csv"


def reference(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def category(row):
    reason = row["terminal_reason"]
    limits = row.get("terminal_limits", [])
    if reason in {"full_input_and_output_reservation_insufficient",
                  "episode_token_reservation_exhausted"}:
        return "cumulative_token_reservation"
    if any(limit.startswith("max_total_tokens_") for limit in limits):
        return "cumulative_token_reservation"
    if reason == "conservative_context_reservation_exhausted" or "context_capacity" in limits:
        return "single_request_context"
    if reason in {"all_model_attempt_limit", "agent_decision_limit"} or any(
        "attempt" in limit or "decision" in limit for limit in limits
    ):
        return "attempt_or_decision_limit"
    if "deadline" in reason:
        return "time_boundary"
    if reason in {"SDK_returned_without_explicit_limit_boundary",
                  "all_members_stopped_or_no_reachable_event"}:
        return "natural_or_no_explicit_limit"
    if reason == "model_budget_exhausted":
        return "model_budget_unspecified"
    return "other_historical_boundary"


def distribution(values):
    values = [value for value in values if isinstance(value, (int, float))]
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": min(values), "median": statistics.median(values),
            "max": max(values), "mean": statistics.mean(values)}


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    metadata = json.loads(META.read_text())
    with SCORES.open(newline="") as stream:
        scores = {row["slot_id"]: row for row in csv.DictReader(stream)}
    assert len(scores) == 4500 and len(metadata) == 4324
    assert len({row["slot_id"] for row in metadata}) == len(metadata)
    rows = []
    for item in metadata:
        score = scores[item["slot_id"]]
        assert item["instance_id"] == score["instance_id"]
        rows.append({
            "slot_id": item["slot_id"], "instance_id": item["instance_id"],
            "group": item["group"], "stop_category": category(item),
            "terminal_reason": item["terminal_reason"],
            "terminal_limits": "|".join(item.get("terminal_limits", [])),
            "code_outcome": score["code_outcome"],
            "tokens": item.get("tokens"), "remaining_of_500000": item.get("unspent_of_500000"),
            "attempts": item.get("attempts"), "decisions": item.get("decisions"),
            "agent_calls": item.get("agent_calls"), "condenser_calls": item.get("condenser_calls"),
            "agent_prompt_tokens": item.get("agent_prompt_tokens"),
            "agent_completion_tokens": item.get("agent_completion_tokens"),
            "condenser_prompt_tokens": item.get("condenser_prompt_tokens"),
            "condenser_completion_tokens": item.get("condenser_completion_tokens"),
            "controller_source_path": item["controller"]["path"],
            "controller_source_sha256": item["controller"]["sha256"],
            "code_score_status": score["code_score_status"],
            "code_score_revision": score["code_score_revision"],
        })
    categories = ("cumulative_token_reservation", "single_request_context",
                  "attempt_or_decision_limit", "time_boundary", "natural_or_no_explicit_limit",
                  "model_budget_unspecified", "other_historical_boundary")
    groups = {}
    table = []
    for group in sorted({row["group"] for row in rows}):
        selected = [row for row in rows if row["group"] == group]
        stats = {"original_normal_closed_denominator": len(selected), "planned_denominator": 500,
                 "excluded_from_original_normal_closed": 500 - len(selected), "stops": {}}
        for name in categories:
            subset = [row for row in selected if row["stop_category"] == name]
            counter = Counter(row["code_outcome"] for row in subset)
            count = {"count": len(subset), "resolved_true": counter["resolved_true"],
                     "resolved_false": counter["resolved_false"],
                     "scoring_unknown": counter["scoring_unknown"],
                     "generation_unknown": counter["generation_unknown"]}
            assert sum(count[key] for key in count if key != "count") == count["count"]
            stats["stops"][name] = {**count,
                "remaining_tokens": distribution([row["remaining_of_500000"] for row in subset]),
                "attempts": distribution([row["attempts"] for row in subset]),
                "agent_calls": distribution([row["agent_calls"] for row in subset])}
            table.append({"group": group, "original_normal_closed_denominator": len(selected),
                          "stop_category": name, **count})
        assert sum(item["count"] for item in stats["stops"].values()) == len(selected)
        groups[group] = stats

    # Prespecified selection: first REF token-stop in retained frozen queue order, not by score.
    sample = next(row for row in rows if row["group"] == "Qwen:REF"
                  and row["stop_category"] == "cumulative_token_reservation")
    episode = Path(sample["controller_source_path"]).parent
    next_request = episode / "ref-ledger" / f"tokenize-{sample['attempts'] + 1:04d}.json"
    tokenization = json.loads(next_request.read_text())
    prompt = tokenization["response"]["count"]
    maximum_output = 32768
    assert prompt + maximum_output > sample["remaining_of_500000"] > 0
    assert tokenization["generation_attempt"] is False
    case = {"selection": "first Qwen REF cumulative-token stop in frozen queue order; no outcome selection",
            **sample, "next_request_input_tokens": prompt,
            "next_request_max_output_reservation": maximum_output,
            "next_request_total_reservation": prompt + maximum_output,
            "next_request_generation_attempt": False,
            "context_limit": tokenization["response"]["max_model_len"],
            "next_request_tokenization_source": reference(next_request),
            "interpretation": "Admission stopped another model request; it does not establish that extra budget would fix the task."}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, contents in (("slot-budget-outcomes.csv", rows), ("stop-outcome-counts.csv", table)):
        with (OUT / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(contents[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(contents)
    write_json("reservation-stop-example.json", case)
    write_json("summary.json", {
        "version": "v055-budget-constraint-audit-r1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [reference(META), reference(SCORES), reference(Path(__file__))],
        "original_normal_closed_count": len(rows), "planned_slots": len(scores), "groups": groups,
        "scope": ["Original normal-closed metadata only; later six recovered pre-entry slots excluded.",
                  "Latest reconciled official code outcome joined by unique slot_id.",
                  "Scoring unknown retained separately; none replaced with failure.",
                  "No score estimate on closed subset; table denominators are descriptive only.",
                  "Budget termination and resolved outcome association is not a causal estimate of extra-budget benefit.",
                  "Unknown legacy budget boundary subtype retained; not inferred from token count.",
                  "Natural means controller return/no reachable member, not official success.",
                  "Legacy global_cny labels do not prove the overall 2000-CNY cap was exhausted."],
        "generation_calls": 0, "test_executions": 0, "scoring_calls": 0})
    print(json.dumps({"output": str(OUT), "rows": len(rows), "groups": groups,
                      "sample": case}, ensure_ascii=False))


if __name__ == "__main__":
    main()
