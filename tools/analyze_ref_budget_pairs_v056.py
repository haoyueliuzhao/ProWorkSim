"""Describe paired budget outcomes without imputing missing technical results."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "runs/software-benchmark-v056/score-encoding-repair-r1/analysis-r2"
OUTPUT = ROOT / "artifacts/software-benchmark-v056/report-evidence-r1"
ARMS = ("REF_B0500K", "REF_B2000K", "REF_B5000K", "REF_B10000K")
SHORT = dict(zip(ARMS, ("500k", "2M", "5M", "10M"), strict=True))
PAIRS = ((0, 1), (1, 2), (2, 3), (0, 2), (0, 3))
BOOTSTRAP_SEED = 20261024056101
BOOTSTRAP_REPETITIONS = 10000


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def boolean(value):
    if value in (None, ""):
        return None
    if value not in ("True", "False"):
        raise ValueError("Unexpected outcome encoding")
    return value == "True"


def conjunction(left, right):
    if left is False or right is False:
        return False
    if left is True and right is True:
        return True
    return None


def percentile(values, proportion):
    position = (len(values) - 1) * proportion
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (position - lo) * (values[hi] - values[lo])


def stratified_pair_bootstrap(records, seed):
    strata = defaultdict(list)
    for record in records:
        strata[record["repo"]].append(record["delta"])
    if not records:
        return None
    rng = random.Random(seed)
    samples = []
    ordered = [strata[name] for name in sorted(strata)]
    for _ in range(BOOTSTRAP_REPETITIONS):
        total = sum(rng.choice(values) for values in ordered for _ in values)
        samples.append(total / len(records))
    samples.sort()
    return {
        "method": "paired tasks resampled within each observed repository, keeping its task count",
        "seed": seed, "replications": BOOTSTRAP_REPETITIONS,
        "percentile_95_interval": [percentile(samples, .025), percentile(samples, .975)],
        "stratum_counts": {name: len(values) for name, values in sorted(strata.items())},
        "scope": "auxiliary jointly known task subset only; no missing-outcome imputation",
        "caveat": "Descriptive conditional resampling, not a complete-panel confidence interval or population guarantee; singleton strata cannot exhibit within-stratum variation.",
    }


def comparison(tasks, low, high, index):
    joint, rows = [], []
    transitions = Counter()
    lower = upper = 0
    for instance, arms in tasks.items():
        left, right = arms[low], arms[high]
        a, b = left["code"], right["code"]
        lows = (0, 1) if a is None else (int(a),)
        highs = (0, 1) if b is None else (int(b),)
        minimum, maximum = min(highs) - max(lows), max(highs) - min(lows)
        lower += minimum
        upper += maximum
        row = {"instance_id": instance, "repo": left["repo"],
               "low_condition": low, "high_condition": high,
               "low_code": a, "high_code": b, "delta_min": minimum, "delta_max": maximum,
               "jointly_known": a is not None and b is not None,
               "low_stop": left["stop_class"], "high_stop": right["stop_class"],
               "low_budget_stop_high_native_finish": left["stop_class"] == "cumulative_token_budget"
                   and right["normal"] is True,
               "low_budget_stop_high_normal_and_resolved": left["stop_class"] == "cumulative_token_budget"
                   and right["normal_and_code"] is True}
        rows.append(row)
        if a is not None and b is not None:
            transitions[f"{int(a)}_to_{int(b)}"] += 1
            joint.append({"repo": left["repo"], "delta": int(b) - int(a)})
    n = len(joint)
    gain, loss = transitions["0_to_1"], transitions["1_to_0"]
    assert sum(transitions.values()) == n and len(rows) == 50
    result = {
        "low_condition": low, "high_condition": high, "planned_pairs": len(tasks),
        "jointly_known_pairs": n, "missing_at_least_one": len(tasks) - n,
        "jointly_known_repositories": len({row["repo"] for row in joint}),
        "both_fail": transitions["0_to_0"], "both_pass": transitions["1_to_1"],
        "fail_to_pass": gain, "pass_to_fail": loss,
        "net_successes_on_jointly_known": gain - loss,
        "net_difference_on_jointly_known": (gain - loss) / n if n else None,
        "full_50_task_difference_count_bounds": [lower, upper],
        "full_50_task_difference_rate_bounds": [lower / len(tasks), upper / len(tasks)],
        "bounds_meaning": "logical worst/best outcome assignments for technical unknowns; not confidence intervals",
        "jointly_known_bootstrap": stratified_pair_bootstrap(joint, BOOTSTRAP_SEED + index),
        "low_budget_stop_high_native_finish_count": sum(row["low_budget_stop_high_native_finish"] for row in rows),
        "low_budget_stop_high_normal_and_resolved_count": sum(row["low_budget_stop_high_normal_and_resolved"] for row in rows),
        "gained_task_ids": [row["instance_id"] for row in rows if row["low_code"] is False and row["high_code"] is True],
        "lost_task_ids": [row["instance_id"] for row in rows if row["low_code"] is True and row["high_code"] is False],
    }
    return result, rows


def write_csv(path, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    Path(path).write_text(buffer.getvalue())


def analyze(input_root=INPUT, output=OUTPUT):
    input_root, output = Path(input_root), Path(output)
    with (input_root / "slot-results.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    state = json.loads((input_root / "source-state.json").read_text())
    state_rows = {row["slot"]["slot_id"]: row for row in state["rows"]}
    if len(rows) != 200 or len(state_rows) != 200 or {row["slot_id"] for row in rows} != set(state_rows):
        raise ValueError("Need the fixed 50-task / four-arm panel")
    tasks, repositories = defaultdict(dict), defaultdict(list)
    for row in rows:
        original = state_rows[row["slot_id"]]
        code, normal = boolean(row["resolved"]), boolean(row["normal_completion"])
        expected_code = original["score"].get("resolved") if original["score"]["status"] == "official_report" else None
        if (code is not expected_code or row["condition_id"] != original["slot"]["condition_id"]
                or row["instance_id"] != original["slot"]["instance_id"]
                or row["generation_status"] != original["generation"]["status"]):
            raise ValueError("Derived row differs from its immutable state source")
        record = {**row, "code": code, "normal": normal, "normal_and_code": conjunction(code, normal)}
        arms = tasks[row["instance_id"]]
        if row["condition_id"] in arms:
            raise ValueError("Duplicate task condition")
        arms[row["condition_id"]] = record
        repositories[(row["repo"], row["condition_id"])].append(record)
    if len(tasks) != 50 or any(set(arms) != set(ARMS) for arms in tasks.values()):
        raise ValueError("Incomplete task inventory")
    comparisons, pair_rows = [], []
    for index, (a, b) in enumerate(PAIRS):
        value, details = comparison(tasks, ARMS[a], ARMS[b], index)
        comparisons.append(value)
        pair_rows.extend(details)
    task_rows, first_counts, all_known_counts = [], Counter(), Counter()
    reversals, censored = [], []
    for instance, arms in tasks.items():
        row = {"instance_id": instance, "repo": arms[ARMS[0]]["repo"]}
        successful = [arm for arm in ARMS if arms[arm]["normal_and_code"] is True]
        first = successful[0] if successful else None
        first_counts[first or "none_observed"] += 1
        all_known = all(arms[arm]["code"] is not None for arm in ARMS)
        all_known_counts[str(all_known).lower()] += 1
        row.update(all_four_code_results_known=all_known,
                   first_observed_normal_and_resolved_tier=first,
                   lower_tiers_known_not_normal_and_resolved=(
                       all(arms[arm]["normal_and_code"] is False for arm in ARMS[:ARMS.index(first)])
                       if first is not None else None))
        reversal_pairs = [f"{SHORT[ARMS[a]]}->{SHORT[ARMS[b]]}" for a in range(4) for b in range(a + 1, 4)
                          if arms[ARMS[a]]["code"] is True and arms[ARMS[b]]["code"] is False]
        row["known_success_reversals"] = ";".join(reversal_pairs)
        if reversal_pairs:
            reversals.append({"instance_id": instance, "repo": row["repo"], "comparisons": reversal_pairs})
        for arm in ARMS:
            row[f"{SHORT[arm]}_code"] = arms[arm]["code"]
            row[f"{SHORT[arm]}_normal_finish"] = arms[arm]["normal"]
            row[f"{SHORT[arm]}_stop"] = arms[arm]["stop_class"]
        task_rows.append(row)
        high = arms[ARMS[-1]]
        if high["stop_class"] == "cumulative_token_budget":
            censored.append({"instance_id": instance, "repo": row["repo"], "resolved": high["code"],
                             "actual_tokens": int(high["actual_tokens"]),
                             "model_attempts": int(high["model_attempts"]),
                             "interpretation": "still stopped at the 10M cumulative-token ceiling; not proof no larger budget could finish"})
    repository_rows = []
    for (repo, arm), subset in sorted(repositories.items()):
        known = sum(row["code"] is not None for row in subset)
        successes = sum(row["code"] is True for row in subset)
        repository_rows.append({"repo": repo, "condition": arm, "planned": len(subset),
            "scored": known, "successes": successes, "unknown": len(subset) - known,
            "success_rate_lower": successes / len(subset),
            "success_rate_upper": (successes + len(subset) - known) / len(subset),
            "native_finished": sum(row["normal"] is True for row in subset),
            "normal_and_resolved": sum(row["normal_and_code"] is True for row in subset),
            "budget_stops": sum(row["stop_class"] == "cumulative_token_budget" for row in subset),
            "sdk_stuck": sum(row["stop_class"] == "sdk_stuck" for row in subset)})
    pair_repository_rows = []
    for value in comparisons:
        low, high = value["low_condition"], value["high_condition"]
        for repo in sorted({row["repo"] for row in task_rows}):
            subset = [row for row in pair_rows if row["repo"] == repo and row["low_condition"] == low and row["high_condition"] == high]
            gains = sum(row["low_code"] is False and row["high_code"] is True for row in subset)
            losses = sum(row["low_code"] is True and row["high_code"] is False for row in subset)
            pair_repository_rows.append({"repo": repo, "low_condition": low, "high_condition": high,
                "planned_pairs": len(subset), "jointly_known_pairs": sum(row["jointly_known"] for row in subset),
                "fail_to_pass": gains, "pass_to_fail": losses, "net_known_successes": gains - losses,
                "full_repo_delta_count_lower": sum(row["delta_min"] for row in subset),
                "full_repo_delta_count_upper": sum(row["delta_max"] for row in subset)})
    stop_rows = []
    for arm in ARMS:
        subset = [arms[arm] for arms in tasks.values()]
        for stop in sorted({row["stop_class"] for row in subset}):
            selected = [row for row in subset if row["stop_class"] == stop]
            stop_rows.append({"condition": arm, "stop_class": stop, "count": len(selected),
                "code_pass": sum(row["code"] is True for row in selected),
                "code_fail": sum(row["code"] is False for row in selected),
                "code_unknown": sum(row["code"] is None for row in selected)})
    any_success = [instance for instance, arms in tasks.items()
                   if any(arms[arm]["code"] is True for arm in ARMS)]
    no_observed_success = [instance for instance in tasks if instance not in any_success]
    never_success_unknown = [instance for instance in no_observed_success
                            if any(tasks[instance][arm]["code"] is None for arm in ARMS)]
    all_failed = [instance for instance in no_observed_success if instance not in never_success_unknown]
    assert len(any_success) + len(no_observed_success) == 50
    assert len(all_failed) + len(never_success_unknown) == len(no_observed_success)
    non_normal_successes = {
        stop: sum(row["code_pass"] for row in stop_rows if row["stop_class"] == stop)
        for stop in ("cumulative_token_budget", "sdk_stuck")}
    output.mkdir(parents=True, exist_ok=True)
    result = {"version": "v056-paired-budget-report-analysis-r1",
        "created_utc": datetime.now(timezone.utc).isoformat(), "script": ref(__file__),
        "sources": {name: ref(input_root / name) for name in ("slot-results.csv", "source-state.json", "summary.json")},
        "planned_tasks": 50, "planned_episodes": 200, "repositories": len({row["repo"] for row in task_rows}),
        "comparisons": comparisons,
        "first_observed_normal_and_resolved_tier_counts": dict(first_counts),
        "all_four_code_results_known_counts": dict(all_known_counts),
        "tasks_with_any_known_success_reversal": reversals,
        "max_budget_token_censored_tasks": censored,
        "stop_by_official_result": stop_rows,
        "non_normal_finish_code_passes": non_normal_successes,
        "observed_success_across_tiers": {
            "any_tier_code_success_count": len(any_success), "any_tier_code_success_task_ids": any_success,
            "no_tier_code_success_observed_count": len(no_observed_success),
            "no_success_observed_with_any_unknown_count": len(never_success_unknown),
            "no_success_observed_with_any_unknown_task_ids": never_success_unknown,
            "all_four_known_code_fail_count": len(all_failed), "all_four_known_code_fail_task_ids": all_failed,
            "interpretation": "Descriptive coverage across four different conditions, never a single-run completion rate or an oracle score."},
        "limitations": ["These 50 repository-stratified tasks are a calibration panel, not the full 500-task benchmark.",
                        "Unknown technical outcomes remain missing; whole-panel rate bounds are logical bounds, not confidence intervals.",
                        "Bootstrap intervals use paired jointly-known tasks only, preserve repository counts, and do not account for missingness or unobserved repositories.",
                        "Four independent initializations per task are four conditions, not 200 independent tasks; equal seeds do not guarantee equal actions.",
                        "A first observed successful tier is not a monotone threshold or a guaranteed sufficient budget."],
        "model_calls": 0, "scoring_calls": 0}
    (output / "paired-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    write_csv(output / "task-budget-pairs.csv", pair_rows)
    write_csv(output / "task-budget-outcomes.csv", task_rows)
    write_csv(output / "repository-budget-outcomes.csv", repository_rows)
    write_csv(output / "repository-budget-pairs.csv", pair_repository_rows)
    write_csv(output / "stop-by-code-result.csv", stop_rows)
    print(json.dumps({"comparisons": comparisons,
                      "first_counts": dict(first_counts), "four_known": dict(all_known_counts),
                      "reversal_tasks": len(reversals), "censored": censored,
                      "non_normal_finish_code_passes": non_normal_successes,
                      "any_tier_code_success": len(any_success),
                      "no_tier_success_observed": len(no_observed_success),
                      "all_four_known_fail": len(all_failed),
                      "no_success_observed_with_unknown": len(never_success_unknown)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    analyze(args.input, args.output)


if __name__ == "__main__":
    main()
