"""Reconcile the real paired Worker experiment and the separate short classification control."""

from pathlib import Path
from collections import Counter
from contextlib import closing
import sqlite3
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_review_handoff_v243_1 as e
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.storage import read_json


def measure(folder, item, arm, db):
    res = read_json(folder / "result.json")
    rows = db.execute("select status,cost,tokens,body from requests where slot=?", (res["slot"],))
    paid = Counter()
    states = Counter()
    for s, c, t, body in rows:
        states[s] += 1
        if s == "settled":
            u = json.loads(body)
            assert c == u["peak_cost_nanoyuan"] and t == u["input_tokens"] + u["output_tokens"]
            paid.update(
                calls=1, input=u["input_tokens"], output=u["output_tokens"], tokens=t, nanoyuan=c
            )
    result = dict(
        status=res["status"], error=res.get("error"), paid=dict(paid), request_states=dict(states)
    )
    if res["status"] != "closed":
        return result
    decision = read_json(folder / "decision.json")
    graph = read_json(folder / "assigned-graph.json")
    oldgraph = read_json(e.event.RUN / e.CASE / "OSA/assigned-graph.json")
    assert graph["after"] == oldgraph["after"] and decision["requested"] == "CHANGE"
    original = next(iter(graph["after"]["execution_orders"].values()))
    assert (
        res["logical_tokens"]
        == 5000000 - item["initial_budget"] + paid["tokens"] + decision["osa_tokens"]
    )
    valid = original["artifact"]
    version = original["version"]
    task = original["task"]
    actor = original["actor"]
    owner = original["recipient"]
    reviews = []
    reopens = []
    tested = []
    stale = []
    news = []
    messages = []
    reads = []
    for i, o in enumerate(
        read_json(folder / "boundary.json")["outcomes"], decision["original_ordinal"] + 1
    ):
        a = o.get("decision") or {}
        args = a.get("arguments") or {}
        r = o.get("response") or {}
        v = r.get("result") or {}
        tool = a.get("action")
        who = o.get("worker_id")
        patch = args.get("patch_id") or v.get("patch_id")
        if not r.get("ok"):
            reason = ((r.get("error") or {}).get("rejection") or {}).get("code")
            if (
                reason == "stale_work_revision"
                and who == actor
                and tool in ("open_patch_review", "run_patch_review_tests", "org_review_patch")
            ):
                stale.append(dict(i=i, patch=patch, tool=tool, command=r.get("command_id")))
            continue
        ref = v.get("source_reference") or (v.get("identity") or {}).get("source_reference")
        if tool == "reopen_work" and who == owner and args.get("task_id") == task:
            reopens.append(dict(i=i, old=valid, epoch=v.get("work_epoch")))
            valid = version = None
        if tool == "complete_work" and who == owner and args.get("task_id") == task:
            valid, version = patch, ref
            news.append(dict(i=i, patch=valid, version=ref))
        if tool == "run_patch_review_tests" and who == actor and v.get("executed"):
            tested.append(dict(i=i, patch=patch, version=ref, passed=v.get("passed")))
        if (
            tool == "org_review_patch"
            and who == actor
            and v.get("author") == owner
            and task in v.get("task_revisions", {})
        ):
            reviews.append(
                dict(
                    i=i,
                    patch=patch,
                    version=ref,
                    verdict=v["decision"],
                    event=v.get("event_sequence"),
                    scoped_current=(patch, ref) == (valid, version),
                    command=r.get("command_id"),
                )
            )
        if tool == "send_message" and who == actor and args.get("recipient") == owner:
            messages.append(dict(i=i, event=v.get("message_sequence"), text=args["body"][:250]))
        if tool == "read_work_event" and who == owner:
            reads.append(dict(i=i, event=v.get("sequence"), kind=v.get("kind")))
    lock = read_json(checked(read_json(folder / "candidate-lock.json")))
    finalref = read_json(checked(lock["terminal_code"]))["source_reference"]
    scores = {}
    for kind in ("code", "delivery"):
        p = folder.with_name(arm + "-" + kind) / "receipt.json"
        r = read_json(p)
        assert r["instance_id"] == item["instance"] and r["kind"] == kind
        s = dict(resolved=r.get("resolved"), status=r["status"], source=reference(p))
        if r.get("official_result"):
            k, report = r["official_result"]
            s["tests"] = report[k]["tests_status"]
        scores[kind] = s
    timeline = folder / "telemetry/review-handoff.json"
    result.update(
        original_verdict=any(
            q["scoped_current"]
            and q["patch"] == original["artifact"]
            and q["version"] == original["version"]
            for q in reviews
        ),
        successor_verdict=any(
            q["scoped_current"] and q["patch"] != original["artifact"] for q in reviews
        ),
        final_accepted=any(
            q["scoped_current"] and q["version"] == finalref and q["verdict"] == "accept"
            for q in reviews
        )
        and next(
            (q["verdict"] == "accept" for q in reversed(reviews) if q["version"] == finalref), False
        ),
        original_osa_tokens=decision["osa_tokens"],
        logical=res["logical_tokens"],
        seconds=res["finished"] - res["started"],
        termination=res["termination"],
        final_version=finalref,
        submitted=lock["submitted"],
        tests=tested,
        reopens=reopens,
        new_candidates=news,
        reviews=reviews,
        stale=stale,
        messages=messages,
        reads=reads,
        scores=scores,
        notices=read_json(timeline) if timeline.exists() else [],
        evidence=[
            reference(folder / f)
            for f in (
                "decision.json",
                "assigned-graph.json",
                "boundary.json",
                "result.json",
                "candidate-lock.json",
            )
        ],
    )
    if type(scores["delivery"]["resolved"]) is bool:
        result["utility"] = int(scores["delivery"]["resolved"]) - res["logical_tokens"] / 50000000
    return result


