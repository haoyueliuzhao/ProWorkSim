"""Reconcile closed branches, official endpoints, actual billing, and native handoff receipts."""

from pathlib import Path
import sys
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_three_graph_worker_v241 import (
    ROOT,
    PLAN,
    RUN,
    ARMS,
    PairedLedger,
    read_json,
    save,
    reference,
    checked,
)

DIAGNOSTIC_TOOLS = {
    "search_repository",
    "search_file",
    "read_file",
    "read_test_result",
    "run_tests",
    "run_patch_review_tests",
}


def actions(boundary):
    records = []
    for step in boundary["outcomes"]:
        d = step.get("decision") or {}
        tool = d.get("action")
        if not tool:
            continue
        res = step.get("response") or {}
        v = res.get("result") or {}
        args = d.get("arguments", {})
        numbers = [
            v.get("event_sequence"),
            (v.get("report_event") or {}).get("sequence"),
            v.get("read_event_sequence"),
            v.get("message_sequence"),
        ]
        records.append(
            dict(
                worker=step["worker_id"],
                tool=tool,
                ok=res.get("ok"),
                error=str(res.get("error") or "")[:230],
                arguments=args,
                event_ids=[n for n in numbers if type(n) is int],
                executed=v.get("executed"),
                passed=v.get("passed"),
                version=v.get("source_reference"),
            )
        )
    return records


