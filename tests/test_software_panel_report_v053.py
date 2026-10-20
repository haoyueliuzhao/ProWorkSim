from collections import Counter
import copy

import pytest

from proworksim.software_panel_report_v053 import build_report, markdown, wilson95
from proworksim.software_panel_v053 import canonical_bytes, sha256
from scripts.software_panel_v053_report import load_observations


SHA = "a" * 64


def panel():
    tasks = [{"task_id": f"t{index}", "repository": f"repo{index // 10}",
              "mutation_family": "fixture"} for index in range(200)]
    repeats = [f"t{repo * 10 + offset}" for repo in range(20) for offset in (0, 1)]
    slots = []
    for repeat_index, task_ids in ((1, [task["task_id"] for task in tasks]), (2, repeats), (3, repeats)):
        for task_id in task_ids:
            slots.append({"slot_id": f"s{len(slots)}", "task_id": task_id,
                          "seed": len(slots), "repeat_index": repeat_index,
                          "role": "main" if repeat_index == 1 else "repeat_diagnostic"})
    return {"tasks": tasks, "slots": slots,
            "main_task_ids": [task["task_id"] for task in tasks], "repeat_task_ids": repeats}


def observation(row, value, *, unknown=False):
    return {
        "panel_sha256": SHA, "row": row,
        "status": "technical_unknown" if unknown else "complete",
        "R_code": None if unknown else value,
        "verdict": {"failure_type": "model_finished_incomplete" if value == 0 else None,
                    "reasons": ["provider_interruption"] if unknown else []},
        "accounting": {
            "known_actual_tokens": 100, "complete_actual_tokens": None if unknown else 100,
            "uncertain_reservation_tokens": 50 if unknown else 0,
            "started_generations": 2 if unknown else 1, "complete_generations": 1,
            "actual_calls": [{"attempt_id": "attempt-1", "usage": {
                "prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}}],
        },
    }


def test_main_uses_only_first_200_and_repeat_histogram_is_task_level():
    frozen = panel()
    observations = []
    for row in frozen["slots"]:
        # All repeats succeed; main only repo0..9 succeed.
        outcome = int(int(row["task_id"][1:]) < 100 or row["repeat_index"] != 1)
        observations.append(observation(row, outcome))
    result = build_report(frozen, observations, panel_sha256=SHA)
    assert result["main"]["completion_rate"] == 0.5
    assert result["main"]["denominator"] == 200
    assert result["repeat_diagnostic"]["success_count_histogram"] == {
        "0/3": 0, "1/3": 0, "2/3": 20, "3/3": 20}
    assert [r["completion_rate"] for r in result["repeat_diagnostic"]["rounds"]] == [0.5, 1, 1]
    assert result["repeat_diagnostic"]["mixed_outcome_task_fraction"] == 0.5
    assert result["interpretation"]["all_280_pooled_completion_rate"] is None
    assert result["tokens"]["all_280_slots"]["known_actual_tokens"] == 28_000
    assert result["tokens"]["main_200_slots"]["known_actual_tokens"] == 20_000
    assert result["tokens"]["main_200_slots"]["per_episode_final_actual_distribution"]["median"] == 100
    assert len(result["tasks"]) == 200 and len(result["episodes"]) == 280
    assert len(result["repositories"]) == 20
    cluster = result["main"]["repository_cluster_bootstrap"]
    assert cluster["clusters"] == 20 and cluster["draws"] == 20_000
    assert cluster["interval95"][0] <= 0.5 <= cluster["interval95"][1]
    assert "280 回合混合平均" in markdown(result)


def test_unknown_keeps_denominator_and_never_becomes_zero_of_three():
    frozen = panel()
    observations = [observation(row, 1) for row in frozen["slots"]]
    observations[0] = observation(frozen["slots"][0], None, unknown=True)
    result = build_report(frozen, observations, panel_sha256=SHA)
    assert result["main"]["completion_rate"] is None
    assert result["main"]["identification_bounds"] == [199 / 200, 1]
    assert result["main"]["wilson95_working_independence"] is None
    assert result["main"]["repository_cluster_bootstrap"]["interval95"] is None
    repeat = result["repeat_diagnostic"]
    assert repeat["success_count_histogram"] == {"0/3": 0, "1/3": 0, "2/3": 0, "3/3": 39}
    assert repeat["unknown_three_run_task_count"] == 1
    assert result["failure_distribution"]["technical_unknown_episodes"] == 1
    assert result["failure_distribution"]["known_model_failures"] == {}
    assert result["tokens"]["all_280_slots"]["complete_observed_actual_tokens"] is None
    assert result["tokens"]["all_280_slots"]["known_actual_tokens"] == 28_000
    assert result["tokens"]["all_280_slots"]["known_uncertain_reservation_tokens"] == 50


def test_partial_inventory_preserves_all_slots_and_running_identity():
    frozen = panel()
    result = build_report(
        frozen, [observation(frozen["slots"][0], 1)], panel_sha256=SHA,
        started_slot_ids={"s0", "s1", "s2"}, active_slot_ids={"s2"})
    assert result["inventory"]["state_counts"] == {
        "complete": 1, "not_started": 277, "running": 1, "technical_unknown": 1}
    assert result["main"]["identification_bounds"] == [1 / 200, 1]
    assert result["main"]["known_subset_rate"] is None
    assert result["tokens"]["all_280_slots"]["full_planned_inventory_actual_tokens"] is None
    assert result["tokens"]["all_280_slots"]["per_episode_final_actual_distribution"]["mean"] is None
    assert result["repeat_diagnostic"]["unknown_three_run_task_count"] == 40
    assert sum(result["repeat_diagnostic"]["success_count_histogram"].values()) == 0


def test_resource_retries_are_zero_model_events_not_new_independent_episodes():
    frozen = panel()
    wait = {
        "panel_sha256": SHA, "row": frozen["slots"][0], "status": "resource_wait",
        "loader_not_entered": True, "model_loader_entered": False,
        "model_calls": 0, "known_actual_tokens": 0, "resident_exists": False,
    }
    result = build_report(frozen, [wait, copy.deepcopy(wait),
                                  observation(frozen["slots"][0], 0)], panel_sha256=SHA)
    assert result["inventory"]["resource_wait_attempts"] == 2
    assert result["main"]["failures"] == 1 and result["main"]["unknown"] == 199
    assert result["tokens"]["all_280_slots"]["known_actual_tokens"] == 100
    wait["model_calls"] = 1
    with pytest.raises(ValueError, match="zero model"):
        build_report(frozen, [wait], panel_sha256=SHA)


def test_duplicate_formal_rows_wrong_identity_and_accounting_conflicts_fail_closed():
    frozen = panel()
    row = observation(frozen["slots"][0], 1)
    with pytest.raises(ValueError, match="Duplicate formal"):
        build_report(frozen, [row, row], panel_sha256=SHA)
    wrong = copy.deepcopy(row)
    wrong["row"]["seed"] += 1
    with pytest.raises(ValueError, match="identity"):
        build_report(frozen, [wrong], panel_sha256=SHA)
    wrong = copy.deepcopy(row)
    wrong["accounting"]["actual_calls"].append(wrong["accounting"]["actual_calls"][0])
    with pytest.raises(ValueError, match="twice"):
        build_report(frozen, [wrong], panel_sha256=SHA)


def test_no_observation_report_and_wilson_boundary():
    result = build_report(panel(), [], panel_sha256=SHA)
    assert result["inventory"]["state_counts"] == {"not_started": 280}
    assert result["main"]["completion_rate"] is None
    assert result["main"]["identification_bounds"] == [0, 1]
    assert Counter(result["repeat_diagnostic"]["success_count_histogram"].values()) == {0: 4}
    assert wilson95(0, 200)[0] == 0
    assert wilson95(200, 200)[1] == 1
    with pytest.raises(ValueError):
        wilson95(1, 0)


def test_file_loader_binds_plan_and_rejects_mixed_configurations(tmp_path):
    frozen = panel()
    plan = tmp_path / "plan.json"
    plan.write_bytes(canonical_bytes({"panel_ref": {"sha256": SHA}, "configuration": "frozen"}))
    reference = {"path": str(plan), "sha256": sha256(plan.read_bytes())}
    worker = tmp_path / "workers" / "one"
    worker.mkdir(parents=True)
    row = observation(frozen["slots"][0], 1)
    row["source_plan"] = reference
    (worker / "report.json").write_bytes(canonical_bytes(row))
    (worker / "model-entered.json").write_bytes(canonical_bytes({
        "row": frozen["slots"][0], "source_plan": reference}))
    observations, started = load_observations(tmp_path / "workers", panel_sha256=SHA)
    assert len(observations) == 1 and started == {"s0"}
    result = build_report(frozen, observations, panel_sha256=SHA, started_slot_ids=started)
    assert result["run_plan_sha256"] == reference["sha256"]
    second_plan = tmp_path / "changed-plan.json"
    second_plan.write_bytes(canonical_bytes({"panel_ref": {"sha256": SHA}, "configuration": "changed"}))
    second = tmp_path / "workers" / "two"
    second.mkdir()
    row = observation(frozen["slots"][1], 1)
    row["source_plan"] = {"path": str(second_plan), "sha256": sha256(second_plan.read_bytes())}
    (second / "report.json").write_bytes(canonical_bytes(row))
    with pytest.raises(ValueError, match="separately"):
        load_observations(tmp_path / "workers", panel_sha256=SHA)


def test_host_preentry_technical_unknown_is_not_unstarted_or_zero_cost(tmp_path):
    frozen = panel()
    plan = tmp_path / "plan.json"
    plan.write_bytes(canonical_bytes({"panel_ref": {"sha256": SHA}}))
    reference = {"path": str(plan), "sha256": sha256(plan.read_bytes())}
    root = tmp_path / "workers"
    root.mkdir()
    state = {"plan_ref": reference, "slots": [{
        **frozen["slots"][0], "status": "technical_unknown",
        "failure_type": "worker_technical_unknown_or_unclosed",
        "attempts": [{"path": str(root / "missing"), "model_entered": False,
                      "ended_at": 2, "exit_code": 1}],
    }]}
    observations, started = load_observations(
        root, panel_sha256=SHA, host_state=state, panel_rows=frozen["slots"])
    result = build_report(frozen, observations, panel_sha256=SHA, started_slot_ids=started)
    assert result["inventory"]["state_counts"] == {"not_started": 279, "technical_unknown": 1}
    assert result["episodes"][0]["tokens"]["known_actual_tokens"] is None
    assert result["tokens"]["all_280_slots"]["complete_observed_actual_tokens"] is None
    assert result["main"]["failures"] == 0 and result["main"]["unknown"] == 200


def test_host_killed_worker_recovers_only_bound_provider_usage_and_reservation(tmp_path):
    frozen = panel()
    plan = tmp_path / "plan.json"
    plan.write_bytes(canonical_bytes({"panel_ref": {"sha256": SHA}}))
    reference = {"path": str(plan), "sha256": sha256(plan.read_bytes())}
    root = tmp_path / "workers"
    attempt = root / "killed"
    calls = attempt / "resident/calls"
    calls.mkdir(parents=True)
    identity = {"model": "synthetic"}
    native_input = {"input_ids": [1, 2], "prompt_tokens": 2}
    for key in ("generation_a", "generation_b"):
        prepared = {"attempt_id": key, "actor_identity": identity,
                    "online_window_id": "software-panel-v053:s0",
                    "native_input": native_input, "generation_started": False,
                    "reserved_maximum_tokens": 5}
        (calls / (key + "-prepared.json")).write_bytes(canonical_bytes(prepared))
        (calls / (key + "-started.json")).write_bytes(canonical_bytes({
            **prepared, "generation_started": True}))
    (calls / "generation_a-complete.json").write_bytes(canonical_bytes({
        "attempt_id": "generation_a", "actor_identity": identity,
        "input": native_input, "output_ids": [3],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
    }))
    state = {"plan_ref": reference, "slots": [{
        **frozen["slots"][0], "status": "technical_unknown", "failure_type": "generation_deadline",
        "attempts": [{"path": str(attempt), "model_entered": True, "ended_at": 2, "exit_code": -9}],
    }]}
    observations, started = load_observations(
        root, panel_sha256=SHA, host_state=state, panel_rows=frozen["slots"])
    result = build_report(frozen, observations, panel_sha256=SHA, started_slot_ids=started)
    tokens = result["tokens"]["all_280_slots"]
    assert tokens["known_actual_tokens"] == 3
    assert tokens["known_uncertain_reservation_tokens"] == 5
    assert tokens["complete_observed_actual_tokens"] is None
    assert result["episodes"][0]["R_code"] is None
    assert len(result["episodes"][0]["accounting_recovery"]["references"]) == 5
    # The same raw receipts must not be attributed to a different frozen slot.
    state["slots"][0].update(frozen["slots"][1])
    observations, _ = load_observations(
        root, panel_sha256=SHA, host_state=state, panel_rows=frozen["slots"])
    assert observations[0]["accounting"] is None
