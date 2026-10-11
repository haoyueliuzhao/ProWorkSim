"""Finite CPU controls for v047 membership, branch isolation and native delivery."""

import copy

import pytest

from proworksim.software_organization_v047 import (
    CASE_IDS,
    CONDITIONS,
    MEMBERS,
    PROJECT,
    SoftwareCollaborationPort,
    assess_software_collaboration,
    build_software_collaboration_case,
    case_spec,
    material,
    member_instruction,
    validate_case,
)
from proworksim.stage_budget_v047 import StageTeamBudget
from proworksim.storage import digest, json_bytes


M1, M2, M3, M4 = MEMBERS


def prepare(tmp_path, condition):
    return build_software_collaboration_case(case_spec(condition=condition), tmp_path / condition)


def call(world, member, name, **arguments):
    result = world.session(member, PROJECT).call(name, **arguments)
    assert result["ok"], result
    return result["result"]


def denied(world, member, name, **arguments):
    result = world.session(member, PROJECT).call(name, **arguments)
    assert result["ok"] is False, result
    return result


def patch(world, member, marker):
    files = material(world._software()["case"]["case_id"])["files"]
    path = next(p for p in world._software()["case"]["editable_paths"] if p != "test_member.py")
    call(world, member, "write_file", path=path, text=files[path] + "\n# " + marker + "\n")
    return call(world, member, "fix_patch", task_ids=[], message=marker), path


@pytest.mark.parametrize(
    "condition,count,cap",
    [
        ("S1", 1, 1),
        ("D2", 1, 2),
        ("D4", 1, 4),
        ("I2", 2, 2),
        ("I4", 4, 4),
        ("P2", 2, 2),
        ("P4", 4, 4),
    ],
)
def test_exact_real_initial_members_slots_and_public_budget(tmp_path, condition, count, cap):
    prepared = prepare(tmp_path, condition)
    case, world = prepared.case, prepared.world
    state = world.store.load()
    assert len(world._software()["registry"]) == count
    assert len(state["actors"]) == count + 1 and len(state["artifacts"]) == count + 1
    assert case["member_limits"]["max_cumulative_births"] == cap
    assert case["team_limits"] == {
        "max_total_tokens": 250000,
        "max_decisions": 128,
        "max_attempts": 128,
        "max_test_runs": 32,
    }
    assert world._software()["tasks"] == {} and state["software_events"] == []
    assert world.test_budget.snapshot()["used"] == 0
    observation = SoftwareCollaborationPort(world.session(M1, PROJECT), M1).observe()
    assert observation["interface_revision"] == "architecture-efficiency-staged-organization-v0.47"
    assert observation["shared_resource_limits"] == case["team_limits"]
    assert "250000" in member_instruction(case)
    assert world.runnable_members() == (
        list(MEMBERS[:count]) if condition.startswith("I") else [M1]
    )
    assert validate_case(case) == case


def test_all_roots_budgets_validate_and_only_new_case_is_accepted():
    for case_id in CASE_IDS:
        for condition in CONDITIONS:
            for total in (250000, 500000):
                case = case_spec(case_id, condition=condition, team_token_budget=total)
                assert validate_case(case) == case
                assert case["initial_binding"] == case_spec(case_id)["initial_binding"]
    changed = copy.deepcopy(case)
    changed["stage_plan"][0]["limits"]["max_total_tokens"] += 1
    with pytest.raises(ValueError):
        validate_case(changed)
    with pytest.raises(ValueError):
        case_spec(condition="F2")
    with pytest.raises(ValueError):
        case_spec(condition="P4", first_member=M4)


@pytest.mark.parametrize("condition,cap", [("D2", 2), ("D4", 4)])
def test_dynamic_starts_one_uses_real_native_births_and_never_reuses_retired_ids(
    tmp_path, condition, cap
):
    world = prepare(tmp_path, condition).world
    for member in MEMBERS[1:cap]:
        assert (
            call(world, M1, "spawn_member", briefing="Member-created current work")["member_id"]
            == member
        )
    assert len(world.live_members()) == cap
    fixed, path = patch(world, M2, "RETIRED_FIXED_TREE")
    call(world, M2, "retire_member", reason="Stop permanently")
    denied(world, M1, "spawn_member", briefing="No cumulative replacement", replaces=M2)
    call(world, M1, "adopt_candidate", patch_id=fixed["patch_id"])
    assert (
        "RETIRED_FIXED_TREE"
        in call(world, M1, "read_file", path=path, start_line=1, max_lines=120)["text"]
    )
    assert len(world._software()["registry"]) == cap


