"""Read-only reconciliation of nine primary conditions and finite recovery records."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools"), str(ROOT)]
from observe_nine_conditions_hourly_v055_r1 import (  # noqa: E402
    ledger_snapshot, score_endpoints, summarize_queue,
)
from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402


def summarize(output):
    evidence = {}

    def read(name, relative):
        path = ROOT / relative
        evidence[name] = reference(path)
        return json.loads(path.read_bytes())

    primary = {
        "qwen": read("qwen_primary", "runs/software-benchmark-v054/formal-queue-r1/state.json"),
        "deepseek": read("deepseek_primary", "runs/software-benchmark-v055/queue-r1/state.json"),
    }
    qwen = read("qwen_r6", "runs/software-benchmark-v055/exception-reconciliation-r1/qwen-four-endpoint-r6/summary.json")
    deep = read("deepseek_r6", "runs/software-benchmark-v055/exception-reconciliation-r1/deepseek-scoring-r1/summary.json")
    preentry = read("preentry", "runs/software-benchmark-v055/pre-entry-recovery-r1/first-scoring/summary.json")
    if len(qwen["results"]) != 4 or len(deep["results"]) != 47 or preentry["generation_terminal"] != 6:
        raise ValueError("All fixed finite recovery inventories must have finished")
    derived = deepcopy(primary)
    rows = {row["slot"]["slot_id"]: row for state in derived.values() for row in state["rows"]}
    if len(rows) != 4500:
        raise ValueError("The original nine conditions require 4500 unique slots")
    for row in rows.values():
        row["scores"] = score_endpoints(row)
    corrections, consumed = [], set()

    def record_score(item, origin, first=False):
        sid, endpoint = item["slot_id"], item["endpoint"]
        key = sid, endpoint
        if key in consumed:
            raise ValueError("A recovery endpoint would be counted twice")
        consumed.add(key)
        row = rows[sid]
        old = row["scores"].get(endpoint)
        if (first and old is not None) or (not first and (old or {}).get("status") != "technical_unknown"):
            raise ValueError("Recovery must bind an originally missing or unknown endpoint")
        official = item.get("official") or {}
        resolved = item.get("resolved", official.get("resolved"))
        if type(resolved) is not bool:
            raise ValueError("A determinate official boolean is required")
        row["scores"][endpoint] = {**(old or {}), "status": "official_report", "resolved": resolved}
        corrections.append({"slot_id": sid, "endpoint": endpoint, "resolved": resolved,
                            "recovery_source": origin, "first_score_after_zero_model_recovery": first})

    for item in qwen["results"]:
        if item["status"] == "official_report":
            record_score(item, "qwen_r6")
    for item in deep["results"]:
        if item["status"] in {"recovered_existing_official_report", "recovered_additional_official_report"}:
            record_score(item, "deepseek_r6")
    for item in preentry["generation_rows"]:
        row = rows[item["slot_id"]]
        if row["generation"]["status"] != "technical_unknown" or item["status"] not in {"closed", "technical_unknown"}:
            raise ValueError("Unexpected zero-model recovery transition")
        row["generation"]["status"] = item["status"]
    for item in preentry["score_rows"]:
        if item["status"] == "official_report":
            record_score(item, "preentry", first=True)
        elif item["status"] not in {"technical_unknown"}:
            raise ValueError("First scoring is not terminal")
    groups = {}
    for family, state in derived.items():
        primary_groups = summarize_queue(primary[family], {}, family)["groups"]
        for condition, group in summarize_queue(state, {}, family)["groups"].items():
            if group["planned"] != 500:
                raise ValueError("The planned denominator must remain 500 per condition")
            unknown = 500 - group["code_score"]["official_report"]
            groups[family + ":" + condition] = {
                "original_primary": primary_groups[condition], "derived_reconciled": group,
                "code_outcome_unknown_including_missing_candidate": unknown,
                "code_success_lower_bound": group["observed_resolved_code"] / 500,
                "code_success_upper_bound": (group["observed_resolved_code"] + unknown) / 500,
                "bounds_are_missing_outcome_bounds_not_confidence_intervals": True,
            }
    now = datetime.now(timezone.utc)
    result = {"version": "v055-nine-condition-exception-reconciliation-summary-r1",
        "observed_utc": now.isoformat(), "evidence": evidence, "groups": groups,
        "score_outcomes_added": len(corrections), "score_corrections": corrections,
        "original_unknown_endpoints_recovered": sum(not x["first_score_after_zero_model_recovery"] for x in corrections),
        "new_first_scores_after_proven_zero_model_recovery": sum(x["first_score_after_zero_model_recovery"] for x in corrections),
        "generation_closed": sum(g["derived_reconciled"]["generation"]["closed"] for g in groups.values()),
        "generation_technical_unknown": sum(g["derived_reconciled"]["generation"]["technical_unknown"] for g in groups.values()),
        "code_official_reports": sum(g["derived_reconciled"]["code_score"]["official_report"] for g in groups.values()),
        "code_scoring_technical_unknown": sum(g["derived_reconciled"]["code_score"]["technical_unknown"] for g in groups.values()),
        "delivery_scoring_technical_unknown": sum(g["derived_reconciled"]["delivery_score"]["technical_unknown"] for g in groups.values()),
        "ledger": ledger_snapshot(now), "primary_records_modified": False,
        "entered_model_episodes_replayed": 0, "same_candidates_rescored_under_separately_reported_revision": True}
    return write_new(Path(output), result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.output)))


if __name__ == "__main__":
    main()
