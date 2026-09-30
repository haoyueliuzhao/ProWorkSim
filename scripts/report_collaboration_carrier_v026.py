"""Read saved C1 receipts and assessments; never load a model or regrade a world.

The pure ``summarize`` function accepts already loaded archive dictionaries.
Initial counterfactual inputs use untouched request dictionaries and the existing
JSON serializer: no field dropping, key sorting or identifier normalization.
"""

import argparse
from collections import Counter, defaultdict
import copy
from datetime import datetime, timezone
import json
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes, read_json
from scripts.collaboration_evidence_v026 import nodes, request_nodes

VERSION = "reciprocal-carrier-report-v0.26"
CONDITIONS = ("normal", "single_pass")
MEMBERS = ("maintainer", "consumer")
TERMINAL = {"complete", "closed_with_incomplete_workers", "supervisor_error"}
TERMS = (
    "correct_current_source_delivery",
    "correct_current_consumer_delivery",
    "reciprocal_consumption_and_revalidation",
)
TERM_LABELS = {
    TERMS[0]: "正确源端固定交付",
    TERMS[1]: "正确消费端固定交付",
    TERMS[2]: "双向消费与最终再验证",
}
KEY_ACTIONS = {
    "request_information",
    "handoff_information",
    "adopt",
    "adopt_version",
    "write_object",
    "sql_build",
    "sql_query",
    "submit",
    "withdraw",
    "inspect_submission",
    "raise_issue",
    "respond_issue",
    "decide_issue",
    "approve",
}


def file_reference(path):
    path = Path(path).resolve()
    import hashlib

    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return {"path": str(path), "sha256": sha.hexdigest(), "bytes": path.stat().st_size}


def checked_reference(value):
    path = Path(value["path"])
    actual = file_reference(path)
    if actual["sha256"] != value["sha256"] or (
        "bytes" in value and actual["bytes"] != value["bytes"]
    ):
        raise ValueError("Saved artifact reference changed: " + str(path))
    return path


def _dict(value):
    return value if isinstance(value, dict) else {}


def _ref(value):
    value = _dict(value)
    if isinstance(value.get("object_id"), str) and isinstance(value.get("version_id"), str):
        return value["object_id"], value["version_id"]
    return None


def _public_request(record):
    return {key: copy.deepcopy(value) for key, value in record.items() if not key.startswith("_")}


def actual_requests(events):
    """Join exact started/finished attempts; retain rejected/no-generation inputs."""
    calls, attempts, errors = {}, {}, []
    generated = {
        (event.get("worker_id"), _dict(event.get("payload")).get("call_id"))
        for event in events
        if event.get("kind") == "model_response"
    }
    for event in events:
        payload = _dict(event.get("payload"))
        role, call = event.get("worker_id"), payload.get("call_id")
        if event.get("kind") == "model_call" and payload.get("stage") == "started":
            calls[role, call] = event
        if event.get("kind") != "model_attempt" or not isinstance(payload.get("request"), dict):
            continue
        key = role, payload.get("attempt_id", call)
        request, sha = payload["request"], digest(json_bytes(payload["request"]))
        if key in attempts and attempts[key]["request_sha256"] != sha:
            errors.append(
                {
                    "kind": "started_finished_request_mismatch",
                    "sequence": event.get("sequence"),
                    "role": role,
                    "call_id": call,
                }
            )
        if key not in attempts or payload.get("stage") == "started":
            start = calls.get((role, call))
            expected = _dict(start.get("payload")).get("request_sha256") if start else None
            if expected and expected != sha:
                errors.append(
                    {
                        "kind": "request_digest_differs_from_call_record",
                        "sequence": event.get("sequence"),
                        "role": role,
                        "call_id": call,
                    }
                )
            attempts[key] = {
                "role": role,
                "call_id": call,
                "attempt_id": payload.get("attempt_id"),
                "decision_index": payload.get("decision_index"),
                "sequence": start.get("sequence") if start else event.get("sequence"),
                "request_event_sequence": event.get("sequence"),
                "request_sha256": sha,
                "request_source": (
                    "original_model_call_audit_file; global sequence unavailable"
                    if event.get("source_file")
                    else "runtime.experience.events/model_attempt/payload/request"
                ),
                "source_file": event.get("source_file"),
                "generation_observed": (role, call) in generated,
                "_request": request,
                "_references": set(),
                "_contents": {},
                "_entities": set(),
                "_tables": set(),
            }
        record = attempts[key]
        if payload.get("stage") == "finished":
            record["attempt_status"] = payload.get("status")
            record["http_status"] = _dict(payload.get("response")).get("http_status")
    records = sorted(
        attempts.values(),
        key=lambda row: (
            row["sequence"] is None,
            row["sequence"] if row["sequence"] is not None else row.get("decision_index", 0),
        ),
    )
    for record in records:
        for pointer, value in request_nodes(record["_request"]):
            if not isinstance(value, dict):
                continue
            ref = _ref(value)
            if ref:
                record["_references"].add(ref)
            content_ref = _ref(value.get("reference"))
            if content_ref and "data" in value:
                record["_references"].add(content_ref)
                record["_contents"][content_ref] = {
                    "data_sha256": digest(json_bytes(value["data"])),
                    "pointer": pointer,
                }
                record["_tables"].update(_dict(_dict(value["data"]).get("tables")))
            for key in (
                "request_id",
                "handoff_id",
                "submission_id",
                "pending_submission_id",
                "latest_submission_id",
                "issue_id",
                "response_id",
            ):
                if isinstance(value.get(key), str):
                    normalized = (
                        "submission_id"
                        if key in {"pending_submission_id", "latest_submission_id"}
                        else key
                    )
                    record["_entities"].add((normalized, value[key]))
    return records, errors


def input_occurrence(requests, role, after, *, reference=None, entity=None, data_sha256=None):
    matches = []
    for request in requests:
        if request["role"] != role or request["sequence"] is None or request["sequence"] <= after:
            continue
        content = request["_contents"].get(reference) if reference else None
        match = entity in request["_entities"] if entity else reference in request["_references"]
        if data_sha256 is not None:
            match = bool(content and content["data_sha256"] == data_sha256)
        if match:
            row = _public_request(request)
            if content:
                row["content_pointer"] = content["pointer"]
                row["content_sha256"] = content["data_sha256"]
            matches.append(row)
    return {
        "first_request_input": matches[0] if matches else None,
        "first_input_with_generation": next(
            (row for row in matches if row["generation_observed"]), None
        ),
    }


