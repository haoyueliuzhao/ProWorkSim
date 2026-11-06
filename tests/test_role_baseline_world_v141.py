"""Real managed transitions over tiny source trees, with actual CPU public tests."""
from __future__ import annotations

import copy
import itertools
import os
import subprocess
import sys

import pytest

from proworksim import software_role_baseline_world_v141 as world
from proworksim.harness_port import HarnessPort
from proworksim.repository_sources_v054 import capture_repository
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.storage import digest, json_bytes

M1, M2 = "member_001", "member_002"


def prepare(folder, group="FREE2"):
    source = folder / "source"
    source.mkdir(parents=True)
    (source / "sample.py").write_text("value = 1\n")
    (source / "test_sample.py").write_text("def test_value():\n    from sample import value\n    assert value == 2\n")
    task = "fixture__roles-141"
    manifest = capture_repository(source, folder / "snapshot", task_id=task,
        problem_statement="Synthetic CPU fixture: change value to 2 and preserve the public test.",
        source_identity={"instance_id": task, "repo": "fixture/roles",
                         "base_commit": "a"*40, "dataset_revision": "b"*40})
    entry = {"version": "v064-repository-public-test-entry-r1", "instance_id": task,
             "argv": [sys.executable, "-m", "pytest", "-q", "test_sample.py"], "cwd": "/testbed",
             "timeout_seconds": 20, "hidden_material_used": False}
    calls = []

    def public_test(*, files, entry_metadata, request):
        assert request["version"] == world.VERSION
        calls.append(copy.deepcopy(request))
        run = folder / "actual-public-tests" / str(len(calls))
        run.mkdir(parents=True)
        for name in ("sample.py", "test_sample.py"):
            (run / name).write_text(files[name])
        proc = subprocess.run(entry["argv"], cwd=run, capture_output=True, text=True, timeout=20,
                              env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
        passed = proc.returncode == 0
        counts = {"collected": 1, "passed": int(passed), "failed": int(not passed),
                  "errors": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "tests_run": 1}
        return {"passed": passed, "execution": {"executed": True,
            "input_tree_sha256": request["tree_sha256"], "actor_id": request["actor_id"],
            "organization_id": group, "managed_request_sha256": digest(json_bytes(request)),
            "argv": entry["argv"], "public_test_selection": request["public_test_selection"],
            "public_test_selection_revision": "v110-public-test-selection-r1",
            "validation_status": "verified" if passed else "failed", "counts": counts,
            "test_evidence": {"source": "actual synthetic CPU pytest subprocess", "returncode": proc.returncode}},
            "groups": {"public_repository_tests": {"passed": passed, "executed": True,
                "status": "passed" if passed else "failed", "output": proc.stdout[-4000:],
                "tests": [{"test_id": "test_sample.py::test_value", "passed": passed}]}},
            "repository_collection_errors": []}

    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = world.prepare_case(manifest, folder / "prepared", organization_id=group,
        public_test_callback=public_test, deadline=deadline, public_test_entry=entry)
    ports = {member: HarnessPort(world.SoftwareCollaborationPort(
        prepared.world.session(member, world.PROJECT), member), member, project_id=world.PROJECT,
        public_sink=lambda *_: None, world_sink=lambda *_: None, harness_sink=lambda *_: None)
        for member in prepared.case["active_roles"]}
    sequence = itertools.count()
    for port in ports.values():
        port.tools()

    def call(member, tool, **arguments):
        return ports[member].call(tool, request_key=f"v141-control-{next(sequence)}", association={}, **arguments)
    return prepared, ports, call, calls


def accepted(call, member, tool, **arguments):
    result = call(member, tool, **arguments)
    assert result["ok"], result
    return result["result"]


def denied(call, member, tool, code=None, **arguments):
    result = call(member, tool, **arguments)
    assert result["ok"] is False, result
    if code:
        assert result["error"]["rejection"]["code"] == code, result
    return result


@pytest.mark.parametrize("group,expected", [("S1", [M1]), ("FREE2", [M1, M2]), ("REVIEW2", [M1, M2])])
def test_roster_and_same_underlying_permissions(tmp_path, group, expected):
    prepared, ports, call, tests = prepare(tmp_path, group)
    assert prepared.case["active_roles"] == expected
    assert prepared.world.organization_active_members() == tuple(expected)
    assert list(prepared.world._software()["registry"]) == expected
    assert prepared.case["team_limits"]["max_total_tokens"] == 5_000_000
    names = [t["name"] for t in ports[M1].tools()]
    assert "org_status" in names and "org_declare_role" in names
    assert not {"terminal", "bash", "spawn_member", "org_sprint_start", "org_pipeline_design"} & set(names)
    if len(expected) == 1:
        assert not {"send_message", "handoff_patch", "offer_transfer", "accept_transfer",
                    "decline_transfer", "org_review_patch"} & set(names)
    else:
        assert ports[M1].tools() == ports[M2].tools()
        accepted(call, M2, "write_file", path="sample.py", text="value = 2\n")
        original = accepted(call, M1, "read_file", path="sample.py")
        assert "value = 1" in str(original)
        denied(call, M2, "submit_integration", code="fixed_delivery_member", message="Only fixed final identity")
    accepted(call, M1, "org_declare_role", role_label="Current focus", responsibility="Investigate public code", reason="Initial explicit focus")
    assert tests == []
    assert prepared.world._software()["deliveries"] == []


def test_free2_partner_changes_return_to001_without_automatic_work(tmp_path):
    prepared, ports, call, tests = prepare(tmp_path)
    accepted(call, M2, "write_file", path="sample.py", text="value = 2\n")
    patch = accepted(call, M2, "fix_patch", task_ids=[], message="Partner implementation")
    accepted(call, M2, "handoff_patch", patch_id=patch["patch_id"], to_member=M1, message="Please validate and integrate")
    assert "value = 1" in str(accepted(call, M1, "read_file", path="sample.py"))
    assert tests == []
    denied(call, M1, "org_review_patch", code="review_requires_adoption", patch_id=patch["patch_id"], decision="accept", reason="No adoption yet")
    accepted(call, M1, "write_file", path="sample.py", text="value = 2\n")
    accepted(call, M1, "run_tests")
    denied(call, M1, "org_review_patch", code="review_requires_adoption", patch_id=patch["patch_id"], decision="accept", reason="Equal bytes alone are not adoption")
    accepted(call, M1, "integrate_patch", patch_id=patch["patch_id"])
    denied(call, M1, "org_review_patch", code="review_requires_same_version_test", patch_id=patch["patch_id"], decision="accept", reason="No actual test yet")
    accepted(call, M1, "run_tests")
    decision = accepted(call, M1, "org_review_patch", patch_id=patch["patch_id"], decision="accept", reason="Actual adopted public tests passed")
    assert decision["test_evidence"]["passed"] is True
    assert decision["test_evidence"]["actor_id"] == M1
    fixed = accepted(call, M1, "fix_patch", task_ids=[], message="Explicitly integrated final version")
    delivered = accepted(call, M1, "submit_integration", message="Legal final result")
    assert delivered["source_reference"] == fixed["source_reference"]
    assert patch["patch_id"] in delivered["included_patch_ids"]
    assert delivered["organization_evidence"]["independent_review"] is None
    assert len(tests) == 2
    assert len(prepared.world._software()["deliveries"]) == 1
    assert ports[M1].observe()["delivery_status"]["legal_delivery_id"] == delivered["delivery_id"]


def test_review2_requires_actual_independent_adoption_and_current_test(tmp_path):
    prepared, _, call, tests = prepare(tmp_path, "REVIEW2")
    accepted(call, M1, "write_file", path="sample.py", text="value = 2\n")
    accepted(call, M1, "run_tests")
    patch = accepted(call, M1, "fix_patch", task_ids=[], message="Author's candidate")
    denied(call, M1, "submit_integration", code="final_review_required", message="No review")
    denied(call, M1, "org_review_patch", code="self_review_forbidden", patch_id=patch["patch_id"], decision="accept", reason="Self not independent")
    denied(call, M2, "org_review_patch", code="review_requires_adoption", patch_id=patch["patch_id"], decision="accept", reason="Merely published")
    accepted(call, M2, "integrate_patch", patch_id=patch["patch_id"])
    accepted(call, M2, "run_tests")
    accepted(call, M2, "org_review_patch", patch_id=patch["patch_id"], decision="accept", reason="Real independent check")
    accepted(call, M1, "submit_integration", message="Same-version accepted delivery")
    accepted(call, M1, "write_file", path="sample.py", text="value = 3\n")
    accepted(call, M1, "run_tests")
    accepted(call, M1, "fix_patch", task_ids=[], message="New unreviewed author version")
    denied(call, M1, "submit_integration", code="final_review_required", message="Old acceptance cannot authorize edited version")
    assert len(tests) == 3 and len(prepared.world._software()["deliveries"]) == 1


def test_review_alias_rejection_task_changes_and_private_state(tmp_path):
    prepared, ports, call, _ = prepare(tmp_path, "REVIEW2")
    accepted(call, M1, "create_task", task_id="repair", description="Repair public value")
    accepted(call, M1, "claim_task", task_id="repair", reason="Author accepts ownership")
    accepted(call, M1, "write_file", path="sample.py", text="value = 2\n")
    accepted(call, M1, "run_tests")
    patch = accepted(call, M1, "fix_patch", task_ids=["repair"], message="Version-bound owned task")
    accepted(call, M2, "integrate_patch", patch_id=patch["patch_id"])
    accepted(call, M2, "run_tests")
    accepted(call, M2, "org_review_patch", patch_id=patch["patch_id"], decision="accept", reason="Accept original revision")
    alias = accepted(call, M1, "fix_patch", task_ids=["repair"], message="Alias, same source version")
    rejected = accepted(call, M2, "org_review_patch", patch_id=alias["patch_id"], decision="request_changes", reason="Revise my explicit opinion")
    assert rejected["rework_responsible"] == M1
    denied(call, M1, "submit_integration", code="final_review_required", message="Older acceptance cannot bypass latest rejection")
    accepted(call, M2, "write_file", path="sample.py", text="private_unpublished_marker = 42\n")
    observation = ports[M1].observe()
    assert "private_unpublished_marker" not in str(observation)
    accepted(call, M1, "revise_task", task_id="repair", description="Clarified original issue", expected_revision=1, reason="Explicit task revision")
    denied(call, M2, "org_review_patch", code="stale_candidate_tasks", patch_id=patch["patch_id"], decision="request_changes", reason="Cannot use old task identity")
    prepared.world.state = prepared.world.store.load()
    private_event = [event for event in prepared.world.state["software_events"]
                     if event["kind"] == "edit" and event["actor_id"] == M2][-1]
    denied(call, M1, "read_work_event", sequence=private_event["sequence"])


def test_unknown_task_and_unscheduled_or_unknown_patch_do_not_mutate(tmp_path):
    prepared, _, call, _ = prepare(tmp_path)
    reply = denied(call, M1, "send_message", code="unknown_task_id", recipient=M2,
                   task_id="fixture__roles-141", body="Not a real task-board ID")
    assert reply["error"]["rejection"]["context"]["message_root_id"] == "root_goal"
    accepted(call, M1, "send_message", recipient=M2, task_id="root_goal", body="Choose responsibilities freely")
    denied(call, M1, "integrate_patch", code="unknown_published_patch", patch_id="private-not-published")
    accepted(call, M2, "write_file", path="sample.py", text="value = 2\n")
    peer_patch = accepted(call, M2, "fix_patch", task_ids=[], message="Published but not a scheduled adoption")
    before = copy.deepcopy(prepared.world._software()["organization_state"])
    before_identity = prepared.world.org_current_identity(M1)
    prepared.world.require_scheduled_actions = True
    prepared.world.scheduled_member = M2
    denied(call, M1, "integrate_patch", code="fixed_organization_schedule", patch_id=peer_patch["patch_id"])
    denied(call, M1, "org_declare_role", code="fixed_organization_schedule", role_label="Forged opportunity",
           responsibility="No scheduled action", reason="Must not change state")
    prepared.world.state = prepared.world.store.load()
    assert prepared.world._software()["organization_state"] == before
    assert prepared.world.org_current_identity(M1) == before_identity


def test_review_status_gives_adopt_test_member_decision_without_automatic_acceptance(tmp_path):
    prepared, _, call, tests = prepare(tmp_path, "REVIEW2")
    initial = accepted(call, M1, "org_status")
    assert initial["your_closure"]["next_explicit_action"]["tool"] == "read_task"
    accepted(call, M1, "write_file", path="sample.py", text="value = 2\n")
    accepted(call, M1, "run_tests")
    patch = accepted(call, M1, "fix_patch", task_ids=[], message="Final author candidate")
    accepted(call, M1, "handoff_patch", patch_id=patch["patch_id"], to_member=M2, message="Please review this exact candidate")
    assert accepted(call, M1, "org_status")["your_closure"]["next_explicit_action"]["tool"] == "staff_wait"
    status = accepted(call, M2, "org_status")
    assert status["your_closure"]["next_explicit_action"]['tool'] == 'integrate_patch'
    accepted(call, M2, "integrate_patch", patch_id=patch["patch_id"])
    status = accepted(call, M2, "org_status")
    assert status["your_closure"]["next_explicit_action"]["tool"] == "run_tests"
    accepted(call, M2, "run_tests")
    status = accepted(call, M2, "org_status")
    action = status["your_closure"]["next_explicit_action"]
    assert action["tool"] == "org_review_patch"
    assert "decision" not in action["arguments"] and "decision" in action["member_must_supply"]
    assert prepared.world.org_state()["reviews"] == []
    accepted(call, M2, "org_review_patch", patch_id=patch["patch_id"], decision="accept", reason="Own checked decision")
    assert accepted(call, M2, "org_status")["your_closure"]["next_explicit_action"]["tool"] == "staff_wait"
    assert accepted(call, M1, "org_status")["your_closure"]["next_explicit_action"]["tool"] == "submit_integration"
    assert len(tests) == 2 and prepared.world._software()["deliveries"] == []
    accepted(call, M1, "submit_integration", message="Record legal accepted candidate")
    rejected = accepted(call, M2, "org_review_patch", patch_id=patch["patch_id"], decision="request_changes", reason="New explicit concern after earlier submission")
    guidance = accepted(call, M1, "org_status")["your_closure"]
    assert guidance["legal_delivery_id"] is not None
    assert guidance["next_explicit_action"]['tool'] == 'read_work_event'
    assert guidance["next_explicit_action"]['arguments']['sequence'] == rejected['event_sequence']


@pytest.mark.parametrize("group", ["S1", "FREE2"])
def test_single_and_free_can_deliver_without_task_board_or_review_gate(tmp_path, group):
    prepared, _, call, _ = prepare(tmp_path, group)
    accepted(call, M1, "write_file", path="sample.py", text="value = 2\n")
    accepted(call, M1, "run_tests")
    fixed = accepted(call, M1, "fix_patch", task_ids=[], message="Direct work without ceremony")
    result = accepted(call, M1, "submit_integration", message="Explicit same-version delivery")
    assert result["source_reference"] == fixed["source_reference"]
    assert prepared.world.org_state()["reviews"] == []
