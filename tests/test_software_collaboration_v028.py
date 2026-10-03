"""Necessary v0.28 message/lifecycle checks on actual WorldCore receipts."""

import copy

import pytest

from proworksim.software_collaboration_v028 import (
    DIFF_MAX_PAGE_CHARS, DIFF_PAGE_CHARS, INTERFACE_REVISION, MEMBERS, PROJECT,
    SoftwareCollaborationPort, build_software_collaboration_case,
    case_spec, software_collaboration_facts,
)
from proworksim.software_collaboration_v027 import _diff
from proworksim.storage import digest


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


def test_diff_pages_reconstruct_large_overwrite_after_workspace_advances(tmp_path):
    prepared, a, _ = setup_case(tmp_path)
    baseline = copy.deepcopy(prepared.world._bundle(MEMBERS[0], baseline=True)[2])
    # Reproduce the real failure's recovery path: overwrite the whole upstream
    # fields.py with a short String class, then inspect the resulting large diff.
    changed = checked(a, "write_file", path="src/marshmallow/fields.py",
                      text="\nclass String(Field[str]):\n    pass  # 修复候选\n")
    snapshot = copy.deepcopy(prepared.world._bundle(MEMBERS[0])[2])
    expected = _diff(baseline["files"], snapshot["files"])
    assert len(expected) > 40_000
    page = checked(a, "diff_workspace")
    assert page["diff"] == expected[:DIFF_PAGE_CHARS]
    assert page["source_reference"] == changed["source_reference"]
    assert page["interface_revision"] == INTERFACE_REVISION
    assert a.observe()["interface_revision"] == INTERFACE_REVISION
    assert page["offset_unit"] == "unicode_characters"
    pinned, baseline_ref = page["source_reference"], page["base_reference"]
    checked(a, "write_file", path="consumer.py", text="# A later private version\n")
    pieces = []
    while True:
        assert page["total_chars"] == len(expected)
        assert page["diff_sha256"] == digest(expected.encode())
        assert page["source_reference"] == pinned
        assert page["base_reference"] == baseline_ref
        assert len(page["diff"]) <= DIFF_PAGE_CHARS
        pieces.append(page["diff"])
        if not page["has_more"]:
            assert page["next_offset"] is None
            break
        assert page["next_offset"] == page["offset"] + len(page["diff"])
        page = checked(a, "diff_workspace", offset=page["next_offset"], source_reference=pinned)
    assert "".join(pieces) == expected
    assert prepared.world._bundle(MEMBERS[0], reference=pinned)[2] == snapshot
    assert checked(a, "diff_workspace", source_reference=pinned)["diff"] == expected[:DIFF_PAGE_CHARS]
    assert checked(a, "diff_workspace", offset=len(expected), source_reference=pinned)["diff"] == ""


def test_diff_pages_keep_small_diffs_exact_and_enforce_bounds(tmp_path):
    prepared, a, _ = setup_case(tmp_path)
    empty = checked(a, "diff_workspace")
    assert empty["diff"] == "" and empty["total_chars"] == 0 and empty["has_more"] is False
    baseline = copy.deepcopy(prepared.world._bundle(MEMBERS[0], baseline=True)[2])
    checked(a, "write_file", path="consumer.py", text=baseline["files"]["consumer.py"] + "\n# 小改动\n")
    expected = _diff(baseline["files"], prepared.world._bundle(MEMBERS[0])[2]["files"])
    page = checked(a, "diff_workspace", max_chars=DIFF_MAX_PAGE_CHARS)
    assert page["diff"] == expected and page["has_more"] is False and page["next_offset"] is None
    assert page["diff_sha256"] == digest(expected.encode())
    for arguments in ({"max_chars": 0}, {"max_chars": DIFF_MAX_PAGE_CHARS + 1},
                      {"max_chars": True}, {"max_chars": "4000"}, {"offset": -1},
                      {"offset": True}, {"offset": "0"}, {"offset": 1},
                      {"offset": len(expected) + 1, "source_reference": page["source_reference"]}):
        assert not a.call("diff_workspace", **arguments)["ok"]
    unknown = {**page["source_reference"], "version_id": "v-does-not-exist"}
    assert not a.call("diff_workspace", source_reference=unknown)["ok"]


def test_diff_reference_cannot_read_unpublished_partner_versions(tmp_path):
    _, a, b = setup_case(tmp_path)
    private_before = a.observe()["workspace_reference"]
    assert not b.call("diff_workspace", source_reference=private_before)["ok"]
    checked(a, "claim_task", task_id="string_api")
    checked(a, "write_file", path="src/marshmallow/fields.py", text="# public patch\n")
    patch = checked(a, "fix_patch", task_ids=["string_api"], message="Publish exact version")
    first = checked(b, "diff_workspace", source_reference=patch["source_reference"])
    assert first["diff_sha256"] == patch["diff_sha256"]
    assert "diff" not in patch
    later = checked(a, "write_file", path="src/marshmallow/fields.py", text="# later private change\n")
    assert not b.call("diff_workspace", source_reference=later["source_reference"])["ok"]
    assert not b.call("diff_workspace", source_reference=private_before)["ok"]
    continued = checked(b, "diff_workspace", offset=first["next_offset"], source_reference=patch["source_reference"])
    assert continued["source_reference"] == first["source_reference"]
    assert continued["diff_sha256"] == patch["diff_sha256"]
