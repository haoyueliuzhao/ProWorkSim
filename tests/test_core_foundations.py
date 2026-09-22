"""Cross-domain rule witnesses: no role or latest-version special cases."""

import copy

import pytest

from proworksim.core.references import ApplicabilityContext, VersionRef
from proworksim.core.rules import confirm_credential, registered_applicability
from proworksim.core.types import Assumption, CheckResult, CheckStatus, Claim, Credential, Fact
from proworksim.core.visibility import grant_version, visible_version
from proworksim.policies.organization import authority


def fixture():
    state = {
        "clock": 5,
        "roles": [{"role_id": actor} for actor in ("editor-7", "author-9", "reader-2")],
        "organization": {
            "positions": {"coordinator": "editor-7", "worker": "author-9"},
            "grants": [
                {
                    "actor_id": "editor-7",
                    "power": "confirm",
                    "subject": "publication_terms",
                    "work_nodes": ["draft-a", "draft-b"],
                }
            ],
        },
        "artifacts": {
            "publication-terms": {
                "current_version": "r2",
                "readers": ["reader-2"],
                "version_readers": {},
                "versions": {
                    v: {"logical_time": i, "derived_from": []} for i, v in enumerate(("r1", "r2"))
                },
            }
        },
        "knowledge": {"author-9": {"read_artifacts": []}},
    }
    credential = Credential(
        reference={"object_id": "publication-terms", "version_id": "r1"},
        project_id="magazine",
        requirement_dimension="publication_terms",
        requirement_version=1,
        work_nodes=("draft-a",),
        period="September",
        purpose="publication",
        effective_at=1,
        confirmed_by="editor-7",
        attestation_ref="permission-1",
    )
    context = ApplicabilityContext(
        project_id="magazine",
        work_id="assignment-a",
        requirement_dimension="publication_terms",
        requirement_version=1,
        work_node="draft-a",
        period="September",
        purpose="publication",
        at=5,
    )
    return state, credential, context


def test_older_credential_remains_applicable_and_another_current_work_can_disagree():
    state, credential, context = fixture()
    confirm_credential(state, "editor-7", credential.reference, credential)
    assert state["artifacts"]["publication-terms"]["current_version"] == "r2"
    assert registered_applicability(state, credential.reference, context).status == CheckStatus.PASS
    other = {**context.to_dict(), "work_id": "assignment-b", "work_node": "draft-b"}
    result = registered_applicability(state, credential.reference, other)
    assert result.status == CheckStatus.FAIL
    assert result.reasons == ("work_scope_mismatch",)
    assert registered_applicability(state, credential.reference, context).status == CheckStatus.PASS


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("purpose", "internal_draft", "purpose_mismatch"),
        ("period", "October", "period_mismatch"),
        ("requirement_dimension", "audience", "requirement_dimension_mismatch"),
        ("requirement_version", 2, "requirement_version_mismatch"),
        ("project_id", "other", "project_id_mismatch"),
    ],
)
def test_applicability_uses_all_query_dimensions(key, value, reason):
    state, credential, context = fixture()
    confirm_credential(state, "editor-7", credential.reference, credential)
    result = registered_applicability(
        state, credential.reference, {**context.to_dict(), key: value}
    )
    assert result.status == CheckStatus.FAIL
    assert reason in result.reasons


def test_confirmation_access_observation_and_adoption_are_distinct():
    state, credential, context = fixture()
    before = copy.deepcopy(state["knowledge"])
    assert authority(state, "editor-7", "confirm", "publication_terms", "draft-a")
    confirm_credential(state, "editor-7", credential.reference, credential)
    artifact = state["artifacts"]["publication-terms"]
    assert visible_version(artifact, "editor-7", 5, "r1") is None
    assert registered_applicability(state, credential.reference, context).status == CheckStatus.PASS
    assert grant_version(state, "publication-terms", "r1", "author-9", "reply-1")
    assert visible_version(artifact, "author-9", 5) == "r1"
    assert visible_version(artifact, "author-9", 5, "r2") is None
    assert state["knowledge"] == before
    assert artifact["versions"]["r1"]["derived_from"] == []
    assert not authority(state, "author-9", "confirm", "publication_terms", "draft-a")
    assert not authority(state, "reader-2", "confirm", "publication_terms", "draft-a")


