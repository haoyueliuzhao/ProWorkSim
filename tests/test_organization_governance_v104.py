"""CPU behavioral checks through the real world, tasks and immutable patches."""
from __future__ import annotations

import copy
import itertools

from proworksim import software_fixed_organization_runtime_v104 as runtime
from proworksim import software_fixed_organization_world_v104 as world
from proworksim.harness_port import HarnessPort
from proworksim.repository_sources_v054 import capture_repository, tree_manifest
from proworksim.software_organization_runtime_v047 import DispatchDeadline

M1, M2, M3, M4 = (f"member_{index:03d}" for index in range(1, 5))


def prepare(tmp_path, organization):
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.py").write_text("value = 0\n")
    manifest = capture_repository(source, tmp_path / "snapshot", task_id="fixture__governance-104",
        problem_statement="Synthetic fixture: update the public value.",
        source_identity={"instance_id": "fixture__governance-104", "repo": "fixture/governance",
                         "base_commit": "a" * 40, "dataset_revision": "b" * 40})
    calls = []

    def public_test(**payload):
        calls.append(copy.deepcopy(payload))
        return {"passed": False, "execution": {"executed": True,
            "input_tree_sha256": tree_manifest(payload["files"], payload["entry_metadata"])["tree_sha256"]},
            "groups": {"programmed": {"executed": True, "status": "failed", "passed": False,
                                      "tests": [{"test_id": "fixture", "passed": False}]}}}

    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = runtime.prepare_case(manifest, tmp_path / "world", organization_id=organization,
        max_total_tokens=5_000_000, public_test_callback=public_test, deadline=deadline)
    ports = {member: HarnessPort(world.SoftwareCollaborationPort(
        prepared.world.session(member, world.PROJECT), member), member, project_id=world.PROJECT,
        public_sink=lambda *_: None, world_sink=lambda *_: None, harness_sink=lambda *_: None)
        for member in prepared.case["active_roles"]}
    sequence = itertools.count()

    def call(member, tool, **arguments):
        return ports[member].call(tool, request_key=f"governance-{next(sequence)}",
                                  association={}, **arguments)

    for port in ports.values():
        port.tools()
    return prepared, ports, call, calls


def accepted(call, actor, tool, **arguments):
    result = call(actor, tool, **arguments)
    assert result["ok"], result
    return result["result"]


def denied(call, actor, tool, **arguments):
    result = call(actor, tool, **arguments)
    assert not result["ok"], result
    return result


def fixed(call, actor, value, *, task_ids=()):
    accepted(call, actor, "write_file", path="sample.py", text=f"value = {value}\n")
    accepted(call, actor, "run_tests")
    return accepted(call, actor, "fix_patch", task_ids=list(task_ids), message="Actual fixture version")


def task(call, task_id="repair"):
    return accepted(call, M1, "create_task", task_id=task_id, description="Repair the public value")


def chief_assignment(call, member, *, task_id="repair", revision=1):
    return accepted(call, M1, "org_assign_task", task_id=task_id, task_revision=revision,
                    assignee=member, priority=1, reason="Explicit lead decision")


def matrix_scope(call, *, revision=1, member=M3):
    return accepted(call, M1, "org_matrix_scope", task_id="repair", task_revision=revision,
                    assignee=member, priority=1, scope="Public value repair", reason="Scope agreement")


def matrix_review(call, actor, patch_id, decision="accept"):
    return accepted(call, actor, "org_matrix_review", patch_id=patch_id, task_ids=["repair"],
                    decision=decision, reason="Independent candidate decision")


def test_chief_authorizes_but_never_directly_changes_owner(tmp_path):
    prepared, _, call, _ = prepare(tmp_path, "CHIEF")
    task(call)
    denied(call, M2, "org_assign_task", task_id="repair", task_revision=1,
           assignee=M3, priority=1, reason="No authority")
    denied(call, M3, "claim_task", task_id="repair")
    chief_assignment(call, M3)
    prepared.world.state = prepared.world.store.load()
    assert prepared.world._task("repair")["owner"] is None
    accepted(call, M3, "claim_task", task_id="repair")
    chief_assignment(call, M4)
    prepared.world.state = prepared.world.store.load()
    assert prepared.world._task("repair")["owner"] == M3
    denied(call, M4, "claim_task", task_id="repair")
    denied(call, M3, "offer_transfer", task_id="repair", to_member=M4,
           reason="Star routing forbids direct spoke-to-spoke transfer")
    chief_assignment(call, M1)
    offer = accepted(call, M3, "offer_transfer", task_id="repair", to_member=M1,
                     reason="Current owner returns responsibility through the lead")
    chief_assignment(call, M2)
    denied(call, M1, "accept_transfer", offer_id=offer["offer_id"])
    chief_assignment(call, M1)
    accepted(call, M1, "accept_transfer", offer_id=offer["offer_id"])
    chief_assignment(call, M4)
    offer = accepted(call, M1, "offer_transfer", task_id="repair", to_member=M4,
                     reason="Lead forwards the accepted responsibility")
    accepted(call, M4, "accept_transfer", offer_id=offer["offer_id"])
    prepared.world.state = prepared.world.store.load()
    assert prepared.world._task("repair")["owner"] == M4


