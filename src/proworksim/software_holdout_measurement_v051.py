"""Readonly HOLD bindings for the unchanged v050 two-member Gamma1 proofs.

No S1 lifecycle transformation is used. The only initial-feedback adaptation
requires explicit evidence that this new protocol has no initial diagnostics.
"""
from __future__ import annotations

from collections import Counter
import copy
from pathlib import Path
from types import FunctionType

from . import software_organization_measurement_v050 as original
from .software_calibration_measurement_v051 import evidence_mode as native_evidence_mode
from .software_holdout_collector_v051 import VERSION as RUNTIME_VERSION, NATIVE_CONTRACT
from .software_holdout_world_v051 import INTERFACE_REVISION, MEMBERS, PURPOSE, SCHEDULER, validate_case
from .storage import atomic_write, digest, json_bytes

VERSION = "heldout-native-measurement-v0.51"
BINDING_VERSION = "v051-heldout-four-authorized-actors-capacity-binding"
CONDITIONS = ("S_star", "B", "Q_plus", "Q_minus")
require, load = original.require, original.load


def state_binding(row, state_authorizations):
    require(isinstance(state_authorizations, dict) and set(state_authorizations) == set(CONDITIONS),
            "missing_frozen_four_state_authorization_registry")
    condition = row.get("heldout_condition")
    require(condition in CONDITIONS, "unknown_heldout_condition")
    expected = state_authorizations[condition]
    identity = row.get("actor_identity", {})
    steps = row.get("episode_start_steps", {})
    historical = [4, 4] if condition == "S_star" else [5, 5]
    require(row.get("checkpoint_authorization") == expected
        and expected.get("historical_steps") == historical
        and [steps.get("actor_steps"), steps.get("critic_steps")] == historical
        and identity.get("checkpoint") == expected.get("checkpoint")
        and identity.get("retained_state_authorization") == expected
        and identity.get("source_actor_identity") == expected.get("actor_identity")
        and identity.get("adapter_sha256") == expected.get("actor_identity", {}).get("adapter_sha256")
        and bool(identity.get("adapter_sha256")), "heldout_condition_checkpoint_registry_or_steps_mismatch")
    return {"heldout_condition": condition, "checkpoint_authorization": copy.deepcopy(expected),
        "state_registry_sha256": digest(json_bytes(state_authorizations)), "historical_steps": historical}


def validate_episode_capacity(binding, *, result, budget):
    require(isinstance(binding, dict) and binding.get("version") == BINDING_VERSION,
            "missing_HOLD_readonly_actor_capacity_binding", missing=binding is None)
    require(result.get("version") == RUNTIME_VERSION and result.get("condition") == "O1"
        and result.get("purpose") == PURPOSE and result.get("training_eligible") is False
        and result.get("holdout_evaluation") is True and result.get("team_token_budget") == 500000
        and budget.get("members") == list(MEMBERS)
        and budget.get("limits") == {"max_decisions": 128, "max_attempts": 128, "max_total_tokens": 500000}
        and budget.get("team_id") == binding.get("window_id") == result.get("online_window_id")
        and binding.get("actor_identity") == result.get("actor_identity"), "heldout_loaded_state_or_budget_mismatch")
    expected = {key: binding[key] for key in ("actor_identity", "window_id", "recipe_sha256")}
    require(budget.get("binding") == expected or budget.get("binding") is None and budget.get("attempts") == 0,
            "heldout_ledger_actor_window_or_recipe_mismatch")
    return copy.deepcopy(binding)


