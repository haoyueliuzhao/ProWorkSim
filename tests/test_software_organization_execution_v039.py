"""Finite v039 controller controls; no resident model, GPU query or old requalification."""
from collections import Counter
import copy
import os

import pytest

from scripts import software_organization_v039 as runner
from scripts.run_ne_v021 import write


def inventory_plan(root):
    plan = {"source": {"code_commit": "cpu-controller-control", "code_dirty": False},
        "assignments": runner.assignments(), "diagnostic_assignments": runner.diagnostic_assignments()}
    write(root / "plan.json", plan)
    return plan


def main_units(plan):
    return [(worker, unit) for worker, rows in plan["assignments"].items() for unit in rows]


def states():
    return {worker: {"worker": worker, "status": "not_started", "attempted": False}
            for worker in runner.ALL_WORKERS}


def save_result(root, worker, unit, *, reward, submitted=False, status="closed", calls=None,
                diagnostic_goal=None, external_implemented=False):
    calls = (2 if reward == 1 else 7) if calls is None else calls
    diagnostic = worker == runner.DIAGNOSTIC_WORKER
    initial = ["member_001", "member_002"]
    result = {**unit, "purpose": "interface_diagnostic" if diagnostic else "organization_development",
        "status": status, "R": reward, "submitted": submitted,
        "training_eligible": False, "admission_eligible": False,
        "outcome_type": "interface_control" if diagnostic else "business_delivery",
        "member_lifecycle": {"initial_members": initial,
            "cumulative_births": 2 + int(external_implemented), "actual_output_participants": 1,
            "member_requested_births": 0, "external_births": int(external_implemented)},
        "external_intervention": {"status": "implemented" if external_implemented else "skipped",
                                  "reason": None if external_implemented else "natural_terminal"},
        "usage": {"decisions": calls + 1, "attempts": calls, "prompt_tokens": 5 * calls,
            "completion_tokens": 2 * calls, "total_tokens": 7 * calls,
            "output_bearing_calls": calls, "budget_charged_tokens": 7 * calls,
            "uncertain_usage_attempts": 0},
        "team_budget": {"tests": {"used": 0 if diagnostic else 1 if reward == 1 else 3}},
        "diagnostic": {"probe_id": unit["probe_id"], "all_goals_met": diagnostic_goal,
            "status": status, "business_R": None, "autonomous_behavior_evidence": False} if diagnostic else None}
    write(root / worker / "actual/episodes" / unit["slot_id"] / "slot-result.json", result)
    return result


def test_main_inventory_is_exact_new_roots_three_conditions_and_paired_first_members():
    inventory = runner.assignments()
    rows = [row for group in inventory.values() for row in group]
    assert tuple(inventory) == ("root-0", "root-1", "root-2", "root-3")
    assert len(rows) == len({row["slot_id"] for row in rows}) == 24
    assert Counter(row["case_id"] for row in rows) == {
        "sc-label-index-v039": 6, "sc-row-projection-v039": 6,
        "sc-record-views-v039": 6, "sc-record-catalog-v039": 6}
    assert Counter(row["root_family"] for row in rows) == {"light_control": 12, "cross_dependency": 12}
    assert Counter(row["condition"] for row in rows) == {"F2": 8, "A3": 8, "X3": 8}
    assert {row["sampling_seed"] for row in rows} == {202610090201, 202610090202}
    assert len({(row["case_id"], row["condition"], row["sampling_seed"]) for row in rows}) == 24
    for root_index, group in enumerate(inventory.values()):
        assert len(group) == 6 and len({row["case_id"] for row in group}) == 1
        for seed_index, seed in enumerate(runner.SEEDS):
            paired = [row for row in group if row["sampling_seed"] == seed]
            assert {row["condition"] for row in paired} == {"F2", "A3", "X3"}
            assert {row["first_member"] for row in paired} == {f"member_{1 + (root_index + seed_index) % 2:03d}"}
        assert {row["first_member"] for row in group} == {"member_001", "member_002"}
    assert [tuple(row["condition"] for row in group) for group in inventory.values()] == [
        ("F2", "A3", "X3", "A3", "X3", "F2"),
        ("X3", "F2", "A3", "F2", "A3", "X3"),
        ("A3", "X3", "F2", "X3", "F2", "A3"),
        ("F2", "A3", "X3", "A3", "X3", "F2")]


