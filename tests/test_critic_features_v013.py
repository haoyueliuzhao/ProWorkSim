"""Real WorldCore observations plus finite critic prefix/shape controls."""

import copy

import pytest

from proworksim.critic_features import FEATURE_VERSION, feature_names, past_features
from scripts.world_core_experiment import (
    ACTORS,
    bootstrap,
    create_report,
    install,
    mustcall,
    package,
)


def observed_event(payload, sequence=0, member="alice"):
    return {
        "sequence": sequence,
        "kind": "public_observation",
        "worker_id": member,
        "payload": payload,
    }


def test_actual_world_progress_and_review_have_distinct_critic_channels(tmp_path):
    world = bootstrap(tmp_path / "world")
    install(world, package("A"))
    alice = world.session("alice", "A")
    create_report(alice)
    opening = alice.observe()
    mustcall(
        alice, "write_object", alias="report", data={"revenue": 11, "cost": 4}, work_id="work-1"
    )
    progress = alice.observe()
    sub = mustcall(alice, "submit", work_id="work-1", artifacts=["report"])
    review = alice.observe()
    mustcall(
        world.session("bob", "A"), "approve", work_id="work-1", submission_id=sub["submission_id"]
    )
    accepted = alice.observe()
    vectors = {}
    for expected, obs in [
        ("open", opening),
        ("in_progress", progress),
        ("in_review", review),
        ("accepted", accepted),
    ]:
        assert obs["work_items"]["A::work-1"]["status"] == expected
        values, proof = past_features([observed_event(obs)], 1, "alice", ACTORS)
        assert len(values) == 30 and proof["version"] == FEATURE_VERSION
        index = feature_names(ACTORS).index("alice.work_status_" + expected)
        assert values[index] == 0.1
        assert values[9:27] == [0.0] * 18
        assert proof["members_without_past_observation"] == ["bob", "manager"]
        vectors[expected] = values
    assert vectors["in_progress"] != vectors["in_review"]
    assert vectors["open"] != vectors["accepted"]


def test_future_truth_and_unseen_business_values_cannot_change_prefix_features():
    obs = {
        "work_items": {"a": {"status": "in_review", "goal": "private business text"}},
        "workspaces": {"P": {"report": "object"}},
    }
    prefix = [
        observed_event(obs),
        {
            "sequence": 1,
            "kind": "tool_call",
            "worker_id": "alice",
            "payload": {"action": "read_version", "response": {"ok": False}},
        },
    ]
    value, proof = past_features(prefix, 2, "alice", ACTORS)
    changed = copy.deepcopy(prefix)
    changed[0]["payload"]["work_items"]["a"]["goal"] = "unrelated value 99999"
    changed += [
        observed_event({"work_items": {"hidden": {"status": "not-a-valid-future-status"}}}, 2),
        {"sequence": 3, "kind": "evaluation", "payload": {"reward": 1}},
    ]
    assert past_features(changed, 2, "alice", ACTORS) == (value, proof)
    assert value[8] == 0.01
    assert proof["latest_observation_sequences"] == {"alice": 0}


def test_unknown_status_is_not_silently_renamed_or_encoded_as_zero():
    with pytest.raises(ValueError, match="Unknown public work status"):
        past_features(
            [observed_event({"work_items": {"work": {"status": "active"}}})], 1, "alice", ACTORS
        )
    values, proof = past_features(
        [observed_event({"work_items": {"work": {"status": "revision_required"}}})],
        1,
        "alice",
        ACTORS,
    )
    assert values[:6] == [0.1, 0, 0, 0, 0, 0]
    assert proof["recognized_unbinned_work_status_counts"]["alice"] == {"revision_required": 1}


def test_fixed_three_member_schema_and_no_observation_actor_blocks():
    values, proof = past_features([], 0, "implementer")
    assert values == [0.0] * 27 + [0.0, 1.0, 0.0]
    assert len(proof["feature_names"]) == 30
    with pytest.raises(ValueError, match="three distinct"):
        past_features([], 0, "only", ["only"])
    with pytest.raises(ValueError, match="acting member"):
        past_features([], 0, "rule-prefix")
