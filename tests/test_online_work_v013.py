"""Real short-scope work credit and boundaries; no target model training."""

import copy

import pytest

from proworksim.episode import begin_episode, finish_episode
from proworksim.online_rewards import _Evidence, assess_online_reward
from proworksim.templates.online_work import build_online_case, registry
from scripts.online_work_experiment_v013 import Witness, run_case


@pytest.mark.parametrize("task", ["implement", "review"])
def test_real_preparation_does_not_create_current_actor_reward(tmp_path, task):
    result = run_case(f"train-w0-{task}", tmp_path / task, control="no_actions")
    assert result["prefix_event_count"] > 0
    assert result["current_episode_excludes_prefix"] is True
    assert result["reward"]["eligible"] is True
    assert result["reward"]["reward"] == 0
    assert result["reward"]["completed"] is False


@pytest.mark.parametrize(
    "control,expected", [(None, 1.0), ("bad_approval", 0.25), ("wrong_location", 0.25)]
)
def test_review_decision_credit_requires_actual_correct_treatment(tmp_path, control, expected):
    result = run_case("train-w1-review", tmp_path / (control or "proper"), control=control)
    assert result["reward"]["eligible"] is True
    assert result["reward"]["reward"] == expected
    assert result["reward"]["work_components"]["basis"]["value"] is True
    assert result["reward"]["work_components"]["delivery"]["value"] is (control is None)


def test_replayed_preexisting_read_receipt_has_no_current_episode_credit(tmp_path):
    prepared = build_online_case("train-w0-handoff", tmp_path / "case")
    old = prepared.world.session("provider", "TEAM").call(
        "read_alias", alias="basis", work_id="TEAM::build", request_key="prior-read"
    )
    assert old["ok"]
    witness = Witness(prepared)
    episode = tmp_path / "episode"
    begin_episode(
        prepared.world,
        episode,
        experience=witness.recorder.snapshot(),
        work_ids=["TEAM::build"],
        scenario=prepared.scenario,
        policies={"provider": {"implementation": "explicit_rule_witness"}},
    )
    witness.call(
        "provider", "read_alias", alias="basis", work_id="TEAM::build", request_key="prior-read"
    )
    finish_episode(
        prepared.world,
        episode,
        experience=witness.recorder.snapshot(),
        termination={"status": "control"},
    )
    reward = assess_online_reward(episode, prepared.reward_spec)
    assert reward["eligible"] and reward["reward"] == 0
    assert reward["work_components"]["basis"]["value"] is False


def test_declared_scope_cannot_be_changed_after_episode(tmp_path):
    result = run_case("train-w0-handoff", tmp_path / "case", control="read_only")
    original = result["reward"]
    changed = copy.deepcopy(original["spec"])
    changed["reward_id"] += "-changed-afterward"
    invalid = assess_online_reward(tmp_path / "case/episode", changed)
    assert invalid["eligible"] is False and invalid["reward"] is None
    assert invalid["episode_id"] == original["episode_id"]
    assert invalid["manifest_sha256"] == original["manifest_sha256"]
    assert invalid["work_components"]["basis"]["value"] is None


def test_recorded_read_must_be_in_actual_consuming_model_input():
    # Explicit offline request/return fixture, not claimed as a model rollout.
    evidence = _Evidence.__new__(_Evidence)
    read = {"sequence": 1, "worker_id": "provider", "payload": {"model_call_id": "read-call"}}
    action = {"sequence": 5, "worker_id": "provider", "payload": {"model_call_id": "handoff-call"}}
    message = {"role": "tool", "content": "actual exact read result"}
    evidence.manifest = {"policies": {"provider": {"implementation": "ModelPolicy"}}}
    evidence.calls = [action]
    evidence.events = [
        {
            "sequence": 2,
            "kind": "model_tool_result",
            "worker_id": "provider",
            "payload": {"call_id": "read-call", "message": message},
        },
        {
            "sequence": 4,
            "kind": "model_attempt",
            "worker_id": "provider",
            "payload": {
                "call_id": "handoff-call",
                "stage": "finished",
                "status": "success",
                "request": {"messages": []},
            },
        },
    ]
    assert evidence.presented_to_consumer(read, 5) is False
    evidence.events[-1]["payload"]["request"]["messages"].append(message)
    assert evidence.presented_to_consumer(read, 5) is True
    evidence.events.pop()
    with pytest.raises(ValueError, match="unavailable"):
        evidence.presented_to_consumer(read, 5)


