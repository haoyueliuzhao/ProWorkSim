"""New binding controls only; synthetic outcomes never establish model benefit."""
import copy
import math

import pytest

from proworksim import experience_allocation_v035 as allocation
from proworksim.member_views import member_view
from proworksim.online_training import validate_actor_composition
from test_online_support_v013 import declaration, rollout


def material(categories=None):
    categories = categories or ["self"] * 4 + ["partner"] * 2 + ["rare"] + [None] * 9
    decl = declaration(active=allocation.MEMBERS, slots=16, xi="one-root:first=A")
    entries, records = [], []
    for index, slot in enumerate(decl["slots"]):
        value = rollout(decl, slot["slot_id"], valid=index < 7)
        category = categories[index]
        mapping = {"rollout_id": value["rollout_id"], "spec_id": slot["mapping_spec_id"],
                   "status": "mapped" if category else "unmapped", "class_id": category}
        entries.append({"slot_id": slot["slot_id"], "rollout": value, "mapping": mapping,
                        "reward": value["reward_eligibility"], "active_members": list(allocation.MEMBERS)})
        records.append({"slot_id": slot["slot_id"], "status": "closed", "rollout": value, "mapping": mapping})
    return entries, decl, records


def panel():
    return {"purpose": "contribution_development", "split_manifest_sha256": "a" * 64,
            "initial_state_sha256": "b" * 64, "training_rng_sha256": "c" * 64,
            "provenance": "synthetic_cpu_control",
            **{name: [{"unit_id": prefix + str(index), "root_id": prefix + str(index // 2),
                       "seed": 100 + index, "weight": 1.0} for index in range(4)]
               for name, prefix in (("units", "dev-"), ("independent_units", "confirm-"))}}


def plan_for(entries, decl, records, **changes):
    gate = allocation.allocation_gate(entries, decl, records)
    return allocation.freeze_allocation_plan(gate["supports_by_xi"], eligible_blocks=gate["eligible_blocks"],
        development=changes.get("development", panel()),
        budget=changes.get("budget", {"max_unique_trial_updates": 33, "max_development_episodes": 132,
            "formal_updates_per_method": 1, "independent_episodes_per_method": 4}))


def receipts(plan, zero=False):
    xi, member = plan["eligible_blocks"][0]
    slope = {str(index): [2, -2, 1, -1, 0.3, 0.7][index] for index in range(6)}
    result = []
    for cid in plan["candidates"]:
        weights = allocation.candidate_materialization(plan, cid)[xi]["members"][member]["weights"]
        utility = 0.0 if zero else sum(weights[key] * value / 6 for key, value in slope.items())
        result.append(allocation.development_receipt(plan, cid, [utility] * 4, provenance="synthetic_cpu_control"))
    return result


def prepared_for(entries, decl):
    decisions = []
    for entry in entries:
        for member in entry["active_members"]:
            view = member_view(entry["rollout"], member)
            for decision in view["decisions"]:
                if decision["actor_required"]:
                    decisions.append({"slot_id": entry["slot_id"], "member_id": member,
                        "call_id": decision["call_id"], "tokens": decision["tokens"],
                        "actual_response_sha256": decision["response_sha256"],
                        "actor_denominator": 16 * 2 * view["own_action_tokens"],
                        "critic_denominator": 16 * 2 * sum(d["actor_required"] for d in view["decisions"])})
    return {"window_id": decl["window_id"], "actor_identity": decl["actor_identity"], "decisions": decisions}


def test_support_taxonomy_keeps_all_raw_slots_and_first_member_only():
    entries, decl, records = material()
    gate = allocation.allocation_gate(entries, decl, records)
    xi = decl["slots"][0]["xi_id"]
    assert gate["status"] == "ready_for_postcollection_freeze"
    assert gate["eligible_blocks"] == [[xi, "member_a"]]
    block = gate["supports_by_xi"][xi]["blocks"]["member_a"]
    assert block["M"] == 16 and block["n_positive"] == 6 and block["v"] == 6 / 16
    assert block["candidate_counts_before_support"] == {"self": 4, "partner": 2, "rare": 1}
    assert not gate["gradient_or_update_identifiability_checked"]
    assert allocation.allocation_gate(*material(["self"] * 7 + [None] * 9))["member_support_states"]["member_a"] == "single_supported_class"
    assert allocation.allocation_gate(*material(["self"] * 6 + ["partner"] + [None] * 9))["member_support_states"]["member_a"] == "multiple_classes_below_frequency"
    assert allocation.allocation_gate(*material([None] * 16))["member_support_states"]["member_a"] == "no_mapped_valid_support"
    unknown = copy.deepcopy(records)
    unknown[0] = {"slot_id": "0", "status": "closed_unassessed"}
    assert allocation.allocation_gate(entries, decl, unknown)["status"] == "incomplete_keep_original_inventory"


def test_full_raw_directions_single_shared_B_and_original_residual_denominator():
    entries, decl, records = material()
    plan = plan_for(entries, decl, records)
    assert plan["actual_inventory"]["unique_trial_updates"] == 13  # 1 + 2*(6-1) + 2*(2-1)
    assert plan["actual_inventory"]["development_episodes"] == 52
    assert len(plan["methods"]["G-raw"]["directions"]) == 5
    assert len(plan["methods"]["I-P"]["directions"]) == 1
    xi = decl["slots"][0]["xi_id"]
    for cid in plan["candidates"]:
        mat = allocation.candidate_materialization(plan, cid)[xi]["members"]
        assert sum(mat["member_a"]["weights"].values()) == pytest.approx(16)
        assert all(mat["member_a"]["weights"][str(i)] == 1 for i in range(6, 16))
        assert all(w == 1 for w in mat["member_b"]["weights"].values())
        assert all(mat["member_a"]["actor_mask"].values())  # Trusted failures stay in base RL.
    with pytest.raises(ValueError, match="do not drop"):
        plan_for(entries, decl, records, budget={"max_unique_trial_updates": 12,
            "max_development_episodes": 132, "formal_updates_per_method": 1,
            "independent_episodes_per_method": 4})
    with pytest.raises(ValueError, match="member ordering"):
        allocation.freeze_allocation_plan(plan["supports_by_xi"], eligible_blocks=[[xi, "member_b"]],
            development=panel(), budget=plan["budget"])


def test_centered_C_uses_latest_solvers_and_Graw_never_gets_semantic_coverage():
    entries, decl, records = material()
    plan = plan_for(entries, decl, records)
    selected = allocation.select_allocation(plan, receipts(plan))
    for method in allocation.METHODS[1:]:
        solution = selected["selections"][method]["solutions"][0]
        assert math.fsum(solution["base"][key] * value for key, value in solution["contribution"].items()) == pytest.approx(0, abs=1e-12)
        assert solution["history_anchor"]["distribution"] == solution["base"]
        assert solution["rule"]["novelty"] == "max(log(coverage/history), 0)"
    raw = selected["selections"]["G-raw"]["solutions"][0]
    assert not raw["semantic_class_input_used"]
    assert all(value == 0 for value in raw["N"].values())
    assert raw["weights"]["0"] > raw["weights"]["1"]
    structured = selected["selections"]["I-P"]["solutions"][0]
    assert structured["N"] == pytest.approx({"self": 0, "partner": math.log(1.5)})
    assert structured["class_shared_weights"]


def test_zero_panel_differences_are_not_true_zero_C_and_unknowns_block_selection():
    entries, decl, records = material()
    plan = plan_for(entries, decl, records)
    observed = receipts(plan, zero=True)
    selected = allocation.select_allocation(plan, observed)
    assert selected["selections"]["G-raw"]["Q_equals_B_within_1e12"]
    assert not selected["selections"]["I-P"]["Q_equals_B"]
    for method in allocation.METHODS[1:]:
        assert selected["selections"][method]["all_observed_direction_differences_zero"]
        assert not selected["selections"][method]["true_contribution_proved_zero"]
    observed[0]["outcomes"][0]["utility"] = None
    with pytest.raises(ValueError, match="unknown development"):
        allocation.select_allocation(plan, observed)
    with pytest.raises(ValueError, match="unknown development"):
        allocation.select_allocation(plan, receipts(plan)[:-1])
    bad = panel()
    bad["independent_units"][0]["root_id"] = "dev-0"
    with pytest.raises(ValueError, match="Independent root"):
        plan_for(entries, decl, records, development=bad)


def test_new_dispatch_validates_own_trace_and_original_denominators_for_trial_and_formal():
    entries, decl, records = material()
    plan = plan_for(entries, decl, records)
    prepared = prepared_for(entries, decl)
    selected = allocation.select_allocation(plan, receipts(plan))
    for composition in (
        allocation.bind_candidate(entries, decl, records, plan, next(k for k in plan["candidates"] if k.startswith("G-raw"))),
        allocation.bind_allocation(entries, decl, records, plan, selected, method="I-P"),
    ):
        weights, proof = validate_actor_composition(entries, prepared, composition)
        assert len(weights) == 32 and proof["original_normalization_preserved"]
        assert {row["actor_denominator"] for row in proof["rows"]} == {32}
        corrupt = copy.deepcopy(prepared)
        corrupt["decisions"][0]["actor_denominator"] = 12
        with pytest.raises(ValueError, match="baseline denominators"):
            validate_actor_composition(entries, corrupt, composition)
        corrupt = copy.deepcopy(prepared)
        corrupt["decisions"][0]["tokens"]["input_ids"] = [999]
        with pytest.raises(ValueError, match="original tokens"):
            validate_actor_composition(entries, corrupt, composition)
