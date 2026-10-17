"""Finite synthetic report controls; no benchmark, candidate or model execution."""
import copy
import json
from pathlib import Path

import pytest

from scripts import software_calibration_v051_report as report


PROMPTS = [337, 441, 273, 369, 570, 455, 424, 661, 412, 458, 609, 692,
           412, 537, 490, 536, 587, 647, 1034, 785, 715, 611, 889, 860]


def metric_rows():
    return [{"ordinal": i, "task_id": f"task-{i}", "seed": 202610170511 + i,
             "arm": arm, "pass_at_1": int(i < (17 if arm == "reference" else 18)),
             "status": "passed" if i < (17 if arm == "reference" else 18) else "official_incorrect"}
            for i in range(24) for arm in report.ARMS]


def test_complete_fixed_panel_reports_one_pair_net_step():
    metrics, pairs = report.outcome_summary(metric_rows())
    assert metrics["reference"]["pass_at_1"] == 17 / 24
    assert metrics["project"]["pass_at_1"] == 18 / 24
    assert metrics["project_minus_reference"]["value"] == pytest.approx(1 / 24)
    assert sum(p["classification"] == "project_only_pass" for p in pairs) == 1


def test_one_unknown_never_uses_twenty_three_as_denominator():
    rows = metric_rows()
    rows[1].update(pass_at_1=None, status="technical_unknown")
    metrics, pairs = report.outcome_summary(rows)
    assert metrics["reference"]["pass_at_1"] == 17 / 24
    assert metrics["project"]["pass_at_1"] is None
    assert metrics["project"]["pass_at_1_bounds"] == [17 / 24, 18 / 24]
    assert metrics["project"]["known_outcomes"] == 23
    assert metrics["project_minus_reference"]["value"] is None
    assert pairs[0]["classification"] == "unresolved"


def test_unstarted_inventory_has_bounds_but_no_zero_score():
    rows = metric_rows()
    for row in rows:
        row.update(pass_at_1=None, status="not_started")
    metrics, _ = report.outcome_summary(rows)
    for arm in report.ARMS:
        assert metrics[arm]["pass_at_1"] is None
        assert metrics[arm]["not_started"] == 24
        assert metrics[arm]["technical_unknown"] == 0
        assert metrics[arm]["pass_at_1_bounds"] == [0, 1]
    assert metrics["project_minus_reference"]["bounds"] == [-1, 1]


def test_unknown_scoring_does_not_create_unknown_generation_fee():
    rows = [{"attempted": True, "actual_tokens": 13, "maximum_tokens": 100,
             "pass_at_1": None},
            {"attempted": True, "actual_tokens": None, "maximum_tokens": 101,
             "pass_at_1": None},
            *[{"attempted": False, "actual_tokens": None, "maximum_tokens": 102,
               "pass_at_1": None} for _ in range(46)]]
    value = report.generation_ledger(rows)
    assert value["known_actual_tokens"] == 13
    assert value["uncertain_reservation_tokens"] == 101
    assert value["ledger_tokens"] == 114
    assert value["complete_actual_tokens"] is None
    assert value["unstarted_slots"] == 46


def test_unique_worker_cost_includes_resource_failure_once(tmp_path):
    a = {"output": str(tmp_path / "attempt-1"), "started_at": 10, "ended_at": 14,
         "seconds": 4, "exit_code": 75, "report": {"status": "pre_model_resource_unavailable"}}
    b = {"output": str(tmp_path / "attempt-2"), "started_at": 20, "ended_at": 30,
         "seconds": 10, "exit_code": 0, "report": {"status": "complete",
                                                     "nested_generation_seconds": 8}}
    value = report.worker_cost({"shard-0": {"attempts": [a, b]},
                                "duplicate": {"attempts": [copy.deepcopy(a)]}})
    assert value["unique_attempts"] == 2
    assert value["gpu_worker_seconds"] == 14
    assert value["issues"][0]["kind"] == "duplicate_worker_attempt_reference"


def test_active_or_unclosed_state_cannot_be_called_final(tmp_path):
    with pytest.raises(ValueError, match="terminal"):
        report._require_final({"status": "running", "states": {}})
    with pytest.raises(ValueError, match="not closed"):
        report.worker_cost({"shard-0": {"attempts": [{"output": str(tmp_path)}]}})


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(report.json_bytes(value))
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": report.sha(path.read_bytes())}


