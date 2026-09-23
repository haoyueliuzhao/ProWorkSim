"""Necessary regressions for World Core's package/runtime contract boundary.

Business setup and transitions use public bound sessions. Assertions inspect the
persisted world and role observations; they never fabricate a successful state.
"""

import copy

import pytest

from proworksim.core.adoption import binding_key
from proworksim.core.world import WorldSpec, object_identity
from proworksim.world_core import WorldCore
from scripts.world_core_experiment import (
    ACTORS,
    bootstrap,
    create_report,
    exact_ref,
    install,
    mustcall,
    package,
)


def material(alias, readers=None):
    return {
        "alias": alias,
        "filename": alias + ".json",
        "owner": "manager",
        "readers": list(ACTORS) if readers is None else readers,
        "data": {"evidence": alias},
    }


@pytest.mark.parametrize("reviewer_can_read", [False, True])
def test_required_credentials_control_submit_and_approve_observations(tmp_path, reviewer_can_read):
    world = bootstrap(tmp_path / "world")
    pkg = package("A")
    pkg["objects"] = [
        material("terms", list(ACTORS) if reviewer_can_read else ["alice", "manager"])
    ]
    install(world, pkg)
    alice, bob, manager = (world.session(actor, "A") for actor in ACTORS)
    create_report(alice)
    ref = {"object_id": object_identity("A", "terms"), "version_id": "v1"}
    replacement = mustcall(
        manager,
        "revise",
        work_id="work-1",
        updates={"required_credentials": [ref]},
        reason="Require the exact current work's formally confirmed terms",
    )["replacements"]["A::work-1"]
    assert "submit" not in alice.observe()["work_items"][replacement]["enabled_actions"]
    denied = alice.call("submit", work_id=replacement, artifacts=["report"])
    assert not denied["ok"]
    assert "Required credential is not applicable" in denied["error"]["message"]
    assert world.store.load()["work_items"][replacement]["submissions"] == []

    mustcall(
        manager,
        "confirm",
        work_id=replacement,
        alias="terms",
        dimension="requirements",
        purpose="delivery",
    )
    assert "submit" in alice.observe()["work_items"][replacement]["enabled_actions"]
    submitted = mustcall(alice, "submit", work_id=replacement, artifacts=["report"])
    assert submitted["required_credentials"] == [ref]
    assert submitted["review"] is None
    enabled = bob.observe()["work_items"][replacement]["enabled_actions"]
    approved = bob.call("approve", work_id=replacement, submission_id=submitted["submission_id"])
    if reviewer_can_read:
        assert "approve" in enabled
        assert approved["ok"], approved
        assert approved["result"]["review"]["decision"] == "accepted"
    else:
        assert "approve" not in enabled
        assert not approved["ok"]
        assert "not shared" in approved["error"]["message"]
        assert world.store.load()["work_items"][replacement]["submissions"][-1]["review"] is None


def test_object_scoped_provider_requires_both_work_and_object_scope(tmp_path):
    world = bootstrap(tmp_path / "world")
    pkg = package("A")
    pkg["objects"] = [material("evidence"), material("other")]
    pkg["works"].append({**copy.deepcopy(pkg["works"][0]), "work_id": "work-2"})
    for grant in pkg["grants"]:
        if grant["power"] == "provide":
            grant["object_ids"] = ["evidence"]
    install(world, pkg)
    alice = world.session("alice", "A")
    good = {"object_id": object_identity("A", "evidence"), "version_id": "v1"}
    wrong_object = alice.call(
        "request",
        work_id="work-1",
        provider="manager",
        reference={"object_id": object_identity("A", "other"), "version_id": "v1"},
        delay=20,
    )
    wrong_work = alice.call(
        "request", work_id="work-2", provider="manager", reference=good, delay=20
    )
    assert not wrong_object["ok"] and not wrong_work["ok"]
    assert world.store.load()["requests"] == {}
    result = mustcall(
        alice, "request", work_id="work-1", provider="manager", reference=good, delay=20
    )
    mustcall(world.session("manager"), "wait", ticks=20)
    state = world.store.load()
    assert state["requests"][result["request_id"]]["status"] == "delivered"
    assert state["condition_specs"][result["condition_id"]]["status"] == "resolved"
    assert state["work_items"]["A::work-2"]["status"] == "open"


