"""Policy choice and immutable per-work adoption context."""

import copy

import pytest

from proworksim.core.adoption import (
    ADOPTION_POLICIES,
    allowed_policies,
    binding_for,
    binding_key,
    make_binding,
    require_policy,
    require_version,
    snapshot_bindings,
    validate_policy_contract,
)


def fixture():
    work = {
        "work_item_id": "B::analysis",
        "project_id": "B",
        "requirement_version": 1,
        "requirements": {"input_policy": "current_published"},
    }
    return {
        "clock": 2,
        "work_items": {work["work_item_id"]: work},
        "adoptions": {},
        "adoption_view": {},
        "work_replacements": {},
    }, work


def register(state, work, version="v1", policy="current_published"):
    record = make_binding(state, work, "input", "source", version, policy, "bob")
    state["adoptions"][record["adoption_id"]] = record
    state["adoption_view"][record["adoption_id"]] = {"target_version": version}
    return record


def test_alias_binding_keeps_each_work_edition_and_snapshot_independent():
    state, old = fixture()
    first = register(state, old)
    snapshot = snapshot_bindings(state, old)
    new = {**copy.deepcopy(old), "work_item_id": "B::analysis@r2", "requirement_version": 2}
    state["work_items"][new["work_item_id"]] = new
    state["work_replacements"][old["work_item_id"]] = new["work_item_id"]
    assert binding_for(state, new["work_item_id"], "input") is None
    second = register(state, new, "v2")
    assert first["version_id"] == "v1"
    assert second["version_id"] == "v2"
    assert set(snapshot_bindings(state, old)) == {binding_key(old["work_item_id"], "input")}
    assert set(snapshot_bindings(state, new)) == {binding_key(new["work_item_id"], "input")}
    state["adoption_view"][first["adoption_id"]]["target_version"] = "v3"
    second["history"].append({"version_id": "v3"})
    assert snapshot[first["adoption_id"]]["target_version"] == "v1"
    assert snapshot[first["adoption_id"]]["history"] == []


def test_contract_blocks_policy_evasion_but_honors_declared_choice():
    _, work = fixture()
    with pytest.raises(ValueError, match="input contract"):
        require_policy(work, "input", "fixed")
    work["requirements"]["input_policies"] = {"input": ["fixed", "current_published"]}
    require_policy(work, "input", "fixed")
    assert allowed_policies(work, "other") == {"current_published"}
    assert allowed_policies({"requirements": {}}, "input") == ADOPTION_POLICIES
    validate_policy_contract(work)


@pytest.mark.parametrize("value", [[], ["fixed", "fixed"], ["fixed", 1], "latest", {}, False, None])
def test_invalid_policy_declarations_are_rejected(value):
    with pytest.raises(ValueError, match="Declared input policy"):
        validate_policy_contract({"requirements": {"input_policies": {"input": value}}})


@pytest.mark.parametrize(
    "field,value", [("project_id", "A"), ("requirement_version", 2), ("work_ids", ["B::other"])]
)
def test_wrong_context_cannot_be_snapshotted(field, value):
    state, work = fixture()
    record = register(state, work)
    record[field] = value
    with pytest.raises(ValueError, match="exact work edition"):
        snapshot_bindings(state, work)


def test_unknown_target_is_not_falsely_substituted_with_current_adoption():
    state, work = fixture()
    record = register(state, work)
    state["adoption_view"][record["adoption_id"]]["target_version"] = None
    assert snapshot_bindings(state, work)[record["adoption_id"]]["target_version"] is None
    state["adoption_view"] = {}
    with pytest.raises(ValueError, match="projection is missing"):
        snapshot_bindings(state, work)


def test_fixed_declared_version_is_a_requirement_not_a_worker_choice():
    work = {
        "requirements": {
            "input_policy": ["fixed", "current_published"],
            "input_versions": {"input": "v2"},
        }
    }
    require_version(work, "input", "v2", "fixed")
    with pytest.raises(ValueError, match="declared input version"):
        require_version(work, "input", "v1", "fixed")
    # Current policy can record a stale adopted version for a negative content
    # experiment; its submission target still demands the published version.
    require_version(work, "input", "v1", "current_published")
    for declaration in (None, [], 2, ""):
        work["requirements"]["input_versions"]["input"] = declaration
        with pytest.raises(ValueError, match="exact nonempty"):
            validate_policy_contract(work)


@pytest.mark.parametrize(
    "group",
    [
        "publication_only",
        "replacement_fixed",
        "replacement_current",
        "late_information",
        "scope_controls",
    ],
)
def test_public_session_work_context_and_information_recovery(tmp_path, group):
    from scripts.work_binding_experiment import run_group

    result = run_group(group, tmp_path)
    assert result["construction_error"] is None, result["construction_error"]
    assert result["passed"], [check for check in result["checks"] if not check["passed"]]