def branch(item, arm, folder, db):
    r = read_json(folder / "result.json")
    slot = r["slot"]
    if r["status"] != "closed":
        return dict(status=r["status"], error=r.get("error"))
    if r["checkpoint"] != item["checkpoint"] or r["available_at_start"] != item["initial_budget"]:
        raise ValueError("Wrong branch prefix")
    b = read_json(folder / "boundary.json")
    m = read_json(folder / "mechanism.json")
    act = read_json(folder / "assigned-graph.json")
    dec = read_json(folder / "decision.json")
    lock = read_json(checked(read_json(folder / "candidate-lock.json")))
    trace = actions(b)
    diagnostic = arm == "OSA" and item["option"] != "K"
    messages = [a for a in trace if a["ok"] and a["tool"] == "send_message"]
    duty = m["control"]["duties"].get(item["first_action"]["package"], {}) if diagnostic else {}
    diagnoses = []
    for i, a in enumerate(trace):
        if a not in messages:
            continue
        args = a["arguments"]
        body = args.get("body", "")
        fields = body.split(maxsplit=2)
        if len(fields) != 3 or fields[0] != "DIAG" or not fields[1].isdigit():
            continue
        seq = int(fields[1])
        links = [
            z for z in trace[:i] if z["ok"] and z["worker"] == a["worker"] and seq in z["event_ids"]
        ]
        diagnoses.append(
            dict(
                sender=a["worker"],
                recipient=args.get("recipient"),
                task=args.get("task_id"),
                message_events=a["event_ids"],
                evidence=seq,
                linked_tools=[z["tool"] for z in links],
                body=body,
                native_handoff=duty.get("status") == "handed_off"
                and duty.get("evidence") == seq
                and duty.get("message_sequence") in a["event_ids"],
            )
        )
    public = [
        dict(
            worker=a["worker"],
            passed=a["passed"],
            executed=a["executed"],
            version=a["version"],
            selection=a["arguments"].get("selection"),
        )
        for a in trace
        if a["tool"] in ("run_tests", "run_patch_review_tests") and a["ok"]
    ]
    scores = {}
    for kind in ("code", "delivery"):
        f = folder.with_name(arm + "-" + kind) / "receipt.json"
        s = read_json(f)
        if s.get("instance_id") != item["instance"] or s.get("kind") != kind:
            raise ValueError("Wrong score receipt")
        scores[kind] = dict(
            status=s.get("status"),
            resolved=s.get("resolved"),
            receipt=reference(f),
            cleanup_errors=s.get("cleanup_errors", []),
        )
        if s.get("status") == "official_report":
            report = s["official_result"][1][item["instance"]]
            scores[kind]["tests"] = {
                k: {"passed": len(v["success"]), "failed": len(v["failure"])}
                for k, v in report["tests_status"].items()
            }
            scores[kind]["patch_applied"] = report["patch_successfully_applied"]
            scores[kind]["infra_failure"] = report.get("infra_failure", False)
        patch = f.parent / "prediction.patch"
        if patch.is_file():
            scores[kind]["changed_paths"] = [
                line.split(" b/", 1)[-1]
                for line in patch.read_text(errors="replace").splitlines()
                if line.startswith("diff --git ")
            ]
    counts = Counter()
    for rid, status, tokens, cost, body in db.execute(
        "select id,status,tokens,cost,body from requests where slot=?", (slot,)
    ):
        counts[status + "_requests"] += 1
        if status != "settled":
            continue
        api = folder / "api" / rid.rsplit(":", 1)[-1]
        u = read_json(api / "usage.json")
        if u["total_tokens"] != tokens or u["peak_cost_nanoyuan"] != cost:
            raise ValueError("Unreconciled model receipt")
        counts.update(
            {
                k: u[k]
                for k in (
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "cache_hit_tokens",
                    "cache_miss_tokens",
                    "peak_cost_nanoyuan",
                )
            }
        )
    if (
        sum([5000000 - item["initial_budget"], counts["total_tokens"], dec["osa_tokens"]])
        != r["logical_tokens"]
    ):
        raise ValueError("Worker/prefix/OSA token discrepancy")
    first = trace[0] if trace else {}
    matching = [
        z
        for z in diagnoses
        if z["native_handoff"]
        and z["sender"] == item["first_action"]["actor"]
        and z["recipient"] == duty.get("recipient")
    ]
    return dict(
        status=r["status"],
        condition=arm,
        checkpoint=r["checkpoint"],
        logical_tokens=r["logical_tokens"],
        prior_prefix=5000000 - item["initial_budget"],
        archived_controller_tokens=dec["osa_tokens"],
        costs=dict(counts),
        seconds=r["finished"] - r["started"],
        termination=r["termination"],
        scores=scores,
        submitted=lock["submitted"],
        observer_errors=r["observer_errors"],
        anomaly=m["endpoint"],
        subject=m["subject"],
        public_tests=public,
        changed=act["changed"],
        activated_option=act["decision"]["option"],
        matches_intended_graph=act["after"] == dec.get("expected_graph", act["before"]),
        first_action=first,
        first_actor_matches=(first.get("worker") == item["first_action"]["actor"])
        if diagnostic
        else None,
        immediate_investigation_accepted=bool(
            first.get("worker") == item["first_action"]["actor"]
            and first.get("ok")
            and first.get("tool") in DIAGNOSTIC_TOOLS
            and first.get("executed") is not False
        )
        if diagnostic
        else None,
        handoff_present=bool(matching) if diagnostic else None,
        diagnoses=diagnoses,
        recipient_disposition=duty.get("recipient_disposition"),
        sender_decisions=[x.get("choice") for x in duty.get("sender_decisions", [])],
        actor_cleanup=read_json(folder / "actor/cleanup.json"),
        sources=[
            reference(folder / name)
            for name in (
                "result.json",
                "decision.json",
                "assigned-graph.json",
                "boundary.json",
                "mechanism.json",
                "candidate-lock.json",
            )
        ],
    )


def main():
    spec = read_json(PLAN / "protocol.json")
    meter = PairedLedger.load(RUN / "authority.json")
    rows = []
    with meter.db() as db:
        for item in spec["roster"]:
            for arm in ARMS:
                root = RUN
                if item["id"] == "q03":
                    root = RUN / ("reason-compat-r1" if arm == "OSA" else "observer-compat-r1")
                rows.append(
                    dict(case=item["case"], **branch(item, arm, root / item["case"] / arm, db))
                )
        spent = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        pending = db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
    save(
        PLAN / "results.json",
        dict(
            rows=rows,
            total_cost_nanoyuan=sum(r["costs"]["peak_cost_nanoyuan"] for r in rows if "costs" in r),
            balance_after_settled_nanoyuan=meter.cap - spent,
            account_held_nanoyuan=held,
            account_pending_nanoyuan=pending,
            zero_worker_call_startup_attempts=3,
            cn_updates=0,
        ),
    )


if __name__ == "__main__":
    main()
