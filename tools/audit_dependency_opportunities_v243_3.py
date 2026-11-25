"""Count structural opportunities for A2 within the already frozen historical window panel."""

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_ordinary_batch_v243_3 import PLAN, ROOT, ordinary, read_json, reference
from proworksim.software_event_harness_v243 import work_budget


def edges(work):
    return {(child, parent) for child, w in work.items() for parent in w.get("depends_on", [])}


def main():
    historical = ROOT / "artifacts/software-benchmark-v242-1/precursors-r1/historical-windows.json"
    inventory = read_json(
        ROOT / "artifacts/software-benchmark-v242/multitype-r1/checkpoint-inventory.json"
    )["records"]
    results = []
    for row in read_json(historical)["rows"]:
        folder = ROOT / row["source"]
        job = read_json(folder / "result.json")
        parent = Path(job["checkpoint_parent"]).parent
        start_file = parent / "dynamic-final.json"
        final_file = folder / "dynamic-final.json"
        snapshots = [read_json(start_file)["work"], read_json(final_file)["work"]]
        seen = set()
        explicit_add = []
        active_checks = Counter()
        for i, o in enumerate(read_json(folder / "boundary.json")["outcomes"], 1):
            d = o.get("decision") or {}
            args = d.get("arguments") or {}
            r = o.get("response") or {}
            v = r.get("result") or {}
            tool = d.get("action")
            if r.get("ok") and tool == "dynamic_status" and isinstance(v.get("work"), dict):
                snapshots.append(v["work"])
            if r.get("ok") and (
                tool == "declare_dependency"
                or tool == "change_dependency"
                and args.get("operation") == "add"
            ):
                child, up = args["task_id"], args["depends_on"]
                if up in v.get("depends_on", []):
                    seen.add((child, up))
                    explicit_add.append(
                        dict(step=i, task=child, upstream=up, command=r["command_id"])
                    )
            if tool == "work_readiness" and r.get("ok"):
                active_checks["check"] += 1
            if tool == "begin_work":
                active_checks["begin_attempt"] += 1
        cross = set()
        for g in snapshots:
            for child, up in edges(g):
                seen.add((child, up))
                if (
                    up in g
                    and all(g[t].get("owner") for t in (child, up))
                    and g[child]["owner"] != g[up]["owner"]
                ):
                    cross.add((child, up))
        hits = [s for s in row["first_signals"] if s["kind"] == "A2"]
        if hits:
            assert all((s["scope"][0], s["subject"]) in seen for s in hits)
        original = read_json(parent / "checkpoint/manifest.json")
        same = [
            r
            for r in inventory
            if r["instance"] == row["instance"]
            for v in r["views"]
            if v["kind"] == "A2" and v["exact"]
        ]
        results.append(
            dict(
                instance=row["instance"],
                arm=row["arm"],
                source=row["source"],
                initial_graph=reference(start_file),
                final_graph=reference(final_file),
                edges=sorted(seen),
                observed_cross_owner_edges=sorted(cross),
                confirmed_adds=explicit_add,
                checks=dict(active_checks),
                a2_receipts=hits,
                parent=original["identity"],
                any_prior_exact_a2_for_task=bool(same) if hits else None,
            )
        )
    masks = {
        "panel": lambda r: True,
        "explicit_edge": lambda r: r["edges"],
        "cross_owner_at_snapshot": lambda r: r["observed_cross_owner_edges"],
        "a2_receipt": lambda r: r["a2_receipts"],
        "a2_above_token_component": lambda r: any(
            s["remaining_tokens"] is not None
            and s["remaining_tokens"] >= work_budget("A2", 0, 0, 0)["required"]
            for s in r["a2_receipts"]
        ),
        "tasks_with_prior_exact_a2": lambda r: r["any_prior_exact_a2_for_task"] is True,
    }
    stats = {}
    for k, test in masks.items():
        group = [r for r in results if test(r)]
        stats[k] = dict(branches=len(group), tasks=len({r["instance"] for r in group}))
    pool_file = ordinary.PLAN / "protocol.json"
    pool = []
    for case in read_json(pool_file)["pool"]:
        path = ROOT / case["source"] / "dynamic-final.json"
        work = read_json(path)["work"]
        pool.append(
            dict(
                instance=case["instance"],
                checkpoint=case["checkpoint"],
                graph=reference(path),
                owners={k: w.get("owner") for k, w in work.items()},
                edges=sorted(edges(work)),
            )
        )
    ordinary.save(
        PLAN / "a2-opportunity-audit.json",
        dict(
            source=reference(historical),
            groups=stats,
            ordinary_pool_source=reference(pool_file),
            ordinary_pool=pool,
            rows=results,
            policy="All 51 previously registered branches. Count explicit edges in observed work graphs at entry, exit, intermediate status, or a native accepted add. Cross-owner count is limited to snapshots with both owners. A2 signal is the original actor-scoped readiness receipt. Historical token component alone does not qualify a pair.",
            provider_calls=0,
        ),
    )
    print(stats)


if __name__ == "__main__":
    main()
