import copy

import pytest

from proworksim.core.projections import rebuild_projections
from proworksim.blockers import (
    bind_request,
    create_blocker,
    mark_unavailable,
    reopen_if_ready,
    resolve_for_reply,
    supersede_blocker,
)


@pytest.fixture
def state():
    return {
        "clock": 7,
        "roles": [{"role_id": role} for role in ("analyst", "manager", "client", "reviewer")],
        "messages": [],
        "work_items": {
            name: {
                "work_item_id": name,
                "owner_role": "analyst",
                "requirement_version": 1,
                "status": "open",
                "dependencies": [],
            }
            for name in ("memo-1", "note-1")
        },
    }


def request(state, blocker, request_id, *, sender="analyst", recipient=None, topic=None):
    state["messages"].append(
        {
            "message_id": request_id,
            "sender": sender,
            "recipients": [recipient or blocker["requested_role"]],
            "subject": topic or blocker["kind"],
        }
    )
    return bind_request(state, blocker["blocker_id"], request_id, sender, blocker["work_item_id"])


def block(state, work="memo-1", kind="scope", role="manager", version=1):
    return create_blocker(state, state["work_items"][work], kind, role, version, "缺少明确确认")


def reply(state, request_id="request-1", role="manager", topic="scope", version=1):
    return resolve_for_reply(state, request_id, role, topic, version, {"message_id": "reply-1"})


def test_reply_resolves_only_its_work_and_preserves_other_blockers(state):
    scope = request(state, block(state), "request-1")
    audience = request(state, block(state, "note-1", "audience", "client", None), "request-2")
    assert reply(state) == [scope["blocker_id"]]
    assert state["work_items"]["memo-1"]["status"] == "open"
    assert state["work_items"]["note-1"]["status"] == "blocked"
    assert state["blockers"][audience["blocker_id"]] == audience
    resolved = state["blockers"][scope["blocker_id"]]
    assert resolved["detail"] == scope["detail"]
    assert resolved["history"][:2] == scope["history"]
    assert resolved["resolution_ref"] == {"message_id": "request-1:reply-1", "reference": None}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"request_id": "unrelated-request"},
        {"role": "client"},
        {"topic": "audience"},
        {"version": 0},
        {"version": 2},
        {"version": True},
        {"version": None},
    ],
)
def test_irrelevant_and_old_replies_preserve_work_while_recording_receipt(state, kwargs):
    request(state, block(state), "request-1")
    before = copy.deepcopy(state)
    assert reply(state, **kwargs) == []
    assert state["work_items"] == before["work_items"]
    assert state["condition_specs"]["condition-1"]["status"] == "open"
    if kwargs.get("request_id") != "unrelated-request":
        assert state["raw_condition_responses"]


def test_multiple_conditions_and_predecessor_must_all_be_satisfied(state):
    item = state["work_items"]["memo-1"]
    item["dependencies"] = ["note-1"]
    scope = request(state, block(state), "request-1")
    evidence = request(state, block(state, kind="evidence", version=None), "request-2")
    assert reply(state) == [scope["blocker_id"]]
    assert item["status"] == "blocked"
    assert reply(state, "request-2", topic="evidence", version=None) == [evidence["blocker_id"]]
    assert item["status"] == "waiting_dependencies"
    state["work_items"]["note-1"]["submissions"] = [
        {"submission_id": "approved-note", "review": {"decision": "accepted"}}
    ]
    assert reopen_if_ready(state, "memo-1")
    assert item["status"] == "open"
    before = copy.deepcopy(state)
    assert reply(state) == []
    assert state == before


def test_a_request_cannot_be_shared_across_works_or_rebound(state):
    first = request(state, block(state), "request-1")
    second = block(state, "note-1")
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="across work"):
        bind_request(state, second["blocker_id"], "request-1", "analyst", "note-1")
    assert state == before
    with pytest.raises(ValueError, match="cannot be replaced"):
        bind_request(state, first["blocker_id"], "request-2", "analyst", "memo-1")
    assert state == before


@pytest.mark.parametrize(
    "kwargs",
    [{"sender": "reviewer"}, {"recipient": "client"}, {"topic": "audience"}],
)
def test_request_binding_checks_sender_recipient_and_topic(state, kwargs):
    blocker = block(state)
    with pytest.raises(ValueError):
        request(state, blocker, "request-1", **kwargs)
    assert state["blockers"][blocker["blocker_id"]]["request_id"] is None


def test_invalid_request_on_creation_does_not_leave_partial_blocker(state):
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="Request does not match"):
        create_blocker(
            state, state["work_items"]["memo-1"], "scope", "manager", 1, "缺少确认", "invented"
        )
    assert state == before


@pytest.mark.parametrize("status", ["superseded", "cancelled", "accepted"])
def test_terminal_work_is_never_reopened_by_old_reply_or_retired_blocker(state, status):
    blocker = request(state, block(state), "request-1")
    item = state["work_items"]["memo-1"]
    if status == "accepted":
        item["submissions"] = [
            {"submission_id": "approved-memo", "review": {"decision": "accepted"}}
        ]
    elif status == "cancelled":
        item["cancelled_at"] = state["clock"]
    else:
        state["work_replacements"] = {"memo-1": "memo-2"}
        state["work_items"]["memo-2"] = {
            **copy.deepcopy(item),
            "work_item_id": "memo-2",
            "requirement_version": 2,
        }
    rebuild_projections(state)
    assert reply(state) == []
    supersede_blocker(state, blocker["blocker_id"], "该工作已经被替代")
    assert item["status"] == status


def test_late_reply_for_previous_requirement_does_not_apply_to_new_requirement(state):
    request(state, block(state), "request-1")
    state["work_items"]["memo-1"]["requirement_version"] = 2
    before = copy.deepcopy(state)
    assert reply(state) == []
    assert state["work_items"] == before["work_items"]
    assert state["condition_specs"]["condition-1"]["status"] == "open"


def test_unavailable_condition_keeps_work_blocked_until_explicitly_superseded(state):
    blocker = request(state, block(state), "request-1")
    unavailable = mark_unavailable(
        state, blocker["blocker_id"], "当前不能取得批准依据", {"message_id": "declined-1"}
    )
    assert unavailable["status"] == "unavailable"
    assert unavailable["history"][-1]["reason"] == "当前不能取得批准依据"
    assert state["work_items"]["memo-1"]["status"] == "blocked"
    assert not reopen_if_ready(state, "memo-1")
    assert reply(state) == []
    retired = supersede_blocker(state, blocker["blocker_id"], "需求已撤除该信息条件")
    assert retired["status"] == "superseded"
    assert retired["history"][:-1] == unavailable["history"]
    assert state["work_items"]["memo-1"]["status"] == "open"


def test_read_access_or_unbound_scope_reply_is_not_adoption_or_resolution(state):
    blocker = block(state)
    state["messages"].append(
        {
            "message_id": "request-1",
            "sender": "analyst",
            "recipients": ["manager"],
            "subject": "scope",
        }
    )
    assert reply(state) == []
    assert state["blockers"][blocker["blocker_id"]]["status"] == "open"


def test_scope_version_is_mandatory_but_unversioned_evidence_is_supported(state):
    with pytest.raises(ValueError, match="explicit applicable version"):
        block(state, version=None)
    evidence = request(state, block(state, kind="evidence", version=None), "request-1")
    assert reply(state, topic="evidence", version=None) == [evidence["blocker_id"]]
