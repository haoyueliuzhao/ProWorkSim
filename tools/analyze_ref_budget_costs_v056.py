"""Read-only v056 cost audit, retaining known usage from all technical unknowns."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics

from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs/software-benchmark-v056"
ANALYSIS = RUNS / "score-encoding-repair-r1/analysis-r2"
OUT = ROOT / "artifacts/software-benchmark-v056/report-evidence-r1"
ARMS = ("REF_B0500K", "REF_B2000K", "REF_B5000K", "REF_B10000K")


def read(path):
    return json.loads(Path(path).read_bytes())


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * fraction
    index = int(position)
    return values[index] + (values[min(index + 1, len(values) - 1)] - values[index]) * (position - index)


def distribution(values):
    return {"n": len(values), "sum": sum(values),
            "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "p90": percentile(values, .9), "max": max(values) if values else None}


def aggregate(rows):
    return {
        "rows": len(rows),
        "generation_status": dict(Counter(row["generation_status"] for row in rows)),
        "complete_actual_usage_rows": sum(row["complete_actual_tokens"] is not None for row in rows),
        "incomplete_actual_usage_rows": sum(row["complete_actual_tokens"] is None for row in rows),
        "known_actual_tokens": sum(row["known_actual_tokens"] for row in rows),
        "prompt_tokens_known": sum(row["prompt_tokens_known"] for row in rows),
        "completion_tokens_known": sum(row["completion_tokens_known"] for row in rows),
        "reasoning_tokens_known": sum(row["reasoning_tokens_known"] for row in rows),
        "reasoning_usage_missing_calls": sum(row["reasoning_usage_missing_calls"] for row in rows),
        "completion_nonreasoning_tokens_known": sum(row["completion_nonreasoning_tokens_known"] for row in rows),
        "condenser_prompt_tokens_known": sum(row["condenser_prompt_tokens_known"] for row in rows),
        "condenser_completion_tokens_known": sum(row["condenser_completion_tokens_known"] for row in rows),
        "uncertain_reserved_tokens_not_actual": sum(row["uncertain_reserved_tokens"] for row in rows),
        "model_attempts": distribution([row["model_attempts"] for row in rows]),
        "agent_decisions": distribution([row["agent_decisions"] for row in rows]),
        "known_actual_tokens_per_episode": distribution([row["known_actual_tokens"] for row in rows]),
        "complete_actual_tokens_per_episode": distribution([row["complete_actual_tokens"] for row in rows
                                                           if row["complete_actual_tokens"] is not None]),
        "closed_episode_enter_to_quiescence_seconds": distribution([
            row["entered_to_quiescence_seconds"] for row in rows
            if row["generation_status"] == "closed" and row["entered_to_quiescence_seconds"] is not None]),
    }


def audit(analysis, output):
    analysis, output = Path(analysis), Path(output)
    state_path, csv_path = analysis / "source-state.json", analysis / "slot-results.csv"
    state = read(state_path)
    with csv_path.open() as stream:
        classifications = {row["slot_id"]: row for row in csv.DictReader(stream)}
    rows, examples, sources = [], [], []
    for item in state["rows"]:
        slot = item["slot"]
        generation = item["generation"]
        job = state["jobs"][generation["job_id"]]
        folder = Path(job["payload"]["output"])
        ledger_path, start_path = folder / "ref-ledger/ledger.json", folder / "start.json"
        ledger, start = read(ledger_path), read(start_path)
        assert ledger["slot_id"] == slot["slot_id"] and start["slot"] == slot
        calls = ledger["calls"]
        calls_with_usage = [call for call in calls if call.get("usage")]
        prompt = sum(call["usage"]["prompt_tokens"] for call in calls_with_usage)
        completion = sum(call["usage"]["completion_tokens"] for call in calls_with_usage)
        assert prompt + completion == ledger["known_actual_tokens"]
        assert prompt == sum(value["prompt_tokens"] for value in ledger["per_usage_id"].values())
        assert completion == sum(value["completion_tokens"] for value in ledger["per_usage_id"].values())
        reasoning = sum((call["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
                        for call in calls_with_usage)
        missing_reasoning = sum((call["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens") is None
                                for call in calls_with_usage)
        assert reasoning <= completion
        # Accounting certainty and trusted candidate closure are distinct:
        # four interrupted slots have fully settled usage but no closed candidate.
        if ledger["complete_actual_tokens"] is not None:
            assert ledger["complete_actual_tokens"] == ledger["known_actual_tokens"]
            assert ledger["uncertain_reserved_tokens"] == 0
        else:
            assert ledger["uncertain_reserved_tokens"] > 0
        claim = Path(start["guard_path"]).parent
        quiescence_path = claim / "quiescence.json"
        duration = None
        if generation["status"] == "closed":
            quiet = read(quiescence_path)
            assert quiet["all_quiet"] is True
            duration = quiet["monotonic_finished"] - start["started"]
            assert 0 <= duration < 23460
        classification = classifications[slot["slot_id"]]
        row = {
            "slot_id": slot["slot_id"], "condition_id": slot["condition_id"],
            "instance_id": slot["instance_id"], "repo": slot["repo"],
            "generation_status": generation["status"], "stop_class": classification["stop_class"],
            "token_limit": ledger["token_limit"], "known_actual_tokens": ledger["known_actual_tokens"],
            "complete_actual_tokens": ledger["complete_actual_tokens"],
            "uncertain_reserved_tokens": ledger["uncertain_reserved_tokens"],
            "prompt_tokens_known": prompt, "completion_tokens_known": completion,
            "reasoning_tokens_known": reasoning, "reasoning_usage_missing_calls": missing_reasoning,
            "completion_nonreasoning_tokens_known": completion - reasoning,
            "condenser_prompt_tokens_known": ledger["per_usage_id"].get("condenser", {}).get("prompt_tokens", 0),
            "condenser_completion_tokens_known": ledger["per_usage_id"].get("condenser", {}).get("completion_tokens", 0),
            "model_attempts": ledger["attempts"], "settled_model_calls": len(calls_with_usage),
            "agent_decisions": ledger["decisions"], "ledger_halted": ledger["halted"],
            "entered_to_quiescence_seconds": duration,
            "unspent_after_known_usage": ledger["token_limit"] - ledger["known_actual_tokens"],
        }
        if row["stop_class"] == "cumulative_token_budget":
            path = folder / "ref-ledger" / f"request-{ledger['attempts'] + 1:04d}.json"
            request = read(path)
            reservation = request["exact_input"]["prompt_tokens"] + request["request"]["max_tokens"]
            assert request["request"]["max_tokens"] == 32768
            assert row["unspent_after_known_usage"] < reservation
            assert ledger["complete_actual_tokens"] is not None
            row.update(rejected_next_prompt_tokens=request["exact_input"]["prompt_tokens"],
                       rejected_next_output_reservation=32768,
                       rejected_next_total_reservation=reservation)
            if slot["condition_id"] not in {entry["condition_id"] for entry in examples}:
                examples.append({**row, "rejected_request": reference(path)})
        else:
            row.update(rejected_next_prompt_tokens=None, rejected_next_output_reservation=None,
                       rejected_next_total_reservation=None)
        rows.append(row)
        sources.append({"slot_id": slot["slot_id"], "ledger": reference(ledger_path),
                        "start": reference(start_path),
                        "quiescence": reference(quiescence_path) if duration is not None else None})
    assert len(rows) == 200
    closed = [row for row in rows if row["generation_status"] == "closed"]
    unknown = [row for row in rows if row["generation_status"] == "deferred"]
    assert len(closed) == 186 and len(unknown) == 14
    groups = {}
    for arm in ARMS:
        subset = [row for row in rows if row["condition_id"] == arm]
        stopped = [row for row in subset if row["stop_class"] == "cumulative_token_budget"]
        groups[arm] = {"all_planned": aggregate(subset),
            "closed_only": aggregate([row for row in subset if row["generation_status"] == "closed"]),
            "generation_unknown_only": aggregate([row for row in subset if row["generation_status"] == "deferred"]),
            "observed_cumulative_token_cutoff_count": len(stopped),
            "cutoff_unspent_tokens": distribution([row["unspent_after_known_usage"] for row in stopped])}
    assert [groups[arm]["observed_cumulative_token_cutoff_count"] for arm in ARMS] == [44, 22, 5, 3]
    events_path = RUNS / "queue-r2/events.jsonl"
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    stopped = next(event for event in events if event["kind"] == "coordinator_stopped")
    resumed = next(event for event in events if event["kind"] == "job_launch"
                   and event.get("kind_name") == "generation" and event["utc"] > stopped["utc"])
    interruption = {"source": reference(events_path), "stop_event": stopped,
                    "first_new_generation_launch": resumed,
                    "seconds_without_new_generation_dispatch":
                    (datetime.fromisoformat(resumed["utc"]) - datetime.fromisoformat(stopped["utc"])).total_seconds(),
                    "meaning": "Observed coordinator stop to first newly dispatched generation; not total host/GPU idle time"}
    totals = aggregate(rows)
    totals["prompt_fraction_of_known_tokens"] = totals["prompt_tokens_known"] / totals["known_actual_tokens"]
    value = {"version": "v056-ref-budget-cost-audit-r1", "sources": {
                "analysis_state": reference(state_path), "classification_csv": reference(csv_path),
                "script": reference(__file__)},
             "planned_token_upper_bound": 875_000_000, "all_200_planned": totals,
             "closed_186": aggregate(closed), "generation_unknown_14": aggregate(unknown),
             "groups": groups, "reservation_cutoff_examples": examples,
             "generation_unknown_rows": unknown, "service_interruption": interruption,
             "per_slot_evidence": sources,
             "interpretation": {
                 "known_usage_is_lower_bound_if_inflight_uncertain": True,
                 "uncertain_reservation_is_not_observed_token_consumption": True,
                 "incomplete_ledger_not_same_as_unknown_model_outcome": True,
                 "tokens_include_repeated_inputs_agent_and_condenser": True,
                 "duration": "Monotonic entered REF to quiescent actor/controller, closed 186 only; excludes rootfs preparation, export, official scoring and downtime between episodes; includes tool/CPU waits and shutdown",
                 "duration_not_gpu_compute_or_residency_time": True,
                 "condenser_tokens_are_included_not_additional": True,
                 "reasoning_tokens_are_subset_of_completion": True,
                 "no_model_or_scoring_calls": True}}
    output.mkdir(parents=True, exist_ok=True)
    atomic_write(output / "cost-analysis.json", json_bytes(value))
    with (output / "slot-costs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"totals": totals, "unknown": aggregate(unknown), "interruption": interruption,
                      "groups": {arm: {"known_tokens": groups[arm]["all_planned"]["known_actual_tokens"],
                          "complete_usage_n": groups[arm]["all_planned"]["complete_actual_usage_rows"],
                          "duration": groups[arm]["closed_only"]["closed_episode_enter_to_quiescence_seconds"]}
                                 for arm in ARMS}}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=ANALYSIS)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    audit(args.analysis, args.output)


if __name__ == "__main__":
    main()