def test_world_material_read_and_future_project_package_adoption(tmp_path):
    world = bootstrap(tmp_path / "world")
    manager = world.session("manager")
    created = mustcall(
        manager, "create_object", alias="material", filename="material.json", data={"source": 7}
    )
    read = mustcall(manager, "read_object", alias="material")
    assert read["data"] == {"source": 7}
    assert read["reference"] == {"artifact_id": created["object_id"], "version_id": "v1"}
    mustcall(
        manager, "share", **exact_ref(created), target_project="Future", actor_ids=list(ACTORS)
    )
    assert world.store.load()["projects"] == {}
    pkg = package("Future")
    pkg["adoptions"] = [
        {"alias": "input", **exact_ref(created), "policy": "fixed", "work_ids": ["work-1"]}
    ]
    install(world, pkg)
    state = world.store.load()
    assert state["adoptions"][binding_key("Future::work-1", "input")]["object_id"] == created["object_id"]
    assert state["adoptions"][binding_key("Future::work-1", "input")]["work_ids"] == ["Future::work-1"]
    assert state["workspaces"]["Future"]["input"] == created["object_id"]
    assert (
        len(
            [
                entry
                for entry in state["project_history"]
                if entry["project_id"] == "Future" and entry["event"] == "installed"
            ]
        )
        == 1
    )
    assert mustcall(world.session("alice", "Future"), "read_object", alias="input")["data"] == {
        "source": 7
    }


@pytest.mark.parametrize("close_policy", ["retain", "cancel"])
def test_project_archive_reply_policy_leaves_other_project_unchanged(tmp_path, close_policy):
    world = bootstrap(tmp_path / "world")
    a = package("A")
    a["close_policy"]["pending_obligations"] = close_policy
    a["objects"] = [material("evidence")]
    install(world, a, package("B"))
    request = mustcall(
        world.session("alice", "A"),
        "request",
        work_id="work-1",
        provider="manager",
        reference={"object_id": object_identity("A", "evidence"), "version_id": "v1"},
        delay=20,
    )
    before = world.store.load()
    b_project = copy.deepcopy(before["projects"]["B"])
    b_work = copy.deepcopy(before["work_items"]["B::work-1"])
    mustcall(
        world.session("manager", "A"),
        "close_project",
        mode="archived",
        reason="Archive according to explicit project contract",
    )
    mustcall(world.session("manager"), "wait", ticks=20)
    state = world.store.load()
    assert state["projects"]["B"] == b_project
    assert state["work_items"]["B::work-1"] == b_work
    assert state["projects"]["A"]["status"] == "archived"
    assert world.session("alice", "A").observe()["work_items"]["A::work-1"]["enabled_actions"] == []
    condition = state["condition_specs"][request["condition_id"]]
    if close_policy == "retain":
        assert state["requests"][request["request_id"]]["status"] == "delivered"
        assert condition["status"] == "resolved"
        assert len(state["raw_condition_responses"]) == 1
        assert state["work_items"]["A::work-1"].get("cancelled_at") is None
    else:
        assert state["requests"][request["request_id"]]["status"] == "cancelled"
        assert condition["status"] == "superseded"
        assert state["raw_condition_responses"] == {}
        assert state["work_items"]["A::work-1"]["cancelled_at"] is not None


def test_adoption_update_requires_visible_version_and_preserves_fixed_snapshot(tmp_path):
    world = bootstrap(tmp_path / "world")
    manager = world.session("manager")
    created = mustcall(
        manager, "create_object", alias="material", filename="material.json", data={"source": 1}
    )
    install(world, package("A"), package("B"))
    for pid, policy in (("A", "current_applicable"), ("B", "fixed")):
        mustcall(manager, "share", **exact_ref(created), target_project=pid, actor_ids=["alice"])
        mustcall(
            world.session("alice", pid),
            "adopt",
            alias="input",
            **exact_ref(created),
            policy=policy,
            work_ids=["work-1"],
        )
    mustcall(manager, "write_object", alias="material", data={"source": 2})
    alice = world.session("alice", "A")
    assert not alice.call("adopt_version", work_id="work-1", alias="input", version_id="v2")["ok"]
    assert world.store.load()["adoptions"][binding_key("A::work-1", "input")]["version_id"] == "v1"
    mustcall(
        manager,
        "share",
        object_id=created["object_id"],
        version_id="v2",
        target_project="A",
        actor_ids=["alice"],
    )
    updated = mustcall(alice, "adopt_version", work_id="work-1", alias="input", version_id="v2")
    assert updated["version_id"] == "v2"
    assert len(updated["history"]) == 1
    assert updated["history"][0]["previous_version"] == "v1"
    assert updated["history"][0]["version_id"] == "v2"
    assert alice.observe()["adoptions"][binding_key("A::work-1", "input")]["status"] == "current"
    before_fixed = copy.deepcopy(world.store.load()["adoptions"][binding_key("B::work-1", "input")])
    denied = world.session("alice", "B").call("adopt_version", work_id="work-1", alias="input", version_id="v2")
    assert not denied["ok"] and "Fixed adoption" in denied["error"]["message"]
    assert world.store.load()["adoptions"][binding_key("B::work-1", "input")] == before_fixed


