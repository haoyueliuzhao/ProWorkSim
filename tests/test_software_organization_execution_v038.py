"""Finite inventory, reporting and GPU-boundary CPU controls; no model or telemetry."""
from collections import Counter
import hashlib
import os

import pytest

from scripts import software_organization_v038 as runner
from scripts.run_ne_v021 import write


def inventory_plan(root):
    plan = {"source": {"code_commit": "cpu-control", "code_dirty": False},
            "assignments": runner.assignments()}
    write(root / "plan.json", plan)
    return plan


def all_units(plan):
    return [(worker, unit) for worker, units in plan["assignments"].items() for unit in units]


def save_result(root, worker, unit, *, reward, status="closed", submitted=False):
    initial = ["member_001", "member_002"]
    if unit["condition"] == "O2":
        initial += ["member_003", "member_004"]
    calls = 2 if reward == 1 else 7
    result = {**unit, "status": status, "R": reward, "submitted": submitted,
        "training_eligible": False,
        "member_lifecycle": {"initial_members": initial, "cumulative_births": len(initial),
                             "actual_output_participants": 1},
        "usage": {"decisions": calls, "attempts": calls, "prompt_tokens": 5 * calls,
                  "completion_tokens": 2 * calls, "total_tokens": 7 * calls, "output_bearing_calls": calls},
        "team_budget": {"tests": {"used": 1 if reward == 1 else 3}}}
    write(root / worker / "actual/episodes" / unit["slot_id"] / "slot-result.json", result)
    return result


def test_inventory_keeps_four_original_roots_all_conditions_and_two_new_paired_seeds():
    inventory = runner.assignments()
    units = [unit for group in inventory.values() for unit in group]
    assert tuple(inventory) == ("root-0", "root-1", "root-2", "root-3")
    assert all(len(group) == 6 and len({u["case_id"] for u in group}) == 1
               for group in inventory.values())
    assert len(units) == len({u["slot_id"] for u in units}) == 24
    assert Counter(u["original_case_id"] for u in units) == {
        "sc-job-policy-v035": 6, "sc-command-set-v035": 6,
        "sc-room-bookings-v036": 6, "sc-order-totals-v036": 6}
    assert Counter(u["condition"] for u in units) == {"O1": 8, "O2": 8, "O3": 8}
    assert {u["sampling_seed"] for u in units} == {202610090101, 202610090102}
    assert len({(u["case_id"], u["sampling_seed"], u["condition"]) for u in units}) == 24
    for group in inventory.values():
        for seed in runner.SEEDS:
            paired = {u["condition"]: u for u in group if u["sampling_seed"] == seed}
            assert set(paired) == {"O1", "O2", "O3"}
            assert paired["O1"]["first_member"] == paired["O3"]["first_member"]
        for condition in ("O1", "O3"):
            assert {u["first_member"] for u in group if u["condition"] == condition} == {
                "member_001", "member_002"}
    assert Counter(u["first_member"] for u in units if u["condition"] == "O2") == {
        "member_001": 2, "member_002": 2, "member_003": 2, "member_004": 2}
    assert [tuple(u["condition"] for u in group) for group in inventory.values()] == [
        ("O1", "O2", "O3", "O2", "O3", "O1"),
        ("O3", "O1", "O2", "O1", "O2", "O3"),
        ("O2", "O3", "O1", "O3", "O1", "O2"),
        ("O1", "O2", "O3", "O2", "O3", "O1")]


def test_pending_and_terminal_unknowns_keep_original_slots_and_do_not_become_failures(tmp_path):
    plan = inventory_plan(tmp_path)
    pairs = all_units(plan)
    first_worker = pairs[0][0]
    first_seed = pairs[0][1]["sampling_seed"]
    for worker, unit in pairs:
        if worker == first_worker and unit["sampling_seed"] == first_seed:
            save_result(tmp_path, worker, unit, reward=int(unit["condition"] == "O1"),
                        submitted=unit["condition"] == "O1")
    unknown_worker, unknown_unit = pairs[6]
    save_result(tmp_path, unknown_worker, unknown_unit, reward=None,
                status="technical_unknown", submitted=None)
    started_worker, started_unit = pairs[7]
    (tmp_path / started_worker / "actual/episodes" / started_unit["slot_id"]).mkdir(parents=True)
    write(tmp_path / "supervisor.json", {"status": "closed_with_unknowns", "states": {}})
    value = runner.results(tmp_path)
    rows = {r["slot_id"]: r for r in value["rows"]}
    assert set(rows) == {u["slot_id"] for _, u in pairs}
    assert value["scheduled"] == len(rows) == 24
    assert value["known"] == 3
    for unit in (unknown_unit, started_unit):
        assert rows[unit["slot_id"]]["status"] == "technical_unknown"
        assert rows[unit["slot_id"]]["R"] is None
        assert rows[unit["slot_id"]]["submitted"] is None
    untouched = rows[pairs[-1][1]["slot_id"]]
    assert untouched["status"] == "not_started"
    assert untouched["R"] is None
    for stats in value["by_condition"].values():
        assert stats["known"] == 1
        assert stats["unknown_or_pending"] == 7
        assert stats["mean_R"] is None
    assert value["by_condition"]["O3"]["episodes_with_new_births"] == 0
    assert value["paired_units"][0]["O3_minus_O1"] == -1
    assert value["paired_units"][0]["O3_minus_O2"] == 0
    assert all(delta is None for delta in value["paired_mean_differences"].values())


