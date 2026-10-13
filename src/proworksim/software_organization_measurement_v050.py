"""Read-only v050 native Γ1, feedback, accounting and local-stop evidence.

No old run is reclassified. The original v048 Γ1 algebra and v047 dispatch-time
proofs are reused with explicit v049 member/interface/window/state bindings.
The library provenance literal ``world_runtime_library=v047`` remains original;
the actual world/runtime is independently bound to v050 by its episode archive.
"""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path

from . import software_context_v048 as reference_protocol
from .software_context_v034 import observation_messages
from .software_context_v041 import deduplicate_static_snapshots
from .software_feedback_v044 import project_format_feedback
from .software_organization_v050 import INTERFACE_REVISION as PAGE_INTERFACE, validate_case
from .software_organization_runtime_v050 import VERSION as RUNTIME_VERSION, SCHEDULER
from .storage import atomic_write, digest, json_bytes
from scripts import measure_organization_work_v039 as base
from scripts.measure_organization_projection_v048 import (
    rebuild_reference_stage, _selected, _require,
)
from scripts.measure_organization_projection_v046 import (
    decoded, load, event_pointer, point, exact, complete_pairs, feedback_saved,
    matches_feedback, followup_candidates, final_relation, archived_reports,
    page_feedback, report_histories,
)
from scripts.measure_organization_budget_v047 import (
    validate_deadline_receipt, sealed, call_ids, one, reference,
)
from scripts.software_organization_reporting_v047 import outcome_values
from scripts.software_organization_stop_policy_v047 import (
    EvidenceProblem, require, unique, snapshot_valid, payload,
    INTEGRITY_KINDS, TECHNICAL_STATUSES, EFFECT_KINDS, GLOBAL_FACTS, PENDING_FACTS,
)

VERSION = "organization-native-measurement-v0.50"
PROJECTION_VERSION = reference_protocol.VERSION
CANDIDATE_SHA256 = reference_protocol.CANDIDATE_SHA256
MEMBERS = ["member_001", "member_002"]
OPPORTUNITY_KIND = "organization_work_opportunity_v049"
LIMIT = "max_total_tokens_exact_reservation"
REASON = "member_fixed_budget"


def representation_binding(representation, candidate_sha256):
    require(representation == "Gamma1" and candidate_sha256 == CANDIDATE_SHA256,
            "v049_requires_the_original_frozen_Gamma1")
    return {"representation": representation, "candidate_sha256": candidate_sha256}


def episode_binding(folder, *, result, budget):
    manifest = load(Path(folder) / "episode/manifest.json")
    require(isinstance(manifest, dict), "missing_episode_manifest", missing=True)
    scope = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
    require(manifest.get("status") == "closed" and scope.get("version") == RUNTIME_VERSION
        and scope.get("slot_id") == result.get("slot_id")
        and scope.get("actor_identity") == result.get("actor_identity")
        and scope.get("online_window_id") == result.get("online_window_id")
        and scope.get("learning_binding") == result.get("learning_binding")
        and scope.get("episode_start_steps") == result.get("episode_start_steps"),
        "episode_manifest_runtime_slot_or_loaded_state_mismatch")
    case = scope.get("case")
    validate_case(case)
    require(manifest["scenario"]["variation"].get("software_case") == case, "duplicated_source_case_differs")
    require(scope.get("purpose") == result.get("purpose") == case["purpose"]
        and scope.get("training_eligible") is result.get("training_eligible") is case["training_eligible"]
        and scope.get("scheduling_protocol") == SCHEDULER
        and result.get("condition") == case["condition"] == "O1"
        and case["active_roles"] == MEMBERS and budget.get("members") == MEMBERS,
        "episode_O1_source_or_member_identity_mismatch")
    window = result["online_window_id"]
    require(window == (case["training_window_id"] if case["training_eligible"]
                       else "organization-v050:" + result["slot_id"]), "wrong_source_logical_window")
    recipe = scope.get("recipe")
    require(isinstance(recipe, dict) and recipe.get("max_length") == 18432
        and recipe.get("max_output_tokens") == 2048
        and recipe.get("members") == [*MEMBERS, "software_inactive"]
        and scope.get("recipe_sha256") == digest(json_bytes(recipe)), "missing_or_wrong_original_recipe_binding")
    policies = manifest.get("policies", {})
    require(set(policies) == set(MEMBERS), "missing_or_extra_stable_member_policy")
    for member in MEMBERS:
        config = policies[member].get("config", {})
        require(config.get("weight_identity") == result["actor_identity"]
            and config.get("max_context_tokens") == 18432 and config.get("max_output_tokens") == 2048,
            "member_policy_differs_from_loaded_actor_or_capacity")
    bound = {"version": "v050-original-loaded-state-capacity-binding", "slot_id": result["slot_id"],
        "actor_identity": copy.deepcopy(result["actor_identity"]), "window_id": window,
        "recipe_sha256": scope["recipe_sha256"], "context_limit": 18432, "reserved_output_tokens": 2048,
        "episode_manifest": reference(Path(folder) / "episode/manifest.json"),
        "source_purpose": case["purpose"], "training_eligible": case["training_eligible"],
        "episode_start_steps": copy.deepcopy(scope["episode_start_steps"]),
        "inherited_projection_library_provenance": reference_protocol.presentation_identity(),
        "actual_world_runtime_version": RUNTIME_VERSION,
        "new_capacity_qualification_performed": False}
    validate_episode_capacity(bound, result=result, budget=budget)
    return bound


def validate_episode_capacity(binding, *, result, budget):
    require(isinstance(binding, dict) and binding.get("version") == "v050-original-loaded-state-capacity-binding",
            "missing_v049_loaded_state_binding", missing=binding is None)
    require(result.get("version") == RUNTIME_VERSION and result.get("condition") == "O1"
        and result.get("team_token_budget") == 500000
        and budget.get("limits") == {"max_decisions": 128, "max_attempts": 128, "max_total_tokens": 500000}
        and budget.get("team_id") == binding.get("window_id") == result.get("online_window_id")
        and binding.get("actor_identity") == result.get("actor_identity"), "episode_current_state_or_budget_mismatch")
    expected = {key: binding[key] for key in ("actor_identity", "window_id", "recipe_sha256")}
    require(budget.get("binding") == expected or budget.get("binding") is None and budget.get("attempts") == 0,
            "episode_ledger_actor_window_or_recipe_mismatch")
    return copy.deepcopy(binding)


