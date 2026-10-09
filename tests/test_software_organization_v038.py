"""Finite CPU organization controls, not model behavior or training evidence."""
import copy

import pytest

from proworksim import software_organization_tasks_v038 as source
from proworksim import software_tasks_v036 as parent_source
from proworksim.software_organization_v038 import (
    CASE_IDS, MEMBERS, PROJECT, ROOT_GOAL_ID, TEAM_LIMITS, SoftwareCollaborationPort,
    assess_software_collaboration, build_software_collaboration_case, case_spec,
    software_collaboration_facts, validate_case,
)


def checked(port, action, **arguments):
    response = port.call(action, **arguments)
    assert response["ok"], response
    return response["result"]


def setup(root, condition="O3", case_id=CASE_IDS[0]):
    prepared = build_software_collaboration_case(case_spec(case_id, condition=condition), root)
    return prepared, {member: port(prepared, member) for member in prepared.case["active_roles"]}


def port(prepared, member):
    return SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member)


def create(actor, task_id="work"):
    checked(actor, "create_task", task_id=task_id, description="CPU-selected public work")
    return checked(actor, "claim_task", task_id=task_id)


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_new_purpose_identity_preserves_all_quality_assets(case_id):
    variant = source.build_case(case_id)
    old = parent_source.build_case(variant["original_case_id"])
    assert variant["purpose"] == "organization_development"
    assert not variant["training_eligible"] and not variant["independent_confirmation_eligible"]
    assert variant["task_definitions"] == {} and variant["initial_owners"] == {}
    assert variant["files"]["contract.md"].replace(source.NEW_ORGANIZATION, source.OLD_ORGANIZATION) == old["root_goal"]
    assert {k: v for k, v in variant["files"].items() if k != "contract.md"} == {
        k: v for k, v in old["files"].items() if k != "contract.md"}
    assert variant["editable_paths"] == old["editable_paths"]
    for key in ("public_checks_sha256", "independent_verifier_sha256", "contract_symbols", "complete_delivery_requires"):
        assert variant["source_contract"][key] == old["source_contract"][key]
    assert variant["source_partition_sha256"] != old["source_partition_sha256"]
    assert variant["source_contract"]["source_manifest_sha256"] == source.source_manifest()["sha256"]
    assert variant["source_contract"]["source_manifest_sha256"] != old["source_contract"]["source_manifest_sha256"]
    assert variant["source_contract"]["parent_source_manifest_sha256"] == old["source_contract"]["source_manifest_sha256"]
    for condition in ("O1", "O2", "O3"):
        case = case_spec(case_id, condition=condition)
        assert case["team_limits"] == TEAM_LIMITS
        assert case["root_goal"] == variant["root_goal"]
        changed = copy.deepcopy(case)
        changed["training_eligible"] = True
        with pytest.raises(ValueError, match="Frozen"):
            validate_case(changed)


@pytest.mark.parametrize("condition,count", [("O1", 2), ("O2", 4)])
def test_fixed_birth_sets_allow_voluntary_exit_without_replacement(tmp_path, condition, count):
    prepared, ports = setup(tmp_path / "run", condition)
    a = ports[MEMBERS[0]]
    assert a.observe()["tasks"] == {}
    assert len(prepared.world.live_members()) == count
    assert not a.call("spawn_member", briefing="An unauthorized fixed-condition birth")["ok"]
    checked(a, "retire_member", reason="Voluntary completion of my opportunities")
    assert len(prepared.world.live_members()) == count - 1
    assert not a.call("create_task", task_id="revive", description="Cannot revive")["ok"]
    assert not ports[MEMBERS[1]].call("spawn_member", briefing="Cannot replace retired member", replaces=MEMBERS[0])["ok"]


