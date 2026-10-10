"""Necessary page truth, immutable versions, permissions and optional-reading controls."""
import copy
import json

import pytest

from proworksim.software_organization_v042 import (
    CASE_IDS, MEMBERS, PAGE_BODY_CHARACTERS, PROJECT, SoftwareCollaborationPort,
    build_software_collaboration_case, build_test_report, case_spec, material,
    test_result_page as report_page,
)
from proworksim.storage import digest, json_bytes
from proworksim.tool_outcomes import ToolRejection


def visible_fixture():
    return {"public_diagnostics": {"diagnostic_a": {"diagnostic_id": "root:diagnostic_a", "passed": False,
        "tests": [{"test_id": "long-original-item", "passed": False, "observed": "汉🙂" * 4000},
                  {"test_id": "later-original-item", "passed": True}]}},
        "groups": {"public_normal": {"status": "failed", "tests": [{"test_id": "same-literal-id", "status": "failed"}]}},
        "source_reference": {"object_id": "work-copy", "version_id": "v1"}, "files_sha256": "fixture-files-sha",
        "executed": True, "passed": False, "scope": "Original public fixture only", "untested": ["independent_acceptance"],
        "independent_acceptance": "not_run_by_public_tool", "fixed_submission_is_acceptance": False}


def identity(sequence=1):
    return {"world_id": "world", "instance_id": "instance", "branch_id": "branch", "project_id": PROJECT,
            "actor_id": MEMBERS[0], "test_event_sequence": sequence, "operation_id": "actual-operation-" + str(sequence)}


def test_long_unicode_item_pages_reconstruct_exact_original_and_distinct_events_stay_distinct():
    original = visible_fixture()
    before = copy.deepcopy(original)
    report = build_test_report(original, actor_id=MEMBERS[0], event_identity=identity())
    assert original == before and report["body"] == json_bytes(original).decode()
    assert "".join(page["text"] for page in report["pages"]) == report["body"]
    assert all(0 < len(page["text"]) <= PAGE_BODY_CHARACTERS for page in report["pages"])
    assert any(any(part["path"].endswith("/tests/0") for part in page["split_entries"]) for page in report["pages"])
    recovered, cursor = [], None
    while True:
        reply = report_page(report, cursor)
        page = reply["page"]
        assert page["text"] == report["body"][page["start"]:page["end"]]
        assert page["sha256"] == digest(page["text"].encode())
        assert report_page(report, page["cursor"]) == reply
        assert ("directory" in reply) is (page["index"] == 0)
        recovered.append(page["text"])
        cursor = page["next_cursor"]
        if cursor is None:
            assert page["is_last"] and page["remaining_pages"] == 0
            break
    assert "".join(recovered) == report["body"]
    other = build_test_report(original, actor_id=MEMBERS[0], event_identity=identity(2))
    assert other["body"] == report["body"] and other["report_id"] != report["report_id"]
    with pytest.raises(ToolRejection, match="cursor"):
        report_page(other, report["pages"][0]["cursor"])
    directory = report["directory"]
    assert [row["group_id"] for row in directory] == ["diagnostic_a", "public_normal"]
    assert [row["test_id"] for row in directory[0]["entries"]] == ["long-original-item", "later-original-item"]
    assert "observed" not in json.dumps(directory)


def test_real_test_runs_once_old_pages_survive_edits_and_partner_or_newborn_ids_give_no_access(tmp_path):
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0], condition="PB"), tmp_path / "case")
    world = prepared.world
    assert world._software()["test_reports"] == {}
    session = world.session(MEMBERS[0], PROJECT)
    result = session.call("run_tests")
    assert result["ok"], result
    first = result["result"]
    report_id = first["report_id"]
    report = copy.deepcopy(world._software()["test_reports"][report_id])
    assert report["body"] == json_bytes(report["visible_result"]).decode()
    assert world.test_budget.snapshot()["used"] == 1
    cursor = first["page"]["next_cursor"]
    before = session.call("read_test_result", report_id=report_id, cursor=cursor)
    assert before["ok"] and before["result"]["page"]["index"] == 1
    path = next(name for name in prepared.case["editable_paths"] if name != "test_member.py")
    assert session.call("write_file", path=path, text=material(CASE_IDS[0])["files"][path] + "\n# later private version\n")["ok"]
    again = session.call("read_test_result", report_id=report_id, cursor=cursor)
    assert again["result"] == before["result"]
    assert again["result"]["source_reference"] != SoftwareCollaborationPort(session, MEMBERS[0]).observe()["workspace_reference"]
    assert world._software()["test_reports"][report_id] == report
    born = session.call("spawn_member", briefing="Only an ID was shared: " + report_id)
    assert born["ok"], born
    child = born["result"]["member_id"]
    for member in (MEMBERS[1], child):
        denied = world.session(member, PROJECT).call("read_test_result", report_id=report_id, cursor=cursor)
        assert denied["ok"] is False
        assert denied["error"]["rejection"]["code"] == "test_report_not_readable"
        assert "page" not in denied and "result" not in denied
        observation = SoftwareCollaborationPort(world.session(member, PROJECT), member).observe()
        assert "test_reports" not in observation and report["body"] not in json.dumps(observation)
    assert world.test_budget.snapshot()["used"] == 1
    unknown = session.call("read_test_result", report_id="not-a-readable-report", cursor=cursor)
    assert unknown["error"]["rejection"]["code"] == "test_report_not_readable"
    bad_cursor = session.call("read_test_result", report_id=report_id, cursor="not-a-page")
    assert bad_cursor["error"]["rejection"]["code"] == "test_report_cursor_invalid"


def test_fixed_submission_does_not_require_reading_every_saved_page(tmp_path):
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0]), tmp_path / "case")
    world = prepared.world
    session = world.session(MEMBERS[0], PROJECT)
    path = next(name for name in prepared.case["editable_paths"] if name != "test_member.py")
    assert session.call("write_file", path=path, text=material(CASE_IDS[0])["files"][path] + "\n# fixed CPU witness\n")["ok"]
    first = session.call("run_tests")
    assert first["ok"] and first["result"]["total_pages"] > 1
    fixed = session.call("fix_patch", task_ids=[], message="Explicit CPU fixed-tree witness")
    assert fixed["ok"], fixed
    submitted = session.call("submit_integration", message="CPU submission without page-completion ceremony")
    assert submitted["ok"], submitted
    assert len(world._software()["deliveries"]) == 1
    assert not any(event["kind"] == "test_report_page_read" for event in world.state["software_events"])
    assert world.test_budget.snapshot()["used"] == 1