def action_summary(event):
    payload = _dict(event.get("payload"))
    response = _dict(payload.get("response"))
    result = _dict(response.get("result"))
    args = _dict(payload.get("arguments"))
    result_ref = _ref(result.get("reference")) or _ref(result)
    return {
        "sequence": event["sequence"],
        "role": event.get("worker_id"),
        "action": payload.get("action"),
        "tool_ok": response.get("ok"),
        "model_call_id": payload.get("model_call_id"),
        "arguments_sha256": digest(json_bytes(args)),
        "argument_scope": {
            key: copy.deepcopy(args[key])
            for key in (
                "alias",
                "work_id",
                "work_ids",
                "reference",
                "object_id",
                "version_id",
                "dependencies",
                "evidence",
                "input_aliases",
                "output_alias",
                "code_alias",
                "source_alias",
                "submission_id",
                "request_id",
                "route_id",
                "issue_id",
                "response_id",
                "decision",
            )
            if key in args
        },
        "result_reference": list(result_ref) if result_ref else None,
        "submission_id": result.get("submission_id"),
        "execution_status": result.get("execution_status"),
        "error": copy.deepcopy(
            response.get("error") or result.get("error") or payload.get("exception")
        ),
    }


def collaboration_layers(events, requests, start, end, assessment):
    """Recorded events and exact references; no causal or business re-evaluation."""
    actions = [event for event in events if event.get("kind") == "tool_call"]
    successful = [
        event
        for event in actions
        if _dict(_dict(event.get("payload")).get("response")).get("ok") is True
    ]
    artifacts = {key: artifact for key, artifact in end.get("artifacts", {}).items()}
    artifacts.update(
        {artifact.get("object_id", key): artifact for key, artifact in list(artifacts.items())}
    )
    records = []
    for event in successful:
        payload = event["payload"]
        result = _dict(payload["response"].get("result"))
        action, sender, seq = payload["action"], event.get("worker_id"), event["sequence"]
        if action not in {
            "handoff_information",
            "request_information",
            "submit",
            "write_object",
            "sql_build",
            "sql_query",
            "raise_issue",
            "respond_issue",
            "decide_issue",
            "approve",
        }:
            continue
        row = {
            "action": action,
            "origin": "current_runtime_action",
            "send_or_write": action_summary(event),
            "sender": sender,
            "recipients": [member for member in MEMBERS if member != sender],
            "delivery_or_access": [],
            "actual_input": {},
            "execution_use": [],
            "scope": "Exact archived relationships only; sending/access/input/use/closure are different observations. No causal contribution inferred.",
        }
        reference = _ref(result.get("reference")) or _ref(result)
        entity = None
        if action == "handoff_information":
            handoff = _dict(end.get("handoffs", {}).get(result.get("handoff_id")))
            row["recipients"] = handoff.get("recipients", row["recipients"])
            reference = _ref(handoff.get("reference")) or _ref(
                _dict(payload.get("arguments")).get("reference")
            )
            entity = ("handoff_id", result.get("handoff_id"))
            row["request_id"] = handoff.get("request_id")
            row["body"] = handoff.get("body", _dict(payload.get("arguments")).get("body"))
            row["delivery_state"] = handoff.get("status")
            for env in events:
                ep = _dict(env.get("payload"))
                if env.get("kind") == "environment_event" and ep.get("event_id") == result.get(
                    "event_id"
                ):
                    row["delivery_or_access"].append(
                        {
                            "kind": "environment_transport",
                            "sequence": env["sequence"],
                            "outcome": ep.get("outcome"),
                        }
                    )
        elif action == "request_information":
            entity = ("request_id", result.get("request_id"))
            request = _dict(end.get("requests", {}).get(result.get("request_id")))
            row["recipients"] = (
                [request["requested_role"]] if request.get("requested_role") else row["recipients"]
            )
        elif action in {"submit", "approve"}:
            entity = (
                "submission_id",
                result.get("submission_id") or _dict(payload.get("arguments")).get("submission_id"),
            )
            row["artifact_versions"] = copy.deepcopy(result.get("artifact_versions", {}))
        elif action in {"raise_issue", "respond_issue", "decide_issue"}:
            key = "response_id" if action == "respond_issue" else "issue_id"
            entity = (key, result.get(key) or _dict(payload.get("arguments")).get(key))
        if reference:
            row["reference"] = list(reference)
            row["alias"] = artifacts.get(reference[0], {}).get("alias")
            inherited = reference[1] in start.get("artifacts", {}).get(reference[0], {}).get(
                "versions", {}
            )
            row["referenced_version_origin"] = (
                "inherited_initial_version" if inherited else "current_episode_version"
            )
        if entity and entity[1]:
            row["entity"] = list(entity)
        for recipient in row["recipients"]:
            levels = {}
            if entity and entity[1]:
                levels["entity_in_input"] = input_occurrence(
                    requests, recipient, seq, entity=entity
                )
            if reference:
                levels["reference_in_input"] = input_occurrence(
                    requests, recipient, seq, reference=reference
                )
                reads = []
                for other in successful:
                    op = other["payload"]
                    returned = _dict(op["response"].get("result"))
                    if (
                        other.get("worker_id") == recipient
                        and other["sequence"] > seq
                        and op["action"] in {"read_alias", "read_version", "read_object"}
                        and _ref(returned.get("reference")) == reference
                        and "data" in returned
                    ):
                        reads.append(
                            {
                                "read_sequence": other["sequence"],
                                **input_occurrence(
                                    requests,
                                    recipient,
                                    other["sequence"],
                                    reference=reference,
                                    data_sha256=digest(json_bytes(returned["data"])),
                                ),
                            }
                        )
                        row["delivery_or_access"].append(
                            {
                                "kind": "successful_exact_version_read",
                                "recipient": recipient,
                                "sequence": other["sequence"],
                            }
                        )
                levels["exact_read_content_in_later_input"] = reads
            row["actual_input"][recipient] = levels
        for later in successful:
            la = _dict(later["payload"].get("arguments"))
            if later["sequence"] <= seq or later.get("worker_id") not in row["recipients"]:
                continue
            same_ref = reference and (
                _ref(la) == reference
                or _ref(la.get("reference")) == reference
                or any(
                    _ref(value) == reference
                    for value in la.get("dependencies", []) + la.get("evidence", [])
                )
            )
            same_entity = entity and entity[1] and la.get(entity[0]) == entity[1]
            if same_ref or same_entity:
                row["execution_use"].append(action_summary(later))
        records.append(row)
    return {
        "records": records,
        "saved_qualified_execution_and_closure": copy.deepcopy(assessment.get("facts", {})),
        "qualification_source": "assessment.json/facts; copied unchanged, not recomputed",
        "causal_effect": None,
        "message_or_arrow_count_is_outcome": False,
    }


