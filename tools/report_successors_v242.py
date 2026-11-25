"""Reconcile comparable evidence: exact public nodes, task-scoped completions and native adoption."""

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory_multitype_v242 import ROOT, PLAN, RUN, save
from proworksim.software_successor_evidence_v242 import evaluate
from proworksim.storage import read_json
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_context_panel_v231 import PairedLedger


def observed_actions(b):
    return [o for o in b["outcomes"] if (o.get("decision") or {}).get("action")]


def accountable(folder, item):
    res = read_json(folder / "result.json")
    if res["status"] != "closed":
        return dict(status=res["status"], error=res.get("error"))
    d = read_json(folder / "decision.json")
    active = read_json(folder / "assigned-graph.json")
    b = read_json(folder / "boundary.json")
    m = read_json(folder / "mechanism.json")
    proc = evaluate(folder)
    ops = observed_actions(b)
    appointed = d.get("first_action")
    first = ops[0] if ops else {}
    lock = read_json(checked(read_json(folder / "candidate-lock.json")))
    metrics = {}
    proof = {}
    for kind in ("code", "delivery"):
        f = folder.with_name(folder.name + "-" + kind) / "receipt.json"
        if f.exists():
            receipt = read_json(f)
            if receipt["instance_id"] != item["instance"] or receipt["kind"] != kind:
                raise ValueError("Wrong grading identity")
            metrics[kind] = receipt.get("resolved")
            proof[kind] = reference(f)
        else:
            metrics[kind] = None
    scope = item["row"]["targets"]
    obligations = {}
    for task in scope:
        prefix = item["row"]["work_status"].get(task, {})
        if item["kind"] == "A4":
            if not prefix.get("completed"):
                obligations[task + "/complete_package"] = any(
                    v["current"] and v["package"] == task and not v["reopened"]
                    for v in proc["closed_packages"]
                )
            obligations[task + "/independent_review"] = any(
                task in v["task_revisions"] and v["source_reference"] == proc["lock"]
                for v in proc["reviews"]
            )
        elif item["kind"] == "A1":
            obligations[task + "/repair_target"] = {
                "RESOLVED": True,
                "ACTIVE": False,
                "REOPENED": False,
            }.get(proc["endpoint"])
        else:
            obligations[task + "/clear_" + item["kind"]] = {
                "RESOLVED": True,
                "ACTIVE": False,
                "REOPENED": False,
            }.get(proc["endpoint"])
    chosen = active["decision"]["option"]
    op = d["menu"]["options"][chosen]["op"]
    product = None
    adopted = None
    received = None
    disposition = None
    new_assignee_acted = None
    if active["changed"]:
        assigned = d["menu"]["options"][chosen]
        new_assignee_acted = any(o["worker_id"] == assigned["assignee"] for o in ops)
        if op == "diagnosis":
            duty = m["control"]["duties"].get(assigned["task"], {})
            matches = [
                o
                for o in ops
                if o.get("response", {}).get("ok")
                and o["worker_id"] == assigned["assignee"]
                and o["decision"]["action"] == "send_message"
                and o["decision"]["arguments"].get("recipient") == duty.get("recipient")
                and o["decision"]["arguments"]
                .get("body", "")
                .startswith("DIAG " + str(duty.get("evidence")) + " ")
                and (o["response"].get("result") or {}).get("message_sequence")
                == duty.get("message_sequence")
            ]
            product = bool(matches and duty.get("status") == "handed_off")
            if product:
                matched = duty.get("recipient_disposition") or {}
                received = any(
                    o["worker_id"] == duty["recipient"]
                    and o["decision"]["action"] == "read_work_event"
                    and o["response"].get("ok")
                    and (o["response"].get("result") or {}).get("sequence")
                    == duty["message_sequence"]
                    for o in ops
                )
                if matched.get("message_sequence") == duty["message_sequence"]:
                    received |= bool(matched.get("full_exposure_request"))
                    disposition = matched.get("choice")
                adopted = disposition == "ADOPT"
        elif op == "verify":
            product = any(
                r["actor"] == assigned["assignee"] and assigned["task"] in r["task_revisions"]
                for r in proc["reviews"]
            )
            adopted = bool(
                product
                and lock["submitted"]
                and any(
                    r["actor"] == assigned["assignee"]
                    and assigned["task"] in r["task_revisions"]
                    and r["source_reference"] == proc["lock"]
                    for r in proc["reviews"]
                )
            )
        elif op == "transfer_unstarted":
            product = any(
                c["package"] == assigned["task"]
                and c["actor"] == assigned["assignee"]
                and not c["reopened"]
                for c in proc["closed_packages"]
            )
    with PairedLedger.load(RUN / "authority.json").db() as db:
        rs = db.execute(
            "select id,status,tokens,cost from requests where slot=?", (res["slot"],)
        ).fetchall()
    usage = Counter()
    for rid, status, tokens, cost in rs:
        usage[status + "_calls"] += 1
        if status != "settled":
            continue
        files = [folder / p / rid.rsplit(":", 1)[-1] / "usage.json" for p in ("api", "osa-api")]
        (f,) = [f for f in files if f.exists()]
        u = read_json(f)
        if tokens != u["total_tokens"] or cost != u["peak_cost_nanoyuan"]:
            raise ValueError("Physical charge differs")
        usage.update(
            {
                k: u[k]
                for k in ("input_tokens", "output_tokens", "total_tokens", "peak_cost_nanoyuan")
            }
        )
        usage["osa_tokens" if f.parents[1].name == "osa-api" else "worker_tokens"] += tokens
    assert usage["total_tokens"] + 5000000 - item["initial_budget"] == res["logical_tokens"]
    return dict(
        status=res["status"],
        case=item["case"],
        arm=folder.name,
        usage=dict(usage),
        source_prefix_tokens=5000000 - item["initial_budget"],
        logical=res["logical_tokens"],
        seconds=res["finished"] - res["started"],
        termination=res["termination"],
        decision=d.get("requested", "KEEP"),
        registered_anomaly=item["kind"],
        proposed_anomaly=(d.get("proposal") or {}).get("anomaly"),
        option=chosen,
        actual_operation=op,
        validator=d.get("validator"),
        reservations=d.get("resources"),
        changed=active["changed"],
        matches_intended=active["after"] == d.get("expected_graph", active["before"]),
        planned_first=appointed,
        first_actor=first.get("worker_id"),
        first_tool=(first.get("decision") or {}).get("action"),
        first_tool_accepted=(first.get("response") or {}).get("ok"),
        paid_action_received=any(o["worker_id"] == appointed["actor"] for o in ops)
        if appointed
        else None,
        product=product,
        new_assignee_acted=new_assignee_acted,
        recipient_read_documented=received,
        disposition=disposition,
        adopted=adopted,
        obligations=obligations,
        process=proc,
        submitted=lock["submitted"],
        scores=metrics,
        score_receipts=proof,
        links=[
            reference(folder / n)
            for n in (
                "boundary.json",
                "assigned-graph.json",
                "decision.json",
                "mechanism.json",
                "result.json",
                "candidate-lock.json",
                "actor/cleanup.json",
            )
        ],
    )


def main():
    archive = read_json(ROOT / "artifacts/software-benchmark-v241/paired-r1/results.json")
    old = []
    for r in archive["rows"]:
        f = next(x for x in r["sources"] if x["path"].endswith("/boundary.json"))
        old.append(
            dict(
                case=r["case"],
                arm=r["condition"],
                old=r["anomaly"],
                new=evaluate(checked(f).parent),
            )
        )
    pairs = []
    for f in sorted(PLAN.glob("*/protocol.json")):
        item = read_json(f)["roster"][0]
        folder = RUN / item["case"]
        if not (folder / "completed.json").exists():
            continue
        pairs.append(
            dict(
                case=item["case"],
                kind=item["kind"],
                instance=item["instance"],
                branches={a: accountable(folder / a, item) for a in ("KEEP", "OSA")},
            )
        )
    save(
        PLAN / "successor-evidence.json",
        dict(
            observer_revision="v242.1 independent receipt-level measurement",
            historical_replay=old,
            pairs=pairs,
            cn_updates=0,
        ),
    )


if __name__ == "__main__":
    main()
