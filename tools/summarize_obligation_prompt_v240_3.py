"""Report paired site behavior and actual provider usage, keeping diagnostic strata separate."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_obligation_prompt_v240_3 import PLAN, previous, read_json


def main():
    records = read_json(PLAN / "results.json")["records"]
    rows = []
    for site in sorted({r["site"] for r in records}):
        pair = {"site": site}
        for arm in ("BASE", "TEXT"):
            runs = [r for r in records if r["site"] == site and r["arm"] == arm]
            pair.update(group=runs[0]["group"], category=runs[0]["category"])
            pair[arm] = dict(
                raw_exact=sum(bool(x.get("raw_ok")) for x in runs),
                final_exact=sum(bool(x.get("effective_ok")) for x in runs),
                first_correct=sum(bool(x.get("first_ok")) for x in runs),
                raw_overinclusive=sum(bool(x.get("raw_extra")) for x in runs),
                raw_sets=[x.get("raw") for x in runs],
            )
        rows.append(pair)
    usage = {}
    for arm in ("BASE", "TEXT"):
        runs = [r for r in records if r["arm"] == arm and r["status"] == "settled"]
        usage[arm] = dict(
            settled=len(runs),
            **{
                k: sum(r[k] for r in runs)
                for k in ("input", "output", "cache_hit", "cost_nanoyuan")
            },
        )
    previous.first.save(PLAN / "paired-diagnostics.json", dict(states=rows, usage=usage))


if __name__ == "__main__":
    main()
