"""Verify the preview, voluntary lookup, returned text and next action using native identities."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_recipient_v232_3 as prior
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_context_builder_v230 import object_text
from proworksim.storage import read_json, json_bytes, atomic_write
from run_preview_v232_4 import PLAN, RUN, CASE, ARM


def main():
    clone_function(
        prior.main, {**prior.main.__globals__, "PLAN": PLAN, "RUN": RUN, "CASE": CASE, "ARM": ARM}
    )()
    out = PLAN / "results.json"
    r = read_json(out)
    folder = RUN / CASE / ARM
    r["prior_recipient_trial"] = {
        k: v
        for k, v in read_json(prior.PLAN / "results.json").items()
        if k
        in (
            "physical",
            "message_attempts",
            "effective_duties",
            "anomaly_endpoint",
            "official",
            "termination",
        )
    }
    actions = {}
    with (folder / "runtime/experience.jsonl").open() as f:
        for line in f:
            e = json.loads(line)
            if e["kind"] == "tool_call":
                d = e["payload"]
                actions[d["model_tool_call_id"]] = d
    requests = {}
    for f in (folder / "api").glob("*/request.json"):
        req = read_json(f)
        requests[req["physical_id"]] = (req, f)
    opportunities = {}
    sender_calls = []
    for req, path in requests.values():
        payload = req["payload"]
        if payload["member_id"] == "member_002" and payload["usage_id"] == "agent":
            msg = read_json(path.with_name("response.json"))["choices"][0]["message"]
            sender_calls.extend(c["function"]["name"] for c in msg.get("tool_calls") or [])
    with (folder / "runtime/experience.jsonl").open() as f:
        for line in f:
            e = json.loads(line)
            d = e["payload"]
            if (
                e.get("worker_id") != "member_002"
                or not isinstance(d, dict)
                or "opportunity_id" not in d
            ):
                continue
            item = opportunities.setdefault(d["opportunity_id"], {})
            if e["kind"] == "organization_work_opportunity_v049" and d["phase"] == "before":
                item.update(
                    ordinal=d["opportunity_ordinal"], available=d["team_budget"]["available_tokens"]
                )
            elif e["kind"] == "model_call" and d.get("reservation"):
                item["quoted"] = d["reservation"]["token_reservation"]
            elif e["kind"] == "model_boundary_error":
                item.update(boundary=d["status"], limits=d["limits"])
    r["sender_boundary"] = [v for v in opportunities.values() if "boundary" in v]
    r["sender_tool_intents"] = sender_calls
    r["physical_requests_with_notice"] = sum(
        any(
            m["role"] == "user" and "truncated_handoff" in (object_text(m.get("content")) or {})
            for m in req["payload"]["wire"]["messages"]
        )
        for req, path in requests.values()
    )
    r["qualifying_long_handoffs"] = sum(
        bool(i["formal_prefix"] and i["world_accepted"] and i["body_chars"] > 500)
        for i in r["message_attempts"]
    )
    r["conditional_readback_observable"] = bool(r["physical_requests_with_notice"])
    for intent in r["message_attempts"]:
        if not intent["formal_prefix"] or not intent["world_accepted"]:
            continue
        seq = intent["message_sequence"]
        accepted_body = actions[intent["call"]]["arguments"]["body"]
        lookup_ids = set()
        for exp in intent["exposures"]:
            req, path = requests[exp["provider_request"]]
            wire = req["payload"]["wire"]
            notice = next(
                (
                    card
                    for m in reversed(wire["messages"])
                    if m["role"] == "user"
                    and (card := (object_text(m.get("content")) or {}).get("truncated_handoff"))
                    and card["message_sequence"] == seq
                ),
                None,
            )
            if notice is not None and (
                notice["total_characters"] != len(accepted_body)
                or notice["displayed_characters"] != exp["verified_prefix_chars"]
                or notice["read_full_text"]
                != {"tool": "read_work_event", "arguments": {"sequence": seq}}
            ):
                raise ValueError("Incorrect displayed length or lookup")
            exp["notice_on_wire"] = notice
            exp["exact_full_tool_result_present"] = any(
                m["role"] == "tool"
                and m.get("tool_call_id") in lookup_ids
                and ((object_text(m.get("content")) or {}).get("result") or {}).get("body")
                == accepted_body
                for m in wire["messages"]
            )
            exp["lookup_attempts"] = []
            response = read_json(path.with_name("response.json"))
            for c in response["choices"][0]["message"].get("tool_calls") or []:
                if c["function"]["name"] != "read_work_event":
                    continue
                try:
                    args = json.loads(c["function"]["arguments"])
                except ValueError:
                    continue
                if not isinstance(args, dict) or args.get("sequence") != seq:
                    continue
                receipt = actions.get(c["id"], {}).get("response", {})
                result = receipt.get("result") or {}
                ok = bool(
                    receipt.get("ok")
                    and result.get("body") == accepted_body
                    and result.get("sequence") == seq
                    and result.get("recipient") == intent["recipient"]
                    and result.get("actor_id") == intent["actor"]
                )
                if ok:
                    lookup_ids.add(c["id"])
                exp["lookup_attempts"].append(
                    {
                        "tool_call_id": c["id"],
                        "world_accepted": receipt.get("ok"),
                        "body_hash_matches_addressed_event": ok,
                    }
                )
        intent["truncated_handoff_test_applicable"] = any(
            e["notice_on_wire"] for e in intent["exposures"]
        )
        intent["accepted_full_lookup_count"] = len(lookup_ids)
    # Recovering T1 observations earlier, and verifying the actual final wire, must agree.
    r["readback_endpoint_evaluable"] = any(
        a.get("truncated_handoff_test_applicable") for a in r["message_attempts"]
    )
    atomic_write(out, json_bytes(r))


if __name__ == "__main__":
    main()
