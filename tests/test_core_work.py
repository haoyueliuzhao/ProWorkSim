"""Institutional lifecycle properties, independent of operating-domain objects."""

import copy

import pytest

from proworksim.core.projections import rebuild_projections
from proworksim.core.work import (
    approve_submission,
    blocked_terminal,
    current_id,
    current_work_items,
    revise_requirement,
    submit_work,
    withdraw_submission,
)


def world_state(worker="writer-zoe", coordinator="desk-lee", reviewer="editor-ren"):
    def work(work_id, deliverable):
        return {
            "work_item_id": work_id,
            "node_id": work_id,
            "requirement_version": 1,
            "owner_role": worker,
            "status": "open",
            "dependencies": [],
            "deliverables": [deliverable],
            "goal": "Prepare publication",
            "visible_requirements": ["Use approved release scope"],
            "required_credentials": [],
            "submissions": [],
            "blocker_ids": [],
        }

    state = {
        "clock": 4,
        "roles": [{"role_id": role} for role in (worker, coordinator, reviewer)],
        "organization": {
            "grants": [
                {"actor_id": coordinator, "power": "revise_requirement", "subject": "*"},
                {"actor_id": reviewer, "power": "approve", "subject": "deliverable"},
            ]
        },
        "work_items": {"release": work("release", "draft"), "other": work("other", "index")},
        "artifacts": {
            aid: {
                "current_version": "v1",
                "versions": {
                    "v1": {
                        "sha256": f"immutable-{aid}",
                        "review_status": "unreviewed",
                        "status": "draft",
                    }
                },
            }
            for aid in ("draft", "index")
        },
        "events": [],
    }
    rebuild_projections(state)
    return state


def submit(state, actor="writer-zoe", work_id="release"):
    aid = state["work_items"][work_id]["deliverables"][0]
    return submit_work(state, actor, work_id, {aid: "v1"}, context_versions={aid: "v1"})


@pytest.mark.parametrize(
    "identities",
    [("writer-zoe", "desk-lee", "editor-ren"), ("agent-a", "principal-z", "assessor-x")],
)
def test_powers_survive_role_renaming_and_bad_content_can_be_approved(identities):
    worker, coordinator, reviewer = identities
    state = world_state(*identities)
    # The opaque bytes stand for an intentionally incorrect draft. Neither
    # submission nor an authorized institutional approval invokes a quality oracle.
    before_hash = state["artifacts"]["draft"]["versions"]["v1"]["sha256"]
    sub = submit(state, worker)
    approve_submission(state, reviewer, "release", sub["submission_id"])
    old = copy.deepcopy(state["work_items"]["release"])
    replacement = revise_requirement(
        state, ["release"], {"requirements": {"edition": "revised"}}, coordinator, "Change edition"
    )["release"]
    assert old["status"] == state["work_items"]["release"]["status"] == "accepted"
    assert (
        old["submissions"][0]["review"]
        == state["work_items"]["release"]["submissions"][0]["review"]
    )
    assert state["work_items"]["release"]["applicability"] == "superseded_requirements"
    assert state["work_items"][replacement]["submissions"] == []
    assert state["artifacts"]["draft"]["versions"]["v1"]["sha256"] == before_hash


def test_explicit_revision_target_preserves_unrelated_work_and_all_artifacts():
    state = world_state()
    other, artifacts = (
        copy.deepcopy(state["work_items"]["other"]),
        copy.deepcopy(state["artifacts"]),
    )
    old = copy.deepcopy(state["work_items"]["release"])
    new_id = revise_requirement(
        state,
        ["release"],
        {"required_credentials": [{"artifact_id": "draft", "version_id": "v1"}]},
        "desk-lee",
        "New release scope",
    )["release"]
    assert state["work_items"]["other"] == other
    assert state["artifacts"] == artifacts
    for key in ("goal", "visible_requirements", "deliverables", "required_credentials"):
        assert state["work_items"]["release"][key] == old[key]
    assert current_id(state, "release") == new_id
    assert {item["work_item_id"] for item in current_work_items(state)} == {new_id, "other"}


def test_scoped_revision_authority_cannot_partially_modify_multi_target_request():
    state = world_state()
    state["organization"]["grants"][0]["work_nodes"] = ["release"]
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="institutional power"):
        revise_requirement(state, ["release", "other"], {"goal": "new"}, "desk-lee", "Both")
    assert state == before


@pytest.mark.parametrize("updates", [{"growth_delta": 0.02}, {"status": "accepted"}, {}])
def test_revision_rejects_procedural_or_reserved_fields_without_mutation(updates):
    state = world_state()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="declarative"):
        revise_requirement(state, ["release"], updates, "desk-lee", "Invalid operation")
    assert state == before


def test_pending_revision_pins_history_and_cannot_be_withdrawn_or_approved_as_current():
    state = world_state()
    sub = submit(state)
    revision = revise_requirement(
        state, ["release"], {"requirements": {"edition": "new"}}, "desk-lee", "New requirement"
    )["release"]
    recorded = state["work_items"]["release"]["submissions"][0]
    for key in ("artifact_versions", "answer", "at", "requirement_snapshot", "context_versions"):
        assert recorded[key] == sub[key]
    assert recorded["review"] is None and recorded["invalidated"]
    assert state["work_items"][revision]["status"] == "open"
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="current obligation"):
        withdraw_submission(state, "writer-zoe", "release", sub["submission_id"], "Too late")
    with pytest.raises(ValueError, match="current obligation"):
        approve_submission(state, "editor-ren", "release", sub["submission_id"])
    assert state == before