def validate_preparation_capacity(prep, binding):
    require(sealed(prep, "preparation_sha256") and prep.get("context_limit") == 18432
        and prep.get("reserved_output_tokens") == 2048
        and all(prep.get(key) == binding.get(key) for key in ("actor_identity", "window_id", "recipe_sha256")),
        "prepared_native_input_differs_from_current_v049_state")
    return binding


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
    for _, observed in observations:
        values = observed["observation"].get("initial_diagnostics", [])
        _require(isinstance(values, list), "malformed_initial_diagnostics")
        reports.extend(values)
    allowed = assignments.get(call["member"], [])
    _require(all(isinstance(report, dict) and report.get("diagnostic_id") in allowed
        and exact(report, initial.get(report.get("diagnostic_id"))) for report in reports), "unauthorized_initial_diagnostic")
    _require(all(any(exact(report, initial.get(identifier)) for report in reports) for identifier in allowed),
        "authorized_initial_diagnostic_missing")
    return sorted({report["diagnostic_id"] for report in reports})


def audit_projection(call, record, initial, assignments, ledger_snapshot, *, capacity_binding=None,
                     representation="Gamma1", candidate_sha256=CANDIDATE_SHA256):
    folder = Path(call["path"]).parent
    result = {"actual_input": point(call), "projection_source": base.pointer(folder / "projection.json", "/"),
        "status": "unresolved", "issues": []}
    try:
        binding = representation_binding(representation, candidate_sha256)
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
        validate_preparation_capacity(prep, capacity_binding)
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
        result["issues"].append("v049_projection_or_binding_violation: " + str(error))
        result["status"] = "violation"
    return result


def bind_context(call_id, record, *, row, budget, evidence, events, feedback):
    """Bind only the saved rejection, without tokenizing or reconstructing inputs."""
    member = record.get("member")
    require(record.get("call_id") == call_id and member in budget.get("members", []), "rejected_call_or_member_mismatch")
    require(record.get("attempt_started") is False and record.get("status") == "admission_rejected",
            "context_rejection_started_or_not_rejected")
    require(not record.get("charge") and not record.get("reservation"), "context_rejection_has_charge_or_active_reservation")
    reservation = record.get("rejected_reservation", {})
    prep = reservation.get("preparation", {})
    require(bool(prep), "context_preparation_missing", missing=True)
    require(prep.get("preparation_sha256") == digest(json_bytes({k: v for k, v in prep.items() if k != "preparation_sha256"})),
            "context_preparation_hash_mismatch")
    require(all(isinstance(prep.get(k), str) and len(prep[k]) == 64 for k in ("original_request_sha256",
            "selected_request_sha256", "rendered_prompt_sha256", "input_ids_sha256")), "context_request_binding_hash_missing", missing=True)
    p, o, c = (prep.get(k) for k in ("prompt_tokens", "reserved_output_tokens", "context_limit"))
    require(type(p) is int and p > 0 and o == 2048 and c == 18432 and prep.get("fits") is False and p + o > c,
            "not_fixed_hard_context_overflow")
    require(reservation.get("input_token_reservation") == p and reservation.get("output_token_reservation") == o
            and reservation.get("token_reservation") == p + o
            and reservation.get("reservation_kind") == "exact_resident_prompt", "context_reservation_mismatch")
    ledger_binding = budget.get("binding")
    binding = ledger_binding or {key: feedback.get("capacity_binding", {}).get(key)
                                 for key in ("actor_identity", "window_id", "recipe_sha256")}
    identity, window = binding.get("actor_identity"), binding.get("window_id")
    require(bool(identity) and identity == row.get("actor_identity") == prep.get("actor_identity"), "context_actor_identity_mismatch")
    require(window == row["online_window_id"] and window == prep.get("window_id")
            and binding.get("recipe_sha256") == prep.get("recipe_sha256") and bool(binding.get("recipe_sha256")),
            "context_window_or_recipe_mismatch")
    require(record.get("budget_kind") == "context_capacity" and record.get("admission_limits") == ["context_capacity"],
            "context_rejection_kind_mismatch")
    start = unique([e for e in events if e.get("kind") == "model_call" and payload(e).get("call_id") == call_id
                    and payload(e).get("stage") == "started"], "context_call_start_missing_or_ambiguous")
    sp = payload(start)
    require(start.get("worker_id") == sp.get("worker_id") == member and sp.get("decision_id") == call_id
            and sp.get("weight_identity") == identity and sp.get("reservation") == reservation
            and sp.get("request_sha256") == prep.get("original_request_sha256"), "context_start_binding_mismatch")
    opportunity = sp.get("opportunity_id")
    require(isinstance(opportunity, str) and bool(opportunity), "context_opportunity_missing", missing=True)
    boundary = unique([e for e in events if e.get("kind") == "model_boundary_error"
                       and payload(e).get("opportunity_id") == opportunity], "context_boundary_missing_or_ambiguous")
    bp = payload(boundary)
    require(boundary.get("worker_id") == member and boundary["sequence"] > start["sequence"]
            and bp.get("status") == "model_budget_exhausted" and bp.get("budget_kind") == "context_capacity"
            and bp.get("limits") == ["context_capacity"], "context_boundary_binding_mismatch")
    contemporaneous = bp.get("team_budget", {})
    require(bool(contemporaneous), "context_boundary_snapshot_missing", missing=True)
    require(snapshot_valid(contemporaneous) and contemporaneous.get("binding") == ledger_binding
            and contemporaneous.get("records", {}).get(call_id) == record
            and not contemporaneous.get("integrity_failure"), "context_boundary_budget_mismatch")
    available = contemporaneous.get("available_tokens")
    require(type(available) is int and available >= 0, "context_team_available_tokens_not_trusted_nonnegative_integer")
    terminal = row.get("boundary", {}).get("terminal_details", {}).get(member, {})
    require(terminal.get("status") == row.get("boundary", {}).get("role_stops", {}).get(member) == "model_budget_exhausted"
            and terminal.get("cause") == terminal.get("budget_kind") == "context_capacity"
            and terminal.get("generation_started") is False
            and {"sequence": boundary["sequence"], "kind": "model_boundary_error"} in terminal.get("evidence", []),
            "context_member_terminal_mismatch")
    linked = [e for e in events if call_id in (payload(e).get("call_id"), payload(e).get("model_call_id"),
              payload(e).get("decision", {}).get("model_call_id") if isinstance(payload(e).get("decision"), dict) else None)]
    require(not any(e.get("kind") in EFFECT_KINDS or (e.get("kind") == "model_call" and payload(e).get("stage") == "finished")
                    for e in linked), "context_rejection_has_output_attempt_or_execution_effect")
    attempts = evidence.get("original_attempts", [])
    require(not any(a.get("call_id") == call_id for a in attempts), "context_rejection_has_original_output")
    require(not any(a.get("worker_id") == member and a.get("experience_sequence", -1) > start["sequence"] for a in attempts),
            "context_member_has_later_actual_generation")
    require(not any(e.get("worker_id") == member and e.get("sequence", -1) > boundary["sequence"]
                    and e.get("kind") in EFFECT_KINDS | {"model_call"} for e in events), "context_member_restarted_after_boundary")
    affected = []
    for f in feedback.get("feedback_records", []):
        if f.get("member") != member or (f.get("no_actual_followup") or {}).get("reason") != "context_capacity":
            continue
        presentation = f.get("presentation", {})
        require(f.get("generated_and_saved") is True and f.get("actual_originating_generation_bound") is True
                and f.get("experience_sequence", start["sequence"]) < start["sequence"], "context_feedback_source_not_bound")
        require(presentation.get("status") == "no_actual_followup" and presentation.get("later_actual_generation_count") == 0
                and presentation.get("first_actual_followup") is None and presentation.get("first_exact_presentation") is None
                and presentation.get("presented_in_first_actual_followup") is False
                and presentation.get("matching_actual_request_count") == 0, "context_feedback_has_actual_followup_or_presentation")
        require(f.get("no_actual_followup", {}).get("terminal_detail") == terminal, "context_feedback_terminal_mismatch")
        origin = unique([a for a in attempts if a.get("call_id") == f.get("originating_call_id")], "context_feedback_origin_missing_or_ambiguous")
        require(origin.get("worker_id") == member and origin.get("original_output_present") is True
                and origin.get("experience_sequence", start["sequence"]) < f["experience_sequence"], "context_feedback_origin_mismatch")
        original_feedback = unique([e for e in events if e.get("sequence") == f["experience_sequence"]], "context_feedback_event_missing_or_ambiguous")
        fp = payload(original_feedback)
        expected_kind = "model_format_feedback" if f.get("kind") == "format_feedback" else "model_tool_result"
        original_value = {"public_format_feedback": fp.get("feedback")} if expected_kind == "model_format_feedback" else fp.get("world_response")
        require(original_feedback.get("worker_id") == member and original_feedback.get("kind") == expected_kind
                and fp.get("call_id") == f.get("originating_call_id")
                and fp.get("model_tool_call_id") == f.get("model_tool_call_id")
                and digest(json_bytes(original_value)) == f.get("feedback_payload_sha256"), "context_feedback_event_binding_mismatch")
        affected.append(f["feedback_id"])
    return {"classification": "safe_local_resource_stop", "call_id": call_id, "member": member,
        "window_id": window, "opportunity_id": opportunity, "call_experience_sequence": start["sequence"],
        "boundary_experience_sequence": boundary["sequence"], "preparation_sha256": prep["preparation_sha256"],
        "selected_request_sha256": prep.get("selected_request_sha256"), "input_ids_sha256": prep.get("input_ids_sha256"),
        "prompt_tokens": p, "reserved_output_tokens": o, "context_limit": c, "excess_tokens": p + o - c,
        "team_available_tokens_at_rejection": available, "concurrent_team_reservation_shortage": available < p + o,
        "attempt_started": False,
        "new_native_output": False, "charged_tokens": 0, "execution_side_effect": False,
        "context_blocked_feedback_ids": affected, "member_remains_stopped": True,
        "R_used_for_classification": False, "submission_timing_used_for_classification": False}