def test_all_closed_no_spawn_episodes_and_unsuccessful_costs_remain_in_comparison(tmp_path):
    plan = inventory_plan(tmp_path)
    originals = [save_result(tmp_path, worker, unit, reward=int(unit["condition"] != "O2"),
                            submitted=unit["condition"] != "O2") for worker, unit in all_units(plan)]
    write(tmp_path / "supervisor.json", {"status": "complete", "states": {}})
    value = runner.results(tmp_path)
    assert value["scheduled"] == value["known"] == len(value["rows"]) == 24
    assert value["rows"] == originals
    assert all(v["known"] == 8 and v["unknown_or_pending"] == 0 for v in value["by_condition"].values())
    assert value["by_condition"]["O3"]["episodes_with_new_births"] == 0
    assert value["by_condition"]["O3"]["mean_R"] == 1
    assert value["by_condition"]["O2"]["mean_R"] == 0
    assert value["paired_mean_differences"] == {"O3_minus_O1": 0, "O3_minus_O2": 1}
    assert len(value["paired_units"]) == 8
    assert value["cost"]["episodes_with_closed_usage"] == 24
    assert value["cost"]["closed_usage"]["attempts"] == 16 * 2 + 8 * 7
    assert value["cost"]["closed_usage"]["total_tokens"] == (16 * 2 + 8 * 7) * 7
    assert value["cost"]["closed_test_runs"] == 16 + 8 * 3
    assert sum(row["usage"]["attempts"] for row in value["rows"]) == 16 * 2 + 8 * 7
    assert all(row["member_lifecycle"]["cumulative_births"] == 2
               for row in value["rows"] if row["condition"] == "O3")


@pytest.mark.parametrize("reward", [None, True, 1.0, 2])
def test_closed_label_does_not_promote_missing_or_invalid_reward_to_known(tmp_path, reward):
    plan = inventory_plan(tmp_path)
    worker, unit = all_units(plan)[0]
    save_result(tmp_path, worker, unit, reward=reward)
    value = runner.results(tmp_path)
    assert value["known"] == 0
    assert value["rows"][0]["R"] == reward
    assert type(value["rows"][0]["R"]) is type(reward)
    assert value["by_condition"][unit["condition"]]["mean_R"] is None
    assert all(p["O3_minus_O1"] is None and p["O3_minus_O2"] is None for p in value["paired_units"])


def test_allowed_resources_queries_only_permitted_physical_cards(monkeypatch):
    calls = []
    sentinel = {"cpu_control": "no telemetry executed"}

    def fake_resources(selector, *, worker_pid):
        calls.append((selector, worker_pid))
        return sentinel

    monkeypatch.setattr(runner, "target_resources", fake_resources)
    assert runner.allowed_resources() is sentinel
    assert calls == [("3,4,5,7", os.getpid())]


@pytest.mark.parametrize("gpu", [3, 4, 5, 7])
def test_worker_environment_replaces_inherited_gpu_selection_with_one_allowed_card(monkeypatch, gpu):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1,2,6")
    monkeypatch.setenv("PYTHONPATH", "/not-the-declared-runtime")
    env = runner.worker_env({"runtime_dependency_path": "/cpu-fixture/runtime"}, gpu)
    assert env["CUDA_VISIBLE_DEVICES"] == str(gpu)
    assert env["PYTHONPATH"].split(os.pathsep) == [
        "/cpu-fixture/runtime", str(runner.SOURCE / "src"), str(runner.SOURCE)]
    assert env["TOKENIZERS_PARALLELISM"] == "false"
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "0,1,2,6"


@pytest.mark.parametrize("gpu", [0, 1, 2, 6, -1, 8, "3", "3,4", "", None])
def test_worker_environment_rejects_nonpermitted_or_ambiguous_assignment(gpu):
    with pytest.raises(ValueError, match="Only physical GPUs 3,4,5,7"):
        runner.worker_env({"runtime_dependency_path": "/cpu-fixture/runtime"}, gpu)


@pytest.mark.parametrize("change", ["unchanged", "wrong_size", "changed_content"])
def test_checkpoint_reference_accepts_optional_exact_bytes_and_rejects_corruption(tmp_path, change):
    path = tmp_path / "common-state.bin"
    original = b"original-common-state"
    path.write_bytes(original)
    reference = {"path": str(path), "sha256": hashlib.sha256(original).hexdigest(),
                 "bytes": len(original)}
    if change == "wrong_size":
        reference["bytes"] += 1
    elif change == "changed_content":
        # Same size isolates the digest binding from the optional size check.
        path.write_bytes(b"X" + original[1:])
    if change == "unchanged":
        assert runner.checked(reference) == path
    else:
        with pytest.raises(ValueError, match="Frozen artifact content or size changed"):
            runner.checked(reference)