def test_withdraw_resubmit_preserves_original_submission_and_decision():
    state = world_state()
    first = submit(state)
    withdraw_submission(state, "writer-zoe", "release", first["submission_id"], "Need revision")
    withdrawn = copy.deepcopy(state["work_items"]["release"]["submissions"][0])
    second = submit(state)
    approve_submission(state, "editor-ren", "release", second["submission_id"])
    assert first["submission_id"] != second["submission_id"]
    assert state["work_items"]["release"]["submissions"][0] == withdrawn
    assert withdrawn["artifact_versions"] == first["artifact_versions"]
    assert withdrawn["review"]["decision"] == "withdrawn"


def test_artifact_edit_prevents_accidental_approval_of_outdated_pinned_delivery():
    state = world_state()
    sub = submit(state)
    state["artifacts"]["draft"]["versions"]["v2"] = {"sha256": "second-version"}
    state["artifacts"]["draft"]["current_version"] = "v2"
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="no longer current"):
        approve_submission(state, "editor-ren", "release", sub["submission_id"])
    assert state == before


def test_submission_extensions_cannot_overwrite_identity_or_pinned_versions():
    state = world_state()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="overwrite core"):
        submit_work(
            state, "writer-zoe", "release", {"draft": "v1"}, extensions={"actor_id": "forged"}
        )
    assert state == before


def test_current_dependency_must_be_reaccepted_after_replacement():
    state = world_state()
    sub = submit(state)
    approve_submission(state, "editor-ren", "release", sub["submission_id"])
    state["work_items"]["other"]["dependencies"] = ["release"]
    revise_requirement(state, ["release"], {"goal": "Revise scope"}, "desk-lee", "New edition")
    with pytest.raises(ValueError, match="dependencies"):
        submit(state, work_id="other")


def test_unavailable_provider_is_not_terminal_with_alternative_or_future_arrival():
    state = world_state()
    state["work_items"].pop("other")
    item = state["work_items"]["release"]
    item.update(status="blocked", blocker_ids=["b1"])
    state["blockers"] = {"b1": {"status": "unavailable", "condition_id": "c1"}}
    condition = {
        "condition_id": "c1",
        "work_item_id": "release",
        "status": "unavailable",
        "providers": ["desk-lee", "editor-ren"],
        "unavailable_providers": ["desk-lee"],
        "history": [{"event": "unavailability_recorded", "provider": "desk-lee", "at": 4}],
    }
    state["condition_specs"] = {"c1": condition}
    assert not blocked_terminal(state)
    condition["history"].append(
        {"event": "unavailability_recorded", "provider": "editor-ren", "at": 4}
    )
    assert blocked_terminal(state)
    state["future_opportunities"] = [
        {"opportunity_id": "later", "condition_id": "c1", "status": "pending"}
    ]
    assert not blocked_terminal(state)
    state["future_opportunities"][0]["status"] = "consumed"
    assert blocked_terminal(state)


def test_resolved_condition_facts_are_not_rewritten_by_revision():
    from proworksim.blockers import create_blocker, bind_request, resolve_for_reply

    state = world_state()
    state["messages"] = [
        {"message_id": "r1", "sender": "writer-zoe", "recipients": ["desk-lee"], "subject": "scope"}
    ]
    blocker = create_blocker(
        state, state["work_items"]["release"], "scope", "desk-lee", 1, "Need approval"
    )
    bind_request(state, blocker["blocker_id"], "r1", "writer-zoe", "release")
    resolve_for_reply(state, "r1", "desk-lee", "scope", 1, {"message_id": "reply"})
    condition = copy.deepcopy(state["condition_specs"][blocker["condition_id"]])
    revise_requirement(state, ["release"], {"goal": "Revise scope"}, "desk-lee", "New edition")
    assert state["condition_specs"][blocker["condition_id"]] == condition
    assert state["blockers"][blocker["blocker_id"]]["status"] == "resolved"


def test_independent_work_actions_commute_in_business_state():
    forward, reverse = world_state(), world_state()
    for state, order in ((forward, ["release", "other"]), (reverse, ["other", "release"])):
        for work_id in order:
            revise_requirement(
                state, [work_id], {"requirements": {"edition": "next"}}, "desk-lee", "New edition"
            )
        # Event order truthfully differs. The independent business state does not.
        state.pop("requirement_events")
    assert forward == reverse


def test_future_opportunity_for_unrelated_condition_does_not_hide_terminal_block():
    state = world_state()
    state["work_items"].pop("other")
    state["work_items"]["release"].update(status="blocked", blocker_ids=["b1"])
    state["blockers"] = {"b1": {"status": "unavailable", "condition_id": "c1"}}
    state["condition_specs"] = {
        "c1": {
            "condition_id": "c1",
            "work_item_id": "release",
            "history": [{"event": "unavailability_recorded", "provider": "desk-lee", "at": 4}],
            "status": "unavailable",
            "providers": ["desk-lee"],
            "unavailable_providers": ["desk-lee"],
        }
    }
    state["future_opportunities"] = [{"condition_id": "unrelated", "status": "pending"}]
    assert blocked_terminal(state)


def test_pending_approval_cannot_use_an_old_accepted_predecessor_after_replacement():
    state = world_state()
    initial = submit(state)
    approve_submission(state, "editor-ren", "release", initial["submission_id"])
    state["work_items"]["other"]["dependencies"] = ["release"]
    pending = submit(state, work_id="other")
    replacement = revise_requirement(
        state, ["release"], {"goal": "New release requirement"}, "desk-lee", "Requirement changed"
    )["release"]
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="dependencies"):
        approve_submission(state, "editor-ren", "other", pending["submission_id"])
    assert state == before
    replacement_submission = submit(state, work_id=replacement)
    approve_submission(state, "editor-ren", replacement, replacement_submission["submission_id"])
    approve_submission(state, "editor-ren", "other", pending["submission_id"])
    assert state["work_items"]["other"]["status"] == "accepted"
