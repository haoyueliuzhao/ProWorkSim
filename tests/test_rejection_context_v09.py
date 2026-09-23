"""Shared diagnostic formatting must also handle the payload it just rejected."""

import copy

import pytest


@pytest.mark.parametrize("arguments", [[], "unexpected", 7, True])
def test_non_object_arguments_return_refusal_and_replay_without_a_second_commit(world_factory, arguments):
    world = world_factory()
    original_artifacts = copy.deepcopy(world.store.load()["artifacts"])
    result = world.act("analyst", "wait", arguments, request_key="invalid-container")
    assert result["ok"] is False
    rejection = result["error"]["rejection"]
    assert rejection["category"] == "policy_error"
    assert rejection["code"] == "invalid_arguments"
    assert rejection["context"]["arguments_type"] == type(arguments).__name__
    assert world.store.load()["artifacts"] == original_artifacts
    state = copy.deepcopy(world.store.load())
    repeated = world.act("analyst", "wait", arguments, request_key="invalid-container")
    assert repeated == result
    assert world.store.load() == state
