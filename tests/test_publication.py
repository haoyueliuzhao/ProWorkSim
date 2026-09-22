"""A second object vocabulary exercises the same state and file action engine."""

import copy
import json

import pytest

from proworksim.core.rules import registered_applicability
from proworksim.core.types import CheckStatus
from proworksim.domains.publication import (
    SOURCE_REF,
    PublicationWorld,
    compile_publication,
    evaluate_publication,
    publication_context,
)


def action(world, actor, name, **arguments):
    result = world.act(actor, name, arguments)
    assert result["ok"], result
    return result["result"]


def write_draft(
    world, actor, policy_version="v1", *, body="READY. Synthetic demonstration", source=None
):
    return action(
        world,
        actor,
        "write_file",
        artifact_id="draft",
        content=json.dumps(
            {
                "title": "Release notice",
                "body": body,
                "source_ref": SOURCE_REF if source is None else source,
            }
        ),
        dependencies=[
            SOURCE_REF,
            {"artifact_id": "editorial_policy", "version_id": policy_version},
        ],
    )


def policy_revision(world, editor, work_id="publish-note", public=False):
    reference = action(
        world,
        editor,
        "confirm",
        required_phrases=["READY", "Revised edition"],
        requirement_version=2,
        public=public,
    )["policy_ref"]
    work_id = action(
        world,
        editor,
        "revise",
        work_item_id=work_id,
        policy_version=reference["version_id"],
        reason="Revise publication edition",
    )["replacements"][work_id]
    return work_id, reference


@pytest.mark.parametrize(
    "actors",
    [
        {"author": "author", "editor": "editor"},
        {"author": "researcher-61", "editor": "signatory-84"},
    ],
)
def test_publication_reuses_files_submit_withdraw_review_with_arbitrary_role_names(
    tmp_path, actors
):
    world = PublicationWorld(compile_publication(tmp_path / "publication", actors))
    author = actors["author"]
    assert action(world, author, "read_file", artifact_id="source_note")["version_id"] == "v1"
    action(world, author, "read_file", artifact_id="editorial_policy")
    write_draft(world, author)
    first = action(world, author, "submit", work_item_id="publish-note")
    action(
        world,
        author,
        "withdraw",
        work_item_id="publish-note",
        submission_id=first["submission_id"],
        reason="Check final wording",
    )
    historical = copy.deepcopy(world.store.load()["work_items"]["publish-note"]["submissions"][0])
    second = action(world, author, "submit", work_item_id="publish-note")
    action(world, author, "wait", ticks=2)
    state = world.store.load()
    assert state["work_items"]["publish-note"]["submissions"][0] == historical
    assert first["submission_id"] != second["submission_id"]
    assert world.session().observe()["complete"]
    assert evaluate_publication(world)["passed"]
    assert all(
        record.get("transition", {}).get("frame_respected", True)
        for record in state["interactions"]
    )


def test_requirement_revision_keeps_draft_and_historical_approval_but_old_credential_is_inapplicable(
    tmp_path,
):
    world = PublicationWorld(compile_publication(tmp_path / "publication"))
    write_draft(world, "author")
    action(world, "author", "submit", work_item_id="publish-note")
    action(world, "author", "wait", ticks=2)
    before = world.store.load()
    draft = world.store.content(before["artifacts"]["draft"])
    review = copy.deepcopy(before["work_items"]["publish-note"]["submissions"][0]["review"])
    new_id, reference = policy_revision(world, "editor")
    after = world.store.load()
    assert world.store.content(after["artifacts"]["draft"]) == draft
    assert (
        after["artifacts"]["draft"]["current_version"]
        == before["artifacts"]["draft"]["current_version"]
    )
    assert after["work_items"]["publish-note"]["submissions"][0]["review"] == review
    assert evaluate_publication(world, "publish-note")["passed"]
    assert not evaluate_publication(world, "publish-note")["currently_applicable"]
    old_ref = {"artifact_id": "editorial_policy", "version_id": "v1"}
    assert (
        registered_applicability(
            after, old_ref, publication_context(after, after["work_items"][new_id])
        ).status
        == CheckStatus.FAIL
    )
    assert (
        action(world, "author", "read_file", artifact_id="editorial_policy", version_id="v1")[
            "version_id"
        ]
        == "v1"
    )
    assert not world.act(
        "author",
        "read_file",
        {"artifact_id": "editorial_policy", "version_id": reference["version_id"]},
    )["ok"]
    request = action(world, "author", "request", work_item_id=new_id)
    response = action(world, "editor", "reply", request_id=request["request_id"])
    assert response["satisfaction"]["resolved_conditions"]
    write_draft(world, "author", reference["version_id"], body="READY. Revised edition")
    action(world, "author", "submit", work_item_id=new_id)
    action(world, "author", "wait", ticks=2)
    assert evaluate_publication(world)["passed"]