def call_counts(events):
    responses = [
        _dict(event.get("payload")).get("response")
        for event in events
        if event.get("kind") == "model_response"
    ]
    responses = [response for response in responses if isinstance(response, dict)]
    attempts = [
        _dict(event.get("payload"))
        for event in events
        if event.get("kind") == "model_attempt"
        and _dict(event.get("payload")).get("stage") == "finished"
    ]
    return {
        "requests": sum(
            event.get("kind") == "model_call"
            and _dict(event.get("payload")).get("stage") == "started"
            for event in events
        ),
        "attempts_started": sum(
            event.get("kind") == "model_attempt"
            and _dict(event.get("payload")).get("stage") == "started"
            for event in events
        ),
        "responses": len(responses),
        "responses_with_actual_token_trace": sum(
            bool(_dict(response.get("token_trace")).get("output_ids")) for response in responses
        ),
        "raw_text_responses": sum(
            isinstance(response.get("raw_generated_text"), str) for response in responses
        ),
        "backend_context_limits": sum(
            attempt.get("status") == "backend_context_limit" for attempt in attempts
        ),
        "model_boundaries": sum(event.get("kind") == "model_boundary_error" for event in events),
        "tool_calls": sum(event.get("kind") == "tool_call" for event in events),
        "tool_refusals": sum(
            event.get("kind") == "tool_call"
            and _dict(_dict(event.get("payload")).get("response")).get("ok") is False
            for event in events
        ),
        "prompt_tokens": sum(
            _dict(response.get("usage")).get("prompt_tokens", 0) for response in responses
        ),
        "completion_tokens": sum(
            _dict(response.get("usage")).get("completion_tokens", 0) for response in responses
        ),
        "finish_reasons": dict(
            Counter(
                choice.get("finish_reason")
                for response in responses
                for choice in response.get("choices", [])
            )
        ),
        "scope": "Requests, generated responses, context refusals and pre-request boundaries are separate; CPU fixture responses without token traces are never labeled real model generations.",
    }


def slot_summary(slot, package):
    row, assessment = _dict(package.get("row")), _dict(package.get("assessment"))
    events = package.get("events", [])
    requests, errors = actual_requests(events)
    started = bool(row or package.get("manifest") or events or assessment)
    known = row.get("status") == "closed" and assessment.get("eligible") is True and not errors
    status = "known" if known else "unknown_started" if started else "not_started"
    boundary = (
        _dict(row.get("boundary"))
        or _dict(assessment.get("termination"))
        or _dict(_dict(package.get("manifest")).get("termination"))
    )
    components = {term["term_id"]: copy.deepcopy(term) for term in assessment.get("components", [])}
    boundaries = [
        {
            "sequence": event["sequence"],
            "role": event.get("worker_id"),
            "kind": event["kind"],
            "details": copy.deepcopy(event.get("payload")),
        }
        for event in events
        if event.get("kind")
        in {"model_boundary_error", "interface_error", "binding_error", "policy_error"}
    ]
    key_actions = [
        action_summary(event)
        for event in events
        if event.get("kind") == "tool_call"
        and _dict(event.get("payload")).get("action") in KEY_ACTIONS
    ]
    facts = copy.deepcopy(assessment.get("facts", {}))
    failures = [
        {"type": "unsatisfied_saved_component", "term_id": key}
        for key, value in components.items()
        if value.get("achieved") is False
    ]
    failures += copy.deepcopy(assessment.get("exclusions", []))
    failures += [
        {"type": "tool_refusal_or_execution_error", **action}
        for action in key_actions
        if action["tool_ok"] is False or action.get("error")
    ]
    if row.get("error"):
        failures.append(copy.deepcopy(row["error"]))
    return {
        **copy.deepcopy(slot),
        "archive_status": status,
        "worker": package.get("worker"),
        "saved_row_status": row.get("status"),
        "score": assessment.get("reward") if known else None,
        "complete": assessment.get("completed") if known else None,
        "saved_assessment": assessment,
        "components": components,
        "saved_facts": facts,
        "role_stops": boundary.get("role_stops", {}),
        "call_counts": call_counts(events),
        "key_actions": key_actions,
        "boundary_events": boundaries,
        "failure_observations": failures,
        "input_integrity_errors": errors,
        "state_guard": copy.deepcopy(package.get("guard") or row.get("evaluation_guard")),
        "collaboration": collaboration_layers(
            events, requests, _dict(package.get("start")), _dict(package.get("end")), assessment
        ),
        "sources": copy.deepcopy(package.get("sources", {})),
        "_requests": requests,
        "_events": events,
    }


