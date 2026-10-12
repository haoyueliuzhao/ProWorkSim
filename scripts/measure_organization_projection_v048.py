"""Isolated v048 representation proof over the unchanged v047 runtime.

This reader reconstructs the authorized feedback/static/reference transformations
from original evidence without model, tokenizer, or world execution. G0 delegates
to its frozen v047 projection reader. Old modules and artifacts remain unchanged.
"""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from proworksim import software_context_v048 as reference_protocol
from proworksim.software_context_v034 import observation_messages
from proworksim.software_context_v041 import deduplicate_static_snapshots, _member_identity, _root_identity
from proworksim.software_feedback_v044 import project_format_feedback
from scripts import measure_organization_projection_v047 as previous
from scripts import measure_organization_budget_v047 as capacity
from scripts import measure_organization_work_v039 as base
from scripts.measure_organization_projection_v046 import (
    decoded, load, event_pointer, point, exact, complete_pairs,
    feedback_saved, matches_feedback, followup_candidates, final_relation,
    archived_reports, page_feedback, report_histories,
)

VERSION = "organization-feedback-projection-v0.48"
PAGE_INTERFACE = previous.PAGE_INTERFACE
CANDIDATE_SHA256 = reference_protocol.CANDIDATE_SHA256
PROJECTION_VERSION = reference_protocol.VERSION


def representation_binding(representation, candidate_sha256):
    if representation not in {"Gamma0", "Gamma1"} or candidate_sha256 != CANDIDATE_SHA256:
        raise ValueError("Representation or candidate differs from the sole frozen v048 protocol")
    return {"representation": representation, "candidate_sha256": candidate_sha256}



def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _leaf(value, path):
    for key in path.split("/")[1:]:
        if not isinstance(value, dict) or key not in value:
            raise KeyError(path)
        value = value[key]
    return value


def _assign(value, path, replacement):
    parts = path.split("/")[1:]
    for part in parts[:-1]:
        value = value[part]
    value[parts[-1]] = replacement


def _marker(value):
    if isinstance(value, dict):
        return "$same_input_ref" in value or any(_marker(item) for item in value.values())
    return isinstance(value, list) and any(_marker(item) for item in value)


def rebuild_reference_stage(static, formatted, member):
    """Independent five-path reconstruction, not a replay of declared changes."""
    selected = copy.deepcopy(static)
    source = list(observation_messages(formatted))
    views = list(observation_messages(static))
    eligible = len(source) == len(views) == 2 and [i for i, _ in source] == [i for i, _ in views]
    if eligible:
        identities = [_member_identity(payload["observation"]) for _, payload in source]
        roots = [_root_identity(payload["observation"]) for _, payload in source]
        eligible = (all(item is not None for item in identities + roots)
            and identities[0]["actor_id"] == member and exact(identities[0], identities[1])
            and exact(roots[0], roots[1])
            and all(exact(_member_identity(payload["observation"]), identities[0]) for _, payload in views))
    # Detect duplicate JSON object keys directly from the original text. The
    # transform never gets to authorize references by normalizing ambiguity.
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    try:
        for candidate in (formatted, static):
            for index, _ in observation_messages(candidate):
                json_bytes(json.loads(candidate["messages"][index]["content"], object_pairs_hook=unique_pairs))
    except (TypeError, ValueError):
        eligible = False
    generated = []
    if eligible:
        (first_index, first), (latest_index, latest) = views
        for path in reference_protocol.ALLOWLIST:
            try:
                target, value = _leaf(first, path), _leaf(latest, path)
            except KeyError:
                continue
            if _marker(target) or _marker(value) or json_bytes(target) != json_bytes(value):
                continue
            reference = {"$same_input_ref": "first_observation#" + path}
            generated.append({"path": path, "reference": reference,
                "value_sha256": digest(json_bytes(value)), "value_bytes": len(json_bytes(value)),
                "first_observation_index": first_index, "latest_observation_index": latest_index})
            _assign(latest, path, reference)
        if generated:
            selected["messages"][latest_index]["content"] = json.dumps(latest, ensure_ascii=False, allow_nan=False)
    proof = {"eligible": bool(eligible), "generated_references": generated}
    if eligible:
        proof.update(member_identity=identities[0], root_identity=roots[0],
            first_observation_index=views[0][0], latest_observation_index=views[-1][0])
    return selected, proof


