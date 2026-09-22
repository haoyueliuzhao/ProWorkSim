"""Condition algebra plus real communication effects, not domain answer tests."""

import copy

import pytest

from proworksim.adapters.communication import deliver_reply
from proworksim.blockers import bind_request, create_blocker
from proworksim.compiler import compile_world
from proworksim.core.conditions import apply_response, condition_has_future, match_response
from proworksim.core.projections import rebuild_projections
from proworksim.core.rules import confirm_credential
from proworksim.core.types import CheckStatus, Credential
from proworksim.designer import design
from proworksim.kernel import World


def protocol_state(*, providers=("licensor",)):
    state = {
        "schema_version": "0.5",
        "clock": 5,
        "project": {"project_id": "p"},
        "roles": [{"role_id": role} for role in ("author", "licensor", "alternate", "stranger")],
        "organization": {
            "positions": {},
            "grants": [
                {
                    "actor_id": provider,
                    "power": "confirm",
                    "subject": "license",
                    "work_nodes": ["article"],
                }
                for provider in ("licensor", "alternate")
            ],
        },
        "artifacts": {
            "permit": {
                "artifact_id": "permit",
                "versions": {
                    "v1": {"logical_time": 1},
                    "v2": {"logical_time": 5},
                },
                "current_version": "v2",
            },
            "draft": {
                "artifact_id": "draft",
                "versions": {"v1": {"logical_time": 1, "content": "unchanged draft"}},
                "current_version": "v1",
            },
        },
        "work_items": {
            "article": {
                "work_item_id": "article",
                "owner_role": "author",
                "requirement_version": 1,
                "status": "blocked",
                "dependencies": [],
            },
            "unrelated": {
                "work_item_id": "unrelated",
                "owner_role": "author",
                "requirement_version": 1,
                "status": "blocked",
                "dependencies": [],
            },
        },
        "requests": {},
        "messages": [],
        "condition_specs": {},
        "events": [],
    }
    credential = Credential(
        reference={"object_id": "permit", "version_id": "v1"},
        project_id="p",
        requirement_dimension="license",
        requirement_version=1,
        work_nodes=("article",),
        period=None,
        purpose="publish",
        effective_at=1,
        confirmed_by="licensor",
        attestation_ref="license-signature-1",
    )
    confirm_credential(state, "licensor", credential.reference, credential)
    state["condition_specs"]["permission"] = {
        "condition_id": "permission",
        "work_item_id": "article",
        "requirement_version": 1,
        "request_id": "request-1",
        "status": "open",
        "providers": list(providers),
        "unavailable_providers": [],
        "expected_version": 1,
        "purpose": "permission",
        "required_power": "confirm",
        "subject": "license",
        "history": [{"event": "created", "request_id": "request-1", "at": 5}],
        "evidence_spec": {"kind": "credential", "reference": credential.reference},
        "context": {
            "project_id": "p",
            "work_id": "article",
            "requirement_dimension": "license",
            "requirement_version": 1,
            "work_node": "article",
            "period": None,
            "purpose": "publish",
            "at": 5,
        },
    }
    state["condition_specs"]["unrelated-condition"] = {
        **copy.deepcopy(state["condition_specs"]["permission"]),
        "condition_id": "unrelated-condition",
        "work_item_id": "unrelated",
        "request_id": None,
        "history": [],
    }
    add_request(state, "request-1", "licensor")
    rebuild_projections(state)
    return state


def add_request(state, request_id, provider):
    state["messages"].append(
        {
            "message_id": request_id,
            "sender": "author",
            "recipients": [provider],
            "work_item_id": "article",
            "subject": "permission",
        }
    )
    state["requests"][request_id] = {
        "request_id": request_id,
        "work_item_id": "article",
        "requested_role": provider,
        "requirement_version": 1,
    }


def response(**changes):
    return {
        "response_id": "response-1",
        "request_id": "request-1",
        "responder": "licensor",
        "work_item_id": "article",
        "requirement_version": 1,
        "condition_version": 1,
        "purpose": "permission",
        "reference": {"object_id": "permit", "version_id": "v1"},
        "status": "delivered",
        **changes,
    }


def test_four_check_outcomes_are_distinct_and_pure():
    state = protocol_state()
    condition = state["condition_specs"]["permission"]
    before = copy.deepcopy(state)
    assert match_response(state, condition, response()).status == CheckStatus.PASS
    assert (
        match_response(
            state, condition, response(reference={"object_id": "permit", "version_id": "v2"})
        ).status
        == CheckStatus.FAIL
    )
    assert (
        match_response(state, condition, response(reference=None)).status == CheckStatus.UNASSESSED
    )
    assert (
        match_response(state, condition, response(request_id="other")).status
        == CheckStatus.NOT_APPLICABLE
    )
    assert state == before


