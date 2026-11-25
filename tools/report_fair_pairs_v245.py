"""Reconcile matched outcomes, work receipts and contribution chains under the v245 contract."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_fair_pairs_v245 import ARMS, AUTH, NS, PLAN, ROOT, RUN, read_json, save
from report_ordinary_successor_v243_2 import counts
from report_midtask_panel_v244 import paired
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_dependency_chain_v243_2 import dependency_chain
from proworksim.storage import digest, json_bytes
from check_midtask_panel_v244 import ReadOnlyStore, BundleCache
from proworksim.software_fair_delivery_v245 import FairWorld
from proworksim.software_graph_controller_v228 import PROJECT


def events(boundary):
    for step, o in enumerate(boundary["outcomes"], 1):
        d = o.get("decision") or {}
        r = o.get("response") or {}
        if d.get("action") and r.get("command_id"):
            yield (
                step,
                o["worker_id"],
                d["action"],
                d.get("arguments") or {},
                r,
                r.get("result") or {},
            )


def mechanism(inp, dec, boundary):
    active = dec["active"]
    info = dec["info"]
    option = active["decision"]["option"]
    change = inp["row"]["options"].get(option) or (info.get("orders") or {}).get(option, {})
    op = change.get("op") or change.get("dimension")
    actor = change.get("assignee") or change.get("actor")
    tid = change.get("task")
    inc = active["before"]["work"].get(tid, {})
    recipient = change.get("recipient") or inc.get("owner")
    products = {}
    adopted = set()
    dispatch = []
    read = []
    rework = []
    tests = Counter()
    same_test = 0
    for step, who, tool, args, r, v in events(boundary):
        if who == actor:
            dispatch.append(dict(step=step, action=tool, ok=r["ok"], command=r["command_id"]))
        if not r["ok"]:
            continue
        if tool == "reopen_work":
            rework.append(dict(step=step, actor=who, task=args["task_id"]))
        if tool in ("run_tests", "run_patch_review_tests") and v.get("executed"):
            version = v.get("source_reference") or (v.get("identity") or {}).get("source_reference")
            if version:
                key = digest(json_bytes([who, version, args.get("selection")]))
                same_test += bool(tests[key])
                tests[key] += 1
        if not active["changed"]:
            continue
        key = None
        if who == actor:
            if (
                op in ("verify", "D5")
                and tool == "org_review_patch"
                and tid in v.get("task_revisions", {})
                and v.get("decision") in ("accept", "request_changes")
            ):
                key = v["review_id"]
            if (
                op in ("verify", "D5")
                and tool == "review_evidence"
                and v.get("evidence_id")
                and args.get("evidence_id") == v["evidence_id"]
            ):
                if v.get("task_id") == tid:
                    key = v["evidence_id"]
            if (
                op == "diagnosis"
                and tool == "send_message"
                and args.get("task_id") == tid
                and args.get("recipient") == recipient
                and args.get("body", "").startswith("DIAG ")
            ):
                key = str(v["message_sequence"])
            if (
                op in ("transfer_unstarted", "D6")
                and tool == "complete_work"
                and v.get("task_id") == tid
            ):
                key = v.get("patch_id")
        if key is not None:
            products[key] = dict(
                step=step,
                tool=tool,
                command=r["command_id"],
                patch=v.get("patch_id"),
                version=v.get("identity"),
                verdict=v.get("decision"),
            )
        if who == actor:
            continue
        if tool == "read_work_event" and str(v.get("sequence")) in products:
            read.append(r["command_id"])
        if (
            recipient == who
            and tool == "send_message"
            and args.get("recipient") == actor
            and args.get("task_id") == tid
        ):
            words = args.get("body", "").split()
            if len(words) >= 2 and words[0] == "ADOPT" and words[1] in products:
                adopted.add(words[1])
        if (
            tool == "integrate_patch"
            and not v.get("conflicts")
            and args.get("patch_id") in products
        ):
            adopted.add(args["patch_id"])
        if tool == "submit_integration" and v.get("accepted"):
            for k, q in products.items():
                if (
                    q["verdict"] == "accept"
                    and q.get("version")
                    and q["version"].get("source_reference") == v.get("source_reference")
                ):
                    adopted.add(k)
    chain = None
    if op == "D4":
        chain = dependency_chain(
            boundary["outcomes"],
            boundary=0,
            start=1,
            upstream=change["upstream"],
            downstream=tid,
            producer=actor,
            consumer=recipient,
            known_artifact=change.get("artifact"),
        )
        for e in chain["events"]:
            art = e.get("artifact")
            if art and e["kind"] == "addressed_handoff":
                products[art] = e
            if art in products and e["kind"] == "adopted" and e.get("addressed"):
                adopted.add(art)
    return dict(
        basis=active.get("evidence_refs"),
        proposal=info.get("proposal"),
        validator=info["validator"],
        requested=info.get("requested", "KEEP"),
        changed=active["changed"],
        operation=op,
        task=tid,
        added_responsibility=change,
        before=inc,
        after=active["after"]["work"].get(tid),
        first_action=info.get("first_action"),
        actual=dispatch,
        products=products,
        downstream_read=read,
        confirmed_adopted=sorted(adopted),
        dependency=chain,
        initial_event="scheduled progress review",
        anomaly_resolution=None,
        reopens=rework,
        comparable_public_tests=sum(tests.values()),
        repeated_public_tests=same_test,
    )


def final_check(folder):
    world = FairWorld.__new__(FairWorld)
    world.store = ReadOnlyStore(folder / "prepared/world")
    world.state = world.store.load()
    world.bundle_cache = BundleCache()
    view = world._action_delivery_readiness("member_001", PROJECT)
    lock = read_json(folder / "closure/terminal-code/lock.json")
    assert all(lock[k] == v for k, v in view["final_identity"].items())
    return dict(
        gaps=view["gaps"],
        fixed=view["current_fixed_patch_ids"],
        test=view["final_test"],
        packages=[
            {
                k: p[k]
                for k in ("task_id", "owner", "reviewer", "missing", "independent_review_required")
            }
            for p in view["package_chain"]["packages"]
        ],
    )


def main():
    roster = read_json(PLAN / "roster.json")["roster"]
    previous = {
        r["instance"]: r
        for r in read_json(ROOT / "artifacts/software-benchmark-v244/midtask15-r1/results.json")[
            "rows"
        ]
    }
    rows = []
    totals = {a: Counter() for a in ARMS}
    with closing(
        sqlite3.connect(Path(read_json(AUTH)["ledger"]).as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("BEGIN")
        for case in roster:
            row = dict(
                instance=case["instance"],
                index=case["index"],
                checkpoint=case["checkpoint"],
                prefix=case["prefix"],
            )
            rows.append(row)
            row["v244"] = {
                a: {k: x.get("resolved") for k, x in previous[row["instance"]][a]["scores"].items()}
                for a in ARMS
            }
            for arm in ARMS:
                base = RUN / str(case["index"])
                folder = base / arm
                inv = counts(db, f"{NS}:{case['index']}:{arm}")["paid"]
                totals[arm].update(inv)
                rec = row[arm] = dict(paid=inv, scores={})
                if not (folder / "result.json").exists():
                    continue
                res = read_json(folder / "result.json")
                rec.update(
                    status=res["status"],
                    termination=res.get("termination"),
                    error=res.get("error"),
                    generation_seconds=res["finished"] - res["started"],
                    started=res["started"],
                )
                if res["status"] != "closed":
                    continue
                dec = read_json(folder / "decision.json")
                inp = read_json(folder / "decision-input.json")
                bound = read_json(folder / "boundary.json")
                rec.update(
                    policy_tokens=dec["info"]["osa_tokens"],
                    logical_tokens=res["logical_tokens"] + dec["info"]["osa_tokens"],
                    input_hash=digest((folder / "decision-input.json").read_bytes()),
                    mechanism=mechanism(inp, dec, bound),
                    opportunities=bound["opportunities"],
                    integrity_error=bound["execution_integrity_failure"],
                    final_check=final_check(folder),
                    missing_reviewer_at_start=[
                        p["task_id"]
                        for p in inp["view"]["package_chain"]["packages"]
                        if "assign_verification" in p["missing"]
                    ],
                    reviewer_calls=[
                        dict(
                            step=i,
                            actor=a,
                            task=args.get("task_id"),
                            ok=r["ok"],
                            code=((r.get("error") or {}).get("rejection") or {}).get("code"),
                        )
                        for i, a, t, args, r, v in events(bound)
                        if t == "assign_verification"
                    ],
                    submissions=[
                        dict(
                            step=i,
                            actor=a,
                            ok=r["ok"],
                            reason=(r.get("error") or {}).get("message"),
                        )
                        for i, a, t, args, r, v in events(bound)
                        if t == "submit_integration"
                    ],
                )
                assert rec["logical_tokens"] == case["prefix"] + inv["tokens"] <= 5_000_000
                for k in ("code", "delivery"):
                    score = base / (arm + "-" + k) / "receipt.json"
                    if not score.exists():
                        continue
                    v = read_json(score)
                    rec["scores"][k] = dict(
                        resolved=v.get("resolved"),
                        status=v["status"],
                        source=reference(score),
                        failure=v.get("failure_evidence"),
                        tests=(v.get("official_result") or [None, {}])[1]
                        .get(case["instance"], {})
                        .get("tests_status"),
                    )
                receipts = list(rec["scores"].values())
                rec["end_wall"] = max(
                    [
                        res["finished"],
                        *[
                            read_json(Path(v["source"]["path"])).get("finished", res["finished"])
                            for v in receipts
                        ],
                    ]
                )
                rec["receipt_cleanup"] = read_json(folder / "actor/cleanup.json").get(
                    "owned_actor_removed"
                )
            if all(a in row and "input_hash" in row[a] for a in ARMS):
                assert row["KEEP"]["input_hash"] == row["OSA"]["input_hash"]
        ledger = db.execute(
            "select status,count(*),sum(cost) from requests group by status"
        ).fetchall()
        pending = db.execute("select count(*) from block_slots where status='pending'").fetchone()[
            0
        ]
        active = db.execute("select count(*) from slots where status!='closed'").fetchone()[0]
    assert sum(t["nanoyuan"] for t in totals.values()) == sum(
        c for state, _, c in ledger if state == "settled"
    )
    if all(r[a].get("status") == "closed" for r in rows for a in ARMS):
        assert pending == active == 0 and all(r[a]["receipt_cleanup"] for r in rows for a in ARMS)
    adjustments = [m for r in rows for m in [r["OSA"].get("mechanism")] if m and m["changed"]]
    n = sum(len(m["products"]) for m in adjustments)
    rates = dict(
        additional=[sum(bool(m["products"]) for m in adjustments), len(adjustments)],
        adoption_confirmed=[sum(len(m["confirmed_adopted"]) for m in adjustments), n],
        resolution=[0, 0],
        resolution_scope="Scheduled midtask forks; no natural starting anomaly was independently enrolled.",
        interpretation="Observed new products of the assigned kind. Matched KEEP and downstream receipts are required for claims of incremental value. Zero denominators are not estimable.",
    )
    result = dict(
        rows=rows,
        totals={a: dict(c) for a, c in totals.items()},
        ledger=ledger,
        pending=pending,
        active=active,
        rates=rates,
        endpoints={k: paired(rows, k) for k in ("code", "delivery")},
    )
    save(PLAN / "results.json", result)
    print(result["endpoints"], result["rates"], result["totals"])


if __name__ == "__main__":
    main()