def fake_final(tmp_path):
    """A small disk fixture with the real48-slot shape, no experimental output."""
    cases, task_rows, slots = [], [], []
    for i, count in enumerate(PROMPTS):
        case = {"ordinal": i, "task_id": f"synthetic-task-{i}", "input_ids": [10] * count,
                "rendered_prompt": "synthetic prompt", "evaluation_sample": {
                    "input_output": json.dumps({"inputs": [""], "outputs": ["1"], "fn_name": None})}}
        cases.append(case)
        task_rows.append({"ordinal": i, "task_id": case["task_id"],
                          "difficulty": "easy", "contest_date": "2025-02-01"})
        arms = report.ARMS if i % 2 == 0 else tuple(reversed(report.ARMS))
        for arm in arms:
            slots.append({"slot_id": f"cal1-{i + 1:02d}-{arm}", "task_id": case["task_id"],
                "ordinal": i, "seed": 202610170511 + i, "arm": arm, "worker": f"shard-{i // 6}",
                "prompt_tokens": count, "maximum_tokens": count + 81920})
    group = write(tmp_path / "group-correction.json", {"new_model_calls": 0, "preserved": True})
    upstream = {path: "f" * 64 for path in report.GRADER_FILES}
    lock = {"tasks": task_rows, "scoring": {"upstream_files": [
        {"path": path, "sha256": value} for path, value in upstream.items()]},
        "artifacts": {"scoring_process_group_correction": group}}
    evidence = []
    for suffix in ("software-calibration-v051-source-lock.json", "source-preparation-control.json",
                   "scoring-control-summary.json", "runtime-controls-summary.json",
                   "runtime-sampling-cpu-controls.json", "host-controls.json",
                   "loading-info-incremental-control.json", "stop-policy-correction.json"):
        reference = write(tmp_path / "evidence" / suffix,
                          lock if "source-lock" in suffix else {"new_model_calls": 0})
        evidence.append({"frozen_copy": reference})
    plan = {"version": "software-calibration-host-v0.51", "evidence": evidence,
            "rows": slots, "maximum_actual_tokens": 3959768,
            "cases": write(tmp_path / "cases.json", cases),
            "model_manifest": write(tmp_path / "raw-model-manifest.json", {"fixture": True}),
            "contract": {"max_output_tokens": 81920, "eos_token_ids": [248044, 248046],
                         "max_generation_seconds": 7200}, "limits": {},
            "source_commit": {"code_commit": "synthetic-no-model-fixture"}}
    plan["sha256"] = report.sha(report.json_bytes(plan))
    plan_ref = write(tmp_path / "plan.json", plan)
    states = {}
    for i in range(4):
        worker = f"shard-{i}"
        output = tmp_path / worker / "attempt-001"
        own = [row["slot_id"] for row in slots if row["worker"] == worker]
        worker_report = {"status": "complete", "completed_slots": own,
                         "guard": {"passed": True}, "source_plan": plan_ref}
        write(output / "report.json", worker_report)
        write(output / "task.json", {"kind": "boundary", "started_at": 199})
        states[worker] = {"status": "complete", "attempts": [{
            "output": str(output), "pid": 1000 + i, "gpu": {"index": i},
            "started_at": 100, "ended_at": 200, "seconds": 100,
            "report": worker_report, "exit_code": 0, "reason": None}]}
    for row in slots:
        case = cases[row["ordinal"]]
        native = {"input_ids": case["input_ids"], "rendered_prompt": case["rendered_prompt"]}
        native["sha256"] = report.sha(report.json_bytes(native))
        directory = tmp_path / "slots" / row["slot_id"]
        native_ref = write(directory / "native-input.json", native)
        write(directory / "started.json", {"row": row, "native_input": native_ref,
              "pid": 1000 + row["ordinal"] // 6, "started_at": 110 + row["ordinal"]})
        raw, code = "```python\nprint(1)\n```", "print(1)"
        generation = {"path": row["arm"], "input": native, "output_ids": [248046],
            "usage": {"prompt_tokens": row["prompt_tokens"], "completion_tokens": 1,
                      "total_tokens": row["prompt_tokens"] + 1},
            "actor_identity": {"raw_release": True, "trained_adapter_loaded": False,
                               "checkpoint": None, "base_manifest": plan["model_manifest"]},
            "finish_reason": "stop", "seconds": .5, "raw_generated_text": raw,
            "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0}
        write(directory / "generation.json", generation)
        value = 0 if row["ordinal"] == 0 and row["arm"] == "project" else 1
        grade = {"status": "passed" if value else "official_incorrect", "pass_at_1": value,
            "evaluation_sample_sha256": report.sha(report.canonical_bytes(case["evaluation_sample"])),
            "per_test_seconds": 6, "grading_attempts": 1, "candidate_generations_added": 0,
            "upstream": {"revision": report.UPSTREAM_REVISION, "files": upstream},
            "code_sha256": report.sha(code.encode()), "raw_output_sha256": report.sha(raw.encode()),
            "official_test_count": 1, "official_reply": {"results": [True] if value else [-2],
                "metadata": {} if value else {"error_code": -2, "error_message": "Wrong Answer"}},
            "sandbox": {"fixture": True}, "returncode": 0,
            "host_wall_timeout": False, "output_truncated": False, "extraction_empty": False}
        write(directory / "grade/result.json", grade)
        (directory / "grade/extracted-code.py").write_text(code)
    known = 2 * sum(PROMPTS) + 48
    supervisor = {"status": "complete", "ended_at": 201, "states": states,
        "plan": plan_ref, "gpu_worker_seconds": 400,
        "ledger": {"complete_generations": 48, "started_generations": 48,
                   "known_actual_tokens": known, "uncertain_reservation_tokens": 0,
                   "complete_actual_tokens": known, "ledger_tokens": known}}
    write(tmp_path / "supervisor.json", supervisor)
    return tmp_path


@pytest.mark.parametrize("variant", ["complete", "missing_grade", "wrong_sample_binding"])
def test_disk_aggregation_preserves_unknown_and_original_records(tmp_path, variant):
    root = fake_final(tmp_path)
    path = root / "slots/cal1-02-project/grade/result.json"
    if variant == "missing_grade":
        path.unlink()
    elif variant == "wrong_sample_binding":
        value = json.loads(path.read_text())
        value["evaluation_sample_sha256"] = "not-the-frozen-sample"
        write(path, value)
    before = {str(p): report.sha(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
    value = report.build_report(root)
    after = {str(p): report.sha(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert value["billing"]["known_actual_tokens"] == 27656
    assert value["billing"]["complete_actual_tokens"] == 27656
    assert value["worker_cost"]["gpu_worker_seconds"] == 400
    assert value["metrics"]["reference"]["pass_at_1"] == 1
    if variant == "complete":
        assert value["metrics"]["project"]["pass_at_1"] == 23 / 24
        assert value["source_and_measurement_integrity"] is True
    else:
        assert value["metrics"]["project"]["pass_at_1"] is None
        assert value["metrics"]["project"]["pass_at_1_bounds"] == [22 / 24, 23 / 24]
        assert value["metrics"]["project_minus_reference"]["value"] is None
        row = next(r for r in value["rows"] if r["slot_id"] == "cal1-02-project")
        assert row["status"] == "technical_unknown"
        if variant == "wrong_sample_binding":
            assert row["original_grade_pass_at_1"] == 1
            assert row["pass_at_1"] is None
    assert value["new_scoring_calls"] == value["new_model_calls"] == 0
    assert "全48槽附表" in report.markdown(value)


def test_missing_worker_guard_preserves_original_grade_and_known_cost(tmp_path):
    root = fake_final(tmp_path)
    path = root / "supervisor.json"
    supervisor = json.loads(path.read_text())
    attempt = supervisor["states"]["shard-0"]["attempts"][0]
    del attempt["report"]["guard"]
    attempt["report"]["status"] = "paused_before_final_guard"
    supervisor["states"]["shard-0"]["status"] = "stopped"
    supervisor["status"] = "paused"
    write(Path(attempt["output"]) / "report.json", attempt["report"])
    write(path, supervisor)
    result = report.build_report(root)
    assert result["billing"]["complete_actual_tokens"] == 27656
    assert result["metrics"]["reference"]["pass_at_1"] is None
    assert result["metrics"]["project"]["pass_at_1"] is None
    assert result["metrics"]["project_minus_reference"]["value"] is None
    row = next(r for r in result["rows"] if r["slot_id"] == "cal1-01-reference")
    assert row["original_grade_pass_at_1"] == 1
    assert row["pass_at_1"] is None
    assert "worker_final_readonly_guard_known_passed" in row["binding_issues"]


def test_explicit_gpu5_relinquishment_keeps_external_cause(tmp_path):
    write(tmp_path / "gpu5-relinquishment.json", {
        "kind": "explicit_user_gpu_relinquishment", "requested_gpu": 5,
        "pid": 123, "reason": "User instruction: 让渡GPU5", "at": 50,
        "restart_or_resample_authorized": False,
        "release_observation": {"worker_process_exists": False}})
    costs = {"attempts": [{"pid": 123, "gpu_index": 5, "output": "original-attempt",
                           "host_stop_reason": "original-host-name"}]}
    result = report.external_interventions(report.Reader(), tmp_path, costs)
    assert result[0]["classification"] == "explicit_user_resource_relinquishment"
    assert result[0]["worker_binding_known"] is True
    assert result[0]["restart_or_resample_authorized"] is False
    assert costs["attempts"][0]["host_stop_reason"] == "original-host-name"
