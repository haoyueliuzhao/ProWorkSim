"""Public organization records must not disclose private repository activity."""
from __future__ import annotations

import copy

from test_organization_governance_v104 import M1, M2, M3, accepted, denied, fixed, prepare, task


def test_public_record_directory_and_private_event_isolation(tmp_path):
    prepared, ports, call, _ = prepare(tmp_path, "REVIEW")
    candidate = fixed(call, M1, 1)
    accepted(call, M2, "org_review_patch", patch_id=candidate["patch_id"],
             decision="accept", reason="Explicit public review of a fixed version")
    accepted(call, M2, "org_review_patch", patch_id=candidate["patch_id"],
             decision="request_changes", reason="Revised public assessment")
    accepted(call, M1, "write_file", path="sample.py", text="PRIVATE_AFTER_PUBLICATION_104 = 2\n")
    page = accepted(call, M1, "org_status", after_sequence=0, limit=1)
    assert page["complete"] is False and len(page["events"]) == 1
    next_page = accepted(call, M1, "org_status", after_sequence=page["next_after_sequence"], limit=1)
    assert next_page["complete"] is True and len(next_page["events"]) == 1
    assert next_page["events"][0]["sequence"] > page["events"][0]["sequence"]
    read = accepted(call, M1, "read_work_event", sequence=next_page["events"][0]["sequence"])
    assert read["decision"] == "request_changes"
    assert "PRIVATE_AFTER_PUBLICATION_104" not in str(ports[M2].observe())
    prepared.world.state = prepared.world.store.load()
    private = [e for e in prepared.world.state["software_events"]
               if e["actor_id"] == M1 and e["kind"] == "edit"][-1]
    denied(call, M2, "read_work_event", sequence=private["sequence"])
    records = prepared.world.reachable_events(M1, 0)
    assert any(e["sequence"] == read["sequence"] for e in records)


def test_invalid_schema_or_unscheduled_action_creates_no_decision(tmp_path):
    prepared, _, call, _ = prepare(tmp_path, "CHIEF")
    task(call)
    prepared.world.state = prepared.world.store.load()
    before = copy.deepcopy(prepared.world.org_state())
    denied(call, M1, "org_assign_task", task_id="repair", task_revision=1,
           assignee=M3, priority=1, reason="No trusted actor override", actor_id=M2)
    prepared.world.state = prepared.world.store.load()
    assert prepared.world.org_state() == before
    prepared.world.require_scheduled_actions = True
    prepared.world.scheduled_member = M2
    denied(call, M1, "org_assign_task", task_id="repair", task_revision=1,
           assignee=M3, priority=1, reason="Not the scheduled member")
    prepared.world.state = prepared.world.store.load()
    assert prepared.world.org_state() == before
    prepared.world.scheduled_member = M1
    accepted(call, M1, "org_assign_task", task_id="repair", task_revision=1,
             assignee=M3, priority=1, reason="Actual scheduled authority")
    prepared.world.state = prepared.world.store.load()
    assert prepared.world.org_state()["chief"]["assignments"]["repair"]["assignee"] == M3
