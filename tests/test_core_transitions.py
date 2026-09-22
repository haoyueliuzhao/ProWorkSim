"""Adversarial frame and history properties, independent of business answers."""

import copy

import pytest

from proworksim.core.transitions import ActionFrame, execute_transition, ordered_due_events
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World


def minimal():
    return {
        "objects": {"target": {"value": 1}, "unrelated": {"value": 2}},
        "messages": [],
        "artifacts": {},
        "work_items": {},
    }


def test_out_of_scope_effect_rolls_back_all_direct_effects():
    state = minimal()
    before = copy.deepcopy(state)

    def buggy_reply():
        state["objects"]["target"]["value"] = 3
        state["objects"]["unrelated"]["value"] = 4

    with pytest.raises(ValueError, match="outside its frame"):
        execute_transition(state, ActionFrame("Reply", (("objects", "target"),)), buggy_reply)
    assert state == before


def test_derive_cannot_silently_fix_a_primary_business_value():
    state = minimal()
    state["view"] = {}
    before = copy.deepcopy(state)
    frame = ActionFrame("Edit", (("objects", "target"),), (("view",),))

    def bad_derive(state):
        state["objects"]["target"]["value"] = 100

    with pytest.raises(ValueError, match="primary fact"):
        execute_transition(state, frame, lambda: None, bad_derive)
    assert state == before


def test_explicit_scope_does_not_authorize_rewriting_historical_messages():
    state = minimal()
    state["messages"] = [{"message_id": "old", "body": "original fact"}]
    before = copy.deepcopy(state)

    def rewrite():
        state["messages"][0]["body"] = "different fact"

    with pytest.raises(ValueError, match="Append-only"):
        execute_transition(state, ActionFrame("Reply", (("messages",),)), rewrite)
    assert state == before


def test_derive_is_repeatable_without_creating_new_base_records():
    state = minimal()
    state["view"] = {}
    frame = ActionFrame("Recompute", (), (("view",),))

    def derive(state):
        state["view"]["sum"] = sum(v["value"] for v in state["objects"].values())

    _, first = execute_transition(state, frame, lambda: None, derive)
    after = copy.deepcopy(state)
    _, second = execute_transition(state, frame, lambda: None, derive)
    assert state == after
    assert first["primary_region_changes"] == []
    assert second["projection_region_changes"] == []


def test_simultaneous_events_follow_enqueue_order_not_random_identifiers():
    events = [
        {"event_id": "z", "at": 2},
        {"event_id": "a", "at": 2},
        {"event_id": "future", "at": 9},
    ]
    assert [e["event_id"] for e in ordered_due_events(events, 2)] == ["z", "a"]


def test_failed_action_keeps_business_effects_but_clock_can_deliver_reply(tmp_path):
    world = World(
        compile_world(design(53, delivery="file", information="clarification"), tmp_path / "world")
    )
    session = world.session()
    assert session.call(
        "mail_send", to="manager", topic="scope", work_item_id="work-1", body="confirm"
    )["ok"]
    state = world.store.load()
    versions = copy.deepcopy(state["artifacts"]["model"]["versions"])
    before_messages = len(state["messages"])
    result = session.call("not_a_tool")
    assert not result["ok"]
    after = world.store.load()
    assert after["clock"] == state["clock"] + 1
    assert after["artifacts"]["model"]["versions"] == versions
    assert len(after["messages"]) == before_messages + 1
    attempt = next(r for r in after["interactions"] if r["action_id"] == result["action_id"])
    assert attempt["transition"]["rolled_back"]
    assert after["event_history"][-1]["transition"]["frame_respected"]


def test_receipt_records_execution_phase_separately_from_field_region():
    state = {"base": 0, "view": 0}
    _, receipt = execute_transition(
        state, ActionFrame("ApplyProjection", (), (("view",),)), lambda: state.update(view=1)
    )
    assert receipt["apply_delta"] == [["view"]]
    assert receipt["derive_delta"] == []
    assert receipt["net_delta"] == [["view"]]
    assert receipt["primary_region_changes"] == []
    assert receipt["projection_region_changes"] == [["view"]]
    assert receipt["committed_revision"] is None


def test_receipt_keeps_both_phases_when_their_effects_cancel():
    state = {"base": 0, "view": 0}
    _, receipt = execute_transition(
        state,
        ActionFrame("Cancel", (), (("view",),)),
        lambda: state.update(view=1),
        lambda s: s.update(view=0),
    )
    assert receipt["apply_delta"] == receipt["derive_delta"] == [["view"]]
    assert receipt["net_delta"] == []
    assert receipt["state_digests"]["before"] == receipt["state_digests"]["after_derive"]
    assert receipt["state_digests"]["before"] != receipt["state_digests"]["after_apply"]


def test_failed_phase_is_not_reported_as_a_completed_empty_delta():
    state = {"primary": 0}

    def partial_apply():
        state["primary"] = 1
        raise ValueError("Stopped during apply")

    with pytest.raises(ValueError) as raised:
        execute_transition(state, ActionFrame("Partial", (("primary",),)), partial_apply)
    receipt = raised.value.transition_receipt
    assert receipt["apply_delta"] is None and receipt["derive_delta"] is None
    assert receipt["attempted_delta"] == [["primary"]]
    assert receipt["net_delta"] == [] and state == {"primary": 0}
