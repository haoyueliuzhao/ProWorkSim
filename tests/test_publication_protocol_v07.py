"""Publication fact protocol only; full session effects are integration experiments."""

import copy

import pytest

from proworksim.core.publication import (
    effective_policy,
    latest_published_version,
    publish_release,
    record_implicit_release,
)


def state_fixture():
    return {
        "actors": {"alice": {}, "bob": {}},
        "clock": 7,
        "publication_policy": "explicit",
        "projects": {
            "A": {"participants": ["alice", "bob"]},
            "B": {"participants": ["bob"]},
        },
        "workspaces": {"A": {"report": "object", "private": "upstream"}, "B": {}},
        "work_items": {
            "A::one": {"project_id": "A", "node_id": "A::one"},
            "A::two": {"project_id": "A", "node_id": "A::two"},
            "B::one": {"project_id": "B", "node_id": "B::one"},
        },
        "artifacts": {
            "object": {
                "project_id": "A",
                "writers": ["alice"],
                "readers": ["alice"],
                "versions": {"v1": {"logical_time": 1}, "v2": {"logical_time": 5}},
                "current_version": "v2",
            },
            "upstream": {
                "project_id": "A",
                "writers": ["alice"],
                "readers": ["alice"],
                "versions": {"v1": {"logical_time": 1}},
                "current_version": "v1",
            },
        },
        "organization": {
            "grants": [
                {
                    "actor_id": "alice",
                    "scope": "project",
                    "project_id": "A",
                    "power": "publish",
                    "subject": "artifact",
                    "object_ids": ["object"],
                    "work_nodes": ["A::one"],
                }
            ]
        },
        "shares": [],
        "messages": [],
        "adoptions": {},
        "releases": [],
    }


def publish(state, **updates):
    args = {
        "actor": "alice",
        "source_project": "A",
        "object_id": "object",
        "version_id": "v1",
        "target_projects": ["A", "B"],
        "work_ids": ["A::one"],
    }
    args.update(updates)
    return publish_release(state, **args)


def test_release_is_scoped_fact_not_read_grant_or_current_version_pointer():
    state = state_fixture()
    before = copy.deepcopy(state)
    assert latest_published_version(state, "object", "B") is None
    result = publish(state, target_projects=["B"])
    assert result["created"]
    assert latest_published_version(state, "object", "B") == "v1"
    assert latest_published_version(state, "object", "A") is None
    assert latest_published_version(state, "object", None) is None
    for key in state.keys() - {"releases"}:
        assert state[key] == before[key]
    assert result["release"]["actor_id"] == "alice"
    assert result["release"]["scope"] == {"target_projects": ["B"], "work_ids": ["A::one"]}
    result["release"]["scope"]["target_projects"].append("A")
    assert latest_published_version(state, "object", "A") is None


def test_exact_publication_retry_is_idempotent_without_new_notification_facts():
    state = state_fixture()
    first = publish(state, target_projects=["B", "A"])
    state["clock"] += 1
    replay = publish(state, target_projects=["A", "B", "A"])
    assert not replay["created"] and replay["release"] == first["release"]
    assert len(state["releases"]) == 1
    second = publish(state, version_id="v2", target_projects=["B"])
    assert second["created"] and len(state["releases"]) == 2
    assert latest_published_version(state, "object", "B") == "v2"
    assert latest_published_version(state, "object", "A") == "v1"


@pytest.mark.parametrize(
    "updates",
    [
        {"actor": "bob"},
        {"work_ids": None},
        {"work_ids": ["A::one", "A::two"]},
        {"object_id": "upstream"},
        {"source_project": "B"},
        {"work_ids": ["B::one"]},
        {"version_id": "v3"},
        {"target_projects": ["future"]},
    ],
)
def test_bad_scope_or_missing_power_has_no_partial_release(updates):
    state = state_fixture()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        publish(state, **updates)
    assert state == before


def test_policy_inheritance_is_explicit_and_does_not_synthesize_old_history():
    state = state_fixture()
    artifact = state["artifacts"]["object"]
    assert effective_policy(state, artifact) == "explicit"
    state["projects"]["A"]["publication_policy"] = "implicit_write"
    assert effective_policy(state, artifact) == "implicit_write"
    artifact["publication_policy"] = "explicit"
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        record_implicit_release(state, "alice", "A", "object", "v2", ["A"])
    assert state == before
    del artifact["publication_policy"]
    release = record_implicit_release(state, "alice", "A", "object", "v2", ["A"])
    assert release["created"] and release["release"]["policy"] == "implicit_write"
    # No explicit publish grant is required for a declared implicit-write policy.
    state["organization"]["grants"] = []
    assert not record_implicit_release(state, "alice", "A", "object", "v2", ["A"])["created"]
    with pytest.raises(ValueError):
        record_implicit_release(state, "bob", "A", "object", "v1", ["A"])
    del state["projects"]["A"]["publication_policy"]
    del state["publication_policy"]
    state["releases"] = []
    assert effective_policy(state, artifact) == "implicit_write"
    assert latest_published_version(state, "object", "A") is None
    assert state["releases"] == []


def test_world_object_publication_has_world_grant_and_no_future_project_scope():
    state = state_fixture()
    state["artifacts"]["object"]["project_id"] = None
    state["organization"]["grants"] = [
        {
            "actor_id": "alice",
            "scope": "world",
            "power": "publish",
            "subject": "artifact",
            "object_ids": ["object"],
            "work_nodes": ["*"],
        }
    ]
    result = publish(state, source_project=None, target_projects=[], work_ids=None)
    assert result["created"]
    assert latest_published_version(state, "object", None) == "v1"
    assert latest_published_version(state, "object", "A") is None


def test_explicit_world_writer_can_save_draft_without_publication_power(tmp_path):
    from proworksim.core.world import WorldSpec
    from proworksim.world_core import WorldCore

    world = WorldCore.create(
        tmp_path / "draft",
        WorldSpec(
            "draft",
            {"writer": {}},
            bootstrap_grants=[{"actor_id": "writer", "scope": "world", "power": "create_object"}],
        ),
    )
    worker = world.session("writer")
    created = worker.call("create_object", alias="draft", filename="draft.json", data={"value": 1})
    assert created["ok"]
    written = worker.call("write_object", alias="draft", data={"value": 2})
    assert written["ok"] and written["result"]["version_id"] == "v2"
    denied = worker.call("publish", alias="draft", version_id="v2", target_projects=[])
    assert not denied["ok"]
    assert world.store.load()["releases"] == []
    assert worker.call("read_object", alias="draft")["result"]["data"] == {"value": 2}
