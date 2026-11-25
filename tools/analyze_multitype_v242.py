"""Audit versioned successors, handoffs, review evidence and the separate official endpoints."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory_multitype_v242 import PLAN, RUN, ROOT, save
from proworksim.software_anomaly_lifecycle_v242 import lifecycle
from proworksim.storage import read_json
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.software_context_panel_v231 import PairedLedger


def main():
    historical = []
    for r in read_json(ROOT / "artifacts/software-benchmark-v241/paired-r1/results.json")["rows"]:
        folder = checked(
            next(f for f in r["sources"] if f["path"].endswith("/boundary.json"))
        ).parent
        historical.append(
            dict(case=r["case"], arm=r["condition"], old=r["anomaly"], new=lifecycle(folder))
        )
    save(PLAN / "observer-replay.json", dict(records=historical, provider_calls=0))
    records = []
    for f in sorted(PLAN.glob("*/protocol.json")):
        item = read_json(f)["roster"][0]
        folder = RUN / item["case"]
        if not (folder / "completed.json").is_file():
            continue
        for arm in ("KEEP", "OSA"):
            dest = folder / arm
            result = read_json(dest / "result.json")
            record = dict(
                case=item["case"],
                kind=item["kind"],
                arm=arm,
                status=result["status"],
                result=reference(dest / "result.json"),
            )
            records.append(record)
            if result["status"] != "closed":
                record["error"] = result.get("error")
                continue
            d = read_json(dest / "decision.json")
            b = read_json(dest / "boundary.json")
            g = read_json(dest / "assigned-graph.json")
            m = read_json(dest / "mechanism.json")
            lock = read_json(checked(read_json(dest / "candidate-lock.json")))
            events = [o for o in b["outcomes"] if (o.get("decision") or {}).get("action")]
            with PairedLedger.load(RUN / "authority.json").db() as db:
                costs = db.execute(
                    "select status,count(*),sum(tokens),sum(cost) from requests where slot=? group by status",
                    (result["slot"],),
                ).fetchall()
            record.update(
                remaining=result["available_at_start"],
                prefix=5000000 - item["initial_budget"],
                logical=result["logical_tokens"],
                costs=costs,
                submitted=lock["submitted"],
                termination=result["termination"],
                decision=d,
                changed=g["changed"],
                graph_realized=g["after"] == d.get("expected_graph", g["before"]),
                lifecycle=lifecycle(dest),
                duties=m["control"]["duties"],
                operations=[
                    dict(
                        actor=o["worker_id"],
                        tool=o["decision"]["action"],
                        ok=(o.get("response") or {}).get("ok"),
                    )
                    for o in events
                ],
                scores={
                    k: read_json(folder / (arm + "-" + k) / "receipt.json")["resolved"]
                    for k in ("code", "delivery")
                },
                receipts=[
                    reference(p)
                    for p in [
                        dest / "mechanism.json",
                        dest / "boundary.json",
                        *(folder / (arm + "-" + k) / "receipt.json" for k in ("code", "delivery")),
                    ]
                ],
            )
    save(PLAN / "results.json", dict(records=records, cn_updates=0))


if __name__ == "__main__":
    main()
