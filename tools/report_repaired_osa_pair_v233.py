"""Reconcile both arms, their actual input, exact public test cases and official scoring."""

import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_organization_v232 as original
from run_repaired_osa_pair_v233 import PLAN, RUN, CASE, ARMS
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_organization_selector_v216 import utility
from proworksim.software_handoff_disposition_v232_5 import has_full
from proworksim.storage import atomic_write, read_json, json_bytes


def public_checks(events, cutoff, subject):
    rows = []
    for event in events:
        if event["sequence"] <= cutoff or event["kind"] != "test" or not event.get("executed"):
            continue
        evidence = event["public_execution"].get("test_evidence") or {}
        cases = [
            r["outcome"]
            for s in evidence.get("sessions", [])
            if s.get("root") is True or s.get("depth") == 0
            for r in s.get("test_reports", [])
            if r["nodeid"] == subject and r["phase"] == "call"
        ]
        rows.append(
            {
                "event": event["sequence"],
                "member": event["actor_id"],
                "source_reference": event["source_reference"],
                "counts": event["public_execution"]["counts"],
                "target_call_outcomes": cases,
                "partial_report": evidence.get("partial"),
            }
        )
    return rows


def next_sites(balance):
    inventory = read_json(
        original.ROOT / "artifacts/software-benchmark-v232/first-pair-r1/engineering-gate.json"
    )["checkpoint_inventory_v227_v229"]
    sources = {
        "astropy__astropy-14182": "runs/software-benchmark-v228/supplement-r1/astropy-evidence-r2-launch2/W1/control-1/options.json",
        "pytest-dev__pytest-7432": "runs/software-benchmark-v228/control-r1/task-05/W1/control-1/options.json",
        "sympy__sympy-19954": "runs/software-benchmark-v229/dev1-balance90-recovery-r1/task-21/PREFIX/candidate-bank.json",
        "django__django-15916": "runs/software-benchmark-v229/dev1-r1/task-01/PREFIX/candidate-bank.json",
    }
    rows = []
    for checkpoint, state in inventory.items():
        if state["case"] not in sources:
            continue
        source = sources[state["case"]]
        raw = read_json(original.ROOT / source)
        menu = raw.get("menu", raw)
        assert menu["subject"] == state["subject"] and menu["anomaly"] == state["type"]
        worst = state["remaining"] * 2 * 8000
        rows.append(
            dict(
                case=state["case"],
                checkpoint=checkpoint,
                anomaly=menu["anomaly"],
                options=menu["options"],
                source=source,
                remaining_per_arm=state["remaining"],
                full_pair_reservation_nanoyuan=worst,
                additional_to_reserve_nanoyuan=max(0, worst - balance),
            )
        )
    return rows


