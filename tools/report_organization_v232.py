"""Reconcile v232 receipts and distinguish actual action, handoff, mechanism and score."""

from collections import Counter
import json
import sqlite3
from pathlib import Path
from proworksim.software_benchmark_deepseek_contract_v105 import normalize_usage
from proworksim.software_context_builder_v230 import (
    identity,
    recover_observations,
    object_text,
)
from proworksim.software_context_panel_v231 import ROOT
from proworksim.storage import atomic_write, json_bytes, read_json, digest

PLAN = ROOT / "artifacts/software-benchmark-v232/first-pair-r1"
RUN = ROOT / "runs/software-benchmark-v232/first-pair-r1"


def inherited_anchors(raw, shown, actor):
    """Check older SDK static-field references after rebuilding the actual v232 wire."""
    snapshots = recover_observations(shown)
    n = 0
    for row in raw["messages"]:
        v = object_text(row.get("content")) or {}
        ref = v.get("_v117_same_input_static_fields")
        if not ref:
            continue
        i = ref["anchor_message_index"]
        literal = raw["messages"][i]["content"]
        if digest(literal.encode()) != ref["anchor_content_sha256"]:
            raise ValueError("Unknown SDK anchor")
        expected = json.loads(literal)
        actual = object_text(shown["messages"][i]["content"]) or {}
        if expected["observation"]["actor_id"] != actor:
            raise ValueError("Foreign SDK anchor")
        for path in ref["omitted_equal_paths"]:
            parts = path.lstrip("/").split("/")
            a = expected
            b = {**actual, "observation": snapshots[i]}
            for k in parts:
                a = a[k]
                b = b[k]
            if identity(a) != identity(b):
                raise ValueError("Static anchor field changed")
        n += 1
    return n


