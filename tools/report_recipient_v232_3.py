"""Reconcile recipient credit, physical exposure and the subsequent world action separately."""

import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_handoff_v232_1 as old
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_context_builder_v230 import identity, recover_observations, object_text
from proworksim.software_graph_execution_v230 import World
from proworksim.storage import read_json, json_bytes, atomic_write
from run_recipient_v232_3 import PLAN, RUN, CASE, ARM


def main():
    if not (RUN / "completed.json").exists():
        raise ValueError("Panel is still open")
    clone_function(old.report, {**old.report.__globals__, "RUN": RUN, "PLAN": PLAN})()
    out = PLAN / "results.json"
    r = read_json(out)
    folder = RUN / CASE / ARM
    r["prior_handoff_trial"] = {
        k: v
        for k, v in read_json(old.PLAN / "results.json").items()
        if k
        in (
            "case",
            "physical",
            "effective_duties",
            "official",
            "message_attempts",
            "anomaly_endpoint",
            "termination",
        )
    }
    with sqlite3.connect(f"file:{folder}/telemetry/events.sqlite?mode=ro", uri=True) as c:
        r["recipient_scheduler"] = [
            {
                k: event[k]
                for k in (
                    "kind",
                    "result",
                    "native_id",
                    "graph" if "graph" in event else "org_graph_version",
                    "details",
                )
            }
            for (raw,) in c.execute("select body from events order by rowid")
            if (event := json.loads(raw))["kind"].startswith("recipient_")
        ]
    actions = {}
    response_at = {}
    chain = []
    with (folder / "runtime/experience.jsonl").open() as events:
        for line in events:
            e = json.loads(line)
            d = e["payload"]
            if e["kind"] == "tool_call":
                actions[d["model_tool_call_id"]] = d
                if d["action"] in (
                    "replace_file",
                    "run_tests",
                    "send_message",
                    "fix_patch",
                    "complete_work",
                    "submit_integration",
                ):
                    receipt = d["response"]
                    b = receipt.get("result") or {}
                    chain.append(
                        {
                            "opportunity": d["opportunity_id"],
                            "actor": e.get("worker_id"),
                            "action": d["action"],
                            "world_ok": receipt.get("ok"),
                            **{
                                k: b[k]
                                for k in (
                                    "counts",
                                    "passed",
                                    "patch_id",
                                    "message_sequence",
                                    "source_reference",
                                )
                                if k in b
                            },
                        }
                    )
            if e["kind"] == "model_response":
                response_at[d["opportunity_id"]] = d["response"]
    r["action_sequence"] = chain
    branch = RUN / CASE / ARM
    for intent in r["message_attempts"]:
        if not intent["formal_prefix"] or not intent["world_accepted"]:
            continue
        action = actions[intent["call"]]
        body = action["arguments"]["body"]
        if identity(body) != intent["body_sha256"]:
            raise ValueError("Wrong accepted body")
        intent["exposures"] = []
        later = set(intent["later_recipient_opportunities"])
        for f in sorted(
            (branch / "api").glob("*/request.json"), key=lambda q: read_json(q)["time"]
        ):
            request = read_json(f)
            payload = request["payload"]
            if payload["member_id"] != intent["recipient"] or payload["usage_id"] != "agent":
                continue
            manifest = read_json(
                branch
                / "telemetry/worker"
                / identity([payload["team_slot_id"], payload["member_id"], payload["request_id"]])
                / "manifest.json"
            )
            op = manifest["opportunity"]
            if int(op.rsplit("-", 1)[1]) not in later:
                continue
            w = payload["wire"]
            snapshots = recover_observations(w)
            previews = [
                msg["body"]
                for snap in snapshots.values()
                for msg in snap.get("messages", [])
                if msg.get("sequence") == intent["message_sequence"]
                and msg.get("actor_id") == intent["actor"]
                and msg.get("recipient") == intent["recipient"]
                and body.startswith(msg.get("body", ""))
                and msg.get("body")
            ]
            # Also look for the full string in instructions and tool returns, including structured JSON.
            values = [m.get("content") or "" for m in w["messages"]]
            stack = [object_text(t) for t in values if isinstance(t, str)]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
                elif isinstance(value, str):
                    values.append(value)
            intent["exposures"].append(
                {
                    "opportunity": op,
                    "provider_request": request["physical_id"],
                    "request_id": payload["request_id"],
                    "verified_prefix_chars": max(map(len, previews), default=0),
                    "body_chars": len(body),
                    "full_text_present": any(body in v for v in values if isinstance(v, str)),
                }
            )
    # Isolated read-only handler replay. Never feed this value to a worker or alter a live receipt.
    archived = read_json(branch / "prepared/world/control/state.json")
    world = World.__new__(World)
    world.state = archived
    for intent in r["message_attempts"]:
        if intent["formal_prefix"] and intent["world_accepted"]:
            event = world._action_read_work_event(
                intent["recipient"], "SOFTWARE27", intent["message_sequence"]
            )
            if identity(event["body"]) != intent["body_sha256"]:
                raise ValueError("Original message not recovered")
            intent["offline_addressed_read"] = {
                "tool": "read_work_event",
                "arguments": {"sequence": intent["message_sequence"]},
                "recipient": intent["recipient"],
                "characters": len(event["body"]),
                "whole_body_hash_matches": True,
                "online_execution": False,
            }
    outcomes = []
    for intent in r["message_attempts"]:
        if not intent["formal_prefix"] or not intent["world_accepted"]:
            continue
        for exposure in intent["exposures"]:
            if not (exposure["verified_prefix_chars"] or exposure["full_text_present"]):
                continue
            op = exposure["opportunity"]
            response = response_at[op]
            calls = []
            for call in response["choices"][0]["message"].get("tool_calls") or []:
                action = actions.get(call["id"])
                args = action["arguments"] if action else {}
                # Preserve locators, not file contents. The complete tool call is archived by ID.
                locators = {
                    k: v
                    for k, v in args.items()
                    if k
                    in (
                        "path",
                        "task_id",
                        "report_id",
                        "patch_id",
                        "selection",
                        "sequence",
                        "recipient",
                    )
                }
                calls.append(
                    {
                        "id": call["id"],
                        "tool": call["function"]["name"],
                        "executed_ok": action["response"].get("ok") if action else None,
                        "locators": locators,
                    }
                )
            outcomes.append(
                {
                    "opportunity": op,
                    "recipient": intent["recipient"],
                    "message_sequence": intent["message_sequence"],
                    "response_id": response["id"],
                    "exposure": exposure,
                    "actions": calls,
                }
            )
    r["recipient_responses_after_verified_exposure"] = outcomes
    if r["status"] == "closed":
        if (
            r["reserved_requests"]
            or r["observer_errors"]
            or any(
                type(r["official"].get(k, {}).get("resolved")) is not bool
                for k in ("code", "delivery")
            )
        ):
            raise ValueError("Incomplete scoring or trace")
        if (
            r["new_controller_calls"] != 0
            or not r["actor_cleanup"]["owned_actor_removed"]
            or any(r["official"][k]["cleanup_errors"] for k in ("code", "delivery"))
        ):
            raise ValueError("Controller usage or cleanup mismatch")
    atomic_write(out, json_bytes(r))


if __name__ == "__main__":
    main()
