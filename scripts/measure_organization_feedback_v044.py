"""Read-only v044 lifecycle feedback and unchanged v042 page opportunities.

Read saved native feedback and charged original generations, never invoke a
model, tokenizer, business test or acceptance. Presentation is not understanding
or causal use. The first-block gate inspects execution evidence only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_work_v039 as base

VERSION = "organization-feedback-opportunities-v0.44"
PROJECTION_VERSION = "software-context-v0.44"
CONTEXT_STAGE_VERSION = "software-context-v0.42"
PAGING_VERSION = "paged-public-test-feedback-v0.42"
SERIALIZATION = "json_unicode_indent2_trailing_lf_v042"
PAGE_INTERFACE = "member-private-exact-test-pages-v0.42"
SCOPE_KEYS = ("world_id", "instance_id", "branch_id", "project_id", "actor_id", "interface_revision")
POLICY_SNAPSHOT_FIELDS = ("action_error_policy", "acceptance_contract", "scheduling", "member_limits",
    "shared_resource_limits", "isolation", "observation_projection", "initial_diagnostic_provenance", "editable_paths")
STATIC_PATHS = {("role_task",), ("observation", "contract"),
                ("observation", "root_goal", "description"), ("observation", "initial_diagnostics"),
                *(("observation", field) for field in POLICY_SNAPSHOT_FIELDS)}
BEHAVIOR = {
    "read_file": "query", "list_files": "query", "read_patch": "query", "read_message": "query",
    "read_test_result": "query",
    "replace_file": "modify", "write_file": "modify", "run_tests": "verify",
    "send_message": "handoff", "fix_patch": "handoff", "integrate_patch": "integrate",
    "submit_integration": "fixed_delivery", "staff_wait": "wait", "staff_done": "end",
}


def interval_union(intervals):
    """Union half-open Unicode-character spans; repeated pages add no coverage."""
    merged = []
    for start, end in sorted(set(tuple(span) for span in intervals)):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def coverage_summary(total_characters, fragments):
    """Only independently verified fragments in actual generated inputs count."""
    shown = [fragment for fragment in fragments if fragment.get("actual_inputs")]
    intervals = interval_union((fragment["start"], fragment["end"]) for fragment in shown)
    covered = sum(end - start for start, end in intervals)
    unseen, cursor = [], 0
    for start, end in intervals:
        if cursor < start:
            unseen.append([cursor, start])
        cursor = end
    if cursor < total_characters:
        unseen.append([cursor, total_characters])
    return {"total_characters": total_characters, "historically_presented_intervals": intervals,
        "historically_presented_characters": covered, "unpresented_intervals": unseen,
        "coverage_fraction": covered / total_characters if total_characters else None,
        "historically_fully_presented": bool(total_characters and covered == total_characters),
        "feedback_page_returns": len(fragments), "page_returns_later_presented": len(shown),
        "actual_request_count": len({point["call_id"] for fragment in shown for point in fragment["actual_inputs"]}),
        "presentation_occurrences": sum(len(fragment["actual_inputs"]) for fragment in shown),
        "scope": "Union within one member/report/event/version only. Not simultaneous current-context coverage, understanding, adoption or contribution. Repeated page calls still incur their original costs."}


def decoded(message):
    try:
        value = json.loads(message.get("content", ""))
        return value if isinstance(value, dict) else None
    except (TypeError, ValueError):
        return None


def load(path, default=None):
    return base.read(path) if path.is_file() else default


def event_pointer(path, index, event):
    return {"path": str(path), "jsonl_line": index + 1, "experience_sequence": event.get("sequence")}


def point(call, message_index=None):
    result = {key: call[key] for key in ("call_id", "member", "experience_sequence", "path",
                                         "selected_request_sha256", "input_ids_sha256")}
    if message_index is not None:
        result.update(message_index=message_index, source=base.pointer(Path(call["path"]), f"/messages/{message_index}"))
    return result


def field_path(value):
    parts = value.split("/")
    if len(parts) < 5 or parts[:2] != ["", "messages"] or not parts[2].isdigit() or parts[3] != "content":
        raise ValueError("Unsupported declared observation path")
    return int(parts[2]), tuple(parts[4:])


def leaf(value, path):
    for key in path:
        value = value[key]
    return value


def exact(left, right):
    return json_bytes(left) == json_bytes(right)


def scope(value):
    observation = value.get("observation", {})
    return tuple(observation.get(key) for key in SCOPE_KEYS)


def complete_pairs(messages):
    pairs = []
    for index, message in enumerate(messages):
        calls = message.get("tool_calls") or []
        if message.get("role") != "assistant" or not calls:
            continue
        if (len(calls) != 1 or index + 1 >= len(messages)
                or messages[index + 1].get("role") != "tool"
                or messages[index + 1].get("tool_call_id") != calls[0].get("id")):
            raise ValueError("Incomplete original native tool round")
        pairs.append([index, index + 1])
    claimed = {pair[1] for pair in pairs}
    if any(m.get("role") == "tool" and i not in claimed for i, m in enumerate(messages)):
        raise ValueError("Orphan native feedback")
    return pairs


def audit_context_stage(call, record, initial, assignments, original, selected, projection):
    """Independently verify declared exact deletions and complete-round selection."""
    folder = Path(call["path"]).parent
    result = {"actual_input": point(call), "projection_source": base.pointer(folder / "projection.json", "/"),
              "status": "unresolved", "issues": []}
    if any(value is None for value in (original, selected, projection)):
        result["issues"].append("missing_original_selected_or_projection")
        return result
    issues = result["issues"]
    result.update(projection_version=projection.get("version"), uses_v042=projection.get("version") == CONTEXT_STAGE_VERSION,
        selected_prompt_tokens=projection.get("selected_prompt_tokens"), context_limit=projection.get("context_limit"),
        reserved_output_tokens=projection.get("reserved_output_tokens"),
        protected_prompt_tokens=projection.get("protected_prompt_tokens"),
        protected_request_sha256=projection.get("protected_request_sha256"),
        protected_input_ids_sha256=projection.get("protected_input_ids_sha256"),
        protected_rendered_prompt_sha256=projection.get("protected_rendered_prompt_sha256"),
        protected_engineering_margin_tokens=1024,
        protected_scope="All legally removable older complete tool rounds removed; not an information-theoretic minimum")
    if not result["uses_v042"]:
        issues.append("old_or_unrecognized_projection")
    tool_names = [tool.get("function", {}).get("name", tool.get("name")) for tool in original.get("tools", [])]
    if tool_names.count("read_test_result") != 1:
        issues.append("new_report_page_tool_missing_or_ambiguous")
    if type(projection.get("protected_prompt_tokens")) is int:
        result["protected_headroom_after_margin_tokens"] = 16384 - 2048 - 1024 - projection["protected_prompt_tokens"]
    else:
        issues.append("missing_protected_request_measurement")
    if (not projection.get("protected_request_sha256") or not projection.get("protected_input_ids_sha256")
            or not projection.get("protected_rendered_prompt_sha256")):
        issues.append("missing_protected_encoding_identity")
    if (projection.get("context_limit") != 16384 or projection.get("reserved_output_tokens") != 2048
            or selected.get("max_tokens") != 2048 or projection.get("fits") is not True):
        issues.append("frozen_context_or_output_limit_mismatch")
    if (digest(json_bytes(original)) != projection.get("original_request_sha256")
            or digest(json_bytes(selected)) != projection.get("selected_request_sha256")
            or projection.get("selected_request_sha256") != call["selected_request_sha256"]
            or projection.get("input_ids_sha256") != call["input_ids_sha256"]):
        issues.append("request_or_actual_input_hash_mismatch")
    prep = record.get("reservation", {}).get("preparation", {})
    usage = record.get("charge", {}).get("reported_usage") or {}
    if (prep.get("original_request_sha256") != projection.get("original_request_sha256")
            or prep.get("prompt_tokens") != projection.get("selected_prompt_tokens")
            or usage.get("prompt_tokens") != projection.get("selected_prompt_tokens")):
        issues.append("actual_generation_preparation_or_prompt_count_mismatch")
    if {k: v for k, v in original.items() if k != "messages"} != {k: v for k, v in selected.items() if k != "messages"}:
        issues.append("tools_or_sampling_parameters_changed")
    selected_payloads = [decoded(message) for message in selected.get("messages", []) if message.get("role") == "user"]
    observations = [value["observation"] for value in selected_payloads if value and isinstance(value.get("observation"), dict)]
    visible_reports = []
    for observation in observations:
        reports = observation.get("initial_diagnostics", [])
        if not isinstance(reports, list):
            issues.append("malformed_initial_diagnostic_payload")
        else:
            visible_reports.extend(reports)
    if any(obs.get("actor_id") != call["member"] for obs in observations):
        issues.append("other_member_observation_in_actual_input")
    if any(obs.get("interface_revision") != PAGE_INTERFACE for obs in observations):
        issues.append("old_or_missing_paged_world_interface")
    allowed = assignments.get(call["member"], [])
    if any(not isinstance(report, dict) or report.get("diagnostic_id") not in allowed
           or not exact(report, initial.get(report.get("diagnostic_id"))) for report in visible_reports):
        issues.append("unauthorized_or_changed_initial_diagnostic")
    if any(not any(exact(report, initial.get(identifier)) for report in visible_reports) for identifier in allowed):
        issues.append("authorized_initial_diagnostic_body_missing")
    result["initial_report_ids_present"] = sorted({report["diagnostic_id"] for report in visible_reports
                                                   if isinstance(report, dict) and isinstance(report.get("diagnostic_id"), str)})
    try:
        messages, kept = original["messages"], projection["selected_indices"]
        if (not isinstance(kept, list) or len(kept) != len(selected["messages"])
                or any(type(i) is not int or i < 0 or i >= len(messages) for i in kept)
                or kept != sorted(set(kept))):
            raise ValueError("Invalid selected message map")
        omitted = set(range(len(messages))) - set(kept)
        pairs = complete_pairs(messages)
        allowed_omitted = {i for pair in pairs[:-1] for i in pair}
        if not omitted <= allowed_omitted or any(bool(set(pair) & omitted) != (set(pair) <= omitted) for pair in pairs):
            issues.append("protected_message_or_partial_round_removed")
        if sorted(omitted) != projection.get("removed_indices"):
            issues.append("declared_removed_indices_mismatch")
        retained = {i: selected["messages"][position] for position, i in enumerate(kept)}
        if pairs and any(retained.get(i) != messages[i] for i in pairs[-1]):
            issues.append("latest_native_tool_round_not_preserved_exactly")
        result["latest_complete_round_present"] = bool(pairs)
        originals = {i: decoded(message) for i, message in enumerate(messages) if message.get("role") == "user"}
        projected = {i: decoded(message) for i, message in retained.items() if message.get("role") == "user"}
        expected = copy.deepcopy(originals)
        scoped = {i: value for i, value in originals.items() if value and isinstance(value.get("observation"), dict)}
        if not scoped:
            raise ValueError("Missing current authorized observation")
        latest = max(scoped)
        if (latest not in projected or not isinstance(scoped[latest].get("role_task"), str) or not scoped[latest]["role_task"]
                or not isinstance(scoped[latest]["observation"].get("contract"), str) or not scoped[latest]["observation"]["contract"]
                or projected[latest].get("role_task") != scoped[latest]["role_task"]
                or projected[latest].get("observation", {}).get("contract") != scoped[latest]["observation"]["contract"]):
            raise ValueError("Latest complete root contract or role instruction body missing")
        removals = projection.get("deduplication", {}).get("removed_values")
        if not isinstance(removals, list):
            raise ValueError("Missing exact-deletion metadata")
        for deletion in removals:
            index, path = field_path(deletion["path"])
            target, target_path = field_path(deletion["retained_equal_path"])
            if path not in STATIC_PATHS or target_path not in STATIC_PATHS:
                raise ValueError("An undeclared dynamic field was removed")
            if path != target_path and not (path == ("observation", "root_goal", "description")
                                           and target_path == ("observation", "contract")):
                raise ValueError("Removal conflates different semantic fields")
            old, target_value = originals[index], originals[target]
            if (old is None or target_value is None or target not in projected
                    or scope(old) != scope(target_value) or scope(old)[4] != call["member"]
                    or any(value is None for value in scope(old))):
                raise ValueError("Static deletion crossed or omitted the member/evidence scope")
            newest_same_scope = max(i for i, value in scoped.items() if scope(value) == scope(old))
            if target != newest_same_scope and not (index == target and path == ("observation", "root_goal", "description")):
                raise ValueError("Duplicate witness is not the latest same-member observation")
            removed_value = leaf(old, path)
            if not exact(removed_value, leaf(target_value, target_path)) or not exact(removed_value, leaf(projected[target], target_path)):
                raise ValueError("The exact full duplicate is absent from the retained selected input")
            if result["uses_v042"]:
                if (deletion.get("value_sha256") != digest(json_bytes(removed_value))
                        or deletion.get("member_identity") != dict(zip(SCOPE_KEYS, scope(old)))):
                    raise ValueError("Declared duplicate identity/hash differs from original evidence")
                if path != ("observation", "initial_diagnostics"):
                    identities = [{"root_goal_id": value["observation"]["root_goal"]["task_id"],
                                   "contract_sha256": digest(value["observation"]["contract"].encode())}
                                  for value in (old, target_value)]
                    expected_identity = identities[0]
                    if len(path) == 2 and path[1] in POLICY_SNAPSHOT_FIELDS:
                        diagnostic_ids = None
                        if path[1] == "initial_diagnostic_provenance":
                            diagnostic_ids = [{key: report[key] for key in
                                ("diagnostic_id", "origin", "initial_source_reference", "files_sha256")}
                                for report in old["observation"]["initial_diagnostics"]]
                            target_ids = [{key: report[key] for key in
                                ("diagnostic_id", "origin", "initial_source_reference", "files_sha256")}
                                for report in target_value["observation"]["initial_diagnostics"]]
                            if not exact(diagnostic_ids, target_ids):
                                raise ValueError("Initial provenance has different initial report identities")
                        expected_identity = {"root": identities[0], "initial_evidence": diagnostic_ids}
                    if not exact(identities[0], identities[1]) or not exact(deletion.get("evidence_identity"), expected_identity):
                        raise ValueError("Equal static text has a different root evidence identity")
                else:
                    identities = [{key: report[key] for key in ("diagnostic_id", "origin", "initial_source_reference", "files_sha256")}
                                  for report in removed_value]
                    if not exact(deletion.get("evidence_identity"), identities):
                        raise ValueError("Initial diagnostic identity metadata is not the exact original identity")
            parent = leaf(expected[index], path[:-1])
            del parent[path[-1]]
        for index in kept:
            if messages[index].get("role") == "user" and originals.get(index) is not None:
                if not exact(expected[index], projected.get(index)):
                    issues.append("undeclared_user_information_change")
                if {k: v for k, v in messages[index].items() if k != "content"} != {k: v for k, v in retained[index].items() if k != "content"}:
                    issues.append("user_message_metadata_changed")
            elif messages[index] != retained[index]:
                issues.append("non_observation_message_changed")
        result["declared_duplicate_fields_removed"] = len(removals)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        issues.append("projection_structure_or_retention_violation: " + str(error))
    result["issues"] = list(dict.fromkeys(issues))
    result["status"] = "violation" if result["issues"] else "verified"
    return result


def audit_projection(call, record, initial, assignments, ledger_snapshot):
    """Rebuild ordinary-feedback state from independent original runtime evidence."""
    from proworksim.software_feedback_v044 import project_format_feedback
    folder = Path(call["path"]).parent
    original, selected = load(folder / "original-request.json"), load(folder / "selected-request.json")
    projection = load(folder / "projection.json")
    result = {"actual_input": point(call), "projection_source": base.pointer(folder / "projection.json", "/"),
              "status": "unresolved", "uses_v044": False, "issues": []}
    if any(value is None for value in (original, selected, projection, ledger_snapshot)):
        result["issues"].append("missing_original_selected_projection_or_lifecycle_state")
        return result
    try:
        formatted, expected_feedback = project_format_feedback(original, ledger=ledger_snapshot,
                                                               member_id=call["member"])
        stage = projection["context_stage_projection"]
        issues = []
        if projection.get("version") != PROJECTION_VERSION:
            issues.append("old_or_unrecognized_projection")
        if not exact(expected_feedback, projection.get("format_feedback_projection")):
            issues.append("feedback_projection_differs_from_bound_original_event_timeline")
        if digest(json_bytes(formatted)) != stage.get("original_request_sha256"):
            issues.append("format_stage_request_identity_mismatch")
        saved_before = load(folder / "feedback-lifecycle-before.json")
        if not exact(saved_before, ledger_snapshot):
            issues.append("saved_lifecycle_state_differs_from_original_events")
        if digest(json_bytes(original)) != projection.get("original_request_sha256"):
            issues.append("transport_original_request_hash_mismatch")
        preparation = record.get("reservation", {}).get("preparation", {})
        if preparation.get("original_request_sha256") != projection.get("original_request_sha256"):
            issues.append("actual_preparation_not_bound_to_transport_original")
        mapping = expected_feedback["selected_indices"]
        indices = [mapping[i] for i in stage["selected_indices"]]
        protected_indices = [mapping[i] for i in stage["protected_selected_indices"]]
        if (projection.get("selected_indices") != indices
                or projection.get("removed_indices") != [i for i in range(len(original["messages"])) if i not in indices]
                or projection.get("protected_selected_indices") != protected_indices):
            issues.append("transport_index_composition_mismatch")
        expected_protected = {"version": PROJECTION_VERSION,
            "format_feedback_projection": expected_feedback,
            "context_stage_projection": stage["protected_projection"],
            "selected_indices": protected_indices,
            "removed_indices": [i for i in range(len(original["messages"])) if i not in protected_indices],
            "request_sha256": stage["protected_request_sha256"]}
        if not exact(projection.get("protected_projection"), expected_protected):
            issues.append("protected_feedback_or_context_proof_mismatch")
        # The nested stage is the exact old v042 static/round projection. Its
        # logical input hash differs from the transport original only by the
        # independently rebuilt authorized feedback stage above.
        stage_record = copy.deepcopy(record)
        stage_record["reservation"]["preparation"]["original_request_sha256"] = stage["original_request_sha256"]
        result = audit_context_stage(call, stage_record, initial, assignments, formatted, selected, stage)
        for field in ("selected_request_sha256", "input_ids_sha256", "selected_prompt_tokens", "context_limit",
                      "reserved_output_tokens", "protected_prompt_tokens", "protected_request_sha256",
                      "protected_input_ids_sha256", "protected_rendered_prompt_sha256", "fits"):
            if projection.get(field) != stage.get(field):
                issues.append("context_stage_identity_or_measurement_mismatch:" + field)
        result.update(projection_version=projection.get("version"), uses_v044=projection.get("version") == PROJECTION_VERSION,
            format_feedback_projection=expected_feedback,
            lifecycle_evidence_scope="Reconstructed from original selected/response/settlement and runner events, not the declared projection snapshot")
        result["issues"] = list(dict.fromkeys([*result["issues"], *issues]))
        result["status"] = "violation" if result["issues"] else "verified"
    except (KeyError, IndexError, TypeError, ValueError) as error:
        result["issues"].append("lifecycle_or_projection_structure_violation:" + str(error))
        result["status"] = "violation"
    return result


def _saved_protocol_feedback(events, inputs, path):
    """Use canonical protocol-visible payloads, including explicit format feedback."""
    decisions, receipts = {}, {}
    for index, event in enumerate(events):
        payload = event.get("payload", {})
        if event["kind"] == "policy_decision":
            decision = payload.get("decision", {})
            decisions[decision.get("model_call_id")] = (index, event, decision)
        if event["kind"] in {"tool_call", "harness_tool_call"}:
            receipts[(payload.get("model_call_id"), payload.get("model_tool_call_id"))] = (index, event)
    records, seen = [], set()
    for index, event in enumerate(events):
        payload = event.get("payload", {})
        kind = event["kind"]
        if kind not in {"model_tool_result", "model_format_feedback"}:
            continue
        call_id = payload.get("call_id")
        member = event.get("worker_id", payload.get("worker_id"))
        call = inputs.calls.get(call_id)
        key = (call_id, payload.get("model_tool_call_id"))
        decision = decisions.get(call_id, (None, None, {}))[2]
        receipt = receipts.get(key)
        message = payload.get("message") if kind == "model_tool_result" else {"role": "user", "content": json.dumps(
            {"public_format_feedback": payload.get("feedback")}, ensure_ascii=False)}
        value = decoded(message or {})
        saved = (value is not None and (exact(value, payload.get("world_response")) if kind == "model_tool_result"
                                      else isinstance(payload.get("feedback"), dict)))
        body = value.get("result", {}) if value else {}
        records.append({"feedback_id": f"feedback-{event['sequence']}", "kind": "format_feedback" if kind == "model_format_feedback" else "native_tool_feedback",
            "member": member, "experience_sequence": event["sequence"], "originating_call_id": call_id,
            "tool": "format_feedback" if kind == "model_format_feedback" else decision.get("action", receipt[1]["payload"].get("action") if receipt else None),
            "arguments": decision.get("arguments", receipt[1]["payload"].get("arguments", {}) if receipt else {}),
            "model_tool_call_id": payload.get("model_tool_call_id"), "generated_and_saved": saved,
            "actual_originating_generation_bound": bool(call and call["member"] == member and call["experience_sequence"] < event["sequence"]),
            "feedback_payload_sha256": digest(json_bytes(value)) if value is not None else None,
            "feedback_source": event_pointer(path, index, event),
            "world_receipt_source": event_pointer(path, *receipt) if receipt else None,
            "source_reference": body.get("source_reference", body.get("reference")) if isinstance(body, dict) else None,
            "public_test": decision.get("action") == "run_tests",
            "feedback_ok": value.get("ok") if value else None,
            "_message": message, "_value": value})
        seen.add(key)
    # A persisted world return without its protocol-visible record stays explicit,
    # rather than silently disappearing from the denominator.
    for key, (index, event) in receipts.items():
        if key in seen:
            continue
        payload = event["payload"]
        records.append({"feedback_id": f"unbound-receipt-{event['sequence']}", "kind": "receipt_without_visible_feedback_record",
            "member": event.get("worker_id"), "experience_sequence": event["sequence"], "originating_call_id": key[0],
            "tool": payload.get("action"), "arguments": payload.get("arguments", {}), "model_tool_call_id": key[1],
            "generated_and_saved": None, "actual_originating_generation_bound": key[0] in inputs.calls,
            "feedback_source": event_pointer(path, index, event), "world_receipt_source": event_pointer(path, index, event),
            "source_reference": None, "public_test": payload.get("action") == "run_tests", "feedback_ok": None,
            "_message": None, "_value": None})
    return sorted(records, key=lambda row: row["experience_sequence"]), decisions


def feedback_saved(events, inputs, path, ledger_snapshot):
    """Bind the full saved original and the separately declared visible correction."""
    rows, decisions = _saved_protocol_feedback(events, inputs, path)
    records = {(r["member_id"], r["call_id"]): r for r in ledger_snapshot.get("records", [])}
    for row in rows:
        if row["kind"] != "format_feedback":
            continue
        entry = records.get((row["member"], row["originating_call_id"]))
        row["full_archived_feedback_payload_sha256"] = row["feedback_payload_sha256"]
        row["feedback_lifecycle"] = copy.deepcopy(entry) if entry else None
        if entry and exact(row["_message"], entry["original_message"]):
            row["_message"] = copy.deepcopy(entry["visible_message"])
            row["_value"] = decoded(row["_message"])
            row["visible_feedback_payload_sha256"] = digest(json_bytes(row["_value"]))
            row["visible_projection"] = "ordinary_actionable_v044" if entry["ordinary"] else "retained_original_nonordinary"
            row["archive_and_prompt_are_distinct"] = entry["ordinary"]
        else:
            row["visible_projection"] = "retained_original_unbound_source"
            row["visible_feedback_payload_sha256"] = row["feedback_payload_sha256"]
    return rows, decisions


def matches_feedback(row, message):
    value = decoded(message)
    if row["kind"] == "format_feedback":
        return message.get("role") == "user" and exact(value, row["_value"])
    return (row["generated_and_saved"] is True and message.get("role") == "tool"
        and message.get("tool_call_id") == row["model_tool_call_id"] and exact(value, row["_value"]))


def no_followup_reason(row, result, events, budget, path):
    member, sequence = row["member"], row["experience_sequence"]
    later = [(i, e) for i, e in enumerate(events) if e.get("worker_id") == member and e["sequence"] > sequence]
    terminal = result.get("boundary", {}).get("terminal_details", {}).get(member, {})
    boundary = result.get("boundary", {})
    evidence = [{"source": event_pointer(path, i, e), "kind": e["kind"],
                 "budget_kind": e.get("payload", {}).get("budget_kind"), "status": e.get("payload", {}).get("status")}
                for i, e in later if e["kind"] in {"model_boundary_error", "model_budget_stop", "model_control", "role_suspended", "policy_error"}]
    context = [(i, e) for i, e in later if e["kind"] == "model_boundary_error"
               and e.get("payload", {}).get("budget_kind") == "context_capacity"]
    if context or terminal.get("cause") == "context_capacity":
        reason = "context_capacity"
    elif (terminal.get("cause") == "shared_team_pool_exhausted" or terminal.get("status") == "team_budget_exhausted"
          or boundary.get("closure_reason") == "shared_team_pool_exhausted"):
        reason = "team_budget"
    elif (terminal.get("status") == "completed" or boundary.get("role_stops", {}).get(member) == "completed"
          or any(e["kind"] == "model_control" and e["payload"].get("kind") == "done" for _, e in later)):
        reason = "voluntary_end"
    elif (member in boundary.get("waiting_members", {}) or terminal.get("cause") == "no_reachable_wake_event"):
        reason = "waiting_without_event"
    elif boundary.get("execution_integrity_failure"):
        reason = "execution_fault"
    elif result.get("status") != "closed":
        reason = "episode_unclosed_or_fault"
    else:
        reason = "unknown_no_actual_followup"
    # Preserve admission/settlement evidence without equating held tokens with use.
    rejected = [{"call_id": key, "status": value.get("status"), "budget_kind": value.get("budget_kind"),
                 "attempt_started": value.get("attempt_started")}
                for key, value in budget.get("records", {}).items()
                if value.get("member") == member and value.get("status") in {"admission_rejected", "attempting"}]
    return {"reason": reason, "terminal_detail": terminal, "later_boundary_evidence": evidence,
            "member_admission_or_unsettled_records": rejected,
            "denominator_scope": "No later bound actual generation by this same member, not merely no successful action"}


def followup_candidates(row, visible, decisions, inputs, experience_path):
    if visible is None:
        return []
    candidates = []
    for index, event, decision in decisions.values():
        call = inputs.calls.get(decision.get("model_call_id"))
        if not call or call["member"] != row["member"] or call["experience_sequence"] < visible["experience_sequence"]:
            continue
        action, args = decision.get("action"), decision.get("arguments", {})
        kind = BEHAVIOR.get(action)
        if kind is None:
            continue
        same_path = bool(row.get("arguments", {}).get("path") and args.get("path") == row["arguments"]["path"])
        candidates.append({"action": action, "kind": kind, "actual_generation": point(call),
            "source": event_pointer(experience_path, index, event), "same_explicit_path": same_path,
            "basis": "same_explicit_path_and_temporal_order" if same_path else "temporal_followup_only",
            "semantic_use": "not_inferred", "causal_use": "not_inferred"})
    return sorted(candidates, key=lambda item: item["actual_generation"]["experience_sequence"])


def final_relation(row, visible, final, world_events, inputs):
    delivery = final.get("delivery")
    if delivery is None:
        return {"status": "no_final_fixed_delivery", "semantic_use": "not_inferred"}
    source = row.get("source_reference")
    test = next((e for e in world_events if e.get("action_id") == (row.get("_value") or {}).get("action_id") and e["kind"] == "test"), None)
    exact = bool(test and source == delivery.get("source_reference") and test["sequence"] == delivery.get("test_sequence")
                 and test["actor_id"] == delivery.get("actor_id"))
    call = inputs.bound(delivery)
    presented_before = bool(visible and call and call["member"] == row["member"]
                            and visible["experience_sequence"] <= call["experience_sequence"])
    return {"status": "exact_test_version_bound_to_fixed_delivery" if exact else "no_exact_version_relation_established",
        "final_delivery": delivery, "feedback_presented_before_same_member_delivery": presented_before,
        "semantic_use": "not_inferred", "scope": "A matching version/test linkage is not understanding, causal necessity or new acceptance"}


def mechanical_directory(visible):
    def path(parts):
        return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)

    def status(row):
        return row["status"] if "status" in row else "untested" if row.get("executed") is False else (
            "passed" if row.get("passed") is True else "failed" if row.get("passed") is False else None)

    directory = []
    for section, groups in visible.items():
        if section not in {"public_diagnostics", "groups"} or not isinstance(groups, dict):
            continue
        for name, group in groups.items():
            if not isinstance(group, dict):
                continue
            item = {"path": path((section, name)), "group_id": name, "status": status(group), "entries": []}
            if "diagnostic_id" in group:
                item["diagnostic_id"] = group["diagnostic_id"]
            for index, entry in enumerate(group.get("tests", [])):
                if isinstance(entry, dict):
                    shown = {"path": path((section, name, "tests", index)), "status": status(entry)}
                    shown.update({key: entry[key] for key in ("test_id", "id") if key in entry})
                    item["entries"].append(shown)
            directory.append(item)
    return directory


def archived_reports(software, world_events, state_path):
    """Verify immutable Pi040-visible bodies and their exact stored page partition."""
    archives = {}
    for report_id, report in software.get("test_reports", {}).items():
        issues = []
        row = {"report_id": report_id, "actor_id": report.get("actor_id"),
            "storage_source": base.pointer(state_path, "/projects/SOFTWARE27/software/test_reports/" + report_id),
            "status": "unresolved", "issues": issues, "_record": report}
        try:
            body, visible, pages = report["body"], report["visible_result"], report["pages"]
            identity = report["event_identity"]
            if (report.get("version") != PAGING_VERSION or report.get("serialization") != SERIALIZATION
                    or report.get("page_body_unicode_characters") != 3072 or report.get("report_id") != report_id
                    or report_id != "test-report-" + digest(json_bytes([report["actor_id"], identity, report["body_sha256"]]))[:24]):
                issues.append("report_protocol_or_immutable_identity_mismatch")
            public_event = {"sequence": identity["test_event_sequence"], "operation_id": identity["operation_id"]}
            row.update(report_event=public_event, event_identity=identity, source_reference=visible["source_reference"],
                files_sha256=visible.get("files_sha256"), body_sha256=report["body_sha256"],
                body_characters=len(body), total_pages=len(pages))
            if (not isinstance(body, str) or body != json_bytes(visible).decode()
                    or digest(body.encode()) != report["body_sha256"]):
                issues.append("archived_visible_body_serialization_or_hash_mismatch")
            if not isinstance(pages, list) or not pages:
                issues.append("missing_stored_page_partition")
            cursor, cursors = 0, set()
            for index, page in enumerate(pages):
                if (page["index"] != index or type(page["start"]) is not int or type(page["end"]) is not int
                        or page["start"] != cursor or not cursor < page["end"] <= len(body)
                        or page["end"] - cursor > 3072 or page["text"] != body[cursor:page["end"]]
                        or page["sha256"] != digest(page["text"].encode())):
                    issues.append("page_partition_not_exact_unicode_body")
                expected_cursor = str(index) + ":" + digest(json_bytes([report_id, report["body_sha256"], index, page["start"], page["end"]]))[:16]
                if (not isinstance(page["cursor"], str) or page["cursor"] != expected_cursor or page["cursor"] in cursors
                        or page["next_cursor"] != (pages[index + 1]["cursor"] if index + 1 < len(pages) else None)
                        or page["is_last"] is not (index == len(pages) - 1)
                        or page["remaining_pages"] != len(pages) - index - 1):
                    issues.append("page_cursor_or_end_contract_mismatch")
                cursor = page["end"]
                cursors.add(page["cursor"])
            if cursor != len(body):
                issues.append("stored_pages_do_not_reconstruct_entire_body")
            event = next((event for event in world_events if event.get("sequence") == identity["test_event_sequence"]), None)
            if (identity.get("actor_id") != report["actor_id"] or not event or event.get("kind") != "test"
                    or event.get("actor_id") != report["actor_id"] or event.get("source_reference") != visible["source_reference"]
                    or event.get("operation_id") != identity.get("operation_id")):
                issues.append("report_owner_event_or_source_version_mismatch")
            if event:
                row["test_action_id"] = event.get("action_id")
                row["test_event_source"] = base.pointer(state_path, "/software_events/" + str(event["sequence"] - 1))
            saves = [event for event in world_events if event.get("kind") == "test_report_saved" and event.get("report_id") == report_id]
            if (len(saves) != 1 or saves[0].get("actor_id") != report["actor_id"]
                    or saves[0].get("test_event_sequence") != identity["test_event_sequence"]
                    or saves[0].get("body_sha256") != report["body_sha256"]
                    or saves[0].get("source_reference") != visible["source_reference"]):
                issues.append("report_save_event_not_uniquely_bound")
            else:
                row["save_event_source"] = base.pointer(state_path, "/software_events/" + str(saves[0]["sequence"] - 1))
            if not exact(report.get("directory"), mechanical_directory(visible)):
                issues.append("directory_not_original_group_item_order_and_status")
            row["status"] = "violation" if issues else "verified"
        except (KeyError, TypeError, ValueError, IndexError) as error:
            issues.append("incomplete_report_storage: " + str(error))
        row["issues"] = list(dict.fromkeys(issues))
        archives[report_id] = row
    return archives


def page_feedback(row, presentations, archives, inputs):
    """Audit the actually returned v042 page, never demand the full body in input."""
    if row["tool"] not in {"run_tests", "read_test_result"}:
        return None
    result = (row.get("_value") or {}).get("result", {})
    requested_id = row.get("arguments", {}).get("report_id") if row["tool"] == "read_test_result" else None
    item = {"tool": row["tool"], "feedback_id": row["feedback_id"], "member": row["member"],
        "requested_report_id": requested_id, "status": "unresolved", "issues": [],
        "directory_actual_inputs": [], "page_actual_inputs": []}
    if row["feedback_ok"] is False:
        item.update(status="request_rejected_without_page", error=(row.get("_value") or {}).get("error"),
                    no_page_generated=True)
        if isinstance(result, dict) and any(key in result for key in ("page", "directory", "body", "visible_result")):
            item.update(status="violation", issues=["report_material_exposed_in_rejected_page_request"])
        return item
    try:
        report_id, page = result["report_id"], result["page"]
        item["report_id"] = report_id
        archive = archives.get(report_id)
        if archive is None or archive["status"] != "verified":
            item["issues"].append("report_archive_missing_or_not_verified")
            return item
        record, visible = archive["_record"], archive["_record"]["visible_result"]
        if record["actor_id"] != row["member"]:
            item["issues"].append("other_member_report_returned_without_permission")
        if (result.get("version") != PAGING_VERSION or result.get("serialization") != SERIALIZATION
                or result["report_event"] != archive["report_event"] or result["source_reference"] != archive["source_reference"]
                or result["files_sha256"] != archive["files_sha256"] or result["body_sha256"] != archive["body_sha256"]
                or result["body_characters"] != archive["body_characters"] or result["total_pages"] != archive["total_pages"]
                or result["executed"] != visible.get("executed") or result["passed"] != visible.get("passed")
                or not isinstance(result.get("serialization"), str) or not result["serialization"]):
            item["issues"].append("returned_report_event_version_or_body_identity_mismatch")
        index = page["index"]
        if type(index) is not int or not 0 <= index < len(record["pages"]) or not exact(page, record["pages"][index]):
            item["issues"].append("returned_page_not_exact_stored_fragment")
        if row["tool"] == "run_tests":
            if index != 0:
                item["issues"].append("initial_test_return_is_not_first_page")
            if (row.get("_value") or {}).get("action_id") != archive.get("test_action_id"):
                item["issues"].append("report_not_bound_to_originating_run_tests_action")
        if row["tool"] == "read_test_result" and (requested_id != report_id or row["arguments"].get("cursor") != page["cursor"]):
            item["issues"].append("read_request_report_or_cursor_mismatch")
        if index == 0:
            if not exact(result.get("directory"), record["directory"]):
                item["issues"].append("first_page_directory_not_exact_frozen_directory")
            if any(not exact(result.get(key), visible.get(key)) for key in
                   ("scope", "untested", "independent_acceptance", "fixed_submission_is_acceptance")):
                item["issues"].append("first_page_original_status_scope_changed")
        elif "directory" in result:
            item["issues"].append("later_page_repeats_or_changes_directory")
        call = inputs.calls.get(row["originating_call_id"])
        observations = [decoded(message) for message in inputs.messages(call)] if call else []
        observations = [value["observation"] for value in observations if value and isinstance(value.get("observation"), dict)]
        if not observations or any(observations[-1].get(key) != record["event_identity"].get(key)
                                   for key in ("world_id", "instance_id", "branch_id", "project_id", "actor_id")):
            item["issues"].append("page_request_member_world_or_branch_not_bound")
        item.update(status="violation" if item["issues"] else "verified", report_event=archive["report_event"],
            source_reference=archive["source_reference"], body_sha256=archive["body_sha256"],
            page_index=index, start=page["start"], end=page["end"], cursor=page["cursor"],
            page_sha256=page["sha256"], next_cursor=page["next_cursor"], is_last=page["is_last"],
            directory_returned=index == 0)
        if item["status"] == "verified":
            item["page_actual_inputs"] = presentations
            item["directory_actual_inputs"] = presentations if index == 0 else []
    except (KeyError, TypeError, ValueError, IndexError) as error:
        item["issues"].append("incomplete_paged_feedback_protocol: " + str(error))
    return item


def report_histories(archives, feedback_records, result, decisions, inputs, experience_path):
    """Keep every immutable report/event/version separate, including equal bodies."""
    histories = []
    for report_id, archive in archives.items():
        associated = [row for row in feedback_records if row.get("report_page", {}).get("report_id") == report_id]
        fragments = [{"start": row["report_page"]["start"], "end": row["report_page"]["end"],
                      "actual_inputs": row["report_page"]["page_actual_inputs"], "feedback_id": row["feedback_id"]}
                     for row in associated if row["report_page"]["status"] == "verified"]
        coverage = coverage_summary(archive["body_characters"], fragments) if archive["status"] == "verified" else None
        last = max(associated, key=lambda row: row["experience_sequence"]) if associated else None
        terminal = result.get("boundary", {}).get("terminal_details", {}).get(archive.get("actor_id"), {})
        if not coverage or last is None:
            continuation = "unknown_report_or_feedback_evidence"
        elif coverage["historically_fully_presented"]:
            continuation = "no_unpresented_remainder"
        elif last.get("no_actual_followup"):
            continuation = last["no_actual_followup"]["reason"]
        elif last["presentation"]["first_exact_presentation"] is None:
            continuation = "requested_feedback_not_presented"
        else:
            first_call = last["presentation"]["first_exact_presentation"]["call_id"]
            action = decisions.get(first_call, (None, None, {}))[2].get("action")
            continuation = "voluntary_end" if action == "staff_done" else "waiting_without_event" if (
                action == "staff_wait" and archive.get("actor_id") in result.get("boundary", {}).get("waiting_members", {})) else "not_requested"
        directories = [point for row in associated for point in row.get("report_page", {}).get("directory_actual_inputs", [])]
        page_requests = [decision for _, _, decision in decisions.values() if decision.get("action") == "read_test_result"
                         and decision.get("arguments", {}).get("report_id") == report_id
                         and decision.get("model_call_id") in inputs.calls
                         and inputs.calls[decision["model_call_id"]]["member"] == archive.get("actor_id")]
        charges = [result.get("team_budget", {}).get("model", {}).get("records", {}).get(decision["model_call_id"], {})
                   .get("charge", {}).get("reported_usage") for decision in page_requests]
        page_cost = {key: sum(charge[key] for charge in charges if isinstance(charge, dict) and type(charge.get(key)) is int)
                     for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
        histories.append({key: value for key, value in archive.items() if key != "_record"} | {
            "member": archive.get("actor_id"), "origin": "member_public_test_execution", "environment_initial_diagnostic": False,
            "directory_presented_in_actual_generation": bool(directories), "first_actual_directory_input": directories[0] if directories else None,
            "directory_actual_request_count": len({point["call_id"] for point in directories}),
            "verified_page_feedback_count": len(fragments), "actual_page_read_requests": len(page_requests),
            "page_read_reported_usage": page_cost, "page_read_calls_without_exact_usage": sum(not isinstance(charge, dict) for charge in charges),
            "page_read_cost_scope": "Repeated reads remain separate charged member actions; no test execution or budget is added by this measurement",
            "coverage": coverage, "continuation": {"reason": continuation,
                "terminal_context": terminal, "unrequested_pages_are_not_a_gate_failure": True,
                "scope": "An unrequested remainder is a work choice. An already returned requested page lacking a later generation is separately classified; terminal context does not prove why earlier pages were not requested."},
            "feedback_ids": [row["feedback_id"] for row in associated],
            "subsequent_work_and_fixed_delivery": [{"feedback_id": row["feedback_id"],
                "following_behavior_candidates": row["following_behavior_candidates"], "final_fixed_relation": row["final_fixed_relation"]}
                for row in associated],
            "scope": "Historical exact-page presentation for this member/report/event/source version only. Sharing an ID is not authorization; unbound text quotations do not fabricate report coverage. No simultaneous-context or comprehension claim."})
    return histories


def _measure_episode(episode_dir):
    folder = Path(episode_dir).resolve()
    result = load(folder / "slot-result.json", {})
    output = {"version": VERSION, "episode": str(folder), "slot_id": result.get("slot_id"),
        "status": "unresolved", "episode_closed": result.get("status") == "closed", "read_only": True,
        "new_model_calls": 0, "new_tokenizer_calls": 0, "new_test_or_acceptance_executions": 0,
        "training_support": False, "feedback_records": [], "projection_audit": [], "measurement_gaps": []}
    evidence_path, experience_path = folder / "organization-evidence.json", folder / "experience.jsonl"
    state_path = folder / "prepared/world/control/state.json"
    if not state_path.is_file():
        state_path = folder / "episode/end/control/state.json"
    missing = [str(p) for p in (folder / "slot-result.json", evidence_path, experience_path, state_path) if not p.is_file()]
    if missing:
        output["measurement_gaps"].append({"reason": "missing_episode_evidence", "paths": missing})
        output["mechanism_gate_inputs"] = {"resolved": False, "reasons": ["missing_episode_evidence"]}
        return output
    evidence, state = base.read(evidence_path), base.read(state_path)
    events = [json.loads(line) for line in experience_path.read_text().splitlines() if line.strip()]
    budget = result.get("team_budget", evidence.get("team_budget", {})).get("model", {})
    inputs = base.Inputs(folder, evidence, budget)
    software = state["projects"][base.PROJECT]["software"]
    initial, assignments = software.get("initial_diagnostics", {}), software.get("initial_diagnostic_assignments", {})
    gaps = output["measurement_gaps"]
    gaps.extend(inputs.issues)
    attempts = [row for row in budget.get("records", {}).values() if row.get("attempt_started") is True]
    if len(attempts) != len(inputs.calls):
        gaps.append({"reason": "actual_attempts_without_complete_original_generation_binding",
                     "attempts": len(attempts), "bound_generations": len(inputs.calls)})
    if not initial or not assignments:
        gaps.append({"reason": "missing_authorized_initial_diagnostic_contract"})
    from scripts.software_context_replay_v044 import load_episode_history, reconstruct_feedback_timeline
    timeline = reconstruct_feedback_timeline(load_episode_history(folder))
    audits = [audit_projection(call, budget["records"][call["call_id"]], initial, assignments,
                               timeline["before_call"].get(call["call_id"]))
              for call in sorted(inputs.calls.values(), key=lambda row: row["experience_sequence"])]
    records, decisions = feedback_saved(events, inputs, experience_path, timeline["final_snapshot"])
    world_events = state.get("software_events", [])
    final = base.final_evidence(result, world_events, state_path)
    if "test_reports" not in software:
        gaps.append({"reason": "missing_v042_immutable_report_registry"})
    archives = archived_reports(software, world_events, state_path)
    for row in records:
        later = [call for call in inputs.by_member(row["member"]) if call["experience_sequence"] > row["experience_sequence"]]
        matches = [{**point(call, index)} for call in later for index, message in enumerate(inputs.messages(call)) if matches_feedback(row, message)]
        visible = matches[0] if matches else None
        first = later[0] if later else None
        first_visible = bool(visible and first and visible["call_id"] == first["call_id"])
        row["presentation"] = {"status": "presented_exact" if visible else "not_in_actual_followup" if later else "no_actual_followup",
            "later_actual_generation_count": len(later), "first_actual_followup": point(first) if first else None,
            "first_exact_presentation": visible, "presented_in_first_actual_followup": first_visible,
            "matching_actual_request_count": len({m["call_id"] for m in matches})}
        row["no_actual_followup"] = no_followup_reason(row, result, events, budget, experience_path) if not later else None
        paged = page_feedback(row, matches, archives, inputs)
        if paged is not None:
            row["report_page"] = paged
        row["following_behavior_candidates"] = followup_candidates(row, visible, decisions, inputs, experience_path)
        row["final_fixed_relation"] = final_relation(row, visible, final, world_events, inputs)
        if row["generated_and_saved"] is not True or not row["actual_originating_generation_bound"]:
            gaps.append({"reason": "feedback_without_complete_original_protocol_binding", "feedback_id": row["feedback_id"]})
        row.pop("_message", None)
        row.pop("_value", None)
    histories = report_histories(archives, records, result, decisions, inputs, experience_path)
    for report_id in archives:
        if not any(row["tool"] == "run_tests" and row.get("report_page", {}).get("report_id") == report_id
                   and row["actual_originating_generation_bound"] for row in records):
            gaps.append({"reason": "report_without_bound_originating_run_tests_feedback", "report_id": report_id})
    page_violations = [{"report_id": value["report_id"], "issues": value["issues"]}
                       for value in archives.values() if value["status"] == "violation"]
    page_unresolved = [{"report_id": value["report_id"], "issues": value["issues"]}
                       for value in archives.values() if value["status"] == "unresolved"]
    for row in records:
        paged = row.get("report_page")
        if paged and paged["status"] in {"violation", "unresolved"}:
            (page_violations if paged["status"] == "violation" else page_unresolved).append(
                {"feedback_id": row["feedback_id"], "issues": paged["issues"]})
    initial_rows = []
    for member, ids in assignments.items():
        for identifier in ids:
            hits = []
            for call in inputs.by_member(member):
                for index, message in enumerate(inputs.messages(call)):
                    value = decoded(message)
                    obs = value.get("observation", {}) if value else {}
                    if message.get("role") == "user" and obs.get("actor_id") == member and any(exact(initial.get(identifier), report) for report in obs.get("initial_diagnostics", [])):
                        hits.append(point(call, index))
            initial_rows.append({"member": member, "diagnostic_id": identifier, "origin": "environment_initial_diagnostic",
                "member_discovery": False, "first_actual_presentation": hits[0] if hits else None,
                "usage_or_understanding": "not_inferred"})
    reasons = Counter(row["no_actual_followup"]["reason"] for row in records if row["no_actual_followup"])
    protected_missing = [row["feedback_id"] for row in records if row["presentation"]["later_actual_generation_count"]
                         and not row["presentation"]["presented_in_first_actual_followup"]]
    blocked = [row["feedback_id"] for row in records if row["generated_and_saved"] is True and row["no_actual_followup"]
               and row["no_actual_followup"]["reason"] == "context_capacity"]
    unresolved_no_followup = [row["feedback_id"] for row in records if row["no_actual_followup"]
        and row["no_actual_followup"]["reason"] in {"unknown_no_actual_followup", "episode_unclosed_or_fault"}]
    denominators = {"all_saved_feedback_units": len(records), "protocol_feedback_saved_exactly": sum(r["generated_and_saved"] is True for r in records),
        "with_later_actual_generation": sum(bool(r["presentation"]["later_actual_generation_count"]) for r in records),
        "presented_in_later_actual_generation": sum(r["presentation"]["first_exact_presentation"] is not None for r in records),
        "presented_in_first_actual_followup": sum(r["presentation"]["presented_in_first_actual_followup"] for r in records),
        "without_later_actual_generation": sum(r["no_actual_followup"] is not None for r in records),
        "no_followup_reasons": dict(reasons), "by_tool": {}}
    for tool in sorted({row["tool"] or "unknown" for row in records}):
        subset = [r for r in records if (r["tool"] or "unknown") == tool]
        denominators["by_tool"][tool] = {"feedback_units": len(subset),
            "presented_in_actual_generation": sum(r["presentation"]["first_exact_presentation"] is not None for r in subset),
            "no_followup_reasons": dict(Counter(r["no_actual_followup"]["reason"] for r in subset if r["no_actual_followup"]))}
    output.update(status="measured", feedback_records=records, projection_audit=audits, denominators=denominators,
        format_feedback_lifecycle=timeline["final_snapshot"],
        lifecycle_original_event_checks=timeline["event_checks"],
        environment_initial_diagnostics=initial_rows, report_histories=histories,
        page_denominators={"reports_saved": len(histories), "reports_storage_verified": sum(row["status"] == "verified" for row in histories),
            "reports_with_directory_presented": sum(row["directory_presented_in_actual_generation"] for row in histories),
            "reports_with_any_page_presented": sum(bool(row["coverage"] and row["coverage"]["historically_presented_characters"]) for row in histories),
            "reports_historically_fully_presented": sum(bool(row["coverage"] and row["coverage"]["historically_fully_presented"]) for row in histories),
            "verified_page_feedback_returns": sum(row["verified_page_feedback_count"] for row in histories),
            "actual_page_read_requests": sum(decision.get("action") == "read_test_result" and decision.get("model_call_id") in inputs.calls
                                             for _, _, decision in decisions.values()),
            "page_read_outcomes": dict(Counter(row["report_page"]["status"] for row in records
                                      if row["tool"] == "read_test_result" and "report_page" in row)),
            "continuation_reasons": dict(Counter(row["continuation"]["reason"] for row in histories))},
        mechanism_gate_inputs={"resolved": not gaps and not unresolved_no_followup and not page_unresolved and output["episode_closed"],
            "page_protocol_violations": page_violations, "page_protocol_unresolved": page_unresolved,
            "actual_generated_requests": len(inputs.calls), "requests_verified_under_v044": sum(a["status"] == "verified" for a in audits),
            "projection_violations": [a["actual_input"]["call_id"] for a in audits if a["status"] == "violation"],
            "projection_unresolved": [a["actual_input"]["call_id"] for a in audits if a["status"] == "unresolved"],
            "feedback_missing_from_first_actual_followup": protected_missing,
            "context_blocked_feedback_ids": blocked, "unresolved_no_followup_ids": unresolved_no_followup,
            "criterion": "Execution/presentation only. No score, message-frequency, page count, report-completion, recruitment or success selection."},
        scope="Full feedback archive, v044 actionable projection, actual presentation, supersession and legal-schema history are separate. Page/feedback chronological follow-ups do not prove semantic or causal adoption; old results remain unchanged.")
    return output


def measure_episode(episode_dir):
    try:
        return _measure_episode(episode_dir)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        return {"version": VERSION, "episode": str(Path(episode_dir).resolve()), "status": "unresolved", "read_only": True,
            "new_model_calls": 0, "new_tokenizer_calls": 0, "new_test_or_acceptance_executions": 0,
            "feedback_records": [], "measurement_gaps": [{"reason": "unreadable_or_inconsistent_episode_evidence",
                "error_type": type(error).__name__, "detail": str(error)}],
            "mechanism_gate_inputs": {"resolved": False, "reasons": ["unreadable_or_inconsistent_episode_evidence"]}}


def first_block_gate(measurements):
    """Frozen four-slot gate, independent of business scores or organization acts."""
    reasons = []
    present = [row for row in measurements if isinstance(row, dict)]
    if len(measurements) != 4 or len(present) != 4 or len({row.get("slot_id") for row in present}) != 4:
        reasons.append({"reason": "gate_unresolved", "detail": "Require four distinct original block measurements"})
    for row in present:
        facts = row.get("mechanism_gate_inputs", {})
        slot = row.get("slot_id")
        if (not facts.get("resolved") or not facts.get("actual_generated_requests") or facts.get("projection_unresolved")
                or facts.get("requests_verified_under_v044") != facts.get("actual_generated_requests")):
            reasons.append({"slot_id": slot, "reason": "gate_unresolved"})
        if facts.get("page_protocol_violations"):
            reasons.append({"slot_id": slot, "reason": "page_permission_version_or_fragment_violation", "details": facts["page_protocol_violations"]})
        if facts.get("projection_violations"):
            reasons.append({"slot_id": slot, "reason": "projection_or_permission_violation", "calls": facts["projection_violations"]})
        if facts.get("feedback_missing_from_first_actual_followup"):
            reasons.append({"slot_id": slot, "reason": "protected_feedback_missing", "feedback_ids": facts["feedback_missing_from_first_actual_followup"]})
        if facts.get("context_blocked_feedback_ids"):
            reasons.append({"slot_id": slot, "reason": "input_feedback_block", "feedback_ids": facts["context_blocked_feedback_ids"]})
    return {"version": VERSION, "passed": not reasons, "reasons": reasons, "measured_slots": len(measurements),
        "scope": "Stop unopened inventory on unresolved or violated execution/presentation of requested feedback. Unrequested pages, incomplete reading, page counts, normal team budget, voluntary ending, waiting and business outcomes are not selection criteria."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(measure_episode(args.episode), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
