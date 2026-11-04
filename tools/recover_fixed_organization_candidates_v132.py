"""Offline only: recover explicitly selected v131 closed-controller host exports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim import software_benchmark_candidate_recovery_v132 as recovery
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--slot-index", type=int, action="append")
    selection.add_argument("--all-existing", action="store_true")
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument("--output-root", type=Path, default=recovery.DEFAULT_OUTPUT)
    parser.add_argument("--index-file", type=Path)
    args = parser.parse_args()
    plan_ref = reference(recovery.ORIGINAL_PLAN)
    plan = recovery.load(plan_ref)
    selected = set(args.slot_index or [])
    if selected - {row["slot_index"] for row in plan["rows"]}:
        parser.error("Every requested slot must belong to the frozen v131 plan")
    rows = []
    for row in plan["rows"]:
        path = recovery.ORIGINAL_BATCH / "episodes" / str(row["slot_index"]) / "result.json"
        if row["slot_index"] not in selected and not args.all_existing:
            continue
        if args.all_existing and not path.exists():
            continue
        item = {"slot_id": row["slot_id"], "slot_index": row["slot_index"],
                "group_id": row["group_id"], "instance_id": row["instance_id"]}
        try:
            original = reference(path)
            item["original_result"] = original
            if args.inspect_only:
                item.update(status="recoverable", proof=recovery.inspect_recoverable(
                    row, original, original_plan_ref=plan_ref))
            else:
                output = args.output_root / str(row["slot_index"])
                result_path = output / "result.json"
                if result_path.exists():
                    ref = reference(result_path)
                    recovery.validate_recovered_result(ref, original_plan_ref=plan_ref)
                else:
                    ref = recovery.recover_closed_candidate(row, original, output, original_plan_ref=plan_ref)
                item.update(status="recovered_closed_pending_scoring", result=ref)
        except (ValueError, FileNotFoundError, KeyError, TypeError, UnicodeError) as error:
            item.update(status="not_recoverable", error={"type": type(error).__name__, "message": str(error)})
        rows.append(item)
    result = {"version": recovery.VERSION, "original_plan": plan_ref, "rows": rows,
              "inspect_only": args.inspect_only, "new_model_calls": 0, "new_scoring_calls": 0,
              "Docker_operations": 0, "original_records_overwritten": False}
    if args.index_file:
        args.index_file.parent.mkdir(parents=True, exist_ok=True)
        print(json.dumps(write_new(args.index_file, result)))
    else:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
