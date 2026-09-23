"""Necessary scope, chronology and history guards for public review relations."""

import copy

import pytest

from proworksim.core.issues import derive_issue_view
from proworksim.core.transitions import preserve_history
from proworksim.core.world import WorldSpec
from proworksim.templates.research_review import package
from proworksim.workers.research_review import PublicReportWorker
from proworksim.world_core import WorldCore
from scripts.issue_relations_experiment import Fixture, must


def submitted_report(tmp_path):
    world = WorldCore.create(
        tmp_path / "world",
        WorldSpec(
            "located-negative-cases",
            {"author": {}, "reviewer": {}, "manager": {}},
            bootstrap_grants=[
                {"actor_id": "manager", "scope": "world", "power": "install_project"}
            ],
        ),
    )
    must(world.session("manager"), "install_project", package=package())
    author, reviewer = world.session("author", "REPORT"), world.session("reviewer", "REPORT")
    source = author.observe()["workspaces"]["REPORT"]["dataset"]
    must(
        author,
        "adopt",
        alias="dataset",
        object_id=source,
        version_id="v1",
        policy="fixed",
        work_ids=["REPORT::research"],
    )
    worker = PublicReportWorker(author)
    data, dependencies = worker.prepare("REPORT::research")
    submission = worker.deliver("REPORT::research", data, dependencies)
    oid, vid = next(iter(submission["artifact_versions"].items()))
    arguments = {
        "work_id": "REPORT::research",
        "submission_id": submission["submission_id"],
        "issue_key": "located-comment",
        "object_id": oid,
        "version_id": vid,
        "locator": ["report", "sections", 1, "body"],
        "description": "Check the located assertion against its original evidence",
        "evidence": dependencies,
        "blocking": True,
    }
    return world, author, reviewer, arguments


def read_required(reviewer, arguments):
    for reference in [
        {key: arguments[key] for key in ("object_id", "version_id")},
        *arguments["evidence"],
    ]:
        must(reviewer, "read_object", **reference)


def relations(world):
    state = world.store.load()
    return {key: state[key] for key in ("issues", "issue_responses", "issue_decisions")}


def test_metadata_and_old_version_read_do_not_count_as_actual_target_or_evidence_read(tmp_path):
    world, _, reviewer, args = submitted_report(tmp_path)
    must(
        reviewer, "inspect_submission", work_id=args["work_id"], submission_id=args["submission_id"]
    )
    must(reviewer, "read_object", object_id=args["object_id"], version_id="v1")
    target_not_read = reviewer.call("raise_issue", **args)
    assert target_not_read["ok"] is False
    assert target_not_read["error"]["rejection"]["code"] == "review_evidence_not_read"
    must(reviewer, "read_object", object_id=args["object_id"], version_id=args["version_id"])
    evidence_not_read = reviewer.call("raise_issue", **args)
    assert evidence_not_read["ok"] is False
    assert evidence_not_read["error"]["rejection"]["code"] == "review_evidence_not_read"
    assert not world.store.load()["issues"]
    for reference in args["evidence"]:
        must(reviewer, "read_object", **reference)
    assert reviewer.call("raise_issue", **args)["ok"] is True


def test_null_locator_cannot_create_an_unlocated_blocking_issue(tmp_path):
    world, _, reviewer, args = submitted_report(tmp_path)
    read_required(reviewer, args)
    result = reviewer.call("raise_issue", **{**args, "locator": None})
    assert result["ok"] is False
    assert not world.store.load()["issues"]


def test_same_relation_key_cannot_change_issue_response_or_decision_payload(tmp_path):
    fixture = Fixture(tmp_path, "report")
    original = relations(fixture.world)
    rejected = fixture.reviewer.call(
        "raise_issue", **{**fixture.issue_args[0], "description": "Changed interpretation"}
    )
    assert rejected["ok"] is False
    assert relations(fixture.world) == original
    _, response = fixture.partial()
    original = relations(fixture.world)
    rejected = fixture.author.call(
        "respond_issue",
        issue_id=fixture.issues[0]["issue_id"],
        response_key=response["response_key"],
        submission_id=fixture.partial_sub["submission_id"],
        body="Different response using the same identity",
        evidence=fixture.deps,
    )
    assert rejected["ok"] is False
    assert relations(fixture.world) == original
    must(fixture.reviewer, "decide_issue", **fixture.decision_args)
    original = relations(fixture.world)
    rejected = fixture.reviewer.call(
        "decide_issue", **{**fixture.decision_args, "reason": "Changed decision basis"}
    )
    assert rejected["ok"] is False
    assert relations(fixture.world) == original