def test_task_ownership_is_not_file_acl_and_transfers_require_consent(tmp_path):
    prepared, ports = setup(tmp_path / "run", "O2")
    a, b, c = [ports[m] for m in MEMBERS[:3]]
    # Direct work is legal before task registration.
    checked(c, "write_file", path="test_member.py", text="assert 3 == 3\n")
    assert c.observe()["tasks"] == {}
    create(a)
    offer = checked(a, "offer_transfer", task_id="work", to_member=MEMBERS[1], reason="Please review ownership")
    assert b.observe()["tasks"]["work"]["owner"] == MEMBERS[0]
    assert not c.call("accept_transfer", offer_id=offer["offer_id"])["ok"]
    checked(b, "decline_transfer", offer_id=offer["offer_id"], reason="I choose a different scope")
    assert a.observe()["tasks"]["work"]["owner"] == MEMBERS[0]
    offer2 = checked(a, "offer_transfer", task_id="work", to_member=MEMBERS[2], reason="A new proposal")
    checked(c, "accept_transfer", offer_id=offer2["offer_id"])
    assert c.observe()["tasks"]["work"]["owner"] == MEMBERS[2]
    # A nonowner may still edit every editable file in their private tree.
    checked(a, "write_file", path="test_member.py", text="assert 1 == 1\n")
    assert not a.call("revise_task", task_id="work", description="Unauthorized revision", expected_revision=1, reason="No longer owner")["ok"]
    offer3 = checked(c, "offer_transfer", task_id="work", to_member=MEMBERS[1], reason="Before a scope revision")
    checked(c, "revise_task", task_id="work", description="Revised public scope", expected_revision=1, reason="New scope")
    assert not b.call("accept_transfer", offer_id=offer3["offer_id"])["ok"]
    checked(b, "decline_transfer", offer_id=offer3["offer_id"], reason="Obsolete revision")
    events = software_collaboration_facts(prepared)["events"]
    original_offer = next(e for e in events if e["kind"] == "transfer_offered")
    assert original_offer["status"] == "pending" and original_offer["task_snapshot"]["owner"] == MEMBERS[0]
    assert any(e["kind"] == "transfer_accepted" and e["previous_owner"] == MEMBERS[0] for e in events)
    assert not a.call("delegate_task", task_id="work", to_member=MEMBERS[1])["ok"]


def test_dynamic_capacity_waiting_birth_cap_nonreused_ids_and_obligations(tmp_path):
    prepared, ports = setup(tmp_path / "run")
    a, b = [ports[m] for m in MEMBERS[:2]]
    create(a)
    third = checked(b, "spawn_member", briefing="Choose useful work from the public goal")
    fourth = checked(a, "spawn_member", briefing="Examine the public contract")
    assert [third["member_id"], fourth["member_id"]] == list(MEMBERS[2:4])
    prepared.world.runtime_availability = lambda: {m: {"status": "waiting", "remaining_decisions": 80,
        "can_receive_work": True} for m in prepared.world.live_members()}
    assert not b.call("spawn_member", briefing="Waiting must not free capacity")["ok"]
    prepared.world.retire_member(MEMBERS[0], reason="staff_done")
    observed = b.observe()
    assert observed["tasks"]["work"]["owner"] == MEMBERS[0]
    assert observed["orphan_obligations"][0]["task_id"] == "work"
    assert not b.call("claim_task", task_id="work")["ok"]
    checked(b, "claim_task", task_id="work", reason="Explicitly accepting the retired member's obligation")
    fifth = checked(b, "spawn_member", briefing="A bounded replacement", replaces=MEMBERS[0])
    assert fifth["member_id"] == MEMBERS[4]
    checked(port(prepared, MEMBERS[2]), "retire_member", reason="Release my remaining opportunity")
    sixth = checked(b, "spawn_member", briefing="Final permitted birth", replaces=MEMBERS[2])
    assert sixth["member_id"] == MEMBERS[5]
    checked(port(prepared, MEMBERS[3]), "retire_member", reason="Retire after the birth cap")
    assert not b.call("spawn_member", briefing="Must not reset cumulative births")["ok"]
    registry = software_collaboration_facts(prepared)["registry"]
    assert list(registry) == list(MEMBERS)
    assert len(prepared.world.live_members()) == 3
    assert all(not row["private_history_copied"] for row in registry.values())
    assert b.observe()["team_test_budget"]["used"] == 0


