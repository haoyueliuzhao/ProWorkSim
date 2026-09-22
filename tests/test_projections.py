"""Disposable-view checks against canonical work, condition and receipt facts."""

import copy

import pytest

from proworksim.core.conditions import apply_response, match_response
from proworksim.core.projections import (
    corrupt_projection_caches,
    derive_condition_view,
    derive_current_work_view,
    rebuild_projections,
    record_artifact_edit,
    remove_projection_caches,
)
from proworksim.core.work import (
    approve_submission,
    revise_requirement,
    submit_work,
    withdraw_submission,
)


def fixture():
    state = {
        "schema_version": "0.5",
        "clock": 1,
        "roles": [{"role_id": "worker"}, {"role_id": "editor"}],
        "organization": {
            "grants": [
                {"actor_id": "editor", "power": "approve", "subject": "deliverable"},
                {"actor_id": "editor", "power": "revise_requirement", "subject": "*"},
            ]
        },
        "artifacts": {
            aid: {"current_version": "v1", "versions": {"v1": {"logical_time": 0}}}
            for aid in ("source", "draft", "index")
        },
        "work_items": {
            wid: {
                "work_item_id": wid,
                "node_id": wid,
                "owner_role": "worker",
                "requirement_version": 1,
                "dependencies": deps,
                "deliverables": [aid],
                "submissions": [],
                "activated_at": 0,
            }
            for wid, aid, deps in (("a", "draft", []), ("b", "index", ["a"]))
        },
        "messages": [
            {"message_id": "req", "sender": "worker", "recipients": ["editor"], "work_item_id": "a"}
        ],
        "requests": {
            "req": {
                "request_id": "req",
                "work_item_id": "a",
                "requirement_version": 1,
                "requested_role": "editor",
            }
        },
        "condition_specs": {
            "need-source": {
                "condition_id": "need-source",
                "blocker_id": "legacy-block",
                "work_item_id": "a",
                "requirement_version": 1,
                "providers": ["editor"],
                "request_id": "req",
                "purpose": "source",
                "expected_version": 1,
                "evidence_spec": {
                    "kind": "version",
                    "reference": {"artifact_id": "source", "version_id": "v1"},
                },
                "history": [{"event": "created", "request_id": "req", "at": 0}],
            }
        },
        "events": [],
    }
    rebuild_projections(state)
    return state


def response(**changes):
    return {
        "response_id": "reply",
        "request_id": "req",
        "responder": "editor",
        "work_item_id": "a",
        "requirement_version": 1,
        "purpose": "source",
        "condition_version": 1,
        "reference": {"artifact_id": "source", "version_id": "v1"},
        "status": "delivered",
        **changes,
    }


def facts(state):
    result = copy.deepcopy(state)
    remove_projection_caches(result)
    return result


def snapshot(stage):
    state = fixture()
    if stage != "pending_reply":
        apply_response(state, response())
    if stage in {"in_review", "withdrawn", "accepted", "revised"}:
        submitted = submit_work(state, "worker", "a", {"draft": "v1"})
        if stage == "withdrawn":
            withdraw_submission(state, "worker", "a", submitted["submission_id"], "Revise text")
        if stage == "accepted":
            approve_submission(state, "editor", "a", submitted["submission_id"])
        if stage == "revised":
            revise_requirement(state, ["a"], {"goal": "New edition"}, "editor", "Revision")
    return state


@pytest.mark.parametrize(
    "stage", ["pending_reply", "resolved", "in_review", "withdrawn", "accepted", "revised"]
)
@pytest.mark.parametrize("damage", [remove_projection_caches, corrupt_projection_caches])
def test_missing_or_false_caches_do_not_change_query_or_rebuilt_facts(stage, damage):
    state = snapshot(stage)
    expected = (derive_condition_view(state), derive_current_work_view(state))
    base = facts(state)
    damage(state)
    damaged = copy.deepcopy(state)
    assert (derive_condition_view(state), derive_current_work_view(state)) == expected
    assert state == damaged
    rebuild_projections(state)
    assert facts(state) == base
    once = copy.deepcopy(state)
    rebuild_projections(state)
    assert state == once


def test_false_legacy_blocker_cannot_enable_submission_or_disable_current_work():
    state = fixture()
    state["blockers"]["legacy-block"]["status"] = "resolved"
    state["work_items"]["a"]["status"] = "open"
    with pytest.raises(ValueError, match="open for submission"):
        submit_work(state, "worker", "a", {"draft": "v1"})
    apply_response(state, response())
    state["blockers"]["legacy-block"]["status"] = "unavailable"
    state["work_items"]["a"]["status"] = "blocked"
    submission = submit_work(state, "worker", "a", {"draft": "v1"})
    state["work_items"]["a"]["status"] = "accepted"
    assert "withdraw" in derive_current_work_view(state)["a"]["enabled_actions"]
    withdraw_submission(state, "worker", "a", submission["submission_id"], "Rewrite")


def test_replacement_predecessor_approval_is_required_even_when_cache_says_accepted():
    state = snapshot("accepted")
    new_id = revise_requirement(state, ["a"], {"goal": "Next edition"}, "editor", "Edition")["a"]
    state["work_items"][new_id]["status"] = "accepted"
    view = derive_current_work_view(state)
    assert view["a"]["status"] == "accepted" and not view["a"]["is_current"]
    assert view["b"]["status"] == "waiting_dependencies"
    assert view["b"]["enabled_actions"] == []


