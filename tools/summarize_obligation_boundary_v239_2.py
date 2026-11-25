"""Account for exposure, paired errors, token cache hits and optional controller choices."""

from pathlib import Path
import sys
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_obligation_boundary_v239_2 import PLAN, RUN, previous, policy, read_json, first


def main():
    res = read_json(PLAN / "results.json")
    rows = {
        s["id"]: s
        for s in read_json(previous.PLAN / "panel.json")
        + read_json(PLAN / "additional-states.json")
    }
    refs = {
        s["id"]: s for p in (previous.PLAN, PLAN) for s in read_json(p / "agreed-reference.json")
    }
    summary = {}
    for scope, prefix in (("dev", "q"), ("additional", "x")):
        arms = {}
        for arm in ("P0", "P1"):
            calls = [r for r in res["records"] if r["arm"] == arm and r["id"].startswith(prefix)]
            arms[arm] = dict(
                decisions=dict(Counter(r.get("choice", "invalid") for r in calls)),
                both_correct_sites=sum(
                    all(r.get("obligation_ok") for r in calls if r["id"] == sid)
                    for sid in refs
                    if sid.startswith(prefix)
                ),
                invalid_reasons=dict(
                    Counter(r.get("error", "unknown") for r in calls if not r.get("valid"))
                ),
            )
        cross = []
        for sid in refs:
            if not sid.startswith(prefix):
                continue
            row = rows[sid]
            tasks = policy.snapshot(row)
            routes = policy.routes(row, tasks)
            available = {(v["action"], v["actor"], v["package"]) for v in routes.values()}
            wanted = {(v["action"], v["actor"], v["package"]) for v in refs[sid]["action_bindings"]}
            v = next(v for v in res["mechanics"] if v["id"] == sid)
            cross.append(
                dict(
                    id=sid,
                    action_count=len(v["distinct_immediate_actions"]),
                    routes=len(routes),
                    binding_available=bool(available & wanted),
                    program_match=v["program_match"],
                )
            )
        summary[scope] = dict(arms=arms, sites=cross)
    accounting = {}
    for arm in ("P0", "P1"):
        totals = Counter()
        for r in res["records"]:
            if r["arm"] != arm or r.get("status") != "settled":
                continue
            folder = RUN / (r["id"] + "_" + arm + "_" + str(r["repeat"]) + "-structured") / "api"
            (f,) = folder.glob("*/usage.json")
            u = read_json(f)
            totals.update(
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
        accounting[arm] = dict(totals)
    first.save(PLAN / "diagnostics.json", dict(strata=summary, usage=accounting))


if __name__ == "__main__":
    main()
