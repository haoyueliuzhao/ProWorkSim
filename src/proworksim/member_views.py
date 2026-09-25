"""Recover actual per-decision requests and only the member's own action tokens.

No tokenization, completion reconstruction, world access or oracle is performed.
Missing tokens leave a semantic view, never a fabricated training example.
"""

import copy
import math

from .storage import digest, json_bytes

MEMBER_VIEW_VERSION = "member-view-v0.13"


def _tokens(response):
    trace = response.get("token_trace")
    if not isinstance(trace, dict):
        return None, ["actual_token_trace_missing"]
    for name in ("input_ids", "output_ids"):
        if (
            not isinstance(trace.get(name), list)
            or not trace[name]
            or any(type(value) is not int or value < 0 for value in trace[name])
        ):
            return None, ["invalid_actual_" + name]
    n, m = len(trace["input_ids"]), len(trace["output_ids"])
    if trace.get("input_mask") != [0] * n or trace.get("output_mask") != [1] * m:
        return None, ["actor_ownership_masks_invalid"]
    logs = trace.get("behavior_logprobs")
    if (
        not isinstance(logs, list)
        or len(logs) != m
        or any(
            type(value) not in (int, float) or not math.isfinite(value) or value > 1e-6
            for value in logs
        )
    ):
        return None, ["actual_behavior_probabilities_missing_or_invalid"]
    if (
        trace.get("source")
        != "actual generation token IDs and sampling logits, not retokenized text"
    ):
        return None, ["token_provenance_unverified"]
    usage = response.get("usage", {})
    if (
        usage.get("prompt_tokens") != n
        or usage.get("completion_tokens") != m
        or usage.get("total_tokens") != n + m
    ):
        return None, ["token_usage_mismatch"]
    return copy.deepcopy(trace), []


def _known_direct_context_stop(attempts, responses, events, call_id, metadata, policy, window):
    if len(attempts) != 1 or responses:
        return None
    attempt = attempts[0]["payload"]
    transport = attempt.get("response", {})
    if not isinstance(transport, dict):
        return None
    body = transport.get("body", {})
    if not isinstance(body, dict):
        return None
    config = policy.get("config", {}) if isinstance(policy, dict) else {}
    identity = config.get("weight_identity", {})
    if not isinstance(identity, dict):
        return None
    error = body.get("error", {})
    if not isinstance(error, dict):
        return None
    lengths = [error.get(key) for key in ("prompt_tokens", "requested_output", "context_limit")]
    if not (
        attempt.get("status") == "backend_context_limit"
        and transport.get("http_status") == 400
        and body.get("transport_kind") == "resident_direct"
        and body.get("generation_started") is False
        and identity.get("version") == "shared-actor-identity-v0.13"
        and body.get("actor_identity") == identity
        and config.get("model_revision") == identity.get("policy_version")
        and body.get("online_window_id") == window.get("window_id")
        and error.get("code") == "context_length_exceeded"
        and all(type(value) is int and value > 0 for value in lengths)
        and lengths[0] + lengths[1] > lengths[2]
        and digest(json_bytes(attempt.get("request"))) == metadata.get("request_sha256")
        and any(
            event["kind"] == "model_boundary_error"
            and event["payload"].get("status") == "model_budget_exhausted"
            and event["payload"].get("model_call_id") == call_id
            and event["payload"].get("backend_error", {}).get("code") == "context_length_exceeded"
            for event in events
        )
    ):
        return None
    return attempt


