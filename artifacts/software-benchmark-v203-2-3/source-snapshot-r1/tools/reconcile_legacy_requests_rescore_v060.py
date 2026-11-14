"""Reconcile only the eight fixed legacy Requests candidates after v060 grading."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_rescore_policy_v060 import require_v060_rescore_allowed
from proworksim.software_benchmark_grading_qualification_v060 import validate_transport_evidence
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "runs/software-benchmark-v056/queue-r2"
TASKS = frozenset(("psf__requests-1766", "psf__requests-1921"))
VERSION = "v060-original-candidate-reconciliation-r1"


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


legacy = module("v060_prior_reconciliation", "repair_ref_grading_environment_v058.py")


def load(ref):
    return json.loads(checked(ref).read_bytes())


def reconcile_evidence(state, prior, plan, outcomes):
    """Preserve other 192 slots, including eight already corrected in v058."""
    rows = plan.get("rows", [])
    expected = {(task, condition) for task in TASKS for condition in
                ("REF_B0500K", "REF_B2000K", "REF_B5000K", "REF_B10000K")}
    actual = {(row.get("instance_id"), row.get("condition_id")) for row in rows}
    allowed = {row.get("slot_id") for row in rows}
    if len(rows) != 8 or len(allowed) != 8 or actual != expected:
        raise ValueError("Reconciliation is restricted to the original two tasks and four budgets")
    result, changed, unknown = legacy.reconciled_state(state, prior, allowed, outcomes)
    before = {row["slot"]["slot_id"]: row for row in state["rows"]}
    for row in result["rows"]:
        slot = row["slot"]["slot_id"]
        if slot not in allowed and row != before[slot]:
            raise ValueError("Reconciliation changed an unrelated task")
    return result, changed, unknown


def environment_strata(state):
    measured = legacy.measurement_state(state)
    counts = {}
    for row in measured["rows"]:
        score = row["score"]
        if score.get("status") == "official_report":
            revision = score.get("scoring_revision", "original-v056")
            counts[revision] = counts.get(revision, 0) + 1
    return {
        "known_reports_by_revision": counts,
        "environment_review_unknown": sum(
            row.get("environment_review", {}).get("status") == "unresolved"
            for row in state["rows"]),
        "generation_unknown": sum(row["generation"]["status"] == "deferred" for row in state["rows"]),
        "homogeneous_full_panel_environment": False,
    }


def collect_outcomes(plan):
    outcomes = legacy.collect_outcomes(plan)
    for outcome in outcomes:
        if not outcome.get("known"):
            continue
        try:
            identity = load(outcome["identity"])
            output = Path(outcome["identity"]["path"]).parent
            observed_ref = reference(output / "initial-container.json")
            validate_transport_evidence(outcome["receipt"], outcome["quiescence"],
                load(observed_ref), identity, output, transport_directory=output, require_usage=False)
            outcome["initial_container"] = observed_ref
        except (ValueError, TypeError, KeyError, OSError) as error:
            outcome["known"] = False
            outcome["error"] = {"type": type(error).__name__, "message": str(error)}
    return outcomes


def reconcile(root):
    require_v060_rescore_allowed("v060.rescore.reconcile")
    root = Path(root).resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v060"):
        raise ValueError("Use the fresh v060 result directory")
    if (root / "reconciliation.json").exists():
        return load(reference(root / "reconciliation.json"))
    runner = module("v060_reconciliation_runner", "repair_legacy_requests_rescore_v060.py")
    plan = runner.validate_plan(load(reference(root / "plan.json")))
    outcomes = collect_outcomes(plan)
    write_new(root / "collected-outcomes.json", {"version": VERSION, "rows": outcomes})
    with legacy.queue.lock(QUEUE / "coordinator.lock"):
        current_ref = reference(QUEUE / "state.json")
        merged, changed, unknown = reconcile_evidence(
            load(current_ref), load(plan["pre_state"]), plan, outcomes)
        strata = environment_strata(merged)
        record = {
            "version": VERSION, "utc": legacy.queue.now(), "prior_state": current_ref,
            "retained_pre_state": plan["pre_state"], "score_changes": changed,
            "unresolved_slots": unknown, "scoring_environment_strata": strata,
            "model_calls": 0, "generation_restarted": False, "candidate_content_changed": False,
            "unrelated_slots_changed": False, "outcomes": reference(root / "collected-outcomes.json"),
        }
        merged["updated_utc"] = record["utc"]
        merged.setdefault("score_recoveries", []).append(record.copy())
        atomic_write(QUEUE / "state.json", json_bytes(merged))
        status = legacy.queue.summary(merged)
        status["scoring_environment_strata"] = strata
        status["current_environment_unknown_slots"] = unknown
        atomic_write(QUEUE / "status.json", json_bytes(status))
        with (QUEUE / "events.jsonl").open("a") as stream:
            stream.write(json.dumps({"utc": record["utc"], "kind": VERSION,
                "updated_slots": [item["slot_id"] for item in changed],
                "unresolved_slots": unknown, "model_calls": 0}) + "\n")
        record["post_state"] = reference(QUEUE / "state.json")
        write_new(root / "reconciliation.json", record)
    measurement = write_new(root / "measurement-state.json", legacy.measurement_state(merged))
    analyzer = module("v060_budget_analysis", "analyze_ref_budget_results_v056.py")
    analyzer.analyze(Path(measurement["path"]), root / "analysis-r1")
    summary_path = root / "analysis-r1/summary.json"
    summary = json.loads(summary_path.read_bytes())
    summary.update(scoring_environment_strata=strata, measurement_state=measurement,
                   environment_repair=reference(root / "reconciliation.json"))
    atomic_write(summary_path, json_bytes(summary))
    with (root / "analysis-r1/scoring-environments.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("slot_id", "condition_id", "status", "resolved",
                                                    "scoring_revision", "environment_unknown"), lineterminator="\n")
        writer.writeheader()
        for row in legacy.measurement_state(merged)["rows"]:
            writer.writerow({"slot_id": row["slot"]["slot_id"], "condition_id": row["slot"]["condition_id"],
                "status": row["score"]["status"], "resolved": row["score"].get("resolved"),
                "scoring_revision": row["score"].get("scoring_revision", "original-v056"),
                "environment_unknown": row.get("environment_review", {}).get("status") == "unresolved"})
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.root), ensure_ascii=False))


if __name__ == "__main__":
    main()