def group_summary(rows):
    known = [row for row in rows if row["archive_status"] == "known"]
    return {
        "scheduled": len(rows),
        "known": len(known),
        "unknown_started": sum(row["archive_status"] == "unknown_started" for row in rows),
        "not_started": sum(row["archive_status"] == "not_started" for row in rows),
        "complete_count": sum(row["complete"] is True for row in known),
        "complete_rate_known": sum(row["complete"] is True for row in known) / len(known)
        if known
        else None,
        "complete_rate_all_scheduled": sum(row["complete"] is True for row in known) / len(rows)
        if rows and len(known) == len(rows)
        else None,
        "mean_score_known": sum(row["score"] for row in known) / len(known) if known else None,
        "mean_score_all_scheduled": sum(row["score"] for row in known) / len(rows)
        if rows and len(known) == len(rows)
        else None,
        "components": {
            term: {
                "achieved_count": sum(
                    row["components"].get(term, {}).get("achieved") is True for row in known
                ),
                "mean_score_known": sum(
                    row["components"].get(term, {}).get("score", 0) for row in known
                )
                / len(known)
                if known
                else None,
            }
            for term in TERMS
        },
    }


def paired_summary(rows):
    pairs = defaultdict(dict)
    for row in rows:
        pairs[row["case_id"], row["repeat_index"]][row["condition"]] = row
    records = []
    for (case, repeat), members in pairs.items():
        left, right = members.get("normal"), members.get("single_pass")
        known = bool(
            left and right and left["archive_status"] == right["archive_status"] == "known"
        )
        records.append(
            {
                "case_id": case,
                "repeat_index": repeat,
                "prototype": (left or right)["prototype"],
                "normal_slot": left["slot_id"] if left else None,
                "single_pass_slot": right["slot_id"] if right else None,
                "known_pair": known,
                "normal_minus_single_pass_complete": int(left["complete"]) - int(right["complete"])
                if known
                else None,
                "normal_minus_single_pass_score": left["score"] - right["score"] if known else None,
                "component_achievement_differences": {
                    term: int(left["components"].get(term, {}).get("achieved", False))
                    - int(right["components"].get(term, {}).get("achieved", False))
                    for term in TERMS
                }
                if known
                else None,
            }
        )
    valid = [record for record in records if record["known_pair"]]
    complete = bool(records) and len(valid) == len(records)
    mean_complete = (
        sum(record["normal_minus_single_pass_complete"] for record in valid) / len(valid)
        if valid
        else None
    )
    return {
        "pairs": records,
        "scheduled_pairs": len(records),
        "known_pairs": len(valid),
        "mean_complete_difference_all_pairs": mean_complete if complete else None,
        "mean_complete_difference_known_pairs_descriptive": mean_complete,
        "mean_score_difference_all_pairs": sum(
            record["normal_minus_single_pass_score"] for record in valid
        )
        / len(valid)
        if complete
        else None,
        "component_achievement_differences_all_pairs": {
            term: sum(record["component_achievement_differences"][term] for record in valid)
            / len(valid)
            for term in TERMS
        }
        if complete
        else None,
        "interpretation": "Communication-condition development contrast; not parameter learning or allocation-algorithm benefit. Missing/unknown pairs are not assigned zero.",
    }


def request_differences(left, right, path="", limit=12):
    """Explain differences without changing the compared original serialization."""
    result = []
    if type(left) is not type(right):
        return [
            {
                "path": path or "/",
                "kind": "type",
                "left": type(left).__name__,
                "right": type(right).__name__,
            }
        ]
    if isinstance(left, dict):
        if list(left) != list(right):
            result.append(
                {
                    "path": path or "/",
                    "kind": "mapping_keys_or_order",
                    "left": list(left),
                    "right": list(right),
                }
            )
        for key in dict.fromkeys([*left, *right]):
            if key not in left or key not in right:
                continue
            result.extend(request_differences(left[key], right[key], path + "/" + str(key), limit))
            if len(result) >= limit:
                break
    elif isinstance(left, list):
        if len(left) != len(right):
            result.append(
                {"path": path, "kind": "list_length", "left": len(left), "right": len(right)}
            )
        for index, (a, b) in enumerate(zip(left, right)):
            result.extend(request_differences(a, b, path + "/" + str(index), limit))
            if len(result) >= limit:
                break
    elif left != right:
        if isinstance(left, str):
            offset = next(
                (i for i, (a, b) in enumerate(zip(left, right)) if a != b),
                min(len(left), len(right)),
            )
            result.append(
                {
                    "path": path,
                    "kind": "string",
                    "first_difference_offset": offset,
                    "left_excerpt": left[max(0, offset - 100) : offset + 200],
                    "right_excerpt": right[max(0, offset - 100) : offset + 200],
                    "left_characters": len(left),
                    "right_characters": len(right),
                }
            )
        else:
            result.append({"path": path, "kind": "value", "left": left, "right": right})
    return result[:limit]


def counterfactual_inputs(rows, catalog):
    case_info = {case["case_id"]: case for case in catalog["cases"]}
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["prototype"], row["condition"], row["repeat_index"]].append(row)
    result = []
    for (prototype, condition, repeat), pair in grouped.items():
        pair.sort(key=lambda row: row["case_id"])
        member = case_info[pair[0]["case_id"]].get(
            "counterfactual_member", "maintainer" if prototype == "demand_pair" else "consumer"
        )
        first = [
            next((request for request in row["_requests"] if request["role"] == member), None)
            for row in pair
        ]
        known = len(pair) == 2 and all(first)
        equal = first[0]["request_sha256"] == first[1]["request_sha256"] if known else None
        result.append(
            {
                "prototype": prototype,
                "condition": condition,
                "repeat_index": repeat,
                "restricted_member": member,
                "slots": [row["slot_id"] for row in pair],
                "status": "equal"
                if equal is True
                else "different"
                if equal is False
                else "unavailable",
                "requests": [_public_request(request) if request else None for request in first],
                "request_hash_equal": equal,
                "first_request_already_contains_structured_distinguishing_material": [
                    bool(
                        request
                        and request["_tables"]
                        & (
                            {"demand_meta"}
                            if member == "maintainer"
                            else {"source_meta", "interface_meta"}
                        )
                    )
                    for request in first
                ],
                "differences": request_differences(first[0]["_request"], first[1]["_request"])
                if known and not equal
                else [],
                "scope": "First actual request of the restricted member, before its own earlier tool action. Partner actions or supplied observations may already differ. Strict original JSON dictionary serialization; no identifier, model, text, key order or field normalization. Table receipts do not exhaust possible natural-language disclosure.",
            }
        )
    return {
        "comparisons": result,
        "counts": dict(Counter(row["status"] for row in result)),
        "all_planned_comparisons_available_and_equal": bool(result)
        and all(row["status"] == "equal" for row in result),
        "comparison_serialization": "proworksim.storage.json_bytes(raw_request): UTF-8, indent=2, original mapping insertion order, ensure_ascii=False, allow_nan=False, trailing newline; SHA256",
        "claim_limit": "Equal initial inputs support this finite interface check only; neither learning value nor later information use is inferred.",
    }


