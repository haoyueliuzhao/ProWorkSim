"""Synthetic CPU selector controls; these are not model/development-effect evidence."""

import copy
import math

import pytest

from proworksim.experience_allocation_v027 import (
    DEFAULT_CONSTRAINTS,
    bind_allocation,
    bind_candidate,
    candidate_materialization,
    development_receipt,
    freeze_allocation_plan,
    inspect_allocation_window,
    materialize_allocation,
    select_allocation,
    solve_first_order,
    supports_from_entries,
    validate_allocation,
)
from proworksim.online_support import declare_window
from test_online_support_v013 import actor, declaration, rollout


def fixture_window():
    specs = []
    for xi in ("api-contract", "integration-conflict"):
        source = declaration(active=("member-one", "member-two"), slots=10, xi=xi)
        for row in source["slots"]:
            row = {k: v for k, v in row.items() if k != "window"}
            row["slot_id"] = xi + "/" + row["slot_id"]
            specs.append(row)
    decl = declare_window(
        "synthetic-v027", actor_identity=actor(), gamma_identity={"explicit_CPU_fixture": True},
        slot_specs=specs, min_class_count=2,
    )
    entries, records = [], []
    for slot in decl["slots"]:
        sid, number = slot["slot_id"], int(slot["slot_id"].split("/")[-1])
        record = rollout(decl, sid, valid=number < 8, tokens=number != 9)
        category = ["negotiate", "negotiate", "negotiate", "negotiate", "prototype", "prototype",
                    "integrate", "integrate", None, None][number]
        mapping = {"rollout_id": record["rollout_id"], "spec_id": slot["mapping_spec_id"],
                   "status": "mapped" if category else "unmapped", "class_id": category}
        entries.append({"slot_id": sid, "active_members": slot["active_members"],
                        "rollout": record, "reward": record["reward_eligibility"], "mapping": mapping})
        records.append({"slot_id": sid, "status": "closed", "rollout": record, "mapping": mapping})
    supports, bindings = supports_from_entries(entries, decl, records)
    return entries, decl, records, supports, bindings


def manifest():
    return {
        "purpose": "contribution_development", "dataset_id": "synthetic-developer",
        "split_manifest_sha256": "a" * 64, "initial_state_sha256": "b" * 64,
        "training_rng_sha256": "c" * 64, "provenance": "synthetic_cpu_control",
        "units": [{"unit_id": "dev-" + str(i), "seed": 101 + i, "weight": i + 1}
                  for i in range(3)],
        "independent_unit_ids": ["independent-confirmation-0"],
    }


def plan_for(supports, eligible=None, **kwargs):
    return freeze_allocation_plan(
        supports, eligible_blocks=eligible if eligible is not None else
        [[xi, member] for xi, support in supports.items() for member in support["blocks"]],
        development=kwargs.pop("development", manifest()),
        budget=kwargs.pop("budget", {"max_trial_updates_per_method": 100,
                                     "max_development_evaluations_per_method": 300,
                                     "formal_updates_per_method": 1}), **kwargs,
    )


def coefficient(sid, member):
    i = int(sid.split("/")[-1])
    return [2.0, -2.0, 1.0, -1.0, 0.4, 0.6, -0.5, -0.5][i] * (1 if member == "member-one" else -1)


def linear_receipts(plan):
    receipts = []
    for cid in plan["candidates"]:
        mat = candidate_materialization(plan, cid)
        utility = 0.0
        for xi, member in plan["eligible_blocks"]:
            block = plan["supports_by_xi"][xi]["blocks"][member]
            utility += sum(mat[xi]["members"][member]["weights"][sid] * coefficient(sid, member)
                           / block["n_positive"] for sid in block["eligible_slots"])
        receipts.append(development_receipt(
            plan, cid, [utility + i / 10 for i in range(3)], provenance="synthetic_cpu_control"
        ))
    return receipts


