"""Compare contextualized organization choices and official endpoints without pooling tasks and calls."""

from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_osa_prompt_pairs_v248_9 as pairs
import report_dynamic_panel_v248 as prior
from report_ordinary_successor_v243_2 import counts
from proworksim.storage import read_json

panel = pairs.panel
first = panel.first
OUTPUT = panel.PLAN.parent / "results.json"


def audit(state, proposal):
    assessment = proposal.get("assessment", {})
    anomaly = assessment.get("anomaly_type")
    incident = state["project_graph"].get("incident") or {}
    result = dict(
        anomaly=anomaly,
        evidence_keys=assessment.get("evidence_refs", []),
        public_incident=bool(incident),
        decision=proposal.get("decision"),
    )
    if anomaly == "A1":
        text = json.dumps(proposal, ensure_ascii=False)
        refs = incident.get("receipts", [])
        versions = [v["version_id"] for v in incident.get("tested_versions", [])]
        result["a1"] = dict(
            public_distinct_receipts=len(set(refs)),
            public_target=incident.get("target"),
            public_versions=versions,
            exact_receipts_written=sum(r in text for r in set(refs)),
            exact_target_written=bool(incident.get("target") and incident["target"] in text),
            versions_written=[v for v in sorted(set(versions)) if v in text],
            target_kind=incident.get("target_kind"),
        )
    return result


def probes(db):
    rows = []
    for s in read_json(pairs.PLAN)["sites"]:
        state = json.loads(
            read_json(Path(s["source"]["path"]))["payload"]["wire"]["messages"][1]["content"]
        )
        row = {k: v for k, v in s.items() if k != "source"}
        answers = {}
        for version in pairs.MODELS:
            folder = pairs.RUN / str(s["index"]) / version
            record = read_json(folder / "record.json")
            if record["status"] == "accepted":
                intent = read_json(folder / "intent.json")
                record["audit"] = audit(state, intent)
            record["usage"] = counts(db, pairs.names(s)[version])
            answers[version] = record
        rows.append(dict(**row, answers=answers))
    summary = {}
    for key in pairs.MODELS:
        records = [r["answers"][key] for r in rows]
        actions = Counter()
        usage = Counter()
        anomalies = Counter()
        for r in records:
            actions[(r.get("decision") or {}).get("action", r["status"])] += 1
            anomalies[(r.get("audit") or {}).get("anomaly", "unavailable")] += 1
            usage.update(r["usage"]["paid"])
        summary[key] = dict(actions=dict(actions), anomalies=dict(anomalies), paid=dict(usage))
    return dict(sites=rows, summary=summary)


def trajectories(db):
    hist = read_json(panel.PLAN.parent.parent / "dynamic-membership-r2/results.json")["blocks"]
    rows = []
    for row in read_json(panel.PLAN)["rows"]:
        case = row["case"]
        i = case["index"]
        previous = next(b for b in hist if b["instance"] == case["instance"])
        arms = {}
        for arm in panel.ARMS:
            root = panel.RUN / str(i) / arm
            item = prior.details(panel.RUN, i, arm)
            cap = counts(db, panel.slot(i, arm))
            item["paid"] = cap
            if item["status"] == "closed":
                assert (
                    item["logical_tokens"] == row["prefix"] + cap["paid"]["tokens"] <= first.LIMIT
                )
                assert item["checkpoint"] == row["identity"]
            for check in item["decisions"]:
                d = root / "decisions" / f"{check['opportunity']:04d}"
                f = d / "proposal.json"
                if f.exists():
                    intent = pairs.compiler.unpack(read_json(f))
                    if isinstance(intent, dict):
                        state = read_json(d / "state.json")
                        check["audit"] = audit(state, intent)
                        if check["status"] in {"CHANGE", "KEEP", "ABSTAIN", "partial"}:
                            compiled = pairs.compiler.compile_intent(state, intent)
                            check["proposal"] = compiled["decision"]
                            check["membership"] = compiled["membership_decision"]
                            check["expected"] = compiled["expected_contribution"]
                            check["first_action"] = compiled["execution_plan"]["immediate_action"]
            arms[arm] = item
        historical = {
            a: dict(
                scores=r["scores"], logical_tokens=r["logical_tokens"], deployment=r["deployment"]
            )
            for a, r in previous["arms"].items()
        }
        rows.append(
            dict(
                instance=case["instance"],
                prefix_tokens=row["prefix"],
                historical=historical,
                current=arms,
            )
        )
    return rows


def main():
    with closing(
        sqlite3.connect(Path(read_json(first.AUTH)["ledger"]).as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("BEGIN")
        fixed = probes(db)
        live = trajectories(db)
        totals = db.execute(
            "select count(*),sum(tokens),sum(cost) from requests where (slot glob 'v248.9:*' or slot glob 'v248.9-probe:*') and status='settled'"
        ).fetchone()
        overall = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
    first.save(
        OUTPUT,
        dict(
            fixed_inputs=fixed,
            live=live,
            settled_calls=totals[0],
            physical_tokens=totals[1],
            nanoyuan=totals[2],
            ledger_paid_nanoyuan=overall,
        ),
    )
    print(fixed["summary"])
    for case in live:
        print(
            case["instance"],
            [(k, v["scores"], v["logical_tokens"]) for k, v in case["current"].items()],
        )


if __name__ == "__main__":
    main()