def _selected(request, indices):
    _require(isinstance(indices, list) and indices == sorted(set(indices))
        and all(type(i) is int and 0 <= i < len(request["messages"]) for i in indices), "invalid_selected_indices")
    value = copy.deepcopy(request)
    value["messages"] = [copy.deepcopy(request["messages"][i]) for i in indices]
    return value


def _permission_and_static_checks(original, selected, call, initial, assignments):
    names = [tool.get("function", {}).get("name", tool.get("name")) for tool in original.get("tools", [])]
    _require(names.count("read_test_result") == 1, "paged_report_tool_missing_or_ambiguous")
    _require(exact({key: value for key, value in selected.items() if key != "messages"},
                   {key: value for key, value in original.items() if key != "messages"}), "tools_or_sampling_parameters_changed")
    originals = list(observation_messages(original))
    observations = list(observation_messages(selected))
    _require(bool(originals) and bool(observations), "missing_authorized_observation")
    _require(all(payload["observation"].get("actor_id") == call["member"]
        and payload["observation"].get("interface_revision") == PAGE_INTERFACE for _, payload in observations),
        "other_member_or_old_interface_observation")
    latest = observations[-1][1]
    raw_latest = originals[-1][1]
    _require(isinstance(latest.get("role_task"), str) and bool(latest["role_task"])
        and isinstance(latest["observation"].get("contract"), str) and bool(latest["observation"]["contract"])
        and latest["role_task"] == raw_latest.get("role_task")
        and latest["observation"]["contract"] == raw_latest["observation"].get("contract"),
        "latest_complete_instruction_or_contract_changed")
    reports = []
    for _, payload in observations:
        values = payload["observation"].get("initial_diagnostics", [])
        _require(isinstance(values, list), "malformed_initial_diagnostics")
        reports.extend(values)
    allowed = assignments.get(call["member"], [])
    _require(all(isinstance(report, dict) and report.get("diagnostic_id") in allowed
        and exact(report, initial.get(report.get("diagnostic_id"))) for report in reports), "unauthorized_initial_diagnostic")
    _require(all(any(exact(report, initial.get(identifier)) for report in reports) for identifier in allowed),
        "authorized_initial_diagnostic_missing")
    return sorted({report["diagnostic_id"] for report in reports})


