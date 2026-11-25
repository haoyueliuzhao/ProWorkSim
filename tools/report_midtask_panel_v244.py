"""Summarize all frozen pairs, including unresolved endpoints, from original receipts."""

from collections import Counter
from hashlib import sha256
from contextlib import closing
from math import comb
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_midtask_panel_v244 import ARMS, AUTH, PLAN, RUN, read_json, save
from report_ordinary_successor_v243_2 import counts


def paired(rows, endpoint):
    bins = Counter()
    bounds = {arm: [0, 0] for arm in ARMS}
    difference = [0, 0]
    for r in rows:
        values = [r[arm]["scores"].get(endpoint, {}).get("resolved") for arm in ARMS]
        for arm, v in zip(ARMS, values):
            bounds[arm][0] += v is True
            bounds[arm][1] += v is not False
        k, o = values
        difference[0] += int(o is True) - int(k is not False)
        difference[1] += int(o is not False) - int(k is True)
        name = (
            "unknown"
            if None in values
            else {
                (True, True): "both",
                (True, False): "KEEP_only",
                (False, True): "OSA_only",
                (False, False): "neither",
            }[k, o]
        )
        bins[name] += 1
    a, b = bins["KEEP_only"], bins["OSA_only"]
    n = a + b
    p = min(1, 2 * sum(comb(n, j) for j in range(min(a, b) + 1)) / 2**n)
    return dict(
        denominator=len(rows),
        cells=dict(bins),
        pass_count_bounds=bounds,
        paired_difference_count_bounds=difference,
        exact_mcnemar_two_sided_if_complete=p if not bins["unknown"] else None,
    )


def main():
    spec = read_json(PLAN / "roster.json")
    records = []
    totals = {a: Counter() for a in ARMS}
    with closing(
        sqlite3.connect(Path(read_json(AUTH)["ledger"]).as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("BEGIN")
        for c in spec["roster"]:
            row = dict(instance=c["instance"], checkpoint=c["checkpoint"], prefix=c["prefix"])
            records.append(row)
            for arm in ARMS:
                base = RUN / str(c["index"])
                dst = base / arm
                result = read_json(dst / "result.json") if (dst / "result.json").exists() else {}
                paid = counts(db, f"v244:{c['index']}:{arm}")["paid"]
                score = {}
                for k in ["code", "delivery"]:
                    path = base / (arm + "-" + k) / "receipt.json"
                    if path.exists():
                        rec = read_json(path)
                        score[k] = {f: rec.get(f) for f in ["status", "resolved"]}
                        if rec.get("official_result"):
                            iid, data = rec["official_result"]
                            score[k]["tests"] = {
                                category: {outcome: len(nodes) for outcome, nodes in groups.items()}
                                for category, groups in data[iid].get("tests_status", {}).items()
                            }
                            score[k]["new_failures"] = (
                                data[iid]
                                .get("tests_status", {})
                                .get("FAIL_TO_PASS", {})
                                .get("failure", [])
                            )
                row[arm] = dict(status=result.get("status", "outstanding"), scores=score, paid=paid)
                totals[arm].update(paid)
                if (dst / "decision.json").exists():
                    dec = read_json(dst / "decision.json")
                    row[arm].update(
                        changed=dec["active"].get("changed"),
                        decision_input_sha256=sha256(
                            (dst / "decision-input.json").read_bytes()
                        ).hexdigest(),
                        requested=dec["info"].get("requested"),
                        first_action=dec["info"].get("first_action"),
                        decision_error=dec["info"].get("error"),
                        applied_choice=dec["active"].get("decision"),
                        ending=result.get("termination"),
                        option=dec["active"].get("decision", {}).get("option"),
                        validator=dec["info"].get("validator"),
                        osa_tokens=dec["info"].get("osa_tokens", 0),
                    )
                    if result.get("status") == "closed":
                        assert (
                            c["prefix"] + paid["tokens"]
                            == result["logical_tokens"] + row[arm]["osa_tokens"]
                        )
                        row[arm]["logical_including_osa"] = c["prefix"] + paid["tokens"]
                if (dst / "boundary.json").exists():
                    outcomes = read_json(dst / "boundary.json")["outcomes"]
                    row[arm]["member_actions"] = dict(Counter(o["worker_id"] for o in outcomes))
                    row[arm]["public_tests"] = [
                        dict(
                            actor=o["worker_id"],
                            action=o["decision"]["action"],
                            passed=(o.get("response", {}).get("result") or {}).get("passed"),
                            executed=(o.get("response", {}).get("result") or {}).get("executed"),
                        )
                        for o in outcomes
                        if (o.get("decision") or {}).get("action")
                        in {"run_tests", "run_patch_review_tests"}
                    ]
                    row[arm]["operations"] = dict(
                        Counter(
                            o.get("decision", {}).get("action")
                            for o in outcomes
                            if o.get("decision")
                        )
                    )
            fingerprints = [row[arm].get("decision_input_sha256") for arm in ARMS]
            if all(fingerprints) and len(set(fingerprints)) != 1:
                raise ValueError(f"Decision inputs differ for {c['instance']}")
        account = db.execute("select value from meta where key='cap'").fetchone()
        receipts = db.execute(
            "select status,count(*),coalesce(sum(cost),0) from requests group by status"
        ).fetchall()
        assert int(account[0]) == 190_000_000_000
        assert sum(d["nanoyuan"] for d in totals.values()) == sum(
            cost for status, _, cost in receipts if status == "settled"
        )
    save(
        PLAN / "results.json",
        dict(
            account=dict(
                cap_nanoyuan=int(account[0]),
                requests={s: dict(count=n, nanoyuan=cost) for s, n, cost in receipts},
            ),
            rows=records,
            total={k: dict(v) for k, v in totals.items()},
            endpoints={k: paired(records, k) for k in ["code", "delivery"]},
        ),
    )


if __name__ == "__main__":
    main()