def test_response_cannot_self_certify_or_use_wrong_attestation():
    state = protocol_state()
    condition = state["condition_specs"]["permission"]
    state["attestations"]["license-signature-1"]["reference"]["version_id"] = "v2"
    result = match_response(state, condition, response(verified=True, approved=True))
    assert result.status == CheckStatus.UNASSESSED
    assert "attestation_mismatch" in result.reasons
    assert not apply_response(state, response())["resolved_conditions"]
    assert state["work_items"]["article"]["status"] == "blocked"


@pytest.mark.parametrize(
    "changes",
    [
        {"responder": "stranger"},
        {"work_item_id": "unrelated"},
        {"condition_version": 2},
        {"condition_version": True},
        {"requirement_version": 2},
        {"purpose": "different"},
    ],
)
def test_matching_topic_cannot_override_request_identity_or_context(changes):
    state = protocol_state()
    before = copy.deepcopy(state)
    assert (
        match_response(state, state["condition_specs"]["permission"], response(**changes)).status
        != CheckStatus.PASS
    )
    assert not apply_response(state, response(**changes))["resolved_conditions"]
    assert state["work_items"] == before["work_items"]
    assert state["artifacts"] == before["artifacts"]
    assert state["condition_specs"]["permission"]["status"] == "open"
    assert state["raw_condition_responses"]["response-1"]["status"] == "delivered"


def test_reply_effects_are_local_and_idempotent():
    state = protocol_state()
    untouched = {
        key: copy.deepcopy(state[key])
        for key in ("artifacts", "attestations", "messages", "requests")
    }
    other = copy.deepcopy(state["work_items"]["unrelated"])
    result = apply_response(state, response())
    assert result["resolved_conditions"] == ["permission"]
    assert state["work_items"]["article"]["status"] == "open"
    assert state["work_items"]["unrelated"] == other
    assert all(state[key] == value for key, value in untouched.items())
    once = copy.deepcopy(state)
    assert apply_response(state, response()) == result
    assert state == once


def test_old_request_after_requirement_replacement_does_not_reopen_work():
    state = protocol_state()
    state["work_replacements"] = {"article": "article-r2"}
    state["work_items"]["article-r2"] = {
        **copy.deepcopy(state["work_items"]["article"]),
        "work_item_id": "article-r2",
        "requirement_version": 2,
    }
    before = copy.deepcopy(state)
    assert (
        match_response(state, state["condition_specs"]["permission"], response()).status
        == CheckStatus.NOT_APPLICABLE
    )
    assert not apply_response(state, response())["resolved_conditions"]
    assert state["work_replacements"] == before["work_replacements"]
    assert state["condition_specs"]["permission"]["status"] == "open"
    assert (
        state["condition_responses"]["response-1"]["checks"]["permission"]["status"]
        == "NOT_APPLICABLE"
    )


def test_alternate_provider_or_future_opportunity_prevents_permanent_unavailable():
    from proworksim.core.work import blocked_terminal

    state = protocol_state(providers=("licensor", "alternate"))
    state["work_items"].pop("unrelated")
    result = apply_response(state, response(status="unavailable", reference=None))
    assert result["checks"]["permission"]["status"] == "UNASSESSED"
    condition = state["condition_specs"]["permission"]
    assert condition["status"] == "unavailable"
    assert condition_has_future(state, condition)
    assert not blocked_terminal(state)
    condition["history"].append(
        {"event": "unavailability_recorded", "provider": "alternate", "at": 5}
    )
    assert not condition_has_future(state, condition)
    state["future_opportunities"] = [
        {
            "opportunity_id": "arrival-1",
            "condition_id": "permission",
            "provider": "alternate",
            "status": "pending",
        }
    ]
    assert condition_has_future(state, condition)
    assert not blocked_terminal(state)