def audit_projection(call, record, initial, assignments, ledger_snapshot, *, capacity_binding=None,
                     representation="Gamma0", candidate_sha256=CANDIDATE_SHA256):
    folder = Path(call["path"]).parent
    result = {"actual_input": point(call), "projection_source": base.pointer(folder / "projection.json", "/"),
        "status": "unresolved", "issues": []}
    try:
        binding = representation_binding(representation, candidate_sha256)
        if representation == "Gamma0":
            audited = previous.audit_projection(call, record, initial, assignments, ledger_snapshot,
                capacity_binding=capacity_binding)
            return {**audited, "representation": binding, "uses_v044_feedback": True}
        result["representation"] = binding
        original, selected, projection, response = (load(folder / name) for name in
            ("original-request.json", "selected-request.json", "projection.json", "response.json"))
        if any(value is None for value in (original, selected, projection, response, ledger_snapshot)):
            result["issues"].append("missing_original_selected_projection_response_or_lifecycle_state")
            return result
        formatted, feedback = project_format_feedback(original, ledger=ledger_snapshot, member_id=call["member"])
        static, deduplication = deduplicate_static_snapshots(formatted)
        referenced, expected_references = rebuild_reference_stage(static, formatted, call["member"])
        _require(projection.get("version") == PROJECTION_VERSION
            and exact(projection.get("actual_presentation"), reference_protocol.presentation_identity()),
            "wrong_representation_or_candidate_identity")
        _require(exact(projection.get("format_feedback_projection"), feedback)
            and exact(load(folder / "feedback-lifecycle-before.json"), ledger_snapshot), "feedback_timeline_or_projection_changed")
        _require(exact(projection.get("deduplication"), deduplication), "v041_static_projection_changed")
        refs = projection["same_input_references"]
        _require(refs.get("candidate_sha256") == candidate_sha256
            and refs.get("version") == reference_protocol.CANDIDATE_VERSION
            and refs.get("allowlist") == list(reference_protocol.ALLOWLIST)
            and refs.get("eligible") is expected_references["eligible"]
            and exact(refs.get("generated_references"), expected_references["generated_references"])
            and refs.get("input_request_sha256") == digest(json_bytes(static))
            and refs.get("referenced_request_sha256") == digest(json_bytes(referenced)), "same_input_reference_reconstruction_mismatch")
        if expected_references["eligible"]:
            _require(all(exact(refs.get(key), expected_references[key]) for key in
                ("member_identity", "root_identity", "first_observation_index", "latest_observation_index")),
                "pre_static_root_or_member_reference_receipt_changed")
        stage = projection["context_stage_projection"]
        _require(stage.get("version") == "software-context-v0.28.1"
            and exact(projection.get("inherited_capacity_projection"), stage)
            and stage.get("retained_messages_unchanged") is True, "capacity_selector_identity_changed")
        indices = stage["selected_indices"]
        expected_selected = _selected(referenced, indices)
        _require(exact(selected, expected_selected), "selected_messages_differ_from_reconstructed_reference_stage")
        pairs = complete_pairs(referenced["messages"])
        removed = sorted(set(range(len(referenced["messages"]))) - set(indices))
        allowed_prefixes = [sorted(i for pair in pairs[:count] for i in pair) for count in range(max(1, len(pairs)))]
        _require(removed in allowed_prefixes and stage.get("removed_indices") == removed
            and stage.get("complete_tool_rounds") == [list(pair) for pair in pairs]
            and stage.get("latest_complete_round_preserved") == (list(pairs[-1]) if pairs else None),
            "not_original_oldest_complete_round_selection")
        count = allowed_prefixes.index(removed)
        measurements = stage["measurements"]
        _require(len(measurements) == count + 1 and all(row.get("removed_indices") == allowed_prefixes[index]
            and type(row.get("prompt_tokens")) is int and row["prompt_tokens"] > 0
            for index, row in enumerate(measurements)), "capacity_measurement_round_prefix_mismatch")
        _require(all(row["prompt_tokens"] + 2048 > 18432 for row in measurements[:-1])
            and measurements[-1]["prompt_tokens"] + 2048 <= 18432, "unjustified_capacity_round_removal")
        _require(stage.get("original_prompt_tokens") == measurements[0]["prompt_tokens"]
            and stage.get("selected_prompt_tokens") == measurements[-1]["prompt_tokens"]
            and stage.get("original_request_sha256") == digest(json_bytes(referenced)), "capacity_stage_input_identity_mismatch")
        selected_proof = reference_protocol.validate_reference_projection(selected, static, indices, refs)
        _require(exact(projection.get("selected_reference_validation"), selected_proof), "selected_reference_receipt_changed")
        protected_removed = sorted(i for pair in pairs[:-1] for i in pair)
        protected_indices = [i for i in range(len(referenced["messages"])) if i not in protected_removed]
        protected = _selected(referenced, protected_indices)
        protected_proof = reference_protocol.validate_reference_projection(protected, static, protected_indices, refs)
        _require(exact(projection.get("protected_reference_validation"), protected_proof), "protected_reference_receipt_changed")
        mapping = feedback["selected_indices"]
        selected_original_indices = [mapping[i] for i in indices]
        protected_original_indices = [mapping[i] for i in protected_indices]
        _require(projection.get("selected_indices") == selected_original_indices
            and projection.get("removed_indices") == [i for i in range(len(original["messages"])) if i not in selected_original_indices]
            and projection.get("protected_selected_indices") == protected_original_indices, "original_message_index_composition_mismatch")
        expected_protected = {"version": PROJECTION_VERSION, "format_feedback_projection": feedback,
            "context_stage_projection": {"selected_indices": protected_indices, "removed_indices": protected_removed,
                "complete_tool_rounds": [list(pair) for pair in pairs], "latest_complete_round_preserved": list(pairs[-1]) if pairs else None},
            "selected_indices": protected_original_indices,
            "removed_indices": [i for i in range(len(original["messages"])) if i not in protected_original_indices],
            "request_sha256": digest(json_bytes(protected)), "reference_validation": protected_proof}
        _require(exact(projection.get("protected_projection"), expected_protected), "protected_request_or_reference_proof_changed")
        prep = record.get("reservation", {}).get("preparation", {})
        capacity.validate_preparation_capacity(prep, capacity_binding)
        body = response.get("body", {})
        trace, usage = body.get("token_trace", {}), body.get("usage", {})
        charge = record.get("charge", {})
        _require(response.get("http_status") == 200 and body.get("id") == charge.get("response_id")
            and digest(json_bytes(body)) == charge.get("response_body_sha256")
            and exact(usage, charge.get("reported_usage")) and body.get("actor_identity") == prep.get("actor_identity")
            and body.get("online_window_id") == prep.get("window_id"), "original_response_usage_or_actor_binding_mismatch")
        _require(type(usage.get("prompt_tokens")) is int and usage["prompt_tokens"] > 0
            and isinstance(trace.get("input_ids"), list) and len(trace["input_ids"]) == usage["prompt_tokens"]
            and isinstance(trace.get("output_ids"), list) and len(trace["output_ids"]) == usage.get("completion_tokens")
            and usage.get("total_tokens") == usage["prompt_tokens"] + usage["completion_tokens"] == charge.get("charged_tokens"),
            "actual_token_trace_counts_or_charge_mismatch")
        _require(projection.get("original_request_sha256") == prep.get("original_request_sha256") == digest(json_bytes(original))
            and projection.get("selected_request_sha256") == prep.get("selected_request_sha256")
                == call["selected_request_sha256"] == digest(json_bytes(selected))
            and projection.get("input_ids_sha256") == prep.get("input_ids_sha256") == call["input_ids_sha256"]
                == digest(json_bytes(trace["input_ids"]))
            and projection.get("selected_prompt_tokens") == prep.get("prompt_tokens") == usage["prompt_tokens"],
            "original_selected_preparation_or_actual_input_mismatch")
        _require(projection.get("rendered_prompt_sha256") == prep.get("rendered_prompt_sha256")
            and projection.get("context_limit") == 18432 and projection.get("reserved_output_tokens") == selected.get("max_tokens") == 2048
            and projection.get("fits") is prep.get("fits") is True and usage["prompt_tokens"] + 2048 <= 18432,
            "frozen_capacity_or_output_contract_mismatch")
        for key in ("selected_request_sha256", "input_ids_sha256", "rendered_prompt_sha256", "selected_prompt_tokens", "fits", "context_limit", "reserved_output_tokens"):
            _require(exact(stage.get(key), projection.get(key)), "capacity_receipt_differs:" + key)
        protected_tokens = projection.get("protected_prompt_tokens")
        _require(type(protected_tokens) is int and protected_tokens > 0
            and projection.get("protected_request_sha256") == digest(json_bytes(protected))
            and all(isinstance(projection.get(key), str) and len(projection[key]) == 64 for key in
                ("protected_input_ids_sha256", "protected_rendered_prompt_sha256"))
            and projection.get("protected_headroom_tokens") == 18432 - 2048 - protected_tokens
            and projection.get("protected_margin_tokens") == 1024
            and projection.get("protected_headroom_after_margin") == 18432 - 2048 - protected_tokens - 1024,
            "protected_measurement_receipt_inconsistent")
        if indices == protected_indices:
            _require(protected_tokens == usage["prompt_tokens"]
                and projection["protected_input_ids_sha256"] == projection["input_ids_sha256"]
                and projection["protected_rendered_prompt_sha256"] == projection["rendered_prompt_sha256"],
                "identical_actual_and_protected_request_encoding_differs")
        report_ids = _permission_and_static_checks(original, selected, call, initial, assignments)
        result.update(status="verified", projection_version=PROJECTION_VERSION, uses_v044_feedback=True,
            selected_prompt_tokens=usage["prompt_tokens"], context_limit=18432, reserved_output_tokens=2048,
            protected_prompt_tokens=protected_tokens, protected_request_sha256=projection["protected_request_sha256"],
            protected_engineering_margin_tokens=1024, protected_headroom_after_margin_tokens=18432 - 2048 - protected_tokens - 1024,
            protected_encoding_recomputed=False, initial_report_ids_present=report_ids,
            latest_complete_round_present=bool(pairs), declared_duplicate_fields_removed=len(deduplication["removed_values"]),
            generated_references=len(expected_references["generated_references"]),
            selected_reference_validation=selected_proof, protected_reference_validation=protected_proof,
            format_feedback_projection=feedback,
            lifecycle_evidence_scope="Rebuilt from original SDK/selected/response/settlement events; G1 fields independently reconstructed from pre-v041 bindings. No tokenizer call.")
    except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
        result["issues"].append("v048_projection_or_binding_violation: " + str(error))
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


