"""Freeze historical member-visible states and a separately labelled delivery-stall control."""

from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_osa_states_v236 import build, save
from proworksim.software_anomaly_graph_v226 import AnomalyGraph
from proworksim.software_context_panel_v231 import ROOT
from proworksim.storage import read_json

PLAN = ROOT / "artifacts/software-benchmark-v237/structured-decisions-r1"


def main():
    rows = [
        r
        for r in read_json(
            ROOT / "artifacts/software-benchmark-v236/decision-differentiation-r1/panel.json"
        )
        if r["id"] != "s11"
    ]
    candidates = []
    scanned = 0
    ready_count = 0
    for f in sorted((ROOT / "runs").glob("software-benchmark-v2*/*/*/*/boundary.json")):
        if (
            any(
                s in str(f).lower()
                for s in ("/sdk", "fixture", "/rehearsal", "performance-benchmark")
            )
            or f.stat().st_size > 24_000_000
        ):
            continue
        outcomes = read_json(f).get("outcomes", [])
        if not outcomes:
            continue
        scanned += 1
        g = AnomalyGraph("member_001")
        for i, o in enumerate(outcomes, 1):
            act = (o.get("decision") or {}).get("action")
            if (
                o.get("worker_id") == "member_001"
                and act == "delivery_readiness"
                and ((o.get("response") or {}).get("result") or {}).get("ready_to_submit") is True
            ):
                ready_count += 1
            g.observe(i, o)
            if any(
                n["anomaly_type"] == "A5" and n["status"] in ("OPEN", "ACTIVE")
                for n in g.nodes.values()
            ):
                candidates.append([str(f.relative_to(ROOT)), i])
                break
    save(
        PLAN / "a5-inventory.json",
        dict(
            branches=scanned,
            ready_receipts=ready_count,
            matches=candidates,
            scope="readable v2* branch boundary archives <=24 MB at */*/* depth, excluding SDK, rehearsal, fixtures and performance benchmarks",
        ),
    )
    if candidates:
        raise RuntimeError("Inspect natural A5 evidence before freezing a synthetic control")
    source = "software-benchmark-v217/selection28-r1/task-21/KEEP"
    row = build("s13", "A5", source, [41])
    ev = row["evidence"]["E1"]
    assert ev["ready"] and ev["fixed"]
    row["targets"] = [x["task_id"] for x in ev["packages"]]
    row["work_status"] = {x: {"completed": True} for x in row["targets"]}
    row["evidence"]["E2"] = {
        "operation": "subsequent_opportunities",
        "observed_owner_steps": 3,
        "submit_attempted": False,
        "code_changed": False,
    }
    row["evidence"]["E3"] = deepcopy(ev)
    row["provenance"]["construction"] = (
        "Synthetic delayed continuation of the real ready receipt. E2 and E3 are scripted, not historical events. Budget held at the real readiness boundary for the control."
    )
    rows.append(row)
    target = PLAN / "panel.json"
    if target.exists() and read_json(target) != rows:
        raise ValueError("Panel changed")
    save(target, rows)


if __name__ == "__main__":
    main()