def test_unavailable_recovers_only_with_new_request_and_true_evidence():
    from proworksim.core.work import blocked_terminal

    state = protocol_state()
    state["work_items"].pop("unrelated")
    condition = state["condition_specs"]["permission"]
    # No credential existed when the original provider was unable to answer.
    state["artifacts"]["permit"]["versions"]["v1"].pop("credential")
    state["attestations"].clear()
    apply_response(state, response(status="unavailable", reference=None))
    assert condition["status"] == "unavailable"
    assert state["work_items"]["article"]["status"] == "blocked"
    assert blocked_terminal(state)
    assert not apply_response(state, response(response_id="invented-followup"))[
        "resolved_conditions"
    ]
    # The finite environment explicitly schedules evidence becoming available.
    state["future_opportunities"] = [
        {
            "opportunity_id": "later-confirmation",
            "condition_id": "permission",
            "provider": "licensor",
            "status": "pending",
        }
    ]
    assert not blocked_terminal(state)
    record = Credential(
        reference={"object_id": "permit", "version_id": "v1"},
        project_id="p",
        requirement_dimension="license",
        requirement_version=1,
        work_nodes=("article",),
        period=None,
        purpose="publish",
        effective_at=5,
        confirmed_by="licensor",
        attestation_ref="later-signature",
    )
    confirm_credential(state, "licensor", record.reference, record)
    add_request(state, "request-2", "licensor")
    condition["request_id"] = "request-2"
    condition["history"].append({"event": "bound", "request_id": "request-2", "at": 5})
    state["future_opportunities"][0]["status"] = "consumed"
    result = apply_response(state, response(request_id="request-2", response_id="response-2"))
    assert result["resolved_conditions"] == ["permission"]
    assert condition["history"][1]["event"] == "response_received"
    assert state["raw_condition_responses"]["response-1"]["status"] == "unavailable"
    assert state["work_items"]["article"]["status"] == "open"
    assert not blocked_terminal(state)


def test_real_world_duplicate_reply_changes_neither_history_nor_authorization(tmp_path):
    root = compile_world(
        design(seed=941, delivery="file", information="clarification"), tmp_path / "world"
    )
    world = World(root)
    session = world.session()
    blocked = session.call(
        "block_work",
        work_item_id="work-1",
        reason="等待正式依据",
        kind="scope",
        requested_role="manager",
    )
    assert blocked["ok"], blocked
    sent = session.call(
        "mail_send",
        to="manager",
        topic="scope",
        body="请提供正式依据",
        work_item_id="work-1",
        blocker_id=blocked["result"]["blocker_id"],
    )
    assert sent["ok"], sent
    assert session.call("wait", ticks=2)["ok"]
    world.state = world.store.load()
    request = world.state["requests"][sent["result"]["message_id"]]
    assert request["conditions_satisfied"]
    before = copy.deepcopy(world.state)
    first = deliver_reply(world, {"request_id": request["request_id"]})
    second = deliver_reply(world, {"request_id": request["request_id"]})
    assert first == second
    assert first["duplicate"]
    assert world.state == before


def test_blocker_retry_preserves_old_reply_and_binds_new_request(tmp_path):
    root = compile_world(design(seed=943, scenario="unavailable"), tmp_path / "world")
    world = World(root)
    state = world.state
    item = state["work_items"]["work-1"]
    blocker = create_blocker(
        state, item, "scope", "manager", item["requirement_version"], "等待批准"
    )
    from proworksim.adapters.communication import register_request

    message = world._message("analyst", ["manager"], "scope", "请提供依据")
    message.update(work_item_id="work-1", topic="scope")
    first = register_request(
        state, item, "analyst", "manager", "scope", message, blocker["blocker_id"]
    )
    deliver_reply(world, {"request_id": first["request_id"]})
    assert state["blockers"][blocker["blocker_id"]]["status"] == "unavailable"
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="new request"):
        bind_request(state, blocker["blocker_id"], first["request_id"], "analyst", "work-1")
    assert state == before
    second_message = world._message("analyst", ["manager"], "scope", "请再次确认当前可得性")
    second_message.update(work_item_id="work-1", topic="scope")
    second = register_request(
        state, item, "analyst", "manager", "scope", second_message, blocker["blocker_id"]
    )
    current = state["blockers"][blocker["blocker_id"]]
    assert current["prior_request_ids"] == [first["request_id"]]
    assert current["request_id"] == second["request_id"]
    assert state["requests"][first["request_id"]]["status"] == "unavailable"
    assert item["status"] == "blocked"


