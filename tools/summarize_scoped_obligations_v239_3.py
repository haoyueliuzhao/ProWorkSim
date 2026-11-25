"""Separate the model's choice, receipt-backed additions and actual cost."""

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_scoped_obligations_v239_3 import PLAN, RUN, GROUPS, old, repaired, prior, first, read_json


def main():
    result = read_json(PLAN / "results.json")
    refs = {x["id"]: x for _, p, _ in GROUPS for x in read_json(p / "agreed-reference.json")}
    strata = {}
    for name, folder, file in GROUPS:
        sources = [s for s in read_json(folder / file) if s["id"] != "gap"]
        coverage = []
        for s in sources:
            expected = {
                (a["actor"], a["action"], a["package"]) for a in refs[s["id"]]["action_bindings"]
            }
            targets = {}
            for key, model in (("BASE", old), ("FIX", repaired)):
                tasks = model.snapshot(s)
                routes = old.routes(s, tasks)
                bindings = {(a["actor"], a["action"], a["package"]) for a in routes.values()}
                targets[key] = {
                    "distinct_actions": len({v["immediate"] for v in routes.values()}),
                    "has_reviewed_binding": bool(bindings & expected),
                }
            coverage.append({"id": s["id"], **targets})
        arms = {}
        for arm in ("BASE", "FIX"):
            group = [r for r in result["records"] if r["group"] == name and r["arm"] == arm]
            cats = {}
            for cat in sorted({r["category"] for r in group}):
                items = [r for r in group if r["category"] == cat]
                cats[cat] = {
                    "n": len(items),
                    **{
                        k: sum(bool(i.get(k)) for i in items)
                        for k in ("raw_ok", "effective_ok", "order_ok", "binding_ok", "valid")
                    },
                }
            arms[arm] = dict(
                by_category=cats,
                decisions=dict(Counter(r.get("choice", "unresolved") for r in group)),
                added_net_wins=sum(
                    bool(r.get("effective_ok")) and not r.get("raw_ok") for r in group
                ),
                added_net_losses=sum(
                    bool(r.get("raw_ok")) and not r.get("effective_ok") for r in group
                ),
            )
        strata[name] = dict(coverage=coverage, arms=arms)
    usage = {}
    for arm in ("BASE", "FIX"):
        total = Counter()
        for r in result["records"]:
            if r["arm"] != arm or r["status"] != "settled":
                continue
            (f,) = (RUN / f"{r['id']}_{arm}_{r['repeat']}-structured" / "api").glob("*/usage.json")
            u = read_json(f)
            total.update(
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
        usage[arm] = dict(total)
    first.save(
        PLAN / "diagnostics.json",
        dict(
            strata=strata,
            usage=usage,
            worker_readiness=read_json(prior.previous.PLAN / "diagnostics.json")["worker_roster"],
        ),
    )


if __name__ == "__main__":
    main()
