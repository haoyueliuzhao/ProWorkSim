"""Read-only paired budget diagnostics; never treat a stopped run as a failed repair."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import statistics

from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]
BUDGET_ORDER = ("REF_B0500K", "REF_B2000K", "REF_B5000K", "REF_B10000K")


def load(ref):
    return json.loads(checked(ref).read_bytes())


def stop_class(controller, generation_status):
    if generation_status == "deferred":
        return "technical_unknown"
    boundary = controller.get("terminal_boundary", {}).get("reason", "")
    if boundary == "full_input_and_output_reservation_insufficient":
        return "cumulative_token_budget"
    if boundary == "full_context_preexecution_rejection":
        return "context"
    if boundary in {"all_model_attempt_limit", "agent_decision_limit"}:
        return "attempt_or_decision"
    if "deadline" in boundary:
        return "time"
    if controller.get("normal_completion") is True:
        return "native_finished"
    if controller.get("sdk_execution_status") in {"stuck", "error"}:
        return "sdk_" + controller["sdk_execution_status"]
    return "pending" if generation_status in {"pending", "running"} else "other_return"


def table(path, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, buffer.getvalue().encode())


def analyze(state_path, output):
    state_path, output = Path(state_path), Path(output)
    raw_state = state_path.read_bytes()
    state = json.loads(raw_state)
    rows, groups, paired = [], defaultdict(list), defaultdict(dict)
    for item in state["rows"]:
        slot, generation, score = item["slot"], item["generation"], item["score"]
        controller, ledger, outcome = {}, {}, None
        if generation.get("result"):
            result = load(generation["result"])
            if result.get("controller_result"):
                controller = load(result["controller_result"])
            else:
                path = Path(generation["result"]["path"]).parent / "controller-result.json"
                if path.is_file():
                    controller = json.loads(path.read_bytes())
            ledger = controller.get("ledger", {})
        if score.get("status") == "official_report":
            outcome = score["resolved"]
        usage = ledger.get("per_usage_id", {})
        row = {"slot_id": slot["slot_id"], "instance_id": slot["instance_id"], "repo": slot["repo"],
            "condition_id": slot["condition_id"], "seed": slot["seed"],
            "token_limit": slot["input_plus_output_tokens"], "generation_status": generation["status"],
            "stop_class": stop_class(controller, generation["status"]), "score_status": score["status"],
            "resolved": outcome, "normal_completion": controller.get("normal_completion"),
            "normal_and_resolved": controller.get("normal_completion") is True and outcome is True,
            "actual_tokens": ledger.get("complete_actual_tokens"),
            "known_tokens": ledger.get("known_actual_tokens"),
            "uncertain_reserved_tokens": ledger.get("uncertain_reserved_tokens"),
            "model_attempts": ledger.get("attempts"), "agent_decisions": ledger.get("decisions"),
            "prompt_tokens": sum(value.get("prompt_tokens", 0) for value in usage.values()) if ledger else None,
            "completion_tokens": sum(value.get("completion_tokens", 0) for value in usage.values()) if ledger else None,
            "condenser_tokens": sum(usage.get("condenser", {}).values()) if ledger else None,
            "generation_result": generation.get("result", {}).get("path")}
        rows.append(row)
        groups[slot["condition_id"]].append(row)
        paired[slot["instance_id"]][slot["condition_id"]] = row
    summaries = {}
    for name in BUDGET_ORDER:
        subset = groups[name]
        known_tokens = [row["actual_tokens"] for row in subset if type(row["actual_tokens"]) is int]
        successes = sum(row["resolved"] is True for row in subset)
        unknown = sum(row["resolved"] is None for row in subset)
        summaries[name] = {"planned": len(subset), "stop_classes": dict(Counter(row["stop_class"] for row in subset)),
            "known_successes": successes, "unknown_or_pending_code_results": unknown,
            "code_result_bounds": [successes / len(subset), (successes + unknown) / len(subset)],
            "normal_and_resolved": sum(row["normal_and_resolved"] for row in subset),
            "actual_tokens_known_rows": len(known_tokens), "known_actual_tokens": sum(known_tokens),
            "actual_token_median_known_rows": statistics.median(known_tokens) if known_tokens else None}
    boundaries = []
    for instance, arms in paired.items():
        successful = [name for name in BUDGET_ORDER if arms[name]["normal_and_resolved"]]
        known_code = [arms[name]["resolved"] for name in BUDGET_ORDER]
        reversal = any(known_code[i] is True and known_code[j] is False
                       for i in range(4) for j in range(i + 1, 4))
        boundaries.append({"instance_id": instance, "repo": arms[BUDGET_ORDER[0]]["repo"],
            "first_observed_normal_and_resolved_tier": successful[0] if successful else None,
            "higher_budget_known_success_reversal": reversal,
            "maximum_tier_token_censored": arms[BUDGET_ORDER[-1]]["stop_class"] == "cumulative_token_budget",
            "all_four_code_results_known": all(type(value) is bool for value in known_code)})
    output.mkdir(parents=True, exist_ok=True)
    atomic_write(output / "source-state.json", raw_state)
    value = {"version": "v056-ref-budget-analysis-r1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "state_source": {"path": str(state_path), "sha256": hashlib.sha256(raw_state).hexdigest(),
                         "bytes": len(raw_state)},
        "retained_state_snapshot": reference(output / "source-state.json"),
        "complete": state["complete"], "groups": summaries,
        "source_claims": "Descriptive 50-task repository-stratified calibration; no general success guarantee",
        "boundary_caveat": "First successful tier is observed, not a proof of monotonicity or a universal minimum",
        "generation_calls": 0, "test_executions": 0, "scoring_calls": 0}
    atomic_write(output / "summary.json", json_bytes(value))
    table(output / "slot-results.csv", rows)
    table(output / "task-budget-boundaries.csv", boundaries)
    print(json.dumps(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=ROOT / "runs/software-benchmark-v056/queue-r1/state.json")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/software-benchmark-v056/analysis-r1")
    args = parser.parse_args()
    analyze(args.state, args.output)


if __name__ == "__main__":
    main()
