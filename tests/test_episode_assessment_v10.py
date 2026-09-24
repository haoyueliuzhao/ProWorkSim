"""Institutional progress, finite quality and process evidence remain distinct."""

import copy

import pytest

from proworksim.evaluation import assess_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.scenarios import bind_runtime, build_scenario, load_scenario, run_scenario


@pytest.mark.parametrize(
    "case",
    [
        "upstream_wrong_downstream_faithful",
        "metadata_right_body_wrong",
        "reasonable_unknown",
        "evaluator_fault",
    ],
)
def test_actual_modular_episode_responsibilities(tmp_path, case):
    from scripts.episode_assessment_experiment import run_case

    report = run_case(case, tmp_path)
    assert report["construction_error"] is None, report["construction_error"]
    assert report["passed"], [row for row in report["checks"] if not row["passed"]]


@pytest.fixture
def report_world(tmp_path):
    from pathlib import Path

    spec = load_scenario(
        Path(__file__).resolve().parents[1] / "examples/scenarios-v10/report-direct.json"
    )
    deployment = build_scenario(spec, tmp_path / "world")
    assert deployment.status == "ready", deployment.diagnostics
    runtime = bind_runtime(deployment)
    result = run_scenario(deployment, runtime)
    assert result["status"] in {"completed", "boundary_reached"}
    return deployment.world, runtime.recorder


def test_real_refused_forbidden_attempt_is_not_completed_process_violation(report_world):
    world, recorder = report_world
    captured = []
    port = capture_port(world.session("author", "REPORT"), captured)
    work = world.store.load()["work_items"]["REPORT::research"]
    response = port.call(
        "approve",
        work_id="REPORT::research",
        submission_id=work["submissions"][-1]["submission_id"],
    )
    assert response["ok"] is False
    recorder.record("tool_call", captured[-1]["payload"], worker_id="unauthorized-probe")
    before = copy.deepcopy(world.store.load())
    value = assess_episode(
        world.store,
        before,
        recorder.snapshot(),
        process_requirements=[
            {
                "requirement_id": "no-formal-approval-by-probe",
                "kind": "forbid_successful_tool",
                "worker_ids": ["unauthorized-probe"],
                "actions": ["approve"],
            }
        ],
    )
    process = value["process_constraints"]
    assert process["status"] == "pass"
    assert process["requirements"][0]["rejected_attempt_sequences"]
    assert not process["requirements"][0]["violation_sequences"]
    assert value["runtime_problems"]["events"][-1]["kind"] == "tool_rejection"
    assert world.store.load() == before


def test_goal_missing_expected_is_unknown_but_declared_null_is_known(report_world):
    world, recorder = report_world
    state = world.store.load()
    base = {
        "target_id": "explicit-expected",
        "work_id": "REPORT::research",
        "path": ["report", "sections", 1, "claims", 0, "value"],
    }
    value = assess_episode(
        world.store,
        state,
        recorder.snapshot(),
        independent_targets=[base, {**base, "target_id": "known-null", "expected": None}],
    )
    unknown, known = value["independent_targets"]["targets"]
    assert unknown["status"] == "unassessed"
    assert known["status"] == "content_failure" and known["actual"] == 120
    assert known["expected"] is None


def test_no_declared_quality_target_or_process_is_fabricated_as_pass(report_world):
    world, recorder = report_world
    value = assess_episode(world.store, world.store.load(), recorder.snapshot())
    assert "passed" not in value
    assert value["institutional_progress"]["quality_claim"] == "none"
    assert value["independent_targets"]["status"] == "unassessed"
    assert value["process_constraints"]["status"] == "unassessed"
    assert value["content_quality"]["submissions"][0]["evaluation"]["status"] == "pass"


def test_incompatible_assessment_configuration_is_not_worker_arithmetic(report_world):
    world, recorder = report_world
    state = copy.deepcopy(world.store.load())
    value = assess_episode(
        world.store,
        state,
        recorder.snapshot(),
        independent_targets=[
            {
                "target_id": "bad-selector",
                "work_id": "REPORT::research",
                "path": [True],
                "expected": 0,
            }
        ],
    )
    assert value["assessment_execution"]["status"] == "evaluator_error"
    assert value["assessment_execution"]["boundary"] == "episode_assessment"
    assert world.store.load() == state


def test_declared_budget_event_remains_separate_from_accepted_content(report_world):
    world, _ = report_world
    recorder = ExperienceRecorder()
    recorder.record("scenario_boundary", {"status": "budget_exhausted", "actions": 0})
    value = assess_episode(world.store, world.store.load(), recorder.snapshot())
    assert value["runtime_problems"]["events"][0]["payload"]["status"] == "budget_exhausted"
    assert value["institutional_progress"]["works"][0]["status"] == "accepted"
    assert value["content_quality"]["submissions"][0]["evaluation"]["status"] == "pass"
