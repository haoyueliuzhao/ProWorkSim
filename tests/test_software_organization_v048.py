"""Affected v048 host controls; no model or tokenizer calls."""
from __future__ import annotations

import copy
import builtins

import pytest

from proworksim.software_organization_v047 import case_spec
from scripts import software_organization_v048 as runner


def test_eight_inventory_exact_reverse_pairs_and_unchanged_cases():
    inventory = runner.assignments()
    assert list(inventory) == ["root-LA", "root-LB"]
    expected = [("S1", "Gamma0"), ("S1", "Gamma1"), ("P4", "Gamma0"), ("P4", "Gamma1")]
    assert [(u["condition"], u["representation"]) for u in inventory["root-LA"]] == expected
    assert [(u["condition"], u["representation"]) for u in inventory["root-LB"]] == expected[::-1]
    assert len({u["slot_id"] for seq in inventory.values() for u in seq}) == 8
    for worker, seed in zip(runner.WORKERS, runner.SEEDS, strict=True):
        units = inventory[worker]
        assert all(u["sampling_seed"] == seed and u["team_token_budget"] == 500000 for u in units)
        cases = runner.cases_for(inventory)[worker]
        for case, unit in zip(cases, units, strict=True):
            assert case == case_spec(unit["case_id"], condition=unit["condition"],
                                     team_token_budget=500000, first_member="member_001")
        for condition in runner.CONDITIONS:
            pair = [c for c, u in zip(cases, units, strict=True) if u["condition"] == condition]
            assert pair[0] == pair[1]


def test_failed_admission_blocks_worker_before_model_import_or_output(tmp_path, monkeypatch):
    root = tmp_path / "run"
    output = root / "root-LA/actual"
    imports = []
    original_import = builtins.__import__

    def tracked_import(name, *args, **kwargs):
        if name == "proworksim.deterministic_work_v024":
            imports.append(name)
            raise AssertionError("model module reached before failed admission")
        return original_import(name, *args, **kwargs)

    def reject(_root):
        raise ValueError("candidate did not fit")

    monkeypatch.setattr(runner, "frozen", reject)
    monkeypatch.setattr(builtins, "__import__", tracked_import)
    with pytest.raises(ValueError, match="did not fit"):
        runner.run_worker(root, "root-LA", output)
    assert imports == []
    assert not output.exists()


def test_independent_workers_release_and_integrity_pause(tmp_path):
    states = {name: {"status": "not_started"} for name in runner.WORKERS}
    assert runner.eligible_workers(states) == list(runner.WORKERS)
    states["root-LA"]["status"] = "complete"
    assert runner.eligible_workers(states) == ["root-LB"]
    plan = {"assignments": runner.assignments()}
    runner.require_worker_release(tmp_path, "root-LB", plan)
    stops = tmp_path / "mechanism-stops"
    stops.mkdir()
    (stops / "failure.json").write_text("{}")
    with pytest.raises(ValueError, match="unopened"):
        runner.require_worker_release(tmp_path, "root-LB", plan)


def test_never_replay_attempted_worker_or_accept_outside_inventory(tmp_path):
    output = tmp_path / "root-LA/actual"
    output.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        runner.validate_worker_target(tmp_path, "root-LA", output)
    with pytest.raises(ValueError):
        runner.validate_worker_target(tmp_path, "old-worker", tmp_path / "old-worker/actual")


def test_authorized_resources_and_no_budget_transfer():
    assert runner.GPU_ORDER == (3, 4, 5, 7)
    assert runner.LIMITS["max_parallel_model_instances"] == 3
    assert runner.LIMITS["max_new_episodes"] == 8
    assert runner.LIMITS["task_seconds"]["episode"] == 6000
    assert runner.DEADLINES == {"soft_seconds": 5400, "hard_seconds": 6000, "close_window_seconds": 600}
    assert runner.budget_caps()["new"] == {
        "slots": 8, "total_tokens": 4000000, "decisions": 1024, "attempts": 1024, "run_tests": 256}
    assert runner.budget_caps()["transfer_old_unused"] is False
    with pytest.raises(ValueError, match="physical GPUs"):
        runner.worker_env({}, 0)


def test_binding_identifies_treatment_without_rewriting_collector_protocol():
    unit = runner.assignments()["root-LA"][0]
    binding = runner.representation_binding(unit, {"candidate": {"sha256": "frozen"}})
    assert binding["representation"] == "Gamma0"
    assert binding["transport_library"] == "software_context_v044"
    assert binding["base_runtime_library"] == "software_organization_runtime_v047"
    assert binding["world_or_prompt_instruction_changes"] is False
    assert runner.transport_factory(unit) is None
    invalid = copy.deepcopy(unit)
    invalid["representation"] = "Gamma2"
    with pytest.raises(ValueError):
        runner.representation_binding(invalid, {"candidate": {}})
    with pytest.raises(ValueError):
        runner.transport_factory(invalid)


def _closed(unit, R=1, censored=False):
    return {**unit, "status": "closed", "R_joint": R, "Q_joint": R,
            "R_token": None if censored else R, "Q_token": None if censored else R,
            "administrative_censoring": censored, "submitted": bool(R),
            "usage": {"total_tokens": 100, "budget_charged_tokens": 100, "uncertain_usage_attempts": 0}}


def test_aggregate_keeps_eight_denominator_unknown_and_administrative_censoring():
    units = [u for seq in runner.assignments().values() for u in seq]
    result = runner.aggregate_metrics(units, [_closed(units[0]), _closed(units[1], censored=True)])
    assert result["planned_slots"] == 8
    assert result["outcomes"]["R_joint"]["known_results"] == 2
    assert result["outcomes"]["R_token"]["known_results"] == 1
    assert result["outcomes"]["R_joint"]["mean"] is None
    assert result["complete_actual_tokens"] is None
    assert len(result["representation_pairs"]) == 4
    assert all(row["R_token_delta"] is None for row in result["representation_pairs"])
    with pytest.raises(ValueError, match="eight-slot"):
        runner.aggregate_metrics(units[:2], [_closed(units[0])])


def test_aggregate_compares_same_root_representation_and_rejects_changed_identity():
    units = [u for seq in runner.assignments().values() for u in seq]
    rows = [_closed(u, R=int(u["representation"] == "Gamma1")) for u in units]
    result = runner.aggregate_metrics(units, rows)
    assert result["complete_actual_tokens"] == 800
    assert all(row["R_joint_delta"] == 1 for row in result["representation_pairs"])
    rows[0]["representation"] = "Gamma1"
    with pytest.raises(ValueError, match="identity"):
        runner.aggregate_metrics(units, rows)