def test_superseded_submission_response_cannot_close_a_current_issue(tmp_path):
    fixture = Fixture(tmp_path, "report")
    fixture.partial()
    must(
        fixture.author,
        "withdraw",
        work_id=fixture.work,
        submission_id=fixture.partial_sub["submission_id"],
        reason="A further concrete repair",
    )
    latest = fixture.deliver(fixture.good)
    fixture.read_submission(latest)
    before = relations(fixture.world)
    stale = fixture.reviewer.call("decide_issue", **fixture.decision_args)
    assert stale["ok"] is False
    assert relations(fixture.world) == before
    assert derive_issue_view(fixture.world.store.load())[fixture.issues[0]["issue_id"]][
        "blocks_approval"
    ]
    fresh = must(
        fixture.author,
        "respond_issue",
        issue_id=fixture.issues[0]["issue_id"],
        response_key="latest-response",
        submission_id=latest["submission_id"],
        body="The response is now bound to the actual current submission",
        evidence=fixture.deps,
    )
    must(
        fixture.reviewer,
        "decide_issue",
        **{
            **fixture.decision_args,
            "response_id": fresh["response_id"],
            "decision_key": "latest-decision",
        },
    )
    views = derive_issue_view(fixture.world.store.load())
    assert views[fixture.issues[0]["issue_id"]]["status"] == "resolved"
    assert views[fixture.issues[1]["issue_id"]]["blocks_approval"]


def test_unknown_and_other_project_issue_are_policy_rejections_without_state_effect(tmp_path):
    world, author, reviewer, args = submitted_report(tmp_path)
    read_required(reviewer, args)
    issue = must(reviewer, "raise_issue", **args)
    must(world.session("manager"), "install_project", package=package("OTHER"))
    other_author = world.session("author", "OTHER")
    before = relations(world)
    for port, iid in ((author, "nonexistent-issue"), (other_author, issue["issue_id"])):
        result = port.call(
            "respond_issue",
            issue_id=iid,
            response_key="scope-probe",
            submission_id=args["submission_id"],
            body="No scope override",
            evidence=args["evidence"],
        )
        assert result["ok"] is False
        assert result["error"]["rejection"]["category"] == "policy_error"
        assert result["error"]["rejection"]["code"] == "issue_scope_mismatch"
        assert relations(world) == before


def test_actual_read_does_not_replace_review_authority_or_responsible_ownership(tmp_path):
    world, author, reviewer, args = submitted_report(tmp_path)
    read_required(author, args)
    assert author.call("raise_issue", **args)["ok"] is False
    assert not world.store.load()["issues"]
    read_required(reviewer, args)
    issue = must(reviewer, "raise_issue", **args)
    wrong_actor = reviewer.call(
        "respond_issue",
        issue_id=issue["issue_id"],
        response_key="not-owner",
        submission_id=args["submission_id"],
        body="A reviewer cannot replace the responsible author",
        evidence=args["evidence"],
    )
    assert wrong_actor["ok"] is False
    assert not world.store.load()["issue_responses"]


def test_all_three_relation_histories_reject_mutation_or_removal(tmp_path):
    fixture = Fixture(tmp_path, "report")
    fixture.partial()
    must(fixture.reviewer, "decide_issue", **fixture.decision_args)
    original = fixture.world.store.load()
    for registry in ("issues", "issue_responses", "issue_decisions"):
        key = next(iter(original[registry]))
        altered = copy.deepcopy(original)
        altered[registry][key]["at"] += 1
        with pytest.raises(ValueError, match="Historical located review fact changed"):
            preserve_history(original, altered)
        removed = copy.deepcopy(original)
        del removed[registry][key]
        with pytest.raises(ValueError, match="Historical located review fact changed"):
            preserve_history(original, removed)
    assert fixture.world.store.load() == original