def test_birth_baseline_or_explicit_fixed_snapshot_and_private_information(tmp_path):
    prepared, ports = setup(tmp_path / "run")
    a, b = [ports[m] for m in MEMBERS[:2]]
    create(a)
    first_edit = checked(a, "write_file", path="test_member.py", text="assert 111 == 111\n")
    patch = checked(a, "fix_patch", task_ids=["work"], message="Published exact snapshot")
    later_edit = checked(a, "write_file", path="test_member.py", text="PRIVATE_LATER_VALUE = 222\n")
    checked(a, "send_message", recipient=MEMBERS[1], task_id=ROOT_GOAL_ID, body="Private addressed dialogue sentinel")
    child = checked(a, "spawn_member", briefing="Only this explicit briefing sentinel", patch_id=patch["patch_id"])
    child_port = port(prepared, child["member_id"])
    child_obs = child_port.observe()
    assert child_obs["own_initial_briefing"] == "Only this explicit briefing sentinel"
    assert child_obs["messages"] == []
    assert "briefing" not in child_obs["member_registry"][MEMBERS[0]]
    assert checked(child_port, "read_file", path="test_member.py", start_line=1, max_lines=10)["text"] == "assert 111 == 111"
    assert patch["patch_id"] in child_obs["included_patch_ids"]
    assert checked(child_port, "diff_workspace", source_reference=first_edit["source_reference"])["source_reference"] == first_edit["source_reference"]
    assert not child_port.call("diff_workspace", source_reference=later_edit["source_reference"])["ok"]
    fourth = checked(b, "spawn_member", briefing="Start from the public baseline")
    fourth_port = port(prepared, fourth["member_id"])
    assert "assert 111" not in checked(fourth_port, "read_file", path="test_member.py", start_line=1, max_lines=10)["text"]
    assert "assert 111" in checked(fourth_port, "read_file", patch_id=patch["patch_id"], path="test_member.py", start_line=1, max_lines=10)["text"]
    assert not fourth_port.call("read_work_event", sequence=next(e["sequence"] for e in software_collaboration_facts(prepared)["events"] if e["kind"] == "work_message"))["ok"]
    assert not fourth_port.call("read_work_event", sequence=child["birth_sequence"])["ok"]
    for path in ("acceptance.json", "../private/acceptance.json", "contract.md", "schema/__init__.py"):
        assert not fourth_port.call("write_file", path=path, text="Weaken quality")["ok"]
    assert not fourth_port.call("read_file", path="acceptance.json", start_line=1, max_lines=10)["ok"]
    assert not b.call("spawn_member", briefing="Private references forbidden", source_reference=later_edit["source_reference"])["ok"]


def test_reachable_events_exclude_private_work_and_unaddressed_messages(tmp_path):
    prepared, ports = setup(tmp_path / "run", "O2")
    a, b, c = [ports[m] for m in MEMBERS[:3]]
    checked(a, "write_file", path="test_member.py", text="assert 1 == 1\n")
    checked(a, "send_message", recipient=MEMBERS[1], task_id=ROOT_GOAL_ID, body="A real addressed message")
    assert [e["kind"] for e in prepared.world.reachable_events(MEMBERS[1])] == ["work_message"]
    assert prepared.world.reachable_events(MEMBERS[2]) == []
    create(a)
    fixed = checked(a, "fix_patch", task_ids=["work"], message="Published work")
    assert [e["kind"] for e in prepared.world.reachable_events(MEMBERS[2])] == ["task_created", "claim", "patch_fixed"]
    checked(a, "handoff_patch", patch_id=fixed["patch_id"], to_member=MEMBERS[3], message="Any live member is addressable")
    assert ports[MEMBERS[3]].observe()["handoffs"][-1]["recipient"] == MEMBERS[3]
    assert not c.call("send_message", recipient=MEMBERS[2], task_id=ROOT_GOAL_ID, body="Cannot self message")["ok"]
    checked(b, "retire_member", reason="No responsibility to transfer")
    assert not a.call("send_message", recipient=MEMBERS[1], task_id=ROOT_GOAL_ID, body="No delivery to retired identity")["ok"]


