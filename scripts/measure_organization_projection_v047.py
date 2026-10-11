"""Strict v047 architecture interface with unchanged v044 feedback projection.

Protocol-bound functions are isolated copies of v046; pure page/source helpers
are imported. No old module globals, artifacts or results are modified.
"""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_budget_v047 as capacity
from scripts import measure_organization_work_v039 as base
from scripts.measure_organization_projection_v046 import (
    PROJECTION_VERSION, CONTEXT_STAGE_VERSION, SCOPE_KEYS, POLICY_SNAPSHOT_FIELDS, STATIC_PATHS,
    decoded,
    load,
    event_pointer,
    point,
    field_path,
    leaf,
    exact,
    scope,
    complete_pairs,
    feedback_saved,
    matches_feedback,
    followup_candidates,
    final_relation,
    archived_reports,
    page_feedback,
    report_histories,
)

VERSION = "organization-feedback-projection-v0.47"
PAGE_INTERFACE = "architecture-efficiency-staged-organization-v0.47"

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
        result["protected_headroom_after_margin_tokens"] = 18432 - 2048 - 1024 - projection["protected_prompt_tokens"]
    else:
        issues.append("missing_protected_request_measurement")
    if (not projection.get("protected_request_sha256") or not projection.get("protected_input_ids_sha256")
            or not projection.get("protected_rendered_prompt_sha256")):
        issues.append("missing_protected_encoding_identity")
    if (projection.get("context_limit") != 18432 or projection.get("reserved_output_tokens") != 2048
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


def audit_projection(call, record, initial, assignments, ledger_snapshot, *, capacity_binding=None):
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
        capacity.validate_preparation_capacity(preparation, capacity_binding)
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
    stage_proof = None
    deadline_proof = None
    if reason in {"unknown_no_actual_followup", "waiting_without_event"}:
        original_stage_boundaries = [event for event in events
            if event.get("kind") == "organization_stage_boundary_v047"
            and event.get("worker_id") == member and event.get("sequence", -1) > sequence
            and event.get("payload", {}).get("member_id") == member
            and event.get("payload", {}).get("permanent_retirement") is False]
        saved_boundaries = result.get("boundary", {}).get("stage_boundaries", [])
        matches = [event for event in original_stage_boundaries if event["payload"] in saved_boundaries]
        value = row.get("_value", {})
        response = value.get("result", {}) if isinstance(value, dict) else {}
        if (row.get("tool") == "finish_stage" and row.get("feedback_ok") is True
                and row.get("actual_originating_generation_bound") is True
                and response.get("status") == "stage_complete"
                and response.get("member_id") == member and response.get("permanent_retirement") is False):
            reason = "stage_boundary"
            stage_proof = {"origin": "actual_native_finish_stage_feedback", "feedback_id": row["feedback_id"],
                           "stage_id": response.get("stage_id"), "permanent_retirement": False,
                           "same_member_future_stage_not_inferred": True}
        elif matches:
            reason = "stage_boundary"
            stage_proof = {"origin": "original_host_stage_boundary", "original_event": matches[-1],
                           "saved_boundary_exactly_equal": True, "permanent_retirement": False,
                           "host_action_not_model_work": True}
    if reason == "unknown_no_actual_followup" and result.get("administrative_censoring") is True:
        try:
            deadline_proof = capacity.validate_deadline_receipt(result, budget, events)
            reason = "administrative_soft_deadline"
        except (KeyError, TypeError, ValueError):
            # A declared administrative stop without original dispatch/close
            # receipts is still unknown; no visibility or denominator is added.
            pass
    # Preserve admission/settlement evidence without equating held tokens with use.
    rejected = [{"call_id": key, "status": value.get("status"), "budget_kind": value.get("budget_kind"),
                 "attempt_started": value.get("attempt_started")}
                for key, value in budget.get("records", {}).items()
                if value.get("member") == member and value.get("status") in {"admission_rejected", "attempting"}]
    return {"reason": reason, "terminal_detail": terminal, "later_boundary_evidence": evidence,
            "stage_boundary_attribution": stage_proof, "administrative_close_attribution": deadline_proof,
            "member_admission_or_unsettled_records": rejected,
            "denominator_scope": "No later bound actual generation by this same member, not merely no successful action"}


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
    capacity_binding = capacity.read_capacity_binding(folder, result=result, budget=budget)
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
                               timeline["before_call"].get(call["call_id"]), capacity_binding=capacity_binding)
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
        capacity_binding=capacity.validate_episode_capacity(capacity_binding, result=result, budget=budget),
        capacity_binding_source=capacity.reference(folder.parent.parent / "capacity-binding.json"),
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