def episode_binding(folder, *, result, budget, provider, state_authorizations):
    state = state_binding(result, state_authorizations)
    manifest = load(Path(folder) / "episode/manifest.json")
    require(isinstance(manifest, dict), "missing_HOLD_episode_manifest", missing=True)
    scope = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
    require(manifest.get("status") == "closed" and scope.get("version") == RUNTIME_VERSION
        and all(scope.get(key) == result.get(key) for key in ("slot_id", "heldout_condition", "checkpoint_authorization",
            "actor_identity", "online_window_id", "learning_binding", "episode_start_steps")),
        "heldout_episode_runtime_slot_or_loaded_state_mismatch")
    case = scope.get("case")
    validate_case(case, provider=provider)
    require(manifest["scenario"]["variation"].get("software_case") == case,
            "duplicated_HOLD_source_case_differs")
    require(scope.get("purpose") == result.get("purpose") == case["purpose"] == PURPOSE
        and scope.get("training_eligible") is result.get("training_eligible") is case["training_eligible"] is False
        and case.get("contribution_eligible") is case.get("independent_confirmation_eligible") is False
        and case.get("holdout_evaluation") is True and scope.get("scheduling_protocol") == SCHEDULER
        and result.get("condition") == case["condition"] == "O1"
        and case["active_roles"] == budget.get("members") == list(MEMBERS),
        "heldout_O1_source_or_fixed_member_identity_mismatch")
    window = result["online_window_id"]
    require(window == "holdout-v051:" + result["slot_id"], "wrong_HOLD_logical_window")
    recipe, contract = scope.get("recipe"), scope.get("native_contract")
    require(isinstance(recipe, dict) and recipe.get("max_length") == 18432
        and recipe.get("max_output_tokens") == 2048 and recipe.get("temperature") == .7
        and scope.get("recipe_sha256") == digest(json_bytes(recipe)), "wrong_HOLD_native_recipe")
    require(contract == NATIVE_CONTRACT and scope.get("native_contract_sha256") == digest(json_bytes(contract)),
            "wrong_HOLD_frozen_decoder")
    policies = manifest.get("policies", {})
    require(set(policies) == set(MEMBERS), "missing_or_extra_stable_HOLD_policy")
    for member in MEMBERS:
        config = policies[member].get("config", {})
        require(config.get("weight_identity") == result["actor_identity"]
            and config.get("max_context_tokens") == 18432 and config.get("max_output_tokens") == 2048
            and config.get("timeout_seconds") == 600, "HOLD_policy_differs_from_actor_or_capacity")
    bound = {"version": BINDING_VERSION, "slot_id": result["slot_id"], **state,
        "actor_identity": copy.deepcopy(result["actor_identity"]), "window_id": window,
        "recipe_sha256": scope["recipe_sha256"], "context_limit": 18432, "reserved_output_tokens": 2048,
        "episode_manifest": original.reference(Path(folder) / "episode/manifest.json"),
        "source_purpose": PURPOSE, "training_eligible": False,
        "episode_start_steps": copy.deepcopy(result["episode_start_steps"]),
        "native_contract_sha256": scope["native_contract_sha256"],
        "inherited_projection_library_provenance": original.reference_protocol.presentation_identity(),
        "actual_world_runtime_version": RUNTIME_VERSION, "new_capacity_qualification_performed": False}
    validate_episode_capacity(bound, result=result, budget=budget)
    return bound


def absent_initial_diagnostics(folder, *, provider):
    """Bind actual empty source state; never synthesize a diagnostic or test."""
    manifest = load(Path(folder) / "episode/manifest.json")
    case = manifest["scenario"]["variation"]["software_case"]
    validate_case(case, provider=provider)
    require(case.get("forced_initial_failure_feedback") is False and case.get("purpose") == PURPOSE,
            "HOLD_initial_diagnostic_absence_not_declared")
    references = []
    for phase in ("start", "end"):
        path = Path(folder) / "episode" / phase / "control/state.json"
        state = load(path)
        software = state["projects"][original.base.PROJECT]["software"]
        require(software.get("case") == case and software.get("initial_diagnostics") == {}
            and software.get("initial_diagnostic_assignments") == {member: [] for member in MEMBERS}
            and software.get("initial_public_feedback") is None,
            "HOLD_initial_diagnostic_absence_not_bound")
        references.append(original.reference(path))
    return {"version": "v051-heldout-explicit-no-initial-diagnostics", "states": references,
        "initial_test_executions_added": 0, "initial_diagnostics": {},
        "member_assignments": {member: [] for member in MEMBERS}}


def adapt_initial_absence(measured, proof):
    """Remove only the inherited requirement in this explicitly different initial contract."""
    old_gap = {"reason": "missing_authorized_initial_diagnostic_contract"}
    gaps = measured.get("measurement_gaps", [])
    require(gaps.count(old_gap) == 1 and proof.get("initial_diagnostics") == {}
        and proof.get("member_assignments") == {member: [] for member in MEMBERS},
        "HOLD_initial_contract_adaptation_not_uniquely_bound")
    result = copy.deepcopy(measured)
    result["measurement_gaps"] = [gap for gap in gaps if gap != old_gap]
    facts = result["mechanism_gate_inputs"]
    facts["resolved"] = (not result["measurement_gaps"] and not facts.get("unresolved_no_followup_ids")
        and not facts.get("page_protocol_unresolved") and result.get("episode_closed") is True)
    result["initial_contract_binding"] = {"original_inherited_gap": old_gap, "explicit_absence_proof": proof,
        "old_records_modified": False, "lifecycle_and_projection_algorithms_changed": False}
    return result