def test_independent_generation_isolates_code_metadata_messages_and_reports(tmp_path):
    world = prepare(tmp_path, "I2").world
    first, path = patch(world, M1, "SECRET_FIXED_CANDIDATE_ONE")
    second, _ = patch(world, M2, "SECRET_FIXED_CANDIDATE_TWO")
    report = call(world, M2, "run_tests")
    view = SoftwareCollaborationPort(world.session(M1, PROJECT), M1).observe()
    assert "SECRET_FIXED_CANDIDATE_TWO" not in str(view)
    assert [p["patch_id"] for p in view["patches"]] == [first["patch_id"]]
    denied(
        world, M1, "read_file", path=path, start_line=1, max_lines=30, patch_id=second["patch_id"]
    )
    denied(world, M1, "integrate_patch", patch_id=second["patch_id"])
    denied(
        world,
        M1,
        "send_message",
        recipient=M2,
        task_id="root_goal",
        body="Forbidden generation communication",
    )
    denied(
        world,
        M1,
        "read_test_result",
        report_id=report["report_id"],
        cursor=report["page"]["cursor"],
    )
    denied(world, M1, "submit_integration")
    call(world, M1, "finish_stage", reason="Candidate fixed; preserve selector session")
    assert M1 in world.live_members() and M1 not in world.runnable_members()
    assert world.advance_stage() is False
    call(world, M2, "retire_member", reason="Published candidate remains")
    assert world.advance_stage() is True
    assert world.runnable_members() == [M1]
    assert set(world.stage_state()["candidate_patch_ids"]) == {
        first["patch_id"],
        second["patch_id"],
    }
    denied(
        world,
        M1,
        "read_test_result",
        report_id=report["report_id"],
        cursor=report["page"]["cursor"],
    )


def test_selector_uses_exact_adoption_and_own_current_test_fix_submit_only(tmp_path):
    prepared = prepare(tmp_path, "I2")
    world = prepared.world
    first, path = patch(world, M1, "FIRST_FIXED")
    second, _ = patch(world, M2, "SECOND_FIXED")
    # A later private edit cannot alter the fixed candidate or become selectable.
    original = material(prepared.case["case_id"])["files"][path]
    call(world, M2, "write_file", path=path, text=original + "\n# UNPUBLISHED_PRIVATE\n")
    for member in (M1, M2):
        call(world, member, "finish_stage", reason="Candidate ready")
    world.advance_stage()
    adopted = call(world, M1, "adopt_candidate", patch_id=second["patch_id"])
    assert adopted["files_sha256"] == second["files_sha256"]
    _, _, bundle = world._bundle(M1)
    assert digest(json_bytes(bundle["files"])) == second["files_sha256"]
    assert "UNPUBLISHED_PRIVATE" not in str(bundle)
    denied(world, M1, "write_file", path=path, text=original)
    denied(world, M1, "integrate_patch", patch_id=first["patch_id"])
    denied(world, M1, "submit_integration")
    call(world, M1, "run_tests")
    denied(world, M1, "submit_integration")
    call(
        world,
        M1,
        "fix_patch",
        task_ids=[],
        message="Exact adopted candidate fixed in selector workspace",
    )
    delivery = call(world, M1, "submit_integration")
    assert delivery["candidate_binding"]["patch_id"] == second["patch_id"]
    # Selecting another version invalidates the previous version's submit gate.
    call(world, M1, "adopt_candidate", patch_id=first["patch_id"])
    denied(world, M1, "submit_integration")
    call(world, M1, "run_tests")
    call(world, M1, "fix_patch", task_ids=[], message="Final exact selected tree")
    final = call(world, M1, "submit_integration")
    assert final["files_sha256"] == first["files_sha256"]
    call(world, M1, "finish_stage", reason="Final delivery complete")
    world.advance_stage()
    # One native assessment of the last fixed delivery; no mutable workspace scan.
    result = assess_software_collaboration(prepared, run_root=tmp_path / "one-final-assessment")
    assert result["submitted"] is True and result["files_sha256"] == first["files_sha256"]
    assert result["delivery"]["delivery_id"] == final["delivery_id"]
    assert "independent_acceptance" in result
    assert world.test_budget.snapshot()["used"] == 2