def test_two_guided_controls_have_separate_ids_seeds_purpose_and_small_budget():
    diagnostic = runner.diagnostic_assignments()
    mains = {row["slot_id"] for rows in runner.assignments().values() for row in rows}
    assert len(diagnostic) == 2
    assert {row["slot_id"] for row in diagnostic}.isdisjoint(mains)
    assert [row["probe_id"] for row in diagnostic] == ["birth-message", "replacement-patch"]
    assert [row["sampling_seed"] for row in diagnostic] == [202610090191, 202610090192]
    assert set(runner.DIAGNOSTIC_SEEDS).isdisjoint(runner.SEEDS)
    assert runner.LIMITS["max_new_episodes"] == 26
    assert runner.LIMITS["max_main_episodes"] == 24 and runner.LIMITS["max_diagnostic_episodes"] == 2
    for unit in diagnostic:
        assert unit["guided"] is True and unit["purpose"] == "interface_diagnostic"
        spec = runner.diagnostic_case_spec(unit["probe_id"], case_id=unit["case_id"], first_member=unit["first_member"])
        assert spec["purpose"] == "interface_diagnostic"
        assert spec["diagnostic"]["main_business_R_eligible"] is False
        assert spec["diagnostic"]["automatic_retry"] is False
        assert {k: spec["team_limits"][k] for k in ("max_decisions", "max_attempts", "max_total_tokens")} == {
            "max_decisions": 12, "max_attempts": 12, "max_total_tokens": 150000}


def test_stage_waiting_requires_closed_controls_but_not_their_model_goal_success():
    state = states()
    before = copy.deepcopy(state)
    assert runner.stage_waiting(state) == [runner.DIAGNOSTIC_WORKER]
    assert state == before
    state[runner.DIAGNOSTIC_WORKER].update(status="running", attempted=True)
    assert runner.stage_waiting(state) == []
    assert all(state[worker]["status"] == "not_started" for worker in runner.WORKERS)
    state[runner.DIAGNOSTIC_WORKER].update(status="complete", all_goals_met=False)
    assert runner.stage_waiting(state) == list(runner.WORKERS)
    state[runner.WORKERS[0]].update(status="running", attempted=True)
    assert runner.stage_waiting(state) == list(runner.WORKERS[1:])


def test_technical_stop_in_controls_blocks_unstarted_main_without_a_retry():
    state = states()
    state[runner.DIAGNOSTIC_WORKER].update(status="stopped", attempted=True, stop_reason="worker_exit_error")
    assert runner.stage_waiting(state) == []
    for worker in runner.WORKERS:
        assert state[worker]["status"] == "stopped"
        assert state[worker]["stop_reason"] == "interface_stage_technical_failure"
        assert state[worker]["attempted"] is False
        assert state[worker]["elapsed_gpu_seconds"] == 0
    unchanged = copy.deepcopy(state)
    assert runner.stage_waiting(state) == []
    assert state == unchanged