def bind_member_fixed_budget(call_id, *, result, budget, evidence, events, capacity_binding=None):
    """Pure strict proof. Equality at the cap is deliberately not a rejection."""
    validate_episode_capacity(capacity_binding, result=result, budget=budget)
    record = budget.get("records", {}).get(call_id, {})
    member = record.get("member")
    require(result.get("status") == "closed" and not result.get("boundary", {}).get("execution_integrity_failure")
            and not budget.get("integrity_failure"), "fixed_budget_episode_not_safely_closed")
    require(record == {"call_id": call_id, "member": member, "status": "decision_consumed", "attempt_started": False}
            and member in budget.get("members", []), "fixed_budget_entered_shared_admission_or_charge")
    start = one([e for e in events if e.get("kind") == "model_call" and call_id in call_ids(e)
                 and payload(e).get("stage") == "started"], "fixed_budget_missing_unique_start")
    stop = one([e for e in events if e.get("kind") == "model_budget_stop" and call_id in call_ids(e)],
               "fixed_budget_missing_unique_stop")
    sp, tp = payload(start), payload(stop)
    opportunity = sp.get("opportunity_id")
    require(isinstance(opportunity, str) and opportunity.startswith("staff-opportunity-"),
            "fixed_budget_missing_original_opportunity")
    boundary = one([e for e in events if e.get("kind") == "model_boundary_error"
                    and (call_id in call_ids(e) or payload(e).get("opportunity_id") == opportunity)],
                   "fixed_budget_missing_unique_boundary")
    ep = payload(boundary)
    require(start.get("worker_id") == stop.get("worker_id") == boundary.get("worker_id") == sp.get("worker_id") == member
            and sp.get("call_id") == sp.get("decision_id") == tp.get("call_id") == ep.get("model_call_id") == call_id
            and ep.get("opportunity_id") == opportunity
            and start["sequence"] < stop["sequence"] < boundary["sequence"], "fixed_budget_call_member_or_order_mismatch")
    reservation = sp.get("reservation", {})
    prep = reservation.get("preparation", {})
    require(bool(prep) and reservation == tp.get("reservation") and sealed(prep, "preparation_sha256"),
            "fixed_budget_missing_or_mismatched_sealed_preparation")
    require(all(isinstance(prep.get(k), str) and len(prep[k]) == 64
                and all(c in "0123456789abcdef" for c in prep[k]) for k in
                ("original_request_sha256", "selected_request_sha256", "rendered_prompt_sha256", "input_ids_sha256")),
            "fixed_budget_missing_original_input_identity")
    binding = budget.get("binding", {})
    require(bool(binding.get("actor_identity")) and binding["actor_identity"] == result.get("actor_identity")
            == prep.get("actor_identity") == sp.get("weight_identity")
            and binding.get("window_id") == prep.get("window_id") == result["online_window_id"]
            and bool(binding.get("recipe_sha256")) and binding["recipe_sha256"] == prep.get("recipe_sha256")
            and prep["original_request_sha256"] == sp.get("request_sha256")
            == sp.get("context_selection", {}).get("request_sha256"), "fixed_budget_slot_actor_recipe_or_input_mismatch")
    p, o, c = (prep.get(k) for k in ("prompt_tokens", "reserved_output_tokens", "context_limit"))
    require(type(p) is int and p > 0 and type(o) is int and o == 2048 and type(c) is int and c == 18432
            and type(prep.get("fits")) is bool and prep["fits"] == (p + o <= c),
            "fixed_budget_context_fit_arithmetic_mismatch")
    require(reservation.get("reservation_kind") == "exact_resident_prompt"
            and reservation.get("input_token_reservation") == p and reservation.get("output_token_reservation") == o
            and reservation.get("token_reservation") == p + o, "fixed_budget_exact_reservation_mismatch")
    require(tp.get("limits") == ep.get("limits") == [LIMIT] and ep.get("status") == "model_budget_exhausted"
            and ep.get("budget_kind") is None, "fixed_budget_different_rejection_kind")
    config, meter = sp.get("config", {}), tp.get("meter", {})
    cap = config.get("budget", {}).get("max_total_tokens")
    require(type(cap) is int and cap == 500000 and config.get("backend_id") == "resident_direct"
            and config.get("max_output_tokens") == o and config.get("max_context_tokens") == c,
            "fixed_budget_original_member_cap_or_config_mismatch")
    attempts = evidence.get("original_attempts", [])
    require(len({a.get("call_id") for a in attempts}) == len(attempts), "fixed_budget_duplicate_original_attempt")
    prior = [a for a in attempts if a.get("worker_id") == member and a.get("experience_sequence", -1) < start["sequence"]]
    require(not any(a.get("call_id") == call_id for a in attempts)
            and not any(a.get("worker_id") == member and a.get("experience_sequence", -1) > start["sequence"] for a in attempts),
            "fixed_budget_original_output_or_later_generation_exists")
    charged = 0
    for original in prior:
        old = budget["records"].get(original["call_id"], {})
        charge, usage = old.get("charge", {}), original.get("usage", {})
        require(old.get("member") == member and old.get("attempt_started") is True and old.get("status") == "settled"
                and original.get("status") == "success" and original.get("original_output_present") is True
                and charge.get("usage_status") == "reported_actual_trace" and charge.get("reported_usage") == usage
                and charge.get("response_id") == original.get("response_id") and bool(original.get("response_id"))
                and charge.get("response_body_sha256") == original.get("response_body_sha256")
                and bool(original.get("response_body_sha256"))
                and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                and charge.get("charged_tokens") == usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"],
                "fixed_budget_original_member_charge_not_exact")
        charged += usage["total_tokens"]
    require({k for k, r in budget["records"].items() if r.get("member") == member and r.get("attempt_started") is True}
            == {a["call_id"] for a in prior}, "fixed_budget_member_attempt_inventory_mismatch")
    require(type(meter.get("budget_accounted_tokens")) is int
            and meter["budget_accounted_tokens"] == meter.get("reported_total_tokens") == charged
            and meter.get("http_attempts") == len(prior) and meter.get("unknown_usage_attempts") == 0
            and charged + p + o > cap, "fixed_budget_member_meter_does_not_prove_strict_excess")
    linked = [e for e in events if call_id in call_ids(e)]
    require([(e["kind"], e["sequence"]) for e in linked]
            == [(e["kind"], e["sequence"]) for e in (start, stop, boundary)],
            "fixed_budget_unexpected_attempt_output_or_world_effect")
    require(not any(e.get("kind") in INTEGRITY_KINDS for e in events), "fixed_budget_integrity_fault_present")
    require(not any(e.get("worker_id") == member and e.get("sequence", -1) > start["sequence"]
                    and (e.get("kind") in EFFECT_KINDS or e.get("kind") == "model_call") for e in events),
            "fixed_budget_member_later_generation_or_world_effect")
    snapshots = [e for e in events if e.get("kind") == OPPORTUNITY_KIND
                 and payload(e).get("opportunity_id") == opportunity]
    require(len(snapshots) == 2 and [payload(e).get("phase") for e in snapshots] == ["before", "after"],
            "fixed_budget_missing_original_opportunity_pair")
    before, after = snapshots
    bp, ap = payload(before), payload(after)
    bb, ab = bp.get("team_budget", {}), ap.get("team_budget", {})
    require(before.get("worker_id") == after.get("worker_id") == bp.get("member_id") == ap.get("member_id") == member
            and bp.get("opportunity_ordinal") == ap.get("opportunity_ordinal")
            and before["sequence"] < start["sequence"] < boundary["sequence"] < after["sequence"]
            and bp.get("world_event_sequence") == ap.get("world_event_sequence")
            and type(bp.get("world_event_sequence")) is int
            and ap.get("outcome_status") == "model_budget_exhausted", "fixed_budget_opportunity_or_world_changed")
    require(sealed(bb, "state_sha256") and sealed(ab, "state_sha256") and sealed(budget, "state_sha256")
            and bb.get("binding") == ab.get("binding") == binding
            and not bb.get("integrity_failure") and not ab.get("integrity_failure")
            and call_id not in bb.get("records", {})
            and ab.get("records") == {**bb.get("records", {}), call_id: record}
            and ab.get("decisions") == bb.get("decisions", -1) + 1
            and ab.get("remaining_decisions") == bb.get("remaining_decisions", -1) - 1
            and all(ab.get(k) == bb.get(k) and type(bb.get(k)) is int for k in
                    ("attempts", "charged_tokens", "held_tokens", "available_tokens", "remaining_attempts")),
            "fixed_budget_shared_reservation_charge_or_snapshot_changed")
    terminal = result.get("boundary", {}).get("terminal_details", {}).get(member, {})
    require(terminal.get("status") == result["boundary"].get("role_stops", {}).get(member) == "model_budget_exhausted"
            and terminal.get("cause") == "model_budget_exhausted" and terminal.get("limits") == [LIMIT]
            and all({"sequence": e["sequence"], "kind": e["kind"]} in terminal.get("evidence", []) for e in (stop, boundary)),
            "fixed_budget_terminal_not_bound_to_original_stop")
    return {"version": VERSION, "reason": REASON, "status": "bound_original_member_fixed_budget",
        "slot_id": result["slot_id"], "member": member, "call_id": call_id, "opportunity_id": opportunity,
        "window_id": prep["window_id"], "preparation_source": "original_model_call_started_and_model_budget_stop",
        "preparation": copy.deepcopy(prep), "reservation": copy.deepcopy(reservation),
        "start_experience_sequence": start["sequence"], "stop_experience_sequence": stop["sequence"],
        "boundary_experience_sequence": boundary["sequence"], "before_experience_sequence": before["sequence"],
        "after_experience_sequence": after["sequence"], "member_accounted_tokens": charged,
        "member_fixed_token_cap": cap, "member_available_tokens": cap - charged,
        "shared_available_tokens_before_opportunity": bb["available_tokens"],
        "hard_context_headroom_tokens": c - p - o, "concurrent_hard_context_overflow": p + o > c,
        "recorded_first_refusal": "member_fixed_budget_before_shared_reserve",
        "attempt_started": False, "charged_tokens": 0,
        "actual_output": False, "world_side_effect": False, "later_member_generation": False,
        "actual_feedback_presentation_added": False, "R_used_for_classification": False,
        "member_remains_stopped": True, "shared_ledger_not_rewritten": True}


