"""Describe the two priority A2 events with budget at the receipt; query no model or grade."""

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_event_pairs_v243 as study
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_three_graph_v240 import base
from proworksim.storage import read_json


def main():
    f = study.ROOT / "artifacts/software-benchmark-v242-1/precursors-r1/historical-windows.json"
    inventory = read_json(
        study.ROOT / "artifacts/software-benchmark-v242/multitype-r1/checkpoint-inventory.json"
    )["records"]
    rows = []
    for track in read_json(f)["rows"]:
        for n in track.get("first_signals", []):
            if n["kind"] != "A2":
                continue
            known = [
                r["checkpoint"]
                for r in inventory
                if r["instance"] == track["instance"]
                and any(v["kind"] == "A2" and v["exact"] for v in r["views"])
            ]
            rows.append(
                dict(
                    instance=track["instance"],
                    arm=track["arm"],
                    subject=n["subject"],
                    command=n["command"],
                    remaining=n["remaining_tokens"],
                    pair_upper_nanoyuan=16000 * n["remaining_tokens"],
                    matched_exact=known,
                )
            )
    spec = read_json(study.PLAN / study.CASE / "protocol.json")
    item = spec["roster"][0]
    (raw,) = list((study.RUN / study.CASE / "OSA/osa-api").glob("*/request.json"))
    message = json.loads(read_json(raw)["payload"]["wire"]["messages"][-1]["content"])
    for key in ("project_graph", "obligation_graph", "organization_graph"):
        assert key in message
    branch = study.RUN / study.CASE / "OSA"
    planned = read_json(branch / "decision.json")["graph_patch"]
    active = read_json(branch / "assigned-graph.json")
    persisted = read_json(branch / "mechanism.json")["control"]["execution_orders"]
    assert planned["target_version"] == base.identity(active["after"])
    assert active["after"]["execution_orders"] == persisted
    assert (
        active["after"]["members"] == active["before"]["members"]
        and len(active["after"]["members"]) == 2
    )
    study.save(
        study.PLAN / study.CASE / "decision-input.json",
        dict(
            checkpoint=item["checkpoint"],
            graphs={
                k: message[k] for k in ("project_graph", "obligation_graph", "organization_graph")
            },
            orders=message["optional_execution_orders"],
            source=reference(raw),
            target_fingerprint=planned["target_version"],
            world_orders=persisted,
            graph_matched=True,
        ),
    )
    study.save(study.PLAN / "priority-a2.json", dict(source=reference(f), cases=rows, paid_calls=0))


if __name__ == "__main__":
    main()
