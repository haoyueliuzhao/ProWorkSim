"""Recheck the registered natural delivery-stall archive scope without synthetic controls."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_three_graph_v240 import ROOT, freeze, read_json
from proworksim.software_anomaly_graph_v226 import AnomalyGraph


def main():
    scanned = 0
    ready = 0
    matches = []
    for f in sorted((ROOT / "runs").glob("software-benchmark-v2*/**/boundary.json")):
        if any(
            s in str(f.relative_to(ROOT)).lower()
            for s in ("/sdk", "fixture", "rehearsal", "performance-benchmark")
        ):
            continue
        outcomes = read_json(f).get("outcomes", [])
        if not outcomes:
            continue
        scanned += 1
        g = AnomalyGraph("member_001")
        for n, o in enumerate(outcomes, 1):
            g.observe(n, o)
            if (
                o.get("worker_id") == "member_001"
                and (o.get("decision") or {}).get("action") == "delivery_readiness"
                and ((o.get("response") or {}).get("result") or {}).get("ready_to_submit")
            ):
                ready += 1
            if any(
                v["anomaly_type"] == "A5" and v["status"] in ("ACTIVE", "OPEN")
                for v in g.nodes.values()
            ):
                matches.append([str(f.relative_to(ROOT)), n])
                break
    freeze(
        "a5-inventory.json",
        dict(
            branches=scanned,
            ready_receipts=ready,
            matches=matches,
            observer="member_001",
            provider_calls=0,
        ),
    )


if __name__ == "__main__":
    main()