def test_restoration_requires_formal_evidence_and_new_reply_to_reopen(tmp_path):
    from proworksim.adapters.communication import restore_information, register_request
    from proworksim.basis import issue_basis
    from proworksim.core.work import blocked_terminal

    root = compile_world(design(seed=947, scenario="unavailable"), tmp_path / "world")
    world = World(root)
    state = world.state
    item = state["work_items"]["work-1"]
    blocker = create_blocker(
        state, item, "scope", "manager", item["basis_requirement_version"], "等待正式依据"
    )
    cid = blocker["condition_id"]
    message = world._message("analyst", ["manager"], "scope", "请提供依据")
    message.update(work_item_id="work-1", topic="scope")
    first = register_request(
        state, item, "analyst", "manager", "scope", message, blocker["blocker_id"]
    )
    deliver_reply(world, {"request_id": first["request_id"]})
    assert blocked_terminal(state)
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="does not satisfy"):
        restore_information(
            world,
            "manager",
            "scope",
            "manager",
            {"artifact_id": "basis", "version_id": "v1"},
            [cid],
        )
    assert state == before
    # Controlled fixture arrival creates and formally signs a new immutable
    # evidence version; restore_information itself is unable to sign anything.
    signed = issue_basis(
        world.store,
        state,
        {"growth": 0.09},
        item["source_period"],
        item["basis_requirement_version"],
        [item["node_id"]],
        item.get("scenario_revision", 1),
    )
    reference = {"artifact_id": "basis", "version_id": signed["version_id"]}
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="institutional power"):
        restore_information(world, "analyst", "scope", "manager", reference, [cid])
    assert state == before
    files = copy.deepcopy(state["artifacts"])
    restore_information(world, "manager", "scope", "manager", reference, [cid])
    assert state["artifacts"] == files
    assert item["required_basis"] == reference
    assert item["required_credentials"] == [reference]
    assert item["status"] == "blocked"
    assert not blocked_terminal(state)
    # Replaying the old negative answer is still a no-op after arrival.
    again = deliver_reply(world, {"request_id": first["request_id"]})
    assert again["duplicate"]
    assert item["status"] == "blocked"
    message = world._message("analyst", ["manager"], "scope", "请提供新到达的确认")
    message.update(work_item_id="work-1", topic="scope")
    second = register_request(
        state, item, "analyst", "manager", "scope", message, blocker["blocker_id"]
    )
    delivered = deliver_reply(world, {"request_id": second["request_id"]})
    assert delivered["resolved_conditions"] == [cid]
    assert item["status"] == "open"
    assert not blocked_terminal(state)
    assert state["requests"][first["request_id"]]["status"] == "unavailable"


def test_scheduled_arrival_uses_real_event_and_preserves_block_until_new_reply(tmp_path):
    from proworksim.basis import issue_basis

    root = compile_world(design(seed=953, scenario="unavailable"), tmp_path / "world")
    world = World(root)
    session = world.session()
    result = session.call(
        "block_work",
        work_item_id="work-1",
        kind="scope",
        requested_role="manager",
        reason="当前缺乏批准",
    )
    assert result["ok"], result
    blocker_id = result["result"]["blocker_id"]
    sent = session.call(
        "mail_send",
        to="manager",
        topic="scope",
        body="请提供依据",
        work_item_id="work-1",
        blocker_id=blocker_id,
    )
    assert sent["ok"], sent
    assert session.call("wait", ticks=2)["ok"]
    assert session.observe()["terminal_reason"] == "blocked_unavailable"
    # The experiment controller creates a formally signed incoming version and
    # explicitly schedules its arrival. Subsequent changes go through the kernel.
    with world.store.lock():
        world.state = world.store.load()
        item = world.state["work_items"]["work-1"]
        condition_id = world.state["blockers"][blocker_id]["condition_id"]
        signed = issue_basis(
            world.store,
            world.state,
            {"growth": 0.09},
            item["source_period"],
            item["basis_requirement_version"],
            [item["node_id"]],
            item.get("scenario_revision", 1),
        )
        reference = {"artifact_id": "basis", "version_id": signed["version_id"]}
        world.state["future_opportunities"] = [
            {
                "opportunity_id": "arrival-1",
                "condition_id": condition_id,
                "provider": "manager",
                "status": "pending",
            }
        ]
        world._event(
            "information_arrival",
            {
                "actor": "manager",
                "topic": "scope",
                "provider": "manager",
                "reference": reference,
                "condition_ids": [condition_id],
                "opportunity_id": "arrival-1",
                "reason": "上游新确认已经签发，按计划送达",
            },
            delay=2,
        )
        world.store.save(world.state)
    assert session.observe()["terminal_reason"] is None
    bad = world.act(
        "analyst",
        "restore_information",
        {
            "topic": "scope",
            "provider": "manager",
            "reference": reference,
            "condition_ids": [condition_id],
        },
    )
    assert not bad["ok"]
    # A failed user action still advances time; the independently due event can
    # legitimately arrive in that interval. Waiting completes the scheduled tick.
    assert session.call("wait", ticks=2)["ok"]
    state = world.store.load()
    assert state["work_items"]["work-1"]["status"] == "blocked"
    assert state["requests"][sent["result"]["message_id"]]["status"] == "unavailable"
    event = next(e for e in state["event_history"] if e["kind"] == "information_arrival")
    assert event["transition"]["frame_respected"]
    assert state["future_opportunities"][0]["status"] == "consumed"
    notice_id = state["information_restorations"][0]["notice_message_ids"][0]
    notice = session.call("mail_read", message_id=notice_id)
    assert notice["ok"]
    assert notice["result"]["body"]["event"] == "information_available"
    assert "assumptions" not in notice["result"]["body"]
    assert notice["result"]["attachments"] == []
    assert session.observe()["terminal_reason"] is None
    fresh = session.call(
        "mail_send",
        to="manager",
        topic="scope",
        body="请提供新到达依据",
        work_item_id="work-1",
        blocker_id=blocker_id,
    )
    assert fresh["ok"], fresh
    assert session.call("wait", ticks=2)["ok"]
    state = world.store.load()
    assert state["work_items"]["work-1"]["status"] == "open"
    assert state["requests"][fresh["result"]["message_id"]]["conditions_satisfied"]
    assert not session.observe()["complete"]


