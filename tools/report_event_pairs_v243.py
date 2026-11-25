"""Join controller intent, execution receipts and independent official grading for each branch."""

from collections import Counter
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_event_pairs_v243 as study
from close_multitype_v242 import resource_receipts
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_successor_evidence_v242 import evaluate
from proworksim.software_dependency_chain_v243_2 import dependency_chain
from proworksim.storage import read_json

PLAN, RUN = study.PLAN, study.RUN


def mechanism(folder, item, active, decision, process, lock):
    outcomes = read_json(folder / "boundary.json")["outcomes"]
    rows = []
    for i, o in enumerate(outcomes, decision["original_ordinal"] + 1):
        d = o.get("decision") or {}
        r = o.get("response") or {}
        if not d.get("action"):
            continue
        rows.append((i, o["worker_id"], d["action"], d.get("arguments") or {}, r))
    order = next(iter(active["after"].get("execution_orders", {}).values()), None)
    action = decision.get("first_action")
    attempts = []
    readiness = []
    reopened = []
    products = []
    uses = []
    matched_test = []
    informal, reads, edits = [], [], []
    tip = None
    published = set()
    for i, actor, tool, args, r in rows:
        ok = r.get("ok")
        v = r.get("result") or {}
        error = (r.get("error") or {}).get("rejection") or {}
        ref = v.get("source_reference") or (v.get("identity") or {}).get("source_reference")
        cmd = r.get("command_id")
        if tool == "reopen_work" and ok:
            reopened.append(dict(actor=actor, task=args.get("task_id"), ordinal=i, command=cmd))
        if tool == "delivery_readiness" and ok:
            tip = dict(ordinal=i, gaps=v.get("gaps"), ready=v.get("ready_to_submit"), command=cmd)
        if item["kind"] == "A2" and actor == item["row"]["observer"]:
            rd = (
                v
                if tool == "work_readiness" and ok
                else (error.get("context") or {}).get("readiness", {})
            )
            if rd.get("task_id") in item["row"]["targets"] and "gaps" in rd:
                target = decision["anomaly"]["subject"]
                gaps = [
                    g
                    for g in rd["gaps"]
                    if target in (g.get("task_id"), g.get("patch_id"), g.get("evidence_id"))
                ]
                readiness.append(
                    dict(
                        ordinal=i,
                        command=cmd,
                        epoch=rd.get("work_epoch"),
                        edge_blocked=bool(gaps),
                        ready=rd.get("ready"),
                        gaps=gaps,
                    )
                )
        if not order:
            continue
        origin = actor == order["actor"]
        consumer = actor == order["recipient"]
        patch = v.get("patch_id") or args.get("patch_id")
        ev = dict(
            ordinal=i, tool=tool, actor=actor, accepted=ok, command=cmd, patch=patch, version=ref
        )
        if origin and tool in (
            "org_review_patch",
            "fix_patch",
            "complete_work",
            "complete_evidence",
            "integrate_patch",
            "handoff_patch",
            "run_patch_review_tests",
        ):
            attempts.append({**ev, "rejection": error.get("code"), "verdict": v.get("decision")})
        if not ok:
            continue
        if (
            origin
            and tool == "send_message"
            and args.get("recipient") == order["recipient"]
            and order.get("artifact")
            and order["artifact"] in args.get("body", "")
        ):
            informal.append(
                {**ev, "message_sequence": v.get("message_sequence"), "text": args["body"][:480]}
            )
        if (
            consumer
            and tool == "read_work_event"
            and any(m["message_sequence"] == v.get("sequence") for m in informal)
        ):
            reads.append({**ev, "sequence": v["sequence"]})
        if (
            consumer
            and reads
            and tool in ("edit_file", "replace_file", "write_file", "apply_patch")
        ):
            edits.append({**ev, "path": args.get("path")})
        if (
            order["dimension"] == "D5"
            and origin
            and patch == order["artifact"]
            and ref == order["version"]
        ):
            if tool == "run_patch_review_tests" and v.get("executed"):
                matched_test.append(ev)
            if (
                tool == "org_review_patch"
                and v.get("author") != actor
                and order["task"] in v.get("task_revisions", {})
                and v.get("decision") in ("accept", "request_changes")
            ):
                products.append(
                    {**ev, "verdict": v["decision"], "sequence": v.get("event_sequence")}
                )
        if order["dimension"] == "D6" and origin:
            pkg = order.get("upstream", order["task"])
            if tool in ("complete_work", "complete_evidence") and args.get("task_id") == pkg:
                aid = patch or v.get("evidence_id") or args.get("evidence_id")
                if aid:
                    published.add(aid)
            if (
                tool == "handoff_patch"
                and patch in published
                and args.get("to_member") == v.get("recipient") == order["recipient"]
            ):
                products.append({**ev, "sequence": v.get("handoff_sequence")})
        if consumer and products:
            if tool == "read_work_event" and any(
                p.get("sequence") is not None and v.get("sequence") == p["sequence"]
                for p in products
            ):
                uses.append({**ev, "kind": "read"})
            if (
                tool in ("integrate_patch", "adopt_evidence")
                and (patch or args.get("evidence_id")) in published
            ):
                uses.append({**ev, "kind": "adopt"})
            if (
                tool == "submit_integration"
                and lock["submitted"]
                and order["dimension"] == "D5"
                and any(
                    p.get("verdict") == "accept" and p["version"] == process["lock"]
                    for p in products
                )
            ):
                delivery = read_json(checked(lock["last_legal_delivery"]))
                if delivery.get("source_reference") == order["version"]:
                    uses.append({**ev, "kind": "adopt"})
    chain = None
    if order and order["dimension"] == "D4":
        chain = dependency_chain(
            outcomes,
            boundary=decision["original_ordinal"],
            start=decision["original_ordinal"] + 1,
            upstream=order["upstream"],
            downstream=order["task"],
            producer=order["actor"],
            consumer=order["recipient"],
            known_artifact=order.get("artifact"),
        )
        products = [r for r in chain["events"] if r["kind"] == "addressed_handoff"]
        uses = [
            {**r, "kind": "adopt" if r["kind"] == "adopted" else "read"}
            for r in chain["events"]
            if r["kind"] == "read_handoff" or (r["kind"] == "adopted" and r["addressed"])
        ]
    booked = next((r for r in rows if action and r[1] == action["actor"]), None)
    return dict(
        proposal=decision.get("proposal"),
        registered_type=item["kind"],
        validator=decision["validator"],
        checks=decision.get("validation_checks", []),
        requested=decision.get("requested", "KEEP"),
        graph_patch=decision.get("graph_patch"),
        actual_graph_changed=active["changed"],
        order=order,
        first_dispatch=action,
        first_actual=dict(ordinal=rows[0][0], actor=rows[0][1], tool=rows[0][2]) if rows else None,
        assigned_actual_opportunity=booked[0] if booked else None,
        grants=decision.get("planned_grants"),
        order_attempts=attempts,
        matching_review_tests=matched_test,
        informal_messages=informal,
        informal_read=reads,
        edits_after_read=edits,
        order_products=products,
        dependency_chain=chain,
        downstream_receipts=uses,
        readiness=readiness,
        recorded_reopen=reopened,
        final_readiness_observation=tip,
    )


