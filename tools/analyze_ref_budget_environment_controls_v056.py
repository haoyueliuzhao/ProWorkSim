"""Compare three completed grader-only positive controls with original reports."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from analyze_ref_budget_failures_v056 import reference, load_ref, test_region, excerpt

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "runs/software-benchmark-v056/grading-environment-controls-r1"
OUT = ROOT / "artifacts/software-benchmark-v056/failure-analysis-r1/environment-controls.json"
DIAGNOSTICS = ROOT / "artifacts/software-benchmark-v056/failure-analysis-r1/official-failures.json"


def failure_block(text, test):
    leaf = test.split("::")[-1]
    headings = list(re.finditer(r"(?m)^_{5,}[^\n]+_{5,}$", text))
    for index, heading in enumerate(headings):
        if leaf not in heading.group():
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        return text[heading.start():end]
    return text


def analyze(root, output):
    plan_ref = reference(root / "plan.json")
    plan = load_ref(plan_ref)
    diagnostics_ref = reference(DIAGNOSTICS)
    diagnostics = load_ref(diagnostics_ref)
    records = []
    matched_sets = 0
    for item in plan["rows"]:
        task = item["instance_id"]
        folder = Path(item["directory"])
        receipt_ref = reference(folder / "receipt.json")
        receipt = load_ref(receipt_ref)
        identity = load_ref(receipt["identity"])
        quiet_ref = reference(folder / "quiescence.json")
        quiet = load_ref(quiet_ref)
        completion_ref = reference(folder / "completion.json")
        completion = load_ref(completion_ref)
        if (receipt["instance_id"] != task or receipt.get("model_calls") != 0
                or receipt.get("preparation_only") is not True
                or receipt.get("official_candidate_scores_changed") is not False
                or receipt.get("status") != "official_report" or receipt.get("resolved") is not False
                or quiet.get("quiescent") is not True or quiet.get("cleanup_errors")
                or completion.get("returncode") != 0):
            raise ValueError("Expected a completed independent failed positive control with quiescence")
        report = receipt["official_result"][1][task]
        if report.get("patch_successfully_applied") is not True or report.get("infra_failure") is not False:
            raise ValueError("Gold control failed before normal official evaluation")
        f, p = report["tests_status"]["FAIL_TO_PASS"], report["tests_status"]["PASS_TO_PASS"]
        logs = list((folder / "official-output").rglob("test_output.txt"))
        assert len(logs) == 1
        text, bounded = test_region(logs[0].read_text(errors="replace"))
        assert bounded
        target = (f["failure"] or p["failure"])[0]
        block = failure_block(text, target)
        symptoms = {
            "dns_resolution_failure": "Temporary failure in name resolution" in text,
            "network_unreachable": "Network is unreachable" in text,
            "recursive_httpbin_fixture": "recursive dependency involving fixture 'httpbin'" in text,
            "missing_trustme": "No module named 'trustme'" in text,
            "httpbin_org_seen": "httpbin.org" in text,
            "unroutable_10_255_255_1_seen": "10.255.255.1" in text,
        }
        matches = []
        for old in diagnostics["requests_environment_diagnostics"]:
            if old["instance_id"] != task:
                continue
            same_f = set(old["official_F2P_nonpass_names"]) == set(f["failure"])
            same_p = set(old["official_P2P_nonpass_names"]) == set(p["failure"])
            matched_sets += same_f and same_p
            matches.append({"slot_id": old["slot_id"], "condition_id": old["condition_id"],
                "official_resolved_unchanged": old["resolved"],
                "same_F2P_nonpass_set_as_gold": same_f, "same_P2P_nonpass_set_as_gold": same_p,
                "additional_F2P_nonpass_vs_gold": sorted(set(old["official_F2P_nonpass_names"]) - set(f["failure"])),
                "additional_P2P_nonpass_vs_gold": sorted(set(old["official_P2P_nonpass_names"]) - set(p["failure"])),
                "original_network_symptom": old["test_network_resolution_or_unreachable"],
                "original_recursive_fixture_symptom": old["test_recursive_fixture"],
                "sources": old["sources"]})
        records.append({"instance_id": task, "control_resolved": False,
            "control_F2P_success_count": len(f["success"]), "control_F2P_nonpass_count": len(f["failure"]),
            "control_P2P_success_count": len(p["success"]), "control_P2P_nonpass_count": len(p["failure"]),
            "control_F2P_nonpass_names": f["failure"], "control_P2P_nonpass_names": p["failure"],
            "symptoms_in_test_region": symptoms, "representative_official_nonpass_test": target,
            "nonpass_test_block_excerpt": block[:1400],
            "network_error_in_that_test": excerpt(block, r"(?:E +.*(?:ConnectionError|Network is unreachable|Temporary failure in name resolution))", before=200, after=700),
            "fixture_excerpt": excerpt(text, r"recursive dependency involving fixture 'httpbin'", before=200, after=500),
            "missing_module_excerpt": excerpt(text, r"ModuleNotFoundError: No module named 'trustme'", before=200, after=250),
            "receipt": receipt_ref, "identity": receipt["identity"], "test_log": reference(logs[0]),
            "quiescence": quiet_ref, "completion": completion_ref,
            "gold_patch_sha256": identity["gold_patch_sha256"], "gold_patch_bytes": identity["gold_patch_bytes"],
            "gold_patch_source": identity["gold_patch_source"], "original_request": item["original_request"],
            "image_id": identity["image"]["image_id"], "baseline_mapping": identity["baseline_mapping"],
            "limits": identity["limits"], "model_calls": 0,
            "matched_original_model_slots": matches})
    assert len(records) == 3 and sum(len(x["matched_original_model_slots"]) for x in records) == 12
    assert matched_sets == 10
    untested = [row for row in diagnostics["requests_environment_diagnostics"] if row["instance_id"] == "psf__requests-1766"]
    result = {"version": "v056-grader-environment-positive-control-analysis-r1",
        "created_utc": datetime.now(timezone.utc).isoformat(), "script": reference(__file__),
        "diagnostics_helper": reference(Path(__file__).with_name("analyze_ref_budget_failures_v056.py")),
        "control_plan": plan_ref, "original_failure_diagnostics": diagnostics_ref,
        "controls_completed": 3, "gold_patch_applied_controls": 3, "gold_resolved_controls": 0,
        "containers_quiescent": 3, "original_model_slots_with_same_task_and_environment": 12,
        "original_slots_matching_both_gold_nonpass_sets": matched_sets,
        "rows": records,
        "untested_requests_1766": {"gold_control_performed": False,
            "original_slot_ids": [row["slot_id"] for row in untested],
            "all_four_network_log_symptom": all(row["test_network_resolution_or_unreachable"] for row in untested),
            "interpretation": "log-based environment suspicion only; not covered by the three gold controls"},
        "supported_conclusion": "The frozen local offline grader cannot resolve the official gold patch on these three tasks. Their original false scores cannot all be attributed to model repair capability.",
        "limits": [
            "A failed positive control does not prove every model patch is correct or would pass in a repaired environment.",
            "Matching F2P/P2P nonpass sets is diagnostic agreement, not a replacement resolved score.",
            "Two 500k model candidates additionally fail their target F2P test beyond the gold control failures.",
            "No benchmark score, denominator, candidate, actor feedback, or generation history is changed.",
            "The fourth requests task has only log evidence, not a gold positive control.",
            "The controls establish a grading-environment problem; the exact remedy and corrected benchmark scores are not measured here."],
        "model_calls": 0, "new_scoring_calls_in_analysis": 0, "separately_completed_gold_scoring_calls": 3,
        "official_candidate_scores_changed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"gold_controls": 3, "gold_resolved": 0, "original_slots_same_failure_sets": matched_sets,
                      "containers_quiescent": 3, "model_calls": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=CONTROL)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    analyze(args.root, args.output)


if __name__ == "__main__":
    main()