def test_chief_final_selection_binds_own_exact_fixed_version(tmp_path):
    _, _, call, _ = prepare(tmp_path, "CHIEF")
    candidate = fixed(call, M3, 1)
    denied(call, M1, "integrate_patch", patch_id=candidate["patch_id"])
    accepted(call, M1, "org_select_patch", patch_id=candidate["patch_id"], recipient=M1,
             reason="Choose actual published implementation")
    accepted(call, M1, "integrate_patch", patch_id=candidate["patch_id"])
    accepted(call, M1, "run_tests")
    final = accepted(call, M1, "fix_patch", task_ids=[], message="Exact integrated final tree")
    denied(call, M1, "submit_integration", message="Incoming selection is not a final decision")
    accepted(call, M1, "org_select_patch", patch_id=final["patch_id"], recipient=M1,
             reason="Final choice")
    accepted(call, M1, "submit_integration", message="Legal final version")
    fixed(call, M1, 2)
    denied(call, M1, "submit_integration", message="Old choice cannot cover new final code")


def test_review_acceptance_is_version_bound_and_independently_revocable(tmp_path):
    _, _, call, _ = prepare(tmp_path, "REVIEW")
    candidate = fixed(call, M1, 1)
    denied(call, M1, "org_review_patch", patch_id=candidate["patch_id"], decision="accept",
           reason="Author cannot self-review")
    denied(call, M1, "submit_integration", message="No independent review yet")
    accepted(call, M2, "org_review_patch", patch_id=candidate["patch_id"], decision="accept",
             reason="Review this exact fixed version")
    accepted(call, M1, "submit_integration", message="Executed tests need not all pass")
    accepted(call, M2, "org_review_patch", patch_id=candidate["patch_id"], decision="request_changes",
             reason="Explicit revised opinion")
    denied(call, M1, "submit_integration", message="Acceptance has been revoked")
    accepted(call, M2, "org_review_patch", patch_id=candidate["patch_id"], decision="accept",
             reason="Concern resolved without changing this version")
    updated = fixed(call, M1, 2)
    denied(call, M1, "submit_integration", message="Old acceptance expires on edit")
    accepted(call, M2, "org_review_patch", patch_id=updated["patch_id"], decision="accept",
             reason="Review changed candidate")
    accepted(call, M1, "submit_integration", message="New version reviewed")


def test_review_cannot_substitute_reviewer_private_candidate(tmp_path):
    _, _, call, _ = prepare(tmp_path, "REVIEW")
    candidate = fixed(call, M2, 4)
    denied(call, M2, "org_review_patch", patch_id=candidate["patch_id"], decision="accept",
           reason="My private candidate is not the author candidate")
    denied(call, M2, "submit_integration", message="No alternate export member")


def test_review_latest_opinion_controls_multiple_patch_ids_of_same_version(tmp_path):
    _, _, call, _ = prepare(tmp_path, "REVIEW")
    first = fixed(call, M1, 1)
    second = accepted(call, M1, "fix_patch", task_ids=[], message="Same source, another patch ID")
    assert first["patch_id"] != second["patch_id"]
    assert first["source_reference"] == second["source_reference"]
    accepted(call, M2, "org_review_patch", patch_id=first["patch_id"], decision="accept",
             reason="Initial review of this author version")
    accepted(call, M2, "org_review_patch", patch_id=second["patch_id"], decision="request_changes",
             reason="New concern about exactly the same version")
    denied(call, M1, "submit_integration", message="Old patch alias cannot bypass latest rejection")
    accepted(call, M2, "org_review_patch", patch_id=first["patch_id"], decision="accept",
             reason="Explicit latest acceptance after discussing the concern")
    accepted(call, M1, "submit_integration", message="Latest independent opinion accepts this version")


