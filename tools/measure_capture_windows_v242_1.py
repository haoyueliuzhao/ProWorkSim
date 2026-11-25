"""Replay all archived successor arms in a defined historical panel. No official scores are read."""

from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory_multitype_v242 import ROOT, history, save, read_json
from proworksim.software_passive_capture_v242_1 import PassiveCapture
from proworksim.software_graph_execution_v230 import CALL_BOUND

PLAN = ROOT / "artifacts/software-benchmark-v242-1/precursors-r1"
FOLDERS = [
    "v216/target-repair6-r1",
    "v216/targeted-closure4-r1",
    "v217/selection28-r1",
    "v217/confirmation-resume-r1",
    "v217/streaming-r2",
]


@lru_cache(maxsize=4)
def initial(path):
    state = dict(read_json(path / "checkpoint/state.json")["__dict__"])
    ordinal = dict(state["runtime"]["__dict__"])["opportunities"]
    return ordinal, [h for h in history(path) if h["ordinal"] <= ordinal]


def budgets(folder, commands):
    ops = {}
    after = {}
    with (folder / "runtime/experience.jsonl").open("rb") as f:
        for line in f:
            if b"tool_call" not in line and b"organization_work_opportunity_v049" not in line:
                continue
            event = json.loads(line)
            data = event.get("payload") or {}
            op = data.get("opportunity_id")
            if not op:
                continue
            if event["kind"] == "tool_call":
                cmd = (data.get("response") or {}).get("command_id")
                if cmd in commands:
                    ops[cmd] = op
            elif (
                event["kind"] == "organization_work_opportunity_v049"
                and data.get("phase") == "after"
            ):
                after[op] = (data.get("team_budget") or {}).get("available_tokens")
    return {k: after.get(v) for k, v in ops.items()}


def main():
    all_rows = []
    hits = defaultdict(set)
    eligible = defaultdict(set)
    for entry in FOLDERS:
        base = ROOT / "runs" / ("software-benchmark-" + entry)
        for b in sorted(base.glob("*/*/boundary.json")):
            if b.parent.name == "PREFIX":
                continue
            result = read_json(b.parent / "result.json")
            row = dict(
                source=str(b.parent.relative_to(ROOT)),
                instance=result.get("instance_id"),
                arm=b.parent.name,
            )
            all_rows.append(row)
            cp = result.get("checkpoint_parent")
            if not cp or not (Path(cp) / "state.json").is_file():
                row.update(status="missing_parent")
                continue
            start, pre = initial(Path(cp).parent)
            rec = PassiveCapture(b.parent / "unused", history=pre)
            first = {}
            for i, o in enumerate(read_json(b)["outcomes"], 1):
                for n in rec.observe(start + i, o):
                    k = n["anomaly_type"]
                    if k in first:
                        continue
                    first[k] = dict(
                        kind=k,
                        since_anchor=i,
                        member=o["worker_id"],
                        subject=n["subject"],
                        scope=n["affected_work"],
                        command=o["response"]["command_id"],
                    )
            cash = budgets(b.parent, {v["command"] for v in first.values()}) if first else {}
            for k, x in first.items():
                x["remaining_tokens"] = cash.get(x["command"])
                hits[k].add(row["instance"])
                if (x["remaining_tokens"] or 0) >= 8 * CALL_BOUND:
                    eligible[k].add(row["instance"])
            row.update(status="inspected", first_signals=list(first.values()))
    save(
        PLAN / "historical-windows.json",
        dict(
            selection=FOLDERS,
            rows=all_rows,
            distinct_tasks_by_signal={k: sorted(v) for k, v in hits.items()},
            distinct_tasks_with_headroom={k: sorted(v) for k, v in eligible.items()},
            minimum_remaining=8 * CALL_BOUND,
            scope="First receipt per type and branch. Separate branches of one task count once per type. Budget from the same historical tool call's settled opportunity. No claim of a restorable checkpoint or contemporary validation of executable graph options.",
            provider_calls=0,
        ),
    )
    print(
        len(all_rows),
        len({x["instance"] for x in all_rows}),
        {k: len(v) for k, v in hits.items()},
        {k: len(v) for k, v in eligible.items()},
    )


if __name__ == "__main__":
    main()
