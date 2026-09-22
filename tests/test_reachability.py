from dataclasses import replace

import pytest

from proworksim.workflow import EventRule, WorkNode, WorkflowSpec, make_workflow, validate_workflow


def flow(nodes, rules=()):
    return WorkflowSpec("reachability-test", tuple(nodes), tuple(rules)).public_spec()


def test_audit_work_release_mutual_wait_is_rejected_with_reasons():
    workflow = flow(
        [WorkNode("A", ("model",), release="R")],
        [EventRule("publish-R", ("A",), (), "R")],
    )
    with pytest.raises(ValueError) as raised:
        validate_workflow(workflow)
    message = str(raised.value)
    assert "Unreachable" in message
    assert "work A: waiting for release 'R'" in message
    assert "event publish-R: waiting for accepted work ['A']" in message


def test_reachable_prefix_does_not_hide_mutually_waiting_releases():
    workflow = flow(
        [
            WorkNode("entry", ("model",)),
            WorkNode("A", ("memo",), ("entry",), "R"),
            WorkNode("B", ("note",), ("entry",), "S"),
        ],
        [
            EventRule("publish-R", ("B",), (), "R"),
            EventRule("publish-S", ("A",), (), "S"),
        ],
    )
    with pytest.raises(ValueError, match="work A.*work B.*event publish-R.*event publish-S"):
        validate_workflow(workflow)


def test_duplicate_release_producers_are_alternatives_and_allow_revision_entry():
    workflow = flow(
        [
            WorkNode("draft", ("model",)),
            WorkNode("review", ("memo",), ("draft",), "review-ready"),
            WorkNode("revision", ("model",), ("review",), "revise"),
        ],
        [
            EventRule("entry", ("draft",), (), "review-ready"),
            EventRule("request-changes", ("review",), (), "revise"),
            EventRule("review-revision", ("revision",), (), "review-ready"),
        ],
    )
    validate_workflow(workflow)


def test_unconditional_release_is_an_entry():
    validate_workflow(
        flow(
            [WorkNode("A", ("model",), release="R")],
            [EventRule("startup", (), (), "R")],
        )
    )


def test_all_work_dependencies_and_all_event_guards_are_required():
    workflow = flow(
        [
            WorkNode("entry", ("model",)),
            WorkNode("A", ("memo",), ("entry", "B")),
            WorkNode("B", ("note",), release="R"),
        ],
        [EventRule("publish-R", ("entry", "A"), (), "R")],
    )
    with pytest.raises(ValueError, match=r"work A: waiting for accepted dependencies \['B'\]"):
        validate_workflow(workflow)


@pytest.mark.parametrize(
    "workflow,match",
    [
        (flow([WorkNode("A", ("model",), ("missing",))]), "unknown dependencies.*missing"),
        (flow([WorkNode("A", ("model",), release="missing")]), "release 'missing'.*no producer"),
        (
            flow([WorkNode("A", ("model",))], [EventRule("R", ("missing",), (), "next")]),
            "unknown accepted-work guards.*missing",
        ),
    ],
)
def test_unknown_references_are_rejected_before_reachability(workflow, match):
    with pytest.raises(ValueError, match=match):
        validate_workflow(workflow)


def test_ordinary_dependency_cycle_reports_unreachable_work():
    workflow = flow([WorkNode("A", ("model",), ("B",)), WorkNode("B", ("memo",), ("A",))])
    with pytest.raises(ValueError, match="Cyclic.*work A.*work B"):
        validate_workflow(workflow)


@pytest.mark.parametrize("delivery", ["short", "project", "continuous"])
def test_existing_chain_specs_remain_reachable(delivery):
    validate_workflow(make_workflow(delivery).public_spec())


@pytest.mark.parametrize("topology", ["fork", "selective", "coordination"])
def test_existing_multi_release_specs_remain_reachable(topology):
    validate_workflow(make_workflow("continuous", topology).public_spec())


def test_multiple_producers_do_not_allow_duplicate_event_ids():
    rule = EventRule("producer", ("A",), (), "next")
    workflow = flow([WorkNode("A", ("model",))], [rule, replace(rule, release="another")])
    with pytest.raises(ValueError, match="Event rules must have unique IDs"):
        validate_workflow(workflow)
