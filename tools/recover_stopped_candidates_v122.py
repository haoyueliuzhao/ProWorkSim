"""Audit and export the nine stopped PROJECT candidates, without model or scoring."""

from __future__ import annotations

import argparse
import json

from proworksim import software_benchmark_stopped_recovery_v122 as recovery
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def run(indices):
    recovery.AUDIT.mkdir(parents=True, exist_ok=True)
    plan = recovery.load(reference(recovery.BATCH / "execution-plan.json"))
    rows = [row for row in plan["rows"] if row["slot_index"] in indices]
    if {row["slot_index"] for row in rows} != set(indices):
        raise ValueError("Choose only declared original stopped tasks")
    usage = recovery.provider_usage(rows)
    outcomes = []
    for row in rows:
        index = row["slot_index"]
        try:
            result = recovery.recover(index, usage[index])
            value = recovery.load(result)
            source = recovery.load(value["source"])
            outcomes.append(
                {
                    "slot_index": index,
                    "instance_id": row["instance_id"],
                    "status": value["status"],
                    "result": result,
                    "source_reference": source["binding"]["source_reference"],
                    "committed_state_revision": source["binding"]["state_revision"],
                    "legal_delivery_records": source["binding"]["legal_delivery_records"],
                    "provider_usage": usage[index],
                    "saved_session": source["saved_session"],
                }
            )
        except Exception as error:
            outcomes.append(
                {
                    "slot_index": index,
                    "instance_id": row["instance_id"],
                    "status": "recovery_unknown",
                    "error": {"type": type(error).__name__, "message": str(error)},
                    "original_result_changed": False,
                }
            )
        print(json.dumps(outcomes[-1], ensure_ascii=False), flush=True)
    return write_new(
        recovery.AUDIT / "summary.json",
        {
            "version": recovery.VERSION,
            "selection_before_any_scoring": "All nine original budget-cancelled tasks; sole committed managed current version",
            "outcomes": outcomes,
            "supplemental_candidates": sum(
                item["status"] == "supplemental_candidate_locked" for item in outcomes
            ),
            "original_unknowns_preserved": len(rows),
            "normal_SDK_closure_reconstructed": False,
            "model_calls": 0,
            "scoring_calls": 0,
            "Docker_operations": 0,
            "API_calls": 0,
            "real_tests": 0,
            "new_delivery_evidence_created": False,
            "source_module": reference(recovery.__file__),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-index", type=int, choices=sorted(recovery.TASKS), action="append")
    args = parser.parse_args()
    print(json.dumps(run(args.slot_index or sorted(recovery.TASKS)), ensure_ascii=False))
