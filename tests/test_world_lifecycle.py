"""World-level lifecycle witnesses through public tool calls, without state mutation."""

import copy
import json

from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.storage import digest
from test_world import call, prepare


def world_at(
    tmp_path, *, scenario="standard", information="mail", delivery="continuous", topology="chain"
):
    root = compile_world(
        design(
            43, delivery=delivery, information=information, topology=topology, scenario=scenario
        ),
        tmp_path / "world",
    )
    return World(root)


def version_bytes(world, state, artifact_id):
    artifact = state["artifacts"][artifact_id]
    return artifact["current_version"], digest(world.store.content(artifact))


def revise(world, work_item_id="work-1"):
    result = world.act(
        "manager",
        "revise_requirements",
        {
            "work_item_ids": [work_item_id],
            "growth_delta": 0.02,
            "reason": "集成回归：财务披露不变，仅修订已批准增长假设",
        },
    )
    assert result["ok"], result
    return result["result"]["replacements"]


def block_scope(world, work_item_id="work-1"):
    state = world.store.load()
    item = state["work_items"][work_item_id]
    version = item.get("basis_requirement_version", item["requirement_version"])
    call(
        world.session(),
        "block_work",
        work_item_id=work_item_id,
        kind="scope",
        requested_role="manager",
        required_scope_version=version,
        reason="等待该工作版本适用的批准假设",
    )
    return world.store.load()["work_items"][work_item_id]["blocker_ids"][-1]


def ask_scope(world, work_item_id, blocker_id):
    return call(
        world.session(),
        "mail_send",
        to="manager",
        topic="scope",
        body="请确认此工作及需求版本适用的假设，并提供可引用凭据。",
        work_item_id=work_item_id,
        blocker_id=blocker_id,
    )


def test_basis_only_change_preserves_financials_and_marks_adopted_outputs_stale(tmp_path):
    world = world_at(tmp_path, scenario="basis_only")
    prepare(world)
    before = world.store.load()
    snapshots = {aid: version_bytes(world, before, aid) for aid in ("financials", "model", "memo")}
    assert before["work_items"]["work-1"]["required_basis"] == {
        "artifact_id": "basis",
        "version_id": "v2",
    }
    assert all(before["artifacts"][aid]["freshness"] == "current" for aid in ("model", "memo"))
    new_id = revise(world)["work-1"]
    after = world.store.load()
    assert snapshots == {aid: version_bytes(world, after, aid) for aid in snapshots}
    assert after["artifacts"]["financials"]["freshness"] == "current"
    assert all(after["artifacts"][aid]["freshness"] == "stale" for aid in ("model", "memo"))
    assert after["work_items"][new_id]["required_basis"] == {
        "artifact_id": "basis",
        "version_id": "v3",
    }
    assert after["work_items"]["work-1"]["status"] == "superseded"


def test_resolved_blocker_history_survives_repeated_requirement_replacement(tmp_path):
    world = world_at(tmp_path, information="clarification")
    session = world.session()
    assert not session.call("read_file", artifact_id="basis", version_id="v2")["ok"]
    blocker_id = block_scope(world)
    ask_scope(world, "work-1", blocker_id)
    call(session, "wait", ticks=2)
    resolved = copy.deepcopy(world.store.load()["blockers"][blocker_id])
    assert resolved["status"] == "resolved"
    assert world.store.load()["work_items"]["work-1"]["status"] == "open"
    assert call(session, "read_file", artifact_id="basis", version_id="v2")["version_id"] == "v2"
    first_id = revise(world)["work-1"]
    second_id = revise(world)[first_id]
    after = world.store.load()
    assert after["blockers"][blocker_id] == resolved
    assert after["work_items"][first_id]["status"] == "superseded"
    assert after["work_items"][second_id]["status"] == "open"
    assert after["work_items"][second_id]["required_basis"]["version_id"] == "v4"
    assert not session.call("read_file", artifact_id="scope")["ok"]
    assert not session.call("read_file", artifact_id="basis", version_id="v4")["ok"]


def test_requirement_change_during_review_cannot_approve_old_submission(tmp_path):
    world = world_at(tmp_path)
    prepare(world)
    session = world.session()
    submission = call(session, "submit", work_item_id="work-1")
    assert world.store.load()["work_items"]["work-1"]["status"] == "in_review"
    new_id = revise(world)["work-1"]
    call(session, "wait", ticks=2)
    state = world.store.load()
    archived = state["work_items"]["work-1"]["submissions"][0]
    assert archived["artifact_versions"] == submission["artifact_versions"]
    assert archived["invalidated"]
    assert archived["review"] is None
    assert archived["current_applicability"] == "superseded_requirements"
    assert state["work_items"][new_id]["submissions"] == []
    assert state["work_items"][new_id]["status"] == "open"
    assert not world.act(
        "reviewer",
        "approve",
        {
            "work_item_id": new_id,
            "submission_id": submission["submission_id"],
        },
    )["ok"]
    assert not world.act(
        "reviewer",
        "approve",
        {
            "work_item_id": "work-1",
            "submission_id": submission["submission_id"],
        },
    )["ok"]