def test_confirmation_and_grant_replay_are_idempotent():
    state, credential, _ = fixture()
    confirm_credential(state, "editor-7", credential.reference, credential)
    grant_version(state, "publication-terms", "r1", "author-9", "reply-1")
    before = copy.deepcopy(state)
    confirm_credential(state, "editor-7", credential.reference, credential)
    assert not grant_version(state, "publication-terms", "r1", "author-9", "reply-1")
    assert state == before


def test_unprivileged_reader_cannot_create_confirmation():
    state, credential, context = fixture()
    record = {**credential.to_dict(), "confirmed_by": "reader-2"}
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="institutional power"):
        confirm_credential(state, "reader-2", credential.reference, record)
    assert state == before
    assert (
        registered_applicability(state, credential.reference, context).status
        == CheckStatus.UNASSESSED
    )


def test_formal_claim_without_registry_attestation_is_unassessed():
    state, credential, context = fixture()
    state["artifacts"]["publication-terms"]["versions"]["r1"]["credential"] = credential.to_dict()
    assert (
        registered_applicability(state, credential.reference, context).status
        == CheckStatus.UNASSESSED
    )


def test_facts_claims_assumptions_and_credentials_have_distinct_kinds():
    state, credential, _ = fixture()
    records = [
        Fact(17, credential.reference, 0),
        Claim(17, "author-9", 1),
        Assumption(17, "author-9", 1),
        credential,
    ]
    assert len({record.to_dict()["kind"] for record in records}) == 4
    assert CheckResult(CheckStatus.UNASSESSED).to_dict()["status"] == "UNASSESSED"
    with pytest.raises(ValueError, match="Only a credential"):
        confirm_credential(state, "editor-7", credential.reference, records[1])


def test_existing_artifact_reference_round_trips_without_guessing_a_version():
    ref = VersionRef.from_mapping({"artifact_id": "document", "version_id": "edition-3"})
    assert ref.to_dict() == {"object_id": "document", "version_id": "edition-3"}
    with pytest.raises(ValueError):
        VersionRef.from_mapping({"artifact_id": "document"})


def test_registered_confirmation_cannot_be_copied_to_another_version():
    state, credential, context = fixture()
    confirm_credential(state, "editor-7", credential.reference, credential)
    versions = state["artifacts"]["publication-terms"]["versions"]
    versions["r2"]["credential"] = copy.deepcopy(versions["r1"]["credential"])
    result = registered_applicability(
        state, {"object_id": "publication-terms", "version_id": "r2"}, context
    )
    assert result.status == CheckStatus.UNASSESSED
    assert result.reasons == ("credential_reference_or_time_mismatch",)


def test_current_schema_missing_attestation_registry_cannot_fall_back_to_legacy(tmp_path):
    from proworksim.compiler import compile_world
    from proworksim.designer import design
    from proworksim.kernel import World
    from proworksim.basis import requirement_basis
    from proworksim.freshness import refresh_freshness

    world = World(compile_world(design(73, delivery="file"), tmp_path / "world"))
    state = world.store.load()
    assert state["basis_approvals"]
    state.pop("attestations")  # Explicit malformed-snapshot fixture, not a worker action.
    assert requirement_basis(world.store, state, state["work_items"]["work-1"]) is None
    refresh_freshness(state)
    assert state["artifacts"]["model"]["basis_applicability"] == "unknown"


def test_current_schema_missing_organization_does_not_create_legacy_power():
    from proworksim.policies.organization import authority

    state = {"schema_version": "0.4", "roles": [{"role_id": "somebody", "can_confirm_basis": True}]}
    assert not authority(state, "somebody", "confirm", "analytical_assumptions", "work")
