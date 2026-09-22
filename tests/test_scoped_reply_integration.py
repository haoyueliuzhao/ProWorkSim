"""WorkerSession regressions for scoped replies and information availability."""

import copy

import pytest

from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World


def call(session, action, **arguments):
    response = session.call(action, **arguments)
    assert response["ok"], response
    return response["result"]


class BeforeSubmission(Exception):
    pass


class PreparationSession:
    def __init__(self, session):
        self.session = session

    def observe(self):
        return self.session.observe()

    def call(self, action, **arguments):
        if action == "submit":
            raise BeforeSubmission
        return self.session.call(action, **arguments)


@pytest.fixture
def fork_world(tmp_path):
    root = tmp_path / "fork"
    compile_world(design(seed=419, topology="fork"), root)
    world = World(root)
    session = world.session()
    with pytest.raises(BeforeSubmission):
        run_baseline(PreparationSession(session))
    call(session, "submit", work_item_id="model-1")
    call(session, "wait", ticks=2)
    assert world.store.load()["work_items"]["model-1"]["status"] == "accepted"
    return world


def block(world, work_item_id, kind, requested_role, version=None):
    if kind == "scope":
        version = world.store.load()["work_items"][work_item_id]["basis_requirement_version"]
    return call(
        world.session(),
        "block_work",
        work_item_id=work_item_id,
        reason=f"等待 {requested_role} 提供 {kind} 确认",
        kind=kind,
        requested_role=requested_role,
        required_scope_version=version,
    )["blocker_id"]


def request_and_wait(world, work_item_id, blocker_id, topic, recipient):
    request = call(
        world.session(),
        "mail_send",
        to=recipient,
        topic=topic,
        body="请提供适用于本项工作的确认凭据。",
        work_item_id=work_item_id,
        blocker_id=blocker_id,
    )
    call(world.session(), "wait", ticks=2)
    return request["message_id"]


def test_fork_scope_reply_releases_only_memo_then_client_reply_releases_note(fork_world):
    memo_blocker = block(fork_world, "memo-1", "scope", "manager")
    note_blocker = block(fork_world, "note-1", "audience", "client")
    before_note = copy.deepcopy(fork_world.store.load()["blockers"][note_blocker])
    request_id = request_and_wait(fork_world, "memo-1", memo_blocker, "scope", "manager")
    state = fork_world.store.load()
    assert state["work_items"]["memo-1"]["status"] == "open"
    assert state["work_items"]["note-1"]["status"] == "blocked"
    assert state["blockers"][memo_blocker]["status"] == "resolved"
    assert state["blockers"][note_blocker] == before_note
    assert state["requests"][request_id]["work_item_id"] == "memo-1"
    assert state["requests"][request_id]["status"] == "delivered"
    request_and_wait(fork_world, "note-1", note_blocker, "audience", "client")
    state = fork_world.store.load()
    assert state["work_items"]["note-1"]["status"] == "open"
    assert state["blockers"][note_blocker]["status"] == "resolved"


def test_one_work_with_two_conditions_stays_blocked_until_both_replies(fork_world):
    scope_blocker = block(fork_world, "memo-1", "scope", "manager")
    audience_blocker = block(fork_world, "memo-1", "audience", "client")
    request_and_wait(fork_world, "memo-1", scope_blocker, "scope", "manager")
    state = fork_world.store.load()
    assert state["blockers"][scope_blocker]["status"] == "resolved"
    assert state["blockers"][audience_blocker]["status"] == "open"
    assert state["work_items"]["memo-1"]["status"] == "blocked"
    assert not fork_world.session().call("submit", work_item_id="memo-1")["ok"]
    request_and_wait(fork_world, "memo-1", audience_blocker, "audience", "client")
    assert fork_world.store.load()["work_items"]["memo-1"]["status"] == "open"


def test_wrong_role_request_and_ordinary_reply_do_not_resolve_blocker(fork_world):
    blocker_id = block(fork_world, "memo-1", "scope", "manager")
    before = copy.deepcopy(fork_world.store.load()["blockers"][blocker_id])
    request = call(
        fork_world.session(),
        "mail_send",
        to="client",
        topic="scope",
        body="请确认情景假设。",
        work_item_id="memo-1",
    )
    call(fork_world.session(), "wait", ticks=2)
    call(
        fork_world.session("client"),
        "mail_send",
        to="analyst",
        topic="scope",
        body="memo-1：普通邮件自称已经确认，不能代替有权限的定向确认。",
    )
    state = fork_world.store.load()
    assert state["requests"][request["message_id"]]["status"] == "wrong_role"
    assert state["blockers"][blocker_id] == before
    assert state["work_items"]["memo-1"]["status"] == "blocked"


def test_available_basis_can_be_used_without_sending_a_scope_request(tmp_path):
    root = tmp_path / "available"
    compile_world(design(seed=419, delivery="file", information="mail"), root)
    world = World(root)
    assert run_baseline(world.session())["complete"]
    state = world.store.load()
    assert not any(
        record["action"] == "mail_send" and record["inputs"].get("topic") == "scope"
        for record in state["interactions"]
    )
    model = state["artifacts"]["model"]
    dependencies = model["versions"][model["current_version"]]["derived_from"]
    assert state["work_items"]["work-1"]["required_basis"] in dependencies
    assert not state.get("blockers")


def test_unavailable_information_ends_blocked_without_fabricated_deliverables(tmp_path):
    root = tmp_path / "unavailable"
    compile_world(design(seed=419, scenario="unavailable"), root)
    world = World(root)
    before = world.store.load()
    result = run_baseline(world.session())
    assert not result["complete"]
    assert result["reason"] == "blocked_unavailable"
    state = world.store.load()
    assert world.session().observe()["terminal_reason"] == "blocked_unavailable"
    assert state["work_items"]["work-1"]["status"] == "blocked"
    assert not state["work_items"]["work-1"]["submissions"]
    assert all(blocker["status"] == "unavailable" for blocker in state["blockers"].values())
    for artifact_id in ("model", "memo"):
        assert state["artifacts"][artifact_id] == before["artifacts"][artifact_id]
    assert not any(record["writes"] for record in state["interactions"])
