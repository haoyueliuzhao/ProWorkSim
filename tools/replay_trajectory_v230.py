"""Index frozen episodes, physical responses and official score receipts by native IDs."""

import json
from collections import Counter
from pathlib import Path

from proworksim.software_trajectory_v230 import Trajectory
from proworksim.storage import read_json, json_bytes, digest, atomic_write

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/software-benchmark-v230/replay-r1"
REPORT = ROOT / "artifacts/software-benchmark-v230/engineering-r1"


def rel(path):
    return str(path.relative_to(ROOT))


def replay(case, branch, archives):
    branch_id = rel(branch)
    trace = Trajectory(
        RUN / "linked-traces" / case / (digest(branch_id.encode()) + ".sqlite"),
        case,
        branch_id,
    )
    start = trace.event("episode", branch_id, layer=1, ref=branch_id)
    connections = {}
    for name in (
        "checkpoint-proof",
        "restore",
        "common-state",
        "candidate-bank",
        "assigned-graph",
        "control-1/activation",
        "control-2/activation",
        "final-organization",
        "boundary",
        "result",
        "candidate-lock",
    ):
        path = branch / (name + ".json")
        if path.exists():
            data = read_json(path)
            connections[name] = trace.event(
                name,
                name,
                layer=4 if "graph" in name or "activation" in name else 1,
                parent=connections.get("restore", start),
                ref=rel(path),
                graph=data.get("version") if type(data.get("version")) is int else None,
                result=data.get("status"),
                details={
                    "sha256": digest(path.read_bytes()),
                    "checkpoint": data.get("checkpoint_identity", data.get("checkpoint")),
                },
            )
    activation_paths = [
        p
        for p in [branch / "assigned-graph.json", *sorted(branch.glob("control-*/activation.json"))]
        if p.exists()
    ]
    versions = [read_json(p) for p in activation_paths]
    counts = Counter()
    actors = {}
    calls, provider, tools, links, world_actions, opps, turns = {}, {}, {}, {}, {}, {}, {}
    source = branch / "runtime/experience.jsonl"
    summary_receipts = []
    evidence = []
    responses = {}
    sdk_results = {}
    rejected = 0
    intent_counts = Counter()
    if source.exists():
        with source.open() as file:
            for n, line in enumerate(file, 1):
                row = json.loads(line)
                kind = row["kind"]
                d = row["payload"]
                agent = row.get("worker_id")
                if not isinstance(d, dict):
                    continue
                op = d.get("opportunity_id")
                call = d.get("call_id", d.get("model_call_id"))
                ref = rel(source) + "#L" + str(n)
                if kind == "organization_work_opportunity_v049":
                    version = next(
                        (
                            v["version"]
                            for v in reversed(versions)
                            if v["after_event"] <= d["world_event_sequence"]
                        ),
                        None,
                    )
                    if d["phase"] == "before":
                        opps[op] = version
                        turns[op] = {
                            "ordinal": d["opportunity_ordinal"],
                            "actor": agent,
                            "available": d["team_budget"]["available_tokens"],
                            "availability": d["availability"],
                            "physical_agent_requests": 0,
                        }
                    parent = (
                        (
                            connections.get("assigned-graph")
                            or connections.get("control-1/activation")
                            or start
                        )
                        if version
                        else start
                    )
                    trace.event(
                        "opportunity-" + d["phase"],
                        op,
                        layer=2,
                        parent=parent
                        if d["phase"] == "before"
                        else trace.key("opportunity-before", op),
                        agent=agent,
                        opportunity=op,
                        graph=version,
                        ref=ref,
                        result=d.get("outcome_status"),
                    )
                    if d["phase"] == "after":
                        turns[op]["outcome"] = d.get("outcome_status")
                elif kind == "model_call":
                    calls[call] = op
                elif kind == "model_response":
                    provider[d["response"]["id"]] = (call, op, agent)
                elif kind == "history_summary_usage_v110":
                    summary_receipts.append((read_json(Path(d["receipt"]["path"])), agent))
                elif kind == "tool_call":
                    tid = d["model_tool_call_id"]
                    key = (call, tid)
                    if key in tools:
                        raise ValueError("Duplicate tool receipt")
                    rejected += not bool(d["response"]["ok"])
                    tools[key] = (d["request_key"], d["response"].get("action_id"))
                    eid = trace.event(
                        "tool",
                        list(key),
                        layer=3,
                        parent=trace.key("logical", call),
                        agent=agent,
                        request=call,
                        opportunity=op,
                        tool=tid,
                        graph=opps.get(op),
                        ref=ref,
                        result=d["response"]["ok"],
                        work=d["arguments"].get("task_id"),
                        details={
                            "action": d["action"],
                            "action_id": d["response"].get("action_id"),
                        },
                    )
                    if d["response"].get("action_id"):
                        world_actions[d["response"]["action_id"]] = eid
                elif kind == "model_tool_result":
                    key = (d["call_id"], d.get("model_tool_call_id"))
                    sdk_results[key] = {"ref": ref, "ok": (d.get("world_response") or {}).get("ok")}
                elif kind == "model_action_link":
                    links[(call, d["model_tool_call_id"])] = (
                        d["request_key"],
                        d["world_action_id"],
                    )
            if tools != links:
                raise ValueError("Native action link mismatch")
            if (branch / "boundary.json").exists():
                native = read_json(branch / "boundary.json")["outcomes"]
                if len(native) != len(turns):
                    raise ValueError("Native opportunity denominator mismatch")
                for outcome, (op, turn) in zip(native, turns.items()):
                    if (outcome["worker_id"], outcome["status"]) != (
                        turn["actor"],
                        turn["outcome"],
                    ):
                        raise ValueError("Boundary and native dispatch disagree")
    for call, op in calls.items():
        trace.event(
            "logical",
            call,
            layer=2,
            parent=trace.key("opportunity-before", op),
            opportunity=op,
            graph=opps[op],
            request=call,
        )
    for usage, agent in summary_receipts:
        parent = usage["parent_call_id"]
        provider[usage["response_id"]] = (parent, calls[parent], agent)
    for archive in archives:
        for row in archive["rows"]:
            rid = row["physical_id"]
            id_ = row["provider_id"]
            ref = row["evidence"]
            role = row["role"]
            if role != "osa":
                call, op, member = provider.pop(id_)
                if member != row["actor"]:
                    raise ValueError("Conflicting actor")
                parent = trace.key("logical", call)
                if role == "worker":
                    turns[op]["physical_agent_requests"] += 1
                    for choice in read_json((ROOT / ref).with_name("response.json"))["choices"]:
                        for requested in choice["message"].get("tool_calls") or []:
                            key = (call, requested["id"])
                            if key in responses:
                                raise ValueError("Duplicate native tool intention")
                            responses[key] = requested["function"]["name"]
                            intent_counts["intents"] += 1
                            if key not in tools:
                                intent_counts["sdk_or_pre_execution"] += 1
                                trace.event(
                                    "intent-without-world-receipt",
                                    list(key),
                                    layer=2,
                                    parent=trace.key("physical", rid),
                                    agent=member,
                                    opportunity=op,
                                    graph=opps.get(op),
                                    tool=key[1],
                                    request=rid,
                                    result="no_world_tool_receipt",
                                    ref=str(Path(ref).with_name("response.json")),
                                    details={
                                        "tool": responses[key],
                                        "sdk_receipt": sdk_results.get(key),
                                    },
                                )
            else:
                op = None
                parent = start
            p = trace.event(
                "physical",
                rid,
                layer=2,
                parent=parent,
                agent=row["actor"],
                request=rid,
                opportunity=op,
                graph=opps.get(op),
                ref=ref,
                timestamp=row["time"],
                details={"provider_response_id": id_, "role": role},
            )
            trace.event(
                "usage",
                rid,
                layer=5,
                parent=p,
                agent=row["actor"],
                request=rid,
                opportunity=op,
                ref=ref.replace("/request.json", "/usage.json"),
                details=row["usage"],
            )
            counts["physical"] += 1
            actors[row["actor"]] = actors.get(row["actor"], 0) + 1
    for key, (request_key, aid) in tools.items():
        trace.event(
            "intent-receipt-link",
            list(key),
            layer=3,
            parent=trace.key("tool", list(key)),
            request=key[0],
            tool=key[1],
            details={
                "sdk_request_key": request_key,
                "world_action_id": aid,
                "intent": responses[key],
            },
        )
    if provider:
        raise ValueError("Unmatched native response")
    if not tools.keys() <= responses.keys():
        raise ValueError("Tool receipt without a matching provider intent")
    scores = {}
    for endpoint in ("code", "delivery"):
        p = branch.with_name(branch.name + "-" + endpoint) / "receipt.json"
        if p.exists():
            data = read_json(p)
            scores[endpoint] = data["resolved"]
            trace.event(
                "score",
                endpoint,
                layer=5,
                parent=connections["candidate-lock"],
                ref=rel(p),
                result=data["resolved"],
                details={"status": data["status"]},
            )
    state = branch / "prepared/world/control/state.json"
    if state.exists():
        for e in read_json(state)["software_events"]:
            aid = e.get("action_id")
            if aid in world_actions:
                trace.event(
                    "world-event",
                    e["sequence"],
                    layer=4,
                    parent=world_actions[aid],
                    agent=e["actor_id"],
                    ref=rel(state) + "#/software_events/" + str(e["sequence"] - 1),
                    details={"native_action": aid, "kind": e["kind"], "sequence": e["sequence"]},
                )
                counts["world_events_linked"] += 1
            else:
                trace.event(
                    "world-external",
                    e["sequence"],
                    layer=4,
                    agent=e["actor_id"],
                    ref=rel(state) + "#/software_events/" + str(e["sequence"] - 1),
                    result="preserved_setup_or_inherited",
                    details={
                        "native_action": aid,
                        "operation_id": e.get("operation_id"),
                        "kind": e["kind"],
                    },
                )
                counts["other_world_events_preserved"] += 1
    counts.update(intent_counts)
    counts["tool_rejections"] = rejected
    counts.update(
        opportunities=len(turns),
        tool_receipts=len(tools),
        action_links=len(links),
        activated_versions=len(versions),
    )
    if case == "Sphinx-9591" and branch.name == "CHANGE":
        evidence = list(turns.values())
    return {
        "branch": branch_id,
        "counts": counts,
        "scores": scores,
        "versions": [v["version"] for v in versions],
        "actor_physical": actors,
        "focus_opportunities": evidence,
        "trace": rel(trace.path),
    }