def test_retired_selector_is_not_revived_and_no_hidden_selector_exists(tmp_path):
    world = prepare(tmp_path, "I2").world
    call(world, M1, "retire_member", reason="Permanently leave")
    call(world, M2, "finish_stage", reason="No candidate")
    assert world.advance_stage()
    assert world.stage_state()["stage_id"] == "select" and world.runnable_members() == []
    assert world.advance_stage() and world.stage_state()["closed"]
    assert world._software()["registry"][M1]["status"] == "retired"
    assert set(world._software()["registry"]) == {M1, M2}


def test_p4_stage_permissions_messages_native_testing_and_final_exact_delivery(tmp_path):
    prepared = prepare(tmp_path, "P4")
    world = prepared.world
    first, path = patch(world, M1, "IMPLEMENTATION_FIXED")
    denied(world, M2, "read_file", path=path, start_line=1, max_lines=10)
    denied(world, M1, "submit_integration")
    call(
        world,
        M1,
        "send_message",
        recipient=M2,
        task_id="root_goal",
        body="Review the explicit fixed version",
    )
    call(world, M1, "finish_stage", reason="Implementation fixed")
    world.advance_stage()
    assert world.runnable_members() == [M2]
    call(world, M2, "adopt_candidate", patch_id=first["patch_id"])
    denied(world, M2, "write_file", path=path, text="forbidden")
    call(world, M2, "run_tests")
    call(
        world,
        M2,
        "send_message",
        recipient=M3,
        task_id="root_goal",
        body="Public review findings on fixed version",
    )
    call(world, M2, "finish_stage", reason="Review forwarded")
    world.advance_stage()
    call(world, M3, "adopt_candidate", patch_id=first["patch_id"])
    _, _, bundle = world._bundle(M3)
    call(world, M3, "write_file", path=path, text=bundle["files"][path] + "\n# REVISION_FIXED\n")
    revised = call(world, M3, "fix_patch", task_ids=[], message="Revision completed")
    call(world, M3, "finish_stage", reason="Fixed revised version")
    world.advance_stage()
    assert world.runnable_members() == [M4]
    call(world, M4, "adopt_candidate", patch_id=revised["patch_id"])
    denied(world, M4, "replace_file", path=path, old="REVISION_FIXED", new="forbidden")
    denied(world, M4, "submit_integration")
    call(world, M4, "run_tests")
    call(world, M4, "fix_patch", task_ids=[], message="Final native-tested current version")
    delivered = call(world, M4, "submit_integration")
    assert delivered["files_sha256"] == revised["files_sha256"]
    assert delivered["actor_id"] == M4 and world.test_budget.snapshot()["used"] == 2
    assert [row["stage_id"] for row in world.test_budget.records] == ["review", "validate_submit"]


def test_host_stage_advance_cannot_release_pending_reservation_or_fake_work(tmp_path):
    prepared = prepare(tmp_path, "P2")
    world = prepared.world
    budget = StageTeamBudget(
        stage_provider=world.stage_state,
        stage_plan=prepared.case["stage_plan"],
        members=[M1, M2],
        team_id="stage-cpu",
        max_total_tokens=250000,
        require_exact_resident=False,
    )
    world.bind_stage_budget(budget)
    budget.consume_decision(M1, "waiting")
    budget.reserve(M1, "waiting", {"token_reservation": 1000})
    world.finish_member_stage(M1, "stage boundary", unavailable=False)
    with pytest.raises(ValueError):
        world.advance_stage()
    assert world.stage_state()["stage_id"] == "implement"
    budget.cleanup(M1, "waiting")
    assert world.advance_stage()
    assert world.store.load()["software_events"] == []
    assert all(row.get("model_generated") is False for row in world.stage_state()["history"])
    assert world.runnable_members() == [M2]