def namespace(provider, state_authorizations):
    values = dict(original.__dict__)
    values.update(VERSION=VERSION, PAGE_INTERFACE=INTERFACE_REVISION, RUNTIME_VERSION=RUNTIME_VERSION,
                  SCHEDULER=SCHEDULER, MEMBERS=list(MEMBERS), validate_episode_capacity=validate_episode_capacity)
    for name, function in original.__dict__.items():
        if isinstance(function, FunctionType) and function.__module__ == original.__name__:
            clone = FunctionType(function.__code__, values, function.__name__, function.__defaults__, function.__closure__)
            clone.__kwdefaults__ = function.__kwdefaults__
            values[name] = clone
    values["validate_episode_capacity"] = validate_episode_capacity
    values["episode_binding"] = lambda folder, *, result, budget: episode_binding(folder, result=result, budget=budget,
        provider=provider, state_authorizations=state_authorizations)
    inherited_feedback = values["_measure_feedback"]
    def feedback(folder, **kwargs):
        proof = absent_initial_diagnostics(folder, provider=provider)
        return adapt_initial_absence(inherited_feedback(folder, **kwargs), proof)
    values["_measure_feedback"] = feedback
    return values


def _signature(input_record, output_ids, usage, identity):
    return digest(json_bytes({"input": input_record, "outputs": output_ids, "usage": usage, "identity": identity}))


