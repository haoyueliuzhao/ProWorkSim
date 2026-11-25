"""Explain the delivery endpoint of all code-correct branches using the locked final world."""

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_midtask_panel_v244 import ReadOnlyStore, ReviewWorld, BundleCache
from run_midtask_panel_v244 import ARMS, PLAN, PROJECT, RUN, read_json, save


def inspect(row, index, arm):
    base = RUN / str(index) / arm
    world = ReviewWorld.__new__(ReviewWorld)
    world.store = ReadOnlyStore(base / "prepared/world")
    world.state = world.store.load()
    world.bundle_cache = BundleCache()
    final = world._action_delivery_readiness("member_001", PROJECT)
    lock = read_json(base / "closure/terminal-code/lock.json")
    for key, val in final["final_identity"].items():
        assert lock[key] == val
    start = read_json(base / "decision-input.json")["view"]
    initial = {p["task_id"]: p["reviewer"] for p in start["package_chain"]["packages"]}
    packages = {
        p["task_id"]: dict(
            owner=p["owner"],
            initial_reviewer=initial[p["task_id"]],
            reviewer=p["reviewer"],
            missing=p["missing"],
            completion=(p.get("completion") or {}).get("patch_id")
            or (p.get("completion") or {}).get("evidence_id"),
        )
        for p in final["package_chain"]["packages"]
    }
    assignments, submissions = [], []
    for i, o in enumerate(read_json(base / "boundary.json")["outcomes"], 1):
        action = o.get("decision") or {}
        tool = action.get("action")
        if tool not in ("assign_verification", "submit_integration"):
            continue
        response = o["response"]
        rejection = (response.get("error") or {}).get("rejection") or {}
        receipt = dict(
            branch_step=i,
            actor=o["worker_id"],
            accepted=response["ok"],
            code=rejection.get("code"),
            command=response.get("command_id"),
        )
        if tool == "assign_verification":
            assignments.append(dict(receipt, task=action["arguments"].get("task_id")))
        else:
            check = (rejection.get("context") or {}).get("checklist") or {}
            submissions.append(
                dict(
                    receipt,
                    missing={
                        p["task_id"]: p["missing"]
                        for p in check.get("packages", [])
                        if p["missing"]
                    },
                )
            )
    return dict(
        instance=row["instance"],
        arm=arm,
        delivery=row[arm]["scores"]["delivery"]["resolved"],
        ending=row[arm]["ending"],
        tree=lock["tree_sha256"],
        packages=packages,
        final_gaps=[g["kind"] for g in final["gaps"] if "kind" in g],
        current_fixed=final["current_fixed_patch_ids"],
        current_test=final["final_test"],
        ready=final["ready_to_submit"],
        assignments=assignments,
        submissions=submissions,
    )


def main():
    ids = {x["instance"]: x["index"] for x in read_json(PLAN / "roster.json")["roster"]}
    rows = []
    for r in read_json(PLAN / "results.json")["rows"]:
        for arm in ARMS:
            if r[arm]["scores"]["code"]["resolved"] is True:
                rows.append(inspect(r, ids[r["instance"]], arm))
    counts = {a: Counter() for a in ARMS}
    for r in rows:
        if r["delivery"]:
            continue
        c = counts[r["arm"]]
        c["not_delivered"] += 1
        c["attempted_submit"] += bool(r["submissions"])
        c["submit_rejections"] += sum(s["accepted"] is False for s in r["submissions"])
        missing = {k for k, v in r["packages"].items() if "assign_verification" in v["missing"]}
        same = [
            s for s in r["assignments"] if s["task"] in missing and s["code"] == "graph_authority"
        ]
        c["missing_reviewer"] += bool(missing)
        c["missing_from_fork"] += any(r["packages"][k]["initial_reviewer"] is None for k in missing)
        c["attempted_assign_missing_reviewer"] += bool(same)
        c["blocked_assignment_calls"] += len(same)
        c["partner_patch_integration"] += any(
            "integrate_partner_patch" in v["missing"] for v in r["packages"].values()
        )
        c["final_test_and_fix_present"] += bool(
            r["current_fixed"] and (r["current_test"] or {}).get("passed")
        )
        c["ready"] += r["ready"]
    save(
        PLAN / "delivery-gaps.json",
        dict(
            counts={k: dict(v) for k, v in counts.items()},
            rows=rows,
            unit="One code-correct branch. Terminal checklist recomputed read-only from the locked code version. Calls count only the continuation.",
        ),
    )
    print(counts)


if __name__ == "__main__":
    main()
