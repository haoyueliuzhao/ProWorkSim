"""Finite-control tests for the actual v036 execution gates, with no target model."""
import copy

import pytest

from proworksim.experience_allocation_v035 import development_receipt
from scripts import software_allocation_v036 as runner
from scripts import software_support_v036 as support
from scripts.run_ne_v021 import write
from test_experience_allocation_v035 import material, plan_for


def allocation():
    panel = {"purpose": "contribution_development", "split_manifest_sha256": "a" * 64,
        "initial_state_sha256": "b" * 64, "training_rng_sha256": "c" * 64,
        "provenance": "current_model_development"}
    for key, prefix in (("units", "dev"), ("independent_units", "confirm")):
        panel[key] = [{"unit_id": f"{prefix}-{root}-{seed}", "root_id": f"{prefix}-{root}",
                       "seed": seed, "weight": 1.0} for seed in range(4) for root in range(4)]
    return plan_for(*material(), development=panel, budget={"max_unique_trial_updates": 33,
        "max_development_episodes": 528, "formal_updates_per_method": 1, "independent_episodes_per_method": 16})


def test_full_update_gate_requires_actual_original_material_and_both_optimizers():
    material = {"admitted_decisions": 701, "admitted_own_output_tokens": 161626}
    report = {"status": "updated", "behavior_probability_passed": True,
        "actor_optimizer_steps": 1, "critic_optimizer_steps": 1,
        "backward_decisions_completed": 701, "admitted_decisions": 701,
        "admitted_output_tokens": 161626, "scheduled_slots": 16, "changed_actor_elements": 9}
    runner.require_actual_update(report, material)
    for mutation in ({"backward_decisions_completed": 700}, {"admitted_output_tokens": 161625},
                     {"actor_optimizer_steps": 0}, {"critic_optimizer_steps": 0},
                     {"changed_actor_elements": 0}, {"behavior_probability_passed": False},
                     {"status": "zero_step_zero_actor_advantage_or_gradient"}, {"scheduled_slots": 15}):
        with pytest.raises(ValueError, match="No complete real"):
            runner.require_actual_update({**report, **mutation}, material)


def test_panel_keeps_all_paired_roots_seeds_and_unknown_without_training_admission():
    inventory = support.inventories()["development"]
    rows = [{**r, "training_eligible": False, "status": "closed", "record_validity": True, "R": index % 2}
            for index, r in enumerate(inventory)]
    assert runner.validate_panel(rows, inventory)
    unknown = copy.deepcopy(rows)
    unknown[-1]["R"] = None
    assert not runner.validate_panel(unknown, inventory)
    for mutated in (rows[:-1], list(reversed(rows)), [{**r, "training_eligible": True} for r in rows]):
        with pytest.raises(ValueError, match="every exact"):
            runner.validate_panel(mutated, inventory)


def test_shared_B_then_all_directions_and_only_complete_known_feedback_allows_formal(tmp_path, monkeypatch):
    plan = allocation()
    freeze = {"allocation": plan}
    assert plan["actual_inventory"] == {"n_positive": 6, "K": 2, "shared_B_copies": 1,
                                        "unique_trial_updates": 13, "development_episodes": 208,
                                        "formal_updates": 3, "independent_episodes": 48}
    reviews = []
    monkeypatch.setattr(runner, "shared_B_cost_review", lambda root, value: reviews.append((root, value)))
    stage, names = runner.next_stage("shared_B", {"trial-B": {"status": "complete"}}, tmp_path, freeze)
    assert stage == "full_trials" and names == ["trial-" + key for key in plan["candidates"] if key != "B"]
    assert len(names) == 12 and len(reviews) == 1
    receipts = {"trial-" + key: development_receipt(plan, key, [0] * 16, provenance="current_model_development")
                for key in plan["candidates"]}
    monkeypatch.setattr(runner, "verified_receipt", lambda root, name, frozen: receipts[name])
    states = {name: {"status": "complete"} for name in names}
    first = names[0]
    receipts[first]["outcomes"][0]["utility"] = None
    with pytest.raises(ValueError, match="Incomplete or unknown"):
        runner.next_stage(stage, states, tmp_path, freeze)
    assert not (tmp_path / "selection.json").exists()
    receipts[first]["outcomes"][0]["utility"] = 0
    assert runner.next_stage(stage, states, tmp_path, freeze) == (
        "formal_and_independent_confirmation", ["formal-B", "formal-G-raw", "formal-I-P"])
    assert runner.next_stage(stage, {first: {"status": "stopped"}}, tmp_path, freeze) == ("incomplete_execution", [])
    with pytest.raises(ValueError, match="must close"):
        runner.next_stage(stage, {first: {"status": "archiving"}}, tmp_path, freeze)


def test_same_full_common_restore_and_material_checks_are_required_in_receipt(tmp_path):
    plan = allocation()
    candidate = "B"
    source = {"code_commit": "synthetic-control", "code_dirty": False}
    inventory = [{"slot_id": r["unit_id"], "case_id": r["root_id"], "sampling_seed": r["seed"]}
                 for r in plan["development"]["units"]]
    write(tmp_path / "plan.json", {"source": source, "inventories": {"development": inventory}})
    folder = tmp_path / "trial-B/actual"
    rows = [{**r, "status": "closed", "record_validity": True, "training_eligible": False, "R": 0}
            for r in inventory]
    write(folder / "panel-summary.json", {"all_known": True, "rows": rows})
    report = {"status": "complete", "source_before": source, "source_after": source,
        "new_actor_steps": 1, "new_critic_steps": 1, "full_material_consumption_passed": True,
        "common_restored_exactly": True, "panel": runner.reference(folder / "panel-summary.json")}
    receipt = development_receipt(plan, candidate, [0] * 16, provenance="current_model_development")
    write(folder / "development-receipt.json", receipt)
    write(folder / "report.json", report)
    assert runner.verified_receipt(tmp_path, "trial-B", plan) == receipt
    for field in ("common_restored_exactly", "full_material_consumption_passed"):
        write(folder / "report.json", {**report, field: False})
        with pytest.raises(ValueError, match="same-common"):
            runner.verified_receipt(tmp_path, "trial-B", plan)