def bind_shared_budget(call_id, record, *, row, budget, evidence, events, binding):
    member = record.get("member")
    require(record.get("call_id") == call_id and member in MEMBERS
        and record.get("status") == "admission_rejected" and record.get("attempt_started") is False
        and not record.get("charge") and not record.get("reservation") and not record.get("budget_kind"),
        "shared_refusal_has_attempt_charge_or_other_cause")
    reservation = record.get("rejected_reservation", {})
    prep = reservation.get("preparation", {})
    validate_preparation_capacity(prep, binding)
    p, o = prep.get("prompt_tokens"), prep.get("reserved_output_tokens")
    require(type(p) is int and p > 0 and prep.get("fits") is True and p + o <= 18432
        and reservation.get("token_reservation") == p + o
        and reservation.get("input_token_reservation") == p and reservation.get("output_token_reservation") == o,
        "shared_refusal_not_exact_fitting_reservation")
    start = unique([e for e in events if e.get("kind") == "model_call" and payload(e).get("call_id") == call_id
                    and payload(e).get("stage") == "started"], "shared_refusal_start_not_unique")
    sp = payload(start)
    opportunity = sp.get("opportunity_id")
    boundary = unique([e for e in events if e.get("kind") == "model_boundary_error"
                       and payload(e).get("opportunity_id") == opportunity], "shared_refusal_boundary_not_unique")
    ep = payload(boundary)
    saved = ep.get("team_budget", {})
    limits = record.get("admission_limits")
    require(start.get("worker_id") == boundary.get("worker_id") == sp.get("worker_id") == member
        and sp.get("decision_id") == call_id and sp.get("reservation") == reservation
        and sp.get("request_sha256") == prep.get("original_request_sha256")
        and sp.get("weight_identity") == row.get("actor_identity")
        and boundary["sequence"] > start["sequence"]
        and ep.get("status") == "team_budget_exhausted" and ep.get("limits") == limits
        and snapshot_valid(saved) and saved.get("records", {}).get(call_id) == record
        and saved.get("binding") == budget.get("binding") and not saved.get("integrity_failure"),
        "shared_refusal_original_binding_mismatch")
    expected = []
    pending = sum(item.get("status") == "reserved" for item in saved.get("records", {}).values())
    if saved.get("attempts", 0) + pending >= 128:
        expected.append("team_max_attempts")
    if p + o > saved.get("available_tokens", 500000):
        expected.append("team_max_total_tokens")
    require(bool(expected) and limits == expected, "shared_refusal_does_not_prove_actual_shortage")
    linked = [e for e in events if call_id in call_ids(e)]
    require(not any(e.get("kind") in EFFECT_KINDS or e.get("kind") == "model_call"
                    and payload(e).get("stage") == "finished" for e in linked), "shared_refusal_has_actual_effect")
    require(not any(a.get("call_id") == call_id or a.get("worker_id") == member
                    and a.get("experience_sequence", -1) > start["sequence"] for a in evidence.get("original_attempts", [])),
            "shared_refusal_has_output_or_member_was_restarted")
    require(not any(e.get("worker_id") == member and e.get("sequence", -1) > boundary["sequence"]
                    and e.get("kind") in EFFECT_KINDS | {"model_call"} for e in events),
            "shared_refusal_member_has_later_generation_or_effect")
    terminal = row.get("boundary", {}).get("terminal_details", {}).get(member, {})
    require(terminal.get("status") == row.get("boundary", {}).get("role_stops", {}).get(member) == "team_budget_exhausted"
        and {"kind": "model_boundary_error", "sequence": boundary["sequence"]} in terminal.get("evidence", []),
        "shared_refusal_terminal_not_original")
    return {"reason": "team_budget", "call_id": call_id, "member": member,
        "boundary_experience_sequence": boundary["sequence"], "start_experience_sequence": start["sequence"],
        "reservation_tokens": p + o, "available_tokens": saved["available_tokens"],
        "attempt_started": False, "charged_tokens": 0, "world_side_effect": False,
        "member_remains_stopped": True, "R_used_for_classification": False}