def resources(root, sock):
    import docker

    proofs = []
    with closing(
        docker.DockerClient(base_url="unix://" + str(Path(sock).resolve()), timeout=12)
    ) as c:
        for arm in e.ARMS:
            for p in [
                root / arm / "actor/created.json",
                *(root / (arm + "-" + k) / "created.json" for k in ("code", "delivery")),
            ]:
                if not p.is_file():
                    continue
                cid = read_json(p)["id"]
                if not re.fullmatch("[a-f0-9]{64}", cid):
                    raise ValueError("Invalid creation receipt")
                try:
                    c.containers.get(cid)
                    absent = False
                except docker.errors.NotFound:
                    absent = True
                proofs.append(dict(receipt=reference(p), container=cid, absent=absent))
    return dict(created=len(proofs), all_absent=all(p["absent"] for p in proofs), proofs=proofs)


def classification():
    trial = read_json(e.PLAN / "classification/results.json")
    result = {}
    for arm in ("KEEP", "OSA"):
        raw_labels = {}
        for r in trial[arm]["rows"]:
            label = None
            if r["receipts"]:
                body = read_json(checked(r["receipts"][0]))
                calls = body["choices"][0]["message"].get("tool_calls") or []
                if len(calls) == 1:
                    try:
                        label = json.loads(calls[0]["function"]["arguments"]).get("anomaly")
                    except (ValueError, AttributeError):
                        pass
            raw_labels[r["site"]] = label
        result[arm] = dict(
            raw_labels=raw_labels,
            raw_correct=sum(raw_labels[r["site"]] == r["expected"] for r in trial[arm]["rows"]),
            complete_valid=trial[arm]["valid"],
            valid_and_correct=sum(
                r["valid"] and r["label"] == r["expected"] for r in trial[arm]["rows"]
            ),
        )
    result["admitted"] = trial["admitted"]
    return result


def main():
    root = e.RUN / e.CASE
    read_json(root / "completed.json")
    item = read_json(e.PLAN / e.CASE / "protocol.json")["roster"][0]
    auth = read_json(e.RUN / "authority.json")
    with closing(sqlite3.connect(Path(auth["ledger"]).as_uri() + "?mode=ro", uri=True)) as db:
        by_arm = {a: measure(root / a, item, a, db) for a in e.ARMS}
        label = db.execute(
            "select count(*),sum(tokens),sum(cost) from requests where status='settled' and slot like 'v243.1-label:%'"
        ).fetchone()
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = (
            db.execute("select coalesce(sum(hold),0) from slots where status!='closed'").fetchone()[
                0
            ]
            + db.execute(
                "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
            ).fetchone()[0]
        )
        pending = db.execute(
            "select slot from block_slots where slot like 'v243.1-%' and status='pending'"
        ).fetchall()
        live = db.execute(
            "select id,status from slots where id like 'v243.1-%' and status!='closed'"
        ).fetchall()
    cfg = read_json(checked(item["configuration"]))
    physical = Counter()
    for b in by_arm.values():
        physical.update(b["paid"])
    e.event.save(
        e.PLAN / "results.json",
        dict(
            scope="same-checkpoint implementation regression",
            case=e.CASE,
            branches=by_arm,
            physical_worker=dict(physical),
            classification=dict(
                calls=label[0], tokens=label[1], nanoyuan=label[2], diagnostics=classification()
            ),
            delta_U=round(by_arm["FIX"]["utility"] - by_arm["BASE"]["utility"], 9)
            if all("utility" in b for b in by_arm.values())
            else None,
            all_new_cost_nanoyuan=physical["nanoyuan"] + label[2],
            account=dict(
                cap=auth["cap_nanoyuan"], held=held, available=auth["cap_nanoyuan"] - paid - held
            ),
            resources=resources(root, cfg["scorer_request_base"]["docker_socket"]),
            pending=pending,
            live=live,
        ),
    )


if __name__ == "__main__":
    main()
