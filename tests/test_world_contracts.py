"""World identity, package atomicity and new project-scope boundaries."""

import copy

import pytest

from proworksim.core.projections import derive_current_work_view
from proworksim.core.rules import confirm_credential, registered_applicability
from proworksim.core.types import Credential
from proworksim.core.work import approve_submission, submit_work
from proworksim.core.adoption import binding_key
from proworksim.core.world import (
    WorldSpec,
    install_package,
    new_world_state,
    object_identity,
    validate_package,
)
from proworksim.policies.organization import authority


def state_fixture():
    return new_world_state(
        WorldSpec(
            "world-1",
            [{"actor_id": actor} for actor in ("admin", "sam", "editor")],
            bootstrap_grants=[{"actor_id": "admin", "power": "install_project", "scope": "world"}],
        )
    )


def package_fixture(project_id="A", policy="review"):
    return {
        "project_id": project_id,
        "goal": "Prepare a result",
        "participants": ["sam", "editor"],
        "objects": [
            {
                "alias": "report",
                "filename": "report.json",
                "owner": "sam",
                "data": {"answer": "intentionally wrong"},
                "deliverable_role": "analysis",
            }
        ],
        "works": [
            {
                "work_id": "work-1",
                "owner": "sam",
                "approval_policy": policy,
                "deliverable_contract": {
                    "min_files": 1,
                    "max_files": 2,
                    "allowed_roles": ["analysis"],
                    "required_fields": ["answer"],
                },
            }
        ],
        "grants": [
            {
                "actor_id": "editor",
                "power": "approve",
                "subject": "deliverable",
                "work_nodes": ["work-1"],
            }
        ],
        "provenance": {"kind": "synthetic", "source_evidence_refs": []},
    }


def install(state, package):
    payloads = install_package(state, package, "admin")
    # These tests exercise state-only contracts; the runtime owns actual files.
    for payload in payloads:
        obj = state["artifacts"][payload["object_id"]]
        obj.update(current_version="v1", versions={"v1": {"logical_time": 0}})
    return payloads


def test_empty_world_has_no_project_or_finance_and_install_is_pure_until_commit():
    state = state_fixture()
    assert state["projects"] == state["work_items"] == {}
    assert not {"project", "facts", "assumptions"} & set(state)
    before = copy.deepcopy(state)
    plan = validate_package(state, package_fixture())
    assert plan["works"][0]["work_item_id"] == "A::work-1"
    assert state == before
    payloads = install(state, package_fixture())
    assert payloads[0]["data"] == {"answer": "intentionally wrong"}
    assert state["world_id"] == before["world_id"]
    assert state["actors"] == before["actors"]
    assert state["clock"] == before["clock"]
    assert state["attestations"] == {} and state["messages"] == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(history=[{"event": "approved"}]),
        lambda p: p["objects"][0].update(filename="../report.json"),
        lambda p: p["objects"][0].update(data={"bad": float("nan")}),
        lambda p: p["grants"][0].update(project_id="B"),
        lambda p: p["grants"][0].update(scope="world"),
        lambda p: p["grants"][0].update(power="install_project"),
        lambda p: p["grants"][0].update(actor_id="stranger"),
        lambda p: p["works"][0].update(submissions=[{"review": {"decision": "accepted"}}]),
        lambda p: p.update(provenance={"kind": "observed", "source_evidence_refs": []}),
    ],
)
def test_invalid_package_never_leaves_partial_objects_or_powers(mutation):
    state = state_fixture()
    before = copy.deepcopy(state)
    package = package_fixture()
    mutation(package)
    with pytest.raises(ValueError):
        install_package(state, package, "admin")
    assert state == before


def test_untrusted_installer_cannot_delegate_even_narrow_project_powers():
    state = state_fixture()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="institutional power"):
        install_package(state, package_fixture(), "sam")
    assert state == before


def test_local_names_do_not_alias_objects_or_grants_and_explicit_scope_must_match():
    state = state_fixture()
    install(state, package_fixture("A"))
    second = package_fixture("B")
    second["grants"][0]["actor_id"] = "sam"
    install(state, second)
    assert state["workspaces"]["A"]["report"] != state["workspaces"]["B"]["report"]
    assert (
        state["artifacts"][object_identity("A", "report")]["filename"]
        == state["artifacts"][object_identity("B", "report")]["filename"]
    )
    assert (
        state["artifacts"][object_identity("A", "report")]["storage_path"]
        != state["artifacts"][object_identity("B", "report")]["storage_path"]
    )
    assert authority(state, "sam", "approve", "deliverable", "B::work-1")
    assert not authority(state, "sam", "approve", "deliverable", "A::work-1")
    assert not authority(state, "sam", "approve", "deliverable", "work-1")
    assert not authority(state, "sam", "approve", "deliverable", "B::work-1", project_id="A")
    assert not authority(state, "sam", "approve", "deliverable")
    assert not authority(
        state,
        "sam",
        "approve",
        "deliverable",
        "B::work-1",
        object_id=object_identity("A", "report"),
    )
    assert not authority(state, "admin", "install_project", "project", project_id="A")