def resource_rejections(result, budget, evidence, events, binding):
    proofs, unresolved = {}, []
    for call_id, record in budget.get("records", {}).items():
        status = record.get("status")
        try:
            if record.get("budget_kind") == "context_capacity":
                proof = bind_context(call_id, record, row=result, budget=budget, evidence=evidence,
                    events=events, feedback={"capacity_binding": binding, "feedback_records": []})
                proof["reason"] = "context_capacity"
            elif status == "admission_rejected":
                proof = bind_shared_budget(call_id, record, row=result, budget=budget,
                    evidence=evidence, events=events, binding=binding)
            elif status == "decision_consumed":
                proof = bind_member_fixed_budget(call_id, result=result, budget=budget,
                    evidence=evidence, events=events, capacity_binding=binding)
            elif status in {"settled", "cancelled_before_dispatch"}:
                continue
            else:
                raise ValueError("Unclosed reservation or attempt is not a safe local resource stop")
            if proof["member"] in proofs:
                raise ValueError("One terminal member cannot acquire multiple refusal proofs")
            proofs[proof["member"]] = proof
        except (ValueError, KeyError, TypeError) as error:
            unresolved.append({"call_id": call_id, "status": status, "detail": str(error)})
    return proofs, unresolved


def no_followup_reason(row, result, events, budget, path, *, rejections):
    member, sequence = row["member"], row["experience_sequence"]
    boundary = result.get("boundary", {})
    terminal = boundary.get("terminal_details", {}).get(member, {})
    proof = rejections.get(member)
    reason, provenance = "unknown_no_actual_followup", None
    if proof and proof.get("boundary_experience_sequence", -1) > sequence:
        reason, provenance = proof["reason"], proof
    elif boundary.get("closure_reason") == "shared_team_pool_exhausted" and any(
            budget.get(key) == 0 for key in ("remaining_decisions", "remaining_attempts", "available_tokens")):
        reason = "team_budget"
    elif member in boundary.get("waiting_members", {}):
        sleeps = [(i, event) for i, event in enumerate(events)
            if event.get("kind") == "organization_work_boundary_v049" and event.get("worker_id") == member
            and event.get("sequence", -1) > sequence and payload(event) in boundary.get("work_boundaries", [])]
        if sleeps:
            i, event = sleeps[-1]
            ended = member in boundary.get("current_work_ended", {})
            reason = "current_work_ended_no_reachable_event" if ended else "waiting_without_event"
            provenance = {"source": event_pointer(path, i, event), "original_boundary": payload(event),
                          "permanent_retirement": False, "actual_visibility_added": False}
    if reason == "unknown_no_actual_followup" and result.get("administrative_censoring") is True:
        try:
            provenance = validate_deadline_receipt(result, budget, events)
            reason = "administrative_soft_deadline"
        except (KeyError, TypeError, ValueError):
            pass
    if reason == "unknown_no_actual_followup" and boundary.get("execution_integrity_failure"):
        reason = "execution_fault"
    return {"reason": reason, "terminal_detail": terminal, "original_termination_proof": copy.deepcopy(provenance),
            "denominator_scope": "No later bound actual generation by this same stable member; never infer retirement or presentation"}


