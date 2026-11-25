"""Reconstruct dependency resolution on the entire previously registered A2 archive."""

from pathlib import Path
from copy import deepcopy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_ordinary_successor_v243_2 import PLAN, ROOT, read_json, save
from proworksim.software_dependency_chain_v243_2 import dependency_chain
from proworksim.software_benchmark_candidates_v054 import reference


def main():
    roster = ROOT / "artifacts/software-benchmark-v243/event-pairs-r1/priority-a2.json"
    source = ROOT / "artifacts/software-benchmark-v242-1/precursors-r1/historical-windows.json"
    table = read_json(source)["rows"]
    rows = []
    for expected in read_json(roster)["cases"]:
        (entry,) = [
            t
            for t in table
            if t["instance"] == expected["instance"]
            and t["arm"] == expected["arm"]
            and any(n["command"] == expected["command"] for n in t["first_signals"])
        ]
        file = ROOT / entry["source"] / "boundary.json"
        ops = read_json(file)["outcomes"]
        ((index, o),) = [
            (i, o)
            for i, o in enumerate(ops, 1)
            if (o.get("response") or {}).get("command_id") == expected["command"]
        ]
        result = (
            o["response"].get("result")
            or o["response"]["error"]["rejection"]["context"]["readiness"]
        )
        down = result["task_id"]
        up = expected["subject"]
        consumer = o["worker_id"]
        (producer,) = {"member_001", "member_002"} - {consumer}
        # Check the producer attribution against actual receipts for this package.
        assert any(
            q.get("worker_id") == producer
            and (q.get("decision") or {}).get("action") == "complete_work"
            and q["decision"]["arguments"].get("task_id") == up
            and (q.get("response") or {}).get("ok")
            for q in ops
        )
        c = dependency_chain(
            ops,
            boundary=index,
            start=1,
            upstream=up,
            downstream=down,
            producer=producer,
            consumer=consumer,
        )
        assert any(x["ordinal"] == index and x["kind"] == "blocked" for x in c["events"])
        rows.append(
            dict(
                instance=entry["instance"],
                arm=entry["arm"],
                trigger=index,
                upstream=up,
                downstream=down,
                source=reference(file),
                chain=c,
            )
        )
    # Exercise specific false-attribution cases against the same genuine receipts.
    selected = next(
        r for r in rows if r["arm"] == "ADAPT" and r["instance"].startswith("matplotlib__")
    )
    control_source = read_json(Path(selected["source"]["path"]))["outcomes"]
    controls = {}
    for name in ("different_recipient", "conflicted_integration", "failed_handoff"):
        ops = deepcopy(control_source)
        for o in ops:
            if not o.get("decision"):
                continue
            t = o["decision"].get("action")
            if t == "handoff_patch" and name == "different_recipient":
                o["decision"]["arguments"]["to_member"] = "member_001"
            if t == "handoff_patch" and name == "failed_handoff":
                o["response"]["ok"] = False
            if (
                t == "integrate_patch"
                and name == "conflicted_integration"
                and o["response"].get("ok")
            ):
                o["response"]["result"]["conflict_count"] = 1
        events = dependency_chain(
            ops,
            boundary=selected["trigger"],
            start=1,
            upstream=selected["upstream"],
            downstream=selected["downstream"],
            producer="member_001",
            consumer="member_002",
        )["events"]
        disallowed = "adopted" if name == "conflicted_integration" else "addressed_handoff"
        assert all(r["kind"] != disallowed for r in events)
        controls[name] = dict(excluded=disallowed)
    save(
        PLAN / "historical-dependencies.json",
        dict(
            registered=reference(roster),
            rows=rows,
            negative_controls=controls,
            new_pairs=0,
            provider_calls=0,
        ),
    )
    for r in rows:
        print(r["instance"], r["arm"], r["trigger"], r["chain"]["last_witness"])


if __name__ == "__main__":
    main()
