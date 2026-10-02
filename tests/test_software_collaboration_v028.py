"""Necessary v0.28 message/lifecycle checks on actual WorldCore receipts."""

import copy

import pytest

from proworksim.software_collaboration_v028 import (
    MEMBERS, PROJECT, SoftwareCollaborationPort, build_software_collaboration_case,
    case_spec, software_collaboration_facts,
)


def setup_case(tmp_path):
    prepared = build_software_collaboration_case(case_spec(), tmp_path / "case")
    return prepared, *(SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member) for member in MEMBERS)


def checked(port, name, **arguments):
    result = port.call(name, **arguments)
    assert result["ok"], result
    return result["result"]


def test_message_before_edit_reaches_only_addressee_and_does_not_import(tmp_path):
    prepared, a, b = setup_case(tmp_path)
    before = {member: copy.deepcopy(prepared.world._bundle(member)[2]) for member in MEMBERS}
    result = checked(a, "send_message", recipient=MEMBERS[1], task_id="string_api", body="Agree on optional keyword before implementation.")
    assert result["world_file_effect"] is False
    assert not a.observe()["messages"]
    received = b.observe()["messages"][-1]
    assert received["body"] == "Agree on optional keyword before implementation."
    assert received["actor_id"] == MEMBERS[0]
    assert all(task["owner"] is None for task in b.observe()["tasks"].values())
    for member in MEMBERS:
        assert prepared.world._bundle(member)[2] == before[member]
    commit = prepared.world.store.load()["operation_commits"][received["operation_id"]]
    assert commit["public_result"]["action_id"] == received["action_id"]
    private = a.observe()["workspace_reference"]
    assert not a.call("send_message", recipient=MEMBERS[1], task_id="string_api", body="private", fixed_reference=private)["ok"]


def test_delegation_notifies_and_return_releases_without_silent_reassignment(tmp_path):
    prepared, a, b = setup_case(tmp_path)
    checked(a, "claim_task", task_id="string_api")
    checked(a, "delegate_task", task_id="string_api", to_member=MEMBERS[1])
    notice = b.observe()["messages"][-1]
    assert notice["kind"] == "delegate" and notice["owner"] == MEMBERS[1]
    checked(b, "return_task", task_id="string_api", reason="Cannot finish this; returning to board")
    assert a.observe()["messages"][-1]["kind"] == "task_returned"
    assert a.observe()["tasks"]["string_api"]["owner"] is None
    assert not b.call("return_task", task_id="string_api", reason="No longer mine")["ok"]
    checked(a, "claim_task", task_id="string_api")
    facts = software_collaboration_facts(prepared)
    assert [event["kind"] for event in facts["events"]] == ["claim", "delegate", "task_returned", "claim"]


@pytest.mark.parametrize("status,remaining", [("completed", 4), ("model_budget_exhausted", 0), ("environment_error", 4)])
def test_cannot_transfer_or_message_terminal_member(tmp_path, status, remaining):
    prepared, a, _ = setup_case(tmp_path)
    checked(a, "claim_task", task_id="string_api")
    prepared.world.runtime_availability = lambda: {
        MEMBERS[0]: {"status": "ready", "remaining_decisions": 10, "can_receive_work": True},
        MEMBERS[1]: {"status": status, "remaining_decisions": remaining, "can_receive_work": False}}
    assert not a.call("delegate_task", task_id="string_api", to_member=MEMBERS[1])["ok"]
    assert not a.call("send_message", recipient=MEMBERS[1], task_id="string_api", body="wake")["ok"]
    assert a.observe()["tasks"]["string_api"]["owner"] == MEMBERS[0]


def test_bounded_message_projection_retains_exact_retrievable_original(tmp_path):
    _, a, b = setup_case(tmp_path)
    for index in range(6):
        checked(a, "send_message", recipient=MEMBERS[1], task_id="string_api", body=str(index) + "x" * 1000)
    observed = b.observe()
    assert len(observed["messages"]) == 4
    assert observed["older_message_sequences"] == [1, 2]
    assert len(observed["messages"][-1]["body"]) == 500
    assert observed["messages"][-1]["body_truncated"] is True
    assert checked(b, "read_work_event", sequence=1)["body"] == "0" + "x" * 1000
    assert not a.call("send_message", recipient=MEMBERS[1], task_id="string_api", body="x" * 4001)["ok"]


def test_cases_fix_first_opportunity_and_limits_without_relabeling_source():
    a, b = case_spec(), case_spec(first_member=MEMBERS[1])
    assert a != b and a["case_id"] == b["case_id"]
    assert a["role_decision_limits"] == dict.fromkeys(MEMBERS, 48)
    assert not a["training_eligible"] and not a["independent_confirmation_eligible"]
    with pytest.raises(ValueError, match="decision limit"):
        case_spec(role_decision_limits=dict.fromkeys(MEMBERS, 0))