def test_old_response_retains_history_and_exact_access_without_resolving_new_obligation(tmp_path):
    world = PublicationWorld(compile_publication(tmp_path / "publication"))
    old = action(world, "author", "request", work_item_id="publish-note")
    new_id, new_ref = policy_revision(world, "editor")
    new = action(world, "author", "request", work_item_id=new_id)
    response = action(world, "editor", "reply", request_id=old["request_id"])
    state = world.store.load()
    assert response["satisfaction"]["resolved_conditions"] == []
    assert state["work_items"][new_id]["status"] == "blocked"
    assert state["condition_specs"][new["condition_id"]]["status"] == "open"
    assert state["requests"][old["request_id"]]["status"] == "delivered"
    assert not world.act(
        "author",
        "read_file",
        {"artifact_id": "editorial_policy", "version_id": new_ref["version_id"]},
    )["ok"]
    action(world, "editor", "reply", request_id=new["request_id"])
    assert world.store.load()["work_items"][new_id]["status"] == "open"


def test_wrong_content_is_writable_and_can_be_approved_but_independent_check_fails(tmp_path):
    world = PublicationWorld(compile_publication(tmp_path / "publication"))
    write_draft(
        world,
        "author",
        body="This unsupported claim omits required facts",
        source={"artifact_id": "invented", "version_id": "v99"},
    )
    submitted = action(world, "author", "submit", work_item_id="publish-note")
    # Direct organizational approval intentionally does not invoke the external Q.
    action(
        world,
        "editor",
        "approve",
        work_item_id="publish-note",
        submission_id=submitted["submission_id"],
    )
    result = evaluate_publication(world)
    assert result["business_accepted"] and not result["passed"]
    assert {check["name"] for check in result["checks"] if check["status"] == "FAIL"} == {
        "source_reference",
        "required_phrases",
    }


def test_formal_confirmation_rejects_unauthorized_actor_without_fabricating_version(tmp_path):
    world = PublicationWorld(compile_publication(tmp_path / "publication"))
    before = world.store.load()
    result = world.act(
        "author", "confirm", {"required_phrases": ["Fake authorization"], "requirement_version": 2}
    )
    assert not result["ok"]
    after = world.store.load()
    assert after["artifacts"] == before["artifacts"]
    assert after["attestations"] == before["attestations"]
    assert after["clock"] == before["clock"] + 1


def test_stale_policy_can_be_written_and_submitted_but_finite_staff_review_rejects_it(tmp_path):
    world = PublicationWorld(compile_publication(tmp_path / "publication"))
    new_id, _ = policy_revision(world, "editor", public=True)
    write_draft(world, "author", "v1")
    action(world, "author", "submit", work_item_id=new_id)
    action(world, "author", "wait", ticks=2)
    state = world.store.load()
    assert state["work_items"][new_id]["status"] == "revision_required"
    assert not evaluate_publication(world)["passed"]
    assert state["artifacts"]["draft"]["versions"]["v2"]["derived_from"][-1]["version_id"] == "v1"


def test_duplicate_reply_preserves_delivery_access_conditions_and_work(tmp_path):
    world = PublicationWorld(compile_publication(tmp_path / "publication"))
    request = action(world, "author", "request", work_item_id="publish-note")
    first = action(world, "editor", "reply", request_id=request["request_id"])
    before = world.store.load()
    second = action(world, "editor", "reply", request_id=request["request_id"])
    after = world.store.load()
    assert first == second
    for key in (
        "messages",
        "requests",
        "condition_specs",
        "condition_responses",
        "work_items",
        "access_grants",
        "artifacts",
    ):
        assert after[key] == before[key]
    assert after["clock"] == before["clock"] + 1
