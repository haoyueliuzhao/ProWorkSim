"""Current work confirmation is distinct from being the latest basis file."""

import copy
import json

import pytest

from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.freshness import refresh_freshness
from proworksim.kernel import World


def call(world, action, **arguments):
    response = world.session().call(action, **arguments)
    assert response["ok"], response
    return response["result"]


def world_at(tmp_path, **options):
    return World(compile_world(design(701, **options), tmp_path / "world"))


def test_initial_unavailable_world_does_not_present_historical_basis_as_current(tmp_path):
    world = world_at(tmp_path, scenario="unavailable")
    state = world.store.load()
    assert state["work_items"]["work-1"]["required_basis"] is None
    assert state["artifacts"]["basis"]["current_version"] == "v1"
    for aid in ("model", "memo"):
        assert state["artifacts"][aid]["basis_applicability"] == "unknown"
        assert state["artifacts"][aid]["data_freshness"] == "stale"


def test_matching_current_data_and_historical_basis_stays_unknown_without_approval(tmp_path):
    world = world_at(tmp_path, scenario="unavailable")
    financials = call(world, "read_file", artifact_id="financials")
    model = call(
        world,
        "sheet_update",
        cells={"Inputs!B2": 1000},
        dependencies=[
            {"artifact_id": "financials", "version_id": financials["version_id"]},
            {"artifact_id": "basis", "version_id": "v1"},
        ],
    )
    memo = call(world, "read_file", artifact_id="memo")
    call(
        world,
        "write_file",
        artifact_id="memo",
        content=memo["content"],
        dependencies=[
            {"artifact_id": "financials", "version_id": financials["version_id"]},
            {"artifact_id": "model", "version_id": model["version_id"]},
        ],
    )
    for aid in ("model", "memo"):
        artifact = world.store.load()["artifacts"][aid]
        assert artifact["data_freshness"] == "current"
        assert artifact["basis_applicability"] == "unknown"
        assert artifact["freshness"] == "unknown"
        assert artifact["possibly_stale"]


@pytest.mark.parametrize("invalid_field", ["role", "version", "node", "time", "permission"])
def test_work_confirmation_requires_authorized_matching_approval_metadata(tmp_path, invalid_field):
    world = world_at(tmp_path, delivery="file")
    assert run_baseline(world.session())["complete"]
    state = world.store.load()
    before_data = state["artifacts"]["model"]["data_freshness"]
    ref = state["work_items"]["work-1"]["required_basis"]
    approval = next(a for a in state["basis_approvals"] if a["basis_version"] == ref["version_id"])
    if invalid_field == "role":
        approval["actor_id"] = "reviewer"
    elif invalid_field == "version":
        approval["requirement_version"] += 1
    elif invalid_field == "node":
        approval["work_nodes"] = ["historical"]
    elif invalid_field == "time":
        approval["at"] = state["clock"] + 1
    else:
        next(role for role in state["roles"] if role["role_id"] == "manager")[
            "can_confirm_basis"
        ] = False
    refresh_freshness(state)
    assert state["artifacts"]["model"]["basis_applicability"] == "unknown"
    assert state["artifacts"]["model"]["freshness"] == "unknown"
    assert state["artifacts"]["model"]["data_freshness"] == before_data == "current"


def test_file_delivery_does_not_invent_a_separate_memo_confirmation_requirement(tmp_path):
    world = world_at(tmp_path, delivery="file")
    assert run_baseline(world.session())["complete"]
    state = world.store.load()
    assert state["work_items"]["work-1"]["deliverables"] == ["model"]
    assert state["artifacts"]["model"]["basis_applicability"] == "current"
    assert state["artifacts"]["memo"]["basis_applicability"] == "stale"
    assert state["artifacts"]["memo"]["data_freshness"] == "stale"


def test_later_stage_approval_does_not_make_final_artifacts_match_old_work_requirements(tmp_path):
    world = world_at(tmp_path, scenario="basis_only")
    assert run_baseline(world.session())["complete"]
    state = world.store.load()
    first = state["work_items"]["work-1"]
    second = state["work_items"]["work-2"]
    assert first["required_basis"] != second["required_basis"]
    historical = copy.deepcopy(first["submissions"])
    refresh_freshness(state)
    assert all(
        state["artifacts"][aid]["basis_applicability"] == "current" for aid in ("model", "memo")
    )
    assert first["submissions"] == historical
    assert all(submission["review"]["decision"] == "accepted" for submission in historical)


def test_new_global_basis_does_not_revoke_an_existing_work_scoped_confirmation(tmp_path):
    world = world_at(tmp_path, delivery="file")
    assert run_baseline(world.session())["complete"]
    state = world.store.load()
    basis = state["artifacts"]["basis"]
    basis["versions"]["unrelated"] = copy.deepcopy(basis["versions"][basis["current_version"]])
    basis["current_version"] = "unrelated"
    refresh_freshness(state)
    assert state["artifacts"]["model"]["basis_applicability"] == "current"
    assert state["artifacts"]["model"]["freshness"] == "current"


def test_basis_propagation_follows_the_adopted_parent_version(tmp_path):
    world = world_at(tmp_path)
    assert run_baseline(world.session())["complete"]
    state = world.store.load()
    current_financials = state["artifacts"]["financials"]["current_version"]
    memo = json.loads(call(world, "read_file", artifact_id="memo")["content"])
    call(
        world,
        "write_file",
        artifact_id="memo",
        content=json.dumps(memo),
        dependencies=[
            {"artifact_id": "financials", "version_id": current_financials},
            {"artifact_id": "model", "version_id": "v2"},
        ],
    )
    state = world.store.load()
    assert state["artifacts"]["model"]["basis_applicability"] == "current"
    assert state["artifacts"]["memo"]["basis_applicability"] == "stale"


def test_replacement_marks_new_work_basis_stale_without_rewriting_approved_history(tmp_path):
    world = world_at(tmp_path, delivery="file")
    assert run_baseline(world.session())["complete"]
    before = world.store.load()
    approved = copy.deepcopy(before["work_items"]["work-1"]["submissions"])
    response = world.session("manager").call(
        "revise_requirements",
        work_item_ids=["work-1"],
        growth_delta=0.02,
        reason="适用性测试：已有批准保留，仅当前需求修订",
    )
    assert response["ok"], response
    after = world.store.load()
    assert after["artifacts"]["model"]["basis_applicability"] == "stale"
    assert after["artifacts"]["model"]["data_freshness"] == "current"
    assert (
        after["artifacts"]["model"]["current_version"]
        == before["artifacts"]["model"]["current_version"]
    )
    historical = after["work_items"]["work-1"]["submissions"]
    assert historical[0]["review"] == approved[0]["review"]
    assert historical[0]["artifact_versions"] == approved[0]["artifact_versions"]
