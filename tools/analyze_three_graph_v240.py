"""Audit counts by state, including sensitivity to earlier dependency annotations."""

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_three_graph_v240 import PLAN, RUN, first, read_json, policy


def main():
    results = read_json(PLAN / "results.json")
    refs = read_json(PLAN / "references.json")
    out = {}
    for arm in ("P0", "P1"):
        records = [r for r in results["records"] if r["arm"] == arm]
        main_rows = [r for r in records if r["id"] != "gap"]
        counts = Counter()
        changed = []
        for r in records:
            if r["status"] != "settled":
                continue
            (f,) = (RUN / f"{r['id']}_{arm}_{r['repeat']}-structured" / "api").glob("*/usage.json")
            u = read_json(f)
            counts.update(
                {
                    k: u[k]
                    for k in (
                        "input_tokens",
                        "output_tokens",
                        "cache_hit_tokens",
                        "cache_miss_tokens",
                        "peak_cost_nanoyuan",
                    )
                }
            )
            if r.get("change") and r["id"] != "gap":
                ref = refs[r["id"]]
                links = [l["obligation"].rsplit("/", 1)[-1] for l in r.get("patch_links", [])]
                changed.append(
                    dict(
                        id=r["id"],
                        repeat=r["repeat"],
                        option=r["option"],
                        choice_ok=r.get("choice_ok"),
                        linked_labels=links,
                        links_supported=all(any(k in a for a in ref["obligations"]) for k in links)
                        if links
                        else None,
                    )
                )
        due = [r for r in main_rows if r["due"]]
        out[arm] = dict(
            usage=dict(counts),
            changes=changed,
            states_with_consensus=len({r["id"] for r in due}),
            both_exact_states=sum(
                all(x.get("effective_ok") for x in main_rows if x["id"] == sid)
                for sid in {r["id"] for r in main_rows}
            ),
            stable_changes=sum(
                bool(r.get("change")) for r in main_rows if r["category"] == "STABLE"
            ),
            historical_order_correct=sum(
                r.get("binding", {}).get("action")
                in refs[r["id"]].get("historical_actions", refs[r["id"]]["actions"])
                for r in main_rows
            ),
            probe=[
                {k: r.get(k) for k in ("repeat", "status", "valid", "choice", "binding")}
                for r in records
                if r["id"] == "gap"
            ],
        )
    first.save(PLAN / "diagnostics.json", out)


if __name__ == "__main__":
    main()