def test_multiple_situations_stable_members_three_classes_and_full_G_basis():
    _, _, _, supports, _ = fixture_window()
    plan = plan_for(supports)
    assert plan["methods"]["G"]["required_trial_updates"] == 57  # 4 * (8 - 1) paired directions
    assert plan["methods"]["I"]["required_trial_updates"] == 17  # 4 * (3 - 1), not first class only
    assert plan["methods"]["G"]["required_development_evaluations"] == 171
    result = select_allocation(plan, linear_receipts(plan))
    assert not result["effectiveness_evidence"]
    assert result["provenance"] == "synthetic_cpu_control"
    for method in ("G", "I"):
        assert not result["selections"][method]["Q_equals_B"]
        materialized = materialize_allocation(plan, result, method)
        for xi, support in supports.items():
            for member, block in support["blocks"].items():
                row = materialized[xi]["members"][member]
                assert row["total_slot_weight"] == pytest.approx(10)
                assert row["eligible_branch_weight"] == pytest.approx(8)
                assert row["weights"][xi + "/8"] == row["weights"][xi + "/9"] == 1
                assert row["actor_mask"][xi + "/8"] is True  # Trusted failure remains base RL.
                assert row["actor_mask"][xi + "/9"] is False  # No invented token target.
                assert all(0.5 <= w <= 2 for w in row["weights"].values())
                if method == "I":
                    assert len({row["weights"][sid] for sid, z in block["eligible_slots"].items()
                                if z == "negotiate"}) == 1
                else:
                    difference = row["weights"][xi + "/0"] - row["weights"][xi + "/1"]
                    assert difference * (1 if member == "member-one" else -1) > 0
        # Exact finite differences recover a linear test oracle, including every raw G coordinate.
        for solved in result["selections"][method]["solutions"]:
            member, xi = solved["member_id"], solved["xi_id"]
            if method == "G":
                expected = {sid: coefficient(sid, member) for sid in solved["contribution"]}
            else:
                block = supports[xi]["blocks"][member]
                expected = {z: sum(coefficient(sid, member) for sid, category
                                   in block["eligible_slots"].items() if category == z) / count
                            for z, count in block["n_by_class"].items()}
            mean = sum(expected.values()) / len(expected)
            assert solved["contribution"] == pytest.approx({k: v - mean for k, v in expected.items()})


def test_common_coverage_target_nonzero_N_and_anchors_are_not_value_or_uncertainty():
    _, _, _, supports, _ = fixture_window()
    plan = plan_for(supports, eligible=[["api-contract", "member-one"]])
    receipts = [development_receipt(plan, cid, [0.0, 0.0, 0.0], provenance="synthetic_cpu_control")
                for cid in plan["candidates"]]
    selected = select_allocation(plan, receipts)
    i = selected["selections"]["I"]["solutions"][0]
    g = selected["selections"]["G"]["solutions"][0]
    assert i["contribution"] == dict.fromkeys(i["contribution"], 0)
    assert i["N"] == {"integrate": 0.25, "negotiate": 0, "prototype": 0.25}
    assert i["constraints"]["beta"] == 0.25
    assert i["q"]["negotiate"] < i["baseline_anchor"]["negotiate"]
    for sid, category in supports["api-contract"]["blocks"]["member-one"]["eligible_slots"].items():
        count = supports["api-contract"]["blocks"]["member-one"]["n_by_class"][category]
        assert g["coverage_anchor"][sid] == pytest.approx(i["coverage_anchor"][category] / count)
        assert g["N"][sid] == i["N"][category]
    for method in ("G", "I"):
        mat = materialize_allocation(plan, selected, method)
        assert all(w == 1 for w in mat["api-contract"]["members"]["member-two"]["weights"].values())
        assert all(w == 1 for row in mat["integration-conflict"]["members"].values()
                   for w in row["weights"].values())