def summarize(plan, catalog, supervisor, workers, episodes, *, sources=None):
    """Pure summary over saved dictionaries; no file reads, model load or grading."""
    slots = catalog["slots"]
    rows = [slot_summary(slot, episodes.get(slot["slot_id"], {})) for slot in slots]
    conditions = {
        condition: group_summary([row for row in rows if row["condition"] == condition])
        for condition in CONDITIONS
    }
    grouped = {}
    for field in ("prototype", "case_id", "repeat_index"):
        grouped[field] = {
            str(value): {
                "all_conditions": group_summary([row for row in rows if row[field] == value]),
                "by_condition": {
                    condition: group_summary(
                        [
                            row
                            for row in rows
                            if row[field] == value and row["condition"] == condition
                        ]
                    )
                    for condition in CONDITIONS
                },
                "paired": paired_summary([row for row in rows if row[field] == value]),
            }
            for value in dict.fromkeys(row[field] for row in rows)
        }
    learning, costs = {}, {}
    for name, worker in workers.items():
        state, report, restore = (
            _dict(worker.get("state")),
            _dict(worker.get("report")),
            _dict(worker.get("restoration")),
        )
        actor_delta = (
            report["actor_steps"] - restore["actor_steps"]
            if type(report.get("actor_steps")) is int and type(restore.get("actor_steps")) is int
            else None
        )
        critic_delta = (
            report["critic_steps"] - restore["critic_steps"]
            if type(report.get("critic_steps")) is int and type(restore.get("critic_steps")) is int
            else None
        )
        learning[name] = {
            "actor_steps_before": restore.get("actor_steps"),
            "actor_steps_after": report.get("actor_steps"),
            "critic_steps_before": restore.get("critic_steps"),
            "critic_steps_after": report.get("critic_steps"),
            "observed_actor_step_delta": actor_delta,
            "observed_critic_step_delta": critic_delta,
            "actor_identity_unchanged": report.get("final_actor_identity")
            == restore.get("actor_identity")
            if restore.get("actor_identity")
            else None,
            "strict_restore": restore.get("strict_restore_executed"),
            "full_state_digest_equal": restore.get("state_tensor_digest")
            == restore.get("restored_state_tensor_digest")
            if restore.get("state_tensor_digest")
            else None,
            "original_marker_unchanged": restore.get("old_marker_bytes_unchanged"),
            "source_unchanged": report.get("source_unchanged"),
            "old_source": restore.get("old_worker_source"),
            "new_source": report.get("source_before"),
        }
        ended = state.get("elapsed_gpu_seconds")
        running = state.get("status") == "running" and type(state.get("started_at")) in (int, float)
        costs[name] = {
            "status": state.get("status"),
            "gpu": state.get("gpu"),
            "gpu_uuid": state.get("gpu_uuid"),
            "started_at": state.get("started_at"),
            "ended_at": state.get("ended_at"),
            "terminated_gpu_seconds": ended,
            "running_gpu_seconds_at_snapshot": max(
                0, supervisor.get("observed_at", state.get("started_at", 0)) - state["started_at"]
            )
            if running
            else 0,
            "budget_seconds": state.get("budget_seconds"),
            "stop_reason": state.get("stop_reason"),
            "exit_code": state.get("exit_code"),
        }
    counts = {
        key: sum(row["call_counts"][key] for row in rows)
        for key in (
            "requests",
            "attempts_started",
            "responses",
            "responses_with_actual_token_trace",
            "raw_text_responses",
            "backend_context_limits",
            "model_boundaries",
            "tool_calls",
            "tool_refusals",
            "prompt_tokens",
            "completion_tokens",
        )
    }
    cf = counterfactual_inputs(rows, catalog)
    result = {
        "version": VERSION,
        "run_status": supervisor.get("status"),
        "terminal": supervisor.get("status") in TERMINAL and bool(supervisor.get("ended_at")),
        "scope": "C1 frozen-parameter carrier development: communication-condition comparison, no learning or allocation effect test. Existing assessment values and eligibility are copied, never replayed or regraded.",
        "plan": {
            key: copy.deepcopy(plan.get(key))
            for key in (
                "version",
                "max_new_episodes",
                "max_new_actor_steps",
                "max_new_critic_steps",
                "model_api_calls",
                "automatic_successors",
                "checkpoint_marker",
                "source_pin",
                "catalog",
                "internal_gpu_seconds",
                "resource_caps",
                "gpu_preference",
                "queue_deadline_at",
                "previous_attempt",
            )
        },
        "overall": group_summary(rows),
        "by_condition": conditions,
        "paired_conditions": paired_summary(rows),
        "groups": grouped,
        "counterfactual_initial_inputs": cf,
        "call_counts": counts,
        "learning_state": learning,
        "all_observed_workers_zero_updates": (
            all(
                value["observed_actor_step_delta"] == value["observed_critic_step_delta"] == 0
                for value in learning.values()
            )
            if learning
            and all(
                value["observed_actor_step_delta"] is not None
                and value["observed_critic_step_delta"] is not None
                for value in learning.values()
            )
            else None
        ),
        "closed_slot_guard_counts": dict(
            Counter(
                "unchanged"
                if _dict(row["state_guard"]).get("learning_unchanged") is True
                and _dict(row["state_guard"]).get("rng_restored_exactly") is True
                else "missing_or_failed"
                for row in rows
                if row["archive_status"] == "known"
            )
        ),
        "resources": {
            "workers": costs,
            "terminated_gpu_seconds": sum(
                value["terminated_gpu_seconds"] or 0 for value in costs.values()
            ),
            "running_gpu_seconds_at_snapshot": sum(
                value["running_gpu_seconds_at_snapshot"] for value in costs.values()
            ),
            "scope": "Sum each owned worker's stage elapsed time, including loading and stopping. Parallel wall duration is not GPU time; old v025 cost is not erased or reclassified as C1.",
        },
        "sources": copy.deepcopy(sources or {}),
        "episodes": [
            {key: value for key, value in row.items() if not key.startswith("_")} for row in rows
        ],
        "limitations": [
            "Four situations and two repeats per condition are a development sample, not a power guarantee or independent-source generalization.",
            "Known business failure, started unknown and not started remain separate. Unknown/missing scores and paired points are null, never zero-filled.",
            "A successful tool receipt is not business correctness. Saved qualified fixed builds and revalidation come only from the original assessment facts.",
            "Information written, delivered, entered into an input, subsequently referenced and closed are separate recorded layers. No causal contribution follows from arrow/message counts.",
            "Single-pass constrains the extra explanatory channel; ordinary artifacts, SQL and formal review still carry information in both conditions.",
            "No parameter update, method-support admission, composition q/b intervention or algorithm increment is inferred from this report.",
        ],
    }
    if plan.get("previous_attempt"):
        previous = plan["previous_attempt"]
        result["resources"].update(
            previous_attempt_gpu_seconds=previous["actual_gpu_seconds"],
            previous_attempt_budget_charge_seconds=previous["budget_charge_seconds"],
            cumulative_terminated_gpu_seconds=(
                previous["actual_gpu_seconds"] + result["resources"]["terminated_gpu_seconds"]
            ),
            original_total_gpu_seconds_cap=14400,
        )
    return result


