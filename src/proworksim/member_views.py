"""Recover actual per-decision requests and only the member's own action tokens.

No tokenization, completion reconstruction, world access or oracle is performed.
Missing tokens leave a semantic view, never a fabricated training example.
"""

import copy
import math

from .storage import digest, json_bytes

MEMBER_VIEW_VERSION = "member-view-v0.13"
SHARED_ADMISSION_PROOF_VERSION = "shared-team-no-generation-v0.33r1"


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
    if "raw_output_ids" in trace or "raw_behavior_logprobs" in trace:
        if trace.get("raw_output_ids") != trace["output_ids"] or trace.get("raw_behavior_logprobs") != trace.get("behavior_logprobs"):
            return None, ["actual_generated_suffix_was_cropped_or_changed"]
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


def _sha256_text(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _known_personal_budget_row(ledger, row, rollout, identity):
    """The personal exact-token guard runs before shared reserve, still unsampled."""
    call_id, member = row["call_id"], row["member"]
    if (row.get("attempt_started") is not False
            or any(key in row for key in ("charge", "reservation", "rejected_reservation"))):
        return False
    events = rollout["events"]
    starts = [event for event in events if event.get("kind") == "model_call"
              and event["payload"].get("stage") == "started" and event["payload"].get("call_id") == call_id]
    stops = [event for event in events if event.get("kind") == "model_budget_stop"
             and event["payload"].get("call_id") == call_id]
    boundaries = [event for event in events if event.get("kind") == "model_boundary_error"
                  and event["payload"].get("model_call_id") == call_id]
    if len(starts) != 1 or len(stops) != 1 or len(boundaries) != 1:
        return False
    start, stop, boundary = starts[0], stops[0], boundaries[0]
    metadata, refusal = start["payload"], stop["payload"]
    config = rollout["manifest"]["policies"][member]["config"]
    reservation = metadata.get("reservation", {})
    prepared = reservation.get("preparation", {})
    if (any(event.get("worker_id") != member for event in (start, stop, boundary))
            or not (start["sequence"] < stop["sequence"] < boundary["sequence"])
            or metadata.get("worker_id") != member or metadata.get("decision_id") != call_id
            or not metadata.get("opportunity_id") or boundary["payload"].get("opportunity_id") != metadata["opportunity_id"]
            or boundary["payload"].get("status") != "model_budget_exhausted"
            or refusal.get("limits") != ["max_total_tokens_exact_reservation"]
            or boundary["payload"].get("limits") != refusal["limits"]
            or metadata.get("config") != config or metadata.get("weight_identity") != identity
            or config.get("weight_identity") != identity or config.get("model_revision") != identity.get("policy_version")
            or metadata.get("model_revision") != identity.get("policy_version")
            or config.get("backend_id") != "resident_direct" or metadata.get("backend_id") != "resident_direct"
            or config.get("format_error_policy") != "format_feedback_budgeted_v033"
            or refusal.get("reservation") != reservation or reservation.get("reservation_kind") != "exact_resident_prompt"
            or prepared.get("version") != "resident-request-budget-v0.31r3"
            or prepared.get("preparation_sha256") != digest(json_bytes({key: value for key, value in prepared.items()
                                                                      if key != "preparation_sha256"}))
            or any(not _sha256_text(prepared.get(key)) for key in (
                "original_request_sha256", "selected_request_sha256", "rendered_prompt_sha256", "input_ids_sha256", "recipe_sha256"))
            or prepared.get("original_request_sha256") != metadata.get("request_sha256")
            or metadata.get("context_selection", {}).get("request_sha256") != metadata.get("request_sha256")
            or prepared.get("actor_identity") != identity or prepared.get("window_id") != ledger["team_id"]
            or prepared.get("context_limit") != config.get("max_context_tokens")
            or prepared.get("reserved_output_tokens") != config.get("max_output_tokens")
            or any(type(prepared.get(key)) is not int or prepared[key] <= 0
                   for key in ("prompt_tokens", "reserved_output_tokens", "context_limit"))
            or reservation.get("input_token_reservation") != prepared["prompt_tokens"]
            or reservation.get("output_token_reservation") != prepared["reserved_output_tokens"]
            or type(reservation.get("token_reservation")) is not int
            or reservation["token_reservation"] != prepared["prompt_tokens"] + prepared["reserved_output_tokens"]
            or type(prepared.get("fits")) is not bool
            or prepared["fits"] != (reservation["token_reservation"] <= prepared["context_limit"])):
        return False
    for event in events:
        value = event["payload"]
        if not isinstance(value, dict):
            continue
        linked = {value.get("call_id"), value.get("model_call_id"), value.get("decision_id")}
        if isinstance(value.get("decision"), dict):
            linked.update(value["decision"].get(key) for key in ("call_id", "model_call_id", "decision_id"))
        if call_id in linked and event.get("kind") in {
                "model_attempt", "model_response", "tool_call", "harness_tool_call", "model_action_link",
                "model_tool_result", "model_control", "policy_decision"}:
            return False
    paid = [value["charge"] for value in ledger["records"].values()
            if value["member"] == member and value.get("status") == "settled"]
    meter = refusal.get("meter", {})
    expected = {"decisions": sum(value["member"] == member for value in ledger["records"].values()),
                "http_attempts": len(paid), "unknown_usage_attempts": 0,
                "budget_accounted_tokens": sum(value["charged_tokens"] for value in paid),
                **{"reported_" + key: sum(value["reported_usage"][key] for value in paid)
                   for key in ("prompt_tokens", "completion_tokens", "total_tokens")}}
    cap = config.get("budget", {}).get("max_total_tokens")
    return (all(type(meter.get(key)) is int and meter[key] == value for key, value in expected.items())
            and type(cap) is int and cap > 0
            and meter["budget_accounted_tokens"] + reservation["token_reservation"] > cap
            and (ledger.get("binding") is None or ledger["binding"] == {
                key: prepared[key] for key in ("actor_identity", "window_id", "recipe_sha256")}))


def _sealed_team_ledger(ledger, rollout, identity):
    """Read only a closed, charge-backed v033 ledger; never restore/mutate it."""
    if not isinstance(ledger, dict):
        return False
    payload = {key: value for key, value in ledger.items() if key != "state_sha256"}
    members = set(rollout["members"])
    if (ledger.get("version") != "shared-team-budget-v0.33"
            or ledger.get("state_sha256") != digest(json_bytes(payload))
            or ledger.get("team_id") != rollout["window"].get("window_id")
            or ledger.get("require_exact_resident") is not True or ledger.get("integrity_failure") is not None
            or not isinstance(ledger.get("members"), list) or len(ledger["members"]) != len(members)
            or set(ledger["members"]) != members or not isinstance(ledger.get("records"), dict)):
        return False
    limits = ledger.get("limits", {})
    if (set(limits) != {"max_decisions", "max_attempts", "max_total_tokens"}
            or any(type(value) is not int or value <= 0 for value in limits.values())):
        return False
    charged, attempts = 0, 0
    for call_id, row in ledger["records"].items():
        if (not isinstance(row, dict) or row.get("call_id") != call_id or row.get("member") not in members
                or type(row.get("attempt_started")) is not bool or row.get("integrity_error") is not None):
            return False
        if row.get("status") == "admission_rejected":
            if row["attempt_started"] or "charge" in row or "reservation" in row:
                return False
        elif row.get("status") == "decision_consumed":
            if not _known_personal_budget_row(ledger, row, rollout, identity):
                return False
        elif row.get("status") == "settled" and row["attempt_started"]:
            charge = row.get("charge", {})
            responses = [event for event in rollout["events"] if event.get("kind") == "model_response"
                         and event.get("worker_id") == row["member"] and event["payload"].get("call_id") == call_id]
            if len(responses) != 1:
                return False
            body = responses[0]["payload"].get("response", {})
            usage = body.get("usage", {})
            if (charge.get("usage_status") != "reported_actual_trace"
                    or charge.get("response_body_sha256") != digest(json_bytes(body))
                    or charge.get("response_id") != body.get("id")
                    or charge.get("reported_usage") != usage
                    or any(type(usage.get(key)) is not int or usage[key] < 0 for key in (
                        "prompt_tokens", "completion_tokens", "total_tokens"))
                    or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
                    or type(charge.get("charged_tokens")) is not int
                    or charge["charged_tokens"] != usage["total_tokens"]
                    or body.get("actor_identity") != identity
                    or body.get("online_window_id") != ledger["team_id"]):
                return False
            attempts += 1
            charged += charge["charged_tokens"]
        else:
            # In-flight or uncertain attempts cannot prove a closed no-generation
            # exception; their missing response/usage stays an actual problem.
            return False
    expected = {"decisions": len(ledger["records"]), "attempts": attempts,
                "charged_tokens": charged, "held_tokens": 0,
                "remaining_decisions": limits["max_decisions"] - len(ledger["records"]),
                "remaining_attempts": limits["max_attempts"] - attempts,
                "available_tokens": limits["max_total_tokens"] - charged}
    return all(type(ledger.get(key)) is int and ledger[key] == value and value >= 0
               for key, value in expected.items())


def _known_shared_admission_stop(rollout, start, member_id):
    """Prove an original pre-generation rejection from three archived records.

    The started request seal, same-opportunity boundary ledger, and final
    episode ledger must agree. No synthetic budget-stop event, response,
    re-tokenized input, or guessed missing attempt is introduced.
    """
    try:
        events, metadata = rollout["events"], start["payload"]
        call_id, opportunity = metadata["call_id"], metadata["opportunity_id"]
        policy = rollout["manifest"]["policies"][member_id]
        config, identity = policy["config"], policy["config"]["weight_identity"]
        if (metadata.get("worker_id") != member_id or metadata.get("decision_id") != call_id
                or not isinstance(opportunity, str) or not opportunity
                or not isinstance(identity, dict) or identity.get("version") != "shared-actor-identity-v0.13"
                or metadata.get("weight_identity") != identity
                or metadata.get("model_revision") != identity.get("policy_version")
                or config.get("model_revision") != identity.get("policy_version")
                or config.get("backend_id") != "resident_direct" or metadata.get("backend_id") != "resident_direct"
                or config.get("format_error_policy") != "format_feedback_budgeted_v033"
                or metadata.get("config") != config
                or rollout["window"].get("team_policy_fingerprint") != digest(json_bytes(rollout["manifest"]["policies"]))):
            return None
        starts = [event for event in events if event.get("kind") == "model_call"
                  and event["payload"].get("call_id") == call_id and event["payload"].get("stage") == "started"]
        if len(starts) != 1 or starts[0] != start:
            return None
        if sum(event.get("kind") == "model_call" and event.get("worker_id") == member_id
               and event["payload"].get("stage") == "started"
               and event["payload"].get("opportunity_id") == opportunity for event in events) != 1:
            return None
        for event in events:
            value = event["payload"]
            if not isinstance(value, dict):
                continue
            associated = {value.get("call_id"), value.get("model_call_id"), value.get("decision_id")}
            decision = value.get("decision")
            if isinstance(decision, dict):
                associated.update(decision.get(key) for key in ("call_id", "model_call_id", "decision_id"))
            if call_id in associated and event.get("kind") in {
                    "model_attempt", "model_response", "tool_call", "harness_tool_call", "model_action_link",
                    "model_tool_result", "model_control", "policy_decision"}:
                return None
        boundaries = [event for event in events if event.get("kind") == "model_boundary_error"
                      and event.get("worker_id") == member_id and event["payload"].get("opportunity_id") == opportunity]
        endings = [event for event in events if event.get("kind") == "run_boundary"]
        if len(boundaries) != 1 or len(endings) != 1:
            return None
        boundary, end = boundaries[0], endings[0]
        if not (start["sequence"] < boundary["sequence"] < end["sequence"]):
            return None
        termination = rollout["manifest"].get("termination")
        if (rollout["manifest"].get("status") != "closed" or termination != end["payload"]
                or termination.get("status") not in {"bounded_work_closed", "workers_done", "blocked_no_reachable_events"}
                or termination.get("execution_integrity_failure") is not None
                or termination.get("role_stops", {}).get(member_id) != boundary["payload"].get("status")):
            return None
        ledger = boundary["payload"].get("team_budget")
        final_wrapper = termination.get("team_budget", {})
        final = final_wrapper.get("model")
        if (final_wrapper.get("world_instance_id") != rollout["manifest"].get("identity", {}).get("instance_id")
                or not _sealed_team_ledger(ledger, rollout, identity)
                or not _sealed_team_ledger(final, rollout, identity)
                or ledger["limits"] != final["limits"]
                or any(final["records"].get(key) != value for key, value in ledger["records"].items())):
            return None
        row = ledger["records"].get(call_id, {})
        reservation = metadata.get("reservation", {})
        prepared = reservation.get("preparation", {})
        if (row.get("member") != member_id or row.get("call_id") != call_id
                or row.get("status") != "admission_rejected" or row.get("attempt_started") is not False
                or row.get("rejected_reservation") != reservation or "charge" in row or "reservation" in row
                or reservation.get("reservation_kind") != "exact_resident_prompt"
                or any(type(reservation.get(key)) is not int or reservation[key] <= 0 for key in (
                    "request_bytes", "input_token_reservation", "output_token_reservation", "token_reservation"))
                or prepared.get("version") != "resident-request-budget-v0.31r3"
                or prepared.get("preparation_sha256") != digest(json_bytes({key: value for key, value in prepared.items()
                                                                          if key != "preparation_sha256"}))
                or any(not _sha256_text(prepared.get(key)) for key in (
                    "original_request_sha256", "selected_request_sha256", "rendered_prompt_sha256",
                    "input_ids_sha256", "recipe_sha256"))
                or prepared.get("original_request_sha256") != metadata.get("request_sha256")
                or metadata.get("context_selection", {}).get("request_sha256") != metadata.get("request_sha256")
                or prepared.get("actor_identity") != identity
                or prepared.get("window_id") != rollout["window"]["window_id"]
                or prepared.get("context_limit") != config.get("max_context_tokens")
                or prepared.get("reserved_output_tokens") != config.get("max_output_tokens")
                or any(type(prepared.get(key)) is not int or prepared[key] <= 0
                       for key in ("prompt_tokens", "reserved_output_tokens", "context_limit"))
                or prepared["reserved_output_tokens"] >= prepared["context_limit"]
                or reservation.get("input_token_reservation") != prepared["prompt_tokens"]
                or reservation.get("output_token_reservation") != prepared["reserved_output_tokens"]
                or reservation.get("token_reservation") != prepared["prompt_tokens"] + prepared["reserved_output_tokens"]
                or type(prepared.get("fits")) is not bool
                or prepared["fits"] != (reservation["token_reservation"] <= prepared["context_limit"])):
            return None
        binding = {key: prepared[key] for key in ("actor_identity", "window_id", "recipe_sha256")}
        if any(value.get("binding") is not None and value["binding"] != binding for value in (ledger, final)):
            return None
        limits = []
        if not prepared["fits"]:
            if boundary["payload"].get("status") != "model_budget_exhausted" or any(
                    value.get("budget_kind") != "context_capacity" for value in (row, boundary["payload"])):
                return None
            limits = ["context_capacity"]
        else:
            if boundary["payload"].get("status") != "team_budget_exhausted":
                return None
            if ledger["attempts"] >= ledger["limits"]["max_attempts"]:
                limits.append("team_max_attempts")
            if reservation["token_reservation"] > ledger["available_tokens"]:
                limits.append("team_max_total_tokens")
        if not limits or row.get("admission_limits") != limits or boundary["payload"].get("limits") != limits:
            return None
        return {"version": SHARED_ADMISSION_PROOF_VERSION, "limits": limits,
                "boundary_event_sequence": boundary["sequence"], "final_boundary_event_sequence": end["sequence"],
                "boundary_ledger_sha256": ledger["state_sha256"], "final_ledger_sha256": final["state_sha256"],
                "preparation_sha256": prepared["preparation_sha256"], "request_sha256": metadata["request_sha256"],
                "generation_attempts": 0, "tokens_charged": 0, "held_tokens": 0,
                "scope": "Existing request/boundary/final-ledger evidence only; no generated response or tokens exist for this rejected decision"}
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


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
            shared_stop = _known_shared_admission_stop(rollout, start, member_id)
            if shared_stop is not None:
                record.update(generation_status="not_started_shared_admission_rejection", actor_required=False,
                              non_generation_contract=SHARED_ADMISSION_PROOF_VERSION,
                              non_generation_evidence=shared_stop)
                decisions.append(record)
                continue
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