def test_pending_P3_never_fills_independent_effects_with_zero(tmp_path, monkeypatch):
    plan = {"source": {"code_commit": "synthetic"}, "inventories": support.inventories()}
    write(tmp_path / "plan.json", plan)
    monkeypatch.setattr(support, "results", lambda plan, root: {"status": "collecting"})
    value = runner.results(tmp_path)
    assert value["status"] == "not_started"
    assert value["I_minus_B"] is value["I_minus_G_raw"] is None
    assert value["independent_paired_units"] == []
    assert "training" not in runner.LIMITS["task_seconds"]
    assert runner.LIMITS["task_seconds"]["training_step"] == 900
    assert runner.LIMITS["artifact_bytes"] == 128 * 1024**3


def test_current_support_gate_rejects_shadow_before_any_allocation_math(monkeypatch):
    from proworksim import experience_allocation_v035
    from proworksim.software_collaboration_v036 import member_test_specification
    from proworksim.software_mapper_v036 import CLASS_ORDER, MAPPER, mapping_spec
    from proworksim.storage import digest, json_bytes
    spec = mapping_spec()
    seal = digest(json_bytes(spec))
    declaration = {"window_id": support.SUPPORT_WINDOW,
        "gamma_identity": {"gamma_version": "software-information-v0.36", "mapper_specification": spec,
                           "member_test_specification": member_test_specification()},
        "slots": [{"mapping_spec_id": MAPPER}]}
    # Deliberately minimal fixture isolates the admission door; raw math is not exercised here.
    entry = {"rollout": {"online_scope": {"method_mapper_spec_sha256": seal}},
        "mapping": {"mapper_spec_sha256": seal, "collection_mapper_binding_matches": True,
                    "shadow_diagnostic_only": False, "class_id": CLASS_ORDER[1],
                    "status": "mapped", "composition_support_eligible": True}}
    calls = []
    monkeypatch.setattr(experience_allocation_v035, "allocation_gate", lambda *args: calls.append(args))
    support.current_support_gate([entry], declaration, [])
    assert len(calls) == 1
    for mutation in ({"shadow_diagnostic_only": True}, {"composition_support_eligible": False},
                     {"collection_mapper_binding_matches": False}, {"class_id": "peer_fixed_product_delivery"}):
        bad = {**entry, "mapping": {**entry["mapping"], **mutation}}
        with pytest.raises(ValueError, match="Shadow"):
            support.current_support_gate([bad], declaration, [])
    with pytest.raises(ValueError, match="newly declared"):
        support.current_support_gate([entry], {**declaration, "window_id": "v035-current-policy-support-16"}, [])
    assert len(calls) == 1


def test_training_progress_is_transparent_and_restores_method_after_error(tmp_path):
    from proworksim.storage import read_json
    token_object = object()
    class Owner:
        def learning_logprobs(self, tokens, *, fail=False):
            assert tokens is token_object
            current = read_json(tmp_path / "task.json")
            assert current["kind"] == "training_step" and current["task"].startswith("learning-forward-")
            if fail:
                raise RuntimeError("actual learner error")
            return token_object
    owner = Owner()
    with runner.training_progress(owner, tmp_path):
        assert owner.learning_logprobs(token_object) is token_object
        assert read_json(tmp_path / "task.json")["task"].startswith("learning-backward-or-bookkeeping-")
    assert "learning_logprobs" not in owner.__dict__
    with pytest.raises(RuntimeError, match="actual learner error"):
        with runner.training_progress(owner, tmp_path):
            owner.learning_logprobs(token_object, fail=True)
    assert "learning_logprobs" not in owner.__dict__


def test_P3_freeze_error_survives_reporting_error_and_is_durably_recorded(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import freeze_software_allocation_v036 as freezer
    from proworksim.storage import read_json
    root = tmp_path / "new-run"
    def pretend_supervision(*args, **kwargs):
        write(root / "supervisor.json", {"status": "complete"})
        return SimpleNamespace(returncode=0)
    def fail_freeze(*args, **kwargs):
        raise RuntimeError("original freeze error")
    def fail_reporting(*args, **kwargs):
        raise ValueError("secondary reporting error")
    monkeypatch.setattr(support.subprocess, "run", pretend_supervision)
    monkeypatch.setattr(support, "report", lambda *args: {"next_stage": {"status": "ready_for_postcollection_freeze"}})
    monkeypatch.setattr(freezer, "freeze", fail_freeze)
    monkeypatch.setattr(runner, "report", fail_reporting)
    with pytest.raises(RuntimeError, match="original freeze error"):
        support.finish(tmp_path / "plan.json", root, tmp_path / "repository")
    state = read_json(tmp_path / "new-run-finish.json")
    assert state["status"] == "P3_preparation_or_execution_error"
    assert state["error"]["message"] == "original freeze error"
    assert state["P3_reporting_error"]["message"] == "secondary reporting error"
    assert state["ended_at"] >= state["started_at"]
