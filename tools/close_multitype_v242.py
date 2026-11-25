"""Account for complete pairs and recruitment separately after the last registered prefix."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory_multitype_v242 import PLAN, RUN, ROOT, read_json, save
from proworksim.software_anomaly_graph_v226 import AnomalyGraph
from proworksim.software_benchmark_candidates_v054 import checked, reference


def actual_cost(db, slot):
    rows = db.execute(
        "select status,count(*),sum(tokens),sum(cost) from requests where slot=? group by status",
        (slot,),
    )
    out = dict(calls=0, tokens=0, cost_nanoyuan=0, other_request_states={})
    for state, calls, tokens, cost in rows:
        if state == "settled":
            out.update(calls=calls, tokens=tokens, cost_nanoyuan=cost)
        else:
            out["other_request_states"][state] = calls
    return out


def trace(prefix, anchor):
    obs = read_json(prefix / "observations.json")
    views = {member: AnomalyGraph(member) for member in ("member_001", "member_002")}
    actions = Counter()
    new_signals = set()
    for event in obs:
        i, o = event["ordinal"], event["outcome"]
        member = o.get("worker_id")
        if member not in views:
            continue
        graph = views[member]
        graph.observe(i, o)
        if i <= anchor:
            continue
        tool = (o.get("decision") or {}).get("action")
        if tool and (o.get("response") or {}).get("ok"):
            actions[tool] += 1
        for n in graph.nodes.values():
            if any(
                h["opportunity"] == i and h["to"] in ("OPEN", "ACTIVE", "REOPENED")
                for h in n["resolution_history"]
            ):
                new_signals.add((member, n["anomaly_id"], n["anomaly_type"]))
    return dict(
        accepted_tools=dict(actions),
        signals_before_eligibility=dict(Counter(s[2] for s in new_signals)),
    )


def resource_receipts(cases, candidates, configurations):
    import docker

    bases = [RUN / x / arm for x in cases for arm in ("KEEP", "OSA")]
    bases += [RUN / "recruitment" / x / "COMMON" for x in candidates]
    paths = [p / "actor/created.json" for p in bases]
    paths += [
        RUN / x / f"{arm}-{kind}" / "created.json"
        for x in cases
        for arm in ("KEEP", "OSA")
        for kind in ("code", "delivery")
    ]
    sockets = {
        read_json(checked(c))["scorer_request_base"]["docker_socket"] for c in configurations
    }
    (sock,) = sockets
    proofs = []
    with closing(
        docker.DockerClient(base_url="unix://" + str(Path(sock).resolve()), timeout=12)
    ) as client:
        for p in paths:
            if not p.is_file():
                continue
            cid = read_json(p)["id"]
            if not re.fullmatch(r"[0-9a-f]{64}", cid):
                raise ValueError("Invalid container identity")
            try:
                client.containers.get(cid)
                absent = False
            except docker.errors.NotFound:
                absent = True
            proofs.append(dict(receipt=reference(p), container=cid, absent=absent))
    return dict(created=len(proofs), all_absent=all(p["absent"] for p in proofs), proofs=proofs)


def main():
    recruitment = read_json(RUN / "registration-recruitment-completed.json")
    prior = read_json(RUN / "recruitment-completed.json")
    frozen = read_json(PLAN / "recruitment.json")["candidates"]
    if [r["case"] for r in recruitment] != [c["case"] + "-r2" for c in frozen]:
        raise ValueError("Incomplete candidate register")
    evidence = read_json(PLAN / "successor-evidence.json")["pairs"]
    pairs = {r["case"]: r for r in evidence}
    prefixes = []
    auth = read_json(RUN / "authority.json")
    with closing(sqlite3.connect(Path(auth["ledger"]).as_uri() + "?mode=ro", uri=True)) as db:
        for rec, c in zip(recruitment, frozen, strict=True):
            dest = RUN / "recruitment" / rec["case"] / "COMMON"
            slot = "v242:recruit:" + rec["case"] + ":COMMON"
            entry = dict(
                **rec, target=c["kind"], historical_tokens=c["prefix"], **actual_cost(db, slot)
            )
            if (dest / "result.json").is_file():
                result = read_json(dest / "result.json")
                entry["result"] = reference(dest / "result.json")
                entry["elapsed_seconds"] = result["finished"] - result["started"]
                if (dest / "progress.json").is_file():
                    progress = read_json(dest / "progress.json")
                    state = dict(
                        read_json(ROOT / c["source"] / "checkpoint/state.json")["__dict__"]
                    )
                    anchor = dict(state["runtime"]["__dict__"])["opportunities"]
                    entry.update(
                        new_opportunities=progress["opportunity"] - anchor,
                        remaining=progress["available"],
                        anchor_ordinal=anchor,
                    )
                    if result["status"] == "no_qualifying_state":
                        if (dest / "boundary.json").exists():
                            entry["stopping_condition"] = "worker_boundary"
                        elif progress["available"] < 8 * 131072:
                            entry["stopping_condition"] = "paired_opportunity_floor"
                        elif entry["new_opportunities"] >= 45:
                            entry["stopping_condition"] = "opportunity_window"
                    if (dest / "observations.json").is_file():
                        entry.update(trace(dest, anchor))
                if result["status"] == "point_ready" and rec["case"] not in pairs:
                    raise ValueError("Missing registered pair analysis")
            prefixes.append(entry)
        first_attempts = [
            dict(**r, **actual_cost(db, "v242:recruit:" + r["case"] + ":COMMON")) for r in prior
        ]
        totals = db.execute(
            "select count(*),sum(tokens),sum(cost) from requests where slot like 'v242%' and status='settled'"
        ).fetchone()
        active = db.execute(
            "select id,status from slots where id like 'v242%' and status!='closed'"
        ).fetchall()
        pending = db.execute(
            "select slot from block_slots where slot like 'v242%' and status='pending'"
        ).fetchall()
        settled = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        reserved = db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
    by_arm = Counter()
    for r in pairs.values():
        for b in r["branches"].values():
            if b["status"] == "closed":
                by_arm.update(b["usage"])
    if (
        not active
        and not pending
        and all(b["status"] == "closed" for r in pairs.values() for b in r["branches"].values())
    ):
        assert (
            sum(x["cost_nanoyuan"] for x in prefixes + first_attempts)
            + by_arm["peak_cost_nanoyuan"]
            == totals[2]
        )
    resources = resource_receipts(
        pairs,
        [r["case"] for r in first_attempts + prefixes],
        [c["task"]["configuration"] for c in frozen]
        + [
            read_json(PLAN / case / "protocol.json")["roster"][0]["configuration"] for case in pairs
        ],
    )
    save(
        PLAN / "closeout.json",
        dict(
            planned_states=dict(A1=2, A2=2, A3=1, A4=1),
            paired_by_type=dict(Counter(r["kind"] for r in pairs.values())),
            physical=dict(calls=totals[0], tokens=totals[1], cost_nanoyuan=totals[2]),
            current_slots=active,
            pending=pending,
            account=dict(
                cap_nanoyuan=auth["cap_nanoyuan"],
                settled_nanoyuan=settled,
                held_nanoyuan=held + reserved,
                available_nanoyuan=auth["cap_nanoyuan"] - settled - held - reserved,
            ),
            initial_attempts=first_attempts,
            prospective=prefixes,
            branch_usage=dict(by_arm),
            resources=resources,
            measurement=reference(PLAN / "successor-evidence.json"),
        ),
    )


if __name__ == "__main__":
    main()