def lifecycle_history(folder, evidence, budget, events, inputs):
    """Bind actual generations only; pre-dispatch refusals never create feedback visibility.

    The old historical replay also rebuilt refused inputs from a first generated
    template. O1 can legitimately reject a member before its first generation;
    no such template is needed to reconstruct the actual feedback lifecycle.
    """
    from scripts.software_context_replay_v044 import (
        EVENT_KINDS, _brief_lifecycle_event, association,
    )
    require([event.get("sequence") for event in events] == list(range(len(events))),
            "original_runtime_event_order_not_consecutive")
    requests, originals = [], {row["call_id"]: row for row in evidence["original_attempts"]}
    require(len(originals) == len(evidence["original_attempts"]), "duplicate_original_attempt")
    for call_id, call in inputs.calls.items():
        directory = Path(call["path"]).parent
        original, selected, response, prep = (load(directory / name) for name in
            ("original-request.json", "selected-request.json", "response.json", "budget-preparation.json"))
        require(all(value is not None for value in (original, selected, response, prep)),
                "missing_generated_native_artifact", missing=True)
        record, actual = budget["records"][call_id], originals[call_id]
        start = unique([event for event in events if event.get("kind") == "model_call"
            and payload(event).get("stage") == "started" and payload(event).get("call_id") == call_id],
            "native_start_not_unique")
        body, charge = response.get("body", {}), record.get("charge", {})
        require(record.get("status") == "settled" and record.get("attempt_started") is True
            and record.get("reservation", {}).get("preparation") == prep
            and start.get("worker_id") == actual.get("worker_id") == call["member"]
            and payload(start).get("request_sha256") == actual.get("request_sha256")
                == prep.get("original_request_sha256") == digest(json_bytes(original))
            and prep.get("selected_request_sha256") == digest(json_bytes(selected))
            and digest(json_bytes(body)) == actual.get("response_body_sha256") == charge.get("response_body_sha256")
            and body.get("id") == actual.get("response_id") == charge.get("response_id")
            and body.get("usage") == actual.get("usage") == charge.get("reported_usage")
            and charge.get("usage_status") == "reported_actual_trace", "native_lifecycle_start_response_or_charge_mismatch")
        requests.append({"kind": "generated", "call_id": call_id, "member": call["member"],
            "original_request": original, "selected_request": selected, "response": response,
            "recorded_preparation": prep, "association": association(payload(start)),
            "team_accounting": copy.deepcopy(charge),
            "sources": {"selected": reference(directory / "selected-request.json"),
                        "response": reference(directory / "response.json")}})
    by_call = {row["call_id"]: row for row in requests}
    reduced, format_errors = [], {}
    for index, event in enumerate(events):
        if event.get("kind") not in EVENT_KINDS:
            continue
        if event["kind"] == "model_format_error":
            format_errors[payload(event).get("call_id")] = event
        if event["kind"] == "model_format_feedback":
            original_error = format_errors.get(payload(event).get("call_id"))
            require(original_error is not None and original_error["sequence"] < event["sequence"]
                    and original_error.get("worker_id") == event.get("worker_id"),
                    "format_feedback_lacks_original_prior_runner_error")
        source = {"path": str(folder / "experience.jsonl"), "jsonl_line": index + 1,
                  "experience_sequence": event["sequence"]}
        brief = _brief_lifecycle_event(event, source)
        if brief is None:
            continue
        value, kind = brief["payload"], brief["kind"]
        row = by_call.get(value.get("call_id"))
        if row and kind in {"model_call", "model_attempt", "model_response", "model_format_error",
                            "model_format_feedback", "harness_explicit_json_control"}:
            require(brief["worker_id"] == row["member"] and association(value) == row["association"],
                    "native_lifecycle_association_changed")
            if kind == "model_attempt":
                require(value.get("status") == "success"
                    and value.get("request_sha256") == digest(json_bytes(row["original_request"]))
                    and value.get("response_sha256") == digest(json_bytes(row["response"]))
                    and value.get("team_accounting") == row["team_accounting"], "native_lifecycle_attempt_changed")
            elif kind == "model_response":
                require(value.get("response_body_sha256") == digest(json_bytes(row["response"]["body"])),
                        "native_lifecycle_response_changed")
        reduced.append(brief)
    return {"requests": requests, "events": reduced}