def main():
    branches = {}
    for f in sorted((RUN / "accounting").glob("*.json")):
        a = read_json(f)
        if not a["case"]:
            continue
        b = (ROOT / a["scope"]).parent
        if b.name in ("draft", "control-1", "control-2"):
            b = b.parent
        branches.setdefault((a["case"], b), []).append(a)
    rows = [replay(k, b, archives) for (k, b), archives in sorted(branches.items())]
    bindings = {}
    for row in rows:
        path = ROOT / row["branch"]
        if (path / "checkpoint-proof.json").exists():
            cp = read_json(path / "checkpoint-proof.json")["identity"]
            bindings[cp] = row["branch"]
    for row in rows:
        path = ROOT / row["branch"]
        for name, field in [("restore", "checkpoint_identity"), ("candidate-bank", "checkpoint")]:
            if (path / (name + ".json")).exists():
                cp = read_json(path / (name + ".json"))[field]
                row["source_checkpoint"] = cp
                row["source_prefix"] = bindings[cp]
                trace = Trajectory(
                    ROOT / row["trace"],
                    next(case for case, b in branches if b == path),
                    row["branch"],
                )
                reftrace = Trajectory(
                    ROOT / next(r["trace"] for r in rows if r["branch"] == bindings[cp]),
                    trace.episode,
                    bindings[cp],
                )
                trace.event(
                    "checkpoint-lineage",
                    name,
                    layer=1,
                    parent=reftrace.key("checkpoint-proof", "checkpoint-proof"),
                    ref=rel(path / (name + ".json")),
                    details={"identity": cp, "prefix": bindings[cp]},
                )
        if (path / "assigned-graph.json").exists():
            bank = read_json(path.parent / "PREFIX/candidate-bank.json")
            if bank["checkpoint"] != row["source_checkpoint"]:
                raise ValueError("Wrong controller checkpoint")
            row["controller_proposal"] = rel(path.parent / "PREFIX/candidate-bank.json")
    atomic_write(REPORT / "trajectory-replay.json", json_bytes(rows))
    print("Replayed", len(rows), "case segments")


if __name__ == "__main__":
    main()