def load_run(run, *, require_terminal=False):
    """Read one saved snapshot; immutable episode hashes are checked, never replayed."""
    run = Path(run).resolve()
    supervisor_path = run / "supervisor.json"
    supervisor = read_json(supervisor_path)
    if require_terminal and (
        supervisor.get("status") not in TERMINAL or not supervisor.get("ended_at")
    ):
        raise ValueError("Require a closed supervisor before terminal reporting")
    plan_path = checked_reference(supervisor["plan"])
    plan = read_json(plan_path)
    if plan.get("previous_attempt"):
        from scripts.collaboration_carrier_v026 import validate_previous_loading_attempt

        validate_previous_loading_attempt(plan)
    catalog_path = checked_reference(plan["catalog"])
    catalog = read_json(catalog_path)
    sources = {
        "supervisor": file_reference(supervisor_path),
        "plan": file_reference(plan_path),
        "catalog": file_reference(catalog_path),
    }
    for key in ("checkpoint_marker", "source_pin", "owner_recipe", "prior_model_plan"):
        sources[key] = file_reference(checked_reference(plan[key]))
    workers, episodes = {}, {}
    for name, slots in supervisor.get("worker_assignments", {}).items():
        directory = run / name
        worker = {"sources": {}}
        for key, relative in (
            ("state", "state.json"),
            ("report", "actual/report.json"),
            ("restoration", "actual/cross-source-restore-proof.json"),
        ):
            path = directory / relative
            if path.exists():
                worker[key] = read_json(path)
                worker["sources"][key] = file_reference(path)
        workers[name] = worker
        sources[name] = worker["sources"]
        progress_path = directory / "actual/progress.json"
        progress = (
            read_json(progress_path)
            if progress_path.exists()
            else worker.get("report", {}).get("rows", [])
        )
        if progress_path.exists():
            worker["sources"]["progress"] = file_reference(progress_path)
        row_index = {row["slot_id"]: row for row in progress}
        for slot in slots:
            folder = directory / "actual" / slot["slot_id"]
            package = {"worker": name, "row": row_index.get(slot["slot_id"], {}), "sources": {}}
            for key, relative in (
                ("assessment", "assessment.json"),
                ("guard", "evaluation-guard.json"),
                ("manifest", "episode/manifest.json"),
            ):
                path = folder / relative
                if path.exists():
                    package[key] = read_json(path)
                    package["sources"][key] = file_reference(path)
            if package["row"].get("assessment_ref"):
                checked_reference(package["row"]["assessment_ref"])
                if package.get("assessment") != package["row"].get("assessment"):
                    raise ValueError(
                        "Saved progress and original assessment differ: " + slot["slot_id"]
                    )
            manifest = package.get("manifest", {})
            manifest_sha = package.get("assessment", {}).get("episode_manifest_sha256")
            if manifest_sha and manifest_sha != package["sources"].get("manifest", {}).get(
                "sha256"
            ):
                raise ValueError("Saved assessment manifest digest changed")
            for boundary in ("start", "end"):
                if boundary in manifest:
                    spec = manifest[boundary]
                    state_path = folder / "episode" / spec["path"] / spec["state"]["path"]
                    state_ref = file_reference(state_path)
                    if state_ref["sha256"] != spec["state"]["sha256"]:
                        raise ValueError("Saved world boundary changed")
                    package[boundary] = read_json(state_path)
                    package["sources"][boundary] = state_ref
            runtime_path = folder / "runtime.json"
            if runtime_path.exists():
                package["events"] = read_json(runtime_path)["experience"]["events"]
                package["sources"]["runtime"] = file_reference(runtime_path)
            else:
                experience_path = folder / "episode/experience.json"
                if experience_path.exists():
                    package["events"] = read_json(experience_path)["events"]
                    package["sources"]["experience"] = file_reference(experience_path)
            if not package.get("events"):
                # A hard stop may precede runtime.json serialization. Read exact
                # independently saved requests, without inventing event sequence.
                raw_records = []
                for path in sorted((folder / "model-calls").glob("*/*.json")):
                    record = read_json(path)
                    payload = _dict(record.get("payload"))
                    raw_records.append(
                        {
                            **record,
                            "worker_id": payload.get("worker_id"),
                            "source_file": file_reference(path),
                        }
                    )
                stage_order = {
                    ("model_call", "started"): 0,
                    ("model_attempt", "started"): 1,
                    ("model_attempt", "finished"): 2,
                    ("model_response", None): 3,
                    ("model_call", "finished"): 4,
                }
                raw_records.sort(
                    key=lambda event: (
                        _dict(event.get("payload")).get("decision_index", 0),
                        str(_dict(event.get("payload")).get("call_id", "")),
                        stage_order.get(
                            (event.get("kind"), _dict(event.get("payload")).get("stage")), 5
                        ),
                    )
                )
                if raw_records:
                    package["events"] = raw_records
                    package["sources"]["raw_model_records"] = [
                        record["source_file"] for record in raw_records
                    ]
            if "experience" in manifest:
                experience_path = folder / "episode" / manifest["experience"]["path"]
                actual = file_reference(experience_path)
                if actual["sha256"] != manifest["experience"]["sha256"]:
                    raise ValueError("Original chronological experience changed")
                if package.get("events") != read_json(experience_path)["events"]:
                    raise ValueError("Runtime events differ from closed episode events")
                package["sources"]["experience"] = actual
            episodes[slot["slot_id"]] = package
    result = summarize(plan, catalog, supervisor, workers, episodes, sources=sources)
    result["run_root"] = str(run)
    result["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    return result


def _display(value, places=4):
    if value is None:
        return "未知 / 未取得"
    if type(value) is bool:
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(report):
    overall = report["overall"]
    paired = report["paired_conditions"]
    cost = report["resources"]
    lines = [
        "# v0.26 C1：冻结参数协作载体验证",
        "",
        f"运行状态：`{report['run_status']}`；终态归档：{_display(report['terminal'])}。",
        "",
        "本报告只读原评分、原角色事件及世界边界；没有重新评分或模型调用。本轮检验小型协作载体与沟通条件，不检验参数学习收益、成员经验配置或 ID-VTDO 增量。",
        "",
        f"预定 {overall['scheduled']} 槽：已知 {overall['known']}，已启动未知 {overall['unknown_started']}，未启动 {overall['not_started']}；已知完整职责 {overall['complete_count']}。未知和未启动均未记作 0。",
        "",
        "## 沟通条件与配对结果",
        "",
        "| 条件 | 预定 / 已知 / 未知 / 未启动 | 完整职责 | 已知均分 | 全预定完成率 |",
        "|---|---|---|---|---|",
    ]
    for condition, group in report["by_condition"].items():
        lines.append(
            f"| {condition} | {group['scheduled']} / {group['known']} / {group['unknown_started']} / {group['not_started']} | {group['complete_count']} / {group['known']} | {_display(group['mean_score_known'])} | {_display(group['complete_rate_all_scheduled'])} |"
        )
    lines += [
        "",
        f"normal − single_pass 的预定完整职责均差：**{_display(paired['mean_complete_difference_all_pairs'])}**；可用配对 {paired['known_pairs']}/{paired['scheduled_pairs']}。已知配对子集描述值：{_display(paired['mean_complete_difference_known_pairs_descriptive'])}，不替代缺失的全预定点估计。",
        "",
        "single_pass 只限制额外解释性交接；两臂保留 SQL、产物访问、正式交付和复核。因此这一差值也不是“有团队与无团队”比较。",
        "",
        "| 成果条款 | normal 达成 / 已知 | single_pass 达成 / 已知 | 全配对达成率差 |",
        "|---|---|---|---|",
    ]
    differences = paired["component_achievement_differences_all_pairs"] or {}
    for term in TERMS:
        a, b = report["by_condition"]["normal"], report["by_condition"]["single_pass"]
        lines.append(
            f"| {TERM_LABELS[term]} | {a['components'][term]['achieved_count']} / {a['known']} | {b['components'][term]['achieved_count']} / {b['known']} | {_display(differences.get(term))} |"
        )
    lines += [
        "",
        "## 原型、情境与重复",
        "",
        "| 分组 | normal 完整 / 已知 | single_pass 完整 / 已知 | 全配对完整职责差 |",
        "|---|---|---|---|",
    ]
    for dimension, groups in report["groups"].items():
        for name, group in groups.items():
            a, b = group["by_condition"]["normal"], group["by_condition"]["single_pass"]
            lines.append(
                f"| {dimension}={name} | {a['complete_count']} / {a['known']} | {b['complete_count']} / {b['known']} | {_display(group['paired']['mean_complete_difference_all_pairs'])} |"
            )
    lines += [
        "",
        "## 初始反事实实际输入",
        "",
        "以下取受限成员第一次真实 model_attempt 请求，直接对完整原字典序列化计算 SHA256。未删除 ID、系统提示、工具、模型标识或任何字段；mapping 顺序也保留。",
        "",
        "| 原型 / 条件 / 重复 | 受限成员 | 原始输入比较 | 原请求序号 |",
        "|---|---|---|---|",
    ]
    cf = report["counterfactual_initial_inputs"]
    for item in cf["comparisons"]:
        sequences = ", ".join(
            str(request["request_event_sequence"]) if request else "缺失"
            for request in item["requests"]
        )
        lines.append(
            f"| {item['prototype']} / {item['condition']} / {item['repeat_index']} | {item['restricted_member']} | {item['status']} | {sequences} |"
        )
        if item["differences"]:
            details = "; ".join(
                f"{value['path']} ({value['kind']})" for value in item["differences"]
            )
            lines.append(
                f"\n差异位置：`{details}`。完整原文差异片段及两份 SHA 见 JSON；不通过归一化隐藏差异。\n"
            )
    lines += [
        "",
        "这只核对有限初始输入；相同输入不自动证明后续使用，差异也需结合此前伙伴动作解释。未观察到结构化资料回执，不代表自然语言中绝无披露。",
        "",
        "## 逐槽工作与协作证据",
        "",
        "| 槽 | 状态 | 分数 / 完整职责 | 请求 / 响应 / 工具拒绝 | 角色停止 |",
        "|---|---|---|---|---|",
    ]
    for row in report["episodes"]:
        count = row["call_counts"]
        stops = (
            "; ".join(f"{role}: {value}" for role, value in row["role_stops"].items()) or "未记录"
        )
        lines.append(
            f"| {row['slot_id']} | {row['archive_status']} | {_display(row['score'])} / {_display(row['complete'])} | {count['requests']} / {count['responses']} / {count['tool_refusals']} | {stops} |"
        )
    for row in report["episodes"]:
        lines += ["", f"### {row['slot_id']}", ""]
        facts = row["saved_facts"]
        for key, label in (
            ("maintainer_current_fixed_build", "源端正确固定构建"),
            ("consumer_current_fixed_build", "消费端正确固定构建"),
            ("consumer_fixed_inspection", "消费端固定版本检查"),
            ("maintainer_revalidation", "维护者最终再验证"),
        ):
            fact = facts.get(key)
            seqs = []
            for path, value in nodes(fact):
                if path.endswith("sequence") and type(value) is int:
                    seqs.append(str(value))
            lines.append(
                f"- {label}：{'原评分未确认' if not fact else '原评分已确认；seq ' + ', '.join(seqs)}。"
            )
        failed = [
            TERM_LABELS.get(
                item.get("term_id"),
                item.get("reason") or item.get("message") or item.get("type", "unknown"),
            )
            for item in row["failure_observations"]
            if item.get("type") != "tool_refusal_or_execution_error"
        ]
        lines.append(
            "- 未达成或未知原因："
            + ("；".join(failed) if failed else "无新增推断，见保存的停止状态")
            + "。"
        )
        for action in row["key_actions"]:
            if action["action"] in {
                "handoff_information",
                "request_information",
                "sql_build",
                "submit",
                "raise_issue",
                "respond_issue",
                "decide_issue",
                "approve",
            } or action.get("error"):
                description = f"seq {action['sequence']}，{action['role']} → {action['action']}，工具返回={action['tool_ok']}"
                if action.get("execution_status"):
                    description += f"，SQL执行={action['execution_status']}"
                if action.get("error"):
                    description += "，错误=" + _display(
                        json.dumps(action["error"], ensure_ascii=False)
                    )
                lines.append("- " + description + "。")
        crossing = [
            record
            for record in row["collaboration"]["records"]
            if record["action"] in {"handoff_information", "request_information", "submit"}
        ]
        for record in crossing:
            levels = []
            for member, data in record["actual_input"].items():
                for level, found in data.items():
                    inputs = found if isinstance(found, list) else [found]
                    for value in inputs:
                        request = value.get("first_input_with_generation")
                        if request:
                            levels.append(
                                f"{member} {level} 进入seq {request['sequence']}的生成输入"
                            )
            lines.append(
                f"- 协作层次 seq {record['send_or_write']['sequence']}：运输/可访问证据 {len(record['delivery_or_access'])} 条；"
                + ("；".join(levels) if levels else "未核对到接收者对应的后续生成输入")
                + f"；显式引用使用 {len(record['execution_use'])} 条。计数仅作索引，不作协作收益。"
            )
        if row["sources"].get("runtime"):
            lines.append(
                f"- [原角色事件]({row['sources']['runtime']['path']})；评分和边界 SHA 见 JSON。"
            )
    lines += [
        "",
        "## 参数身份、成本与限制",
        "",
        f"全部已观察 worker 的 actor/critic 实际步数增量均为 0：{_display(report['all_observed_workers_zero_updates'])}。",
        f"已知闭合槽的完整学习状态与 RNG 保护：{report['closed_slot_guard_counts'].get('unchanged', 0)} 个通过，{report['closed_slot_guard_counts'].get('missing_or_failed', 0)} 个缺失或失败。这是保存的 guard 结果，报告不重新加载张量。",
        "",
        "| Worker | Actor 前→后 | Critic 前→后 | 完整恢复/原标记不变 | 已终止 GPU 小时 |",
        "|---|---|---|---|---|",
    ]
    for name, state in report["learning_state"].items():
        seconds = cost["workers"][name]["terminated_gpu_seconds"]
        lines.append(
            f"| {name} | {state['actor_steps_before']}→{state['actor_steps_after']} | {state['critic_steps_before']}→{state['critic_steps_after']} | {_display(state['full_state_digest_equal'])} / {_display(state['original_marker_unchanged'])} | {_display(seconds / 3600 if seconds is not None else None)} |"
        )
    lines += [
        "",
        f"两个 worker 已终止阶段成本合计 **{cost['terminated_gpu_seconds'] / 3600:.4f} GPU 小时**；快照中尚在运行的额外成本 {cost['running_gpu_seconds_at_snapshot'] / 3600:.4f} GPU 小时。加载、异常和停止耗时保留；并行墙钟时间未当作 GPU 小时。",
        "",
        f"实际请求 {report['call_counts']['requests']}；响应 {report['call_counts']['responses']}；其中带实际输出 token trace {report['call_counts']['responses_with_actual_token_trace']}；上下文拒绝 {report['call_counts']['backend_context_limits']}；工具拒绝 {report['call_counts']['tool_refusals']}。",
        "",
        "本轮没有参数学习或经验配置干预。消息更多、工具成功更多或出现闭环，都不能单独证明成员经历更值得训练。C2/C3 需要另行冻结当前策略支持及共同学习状态的配置对照；本报告不自动启动后继。",
        "",
        "全部源路径、SHA、逐组件结果、精确初始输入比较、动作序号和各协作层次保存在同名 JSON。",
    ]
    if "previous_attempt_gpu_seconds" in cost:
        lines += ["", (
            f"原C1加载失败另耗 {cost['previous_attempt_gpu_seconds']:.6f} GPU秒；"
            f"本次按每worker向上取整扣除，共 {cost['previous_attempt_budget_charge_seconds']} 秒。"
            f"原尝试与本恢复已终止部分累计 **{cost['cumulative_terminated_gpu_seconds'] / 3600:.6f} GPU小时**，"
            "仍受原4 GPU小时总上限约束。两次加载失败没有产生业务episode，不增加16槽分母。"
        )]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--require-terminal", action="store_true")
    args = parser.parse_args()
    result = load_run(args.run, require_terminal=args.require_terminal)
    atomic_write(args.output_json, json_bytes(result))
    atomic_write(args.output_md, markdown(result).encode())
    print(
        json.dumps(
            {
                "status": result["run_status"],
                "overall": result["overall"],
                "json": str(args.output_json),
                "markdown": str(args.output_md),
            },
            ensure_ascii=False,
        )
    )