def test_pause_blocks_new_work_and_environment_but_keeps_reads_and_episode_end(tmp_path):
    world = WorldCore.create(
        tmp_path / "world",
        WorldSpec(
            "pause-witness",
            actors={actor: {} for actor in ACTORS},
            bootstrap_grants=[
                {"actor_id": "manager", "scope": "world", "power": power}
                for power in ("install_project", "pause_world")
            ],
        ),
    )
    pkg = package("A")
    pkg["objects"] = [material("evidence")]
    install(world, pkg)
    manager = world.session("manager")
    alice = world.session("alice", "A")
    mustcall(manager, "start_episode", episode_id="episode-A", project_ids=["A"])
    request = mustcall(
        alice,
        "request",
        work_id="work-1",
        provider="manager",
        reference={"object_id": object_identity("A", "evidence"), "version_id": "v1"},
        delay=3,
    )
    queued = copy.deepcopy(world.store.load()["events"])
    mustcall(manager, "pause")
    assert manager.observe()["world_status"] == "paused"
    assert alice.observe()["work_items"]["A::work-1"]["enabled_actions"] == []
    assert not manager.call("wait", ticks=1)["ok"]
    assert not alice.call("create_object", alias="during-pause", filename="pause.json", data={})[
        "ok"
    ]
    assert mustcall(alice, "read_object", alias="evidence")["data"] == {"evidence": "evidence"}
    ended = mustcall(manager, "end_episode", episode_id="episode-A")
    assert ended["ended_at"] is not None
    paused = world.store.load()
    assert paused["events"] == queued
    assert paused["clock"] >= queued[0]["at"]
    assert paused["event_history"] == []
    assert paused["requests"][request["request_id"]]["status"] == "pending"
    mustcall(manager, "resume")
    resumed = world.store.load()
    assert manager.observe()["world_status"] == "active"
    assert resumed["events"] == []
    assert resumed["requests"][request["request_id"]]["status"] == "delivered"
    assert resumed["condition_specs"][request["condition_id"]]["status"] == "resolved"


def test_observation_supplies_public_contract_and_readable_aliases(tmp_path):
    from proworksim.core.world import WorldSpec
    from proworksim.world_core import WorldCore

    world = WorldCore.create(
        tmp_path / "public",
        WorldSpec(
            "public",
            {"operator": {}, "worker": {}},
            bootstrap_grants=[
                {"actor_id": "operator", "power": "install_project", "scope": "world"}
            ],
        ),
    )
    package = {
        "project_id": "P",
        "goal": "Flexible delivery",
        "participants": ["worker", "operator"],
        "objects": [
            {
                "alias": "visible",
                "filename": "visible.json",
                "data": {},
                "owner": "worker",
                "readers": ["worker"],
                "writers": ["worker"],
            },
            {
                "alias": "private",
                "filename": "private.json",
                "data": {},
                "owner": "operator",
                "readers": ["operator"],
                "writers": ["operator"],
            },
        ],
        "works": [
            {
                "work_id": "work-1",
                "owner": "worker",
                "approval_policy": "delivery_only",
                "deliverable_contract": {
                    "required_fields": ["result"],
                    "min_files": 1,
                    "max_files": 2,
                },
            }
        ],
    }
    assert world.session("operator").call("install_project", package=package)["ok"]
    observed = world.session("worker", "P").observe()
    item = observed["work_items"]["P::work-1"]
    assert item["deliverable_contract"]["required_fields"] == ["result"]
    assert item["approval_policy"] == "delivery_only" and item["requirement_version"] == 1
    assert set(observed["workspaces"]["P"]) == {"visible"}
    assert len(observed["objects"]) == 1