def _measure_episode(episode_dir, *, representation, candidate_sha256):
    binding = representation_binding(representation, candidate_sha256)
    folder = Path(episode_dir).resolve()
    result = load(folder / "slot-result.json", {})
    output = {"version": VERSION, "episode": str(folder), "slot_id": result.get("slot_id"),
        "representation": binding, "status": "unresolved", "episode_closed": result.get("status") == "closed", "read_only": True,
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
                               timeline["before_call"].get(call["call_id"]), capacity_binding=capacity_binding,
                               representation=representation, candidate_sha256=candidate_sha256)
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
            "actual_generated_requests": len(inputs.calls), "requests_verified_under_v048": sum(a["status"] == "verified" for a in audits),
            "projection_violations": [a["actual_input"]["call_id"] for a in audits if a["status"] == "violation"],
            "projection_unresolved": [a["actual_input"]["call_id"] for a in audits if a["status"] == "unresolved"],
            "feedback_missing_from_first_actual_followup": protected_missing,
            "context_blocked_feedback_ids": blocked, "unresolved_no_followup_ids": unresolved_no_followup,
            "criterion": "Execution/presentation only. No score, message-frequency, page count, report-completion, recruitment or success selection."},
        scope="Full feedback archive, v044 actionable projection, actual presentation, supersession and legal-schema history are separate. Page/feedback chronological follow-ups do not prove semantic or causal adoption; old results remain unchanged.")
    return output


def measure_episode(episode_dir, representation="Gamma0", candidate_sha256=CANDIDATE_SHA256):
    try:
        return _measure_episode(episode_dir, representation=representation, candidate_sha256=candidate_sha256)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        return {"version": VERSION, "episode": str(Path(episode_dir).resolve()), "status": "unresolved", "read_only": True,
            "new_model_calls": 0, "new_tokenizer_calls": 0, "new_test_or_acceptance_executions": 0,
            "representation": {"representation": representation, "candidate_sha256": candidate_sha256},
            "feedback_records": [], "measurement_gaps": [{"reason": "unreadable_or_inconsistent_episode_evidence",
                "error_type": type(error).__name__, "detail": str(error)}],
            "mechanism_gate_inputs": {"resolved": False, "reasons": ["unreadable_or_inconsistent_episode_evidence"]}}
