"""Finite affected representation/host controls; no model or tokenizer."""
import copy
import json

import pytest

from proworksim.software_context_v048 import CANDIDATE_SHA256
from scripts import software_organization_stop_policy_v048 as policy
from tests.test_software_organization_stop_policy_v047 import fixture as old_fixture


def fixture(gamma="Gamma1", **kwargs):
    data = old_fixture(**kwargs)
    data["feedback"]["version"] = "organization-feedback-opportunities-v0.48"
    data["feedback"]["representation"] = {
        "representation": gamma, "candidate_sha256": CANDIDATE_SHA256}
    facts = data["feedback"]["mechanism_gate_inputs"]
    facts["requests_verified_under_v048"] = facts.pop("requests_verified_under_v044")
    data["representation_binding"] = {
        "version": "v048-representation-slot-binding-v1", "slot_id": "fixture",
        "representation": gamma, "candidate": {"sha256": CANDIDATE_SHA256},
        "transport_library": "software_context_v044" if gamma == "Gamma0" else "software_context_v048",
        "base_runtime_library": "software_organization_runtime_v047",
        "new_model_qualification_calls": 0, "world_or_prompt_instruction_changes": False}
    return data


@pytest.mark.parametrize("gamma", ["Gamma0", "Gamma1"])
@pytest.mark.parametrize(("censored", "R", "submitted"), [
    (False, 0, False), (False, 0, True), (False, 1, True),
    (True, 0, False), (True, 1, True)])
def test_known_safe_closure_is_independent_of_gamma_score_or_submission(gamma, censored, R, submitted):
    data = fixture(gamma, censored=censored, R=R, submitted=submitted)
    before = copy.deepcopy(data)
    result = policy.assess_records(**data)
    assert result["decision"] == "continue", result
    assert result["representation_binding"]["representation"] == gamma
    assert result["administrative_close"]["token_outcomes_censored"] is censored
    assert data == before


@pytest.mark.parametrize("mutation", [
    "gamma", "candidate", "slot", "transport", "runtime", "qualification",
    "world", "feedback", "verified_count", "old_feedback"])
def test_representation_or_input_binding_failure_pauses_independent_stock(mutation):
    data = fixture()
    binding = data["representation_binding"]
    if mutation == "gamma":
        binding["representation"] = "Gamma0"
    elif mutation == "candidate":
        binding["candidate"]["sha256"] = "0" * 64
    elif mutation == "slot":
        binding["slot_id"] = "another-slot"
    elif mutation == "transport":
        binding["transport_library"] = "software_context_v044"
    elif mutation == "runtime":
        binding["base_runtime_library"] = "software_organization_runtime_v046"
    elif mutation == "qualification":
        binding["new_model_qualification_calls"] = 1
    elif mutation == "world":
        binding["world_or_prompt_instruction_changes"] = True
    elif mutation == "feedback":
        data["feedback"]["representation"]["representation"] = "Gamma0"
    elif mutation == "verified_count":
        data["feedback"]["mechanism_gate_inputs"]["projection_violations"] = ["call-1"]
    else:
        data["feedback"]["version"] = "organization-feedback-opportunities-v0.47"
    assert policy.assess_records(**data)["decision"] == "global_pause"


def test_missing_representation_or_actual_input_proof_remains_pending():
    data = fixture()
    data["representation_binding"] = None
    assert policy.assess_records(**data)["decision"] == "measurement_pending"
    data = fixture()
    data["feedback"]["mechanism_gate_inputs"]["requests_verified_under_v048"] = 0
    assert policy.assess_records(**data)["decision"] == "measurement_pending"


def test_unchanged_host_guard_still_blocks_unknown_usage():
    data = fixture()
    data["row"]["usage"]["uncertain_usage_attempts"] = 1
    assert policy.assess_records(**data)["decision"] == "global_pause"


@pytest.mark.parametrize("valid_candidate", [False, True])
def test_changed_candidate_file_is_integrity_pause_not_pending(tmp_path, valid_candidate):
    data = fixture()
    folder = tmp_path / "actual" / "episodes" / "fixture"
    folder.mkdir(parents=True)
    candidate = tmp_path / "candidate.json"
    if valid_candidate:
        from pathlib import Path
        original = Path(__file__).resolve().parents[1] / "docs/experiments/software-organization-v048-candidate.json"
        candidate.write_bytes(original.read_bytes())
        # The original runner reference contains path and sha256, without size.
        data["representation_binding"]["candidate"].update(path=str(candidate))
    else:
        candidate.write_text("{}")
        data["representation_binding"]["candidate"].update(path=str(candidate), bytes=2)
    files = {"slot-result.json": data["row"], "feedback-loop.json": data["feedback"],
             "team-budget.json": data["team_budget"], "organization-evidence.json": data["evidence"],
             "evaluation-guard.json": data["guard"], "representation-binding.json": data["representation_binding"]}
    for name, value in files.items():
        (folder / name).write_text(json.dumps(value))
    (folder / "experience.jsonl").write_text("\n".join(map(json.dumps, data["events"])))
    (folder.parent.parent / "capacity-binding.json").write_text(json.dumps(data["capacity_binding"]))
    result = policy.assess_episode(folder)
    assert result["decision"] == ("continue" if valid_candidate else "global_pause"), result
    if not valid_candidate:
        assert "representation_candidate_file_changed" in result["global_violations"]


def test_stage_refusal_reaches_original_binding_rule_without_new_keyword():
    data = fixture()
    data["team_budget"]["model"]["records"]["call-1"]["budget_kind"] = "stage_budget"
    from tests.test_measure_organization_budget_v046 import seal
    seal(data["team_budget"]["model"], "state_sha256")
    result = policy.assess_records(**data)
    assert result["decision"] == "global_pause"
    assert {"call_id": "call-1", "unbound_stage_refusal":
            "stage_refusal_has_dispatch_charge_or_different_kind"} in result["global_violations"]