def main():
    auth = read_json(RUN / "authority.json")
    cases = []
    allcost = Counter()
    specs = []
    with closing(sqlite3.connect(Path(auth["ledger"]).as_uri() + "?mode=ro", uri=True)) as db:
        for f in sorted(PLAN.glob("*/protocol.json")):
            spec = read_json(f)
            item = spec["roster"][0]
            case = item["case"]
            base = RUN / case
            if not (base / "completed.json").exists():
                raise ValueError("Unfinished " + case)
            specs.append(item)
            row = dict(
                case=case,
                instance=item["instance"],
                anomaly=item["kind"],
                checkpoint=item["checkpoint"],
                branches={},
            )
            for arm in ("KEEP", "OSA"):
                folder = base / arm
                res = read_json(folder / "result.json")
                usage = Counter()
                states = Counter()
                for status, cost, tokens, body in db.execute(
                    "select status,cost,tokens,body from requests where slot=?", (res["slot"],)
                ):
                    states[status] += 1
                    if status == "settled":
                        u = json.loads(body)
                        assert (
                            tokens == u["input_tokens"] + u["output_tokens"]
                            and cost == u["peak_cost_nanoyuan"]
                        )
                        usage.update(
                            calls=1,
                            input=u["input_tokens"],
                            output=u["output_tokens"],
                            tokens=tokens,
                            cost_nanoyuan=cost,
                        )
                allcost.update(usage)
                b = row["branches"][arm] = dict(
                    status=res["status"],
                    error=res.get("error"),
                    usage=dict(usage),
                    physical_request_states=dict(states),
                )
                if res["status"] != "closed":
                    continue
                logical = res["logical_tokens"]
                assert logical == 5000000 - item["initial_budget"] + usage["tokens"]
                d = read_json(folder / "decision.json")
                active = read_json(folder / "assigned-graph.json")
                lock = read_json(checked(read_json(folder / "candidate-lock.json")))
                proc = evaluate(folder)
                scores = {}
                receipts = {}
                for k in ("code", "delivery"):
                    g = base / (arm + "-" + k) / "receipt.json"
                    r = read_json(g)
                    assert r["instance_id"] == item["instance"] and r["kind"] == k
                    scores[k] = r.get("resolved")
                    receipts[k] = reference(g)
                y = scores["delivery"]
                metric = mechanism(folder, item, active, d, proc, lock)
                capture_index = read_json(folder / "passive-captures/capture-index.json")
                for event in capture_index["events"]:
                    cap = read_json(folder / "passive-captures" / event["site"] / "capture.json")
                    event["total_remaining_including_protected"] = (
                        5000000 - cap["prefix_tokens"] - d["osa_tokens"]
                    )
                    event["uncommitted_remaining"] = cap.get(
                        "remaining", (cap.get("capacity") or {}).get("remaining")
                    )
                b.update(
                    termination=res["termination"],
                    logical=logical,
                    osa_tokens=d["osa_tokens"],
                    seconds=res["finished"] - res["started"],
                    mechanism=metric,
                    process=proc,
                    submitted=lock["submitted"],
                    scores=scores,
                    score_receipts=receipts,
                    utility=(int(y) - logical / 50000000) if type(y) is bool else None,
                    source=[
                        reference(folder / k)
                        for k in (
                            "result.json",
                            "decision.json",
                            "assigned-graph.json",
                            "boundary.json",
                            "mechanism.json",
                            "candidate-lock.json",
                            "passive-captures/capture-index.json",
                        )
                    ],
                    captures=capture_index,
                )
            u = [row["branches"][a].get("utility") for a in ("KEEP", "OSA")]
            row["delta_U"] = round(u[1] - u[0], 9) if None not in u else None
            cases.append(row)
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        held += db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        pending = db.execute(
            "select slot from block_slots where status='pending' and slot like 'v243:%'"
        ).fetchall()
        live = db.execute(
            "select id,status from slots where status!='closed' and id like 'v243:%'"
        ).fetchall()
    metrics = {}
    for arm in ("KEEP", "OSA"):
        branches = [c["branches"][arm] for c in cases if c["branches"][arm]["status"] == "closed"]
        judged = [
            b for b in branches if b["process"]["endpoint"] in ("RESOLVED", "ACTIVE", "REOPENED")
        ]
        changed = [b for b in branches if b["mechanism"]["actual_graph_changed"]]
        ordered = [b for b in changed if b["mechanism"]["order"]]
        products = [b for b in ordered if b["mechanism"]["order_products"]]
        gaps = [
            b
            for b in branches
            if b["mechanism"]["registered_type"] == "A4"
            and b["process"]["target"] == "independent_current_review"
        ]
        metrics[arm] = dict(
            planned=len(cases),
            closed=len(branches),
            correct_code=[
                sum(b["scores"]["code"] is True for b in branches),
                sum(type(b["scores"]["code"]) is bool for b in branches),
            ],
            correct_delivery=[
                sum(b["scores"]["delivery"] is True for b in branches),
                sum(type(b["scores"]["delivery"]) is bool for b in branches),
            ],
            anomaly_resolved=[
                sum(b["process"]["endpoint"] == "RESOLVED" for b in judged),
                len(judged),
            ],
            process_unknown=len(branches) - len(judged),
            changed_realized=[
                sum(
                    b["mechanism"]["actual_graph_changed"]
                    for b in branches
                    if b["mechanism"]["validator"] == "accepted"
                    and b["mechanism"]["requested"] == "CHANGE"
                ),
                sum(
                    b["mechanism"]["validator"] == "accepted"
                    and b["mechanism"]["requested"] == "CHANGE"
                    for b in branches
                ),
            ],
            formal_order_products=[len(products), len(ordered)],
            adopted_formal_products=[
                sum(
                    any(u["kind"] == "adopt" for u in b["mechanism"]["downstream_receipts"])
                    for b in products
                ),
                len(products),
            ],
            accepted_current_independent_review=[
                sum(
                    any(
                        r["source_reference"] == b["process"]["lock"]
                        and set(b["process"]["scope"]) <= set(r["task_revisions"])
                        for r in b["process"]["reviews"]
                    )
                    for b in gaps
                ),
                len(gaps),
            ],
            explicit_reopened_packages=sum(
                len(b["mechanism"]["recorded_reopen"]) for b in branches
            ),
            duplicate_public_checks=sum(
                b["process"]["rework"]["repeated_identical_tests"] for b in branches
            ),
        )
    release = clone_function(resource_receipts, {**resource_receipts.__globals__, "RUN": RUN})(
        [r["case"] for r in cases], [], [i["configuration"] for i in specs]
    )
    study.save(
        PLAN / "results.json",
        dict(
            cases=cases,
            metrics=metrics,
            totals=dict(allcost),
            account=dict(
                cap=auth["cap_nanoyuan"], available=auth["cap_nanoyuan"] - paid - held, held=held
            ),
            active=live,
            pending=pending,
            resources=release,
            cn_updates=0,
        ),
    )


if __name__ == "__main__":
    main()
