"""Committed commands and environment events have independent retry identities."""

import copy

import pytest

from proworksim.core.journal import validate_committed_prefix
from proworksim.kernel import World
from test_world import prepare, call


class Interrupted(BaseException):
    pass


def test_same_identity_same_canonical_payload_reuses_result_but_different_payload_conflicts(
    world_factory,
):
    world = world_factory("file")
    first = world.act(
        "analyst", "calculate", {"expression": "x+1", "variables": {"x": 3}}, request_key="stable"
    )
    before = world.store.load()
    repeated = World(world.store.root).act(
        "analyst", "calculate", {"variables": {"x": 3}, "expression": "x+1"}, request_key="stable"
    )
    assert repeated == first
    assert world.store.load() == before
    conflict = world.act("analyst", "calculate", {"expression": "99"}, request_key="stable")
    assert not conflict["ok"] and conflict["error"]["type"] == "CommandConflict"
    assert world.store.load() == before


def test_committed_command_survives_failure_of_subsequent_due_event(world_factory, monkeypatch):
    world = world_factory("file")
    prepare(world)
    call(world.session(), "submit", work_item_id="work-1")
    original = world._apply_event

    def fail_event(event):
        raise ValueError("Injected event failure")

    monkeypatch.setattr(world, "_apply_event", fail_event)
    response = world.act("analyst", "wait", {"ticks": 2}, request_key="waiting-command")
    assert response["ok"] and response["command_committed"]
    assert response["pending_event_errors"][0]["event_committed"] is False
    checkpoint = world.store.load()
    assert checkpoint["events"]
    action_count = sum(
        r["request_key"] == "waiting-command"
        for r in checkpoint["interactions"]
        if "request_key" in r
    )
    monkeypatch.setattr(world, "_apply_event", original)
    retried = world.act("analyst", "wait", {"ticks": 2}, request_key="waiting-command")
    assert retried == {k: v for k, v in response.items() if k != "pending_event_errors"}
    state = world.store.load()
    assert state["work_items"]["work-1"]["status"] == "accepted"
    assert action_count == sum(
        r.get("request_key") == "waiting-command" for r in state["interactions"]
    )
    assert not state["events"]
    validate_committed_prefix(state)


@pytest.mark.parametrize("phase", ["version_staged", "after_apply", "after_command_commit"])
def test_reopen_uses_committed_prefix_after_interruption(world_factory, phase):
    world = world_factory("file")
    args = {"artifact_id": "memo", "content": '{"wrong_but_real":true}'}
    before = world.store.load()

    def fault(current, context):
        if current == phase:
            raise Interrupted(phase)

    world.fault_hook = fault
    with pytest.raises(Interrupted):
        world.act("analyst", "write_file", args, request_key="write-once")
    recovered = World(world.store.root)
    result = recovered.act("analyst", "write_file", args, request_key="write-once")
    assert result["ok"]
    state = recovered.store.load()
    assert (
        len(state["artifacts"]["memo"]["versions"])
        == len(before["artifacts"]["memo"]["versions"]) + 1
    )
    assert recovered.store.content(state["artifacts"]["memo"]) == args["content"].encode()
    assert sum(r.get("request_key") == "write-once" for r in state["interactions"]) == 1
    validate_committed_prefix(state)


def test_duplicate_event_acknowledges_without_second_effect_and_changed_payload_conflicts(
    world_factory,
):
    world = world_factory("file")
    prepare(world)
    call(world.session(), "submit", work_item_id="work-1")
    call(world.session(), "wait", ticks=2)
    state = world.store.load()
    event = next(e for e in state["event_history"] if e["kind"] == "review")
    original = copy.deepcopy(state)
    state["events"].append(copy.deepcopy(event))
    world.store.save(state)
    assert world.recover()["pending_event_errors"] == []
    assert world.store.load() == original
    bad = copy.deepcopy(event)
    bad["payload"]["submission_id"] = "different-submission"
    original["events"].append(bad)
    world.store.save(original)
    result = world.recover()
    assert result["pending_event_errors"][0]["error"]["type"] == "CommandConflict"
    observed = world.store.load()
    attempts = observed.pop("event_attempts")
    assert attempts[-1]["error"]["type"] == "CommandConflict"
    assert observed == original


def test_public_enabled_actions_respect_bound_actor(world_factory):
    world = world_factory("file")
    worker = world.observe("analyst")["work_items"][0]
    manager = world.observe("manager")["work_items"][0]
    assert "submit" in worker["enabled_actions"]
    assert "submit" not in manager["enabled_actions"]


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
def test_event_ack_error_after_commit_does_not_rollback_committed_versions(tmp_path, error_type):
    from proworksim.compiler import compile_world
    from proworksim.designer import design

    world = World(compile_world(design(827, scenario="during_update"), tmp_path / "world"))

    def fault(phase, context):
        if phase == "after_event_commit":
            raise error_type("Delivery acknowledgement failed after durable state commit")

    world.fault_hook = fault
    arguments = {"cells": {"Probe!A1": 1}}
    result = world.act("analyst", "sheet_update", arguments, request_key="commit-then-ack-fail")
    assert result["ok"] and result["command_committed"]
    assert not result.get("pending_event_errors")
    assert result["event_delivery_errors"][0]["event_committed"]
    reopened = World(world.store.root)
    before = reopened.store.load()
    assert before["artifacts"]["basis"]["current_version"] == "v3"
    assert before["artifacts"]["scope"]["current_version"] == "v2"
    retried = reopened.act("analyst", "sheet_update", arguments, request_key="commit-then-ack-fail")
    assert retried == {
        key: value for key, value in result.items() if key != "event_delivery_errors"
    }
    assert reopened.store.load() == before


def test_nonfinite_payload_is_outside_identity_domain_and_cannot_be_cached(world_factory):
    world = world_factory("file")
    before = world.store.load()
    for suffix in ("a", "b"):
        result = world.act(
            "analyst",
            "wait",
            {"ticks": float("nan"), "prefix": "x" * 3000, "tail": suffix},
            request_key="invalid",
        )
        assert result["error"]["type"] == "InvalidInput"
        assert not result["command_committed"]
    assert world.store.load() == before


def test_old_schema_is_not_silently_reinterpreted_as_new_projection_facts(world_factory):
    world = world_factory("file")
    state = world.store.load()
    state["schema_version"] = "0.4"  # Explicit old-checkpoint boundary fixture.
    world.store.save(state)
    before = (world.store.control / "state.json").read_bytes()
    with pytest.raises(ValueError, match="historical frozen runtime"):
        World(world.store.root)
    assert (world.store.control / "state.json").read_bytes() == before


def test_missing_committed_journal_is_an_explicit_recovery_error(world_factory):
    world = world_factory("file")
    assert world.act("analyst", "calculate", {"expression": "1+1"}, request_key="real-commit")["ok"]
    state = world.store.load()
    state.pop("operation_commits")  # Explicit corrupt checkpoint, not a cache mutation.
    world.store.save(state)
    before = (world.store.control / "state.json").read_bytes()
    with pytest.raises(ValueError, match="no operation journal"):
        World(world.store.root)
    assert (world.store.control / "state.json").read_bytes() == before
