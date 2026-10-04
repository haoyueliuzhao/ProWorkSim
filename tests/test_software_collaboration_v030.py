"""CPU controls for autonomous task formation; these are not model outcomes."""
import copy

import pytest

from proworksim import software_tasks_v030 as source
from proworksim.software_collaboration_v030 import (
    CASE_IDS, MEMBERS, PROJECT, ROOT_GOAL_ID, SoftwareCollaborationPort,
    assess_software_collaboration, build_software_collaboration_case, case_spec,
    software_collaboration_facts, validate_case,
)


def checked(port, action, **arguments):
    response = port.call(action, **arguments)
    assert response["ok"], response
    return response["result"]


def setup(root, task_id=CASE_IDS[-1]):
    prepared = build_software_collaboration_case(case_spec(task_id), root)
    ports = {member: SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member)
             for member in prepared.case["active_roles"]}
    return prepared, ports


def create(port, task_id, description="A task chosen by the CPU control"):
    checked(port, "create_task", task_id=task_id, description=description)
    return checked(port, "claim_task", task_id=task_id)


def write_solution(prepared, port):
    current = source.build_case(prepared.case["case_id"])["files"]
    solution = source.reference_solution(prepared.case["case_id"])
    for path in prepared.case["editable_paths"]:
        if current[path] != solution[path]:
            checked(port, "write_file", path=path, text=solution[path])


def test_o1_empty_board_revision_responsibility_and_root_negotiation(tmp_path):
    prepared, ports = setup(tmp_path / "world")
    a, b = (ports[member] for member in MEMBERS)
    observed = a.observe()
    assert observed["tasks"] == {}
    assert observed["root_goal"]["immutable"]
    assert not observed["task_formation"]["predefined_tasks"]
    checked(a, "send_message", recipient=MEMBERS[1], task_id=ROOT_GOAL_ID,
            body="I propose examining the contract before creating tasks.")
    assert b.observe()["messages"][-1]["task_id"] == ROOT_GOAL_ID
    assert not a.call("claim_task", task_id="library_repair")["ok"]
    assert not a.call("create_task", task_id=ROOT_GOAL_ID, description="Replace root contract")["ok"]
    checked(a, "create_task", task_id="own-plan", description="Study the public behavior")
    assert not b.call("revise_task", task_id="own-plan", description="Overwrite somebody else's plan",
                      expected_revision=1, reason="No authority")["ok"]
    revised = checked(a, "revise_task", task_id="own-plan", description="Study and implement the public behavior",
                      expected_revision=1, reason="Combine work after reading requirements")
    assert revised["revision"] == 2
    checked(b, "claim_task", task_id="own-plan")
    assert not a.call("revise_task", task_id="own-plan", description="Stale creator rewrite",
                      expected_revision=2, reason="Current owner differs")["ok"]
    checked(b, "delegate_task", task_id="own-plan", to_member=MEMBERS[0])
    checked(a, "return_task", task_id="own-plan", reason="Request repartitioning before accepting")
    checked(a, "claim_task", task_id="own-plan")
    assert not a.call("revise_task", task_id="own-plan", description="Wrong revision",
                      expected_revision=1, reason="Must reject stale operation")["ok"]
    facts = software_collaboration_facts(prepared)
    assert [event["kind"] for event in facts["events"]] == [
        "work_message", "task_created", "task_revised", "claim", "delegate", "task_returned", "claim"]
    assert facts["events"][2]["previous_task"]["description"] == "Study the public behavior"
    assert facts["events"][-1]["responsibility_snapshot"] == {"own-plan": MEMBERS[0]}


def test_o1_dependencies_fixed_snapshots_and_explicit_integration(tmp_path):
    prepared, ports = setup(tmp_path / "world")
    a, b = (ports[member] for member in MEMBERS)
    create(a, "basis")
    checked(b, "create_task", task_id="delivery", description="Integrate our selected implementation",
            parent_task_id="basis")
    checked(b, "claim_task", task_id="delivery")
    checked(b, "declare_dependency", task_id="delivery", depends_on="basis")
    assert not a.call("declare_dependency", task_id="basis", depends_on="delivery")["ok"]
    checked(a, "write_file", path="test_member.py", text="assert 1 + 1 == 2\n")
    fixed = checked(a, "fix_patch", task_ids=["basis"], message="CPU witness only")
    checked(a, "revise_task", task_id="basis", description="A later revision after fixed work",
            expected_revision=1, reason="Record additional future scope")
    assert fixed["task_snapshots"]["basis"]["revision"] == 1
    checked(b, "write_file", path="test_member.py", text="assert 3 * 3 == 9\n")
    assert not b.call("fix_patch", task_ids=["delivery"], message="Dependency has not been imported")["ok"]
    merged = checked(b, "integrate_patch", patch_id=fixed["patch_id"])
    assert merged["conflicts"] == ["test_member.py"]
    checked(b, "write_file", path="test_member.py", text="assert 1 + 1 == 2\nassert 3 * 3 == 9\n")
    integrated = checked(b, "fix_patch", task_ids=["delivery"], message="Resolved actual conflict")
    assert integrated["task_snapshots"]["delivery"]["depends_on"] == ["basis"]
    checked(b, "remove_dependency", task_id="delivery", depends_on="basis", reason="Revise subsequent work")
    facts = software_collaboration_facts(prepared)
    assert facts["patches"][integrated["patch_id"]]["task_snapshots"]["delivery"]["depends_on"] == ["basis"]
    assert facts["tasks"]["delivery"]["depends_on"] == []
    assert facts["tasks"]["delivery"]["revision"] == 3
    checked(b, "declare_dependency", task_id="delivery", depends_on="basis")
    assert not b.call("fix_patch", task_ids=["delivery"], message="Old task revision cannot satisfy revised prerequisite")["ok"]
    assert b.observe()["tasks"]["delivery"]["dependency_revisions"] == {"basis": 2}