def run(*, namespace="v233", include_inventory=True):
    read_json(RUN / "completed.json")
    p = read_json(PLAN / "protocol.json")
    auth = read_json(RUN / "authority.json")
    folder = RUN / CASE
    analyze = clone_function(original.scan, {**original.scan.__globals__, "PLAN": PLAN})
    records = {}
    with sqlite3.connect("file:" + auth["ledger"] + "?mode=ro", uri=True) as db:
        balance = (
            auth["cap_nanoyuan"]
            - db.execute(
                "select sum(cost) from requests where status='settled' and rowid <= (select max(rowid) from requests where slot like ?)",
                (namespace + ":%",),
            ).fetchone()[0]
        )
        reserved = db.execute(
            "select count(*) from requests where slot like ? and status='reserved'",
            (namespace + ":%",),
        ).fetchone()[0]
        for arm in ARMS:
            dest = folder / arm
            rc = read_json(dest / "result.json")
            if rc["status"] != "closed":
                records[arm] = rc
                continue
            row = analyze(dest, db, CASE, arm)
            state = read_json(dest / "prepared/world/control/state.json")
            graph = read_json(dest / "assigned-graph.json")
            decision = read_json(dest / "decision.json")
            observed = decision["anomaly"]
            events = state["software_events"]
            duties = row["effective_duties"] or {}
            for duty in duties.values():
                disposition = duty.get("recipient_disposition") or {}
                if disposition.get("full_exposure_request"):
                    event = next(e for e in events if e["sequence"] == duty["message_sequence"])
                    requests = (
                        read_json(path)["payload"] for path in (dest / "api").glob("*/request.json")
                    )
                    (shown,) = [
                        q
                        for q in requests
                        if q["request_id"] == disposition["full_exposure_request"]
                    ]
                    if shown["member_id"] != duty["recipient"] or not has_full(
                        shown["wire"], event
                    ):
                        raise ValueError("Recipient decision lacks full addressed diagnosis")
            tools = []
            with (dest / "runtime/experience.jsonl").open() as f:
                for line in f:
                    e = json.loads(line)
                    if e["kind"] == "tool_call":
                        d = e["payload"]
                        r = d["response"]
                        tools.append(
                            {
                                "opportunity": d["opportunity_id"],
                                "member": e["worker_id"],
                                "tool": d["action"],
                                "path": d["arguments"].get("path"),
                                "target": d["arguments"].get("selection"),
                                "event_read": d["arguments"].get("sequence")
                                if d["action"] == "read_work_event"
                                else None,
                                "message_sequence": (r.get("result") or {}).get("message_sequence"),
                                "accepted": r["ok"],
                                "reason": ((r.get("error") or {}).get("rejection") or {}).get(
                                    "code"
                                ),
                            }
                        )
            official_code = read_json(folder.joinpath(arm + "-code", "receipt.json"))
            official = official_code.get("official_result")
            failures = None
            if official and official_code["status"] == "official_report":
                task, report = official
                failures = report[task]["tests_status"]["FAIL_TO_PASS"]["failure"]
            delivery = row["official"]["delivery"]
            value = (
                utility(delivery["resolved"], rc["logical_tokens"])
                if delivery["status"] in ("official_report", "no_legal_delivery")
                and type(delivery["resolved"]) is bool
                else None
            )
            records[arm] = dict(
                status=rc["status"],
                checkpoint=rc["checkpoint"],
                initial_budget=rc["available_at_start"],
                graph_before=graph["before"],
                base_hash=decision["menu"]["base_sha256"],
                menu=row["menu"],
                option=rc["option"],
                graph_changed=graph["changed"],
                decision_source=decision["source"],
                proposal=decision["proposal"],
                validator=decision["validator"],
                controller_tokens=decision["osa_tokens"],
                request_roles=row["requests_by_role"],
                counts=row["execution"],
                tools=tools,
                grants=row["grants"],
                duties=duties,
                anomaly=row["anomaly_endpoint"],
                public_subject=observed["subject"],
                public_checks=public_checks(events, graph["after_event"], observed["subject"]),
                official=row["official"],
                failed_official_targets=failures,
                termination=rc["termination"],
                use=row["provider_usage"],
                logical_tokens=rc["logical_tokens"],
                utility=value,
                observer_errors=row["observer_errors"],
                cleanup=row["cleanup"],
            )
    paired = all(records[a]["status"] == "closed" for a in ARMS)
    difference = None
    if paired:
        k, o = [records[a] for a in ARMS]
        if (
            k["checkpoint"] != o["checkpoint"]
            or k["checkpoint"] != p["checkpoint"]
            or k["graph_before"] != o["graph_before"]
            or k["initial_budget"] != o["initial_budget"]
            or k["menu"] != o["menu"]
        ):
            raise ValueError("Unmatched decision boundary")
        if (
            k["decision_source"] != "fixed_keep"
            or o["decision_source"] != "independent_osa"
            or k["controller_tokens"] != 0
            or o["controller_tokens"] <= 0
        ):
            raise ValueError("Incorrect policy dispatch")
        if o["graph_changed"] and all(r["utility"] is not None for r in (o, k)):
            difference = o["utility"] - k["utility"]
    out = dict(
        case=CASE,
        arms=records,
        realized_utility_difference=difference,
        CN_updates=0,
        independent_sites=next_sites(balance) if include_inventory else [],
        distinct_checkpoints=int(paired),
        reserved_requests=reserved,
        balance_nanoyuan=balance,
    )
    atomic_write(PLAN / "results.json", json_bytes(out))


if __name__ == "__main__":
    run()