def test_fixed_report_remains_private_and_latest_candidate_release_has_no_free_copy(tmp_path):
    world = prepare(tmp_path, "I2").world
    early, path = patch(world, M2, "EARLY_FIXED")
    late, _ = patch(world, M2, "LAST_FIXED")
    _, before, bundle_before = world._bundle(M1)
    for member in (M1, M2):
        call(world, member, "finish_stage", reason="Generation done")
    world.advance_stage()
    assert world.stage_state()["candidate_patch_ids"] == [late["patch_id"]]
    _, after, bundle_after = world._bundle(M1)
    assert before == after and bundle_before == bundle_after
    denied(world, M1, "adopt_candidate", patch_id=early["patch_id"])
    call(world, M1, "adopt_candidate", patch_id=late["patch_id"])
    assert (
        "LAST_FIXED" in call(world, M1, "read_file", path=path, start_line=1, max_lines=120)["text"]
    )


def test_invalid_native_stage_arguments_use_original_schema_rejection(tmp_path):
    world = prepare(tmp_path, "I2").world
    result = denied(world, M1, "finish_stage", reason="x" * 2001)
    assert result["error"]["rejection"]["code"] == "public_argument_schema"
    assert world.stage_state()["finished_members"] == []
    result = denied(world, M1, "adopt_candidate", patch_id="patch-1", extra="not public")
    assert result["error"]["rejection"]["code"] == "public_argument_schema"


def test_independent_registry_retirement_prose_cannot_leak_private_branch_content(tmp_path):
    world = prepare(tmp_path, "I2").world
    call(world, M2, "retire_member", reason="PRIVATE_BRANCH_REASON_WITH_REPAIR_DETAILS")
    observation = SoftwareCollaborationPort(world.session(M1, PROJECT), M1).observe()
    assert "PRIVATE_BRANCH_REASON_WITH_REPAIR_DETAILS" not in str(observation)
    assert observation["member_registry"][M2]["status"] == "retired"
    assert world.reachable_events(M1) == []


@pytest.mark.parametrize("condition", ["I2", "I4", "P2", "P4"])
def test_model_catalog_reference_is_lossless_and_keeps_fixed_permissions(tmp_path, condition):
    prepared = prepare(tmp_path, condition)
    world = prepared.world
    first, path = patch(world, M1, "LEGAL_FIXED_ONE")
    second = None
    if condition.startswith("I"):
        second, _ = patch(world, M2, "INDEPENDENT_FIXED_TWO")

    def check_projection(member):
        expected = world.architecture_snapshot(member)
        before = world.store.load()
        observation = SoftwareCollaborationPort(world.session(member, PROJECT), member).observe()
        projected = copy.deepcopy(observation["architecture"])
        assert "candidates" not in projected
        assert projected.pop("fixed_patch_catalog_field") == "patches"
        projected["candidates"] = copy.deepcopy(observation["patches"])
        assert projected == expected
        assert world.architecture_snapshot(member) == expected
        assert world.store.load() == before
        assert observation["patches"] == world.visible_patches(member)
        return observation

    initial = check_projection(M1)
    assert initial["architecture"]["candidate_patch_ids"] == []
    if condition.startswith("I"):
        assert [row["patch_id"] for row in initial["patches"]] == [first["patch_id"]]
        assert "INDEPENDENT_FIXED_TWO" not in str(initial)
        denied(
            world,
            M1,
            "read_file",
            path=path,
            start_line=1,
            max_lines=10,
            patch_id=second["patch_id"],
        )
        for member in prepared.case["active_roles"]:
            call(world, member, "finish_stage", reason="Finish this finite CPU generation fixture")
        world.advance_stage()
        selected = check_projection(M1)
        assert selected["architecture"]["candidate_patch_ids"] == [
            first["patch_id"],
            second["patch_id"],
        ]
        assert [row["patch_id"] for row in selected["patches"]] == [
            first["patch_id"],
            second["patch_id"],
        ]
        assert (
            call(world, M1, "adopt_candidate", patch_id=second["patch_id"])["files_sha256"]
            == second["files_sha256"]
        )
    else:
        call(world, M1, "finish_stage", reason="Hand off the finite CPU fixed fixture")
        world.advance_stage()
        next_stage = check_projection(M2)
        assert next_stage["patches"] == [first]
        assert (
            call(world, M2, "adopt_candidate", patch_id=first["patch_id"])["files_sha256"]
            == first["files_sha256"]
        )
        if condition == "P4":
            denied(world, M2, "write_file", path=path, text="Still forbidden in review")