def native_accounting_binding(row, *, allow_cpu_fixture=False):
    mode = native_evidence_mode(row, allow_cpu_fixture=allow_cpu_fixture)
    if allow_cpu_fixture:
        return {**mode, "fee_scope": "Explicit programmed CPU fixture; not native model qualification"}
    folder = Path(row["episode_manifest"]).resolve().parent.parent
    calls = Path(row["native_provider_calls_path"])
    starts = {path.name.removesuffix("-started.json"): load(path) for path in calls.glob("*-started.json")}
    complete = {path.name.removesuffix("-complete.json"): load(path) for path in calls.glob("*-complete.json")}
    require(set(starts) == set(complete), "HOLD_native_inflight_or_missing_actual_response", missing=True)
    native_keys, response_keys, total = [], [], 0
    for key, result in complete.items():
        start = starts[key]
        prepared = load(calls / (key + "-prepared.json"))
        usage, inputs, outputs = result.get("usage", {}), result.get("input", {}), result.get("output_ids")
        require(isinstance(prepared, dict) and start.get("attempt_id") == result.get("attempt_id") == key
            and start.get("generation_started") is True
            and start.get("online_window_id") == row["online_window_id"]
            and start.get("actor_identity") == result.get("actor_identity") == row["actor_identity"]
            and start.get("native_input") == prepared.get("native_input") == inputs
            and result.get("path") == "project" and isinstance(outputs, list)
            and all(type(usage.get(k)) is int for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
            and usage["prompt_tokens"] == len(inputs.get("input_ids", []))
            and usage["completion_tokens"] == len(outputs)
            and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
            and 0 < usage["total_tokens"] <= start.get("reserved_maximum_tokens", 0),
            "HOLD_actual_native_usage_or_identity_unbound")
        native_keys.append(_signature(inputs, outputs, usage, row["actor_identity"]))
        total += usage["total_tokens"]
    for path in (folder / "raw-transport").glob("request-*/response.json"):
        body = load(path).get("body", {})
        response_keys.append(_signature(body.get("prompt_projection"), body.get("token_trace", {}).get("output_ids"),
            body.get("usage"), body.get("actor_identity")))
    require(Counter(native_keys) == Counter(response_keys)
        and row.get("usage", {}).get("attempts") == len(complete)
        and row.get("usage", {}).get("total_tokens") == total, "HOLD_sdk_to_unique_native_accounting_mismatch")
    return {**mode, "actual_native_generations": len(complete), "known_actual_tokens": total,
        "unique_native_call_ids": sorted(complete), "exact_response_multiset_bound": True,
        "prepared_without_generation": sorted(path.name.removesuffix("-prepared.json")
            for path in calls.glob("*-prepared.json") if path.name.removesuffix("-prepared.json") not in starts),
        "all_started_settled": True}


def fixed_endpoint_binding(row):
    folder = Path(row["episode_manifest"]).resolve().parent.parent
    lock = load(folder / "final-candidate-lock.json")
    raw = load(folder / "raw-independent-assessment.json")
    assessment = load(folder / "assessment.json")
    require(assessment == row.get("assessment") and isinstance(raw, dict) and isinstance(lock, dict),
            "HOLD_fixed_assessment_or_lock_missing", missing=True)
    require(row.get("mutable_terminal_working_tree_assessed") is False
        and not any(key in row for key in ("R_code", "terminal_code", "Q_task_terminal"))
        and row.get("F") == row.get("R") == row.get("R_joint") == assessment.get("R"),
        "HOLD_fixed_F_replaced_by_mutable_terminal_tree")
    submitted = raw.get("submitted") is True
    execution = raw.get("independent_acceptance", {}).get("execution", {})
    require(lock.get("delivery") == raw.get("delivery") and lock.get("absence_locked") is (not submitted)
        and row.get("submitted") is submitted
        and row.get("host_final_evaluation_attempts") == int(submitted)
        and row.get("host_final_test_executions") == int(execution.get("command_executed") is True),
        "HOLD_final_fixed_delivery_or_unique_evaluation_mismatch")
    if not submitted:
        require(raw.get("R") == 0 and row["F"] == 0 and raw.get("status") == "evaluable"
            and not raw.get("independent_acceptance") and row["host_final_test_executions"] == 0,
            "HOLD_no_submit_must_close_F0_without_test")
    else:
        require(raw.get("executed") is True and execution.get("executed") is True,
                "HOLD_submitted_fixed_test_execution_unknown", missing=True)
        require(execution.get("input_files_sha256") == raw.get("files_sha256")
            and raw.get("delivery", {}).get("files_sha256") == raw.get("files_sha256")
            and execution.get("source_unchanged") is True and execution.get("test_integrity") is True,
            "HOLD_fixed_tree_test_source_unbound")
    return {"status": "verified", "submitted": submitted, "F": row["F"],
        "raw_assessment": original.reference(folder / "raw-independent-assessment.json"),
        "final_lock": original.reference(folder / "final-candidate-lock.json"),
        "host_final_test_executions": row["host_final_test_executions"],
        "terminal_working_tree_assessed": False, "no_submit_F0_does_not_bypass_mechanical_gate": True}


def measure_slot(row, destination=None, *, provider, state_authorizations, allow_cpu_fixture=False):
    """New receipt only; host must never enable the explicit CPU fixture branch."""
    try:
        actor = state_binding(row, state_authorizations)
        native = native_accounting_binding(row, allow_cpu_fixture=allow_cpu_fixture)
        scope = namespace(provider, state_authorizations)
        report = scope["measure_slot"](row)
        fixed = fixed_endpoint_binding(row)
        report.update(state_binding=actor, native_accounting=native, fixed_endpoint_binding=fixed,
            adaptation={"original_module": original.reference(Path(original.__file__)),
                "private_constant_bindings": {"interface": INTERFACE_REVISION, "runtime": RUNTIME_VERSION,
                    "scheduler": SCHEDULER, "members": list(MEMBERS)},
                "unchanged_two_member_code_objects": ["assess_records", "lifecycle_history", "audit_projection",
                    "bind_context", "bind_shared_budget", "bind_member_fixed_budget"],
                "S1_AST_adaptation_used": False, "old_module_globals_modified": False},
            scope="Held-out fixed-submit F only; unchanged two-member Gamma1 feedback/refusal mechanics with explicit new source and readonly actor bindings")
    except (KeyError, TypeError, ValueError, OSError, AttributeError) as error:
        violation = isinstance(error, original.EvidenceProblem) and not error.missing
        decision = "global_pause" if violation else "measurement_pending"
        report = {"version": VERSION, "slot_id": row.get("slot_id"), "decision": decision,
            "read_only": True, "new_model_calls": 0, "new_tokenizer_calls": 0,
            "new_test_or_acceptance_executions": 0, "new_world_actions": 0,
            "stop_assessment": {"decision": decision, "unresolved": [] if violation else [str(error)],
                                "global_violations": [str(error)] if violation else []}}
    if destination is not None:
        path = Path(destination)
        if path.exists():
            raise FileExistsError("Preserve original HOLD measurements; use a new receipt path")
        atomic_write(path, json_bytes(report))
    return report