def test_multiworkspace_conflicts_historical_patches_and_exact_submission_gate(tmp_path):
    prepared, ports = setup(tmp_path / "run", "O2")
    a, b = [ports[m] for m in MEMBERS[:2]]
    create(a, "upstream")
    create(b, "assembly")
    checked(a, "write_file", path="test_member.py", text="assert 1 == 1\n")
    patch = checked(a, "fix_patch", task_ids=["upstream"], message="One real private version")
    checked(b, "write_file", path="test_member.py", text="assert 2 == 2\n")
    merged = checked(b, "integrate_patch", patch_id=patch["patch_id"])
    assert merged["conflicts"] == ["test_member.py"]
    checked(b, "write_file", path="test_member.py", text="assert 1 == 1\nassert 2 == 2\n")
    assert "assert 2" not in checked(a, "read_file", patch_id=patch["patch_id"], path="test_member.py", start_line=1, max_lines=10)["text"]
    before = assess_software_collaboration(prepared, run_root=tmp_path / "unsubmitted-not-assessed")
    assert before["R"] == 0 and not (tmp_path / "unsubmitted-not-assessed").exists()
    assert not b.call("submit_integration")["ok"]
    tested = checked(b, "run_tests")
    assert tested["executed"] and tested["team_test_budget"]["used"] == 1
    assert not b.call("submit_integration")["ok"]
    checked(b, "fix_patch", task_ids=["assembly"], message="Tests may fail; submission is not acceptance")
    assert checked(b, "submit_integration")["accepted"] is None
    checked(b, "write_file", path="test_member.py", text="assert 4 == 4\n")
    assert not b.call("submit_integration")["ok"]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_unchanged_private_and_public_quality_on_cpu_reference(tmp_path, case_id):
    # A reference positive control, never model evidence or visible preparation.
    result = source.assess_files(case_id, source.reference_solution(case_id), run_root=tmp_path / case_id)
    assert result["executed"] and result["passed"]
    assert result["purpose"] == "organization_development"
    assert not result["training_eligible"] and not result["independent_confirmation_eligible"]


def test_explicit_new_offer_replaces_unreachable_retired_recipient(tmp_path):
    prepared, ports = setup(tmp_path / "run", "O2")
    a, b, c = [ports[m] for m in MEMBERS[:3]]
    create(a)
    first = checked(a, "offer_transfer", task_id="work", to_member=MEMBERS[1], reason="Proposal before retirement")
    checked(b, "retire_member", reason="I do not accept this proposal")
    assert a.observe()["tasks"]["work"]["owner"] == MEMBERS[0]
    second = checked(a, "offer_transfer", task_id="work", to_member=MEMBERS[2], reason="Explicit replacement proposal")
    checked(c, "accept_transfer", offer_id=second["offer_id"])
    facts = software_collaboration_facts(prepared)
    assert facts["transfer_offers"][first["offer_id"]]["status"] == "expired"
    original = next(e for e in facts["events"] if e["kind"] == "transfer_offered")
    assert original["status"] == "pending" and original["recipient"] == MEMBERS[1]
    assert facts["tasks"]["work"]["owner"] == MEMBERS[2]


def test_direct_concentrated_work_can_submit_without_task_registration(tmp_path):
    prepared, ports = setup(tmp_path / "run", "O1")
    a = ports[MEMBERS[0]]
    checked(a, "write_file", path="test_member.py", text="assert 1 == 1\n")
    assert not a.call("fix_patch", task_ids=[ROOT_GOAL_ID], message="The root is not an execution task")["ok"]
    tested = checked(a, "run_tests")
    fixed = checked(a, "fix_patch", task_ids=[], message="Explicitly unbound concentrated work")
    assert fixed["task_ids"] == [] and fixed["task_snapshots"] == {}
    assert checked(a, "submit_integration")["accepted"] is None
    facts = software_collaboration_facts(prepared)
    assert facts["tasks"] == {}
    assert facts["deliveries"][-1]["source_reference"] == tested["source_reference"]
    assert facts["patches"][fixed["patch_id"]]["task_snapshots"] == {}
