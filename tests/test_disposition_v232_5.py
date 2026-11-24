"""Reject misleading sender/recipient closure before a project message is recorded."""

import pytest
from proworksim.software_handoff_disposition_v232_5 import DecisionWorld, World
from proworksim.tool_outcomes import ToolRejection


def test_pending_and_recipient_guards(monkeypatch):
    world = DecisionWorld.__new__(DecisionWorld)
    duty = {"owner": "member_002", "recipient": "member_001", "status": "pending"}
    world.protocol = lambda: {"graph_control": {"duties": {"work_root": duty}}}
    world.decision_task = "work_root"
    world.sender_due = True
    world.full_exposures = {}
    ref = {"object_id": "code", "version_id": "v4"}
    world.org_current_identity = lambda actor: {"source_reference": ref}
    world.state = {
        "software_events": [
            {
                "actor_id": "member_001",
                "source_reference": {**ref, "version_id": "v3"},
                "kind": "test",
                "sequence": 40,
            }
        ]
    }
    called = []

    def native(self, actor, project, tool, args, profile):
        called.append((actor, tool))
        return {"message_sequence": 61}

    monkeypatch.setattr(World, "_tool_project_action", native)

    def send(actor, other, body):
        return world._tool_project_action(
            actor,
            "SOFTWARE27",
            "send_message",
            dict(recipient=other, task_id="work_root", body=body),
        )

    with pytest.raises(ToolRejection):
        world._tool_project_action(
            "member_002", "SOFTWARE27", "open_patch_review", {"patch_id": "patch-1"}
        )
    with pytest.raises(ToolRejection):
        send("member_001", "member_002", "ADOPT 60 Not delivered")
    duty.update(status="handed_off", message_sequence=60)
    with pytest.raises(ToolRejection):
        send("member_001", "member_002", "ADOPT 60 Preview alone")
    with pytest.raises(ToolRejection):
        send("member_001", "member_002", "SKIP 60 40 My evidence is stale")
    assert not called and "recipient_disposition" not in duty
    world.full_exposures[60] = "actual-request"
    send("member_001", "member_002", "DEFER 60 Need a second validation")
    with pytest.raises(ToolRejection):
        send("member_001", "member_002", "REJECT 60 Duplicate receipt")
    assert len(called) == 1 and duty["recipient_disposition"]["choice"] == "DEFER"
