"""Readable fixed boundaries, canonical diagnostics and later-world separation."""

import copy
import json
import shutil
from pathlib import Path

import pytest

from proworksim.episode import assess_historical_episode, begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder
from proworksim.rewards import REWARD_VERSION, episode_reward
from proworksim.scenarios import bind_runtime, build_scenario, load_scenario, run_scenario


@pytest.fixture(scope="module")
def actual_boundaries(tmp_path_factory):
    from scripts.episode_boundary_experiment_v011 import run

    root = tmp_path_factory.mktemp("episode-evidence") / "run"
    result = run(root)
    assert result["passed"], result["checks"]
    return root, result


def test_condition_scope_uses_canonical_field_in_real_sessions(tmp_path):
    from scripts.condition_scope_experiment_v011 import run

    result = run(tmp_path / "condition")
    assert result["passed"], result["checks"]


def test_real_s1_s2_and_empty_episode_remain_fixed(actual_boundaries):
    _, result = actual_boundaries
    assert result["passed_checks"] == result["total_checks"] == 14


def test_episode_end_bytes_tampering_does_not_become_worker_zero(actual_boundaries, tmp_path):
    root, _ = actual_boundaries
    target = tmp_path / "archive"
    shutil.copytree(root / "E1", target)
    manifest = json.loads((target / "manifest.json").read_text())
    entry = manifest["end"]["files"][0]
    (target / "end" / entry["path"]).write_bytes(b"changed after boundary")
    result = assess_historical_episode(target)
    assert result["assessment_execution"]["status"] == "source_unavailable"
    reward = episode_reward(
        result,
        {
            "version": REWARD_VERSION,
            "reward_id": "quality",
            "objectives": [{"kind": "content", "work_id": "REPORT::research"}],
        },
    )
    assert reward["eligible"] is False and reward["reward"] is None


def test_later_event_history_cannot_be_appended_to_closed_episode(actual_boundaries, tmp_path):
    root, _ = actual_boundaries
    target = tmp_path / "archive"
    shutil.copytree(root / "E1", target)
    path = target / "experience.json"
    value = json.loads(path.read_text())
    value["events"].append(
        {"sequence": len(value["events"]), "kind": "fabricated-later-success", "payload": {}}
    )
    path.write_text(json.dumps(value))
    assert (
        assess_historical_episode(target)["assessment_execution"]["status"] == "source_unavailable"
    )


def test_empty_wrong_correct_reward_denominators_differ(actual_boundaries):
    _, result = actual_boundaries
    spec = {
        "version": REWARD_VERSION,
        "reward_id": "quality",
        "objectives": [{"kind": "content", "work_id": "REPORT::research"}],
    }
    rewards = [
        episode_reward(result["assessments"][key], spec) for key in ("E0_after", "E1_after", "E2")
    ]
    assert [row["reward"] for row in rewards] == [0, 0, 1]
    assert all(row["eligible"] for row in rewards)


def test_unknown_goal_is_excluded_not_filtered_worker_failure(actual_boundaries):
    root, _ = actual_boundaries
    assessment = assess_historical_episode(
        root / "E2",
        independent_targets=[
            {"target_id": "unobserved", "work_id": "REPORT::research", "availability": "unknown"}
        ],
    )
    reward = episode_reward(
        assessment,
        {
            "version": REWARD_VERSION,
            "reward_id": "unknown",
            "objectives": [{"kind": "independent_target", "target_id": "unobserved"}],
        },
    )
    assert not reward["eligible"] and reward["reward"] is None


def test_current_progress_report_is_not_an_episode_reward(actual_boundaries):
    _, result = actual_boundaries
    value = episode_reward(
        result["assessments"]["current_progress"],
        {
            "version": REWARD_VERSION,
            "reward_id": "quality",
            "objectives": [{"kind": "content", "work_id": "REPORT::research"}],
        },
    )
    assert not value["eligible"] and value["reward"] is None


def test_maintenance_head_selected_once_with_predecessors_retained(tmp_path):
    spec = load_scenario(
        Path(__file__).resolve().parents[1] / "examples/scenarios-v10/chain-accepted.json"
    )
    deployment = build_scenario(spec, tmp_path / "world")
    runtime = bind_runtime(deployment)
    nodes = ["FINANCE::reconcile", "REPORT::research"]
    begin_episode(
        deployment.world,
        tmp_path / "episode",
        experience=runtime.recorder.snapshot(),
        work_ids=nodes,
        work_nodes=nodes,
        scenario=spec,
        policies={"kind": "actual rules"},
    )
    outcome = run_scenario(deployment, runtime)
    assert outcome["status"] == "completed", outcome["status"]
    manifest = finish_episode(
        deployment.world,
        tmp_path / "episode",
        experience=runtime.recorder.snapshot(),
        termination={"status": outcome["status"]},
    )
    assert len(manifest["selected_work_ids"]) == 2
    assert all("@m-" in wid for wid in manifest["selected_work_ids"])
    assert set(manifest["prior_node_obligations"]) == set(nodes)
    assert all(row["status"] == "accepted" for row in manifest["prior_node_obligations"].values())
    assessment = assess_historical_episode(tmp_path / "episode")
    assert {row["work_id"] for row in assessment["content_quality"]["submissions"]} == set(
        manifest["selected_work_ids"]
    )