def test_unknown_is_not_zero_and_does_not_allow_coverage_only_configuration():
    _, _, _, supports, _ = fixture_window()
    plan = plan_for(supports)
    receipts = linear_receipts(plan)
    receipts[0]["outcomes"][1]["utility"] = None  # Common B unknown invalidates both paired estimates.
    result = select_allocation(plan, receipts)
    for method in ("G", "I"):
        assert result["selections"][method]["Q_equals_B"]
        assert result["selections"][method]["reason"] == "development_unknown_keep_B"
        assert result["selections"][method]["solutions"] == []
    empty = plan_for(supports, eligible=[])
    assert select_allocation(empty, [])["selections"]["I"]["reason"] == "no_configurable_support_keep_B"
    assert empty["status"] == "no_configurable_support"
    assert empty["methods"]["G"]["required_trial_updates"] == 0
    entries, decl, records, _, _ = fixture_window()
    with pytest.raises(ValueError, match="ends without an update"):
        bind_candidate(entries, decl, records, empty, "B")


@pytest.mark.parametrize("changed", ["purpose", "independent-unit", "seed", "initial-state", "provenance", "extra-test"])
def test_test_or_unpaired_feedback_cannot_select_weights(changed):
    _, _, _, supports, _ = fixture_window()
    plan = plan_for(supports, eligible=[["api-contract", "member-one"]])
    receipts = linear_receipts(plan)
    if changed == "purpose":
        receipts[0]["purpose"] = "independent_test"
    elif changed == "independent-unit":
        receipts[0]["outcomes"][0]["unit_id"] = "independent-confirmation-0"
    elif changed == "seed":
        receipts[0]["outcomes"][0]["seed"] += 1
    elif changed == "initial-state":
        receipts[0]["initial_state_sha256"] = "d" * 64
    elif changed == "provenance":
        receipts[0]["provenance"] = "current_model_development"
    else:
        receipts[0]["test_score"] = 1.0
    with pytest.raises(ValueError, match="common development"):
        select_allocation(plan, receipts)
    dev = manifest()
    dev["independent_unit_ids"].append("dev-0")
    with pytest.raises(ValueError, match="Independent confirmation"):
        plan_for(supports, development=dev)


def test_budget_cannot_silently_truncate_G_and_support_cannot_pool_windows():
    _, _, _, supports, _ = fixture_window()
    with pytest.raises(ValueError, match="G needs 57"):
        plan_for(supports, budget={"max_trial_updates_per_method": 17,
                                  "max_development_evaluations_per_method": 300,
                                  "formal_updates_per_method": 1})
    altered = copy.deepcopy(supports)
    altered["integration-conflict"]["window"]["window_id"] = "old-policy"
    with pytest.raises(ValueError, match="Do not pool"):
        plan_for(altered)
    altered = copy.deepcopy(supports)
    altered["api-contract"]["blocks"]["member-one"]["n_by_class"]["negotiate"] += 1
    with pytest.raises(ValueError, match="Support counts"):
        plan_for(altered)


def test_incomplete_window_retains_unknown_inventory_and_does_not_estimate_b_or_v():
    entries, decl, records, supports, _ = fixture_window()
    complete = inspect_allocation_window(decl, records)
    assert complete["status"] == "ready"
    assert complete["supports_by_xi"] == supports
    incomplete = records[:-2] + [{"slot_id": records[-2]["slot_id"], "status": "interrupted"}]
    result = inspect_allocation_window(decl, incomplete)
    assert result["status"] == "incomplete_keep_original_inventory"
    assert result["supports_by_xi"] is None
    assert len(result["raw_slot_inventory"]) == len(entries) == 20
    assert [row["status"] for row in result["raw_slot_inventory"]][-2:] == ["interrupted", "not_started"]
    group = result["diagnostic"]["groups"][-1]
    assert group["planned"] == 10 and group["support"] is None
    assert group["empirical_distribution_status"] == "incomplete_no_b_or_v_estimate"