def member_view(rollout, member_id):
    if member_id not in rollout["members"]:
        raise ValueError("Unknown member")
    member = rollout["members"][member_id]
    events = [event for event in rollout["events"] if event.get("worker_id") == member_id]
    starts = [
        event
        for event in events
        if event["kind"] == "model_call" and event["payload"].get("stage") == "started"
    ]
    decisions, issues = [], []
    call_ids = [event["payload"]["call_id"] for event in starts]
    repeated_calls = {call_id for call_id in call_ids if call_ids.count(call_id) > 1}
    orphan_calls = {
        event["payload"].get("call_id")
        for event in events
        if event["kind"] in {"model_response", "model_attempt"}
    } - set(call_ids)
    issues.extend(
        {"call_id": call_id, "reason": "orphan_actual_model_record"}
        for call_id in sorted(orphan_calls, key=str)
    )
    for start in starts:
        metadata = start["payload"]
        call_id = metadata["call_id"]
        attempts = [
            event
            for event in events
            if event["kind"] == "model_attempt"
            and event["payload"].get("call_id") == call_id
            and event["payload"].get("stage") == "finished"
        ]
        successes = [event for event in attempts if event["payload"].get("status") == "success"]
        responses = [
            event
            for event in events
            if event["kind"] == "model_response" and event["payload"].get("call_id") == call_id
        ]
        record = {
            "call_id": call_id,
            "decision_index": metadata.get("decision_index"),
            "opportunity_id": metadata.get("opportunity_id"),
            "member_id": member_id,
            "actual_input": None,
            "actual_response": None,
            "tokens": None,
            "actor_trainable": False,
            "semantic_recoverable": False,
            "diagnostics": [],
            "policy_identity": copy.deepcopy(rollout["manifest"]["policies"].get(member_id)),
            "behavior_metadata": copy.deepcopy(metadata),
            "generation_status": "unknown_or_missing",
            "actor_required": True,
            "world_actions": [
                copy.deepcopy(event["payload"])
                for event in events
                if event["kind"] == "tool_call" and event["payload"].get("model_call_id") == call_id
            ],
        }
        if len(successes) != 1 or len(responses) != 1:
            budget_stopped = not attempts and any(
                event["kind"] == "model_budget_stop" and event["payload"].get("call_id") == call_id
                for event in events
            )
            if budget_stopped:
                record.update(generation_status="not_started_budget_stop", actor_required=False)
            direct_stop = _known_direct_context_stop(
                attempts,
                responses,
                events,
                call_id,
                metadata,
                record["policy_identity"],
                rollout["window"],
            )
            if direct_stop is not None:
                record.update(
                    generation_status="not_started_direct_context_limit",
                    actor_required=False,
                    actual_input=copy.deepcopy(direct_stop["request"]),
                    input_sha256=digest(json_bytes(direct_stop["request"])),
                    non_generation_response=copy.deepcopy(direct_stop["response"]),
                    non_generation_contract="resident-direct-context-stop-v0.13",
                )
                record["diagnostics"].append("known_direct_no_generation_context_limit")
            else:
                record["diagnostics"].append("no_unique_successful_actual_completion")
            if call_id in repeated_calls:
                record["diagnostics"].append("duplicate_model_call_identity")
            decisions.append(record)
            issues.extend(
                {"call_id": call_id, "reason": reason} for reason in record["diagnostics"]
            )
            continue
        attempt, response = successes[0]["payload"], responses[0]["payload"]["response"]
        record.update(
            actual_input=copy.deepcopy(attempt["request"]),
            actual_response=copy.deepcopy(response),
            input_sha256=digest(json_bytes(attempt["request"])),
            response_sha256=digest(json_bytes(response)),
            context_selection=copy.deepcopy(attempt.get("context_selection")),
            input_event_sequence=successes[0]["sequence"],
            response_event_sequence=responses[0]["sequence"],
            generation_status="observed_completion",
            attempt_id=attempt.get("attempt_id"),
            service_completion_id=response.get("id"),
            effective_generation=copy.deepcopy(response.get("effective_generation")),
            reported_model=response.get("model"),
            system_fingerprint=response.get("system_fingerprint"),
        )
        if response != attempt.get("response", {}).get("body") or record[
            "input_sha256"
        ] != metadata.get("request_sha256"):
            record["diagnostics"].append("transport_response_or_request_link_mismatch")
        if call_id in repeated_calls:
            record["diagnostics"].append("duplicate_model_call_identity")
        selection = record["context_selection"]
        if selection is not None and selection.get("request_sha256") != record["input_sha256"]:
            record["diagnostics"].append("context_selection_request_mismatch")
        record["semantic_recoverable"] = not record["diagnostics"] and len(attempts) == 1
        trace, missing = _tokens(response)
        record["diagnostics"].extend(missing)
        # A retried service may have generated an unobserved action. The first
        # version conservatively retains it semantically but excludes actor use.
        if len(attempts) != 1:
            record["diagnostics"].append("behavior_draw_after_service_retry_not_admitted")
        if trace is not None:
            record["tokens"] = trace
            n, m = len(trace["input_ids"]), len(trace["output_ids"])
            record.update(labels=[-100] * n + trace["output_ids"], loss_mask=[0] * n + [1] * m)
        record["actor_trainable"] = not record["diagnostics"] and member["origin"] == "target_model"
        decisions.append(record)
        issues.extend({"call_id": call_id, "reason": reason} for reason in record["diagnostics"])
    sampled = [row for row in decisions if row["actual_response"] is not None]
    complete = (
        bool(sampled)
        and not orphan_calls
        and not repeated_calls
        and all(row["actor_trainable"] for row in decisions if row["actor_required"])
    )
    semantic_complete = (
        bool(sampled)
        and not orphan_calls
        and not repeated_calls
        and all(row["semantic_recoverable"] for row in decisions if row["actor_required"])
    )
    return {
        "version": MEMBER_VIEW_VERSION,
        "rollout_id": rollout["rollout_id"],
        "member_id": member_id,
        "origin": member["origin"],
        "window": copy.deepcopy(rollout["window"]),
        "decisions": decisions,
        "diagnostics": issues,
        "own_action_count": len(sampled),
        "own_action_tokens": sum(
            len(row["tokens"]["output_ids"]) for row in sampled if row["tokens"]
        ),
        "complete_actor_trajectory": complete,
        "complete_semantic_trajectory": semantic_complete,
        "no_own_actions": not sampled,
        "scope": "All recorded member completions, including failed-format decisions; colleague messages and tool results remain input-only. No silent first-response selection or retokenization.",
    }
