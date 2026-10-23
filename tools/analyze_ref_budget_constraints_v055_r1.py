"""REF-only descriptive follow-up using existing compact metadata and stop audit."""
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
INPUT = OUT / "slot-budget-outcomes.csv"
GROUPS = ("Qwen:REF", "DeepSeek:REF-nonthinking", "DeepSeek:REF-thinking")


def reference(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def quantile(values, fraction):
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def distribution(values):
    values = sorted(float(value) for value in values if value not in {None, ""})
    if not values:
        return {"n": 0}
    return {"n": len(values), "sum": sum(values), "min": values[0],
            "p25": quantile(values, .25), "median": statistics.median(values),
            "p75": quantile(values, .75), "max": values[-1], "mean": statistics.mean(values)}


def outcomes(rows):
    counts = Counter(row["code_outcome"] for row in rows)
    return {"n": len(rows), **{name: counts[name] for name in (
        "resolved_true", "resolved_false", "scoring_unknown", "generation_unknown")}}


def summarize(rows):
    metrics = ("tokens", "remaining_of_500000", "attempts", "decisions", "agent_calls",
               "condenser_calls", "agent_prompt_tokens", "agent_completion_tokens",
               "condenser_prompt_tokens", "condenser_completion_tokens")
    totals = {name: sum(int(row[name]) for row in rows) for name in (
        "tokens", "attempts", "agent_calls", "condenser_calls", "agent_prompt_tokens",
        "agent_completion_tokens", "condenser_prompt_tokens", "condenser_completion_tokens")}
    input_tokens = totals["agent_prompt_tokens"] + totals["condenser_prompt_tokens"]
    output_tokens = totals["agent_completion_tokens"] + totals["condenser_completion_tokens"]
    condenser_tokens = totals["condenser_prompt_tokens"] + totals["condenser_completion_tokens"]
    calls = totals["agent_calls"] + totals["condenser_calls"]
    assert input_tokens + output_tokens == totals["tokens"]
    composition = {"total_input_tokens": input_tokens, "total_output_tokens": output_tokens,
        "total_condenser_tokens": condenser_tokens, "total_tokens": totals["tokens"],
        "settled_calls": calls, "ledger_attempts": totals["attempts"],
        "input_fraction": input_tokens / totals["tokens"] if totals["tokens"] else None,
        "output_fraction": output_tokens / totals["tokens"] if totals["tokens"] else None,
        "condenser_fraction": condenser_tokens / totals["tokens"] if totals["tokens"] else None,
        "mean_input_tokens_per_settled_call": input_tokens / calls if calls else None,
        "mean_output_tokens_per_settled_call": output_tokens / calls if calls else None}
    return {**outcomes(rows), "token_composition": composition,
            "metrics": {name: distribution([row[name] for row in rows]) for name in metrics},
            "attempts_below_128": sum(int(row["attempts"]) < 128 for row in rows),
            "attempts_at_or_above_128": sum(int(row["attempts"]) >= 128 for row in rows),
            "decisions_below_128": sum(int(row["decisions"]) < 128 for row in rows),
            "terminal_reason_counts": dict(Counter(row["terminal_reason"] for row in rows))}


def deepseek_case(row):
    episode = Path(row["controller_source_path"]).parent
    controller = json.loads((episode / "controller-result.json").read_text())
    config = json.loads((episode / "controller-config.json").read_text())
    source = ROOT / "src/proworksim/software_benchmark_deepseek_interfaces_v055.py"
    source_ref = reference(source)
    frozen = next(item for item in config["frozen_sources"] if item["path"] == str(source))
    assert source_ref["sha256"] == frozen["sha256"]
    index = int(row["attempts"]) + 1
    absent_request = episode / "deepseek-ledger" / f"request-{index:04d}.json"
    assert not absent_request.exists()
    remaining = int(row["remaining_of_500000"])
    assert controller["terminal_boundary"] == "episode_token_reservation_exhausted"
    return {
        "selection": "first cumulative-token stop in retained frozen queue order, not by score",
        "group": row["group"], "slot_id": row["slot_id"], "instance_id": row["instance_id"],
        "code_outcome": row["code_outcome"], "actual_tokens": int(row["tokens"]),
        "remaining_tokens": remaining, "next_request_max_output_tokens": 32768,
        "next_request_input_tokens": None, "next_request_total_reservation": None,
        "input_count_retention": "Not persisted: budget admission rejection precedes request artifact write.",
        "input_reservation_strictly_greater_than": remaining - 32768,
        "output_reservation_alone_exceeds_remaining": 32768 > remaining,
        "next_request_artifact_exists": False, "next_request_generation_dispatched": False,
        "known_attempts": controller["ledger"]["attempts"],
        "inflight_at_stop": controller["ledger"]["inflight"],
        "boundary": controller["terminal_boundary"],
        "controller_source": reference(episode / "controller-result.json"),
        "configuration_source": reference(episode / "controller-config.json"),
        "frozen_source_reference": frozen, "verified_current_source_reference": source_ref,
        "source_order_evidence": {
            "method": "DeepSeekAdapter.complete", "budget_rejection_line": 202,
            "request_artifact_write_line": 204, "provider_complete_call_line": 226,
            "order": "count; context guard; call guard; token guard; persist request; provider dispatch"},
        "interpretation": "A later request was prevented; benefit of extra budget is not observed."}


def main():
    with INPUT.open(newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["group"] in GROUPS]
    groups, table, cases = {}, [], []
    for group in GROUPS:
        selected = [row for row in rows if row["group"] == group]
        budget = [row for row in selected if row["stop_category"] == "cumulative_token_reservation"]
        other = [row for row in selected if row["stop_category"] != "cumulative_token_reservation"]
        stats = {"planned_denominator": 500, "original_normal_closed_denominator": len(selected),
                 "excluded_from_stop_audit": 500 - len(selected),
                 "confirmed_budget_stops_per_planned500": len(budget) / 500,
                 "token_stopped_fraction_of_original_closed": len(budget) / len(selected),
                 "token_stopped": summarize(budget),
                 "not_token_stopped": summarize(other),
                 "all_original_closed": summarize(selected), "by_recorded_terminal_reason": {}}
        for reason in sorted({row["terminal_reason"] for row in selected}):
            subset = [row for row in selected if row["terminal_reason"] == reason]
            stats["by_recorded_terminal_reason"][reason] = outcomes(subset)
            table.append({"group": group, "planned_denominator": 500,
                          "confirmed_budget_stop_count": len(budget),
                          "confirmed_budget_stops_per_planned500": len(budget) / 500,
                          "excluded_from_stop_audit": 500 - len(selected),
                          "original_normal_closed_denominator": len(selected),
                          "terminal_reason": reason, **outcomes(subset)})
        groups[group] = stats
        if group == "Qwen:REF":
            cases.append(json.loads((OUT / "reservation-stop-example.json").read_text()))
        else:
            cases.append(deepseek_case(budget[0]))
    summary = {
        "version": "v055-ref-budget-constraint-audit-r1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [reference(INPUT), reference(Path(__file__))], "groups": groups,
        "planned_panel_aggregate": {
            "planned_denominator": 1500,
            "confirmed_budget_stop_count": sum(group["token_stopped"]["n"] for group in groups.values()),
            "confirmed_budget_stops_per_planned1500": sum(
                group["token_stopped"]["n"] for group in groups.values()) / 1500,
            "included_in_stop_audit": len(rows), "excluded_from_stop_audit": 1500 - len(rows)},
        "quartiles": "Linear interpolation at (n-1)*p; metrics derived from retained controller ledger metadata.",
        "scope": [
            "Original normal-closed subset only; final official outcomes joined without selecting successful tasks.",
            "Excluded-from-stop-audit slots are not necessarily current generation unknowns; some were recovered later.",
            "Not-token-stopped is a recorded-boundary classification, not proof of voluntary model finish.",
            "SDK_returned_without_explicit_limit_boundary does not rule out an unrecorded SDK iteration boundary.",
            "Ledger attempts include Agent and condenser; SDK iterations and individual tool executions are different units.",
            "Below 128 attempts is measured ledger state, not proof that SDK max_iterations was never reached.",
            "No extra-budget continuation, no causal estimate of recoverable failures.",
            "DeepSeek rejected prompt counts were not persisted; exact values intentionally remain null."],
        "reservation_cases": cases, "generation_calls": 0, "test_executions": 0, "scoring_calls": 0}
    (OUT / "ref-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    with (OUT / "ref-stop-outcome-counts.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(table)
    print(json.dumps({"groups": groups, "cases": cases}, ensure_ascii=False))


if __name__ == "__main__":
    main()
