"""Finite inventory/resource-policy controls; no resident or GPU subprocess."""
import copy

import pytest

from scripts import software_organization_v047 as pilot
from scripts.run_ne_v021 import write


def states(status="not_started"):
    return {name: {"status": status} for name in pilot.WORKERS}


def test_prelocked44_has_real_budget_pairs_and_no_old_seed_or_slot():
    grouped = pilot.assignments()
    units = [u for seq in grouped.values() for u in seq]
    assert len(units) == len({u["slot_id"] for u in units}) == 44
    assert sum(u["team_token_budget"] for u in units) == 15000000
    for root in pilot.ROOT_LABELS:
        rows = [u for u in units if u["root_id"] == root]
        assert len(rows) == 11 and len({u["sampling_seed"] for u in rows}) == 1
        low = {u["condition"]: u for u in rows if u["stage"] == "A"}
        high = {u["condition"]: u for u in rows if u["stage"] == "B"}
        assert set(low) == set(pilot.CONDITIONS)
        assert set(high) == set(pilot.HIGH_BUDGET_CONDITIONS)
        for c, high_unit in high.items():
            assert low[c]["sampling_seed"] == high_unit["sampling_seed"]
            assert low[c]["slot_id"] != high_unit["slot_id"]
            assert (low[c]["team_token_budget"], high_unit["team_token_budget"]) == (250000, 500000)
    assert all(u["first_member"] == "member_001" for u in units)
    assert not {u["sampling_seed"] for u in units} & {202610100451, 202610100452, 202610110046}


def test_stage_B_waits_for_all_A_workers_without_outcome_selection():
    value = states()
    assert pilot.eligible_workers(value) == list(pilot.WORKERS[:4])
    for name in pilot.WORKERS[:3]:
        value[name] = {"status": "complete", "R": 0, "births": 0, "R_token": None}
    value[pilot.WORKERS[3]]["status"] = "running"
    assert pilot.eligible_workers(value) == []
    value[pilot.WORKERS[3]]["status"] = "complete"
    assert pilot.eligible_workers(value) == list(pilot.WORKERS[4:])
    altered = copy.deepcopy(value)
    for name in pilot.WORKERS[:4]:
        altered[name].update(R=1, births=4, R_token=1)
    assert pilot.eligible_workers(altered) == pilot.eligible_workers(value)


@pytest.mark.parametrize("status", ["stopped", "measurement_pending", "global_pause"])
def test_incomplete_A_never_releases_B(status):
    value = states("complete")
    value[pilot.WORKERS[0]]["status"] = status
    for name in pilot.WORKERS[4:]:
        value[name]["status"] = "not_started"
    assert pilot.eligible_workers(value) == []


def test_hard_episode_only_changes_inherited_resource_limits():
    expected = {**copy.deepcopy(pilot.prior.LIMITS), "max_new_episodes": 44,
                "max_parallel_model_instances": 3,
                "task_seconds": {"loading": 900, "episode": 6000, "boundary": 600}}
    assert pilot.LIMITS == expected
    assert pilot.DEADLINES == {"soft_seconds": 5400, "hard_seconds": 6000, "close_window_seconds": 600}
    assert pilot.GPU_ORDER == (3, 4, 5, 7)


def test_worker_target_cannot_replay_or_redirect(tmp_path):
    worker = pilot.WORKERS[0]
    output = tmp_path / worker / "actual"
    assert pilot.validate_worker_target(tmp_path, worker, output) == (tmp_path, output)
    with pytest.raises(ValueError):
        pilot.validate_worker_target(tmp_path, worker, tmp_path / "elsewhere")
    output.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        pilot.validate_worker_target(tmp_path, worker, output)


def test_no_other_gpu_or_wrong_python_environment():
    plan = {"native_python": "/tmp/native-venv/bin/python", "native_python_prefix": "/tmp/native-venv"}
    pilot.validate_worker_interpreter(plan, executable=plan["native_python"], prefix=plan["native_python_prefix"])
    with pytest.raises(ValueError):
        pilot.validate_worker_interpreter(plan, executable=plan["native_python"], prefix="/tmp/other-venv")
    with pytest.raises(ValueError):
        pilot.worker_env(plan, 0)


def test_budget_caps_no_qualification_or_old_transfer():
    caps = pilot.budget_caps()
    assert caps["new"] == {"slots": 44, "total_tokens": 15000000, "decisions": 5632, "attempts": 5632, "run_tests": 1408}
    assert caps["new_qualification_model_calls"] == caps["new_qualification_actual_tokens"] == 0
    assert caps["transfer_old_unused"] is False and caps["automatic_successors"] == []


@pytest.mark.parametrize("unreleased", ["missing_supervisor", "running_A", "wrong_source"])
def test_direct_stage_B_worker_cannot_bypass_release(tmp_path, unreleased):
    plan = {"source": {"code_commit": "frozen"}}
    value = {"source": plan["source"], "states": states("complete")}
    if unreleased == "running_A":
        value["states"][pilot.WORKERS[3]]["status"] = "running"
    if unreleased == "wrong_source":
        value["source"] = {"code_commit": "different"}
    if unreleased != "missing_supervisor":
        write(tmp_path / "supervisor.json", value)
    with pytest.raises(ValueError, match="Stage B cannot load"):
        pilot.require_worker_release(tmp_path, pilot.WORKERS[4], plan)
    write(tmp_path / "supervisor.json", {"source": plan["source"], "states": states("complete")})
    pilot.require_worker_release(tmp_path, pilot.WORKERS[4], plan)
