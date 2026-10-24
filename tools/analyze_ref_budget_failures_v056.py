"""Read-only official-test and final-patch diagnostics for the v056 budget panel.

Reported nonpasses are endpoints, not automatically causal model errors. Test
log environment symptoms are kept separate and never alter official scores.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "runs/software-benchmark-v056/score-encoding-repair-r1/analysis-r2"
OUTPUT = ROOT / "artifacts/software-benchmark-v056/failure-analysis-r1"
ARMS = ("REF_B0500K", "REF_B2000K", "REF_B5000K", "REF_B10000K")
PATTERNS = {
    "network_resolution_or_unreachable": r"Temporary failure in name resolution|Network is unreachable|Name or service not known",
    "recursive_fixture": r"recursive dependency involving fixture",
    "import_error": r"ModuleNotFoundError:|ImportError:",
}


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def load_ref(ref):
    actual = reference(ref["path"])
    if actual != ref:
        raise ValueError("Immutable scoring evidence changed: " + ref["path"])
    return json.loads(Path(ref["path"]).read_bytes())


def test_region(text):
    start, end = text.find(">>>>> Start Test Output"), text.rfind(">>>>> End Test Output")
    if start < 0 or end <= start:
        return text, False
    return text[start:end], True


def excerpt(text, pattern, before=160, after=900):
    match = re.search(pattern, text)
    if not match:
        return None
    return {"character_offset": match.start(), "text": text[max(0, match.start()-before):match.end()+after]}


def aggregate(rows):
    failed = [row for row in rows if row["resolved"] is False]
    return {
        "scored": len(rows), "resolved": sum(row["resolved"] for row in rows),
        "unresolved": len(failed),
        "unresolved_by_stop": dict(Counter(row["stop_class"] for row in failed)),
        "reported_endpoint_classes": dict(Counter(row["endpoint_class"] for row in rows)),
        "unresolved_empty_patch": sum(row["patch_empty"] for row in failed),
        "unresolved_no_existing_path_changed": sum(not row["existing_path_changed"] for row in failed),
        "unresolved_added_only_nonempty_patch": sum(not row["patch_empty"] and not row["existing_path_changed"] for row in failed),
        "unresolved_partial_f2p_success": sum(row["f2p_pass"] > 0 and row["f2p_nonpass"] > 0 for row in failed),
        "unresolved_any_p2p_nonpass": sum(row["p2p_nonpass"] > 0 for row in failed),
        "unresolved_network_log_symptom": sum(row["test_network_resolution_or_unreachable"] for row in failed),
        "unresolved_recursive_fixture_log_symptom": sum(row["test_recursive_fixture"] for row in failed),
        "unresolved_import_error_log_symptom": sum(row["test_import_error"] for row in failed),
    }


def analyze(input_root, output):
    state_path = input_root / "source-state.json"
    state = json.loads(state_path.read_bytes())
    with (input_root / "slot-results.csv").open() as stream:
        classes = {row["slot_id"]: row for row in csv.DictReader(stream)}
    rows, evidence, detailed, requests = [], [], [], []
    example_keys = set()
    for item in state["rows"]:
        if item["score"]["status"] != "official_report":
            continue
        slot = item["slot"]
        pointer = load_ref(item["score"]["receipt"])
        receipt = load_ref(pointer["receipt"])
        identity = load_ref(pointer["identity"])
        request = load_ref(item["score"]["dispatched_request"])
        candidate = load_ref(request["native_candidate_lock"])
        patch = candidate["patch_receipt"]
        report = receipt["official_result"][1][slot["instance_id"]]
        if (identity.get("slot_id") != slot["slot_id"] or identity.get("condition_id") != slot["condition_id"]
                or receipt["slot_id"] != slot["slot_id"] or receipt["condition_id"] != slot["condition_id"]
                or receipt["resolved"] != item["score"]["resolved"]
                or report.get("patch_successfully_applied") is not True
                or report.get("infra_failure") is not False):
            raise ValueError("Unexpected scoring identity or infrastructure status")
        tests = report.get("tests_status", {})
        f, p = tests.get("FAIL_TO_PASS", {}), tests.get("PASS_TO_PASS", {})
        missing_schema = not all(isinstance(group.get(key), list) for group in (f, p)
                                 for key in ("success", "failure"))
        f2p_bad, p2p_bad = len(f.get("failure", [])), len(p.get("failure", []))
        category = ("resolved" if receipt["resolved"] else "unclassified_missing_test_status" if missing_schema
                    else "reported_both_nonpass" if f2p_bad and p2p_bad
                    else "reported_F2P_nonpass_only" if f2p_bad
                    else "reported_P2P_nonpass_only" if p2p_bad else "unclassified_no_reported_nonpass")
        root = Path(pointer["receipt"]["path"]).parent
        log_paths = list(root.rglob("test_output.txt"))
        if len(log_paths) != 1:
            raise ValueError("Expected exactly one official test log")
        log = log_paths[0]
        text, bounded = test_region(log.read_text(errors="replace"))
        flags = {name: bool(re.search(pattern, text)) for name, pattern in PATTERNS.items()}
        existing = bool(patch.get("modified_paths") or patch.get("deleted_paths"))
        row = {"slot_id": slot["slot_id"], "instance_id": slot["instance_id"], "repo": slot["repo"],
            "condition_id": slot["condition_id"], "stop_class": classes[slot["slot_id"]]["stop_class"],
            "resolved": receipt["resolved"], "endpoint_class": category,
            "f2p_pass": len(f.get("success", [])), "f2p_nonpass": f2p_bad,
            "p2p_pass": len(p.get("success", [])), "p2p_nonpass": p2p_bad,
            "test_status_schema_missing": missing_schema, "test_output_markers_present": bounded,
            "patch_empty": patch["patch"]["bytes"] == 0, "existing_path_changed": existing,
            "added_path_count": len(patch.get("added_paths", [])),
            "modified_path_count": len(patch.get("modified_paths", [])),
            "deleted_path_count": len(patch.get("deleted_paths", [])),
            **{"test_"+name: value for name, value in flags.items()},
            "receipt_path": pointer["receipt"]["path"], "test_log_path": str(log)}
        rows.append(row)
        refs = {"slot_id": slot["slot_id"], "receipt": pointer["receipt"], "identity": pointer["identity"],
            "request": item["score"]["dispatched_request"], "candidate_lock": request["native_candidate_lock"],
            "patch": patch["patch"], "test_log": reference(log)}
        evidence.append(refs)
        key = (row["stop_class"], category)
        if not row["resolved"] and slot["condition_id"] in ARMS[2:] and key not in example_keys:
            example_keys.add(key)
            detailed.append({**row, "selection": "first panel-order failure for each high-budget stop/endpoint category",
                "official_F2P_nonpass_names": f.get("failure", []),
                "official_P2P_nonpass_names": p.get("failure", []),
                "failure_section_excerpt": excerpt(text, r"=+ FAILURES =+", after=1700),
                "first_error_line_excerpt": excerpt(text, r"(?m)^E +", after=650),
                "sources": refs})
        if slot["repo"] == "psf/requests":
            failures = f.get("failure", []) + p.get("failure", [])
            requests.append({**row, "official_F2P_nonpass_names": f.get("failure", []),
                "official_P2P_nonpass_names": p.get("failure", []),
                "official_nonpass_count": len(failures),
                "network_excerpt": excerpt(text, PATTERNS["network_resolution_or_unreachable"], after=1400),
                "fixture_excerpt": excerpt(text, PATTERNS["recursive_fixture"], after=600),
                "external_host_httpbin_org_seen": "httpbin.org" in text,
                "private_ip_10_255_255_1_seen": "10.255.255.1" in text,
                "sources": refs})
    assert len(rows) == 186 and sum(row["resolved"] for row in rows) == 72
    high = [row for row in rows if row["condition_id"] in ARMS[2:]]
    assert len(high) == 88 and sum(not row["resolved"] for row in high) == 49
    qualification = []
    for task in sorted({row["instance_id"] for row in requests}):
        path = ROOT / "runs/software-benchmark-v054/images/actor-admission-r3/instances" / (task + ".json")
        old = json.loads(path.read_bytes())
        qualification.append({"instance_id": task, "source": reference(path),
            "test_executions": old.get("test_executions"),
            "actor_tree_equals_official_tree": old.get("actor_tree_equals_official_tree"),
            "runtime_import_version_equal": old.get("runtime_version", {}).get("equal"),
            "meaning": "source/import identity admission; zero test executions is not a gold-test qualification"})
    result = {"version": "v056-official-failure-diagnostics-r1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "script": reference(__file__), "sources": {"state": reference(state_path),
            "classification": reference(input_root / "slot-results.csv")},
        "planned_tasks": 50, "planned_episodes": 200, "generation_technical_unknown_not_reclassified": 14,
        "all_scored": aggregate(rows), "high_budget_5M_and_10M": aggregate(high),
        "by_condition": {arm: aggregate([row for row in rows if row["condition_id"] == arm]) for arm in ARMS},
        "by_stop": {stop: aggregate([row for row in rows if row["stop_class"] == stop])
                    for stop in sorted({row["stop_class"] for row in rows})},
        "network_symptom_rows": [row["slot_id"] for row in rows if row["test_network_resolution_or_unreachable"]],
        "requests_environment_diagnostics": requests, "requests_source_admission": qualification,
        "representative_failures": detailed, "per_slot_sources": evidence,
        "limitations": [
            "F2P/P2P failure entries mean not passed in the official report, not proven causal repair error or regression.",
            "Network/import/fixture text is a symptom scan inside test markers, not an automatic environmental-failure classifier.",
            "All four requests tasks fail all four budgets with network symptoms; no source-only admission proves tests usable.",
            "No baseline/gold CPU counterfactual was run here, so environmental contribution and potential corrected scores remain unknown.",
            "No existing path changes includes empty patches and additions-only candidates, not a proof all additions are useless.",
            "Official scores and the 50-task denominator are preserved. Diagnostic selection by failure is not a new evaluation panel."],
        "model_calls": 0, "scoring_calls": 0, "official_scores_changed": False}
    output.mkdir(parents=True, exist_ok=True)
    (output / "official-failures.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    with (output / "official-failures-per-slot.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"all": result["all_scored"], "high": result["high_budget_5M_and_10M"],
                      "requests_tasks": len(qualification)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    analyze(args.input, args.output)


if __name__ == "__main__":
    main()