def test_restore_one_work_does_not_change_other_work_provider_availability(tmp_path):
    from proworksim.adapters.communication import register_request, restore_information
    from proworksim.basis import issue_basis

    root = compile_world(design(seed=967, scenario="unavailable"), tmp_path / "world")
    world = World(root)
    state = world.state
    first = state["work_items"]["work-1"]
    other = {**copy.deepcopy(first), "work_item_id": "other-work", "node_id": "other-work"}
    state["work_items"]["other-work"] = other
    blocker = create_blocker(
        state, first, "scope", "manager", first["basis_requirement_version"], "本项资料不可得"
    )
    signed = issue_basis(
        world.store,
        state,
        {"growth": 0.09},
        first["source_period"],
        first["basis_requirement_version"],
        [first["node_id"], other["node_id"]],
        first.get("scenario_revision", 1),
    )
    reference = {"artifact_id": "basis", "version_id": signed["version_id"]}
    other["required_basis"] = reference
    untouched = copy.deepcopy(other)
    restore_information(world, "manager", "scope", "manager", reference, [blocker["condition_id"]])
    assert other == untouched
    assert state["provider_availability"]["manager"]["scope"] == {"work-1": True}
    message = world._message("analyst", ["manager"], "scope", "请求另一个工作的资料")
    message.update(work_item_id="other-work", topic="scope")
    request = register_request(state, other, "analyst", "manager", "scope", message)
    deliver_reply(world, {"request_id": request["request_id"]})
    assert state["requests"][request["request_id"]]["status"] == "unavailable"
    assert "analyst" not in state["artifacts"]["basis"].get("version_readers", {}).get(
        signed["version_id"], []
    )


@pytest.mark.parametrize(
    "old_status,current_status,expected_open",
    [("superseded", "accepted", True), ("accepted", "open", False)],
)
def test_reply_reopening_checks_current_predecessor_after_its_revision(
    old_status, current_status, expected_open
):
    state = protocol_state()
    item = state["work_items"]["article"]
    item["dependencies"] = ["predecessor"]
    state["work_replacements"] = {"predecessor": "predecessor@r2"}
    state["work_items"]["predecessor"] = {
        "work_item_id": "predecessor",
        "status": old_status,
    }
    state["work_items"]["predecessor@r2"] = {
        "work_item_id": "predecessor@r2",
        "status": current_status,
    }
    for wid, status in (("predecessor", old_status), ("predecessor@r2", current_status)):
        state["work_items"][wid]["requirement_version"] = 2 if "@r2" in wid else 1
        state["work_items"][wid]["submissions"] = (
            [
                {
                    "submission_id": wid + "-approved",
                    "review": {"decision": "accepted"},
                    "requirement_version": state["work_items"][wid]["requirement_version"],
                    "artifact_versions": {},
                }
            ]
            if status == "accepted"
            else []
        )
    rebuild_projections(state)
    predecessor_history = copy.deepcopy(state["work_items"]["predecessor"])
    result = apply_response(state, response())
    assert result["resolved_conditions"] == ["permission"]
    assert (item["status"] == "open") is expected_open
    assert item["dependencies"] == ["predecessor"]
    assert state["work_items"]["predecessor"] == predecessor_history
