"""Bounded synthetic receipt controls for the sole C18432 candidate."""
import copy

import pytest

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_budget_v045 as old
from scripts import measure_organization_budget_v046 as proof
from scripts import measure_organization_feedback_v046 as feedback
from tests.test_measure_organization_budget_v045 import fixture as old_fixture, mutate, seal


def capacity_binding():
    recipe = {"max_length": 16384, "max_output_tokens": 2048, "temperature": 0.7,
              "members": ["member_a", "member_b", "software_inactive"]}
    profile = {"max_context_tokens": 16384, "dtype": "bfloat16", "attention_backend": "frozen"}
    new_recipe, new_profile = {**recipe, "max_length": 18432}, {**profile, "max_context_tokens": 18432}
    identity = {"adapter_sha256": "fixture-frozen-actor", "inference_profile_sha256": digest(json_bytes(profile))}
    return {"version": "software-capacity-binding-v0.46", "passed": True,
        "original_context_limit": 16384, "context_limit": 18432, "reserved_output_tokens": 2048,
        "original_recipe": recipe, "capacity_recipe": new_recipe,
        "original_recipe_sha256": digest(json_bytes(recipe)), "capacity_recipe_sha256": digest(json_bytes(new_recipe)),
        "original_inference_profile": profile, "capacity_inference_profile": new_profile,
        "original_profile_sha256": digest(json_bytes(profile)), "capacity_profile_sha256": digest(json_bytes(new_profile)),
        "original_actor_identity": identity,
        "capacity_actor_identity": {**identity, "inference_profile_sha256": digest(json_bytes(new_profile))},
        "before_state_sha256": "1" * 64, "after_state_sha256": "2" * 64,
        "protected_components_unchanged": dict.fromkeys(proof.PROTECTED_COMPONENTS, True),
        "new_parameter_updates": 0, "new_backward_calls": 0}


def fixture():
    data, baseline = old_fixture()
    cap = capacity_binding()
    actor = cap["capacity_actor_identity"]
    binding = {"actor_identity": actor, "recipe_sha256": cap["capacity_recipe_sha256"],
               "window_id": "organization-v045:fixture"}
    data["result"]["actor_identity"] = actor
    data["budget"]["binding"] = copy.deepcopy(binding)
    data["events"][2]["payload"]["team_budget"]["binding"] = copy.deepcopy(binding)
    for i in (3, 4):
        prep = data["events"][i]["payload"]["reservation"]["preparation"]
        prep.update(binding, context_limit=18432)
        seal(prep, "preparation_sha256")
    start = data["events"][3]["payload"]
    start["weight_identity"] = actor
    start["config"]["max_context_tokens"] = 18432
    seal(data["budget"], "state_sha256")
    seal(data["events"][2]["payload"]["team_budget"], "state_sha256")
    data["capacity_binding"] = cap
    return data, baseline


def test_C18432_fixed_budget_preserves_feedback_and_exact_old_pipeline_order():
    data, baseline = fixture()
    before = copy.deepcopy((data, baseline))
    result = feedback.revise_records(baseline, **data)
    row = result["feedback_records"][0]
    assert row["no_actual_followup"]["reason"] == "member_fixed_budget"
    assert row["presentation"] == baseline["feedback_records"][0]["presentation"]
    assert result["denominators"]["all_saved_feedback_units"] == 1
    p = row["member_fixed_budget_attribution"]
    assert p["hard_context_headroom_tokens"] == 3106 and p["member_available_tokens"] == 1438
    assert p["recorded_first_refusal"] == "member_fixed_budget_before_shared_reserve"
    assert (data, baseline) == before
    old_data = {k: v for k, v in data.items() if k != "capacity_binding"}
    with pytest.raises(ValueError):
        old.bind_member_fixed_budget("new", **old_data)


@pytest.mark.parametrize("mutation", ["equal_cap", "missing_prep", "mismatch_prep", "wrong_member", "wrong_opportunity",
    "wrong_input", "output", "charge", "world_effect", "later_generation", "context", "shared", "service"])
def test_original_fixed_budget_counterexamples_remain_pending_at_new_C(mutation):
    data, baseline = fixture()
    mutate(data, mutation)
    with pytest.raises(ValueError):
        proof.bind_member_fixed_budget("new", **data)
    assert feedback.revise_records(baseline, **data)["mechanism_gate_inputs"]["resolved"] is False


@pytest.mark.parametrize("change", ["old_context", "second_candidate", "changed_output", "changed_recipe_field",
    "changed_profile_field", "wrong_hash", "wrong_identity", "missing_protected", "changed_tensor", "backward"])
def test_only_exact_capacity_metadata_transition_is_accepted(change):
    value = capacity_binding()
    if change == "old_context":
        value["context_limit"] = 16384
    elif change == "second_candidate":
        value["context_limit"] = 32768
    elif change == "changed_output":
        value["reserved_output_tokens"] = 4096
    elif change == "changed_recipe_field":
        value["capacity_recipe"]["temperature"] = 0.6
        value["capacity_recipe_sha256"] = digest(json_bytes(value["capacity_recipe"]))
    elif change == "changed_profile_field":
        value["capacity_inference_profile"]["attention_backend"] = "another"
        value["capacity_profile_sha256"] = digest(json_bytes(value["capacity_inference_profile"]))
    elif change == "wrong_hash":
        value["capacity_recipe_sha256"] = "0" * 64
    elif change == "wrong_identity":
        value["capacity_actor_identity"]["adapter_sha256"] = "new-weights"
    elif change == "missing_protected":
        value["protected_components_unchanged"].pop("rng_cpu")
    elif change == "changed_tensor":
        value["protected_components_unchanged"]["actor"] = False
    else:
        value["new_backward_calls"] = 1
    with pytest.raises(ValueError):
        proof.validate_capacity_binding(value)


@pytest.mark.parametrize("context", [16384, 32768])
def test_same_recipe_hash_does_not_allow_another_preparation_capacity(context):
    data, _ = fixture()
    for i in (3, 4):
        prep = data["events"][i]["payload"]["reservation"]["preparation"]
        prep["context_limit"] = context
        seal(prep, "preparation_sha256")
    with pytest.raises(ValueError):
        proof.bind_member_fixed_budget("new", **data)


@pytest.mark.parametrize(("prompt", "fits"), [(16384, True), (17000, False)])
def test_exact_context_equality_and_concurrent_overflow_keep_recorded_member_first_cause(prompt, fits):
    data, _ = fixture()
    for i in (3, 4):
        reservation = data["events"][i]["payload"]["reservation"]
        reservation.update(input_token_reservation=prompt, token_reservation=prompt + 2048)
        reservation["preparation"].update(prompt_tokens=prompt, fits=fits)
        seal(reservation["preparation"], "preparation_sha256")
    result = proof.bind_member_fixed_budget("new", **data)
    assert result["hard_context_headroom_tokens"] == 18432 - prompt - 2048
    assert result["concurrent_hard_context_overflow"] is (not fits)
    assert result["reason"] == "member_fixed_budget"
