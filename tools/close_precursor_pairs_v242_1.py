"""Reconcile the separately registered extension without rewriting the original v242 closeout."""

from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_precursor_pairs_v242_1 import PLAN, RUN, TRIAL, clone, read_json, save
from close_multitype_v242 import resource_receipts, trace
from report_successors_v242 import accountable
from proworksim.software_anomaly_graph_v226 import tested_nodes, TESTS
from proworksim.software_benchmark_candidates_v054 import reference


def results():
    done = read_json(RUN / "completed.json")
    spec = read_json(TRIAL)
    auth = read_json(RUN / "authority.json")
    totals = Counter()
    entries = []
    pairs = []
    with closing(sqlite3.connect(Path(auth["ledger"]).as_uri() + "?mode=ro", uri=True)) as db:
        for c in spec["candidates"]:
            case = c["case"]
            dest = RUN / "recruitment" / case / "COMMON"
            entry = dict(case=case, status=done[case], scope=c["kind"], stages={})
            anchors = next(r for r in spec["screening"] if r["source"] == c["source"])
            markers = anchors["indicators"]
            if (dest / "observations.json").exists():
                signals = {}
                for marker in markers:
                    if marker["kind"] == "A1":
                        signals.setdefault((marker["actor"], marker["target"]), [])
                for h in read_json(dest / "observations.json"):
                    if h["ordinal"] <= c["anchor_ordinal"]:
                        continue
                    o = h["outcome"]
                    response = o.get("response") or {}
                    v = response.get("result") or {}
                    if (o.get("decision") or {}).get("action") not in TESTS or not response.get(
                        "ok"
                    ):
                        continue
                    fail, passed = tested_nodes(v)
                    for (a, node), witness in signals.items():
                        if a == o["worker_id"] and (node in fail or node in passed):
                            witness.append(
                                dict(
                                    ordinal=h["ordinal"],
                                    passed=node in passed,
                                    source=v.get("source_reference"),
                                )
                            )
                entry["later_named_test_receipts"] = [
                    dict(actor=k[0], target=k[1], later=w) for k, w in signals.items()
                ]
                entry.update(trace(dest, c["anchor_ordinal"]))
            if (dest / "progress.json").exists():
                progress = read_json(dest / "progress.json")
                entry.update(
                    opportunities=progress["opportunity"] - c["anchor_ordinal"],
                    remaining=progress["available"],
                )
            if (dest / "result.json").exists():
                entry["result"] = reference(dest / "result.json")
            stages = {"common": "v242:recruit:" + case + ":COMMON"}
            if done[case] == "point_ready":
                item = read_json(PLAN / case / "protocol.json")["roster"][0]
                pair = {arm: accountable(RUN / case / arm, item) for arm in ("KEEP", "OSA")}
                pairs.append(dict(case=case, branches=pair))
                stages.update({arm: "v242.1:" + case + ":" + arm for arm in pair})
            for stage, slot in stages.items():
                paid = Counter()
                states = Counter()
                for status, cost, tokens, body in db.execute(
                    "select status,cost,tokens,body from requests where slot=?", (slot,)
                ):
                    states[status] += 1
                    if status != "settled":
                        continue
                    u = json.loads(body)
                    assert (
                        tokens == u["input_tokens"] + u["output_tokens"]
                        and cost == u["peak_cost_nanoyuan"]
                    )
                    paid.update(
                        calls=1,
                        input=u["input_tokens"],
                        output=u["output_tokens"],
                        tokens=tokens,
                        cost_nanoyuan=cost,
                    )
                entry["stages"][stage] = dict(usage=dict(paid), request_states=dict(states))
                totals.update(paid)
            entries.append(entry)
        settled = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        held += db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        active = db.execute(
            "select id,status from slots where (id like 'v242:recruit:p242b-%' or id like 'v242.1:p242b-%') and status!='closed'"
        ).fetchall()
        pending = db.execute(
            "select slot from block_slots where (slot like 'v242:recruit:p242b-%' or slot like 'v242.1:p242b-%') and status='pending'"
        ).fetchall()
    release = clone(resource_receipts, {**resource_receipts.__globals__, "RUN": RUN})(
        [p["case"] for p in pairs], done, [c["task"]["configuration"] for c in spec["candidates"]]
    )
    save(
        PLAN / "closeout.json",
        dict(
            physical=dict(totals),
            remaining_nanoyuan=auth["cap_nanoyuan"] - settled - held,
            account_cap_nanoyuan=auth["cap_nanoyuan"],
            preexisting_and_current_holds=held,
            active=active,
            pending=pending,
            cases=entries,
            pairs=pairs,
            resources=release,
        ),
    )


if __name__ == "__main__":
    results()