def test_matrix_requires_two_lanes_for_incoming_and_final_candidates(tmp_path):
    prepared, _, call, _ = prepare(tmp_path, "MATRIX")
    task(call)
    denied(call, M2, "org_matrix_scope", task_id="repair", task_revision=1,
           assignee=M3, priority=1, scope="Technical member cannot assign project scope", reason="No authority")
    matrix_scope(call)
    accepted(call, M3, "claim_task", task_id="repair")
    candidate = fixed(call, M3, 1, task_ids=["repair"])
    matrix_review(call, M1, candidate["patch_id"])
    denied(call, M1, "integrate_patch", patch_id=candidate["patch_id"])
    # The technical lead can inspect and test in its private tree before approval.
    accepted(call, M2, "integrate_patch", patch_id=candidate["patch_id"])
    accepted(call, M2, "run_tests")
    matrix_review(call, M2, candidate["patch_id"])
    accepted(call, M1, "integrate_patch", patch_id=candidate["patch_id"])
    accepted(call, M1, "run_tests")
    final = accepted(call, M1, "fix_patch", task_ids=[], message="Integrated exact final candidate")
    denied(call, M1, "submit_integration", message="Incoming approvals do not cover final identity")
    matrix_review(call, M1, final["patch_id"])
    denied(call, M1, "submit_integration", message="No unilateral project override")
    matrix_review(call, M2, final["patch_id"])
    accepted(call, M1, "submit_integration", message="Both authorities accepted final version")
    prepared.world.state = prepared.world.store.load()
    assert prepared.world._task("repair")["owner"] == M3
    changed = fixed(call, M1, 3)
    matrix_review(call, M1, changed["patch_id"])
    denied(call, M1, "submit_integration", message="Direct final edit still needs technical acceptance")


def test_matrix_scope_change_invalidates_both_lanes_and_reject_cannot_be_overridden(tmp_path):
    _, _, call, _ = prepare(tmp_path, "MATRIX")
    task(call)
    matrix_scope(call)
    accepted(call, M3, "claim_task", task_id="repair")
    candidate = fixed(call, M3, 1, task_ids=["repair"])
    matrix_review(call, M1, candidate["patch_id"])
    matrix_review(call, M2, candidate["patch_id"], "request_changes")
    matrix_review(call, M1, candidate["patch_id"])
    denied(call, M1, "integrate_patch", patch_id=candidate["patch_id"])
    matrix_review(call, M2, candidate["patch_id"])
    matrix_scope(call)
    denied(call, M1, "integrate_patch", patch_id=candidate["patch_id"])
    matrix_review(call, M1, candidate["patch_id"])
    denied(call, M1, "integrate_patch", patch_id=candidate["patch_id"])
    matrix_review(call, M2, candidate["patch_id"])
    accepted(call, M1, "integrate_patch", patch_id=candidate["patch_id"])


def test_matrix_task_revision_needs_new_scope_and_bound_candidate(tmp_path):
    _, _, call, _ = prepare(tmp_path, "MATRIX")
    task(call)
    matrix_scope(call)
    accepted(call, M3, "claim_task", task_id="repair")
    old = fixed(call, M3, 1, task_ids=["repair"])
    accepted(call, M3, "revise_task", task_id="repair", description="Revised public repair",
             expected_revision=1, reason="Actual task revision")
    denied(call, M1, "org_matrix_review", patch_id=old["patch_id"], task_ids=["repair"],
           decision="accept", reason="Old task snapshot cannot represent new scope")
    matrix_scope(call, revision=2)
    denied(call, M2, "org_matrix_review", patch_id=old["patch_id"], task_ids=["repair"],
           decision="accept", reason="New scope alone cannot upgrade the old patch")
    current = fixed(call, M3, 2, task_ids=["repair"])
    matrix_review(call, M1, current["patch_id"])
    matrix_review(call, M2, current["patch_id"])
    accepted(call, M1, "integrate_patch", patch_id=current["patch_id"])


def test_matrix_requires_all_candidate_tasks_and_blocks_implementer_signoff(tmp_path):
    _, _, call, _ = prepare(tmp_path, "MATRIX")
    task(call)
    matrix_scope(call)
    accepted(call, M3, "claim_task", task_id="repair")
    candidate = fixed(call, M3, 1, task_ids=["repair"])
    denied(call, M3, "org_matrix_review", patch_id=candidate["patch_id"], task_ids=["repair"],
           decision="accept", reason="Implementer has no authority lane")
    denied(call, M1, "org_matrix_review", patch_id=candidate["patch_id"], task_ids=[],
           decision="accept", reason="Cannot omit the task binding")


def test_matrix_same_version_patch_alias_cannot_bypass_newer_lane_rejection(tmp_path):
    _, _, call, _ = prepare(tmp_path, "MATRIX")
    task(call)
    matrix_scope(call)
    accepted(call, M3, "claim_task", task_id="repair")
    first = fixed(call, M3, 1, task_ids=["repair"])
    second = accepted(call, M3, "fix_patch", task_ids=["repair"], message="Another ID, same source")
    assert first["source_reference"] == second["source_reference"]
    matrix_review(call, M1, second["patch_id"])
    matrix_review(call, M2, second["patch_id"])
    matrix_review(call, M2, first["patch_id"], "request_changes")
    denied(call, M1, "integrate_patch", patch_id=second["patch_id"])
    matrix_review(call, M2, second["patch_id"])
    matrix_review(call, M1, first["patch_id"], "request_changes")
    denied(call, M1, "integrate_patch", patch_id=second["patch_id"])
    matrix_review(call, M1, second["patch_id"])
    accepted(call, M1, "integrate_patch", patch_id=second["patch_id"])
