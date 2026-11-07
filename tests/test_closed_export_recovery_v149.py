"""Identity repair uses actual fixed-world closure; unfinished work stays unknown."""

from __future__ import annotations

import copy
import json

import pytest

from proworksim import software_benchmark_project_closure_v149 as closure
from proworksim import software_benchmark_closed_export_recovery_v149 as recovery
from proworksim.software_benchmark_alignment_contract_v141 import condition
from proworksim.software_benchmark_candidates_v054 import checked
from test_role_controller_closure_v141 import fixture


def identity(prepared, group, slot="independent-run:any-opaque-id"):
    spec = condition(group)
    return {
        "slot_id": slot,
        "instance_id": prepared.case["case_id"],
        "condition_id": spec["condition_id"],
        "seed": 141,
        "organization_id": group,
        "group_id": group,
        "arm": "PROJECT",
        "execution_arm": "PROJECT",
        "fixed_members": spec["fixed_members"],
        "member_count": spec["member_count"],
    }


@pytest.mark.parametrize("group", ["FREE2", "REVIEW2"])
def test_real_completed_world_new_identity_preserves_terminal_and_legal_delivery(tmp_path, group):
    prepared, _, call, _ = fixture.prepare(tmp_path / "world", group)

    def act(member, tool, **args):
        return fixture.accepted(call, member, tool, **args)

    act("member_001", "write_file", path="sample.py", text="value = 2\n")
    act("member_001", "run_tests")
    patch = act("member_001", "fix_patch", task_ids=[], message="Existing exact code")
    if group == "REVIEW2":
        act("member_002", "integrate_patch", patch_id=patch["patch_id"])
        act("member_002", "run_tests")
        act(
            "member_002",
            "org_review_patch",
            patch_id=patch["patch_id"],
            decision="accept",
            reason="Existing accepted version",
        )
    act("member_001", "submit_integration", message="Existing real delivery")
    act("member_001", "write_file", path="sample.py", text="value = 3\n")
    row = identity(prepared, group)
    result = closure.export_managed_closure(
        prepared,
        tmp_path / "closed",
        slot_id=row["slot_id"],
        sdk_closed=True,
        validated_identity=row,
    )
    evidence = json.loads(checked(result["delivery_evidence"]).read_bytes())
    snapshot = json.loads(checked(result["delivery_snapshot"]).read_bytes())
    baseline = json.loads(checked(result["baseline_snapshot"]).read_bytes())
    assert evidence["slot_id"] == snapshot["slot_id"] == row["slot_id"]
    assert evidence["execution_identity"] == row
    assert result["terminal_bundle"]["files"]["sample.py"] == "value = 3\n"
    assert snapshot["candidate"]["files"]["sample.py"] == "value = 2\n"
    assert result["submitted"] and result["same_tree"] is False
    assert closure.validate_delivery_evidence(evidence, snapshot, baseline)[
        "organization_submission_verified"
    ]
    bad = copy.deepcopy(evidence)
    bad["execution_identity"]["seed"] += 1
    with pytest.raises(ValueError):
        closure.validate_delivery_evidence(bad, snapshot, baseline)


def test_unfinished_sdk_does_not_acquire_closed_export(tmp_path):
    prepared, _, _, _ = fixture.prepare(tmp_path / "world", "FREE2")
    row = identity(prepared, "FREE2")
    with pytest.raises(ValueError, match="SDK must close"):
        closure.export_managed_closure(
            prepared,
            tmp_path / "closed",
            slot_id=row["slot_id"],
            sdk_closed=False,
            validated_identity=row,
        )
    assert not (tmp_path / "closed").exists()


def test_completed_work_proof_rejects_API_failure_before_archive_read():
    row = {
        "slot_id": "v146:opaque",
        "instance_id": "fixture__task-1",
        "seed": 141,
        "organization_id": "FREE2",
        "group_id": "FREE2",
        "condition_id": condition("FREE2")["condition_id"],
        "arm": "PROJECT",
        "execution_arm": "PROJECT",
        "fixed_members": ["member_001", "member_002"],
        "member_count": 2,
    }
    child = {
        "status": "technical_unknown",
        "error": {
            "type": "ValueError",
            "message": "An exact v142 task/organization/seed identity is required",
        },
        "traceback": "software_benchmark_project_closure_v141.py validate_slot_identity",
        "managed_boundary": {
            "status": "bounded_work_closed",
            "execution_integrity_failure": {"status": "model_service_error"},
        },
    }
    with pytest.raises(ValueError, match="solely identity-export"):
        recovery.validate_completed_work(row, {"status": "technical_unknown"}, child, {}, {}, {})