def scan(folder, db, case, arm):
    rc = read_json(folder / "result.json")
    slot = rc["slot"]
    decision = read_json(folder / "decision.json") if (folder / "decision.json").exists() else {}
    graph = (
        read_json(folder / "assigned-graph.json")
        if (folder / "assigned-graph.json").exists()
        else {}
    )
    ledger = {
        rid: (status, u, cost)
        for rid, status, u, cost in db.execute(
            "select id,status,body,cost from requests where slot=?", (slot,)
        )
    }
    totals = Counter()
    sources = Counter()
    observations = Counter()
    reqs = []
    intents = []
    format_errors = {}
    controls = Counter()
    physical_worker = set()
    for sub in ("api", "osa-api"):
        for p in sorted((folder / sub).glob("*/request.json")):
            req = read_json(p)
            payload = req["payload"]
            rid = req["physical_id"]
            status, usage, cost = ledger.pop(rid)
            if status != "settled":
                totals[status] += 1
                continue
            u = normalize_usage(read_json(p.with_name("response.json")))
            if (
                u != json.loads(usage)
                or u != read_json(p.with_name("usage.json"))
                or cost != u["peak_cost_nanoyuan"]
            ):
                raise ValueError("Usage receipt mismatch")
            role = (
                "osa"
                if sub == "osa-api"
                else "worker"
                if payload["wire"].get("tools")
                else "condenser"
            )
            actor = payload["member_id"]
            logical = payload["request_id"]
            archive = folder / "telemetry" / role / identity([slot, actor, logical])
            m = read_json(archive / "manifest.json")
            orig = read_json(archive / "original.json")
            shown = read_json(archive / "shown.json")
            if (
                shown != payload["wire"]
                or identity(orig) != m["original_wire"]
                or identity(shown) != m["shown_wire"]
                or identity(recover_observations(orig)) != identity(recover_observations(shown))
            ):
                raise ValueError("Payload/observation mismatch")
            if role != "osa" and (
                m["org_graph_version"] != graph["version"] or not m["opportunity"]
            ):
                raise ValueError("Unbound worker request")
            if role == "worker":
                physical_worker.add(m["opportunity"])
            observations["static_sdk_anchors_verified"] += inherited_anchors(orig, shown, actor)
            for action in (
                read_json(p.with_name("response.json"))["choices"][0]["message"].get("tool_calls")
                or []
            ):
                if action["function"]["name"] != "send_message":
                    continue
                args = json.loads(action["function"]["arguments"])
                schema = next(
                    t["function"]["parameters"]
                    for t in shown["tools"]
                    if t["function"]["name"] == "send_message"
                )
                hint = next(
                    (
                        v["pending_diagnosis"]
                        for msg in reversed(shown["messages"])
                        if (v := object_text(msg.get("content")) or {}).get("pending_diagnosis")
                    ),
                    {},
                )
                intents.append(
                    {
                        "agent": actor,
                        "physical_request": rid,
                        "opportunity": m["opportunity"],
                        "tool_call_id": action["id"],
                        "formal_prefix": args.get("body", "").startswith("DIAG "),
                        "body_leading_fields": args.get("body", "").split()[:2],
                        "body_characters": len(args.get("body", "")),
                        "unexpected_arguments": sorted(set(args) - set(schema["properties"])),
                        "missing_required": sorted(set(schema["required"]) - set(args)),
                        "task": args.get("task_id"),
                        "recipient": args.get("recipient"),
                        "shown_duty": hint,
                    }
                )
            totals.update(
                requests=1,
                input=u["input_tokens"],
                output=u["output_tokens"],
                cost_nanoyuan=cost,
                cache_hit=u["cache_hit_tokens"],
                local_input=m["local_input"],
                template_residual=m["template_and_segmentation_residual"],
            )
            sources.update(m["source_estimates"])
            controls[role] += 1
            for s in m["snapshots"]:
                observations[s["full"] or "delta"] += 1
            reqs.append(
                {
                    "physical_id": rid,
                    "provider_id": u["provider_response_id"],
                    "logical_id": logical,
                    "actor": actor,
                    "role": role,
                    "graph_version": m["org_graph_version"],
                    "opportunity": m["opportunity"],
                    "manifest": str((archive / "manifest.json").relative_to(ROOT)),
                    "shown_sha256": m["shown_wire"],
                    "visibility": m["visibility"],
                    "source_estimates": m["source_estimates"],
                }
            )
    if ledger:
        raise ValueError("Unarchived physical request")
    if totals["local_input"] != sum(sources.values()) + totals["template_residual"]:
        raise ValueError("Source arithmetic")
    counts = Counter()
    member_tools = Counter()
    handoffs = []
    returned = set()
    reads = []
    grants = []
    if (folder / "telemetry/events.sqlite").exists():
        with sqlite3.connect(
            "file:" + str(folder / "telemetry/events.sqlite") + "?mode=ro", uri=True
        ) as c:
            for (body,) in c.execute("select body from events"):
                row = json.loads(body)
                kind = row["kind"]
                if kind in ("grant-dispatched", "grant-blocked"):
                    grants.append(
                        {
                            "stage": row["native_id"][1],
                            "actor": row["agent_id"],
                            "result": row["result"],
                            "request": row["request_id"],
                        }
                    )
                if kind != "native":
                    continue
                r = read_json(Path(row["payload_ref"]))
                d = r["payload"]
                if r["kind"] == "organization_work_opportunity_v049" and d["phase"] == "before":
                    counts["opportunities"] += 1
                    returned.add(d["opportunity_id"])
                if r["kind"] != "tool_call":
                    continue
                counts["tool_receipts"] += 1
                if (
                    row["org_graph_version"] == graph.get("version")
                    and row["dispatch_opportunity_id"] in physical_worker
                ):
                    counts["actions_graph_and_request_bound"] += 1
                name = d["action"]
                resp = d["response"]
                actor = row["agent_id"]
                if actor == "member_002" and resp.get("ok"):
                    member_tools[name] += 1
                if name in ("read_test_result", "read_work_event") and resp.get("ok"):
                    reads.append(
                        {
                            "tool": name,
                            "call": d["model_tool_call_id"],
                            "actor": actor,
                            "requested": d["arguments"],
                        }
                    )
                if name == "send_message" and actor == "member_002":
                    handoffs.append(
                        {
                            "actor": actor,
                            "formal_prefix": str(d["arguments"].get("body", "")).startswith(
                                "DIAG "
                            ),
                            "accepted": resp["ok"],
                            "recipient": d["arguments"].get("recipient"),
                        }
                    )
    events = folder / "runtime/experience.jsonl"
    if events.exists():
        with events.open() as source:
            for line in source:
                e = json.loads(line)
                if e["kind"] == "model_format_error":
                    d = e["payload"]
                    format_errors[d["opportunity_id"]] = d["parse_diagnostics"].get(
                        "failure", d["reason"]
                    )
    for i in intents:
        i["native_format_error"] = format_errors.get(i["opportunity"])
    if not physical_worker <= returned:
        raise ValueError("Worker sent without opportunity")
    official = {}
    for kind in ("code", "delivery"):
        path = folder.with_name(arm + "-" + kind) / "receipt.json"
        s = read_json(path) if path.exists() else {}
        official[kind] = {k: s.get(k) for k in ("status", "resolved", "cleanup_errors")}
        official[kind]["receipt"] = str(path.relative_to(ROOT))
    mechanism = read_json(folder / "mechanism.json") if (folder / "mechanism.json").exists() else {}
    if (
        rc["status"] == "closed"
        and rc["logical_tokens"]
        != totals["input"] + totals["output"] + read_json(PLAN / "protocol.json")["prefix_tokens"]
    ):
        raise ValueError("Checkpoint/worker/controller budget mismatch")
    if (
        rc["status"] == "closed"
        and counts["actions_graph_and_request_bound"] != counts["tool_receipts"]
    ):
        raise ValueError("Missing action version")
    return {
        "arm": arm,
        "status": rc["status"],
        "error": rc.get("error"),
        "termination": rc.get("termination"),
        "graph_changed": graph.get("changed"),
        "option": rc.get("option"),
        "menu": decision.get("menu", {}).get("options"),
        "decision": {k: v for k, v in decision.items() if k not in ("menu", "anomaly")},
        "effective_duties": mechanism.get("control", {}).get("duties"),
        "anomaly_endpoint": mechanism.get("endpoint"),
        "time_seconds": rc["finished"] - rc["started"],
        "provider_usage": totals,
        "requests_by_role": controls,
        "input_source_estimates": sources,
        "observations": observations,
        "grants": grants,
        "execution": counts,
        "accepted_member002_tools": member_tools,
        "member002_messages": handoffs,
        "send_message_model_intents": intents,
        "successful_reads": reads,
        "official": official,
        "cleanup": read_json(folder / "actor/cleanup.json")
        if (folder / "actor/cleanup.json").exists()
        else None,
        "observer_errors": rc.get("observer_errors"),
        "requests": reqs,
    }


def main():
    a = read_json(RUN / "authority.json")
    case = read_json(PLAN / "protocol.json")["case"]
    with sqlite3.connect("file:" + a["ledger"] + "?mode=ro", uri=True) as db:
        rows = [scan(RUN / case / arm, db, case, arm) for arm in ("KEEP", "OSA")]
        cost = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        reserved = db.execute(
            "select count(*) from requests where slot glob 'v232:*' and status='reserved'"
        ).fetchone()[0]
    report = {
        "rows": rows,
        "reserved_requests": reserved,
        "case": case,
        "CN_updates": 0,
        "incremental_nanoyuan": sum(r["provider_usage"]["cost_nanoyuan"] for r in rows),
        "cumulative_nanoyuan": cost,
        "balance_nanoyuan": a["cap_nanoyuan"] - cost,
        "protocol_sha256": digest((PLAN / "protocol.json").read_bytes()),
    }
    atomic_write(PLAN / "results.json", json_bytes(report))


if __name__ == "__main__":
    main()