def test_response_context_pins_facts_and_cannot_be_forged_by_caller():
    state = fixture()
    new_id = revise_requirement(state, ["a"], {"goal": "New edition"}, "editor", "Edition")["a"]
    result = apply_response(
        state, response(receipt_context={"work_replacements": {}}, received_sequence=-1)
    )
    assert not result["resolved_conditions"]
    stored = state["raw_condition_responses"]["reply"]
    assert stored["receipt_context"]["work_replacements"]["a"] == new_id
    assert stored["received_sequence"] == 1
    assert derive_current_work_view(state)[new_id]["status"] == "open"


def test_received_wrong_response_is_preserved_without_satisfaction():
    state = fixture()
    result = apply_response(state, response(condition_version=2))
    assert not result["resolved_conditions"]
    assert state["raw_condition_responses"]["reply"]["condition_version"] == 2
    assert derive_condition_view(state)["need-source"]["status"] == "open"
    before = copy.deepcopy(state)
    assert (
        match_response(state, state["condition_specs"]["need-source"], response()).status.value
        == "PASS"
    )
    assert state == before


def test_edit_fact_invalidates_pending_and_does_not_write_domain_bytes():
    state = snapshot("in_review")
    artifacts = copy.deepcopy(state["artifacts"])
    record_artifact_edit(state, "worker", "draft", "v2")
    assert state["artifacts"] == artifacts
    view = derive_current_work_view(state)["a"]
    assert view["status"] == "in_progress" and view["enabled_actions"] == ["submit"]
    assert state["work_items"]["a"]["submissions"][0]["artifact_versions"] == {"draft": "v1"}


def test_same_tick_later_confirmation_cannot_rewrite_old_reply_outcome():
    from proworksim.core.rules import confirm_credential
    from proworksim.core.types import Credential

    state = fixture()
    state["organization"]["grants"].append(
        {"actor_id": "editor", "power": "confirm", "subject": "license"}
    )
    condition = state["condition_specs"]["need-source"]
    condition.update(
        evidence_spec={
            "kind": "credential",
            "reference": {"artifact_id": "source", "version_id": "v1"},
        },
        required_power="confirm",
        subject="license",
        context={
            "project_id": "p",
            "work_id": "a",
            "work_node": "a",
            "requirement_dimension": "license",
            "requirement_version": 1,
            "period": None,
            "purpose": "publish",
            "at": 1,
        },
    )
    first = apply_response(state, response())
    assert first["checks"]["need-source"]["status"] == "UNASSESSED"
    record = Credential(
        reference={"object_id": "source", "version_id": "v1"},
        project_id="p",
        requirement_dimension="license",
        requirement_version=1,
        work_nodes=("a",),
        period=None,
        purpose="publish",
        effective_at=1,
        confirmed_by="editor",
        attestation_ref="signed-after-receipt",
    )
    confirm_credential(state, "editor", record.reference, record)
    rebuild_projections(state)
    assert state["condition_responses"]["reply"]["checks"]["need-source"]["status"] == "UNASSESSED"
    assert derive_condition_view(state)["need-source"]["status"] == "open"
    assert (
        match_response(state, condition, response(response_id="new-response")).status.value
        == "PASS"
    )


def test_pending_submission_survives_predecessor_replacement_and_can_be_withdrawn():
    state = snapshot("accepted")
    submitted = submit_work(state, "worker", "b", {"index": "v1"})
    pinned = copy.deepcopy(state["work_items"]["b"]["submissions"][-1]["artifact_versions"])
    revise_requirement(state, ["a"], {"goal": "Replace prerequisite"}, "editor", "New edition")
    view = derive_current_work_view(state)["b"]
    assert view["status"] == "waiting_dependencies"
    assert view["submission_state"] == "pending"
    assert view["pending_submission_id"] == submitted["submission_id"]
    assert view["enabled_actions"] == ["withdraw"]
    with pytest.raises(ValueError, match="dependencies"):
        approve_submission(state, "editor", "b", submitted["submission_id"])
    withdraw_submission(
        state, "worker", "b", submitted["submission_id"], "Revise after prerequisite"
    )
    view = derive_current_work_view(state)["b"]
    assert view["submission_state"] == "withdrawn" and view["pending_submission_id"] is None
    assert state["work_items"]["b"]["submissions"][-1]["artifact_versions"] == pinned


@pytest.mark.parametrize(
    "change", ["artifact_version", "required_credentials", "requirement_version"]
)
def test_changed_approval_references_disable_approval_without_erasing_pending(change):
    state = snapshot("in_review")
    item = state["work_items"]["a"]
    submitted = copy.deepcopy(item["submissions"][-1])
    if change == "artifact_version":
        state["artifacts"]["draft"]["versions"]["v2"] = {"logical_time": 1}
        state["artifacts"]["draft"]["current_version"] = "v2"
    elif change == "required_credentials":
        item["required_credentials"] = [{"artifact_id": "source", "version_id": "v1"}]
    else:
        item["requirement_version"] = 2
    view = derive_current_work_view(state)["a"]
    assert view["submission_state"] == "pending"
    assert view["pending_submission_id"] == submitted["submission_id"]
    assert not view["submission_versions_current"]
    assert view["enabled_actions"] == ["withdraw"]
    with pytest.raises(ValueError, match="no longer current"):
        approve_submission(state, "editor", "a", submitted["submission_id"])
    assert item["submissions"][-1] == submitted