def test_general_solver_against_feasible_three_class_grid_and_positive_anchors():
    b = {"a": 0.5, "b": 0.3, "c": 0.2}
    c = {"a": -2.0, "b": 0.4, "c": 3.0}
    r = dict.fromkeys(b, 1 / 3)
    n = {k: max(0.0, 1 - 3 * value) for k, value in b.items()}
    solved = solve_first_order(b, c, r, n)
    limits = DEFAULT_CONSTRAINTS
    assert solved["tv"] <= limits["tv_limit"] + 1e-12
    assert sum(solved["q"].values()) == pytest.approx(1)
    for i in range(1, 100):
        for j in range(1, 100 - i):
            q = {"a": i / 100, "b": j / 100, "c": (100 - i - j) / 100}
            if any(not 0.5 <= q[k] / b[k] <= 2 for k in b):
                continue
            if sum(abs(q[k] - b[k]) for k in b) / 2 > limits["tv_limit"]:
                continue
            objective = sum(q[k] * (c[k] + limits["beta"] * n[k])
                            - limits["lambda_b"] * q[k] * math.log(q[k] / b[k])
                            - limits["lambda_coverage"] * q[k] * math.log(q[k] / r[k]) for k in b)
            assert objective <= solved["objective"] + 1e-10
    with pytest.raises(ValueError, match="positive B/coverage"):
        solve_first_order(b, c, r, n, constraints={**limits, "lambda_coverage": 0})


def test_bound_actor_rows_reject_forged_weights_tokens_and_denominators():
    entries, decl, records, supports, bindings = fixture_window()
    plan = plan_for(supports, eligible=[["integration-conflict", "member-two"]])
    selection = select_allocation(plan, linear_receipts(plan))
    allocation = bind_allocation(entries, decl, records, plan, selection, method="G")
    decisions = []
    for entry in entries:
        sid = entry["slot_id"]
        for member, view in bindings[sid]["member_views"].items():
            if not view["complete_actor_trajectory"]:
                continue
            for own in view["decisions"]:
                if own["actor_required"]:
                    decisions.append({
                        "slot_id": sid, "member_id": member, "call_id": own["call_id"],
                        "tokens": copy.deepcopy(own["tokens"]),
                        "actual_response_sha256": own["response_sha256"],
                        "actor_denominator": len(entries) * 2 * view["own_action_tokens"],
                        "critic_denominator": len(entries) * 2
                        * sum(d["actor_required"] for d in view["decisions"]),
                    })
    prepared = {"window_id": decl["window_id"], "actor_identity": decl["actor_identity"],
                "decisions": decisions}
    weights, report = validate_allocation(entries, prepared, allocation)
    assert len(weights) == 36
    assert report["original_normalization_preserved"] and not report["Q_equals_B"]
    assert report["changed_blocks"] == [{"xi_id": "integration-conflict", "member_id": "member-two"}]
    # Trial composition is available before developer feedback, without a circular dependency.
    for candidate_id in ("B", plan["methods"]["G"]["directions"][0]["plus_id"],
                         plan["methods"]["I"]["directions"][0]["minus_id"]):
        trial = bind_candidate(entries, decl, records, plan, candidate_id)
        trial_weights, trial_report = validate_allocation(entries, prepared, trial)
        assert len(trial_weights) == len(weights)
        assert trial_report["Q_equals_B"] is (candidate_id == "B")
    for field in ("tokens", "actor_denominator", "critic_denominator"):
        bad = copy.deepcopy(prepared)
        if field == "tokens":
            bad["decisions"][0][field]["output_ids"][0] += 1
        else:
            bad["decisions"][0][field] += 1
        with pytest.raises(ValueError, match="Own tokens"):
            validate_allocation(entries, bad, allocation)
    forged = copy.deepcopy(allocation)
    forged["materialized_by_xi"]["integration-conflict"]["members"]["member-two"]["weights"][
        "integration-conflict/0"] = 1.999
    with pytest.raises(ValueError, match="original entries"):
        validate_allocation(entries, prepared, forged)
    forged = copy.deepcopy(selection)
    forged["selections"]["G"]["q_by_xi"]["integration-conflict"]["member-two"][
        "integration-conflict/0"] = 1
    with pytest.raises(ValueError, match="frozen rule"):
        materialize_allocation(plan, forged, "G")