def test_empty_experience_prefix_cannot_be_replaced_after_begin(actual_boundaries, tmp_path):
    from proworksim.world_core import WorldCore

    root, _ = actual_boundaries
    world = WorldCore(root / "world")
    recorder = ExperienceRecorder()
    recorder.record("original", {})
    begin_episode(
        world,
        tmp_path / "episode",
        experience=recorder.snapshot(),
        work_ids=["REPORT::research"],
        scenario={},
        policies={},
    )
    bad = copy.deepcopy(recorder.snapshot())
    bad["events"][0]["kind"] = "replacement"
    with pytest.raises(ValueError, match="prefix"):
        finish_episode(
            world, tmp_path / "episode", experience=bad, termination={"status": "budget_exhausted"}
        )


@pytest.mark.parametrize(
    "status,eligible,reward",
    [("model_service_error", False, None), ("model_format_error", True, 0), ("wait", True, 0)],
)
def test_model_boundary_and_waiting_reward_have_explicit_denominators(
    tmp_path, status, eligible, reward
):
    from proworksim.staff_runtime import PolicyBoundaryError, StaffRuntime

    spec = load_scenario(
        Path(__file__).resolve().parents[1] / "examples/scenarios-v10/report-direct.json"
    )
    deployment = build_scenario(spec, tmp_path / "world")

    class DeclaredOfflineBoundaryPolicy:
        config = {"kind": "offline_boundary_control", "status": status}

        def decide(self, context):
            if status == "wait":
                return {"kind": "wait", "memory": {}, "reason": "Declared always-wait fault policy"}
            raise PolicyBoundaryError(
                status, "Offline adapter boundary fixture; no HTTP request", memory={}
            )

    runtime = StaffRuntime(
        {"author": deployment.world.session("author", "REPORT")},
        {"author": DeclaredOfflineBoundaryPolicy()},
    )
    begin_episode(
        deployment.world,
        tmp_path / "episode",
        experience=runtime.recorder.snapshot(),
        work_ids=["REPORT::research"],
        scenario=spec,
        policies={"author": DeclaredOfflineBoundaryPolicy.config},
    )
    result = runtime.run(max_actions=1, max_opportunities=1)
    finish_episode(
        deployment.world,
        tmp_path / "episode",
        experience=runtime.recorder.snapshot(),
        termination={"status": result["status"]},
    )
    diagnostic = assess_historical_episode(tmp_path / "episode")
    scored = episode_reward(
        diagnostic,
        {
            "version": REWARD_VERSION,
            "reward_id": "attempt",
            "objectives": [{"kind": "content", "work_id": "REPORT::research"}],
            "cost": {"per_tool_call": 0.01, "max_penalty": 1},
        },
    )
    assert scored["eligible"] is eligible and scored["reward"] == reward


def test_preexisting_good_submission_cannot_reward_an_idle_new_episode(actual_boundaries, tmp_path):
    from proworksim.world_core import WorldCore

    root, _ = actual_boundaries
    world = WorldCore(root / "world")
    recorder = ExperienceRecorder()
    begin_episode(
        world,
        tmp_path / "episode",
        experience=recorder.snapshot(),
        work_ids=["REPORT::research"],
        scenario={},
        policies={},
    )
    finish_episode(
        world,
        tmp_path / "episode",
        experience=recorder.snapshot(),
        termination={"status": "worker_waiting"},
    )
    diagnostic = assess_historical_episode(tmp_path / "episode")
    scored = episode_reward(
        diagnostic,
        {
            "version": REWARD_VERSION,
            "reward_id": "idle",
            "objectives": [{"kind": "content", "work_id": "REPORT::research"}],
        },
    )
    assert scored["eligible"] is False and scored["reward"] is None
    assert scored["components"][0]["reason"].startswith("Passed fixed submission predates")


