"""Measure the schema->world->recipient chain for the one fresh handoff continuation."""

import json
from collections import Counter
from pathlib import Path
import sqlite3
from proworksim.software_benchmark_deepseek_contract_v105 import normalize_usage
from proworksim.software_context_builder_v230 import identity, recover_observations
from proworksim.software_context_panel_v231 import ROOT
from proworksim.storage import atomic_write, json_bytes, read_json

PLAN = ROOT / "artifacts/software-benchmark-v232-1/handoff-r1"
RUN = ROOT / "runs/software-benchmark-v232-1/handoff-r1"


def report():
    p = read_json(PLAN / "protocol.json")
    a = read_json(RUN / "authority.json")
    folder = RUN / p["case"] / p["arm"]
    rc = read_json(folder / "result.json")
    slot = rc["slot"]
    totals = Counter()
    attempts = []
    views = []
    responses = {}
    with sqlite3.connect("file:" + a["ledger"] + "?mode=ro", uri=True) as db:
        records = {
            rid: (status, pid, cost, tokens)
            for rid, status, pid, cost, tokens in db.execute(
                "select id,status,provider_id,cost,tokens from requests where slot=?", (slot,)
            )
        }
        cumulative = db.execute(
            "select coalesce(sum(cost),0) from requests where status='settled'"
        ).fetchone()[0]
        open_holds = db.execute(
            "select count(*) from requests where slot=? and status='reserved'", (slot,)
        ).fetchone()[0]
    for f in sorted(
        (folder / "api").glob("*/request.json"), key=lambda path: read_json(path)["time"]
    ):
        req = read_json(f)
        rid = req["physical_id"]
        payload = req["payload"]
        actor = payload["member_id"]
        status, pid, cost, tokens = records.pop(rid)
        totals[status] += 1
        if status != "settled":
            continue
        body = read_json(f.with_name("response.json"))
        u = normalize_usage(body)
        if (pid, cost, tokens) != (
            body["id"],
            u["peak_cost_nanoyuan"],
            u["total_tokens"],
        ) or u != read_json(f.with_name("usage.json")):
            raise ValueError("Physical receipt differs")
        totals.update(
            input=u["input_tokens"],
            output=u["output_tokens"],
            cost_nanoyuan=cost,
            cache_hit=u["cache_hit_tokens"],
        )
        wire = payload["wire"]
        role = "worker" if wire.get("tools") else "condenser"
        mpath = (
            folder
            / "telemetry"
            / role
            / identity([slot, actor, payload["request_id"]])
            / "manifest.json"
        )
        m = read_json(mpath)
        if identity(wire) != m["shown_wire"] or m["org_graph_version"] != 1:
            raise ValueError("Unbound request")
        if role != "worker":
            continue
        op = m["opportunity"]
        responses[op] = actor
        actual_example = any(
            text["role"] == "user"
            and "When ready to hand off, call send_message with this argument shape:"
            in (text.get("content") or "")
            for text in wire["messages"]
        )
        totals["requests_showing_example"] += actual_example
        if actor == "member_001":
            views.append(
                (
                    op,
                    [
                        msg
                        for snap in recover_observations(wire).values()
                        for msg in snap.get("messages", [])
                        if isinstance(msg, dict)
                    ],
                )
            )
        for c in body["choices"][0]["message"].get("tool_calls") or []:
            if c["function"]["name"] == "send_message":
                try:
                    args = json.loads(c["function"]["arguments"])
                except ValueError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                text = args.get("body") or ""
                attempts.append(
                    dict(
                        actor=actor,
                        call=c["id"],
                        opportunity=op,
                        keys=sorted(args),
                        formal_prefix=text.startswith("DIAG "),
                        header=text.split()[:2],
                        body_sha256=identity(text),
                        body_chars=len(text),
                        example_shown=actual_example,
                        task=args.get("task_id"),
                        recipient=args.get("recipient"),
                    )
                )
    if records:
        raise ValueError("Missing physical requests")
    opportunity_ordinals = {}
    opportunity_actors = {}
    actions = {}
    errors = {}
    world_tools = Counter()
    with (folder / "runtime/experience.jsonl").open() as f:
        for line in f:
            e = json.loads(line)
            d = e["payload"]
            if e["kind"] == "organization_work_opportunity_v049" and d["phase"] == "before":
                opportunity_ordinals[d["opportunity_id"]] = d["opportunity_ordinal"]
                opportunity_actors[d["opportunity_id"]] = d["member_id"]
            if e["kind"] == "tool_call":
                actions[d["model_tool_call_id"]] = d["response"]
                world_tools[d["action"]] += 1
            elif e["kind"] == "model_format_error":
                errors[d["opportunity_id"]] = d["reason"]
    for attempt in attempts:
        resp = actions.get(attempt["call"], {})
        attempt.update(
            world_accepted=resp.get("ok"),
            message_sequence=(resp.get("result") or {}).get("message_sequence"),
            format_error=errors.get(attempt["opportunity"]),
        )
        attempt["recipient_saw_body_at"] = [
            op
            for op, msgs in views
            if attempt["recipient"] == "member_001"
            and resp.get("ok")
            and any(
                msg.get("sequence") == attempt["message_sequence"]
                and identity(msg.get("body")) == attempt["body_sha256"]
                for msg in msgs
            )
        ]
        if resp.get("ok"):
            later = [
                op
                for op, n in opportunity_ordinals.items()
                if n > opportunity_ordinals[attempt["opportunity"]]
                and opportunity_actors[op] == attempt["recipient"]
            ]
            attempt["later_recipient_opportunities"] = [opportunity_ordinals[op] for op in later]
            attempt["later_recipient_worker_requests"] = sum(op in responses for op in later)
    mechanism = read_json(folder / "mechanism.json") if (folder / "mechanism.json").exists() else {}
    registered = mechanism.get("control", {}).get("duties", {})
    with sqlite3.connect(
        "file:" + str(folder / "telemetry/events.sqlite") + "?mode=ro", uri=True
    ) as c:
        audit = [
            {k: d[k] for k in ("kind", "native_id", "agent_id", "request_id", "result", "details")}
            for (raw,) in c.execute("select body from events order by rowid")
            if (d := json.loads(raw))["kind"]
            in {
                "repair_reserved",
                "repair_triggered",
                "repair_released",
                "grant-dispatched",
                "grant-blocked",
                "handoff_example",
            }
        ]
    scoring = {}
    for kind in ("code", "delivery"):
        f = folder.with_name(p["arm"] + "-" + kind) / "receipt.json"
        if f.exists():
            s = read_json(f)
            scoring[kind] = {k: s.get(k) for k in ("status", "resolved", "cleanup_errors")}
            scoring[kind]["receipt"] = str(f.relative_to(ROOT))
    if (
        rc["status"] == "closed"
        and rc["logical_tokens"]
        != p["prefix_tokens"]
        + p["inherited_controller_tokens"]
        + totals["input"]
        + totals["output"]
    ):
        raise ValueError("Shared and physical budgets differ")
    baseline = next(r for r in read_json(Path(p["baseline"]["path"]))["rows"] if r["arm"] == "OSA")
    result = {
        "case": p["case"],
        "status": rc["status"],
        "termination": rc.get("termination"),
        "effective_duties": registered,
        "anomaly_endpoint": mechanism.get("endpoint"),
        "official": scoring,
        "control_events": audit,
        "message_attempts": attempts,
        "world_tools": world_tools,
        "physical": totals,
        "inherited_controller_usage": p["inherited_controller_tokens"],
        "new_controller_calls": len(list((folder / "osa-api").glob("*/request.json"))),
        "old_osa": {
            k: baseline[k]
            for k in (
                "option",
                "termination",
                "provider_usage",
                "member002_messages",
                "send_message_model_intents",
                "anomaly_endpoint",
                "effective_duties",
            )
        },
        "observer_errors": rc.get("observer_errors"),
        "actor_cleanup": read_json(folder / "actor/cleanup.json"),
        "reserved_requests": open_holds,
        "cumulative_nanoyuan": cumulative,
        "available_nanoyuan": a["cap_nanoyuan"] - cumulative,
    }
    atomic_write(PLAN / "results.json", json_bytes(result))


if __name__ == "__main__":
    report()
