"""Post hoc, zero-provider-call projection check, separate from all prospective scores."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_three_graph_v240 import PLAN, first, read_json, policy, sources
from proworksim import software_obligation_projection_v240 as projection
from proworksim.software_benchmark_candidates_v054 import checked


def main():
    rows = {s["id"]: s for s in sources()}
    refs = read_json(PLAN / "references.json")
    records = []
    for r in read_json(PLAN / "results.json")["records"]:
        if r["arm"] != "P1":
            continue
        sid = r["id"]
        ref = refs[sid]
        if not r.get("valid"):
            records.append(dict(site=sid, repeat=r["repeat"], ok=False, retained=0))
            continue
        row = {**rows[sid], "probe_id": ref["probe_id"]}
        d = policy.parse(row, read_json(checked(r["response"])))
        original = policy.compile_decision(row, d)
        revised = projection.compile_decision(row, d)
        assert (
            original["execution"] == revised["execution"] and original["patch"] == revised["patch"]
        )
        assert set(original["effective"]) == set(revised["effective"]) | set(
            revised["conditional_or_unknown"]
        )
        _, nodes, _ = policy.build(row)
        labels = {nodes[k]["label"] for k in revised["effective"]}
        retain = set(ref["consensus_due"]) & labels
        records.append(
            dict(
                site=sid,
                repeat=r["repeat"],
                raw=r["raw"],
                old=r["effective"],
                current=sorted(labels),
                deferred=revised["conditional_or_unknown"],
                ok=any(labels == set(v) for v in ref["obligations"]),
                retained=len(retain),
            )
        )
    main_rows = [r for r in records if r["site"] != "gap"]
    first.save(
        PLAN / "projection-replay.json",
        dict(
            records=records,
            correct=sum(r["ok"] for r in main_rows),
            retained=sum(r["retained"] for r in main_rows),
            denominator=sum(len(refs[r["site"]]["consensus_due"]) for r in main_rows),
            n=len(main_rows),
            provider_calls=0,
            affects_gate=False,
        ),
    )


if __name__ == "__main__":
    main()