def test_all_main_slots_and_costs_remain_when_x3_intervention_is_skipped(tmp_path):
    plan = inventory_plan(tmp_path)
    expected = {}
    for worker, unit in main_units(plan):
        success = unit["condition"] != "A3"
        expected[unit["slot_id"]] = save_result(tmp_path, worker, unit, reward=int(success), submitted=success,
            external_implemented=unit["condition"] == "X3" and unit["sampling_seed"] == runner.SEEDS[0])
    for index, unit in enumerate(plan["diagnostic_assignments"]):
        save_result(tmp_path, runner.DIAGNOSTIC_WORKER, unit, reward=None, calls=index + 3,
                    diagnostic_goal=index == 1)
    state = states()
    for index, worker in enumerate(runner.ALL_WORKERS):
        state[worker].update(status="complete", attempted=True, elapsed_gpu_seconds=100 + index)
    write(tmp_path / "supervisor.json", {"status": "complete", "states": state,
        "closed_worker_gpu_seconds": sum(s["elapsed_gpu_seconds"] for s in state.values()),
        "running_worker_gpu_seconds": 0})
    value = runner.results(tmp_path)
    assert value["scheduled"] == value["known"] == len(value["rows"]) == 24
    assert value["primary_scheduled"] == 16 and value["auxiliary_scheduled"] == 8
    assert set(row["slot_id"] for row in value["rows"]) == set(expected)
    assert all(row["purpose"] == "organization_development" for row in value["rows"])
    for row in value["rows"]:
        assert row["usage"] == expected[row["slot_id"]]["usage"]
        assert row["R"] == expected[row["slot_id"]]["R"]
    for condition in runner.CONDITIONS:
        assert value["by_condition"][condition]["known"] == 8
        assert value["by_condition"][condition]["scheduled"] == 8
    assert value["by_condition"]["A3"]["mean_R"] == 0
    assert value["by_condition"]["X3"]["mean_R"] == 1
    assert value["by_condition"]["A3"]["comparison_role"] == "primary_natural_regime"
    assert value["by_condition"]["X3"]["comparison_role"] == "auxiliary_external_control"
    assert value["by_condition"]["X3"]["member_requested_births"] == 0
    assert value["by_condition"]["X3"]["external_births"] == 4
    assert len(value["by_condition"]["X3"]["external_intervention_dispositions"]) == 8
    assert value["paired_mean_differences"] == {"A3_minus_F2": -1, "X3_minus_A3": 1}
    assert len(value["paired_units"]) == 8
    assert sum(row["external_intervention"]["status"] == "skipped" for row in value["rows"] if row["condition"] == "X3") == 4
    assert value["cost"]["episodes_with_closed_usage"] == 24
    assert value["cost"]["closed_usage"]["attempts"] == 16 * 2 + 8 * 7
    assert value["cost"]["closed_usage"]["total_tokens"] == (16 * 2 + 8 * 7) * 7
    assert value["cost"]["closed_test_runs"] == 16 + 8 * 3
    assert value["cost"]["closed_worker_gpu_seconds"] == sum(state[worker]["elapsed_gpu_seconds"] for worker in runner.WORKERS)
    diagnostic = value["diagnostics"]
    assert diagnostic["scheduled"] == diagnostic["closed"] == len(diagnostic["rows"]) == 2
    assert diagnostic["goals_met"] == 1 and diagnostic["not_business_R"] is True
    assert all(row["R"] is None for row in diagnostic["rows"])
    assert diagnostic["cost"]["closed_usage"]["attempts"] == 7
    assert diagnostic["cost"]["closed_worker_gpu_seconds"] == 100
    assert value["total_worker_gpu_seconds"] == {
        "closed": sum(state[worker]["elapsed_gpu_seconds"] for worker in runner.ALL_WORKERS), "running": 0}