def test_fixed_internal_uses_do_not_claim_independent_source_splits():
    declared = registry()
    assert declared["independent_test_source_families"] == []
    assert {case["split"] for case in declared["situations"]} == {"development"}
    assert len({case["family"] for case in declared["situations"]}) == 1
    assert {case["usage"] for case in declared["situations"]} == {
        "online_train",
        "dev_check",
        "locked_within_family_check",
    }
    train = [case for case in declared["situations"] if case["usage"] == "online_train"]
    for window in range(2):
        cases = [case for case in train if case["window"] == window]
        assert [case["task"] for case in cases] == ["handoff", "implement", "review", "chain"]
        assert [case["case_share"] for case in cases] == [0.25] * 4
    assert len({case["facts_seed"] for case in declared["situations"]}) == len(
        declared["situations"]
    )


def test_renaming_a_legacy_read_does_not_forge_a_canonical_receipt(tmp_path):
    prepared = build_online_case("train-w0-handoff", tmp_path / "case")
    witness = Witness(prepared)
    episode = tmp_path / "episode"
    begin_episode(
        prepared.world,
        episode,
        experience=witness.recorder.snapshot(),
        work_ids=["TEAM::build"],
        scenario=prepared.scenario,
        policies={"provider": {"implementation": "explicit_rule_witness"}},
    )
    witness.call("provider", "read_object", alias="basis", work_id="TEAM::build")
    # Intentional offline corruption control, not a genuine canonical read.
    witness.recorder.events[-1]["payload"]["action"] = "read_alias"
    finish_episode(
        prepared.world,
        episode,
        experience=witness.recorder.snapshot(),
        termination={"status": "corruption_control"},
    )
    reward = assess_online_reward(episode, prepared.reward_spec)
    assert reward["eligible"] is False and reward["reward"] is None
    assert "receipt contract" in reward["exclusions"][0]["reason"]


def test_public_review_contract_does_not_expose_preparation_answer_label():
    from proworksim.templates.online_work import case_spec, scenario

    first = scenario(case_spec("train-w0-review"))
    second = scenario(case_spec("train-w1-review"))
    assert first["roles"] == second["roles"]
    assert first["variation"]["online_reward"] == second["variation"]["online_reward"]
    assert (
        first["projects"][0]["package"]["works"][0]["requirements"]["online_scope"]
        == second["projects"][0]["package"]["works"][0]["requirements"]["online_scope"]
    )


def test_late_reads_cannot_repair_an_already_unsupported_approval(tmp_path):
    from scripts.online_work_experiment_v013 import review

    prepared = build_online_case("train-w0-review", tmp_path / "case")
    witness = Witness(prepared)
    episode = tmp_path / "episode"
    begin_episode(
        prepared.world,
        episode,
        experience=witness.recorder.snapshot(),
        work_ids=["TEAM::build"],
        scenario=prepared.scenario,
        policies={"reviewer": {"implementation": "explicit_rule_witness"}},
    )
    public = witness.observe("reviewer")
    sid = public["work_items"]["TEAM::build"]["pending_submission_id"]
    witness.call("reviewer", "approve", work_id="TEAM::build", submission_id=sid)
    review(witness, judgment="read_only")
    finish_episode(
        prepared.world,
        episode,
        experience=witness.recorder.snapshot(),
        termination={"status": "read_after_approval_control"},
    )
    reward = assess_online_reward(episode, prepared.reward_spec)
    assert reward["eligible"] is True and reward["reward"] == 0
    assert reward["work_components"]["basis"]["value"] is False
    assert reward["work_components"]["delivery"]["value"] is False