def _measure_feedback(episode_dir, *, representation="Gamma1", candidate_sha256=CANDIDATE_SHA256):
    binding = representation_binding(representation, candidate_sha256)
    folder = Path(episode_dir).resolve()
    result = load(folder / "slot-result.json", {})
    output = {"version": VERSION, "episode": str(folder), "slot_id": result.get("slot_id"),
        "representation": binding, "status": "unresolved", "episode_closed": result.get("status") == "closed", "read_only": True,
        "new_model_calls": 0, "new_tokenizer_calls": 0, "new_test_or_acceptance_executions": 0,
        "training_support": "Mechanical evidence only; training and Mapper validity are separate", "feedback_records": [], "projection_audit": [], "measurement_gaps": []}
    evidence_path, experience_path = folder / "organization-evidence.json", folder / "experience.jsonl"
    state_path = folder / "episode/end/control/state.json"
    missing = [str(p) for p in (folder / "slot-result.json", evidence_path, experience_path, state_path) if not p.is_file()]
    if missing:
        output["measurement_gaps"].append({"reason": "missing_episode_evidence", "paths": missing})
        output["mechanism_gate_inputs"] = {"resolved": False, "reasons": ["missing_episode_evidence"]}
        return output
    evidence, state = base.read(evidence_path), base.read(state_path)
    events = [json.loads(line) for line in experience_path.read_text().splitlines() if line.strip()]
    budget = result.get("team_budget", evidence.get("team_budget", {})).get("model", {})
    capacity_binding = episode_binding(folder, result=result, budget=budget)
    rejections, rejection_gaps = resource_rejections(result, budget, evidence, events, capacity_binding)
    inputs = base.Inputs(folder, evidence, budget)
    software = state["projects"][base.PROJECT]["software"]
    initial, assignments = software.get("initial_diagnostics", {}), software.get("initial_diagnostic_assignments", {})
    gaps = output["measurement_gaps"]
    gaps.extend(inputs.issues)
    gaps.extend({"reason": "resource_refusal_unresolved", **gap} for gap in rejection_gaps)
    attempts = [row for row in budget.get("records", {}).values() if row.get("attempt_started") is True]
    if len(attempts) != len(inputs.calls):
        gaps.append({"reason": "actual_attempts_without_complete_original_generation_binding",
                     "attempts": len(attempts), "bound_generations": len(inputs.calls)})
    if not initial or not assignments:
        gaps.append({"reason": "missing_authorized_initial_diagnostic_contract"})
    from scripts.software_context_replay_v044 import reconstruct_feedback_timeline
    timeline = reconstruct_feedback_timeline(lifecycle_history(folder, evidence, budget, events, inputs))
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
        row["no_actual_followup"] = no_followup_reason(row, result, events, budget, experience_path, rejections=rejections) if not later else None
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
        capacity_binding=validate_episode_capacity(capacity_binding, result=result, budget=budget),
        local_resource_rejections=copy.deepcopy(rejections),
        capacity_binding_source=reference(folder / "episode/manifest.json"),
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
            "actual_generated_requests": len(inputs.calls), "requests_verified_under_v049": sum(a["status"] == "verified" for a in audits),
            "projection_violations": [a["actual_input"]["call_id"] for a in audits if a["status"] == "violation"],
            "projection_unresolved": [a["actual_input"]["call_id"] for a in audits if a["status"] == "unresolved"],
            "feedback_missing_from_first_actual_followup": protected_missing,
            "context_blocked_feedback_ids": blocked, "unresolved_no_followup_ids": unresolved_no_followup,
            "criterion": "Execution/presentation only. No score, message-frequency, page count, report-completion, recruitment or success selection."},
        scope="Full feedback archive, v044 actionable projection, actual presentation, supersession and legal-schema history are separate. Page/feedback chronological follow-ups do not prove semantic or causal adoption; old results remain unchanged.")
    return output


def measure_feedback(episode_dir):
    """Read original archives; no world, tokenizer, model or acceptance execution."""
    try:
        return _measure_feedback(episode_dir)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        saved_result = load(Path(episode_dir) / "slot-result.json", {})
        return {"version": VERSION, "slot_id": saved_result.get("slot_id"), "episode": str(Path(episode_dir).resolve()), "status": "unresolved",
            "episode_closed": False, "read_only": True, "new_model_calls": 0, "new_tokenizer_calls": 0,
            "new_test_or_acceptance_executions": 0, "feedback_records": [], "projection_audit": [],
            "representation": representation_binding("Gamma1", CANDIDATE_SHA256),
            "measurement_gaps": [{"reason": "missing_or_inconsistent_original_evidence",
                "error_type": type(error).__name__, "detail": str(error)}],
            "mechanism_gate_inputs": {"resolved": False}}