def test_historical_approval_is_retained_with_separate_current_applicability(tmp_path):
    world = world_at(tmp_path, delivery="file")
    assert run_baseline(world.session())["complete"]
    before = world.store.load()
    accepted = copy.deepcopy(before["work_items"]["work-1"]["submissions"][0])
    assert accepted["review"]["decision"] == "accepted"
    new_id = revise(world)["work-1"]
    state = world.store.load()
    historical = state["work_items"]["work-1"]
    assert historical["status"] == "accepted"
    assert historical["applicability"] == "superseded_requirements"
    assert historical["submissions"][0]["review"] == accepted["review"]
    assert historical["submissions"][0]["artifact_versions"] == accepted["artifact_versions"]
    assert historical["submissions"][0]["current_applicability"] == "superseded_requirements"
    assert state["work_items"][new_id]["status"] == "open"
    assert state["work_items"][new_id]["submissions"] == []
    assert not world.session().observe()["complete"]


def test_audience_only_change_preserves_unaffected_outputs_and_basis(tmp_path):
    world = world_at(tmp_path, topology="selective")
    assert run_baseline(world.session())["complete"]
    before = world.store.load()
    snapshots = {aid: version_bytes(world, before, aid) for aid in ("model", "memo", "basis")}
    result = world.act(
        "client",
        "write_file",
        {
            "artifact_id": "brief",
            "content": json.dumps({"audience": "investment_committee"}),
        },
    )
    assert result["ok"], result
    after = world.store.load()
    assert snapshots == {aid: version_bytes(world, after, aid) for aid in snapshots}
    assert all(after["artifacts"][aid]["freshness"] == "current" for aid in ("model", "memo"))
    assert after["artifacts"]["note"]["freshness"] == "stale"
    for work_id in ("model-1", "memo-1"):
        assert after["work_items"][work_id]["status"] == "accepted"
        assert (
            after["work_items"][work_id]["submissions"]
            == before["work_items"][work_id]["submissions"]
        )


def test_old_reply_keeps_history_without_unblocking_replacement_work(tmp_path):
    world = world_at(tmp_path, scenario="waiting_reply", information="clarification")
    session = world.session()
    old_blocker = block_scope(world)
    ask_scope(world, "work-1", old_blocker)
    state = world.store.load()
    new_id = state["work_replacements"]["work-1"]
    assert state["work_items"][new_id]["required_basis"]["version_id"] == "v3"
    new_blocker = block_scope(world, new_id)
    call(session, "wait", ticks=2)
    state = world.store.load()
    assert state["work_items"]["work-1"]["status"] == "superseded"
    assert state["blockers"][old_blocker]["status"] == "superseded"
    assert state["work_items"][new_id]["status"] == "blocked"
    assert state["blockers"][new_blocker]["status"] == "open"
    assert call(session, "read_file", artifact_id="basis", version_id="v2")["version_id"] == "v2"
    assert not session.call("read_file", artifact_id="basis", version_id="v3")["ok"]
    assert not session.call("read_file", artifact_id="scope")["ok"]
    ask_scope(world, new_id, new_blocker)
    call(session, "wait", ticks=2)
    final = world.store.load()
    assert final["work_items"][new_id]["status"] == "open"
    assert final["blockers"][new_blocker]["status"] == "resolved"
    assert call(session, "read_file", artifact_id="basis", version_id="v3")["version_id"] == "v3"


def test_request_then_declare_unavailability_stops_without_repeated_requests(tmp_path):
    world = world_at(tmp_path, scenario="unavailable")
    session = world.session()
    request = call(
        session,
        "mail_send",
        to="manager",
        topic="scope",
        work_item_id="work-1",
        body="请提供可用批准依据",
    )
    call(session, "wait", ticks=2)
    assert not session.call(
        "block_work",
        work_item_id="work-1",
        kind="scope",
        requested_role="manager",
        required_scope_version=99,
        request_id=request["message_id"],
        reason="错误版本请求",
    )["ok"]
    blocked = call(
        session,
        "block_work",
        work_item_id="work-1",
        kind="scope",
        requested_role="manager",
        required_scope_version=1,
        request_id=request["message_id"],
        reason="负责人明确无法提供适用确认",
    )
    assert blocked["blocker"]["status"] == "unavailable"
    assert session.observe()["terminal_reason"] == "blocked_unavailable"