def test_dynamic_contract_allows_one_or_two_files_and_preserves_content_errors():
    for split in (False, True):
        state = state_fixture()
        install(state, package_fixture(policy="delivery_only"))
        pinned = {object_identity("A", "report"): "v1"}
        if split:
            state["artifacts"]["dynamic-part"] = {
                "deliverable_role": "analysis",
                "current_version": "v1",
                "versions": {"v1": {}},
            }
            pinned["dynamic-part"] = "v1"
        sub = submit_work(state, "sam", "A::work-1", pinned)
        assert sub["artifact_versions"] == pinned
        assert sub["review"]["decision"] == "accepted"
        assert sub["review"]["decision_basis"] == "delivery_only"
        assert derive_current_work_view(state)["A::work-1"]["status"] == "accepted"
        assert sub["requirement_snapshot"]["deliverable_contract"]["required_fields"] == ["answer"]


def test_review_policy_requires_actual_scoped_approval():
    state = state_fixture()
    install(state, package_fixture())
    sub = submit_work(state, "sam", "A::work-1", {object_identity("A", "report"): "v1"})
    assert sub["review"] is None
    with pytest.raises(ValueError, match="institutional power"):
        approve_submission(state, "sam", "A::work-1", sub["submission_id"])
    approve_submission(state, "editor", "A::work-1", sub["submission_id"])
    assert derive_current_work_view(state)["A::work-1"]["status"] == "accepted"


def test_adoption_requires_exact_shared_version_without_importing_upstream_files():
    state = state_fixture()
    install(state, package_fixture("A"))
    target = package_fixture("B")
    target["adoptions"] = [
        {
            "alias": "input",
            "object_id": object_identity("A", "report"),
            "version_id": "v1",
            "policy": "fixed",
        }
    ]
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="prior explicit"):
        install_package(state, target, "admin")
    assert state == before
    state["shares"].append(
        {
            "project_id": "B",
            "object_id": object_identity("A", "report"),
            "version_id": "v1",
            "actor_ids": ["sam", "editor"],
        }
    )
    install(state, target)
    assert state["workspaces"]["B"]["input"] == object_identity("A", "report")
    assert state["adoptions"][binding_key("B::work-1", "input")]["version_id"] == "v1"
    assert state["adoptions"][binding_key("B::work-1", "input")]["work_ids"] == ["B::work-1"]


def test_confirmation_is_both_project_and_object_scoped():
    state = state_fixture()
    package = package_fixture()
    package["grants"].append(
        {
            "actor_id": "editor",
            "power": "confirm",
            "subject": "requirements",
            "work_nodes": ["work-1"],
            "object_ids": ["report"],
        }
    )
    install(state, package)
    install(state, package_fixture("B"))
    credential = Credential(
        reference={"object_id": object_identity("A", "report"), "version_id": "v1"},
        project_id="A",
        requirement_dimension="requirements",
        requirement_version=1,
        work_nodes=("A::work-1",),
        purpose="delivery",
        period=None,
        effective_at=0,
        confirmed_by="editor",
        attestation_ref="signed-A",
    )
    confirm_credential(state, "editor", credential.reference, credential)
    context = {
        "project_id": "A",
        "work_id": "A::work-1",
        "work_node": "A::work-1",
        "requirement_dimension": "requirements",
        "requirement_version": 1,
        "purpose": "delivery",
        "period": None,
        "at": 0,
    }
    assert registered_applicability(state, credential.reference, context).status.value == "PASS"
    assert (
        registered_applicability(
            state,
            credential.reference,
            {**context, "project_id": "B", "work_id": "B::work-1", "work_node": "B::work-1"},
        ).status.value
        != "PASS"
    )
    with pytest.raises(ValueError, match="institutional power"):
        confirm_credential(
            state,
            "editor",
            {"object_id": object_identity("B", "report"), "version_id": "v1"},
            {
                **credential.to_dict(),
                "reference": {"object_id": object_identity("B", "report"), "version_id": "v1"},
                "project_id": "B",
                "work_nodes": ["B::work-1"],
                "attestation_ref": "fake-B",
            },
        )


def test_world_object_names_and_project_aliases_have_distinct_identities():
    assert object_identity(None, "report") != object_identity("world", "report")
    assert object_identity("A--B", "report") != object_identity("A", "B--report")
    assert object_identity("A", "report") == object_identity("A", "report")


@pytest.mark.parametrize("change", ["unimplemented_content_rule", "non_object_data"])
def test_package_rejects_contracts_and_payload_shapes_the_runtime_does_not_execute(change):
    state = state_fixture()
    package = package_fixture()
    if change == "unimplemented_content_rule":
        package["works"][0]["deliverable_contract"]["content_rules"] = {"answer": {"minimum": 0}}
    else:
        package["objects"][0]["data"] = [{"answer": 1}]
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        install_package(state, package, "admin")
    assert state == before