def test_single_executor_and_frozen_development_partition(tmp_path):
    prepared, ports = setup(tmp_path / "world", CASE_IDS[0])
    a = ports[MEMBERS[0]]
    assert prepared.case["active_roles"] == [MEMBERS[0]]
    assert a.observe()["member_availability"][MEMBERS[1]]["status"] == "inactive"
    create(a, "single-work")
    assert not a.call("delegate_task", task_id="single-work", to_member=MEMBERS[1])["ok"]
    with pytest.raises(ValueError, match="Inactive"):
        SoftwareCollaborationPort(prepared.world.session(MEMBERS[1], PROJECT), MEMBERS[1])
    assert not prepared.world.session(MEMBERS[1], PROJECT).call(
        "create_task", task_id="inactive-work", description="Must reject inactive participant")["ok"]
    assert not a.call("write_file", path="contract.md", text="Weaker acceptance")["ok"]
    for case_id in CASE_IDS:
        case = case_spec(case_id)
        assert case["purpose"] == "model_interface_development"
        assert not case["training_eligible"] and not case["independent_confirmation_eligible"]
        modified = copy.deepcopy(case)
        modified["purpose"] = "contribution_development"
        with pytest.raises(ValueError, match="source/purpose"):
            validate_case(modified)
    with pytest.raises(ValueError, match="first opportunity"):
        case_spec(CASE_IDS[0], first_member=MEMBERS[1])


def test_public_feedback_fixed_failure_and_latest_tree_only(tmp_path):
    prepared, ports = setup(tmp_path / "world", CASE_IDS[0])
    a = ports[MEMBERS[0]]
    before = a.observe()
    assert all(group["status"] == "untested" for group in before["current_version_test_coverage"].values())
    create(a, "chosen-work")
    checked(a, "write_file", path="test_member.py", text="assert 1 == 1\n")
    assert not a.call("submit_integration", message="No test or fixed patch")["ok"]
    feedback = checked(a, "run_tests")
    assert set(feedback["groups"]) == {"upstream_regressions", "public_normal", "member_tests"}
    assert feedback["groups"]["member_tests"]["passed"] is True
    assert feedback["groups"]["public_normal"]["passed"] is False
    assert "independent_acceptance" in feedback["untested"]
    checked(a, "fix_patch", task_ids=["chosen-work"], message="Known incomplete CPU control")
    delivery = checked(a, "submit_integration", message="Fixed failure is still a submission")
    assert delivery["accepted"] is None and not delivery["fixed_submission_is_acceptance"]
    assessment = assess_software_collaboration(prepared, run_root=tmp_path / "failed-assessment")
    assert assessment["submitted"] and assessment["R"] == 0
    write_solution(prepared, a)
    assert all(group["status"] == "untested" for group in a.observe()["current_version_test_coverage"].values())
    assert not a.call("submit_integration", message="Stale successful-looking tests do not count")["ok"]
    fixed_assessment = assess_software_collaboration(prepared, run_root=tmp_path / "still-fixed-failure")
    assert fixed_assessment["R"] == 0  # Unsaved repaired working bytes are never substituted.
    checked(a, "run_tests")
    checked(a, "fix_patch", task_ids=["chosen-work"], message="CPU positive control")
    latest = checked(a, "submit_integration", message="Explicit positive control, not model work")
    assessment = assess_software_collaboration(prepared, run_root=tmp_path / "success-assessment")
    assert assessment["R"] == 1
    assert assessment["source_reference"] == latest["source_reference"]
    assert assessment["files_sha256"] == latest["files_sha256"]


@pytest.mark.parametrize("case_id", CASE_IDS[2:4])
def test_repair_cases_have_real_forced_feedback_without_actor_credit(tmp_path, case_id):
    prepared, ports = setup(tmp_path / case_id, case_id)
    a = ports[MEMBERS[0]]
    initial = a.observe()["initial_public_feedback"]
    assert initial["origin"] == "forced_baseline_public_test"
    assert initial["executed"] and not initial["passed"]
    assert initial["actor_trajectory"] is False and initial["autonomous_failure_discovery"] is False
    assert software_collaboration_facts(prepared)["events"] == []
    assert a.observe()["tasks"] == {}
    assert all(group["status"] == "untested" for group in a.observe()["current_version_test_coverage"].values())


def test_repair_initial_situation_identity_excludes_measured_execution_duration(tmp_path):
    first, _ = setup(tmp_path / "first", CASE_IDS[2])
    second, _ = setup(tmp_path / "second", CASE_IDS[2])
    assert (first.prefix["prepared_business_state_sha256"]
            == second.prefix["prepared_business_state_sha256"])
    assert (tmp_path / "first/initial-public-execution.json").exists()
    assert (tmp_path / "second/initial-public-execution.json").exists()