def test_missing_declared_adoption_gate_is_zero_without_inventing_content_verdict(tmp_path):
    from proworksim.experience import capture_port
    from proworksim.templates.research_review import package
    from proworksim.workers.research_review import _fact, _sentence

    spec = load_scenario(
        Path(__file__).resolve().parents[1] / "examples/scenarios-v10/report-direct.json"
    )
    config = package()
    config["works"][0]["visible_requirements"] = [
        "Adopt the exact dataset source for this work before submitting the report."
    ]
    spec["projects"] = [{"package": config}]
    deployment = build_scenario(spec, tmp_path / "world")
    world = deployment.world
    recorder = ExperienceRecorder()
    begin_episode(
        world,
        tmp_path / "episode",
        experience=recorder.snapshot(),
        work_ids=["REPORT::research"],
        work_nodes=["REPORT::research"],
        scenario=spec,
        policies={"fault": "omit declared source adoption"},
    )
    captures = []
    port = capture_port(world.session("author", "REPORT"), captures)
    observation = port.observe()
    contract = observation["work_items"]["REPORT::research"]["deliverable_contract"][
        "content_checks"
    ][0]
    source = port.call("read_object", alias="dataset", version_id="v1", work_id="REPORT::research")[
        "result"
    ]
    data = port.call("read_object", alias="report", work_id="REPORT::research")["result"]["data"]
    for claim in contract["claims"]:
        fact = _fact(claim, source["data"])
        data["report"]["sections"].append(
            {
                "section_id": claim["section_id"],
                "body": _sentence(claim, fact, "prose"),
                "claims": [fact],
            }
        )
    ref = {"object_id": source["reference"]["artifact_id"], "version_id": "v1"}
    data["sources"] = {"dataset": ref}
    assert port.call(
        "write_object", alias="report", data=data, dependencies=[ref], work_id="REPORT::research"
    )["ok"]
    assert port.call("submit", work_id="REPORT::research", artifacts=["report"])["ok"]
    for event in captures:
        recorder.record(event["kind"], event["payload"], worker_id="author")
    finish_episode(
        world,
        tmp_path / "episode",
        experience=recorder.snapshot(),
        termination={"status": "worker_waiting"},
    )
    gate = {
        "requirement_id": "declared-adoption",
        "kind": "required_source_adoption",
        "work_node": "REPORT::research",
        "aliases": ["dataset"],
    }
    diagnostic = assess_historical_episode(tmp_path / "episode", process_requirements=[gate])
    assert diagnostic["content_quality"]["submissions"][0]["evaluation"]["status"] == "unassessed"
    assert diagnostic["process_constraints"]["requirements"][0]["missing_aliases"] == ["dataset"]
    reward = episode_reward(
        diagnostic,
        {
            "version": REWARD_VERSION,
            "reward_id": "adoption-gated",
            "objectives": [{"kind": "content", "work_node": "REPORT::research"}],
            "process_requirements": ["declared-adoption"],
        },
    )
    assert reward["eligible"] and reward["reward"] == 0 and reward["components"][0]["score"] is None
    assert "unassessed_components" in reward
    # Subsequent actual adoption cannot fill a historical submission snapshot.
    assert port.call(
        "adopt",
        alias="dataset",
        object_id=ref["object_id"],
        version_id="v1",
        policy="fixed",
        work_ids=["REPORT::research"],
    )["ok"]
    assert (
        assess_historical_episode(tmp_path / "episode", process_requirements=[gate]) == diagnostic
    )


def test_unavailable_declared_source_gate_has_priority_over_empty_submission(tmp_path):
    from scripts.condition_scope_experiment_v011 import run
    from proworksim.world_core import WorldCore

    directory = tmp_path / "unavailable"
    run(directory)
    world = WorldCore(directory / "world")
    recorder = ExperienceRecorder()
    begin_episode(
        world,
        tmp_path / "episode",
        experience=recorder.snapshot(),
        work_ids=["P::reconcile"],
        scenario={},
        policies={},
    )
    finish_episode(
        world,
        tmp_path / "episode",
        experience=recorder.snapshot(),
        termination={"status": "world_blocked"},
    )
    gate = {
        "requirement_id": "declared-source",
        "kind": "required_source_adoption",
        "work_id": "P::reconcile",
        "aliases": ["statement"],
    }
    diagnostic = assess_historical_episode(tmp_path / "episode", process_requirements=[gate])
    assert diagnostic["process_constraints"]["status"] == "source_unavailable"
    reward = episode_reward(
        diagnostic,
        {
            "version": REWARD_VERSION,
            "reward_id": "unavailable-source",
            "objectives": [{"kind": "content", "work_id": "P::reconcile"}],
            "process_requirements": ["declared-source"],
        },
    )
    assert not reward["eligible"] and reward["reward"] is None