def test_partial_results_keep_main_inventory_and_worker_terminal_unknowns(tmp_path):
    plan = inventory_plan(tmp_path)
    units = main_units(plan)
    for worker, unit in units[:3]:
        save_result(tmp_path, worker, unit, reward=int(unit["condition"] == "F2"),
                    submitted=unit["condition"] == "F2")
    worker, started = units[6]
    (tmp_path / worker / "actual/episodes" / started["slot_id"]).mkdir(parents=True)
    _, explicit = units[7]
    save_result(tmp_path, worker, explicit, reward=None, submitted=None, status="technical_unknown")
    state = states()
    state[runner.DIAGNOSTIC_WORKER].update(status="complete", attempted=True)
    state[worker].update(status="stopped", attempted=True)
    state[runner.WORKERS[-1]].update(status="running", attempted=True, started_at=100.0)
    write(tmp_path / "supervisor.json", {"status": "running", "observed_at": 200.0, "states": state})
    value = runner.results(tmp_path)
    rows = {row["slot_id"]: row for row in value["rows"]}
    assert value["scheduled"] == len(rows) == 24 and value["known"] == 3
    for unit in (started, explicit):
        assert rows[unit["slot_id"]]["status"] == "technical_unknown"
        assert rows[unit["slot_id"]]["R"] is None and rows[unit["slot_id"]]["submitted"] is None
    assert rows[units[-1][1]["slot_id"]]["status"] == "not_started"
    assert rows[units[-1][1]["slot_id"]]["R"] is None
    for condition in runner.CONDITIONS:
        assert value["by_condition"][condition]["known"] == 1
        assert value["by_condition"][condition]["unknown_or_pending"] == 7
        assert value["by_condition"][condition]["mean_R"] is None
    assert all(value is None for value in value["paired_mean_differences"].values())
    assert value["diagnostics"]["closed"] == 0


@pytest.mark.parametrize("reward", [None, True, 1.0, 2])
def test_closed_status_cannot_promote_an_unknown_or_invalid_main_reward(tmp_path, reward):
    plan = inventory_plan(tmp_path)
    worker, unit = main_units(plan)[0]
    save_result(tmp_path, worker, unit, reward=reward)
    value = runner.results(tmp_path)
    assert value["known"] == 0
    row = next(row for row in value["rows"] if row["slot_id"] == unit["slot_id"])
    assert row["R"] == reward and type(row["R"]) is type(reward)
    assert value["by_condition"][unit["condition"]]["mean_R"] is None


def test_gpu_queries_and_worker_environments_are_confined_to_allowed_physical_cards(monkeypatch):
    calls = []
    marker = {"cpu_control_only": True}

    def fake_resources(selector, *, worker_pid):
        calls.append((selector, worker_pid))
        return marker

    monkeypatch.setattr(runner, "target_resources", fake_resources)
    assert runner.allowed_resources() is marker
    assert calls == [("3,4,5,7", os.getpid())]
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1,2,6")
    monkeypatch.setenv("PROWORKSIM_REPLICA_GPUS", "0,1")
    for gpu in (3, 4, 5, 7):
        env = runner.worker_env({"runtime_dependency_path": "/cpu-fixture/runtime"}, gpu)
        assert env["CUDA_VISIBLE_DEVICES"] == str(gpu)
        assert "PROWORKSIM_REPLICA_GPUS" not in env
        assert env["PYTHONPATH"].split(os.pathsep) == ["/cpu-fixture/runtime", str(runner.SOURCE / "src"), str(runner.SOURCE)]
        assert env["HF_HUB_OFFLINE"] == env["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "0,1,2,6"
    for gpu in (0, 1, 2, 6, -1, 8, "3", "3,4", None):
        with pytest.raises(ValueError, match="Only physical GPUs 3,4,5,7"):
            runner.worker_env({"runtime_dependency_path": "/cpu-fixture/runtime"}, gpu)
    sample = {"gpus": {"returncode": 0, "stdout": "\n".join(
        f"{gpu}, GPU-{gpu}, NVIDIA A100-SXM4-80GB, 80000, 81920, 0" for gpu in range(8))},
        "processes": {"returncode": 0, "stdout": ""}}
    cards = runner.available_cards({"gpu_preference": list(runner.GPU_ORDER), "limits": runner.LIMITS}, sample)
    assert [card["index"] for card in cards] == [3, 4, 5, 7]
    assert not runner.available_cards({"gpu_preference": list(runner.GPU_ORDER), "limits": runner.LIMITS}, sample,
                                      excluded=[3, 4, 5, 7])