def assess_records(row, feedback, team_budget, evidence, guard, events):
    """Pure host stop assessment, independent of success and composition support."""
    result = {"version": VERSION, "slot_id": row.get("slot_id"), "decision": "measurement_pending",
        "read_only": True, "global_violations": [], "unresolved": [],
        "formal_result": {key: row.get(key) for key in
            ("status", "R", "R_joint", "R_token", "Q_joint", "Q_token", "submitted", "complete_delivery")},
        "R_used_for_scope": False, "restart_current_member": False,
        "feedback_visibility_changed": False, "new_model_calls": 0, "new_tokenizer_calls": 0,
        "new_test_or_acceptance_executions": 0, "new_world_actions": 0,
        "scope": "A continue decision releases only independently authorized unstarted inventory."}
    bad, pending = result["global_violations"], result["unresolved"]
    facts, boundary, budget = feedback.get("mechanism_gate_inputs", {}), row.get("boundary", {}), team_budget.get("model", {})
    if row.get("version") != RUNTIME_VERSION or evidence.get("version") != RUNTIME_VERSION or feedback.get("version") != VERSION:
        bad.append("wrong_actual_v049_runtime_or_measurement_identity")
    for key in GLOBAL_FACTS:
        if facts.get(key):
            bad.append({key: copy.deepcopy(facts[key])})
    for key in PENDING_FACTS:
        if facts.get(key):
            pending.append({key: copy.deepcopy(facts[key])})
    if feedback.get("status") != "measured" or facts.get("resolved") is not True:
        pending.append({"feedback_or_projection_unresolved": feedback.get("measurement_gaps", [])})
    if facts.get("actual_generated_requests") != facts.get("requests_verified_under_v049"):
        pending.append("not_every_actual_input_is_verified")
    for key in ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged"):
        if key not in guard:
            pending.append("missing_guard:" + key)
        elif guard[key] is not True:
            bad.append("failed_guard:" + key)
    if not guard.get("learning_before_sha256") or not guard.get("rng_before_sha256"):
        pending.append("missing_original_guard_hashes")
    if (guard.get("learning_before_sha256") != guard.get("learning_after_sha256")
            or guard.get("rng_before_sha256") != guard.get("rng_after_restore_sha256")):
        bad.append("guard_hash_mismatch")
    if any(row.get(key) != 0 for key in ("actor_updates", "critic_updates", "new_backward_calls")):
        bad.append("learning_occurred_inside_frozen_episode")
    if boundary.get("execution_integrity_failure") or budget.get("integrity_failure"):
        bad.append("execution_or_billing_integrity_failure")
    if row.get("process_violation") or row.get("assessment", {}).get("process_violation"):
        bad.append("process_violation")
    for member, status in boundary.get("role_stops", {}).items():
        if member not in MEMBERS or status not in {"model_budget_exhausted", "team_budget_exhausted"}:
            bad.append({"untrusted_member_terminal": member, "status": status})
    for event in events:
        value = payload(event)
        if (event.get("kind") in INTEGRITY_KINDS or value.get("status") in TECHNICAL_STATUSES
                or event.get("kind") == "model_boundary_error"
                and value.get("status") not in {"model_budget_exhausted", "team_budget_exhausted"}):
            bad.append({"integrity_event": event.get("sequence"), "kind": event.get("kind")})
    try:
        require(row.get("status") == "closed" and type(row.get("R")) is int and row["R"] in (0, 1),
                "episode_lacks_known_closed_formal_result", missing=True)
        assessment = row.get("assessment", {})
        require(assessment.get("status") == "evaluable", "formal_assessment_unknown", missing=True)
        require(assessment.get("R") == row.get("R") and assessment.get("submitted") == row.get("submitted"),
                "formal_assessment_disagrees_with_result")
        require(feedback.get("slot_id") == team_budget.get("slot_id") == row["slot_id"], "slot_identity_mismatch")
        require(snapshot_valid(budget), "final_ledger_hash_mismatch")
        require(row.get("team_budget") == team_budget == evidence.get("team_budget") == boundary.get("team_budget"),
                "final_ledger_copies_disagree")
        usage, records = row.get("usage", {}), budget.get("records", {})
        attempts = evidence.get("original_attempts", [])
        require(usage == evidence.get("total_usage") and len({entry.get("call_id") for entry in attempts}) == len(attempts),
                "usage_or_unique_original_attempts_disagree")
        require(usage.get("uncertain_usage_attempts") == 0
            and usage.get("attempts") == len(attempts) == budget.get("attempts") == facts.get("actual_generated_requests")
            and usage.get("decisions") == budget.get("decisions") == len(records)
            and usage.get("total_tokens") == usage.get("budget_charged_tokens") == budget.get("charged_tokens")
                == sum(record.get("charge", {}).get("charged_tokens", 0) for record in records.values())
            and budget.get("held_tokens") == 0, "billing_or_attempt_inventory_incomplete")
        tests = team_budget.get("tests", {})
        require(tests.get("limit") == 32 and tests.get("used") == len(tests.get("records", []))
                and tests.get("remaining") == 32 - tests["used"], "test_budget_not_conserved")
        require(all(record.get("member") in MEMBERS and record.get("call_id") == call_id
                    and "stage_id" not in record for call_id, record in records.items()), "invalid_O1_member_or_phase_record")
        result["capacity_binding"] = validate_episode_capacity(feedback.get("capacity_binding"), result=row, budget=budget)
        result["outcome_scope"] = outcome_values(row)
        result["administrative_close"] = validate_deadline_receipt(row, budget, events)
        require(not result["administrative_close"].get("stage_transitions"), "O1_must_not_gain_architecture_stages")
        proofs = feedback.get("local_resource_rejections", {})
        for member in boundary.get("role_stops", {}):
            require(member in proofs, "terminal_member_lacks_safe_original_refusal_proof", missing=True)
        result["local_resource_rejections"] = copy.deepcopy(proofs)
        result["context_blocked_feedback_ids"] = copy.deepcopy(facts.get("context_blocked_feedback_ids", []))
        contexts = []
        for member, proof in proofs.items():
            if proof.get("reason") == "context_capacity":
                contexts.append(bind_context(proof["call_id"], records[proof["call_id"]], row=row,
                    budget=budget, evidence=evidence, events=events, feedback=feedback))
        require(sorted(identifier for proof in contexts for identifier in proof["context_blocked_feedback_ids"])
                == sorted(result["context_blocked_feedback_ids"]), "context_feedback_not_uniquely_bound", missing=True)
        result["local_context_events"] = contexts
        lifecycle = row.get("member_lifecycle", {})
        require(lifecycle.get("stable_member_ids") == MEMBERS and lifecycle.get("cumulative_births") == 2
            and lifecycle.get("live_at_end") == 2 and lifecycle.get("events") == []
            and all(record.get("status") == "live" for record in lifecycle.get("registry", {}).values()),
            "stable_O1_member_identity_changed")
    except EvidenceProblem as error:
        (pending if error.missing else bad).append(str(error))
    except (KeyError, TypeError, ValueError) as error:
        pending.append({"incomplete_original_mechanical_binding": str(error)})
    result["decision"] = "global_pause" if bad else "measurement_pending" if pending else "continue"
    result["classification"] = ("safe_administrative_close" if row.get("administrative_censoring")
        else "safe_local_resource_stop" if result.get("local_resource_rejections")
        else "ordinary_closed_stable_O1") if result["decision"] == "continue" else result["decision"]
    return result


def measure_slot(row, destination=None):
    """Measure one returned collector row; optionally save this new receipt only.

    ``row`` must be the unchanged collector result, not a merged or rewritten
    row. ``destination`` is a new report file; old records are never overwritten.
    The report contains ``feedback`` and ``stop_assessment``; ``decision`` aliases
    the latter. CPU fixtures remain explicitly fixtures, not model evidence.
    """
    folder = Path(row["episode_manifest"]).resolve().parent.parent
    saved = load(folder / "slot-result.json")
    report = {"version": VERSION, "slot_id": row.get("slot_id"), "episode": str(folder),
        "read_only": True, "new_model_calls": 0, "new_tokenizer_calls": 0,
        "new_test_or_acceptance_executions": 0, "new_world_actions": 0,
        "source_result": reference(folder / "slot-result.json")}
    try:
        require(saved == row, "supplied_row_differs_from_original_collector_result")
        feedback = measure_feedback(folder)
        events = [json.loads(line) for line in (folder / "experience.jsonl").read_text().splitlines() if line.strip()]
        stop = assess_records(saved, feedback, load(folder / "team-budget.json"),
            load(folder / "organization-evidence.json"), load(folder / "evaluation-guard.json"), events)
        report.update(feedback=feedback, stop_assessment=stop, decision=stop["decision"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        decision = "global_pause" if isinstance(error, EvidenceProblem) and not error.missing else "measurement_pending"
        report.update(decision=decision, feedback=None, stop_assessment={"decision": decision,
            "unresolved": [{"error_type": type(error).__name__, "detail": str(error)}]})
    if destination is not None:
        destination = Path(destination)
        if destination.exists():
            raise FileExistsError("A prior v049 mechanical receipt cannot be replaced")
        atomic_write(destination, json_bytes(report))
    return report
