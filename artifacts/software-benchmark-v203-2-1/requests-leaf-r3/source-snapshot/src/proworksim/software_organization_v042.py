"""v042: original v040 business semantics with private exact test-report pages.

The report body is exactly the original v040 visible result, never raw host logs
or private acceptance. Tests still execute once; later page reads only access an
immutable actor-owned report. No page coverage is required for business delivery.
"""
from __future__ import annotations

from bisect import bisect_right
import copy
import json
from pathlib import Path

from . import software_organization_v040 as previous
from .scenarios import initial_business_state
from .storage import atomic_write, digest, json_bytes
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors
from .world_core import WorldCore

VERSION = "software-organization-v0.42"
PAGING_VERSION = "paged-public-test-feedback-v0.42"
INTERFACE_REVISION = "member-private-exact-test-pages-v0.42"
PAGE_BODY_CHARACTERS = 3072
SERIALIZATION = "json_unicode_indent2_trailing_lf_v042"
CASE_IDS, CONDITIONS, MEMBERS, PROJECT = previous.CASE_IDS, previous.CONDITIONS, previous.MEMBERS, previous.PROJECT
TEAM_LIMITS, SCHEDULER = previous.TEAM_LIMITS, previous.SCHEDULER
case_spec, validate_case, material = previous.case_spec, previous.validate_case, previous.material
assess_software_collaboration = previous.assess_software_collaboration
PAGING_INSTRUCTION = (
    " Test results are private, versioned reports. run_tests executes once and returns a fixed-order directory and "
    "the first exact body page. Use read_test_result(report_id, cursor) to read more saved pages without rerunning tests. "
    "Only the original testing member can read the report; sharing an ID gives no permission. Share actual text if useful. "
    "Old cursors remain tied to the old event and version after edits. Page reads spend the same team decision/token pool "
    "but no test call. Reading all pages is optional and is not a submission requirement.")
READ_TEST_RESULT_TOOL = {"name": "read_test_result",
    "description": "Read one exact saved page of your own test report. Use its returned cursor. No test executes, no budget resets, and edits do not change old pages. Report IDs do not grant access to other members.",
    "parameters": {"type": "object", "properties": {
        "report_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "cursor": {"type": "string", "minLength": 1, "maxLength": 128}},
        "required": ["report_id", "cursor"], "additionalProperties": False}}
TOOLS = copy.deepcopy(previous.TOOLS)
for _tool in TOOLS:
    if _tool["name"] == "run_tests":
        _tool["description"] = (
            "Execute the same public upstream/business checks and optional member script once on this exact tree. "
            "Save the complete permitted result as your private immutable report; return status, a fixed-order directory "
            "and its first exact page (at most 3072 Unicode body characters). Use read_test_result for further pages. "
            "At most 32 actual test runs across the team. Public passing is not independent acceptance; reading all pages is optional.")
TOOLS.append(copy.deepcopy(READ_TEST_RESULT_TOOL))


def project_role_task(task):
    if not isinstance(task, str):
        raise TypeError("The original member instruction must be text")
    return task if task.endswith(PAGING_INSTRUCTION) else task + PAGING_INSTRUCTION


def project_observation(observation):
    """The report itself is never reassembled into a later observation."""
    value = copy.deepcopy(observation)
    value["interface_revision"] = INTERFACE_REVISION
    value["profile"] = VERSION + ":" + value["actor_id"]
    return value


def member_instruction(case, *, briefing="", born=False, origin=None):
    return project_role_task(previous.member_instruction(case, briefing=briefing, born=born, origin=origin))


def _pointer(path):
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in path)


def _body_and_entries(value):
    """Produce the fixed JSON text and exact original group/test item spans."""
    parts, entries, length = [], [], 0

    def append(text):
        nonlocal length
        parts.append(text)
        length += len(text)

    def emit(item, level, path):
        start = length
        is_entry = (len(path) == 2 and path[0] in {"public_diagnostics", "groups"}
                    or len(path) >= 2 and path[-2] == "tests" and isinstance(path[-1], int))
        if isinstance(item, dict) and item:
            append("{\n")
            for index, (key, child) in enumerate(item.items()):
                append("  " * (level + 1) + json.dumps(key, ensure_ascii=False, allow_nan=False) + ": ")
                emit(child, level + 1, (*path, key))
                append(("," if index + 1 < len(item) else "") + "\n")
            append("  " * level + "}")
        elif isinstance(item, list) and item:
            append("[\n")
            for index, child in enumerate(item):
                append("  " * (level + 1))
                emit(child, level + 1, (*path, index))
                append(("," if index + 1 < len(item) else "") + "\n")
            append("  " * level + "]")
        else:
            append(json.dumps(item, ensure_ascii=False, allow_nan=False))
        if is_entry:
            entries.append({"path": _pointer(path), "start": start, "end": length})

    emit(value, 0, ())
    append("\n")
    body = "".join(parts)
    if body != json_bytes(value).decode():
        raise ValueError("Page serialization must equal the fixed original visible JSON exactly")
    return body, sorted(entries, key=lambda row: (row["start"], row["end"]))


def _status(row):
    if "status" in row:
        return copy.deepcopy(row["status"])
    if row.get("executed") is False:
        return "untested"
    return "passed" if row.get("passed") is True else "failed" if row.get("passed") is False else None


def report_directory(visible_result):
    """Mechanical existing group/item order and IDs/status only; no advice."""
    directory = []
    for section, groups in visible_result.items():
        if section not in {"public_diagnostics", "groups"} or not isinstance(groups, dict):
            continue
        for name, group in groups.items():
            if not isinstance(group, dict):
                continue
            row = {"path": _pointer((section, name)), "group_id": name, "status": _status(group), "entries": []}
            if "diagnostic_id" in group:
                row["diagnostic_id"] = group["diagnostic_id"]
            for index, item in enumerate(group.get("tests", [])):
                if not isinstance(item, dict):
                    continue
                entry = {"path": _pointer((section, name, "tests", index)), "status": _status(item)}
                for key in ("test_id", "id"):
                    if key in item:
                        entry[key] = copy.deepcopy(item[key])
                row["entries"].append(entry)
            directory.append(row)
    return directory


def build_test_report(visible_result, *, actor_id, event_identity, report_id=None):
    """Pure pagination of Pi040(result), also used by offline copied prefixes."""
    required = {"world_id", "instance_id", "branch_id", "project_id", "actor_id", "test_event_sequence", "operation_id"}
    if (not isinstance(visible_result, dict) or not isinstance(actor_id, str) or not actor_id
            or not isinstance(event_identity, dict) or set(event_identity) != required
            or event_identity["actor_id"] != actor_id
            or type(event_identity["test_event_sequence"]) is not int or event_identity["test_event_sequence"] < 1
            or any(not isinstance(event_identity[key], str) or not event_identity[key] for key in required - {"test_event_sequence"})):
        raise ValueError("A report requires the original visible result, actor and complete immutable test-event identity")
    body, entries = _body_and_entries(visible_result)
    body_sha = digest(body.encode())
    if report_id is None:
        report_id = "test-report-" + digest(json_bytes([actor_id, event_identity, body_sha]))[:24]
    if not isinstance(report_id, str) or not report_id or len(report_id) > 128:
        raise ValueError("The report ID must be a bounded stable string")
    preferred = sorted({0, len(body), *(row[key] for row in entries for key in ("start", "end"))})
    pages, start = [], 0
    while start < len(body):
        limit = min(start + PAGE_BODY_CHARACTERS, len(body))
        boundary = preferred[bisect_right(preferred, limit) - 1]
        end = len(body) if limit == len(body) else boundary if boundary > start else limit
        text = body[start:end]
        index = len(pages)
        cursor = str(index) + ":" + digest(json_bytes([report_id, body_sha, index, start, end]))[:16]
        split = [{"path": entry["path"], "entry_start": entry["start"], "entry_end": entry["end"],
            "continued_from_previous": entry["start"] < start < entry["end"],
            "continues_on_next": entry["start"] < end < entry["end"]}
            for entry in entries if entry["start"] < start < entry["end"] or entry["start"] < end < entry["end"]]
        pages.append({"index": index, "cursor": cursor, "start": start, "end": end, "text": text,
                      "sha256": digest(text.encode()), "split_entries": split})
        start = end
    for index, page in enumerate(pages):
        page.update(next_cursor=pages[index + 1]["cursor"] if index + 1 < len(pages) else None,
                    is_last=index == len(pages) - 1, remaining_pages=len(pages) - index - 1)
    return {"version": PAGING_VERSION, "report_id": report_id, "actor_id": actor_id,
        "event_identity": copy.deepcopy(event_identity), "visible_result": copy.deepcopy(visible_result),
        "serialization": SERIALIZATION, "body": body, "body_sha256": body_sha, "pages": pages,
        "directory": report_directory(visible_result), "entry_spans": entries,
        "page_body_unicode_characters": PAGE_BODY_CHARACTERS,
        "scope": "Exact original Pi040 visible result. No host-only detail, private acceptance or generated summary."}


def test_result_page(report, cursor=None):
    page = report["pages"][0] if cursor is None else next((row for row in report["pages"] if row["cursor"] == cursor), None)
    if page is None:
        raise ToolRejection("The cursor does not identify a page of this saved report",
                            code="test_report_cursor_invalid", category="business_constraint")
    visible = report["visible_result"]
    value = {"version": PAGING_VERSION, "report_id": report["report_id"],
        "report_event": {"sequence": report["event_identity"]["test_event_sequence"],
                         "operation_id": report["event_identity"]["operation_id"]},
        "source_reference": copy.deepcopy(visible["source_reference"]), "files_sha256": visible["files_sha256"],
        "executed": visible["executed"], "passed": visible["passed"], "serialization": SERIALIZATION,
        "body_sha256": report["body_sha256"], "body_characters": len(report["body"]), "total_pages": len(report["pages"]),
        "page": copy.deepcopy(page)}
    if page["index"] == 0:
        value.update(directory=copy.deepcopy(report["directory"]), scope=visible["scope"],
            untested=copy.deepcopy(visible["untested"]), independent_acceptance=visible["independent_acceptance"],
            fixed_submission_is_acceptance=visible["fixed_submission_is_acceptance"])
    return value


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool != "read_test_result":
            return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)
        if project_id != PROJECT or actor not in self.live_members():
            raise ValueError("Only currently live registered members may act")
        errors = _schema_errors(READ_TEST_RESULT_TOOL["parameters"], arguments)
        if errors:
            raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
        return WorldCore._tool_project_action(self, actor, project_id, tool, arguments, interface_profile)

    def _action_run_tests(self, actor, project_id):
        visible = super()._action_run_tests(actor, project_id)
        event = self.state["software_events"][-1]
        if event["kind"] != "test" or event["actor_id"] != actor:
            raise RuntimeError("The paged result must bind the one original test event")
        identity = {key: self.state[key] for key in ("world_id", "instance_id", "branch_id")}
        identity.update(project_id=project_id, actor_id=actor, test_event_sequence=event["sequence"], operation_id=event["operation_id"])
        report = build_test_report(visible, actor_id=actor, event_identity=identity)
        reports = self._software()["test_reports"]
        if report["report_id"] in reports:
            raise RuntimeError("An independent test event cannot replace a saved report")
        reports[report["report_id"]] = report
        self._event(actor, "test_report_saved", report_id=report["report_id"], test_event_sequence=event["sequence"],
            body_sha256=report["body_sha256"], body_characters=len(report["body"]), total_pages=len(report["pages"]),
            source_reference=visible["source_reference"], files_sha256=visible["files_sha256"],
            serialization=SERIALIZATION, page_body_unicode_characters=PAGE_BODY_CHARACTERS)
        return test_result_page(report)

    def _action_read_test_result(self, actor, project_id, report_id, cursor):
        report = self._software()["test_reports"].get(report_id)
        if report is None or report["actor_id"] != actor:
            raise ToolRejection("No report with that ID is readable by this member",
                                code="test_report_not_readable", category="capability_gap")
        value = test_result_page(report, cursor)
        page = value["page"]
        self._event(actor, "test_report_page_read", report_id=report_id, page_index=page["index"],
            start=page["start"], end=page["end"], page_sha256=page["sha256"], test_rerun=False)
        return value


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        return project_observation(super().observe())


def build_software_collaboration_case(case, root):
    """Reuse the unchanged initial business state, then bind the new interface."""
    prepared = previous.build_software_collaboration_case(case, root)
    original = prepared.world
    world = SoftwareCollaborationWorld(original.store.root)
    world.test_budget = original.test_budget
    prepared.deployment.world = world
    prepared.port_factory = SoftwareCollaborationPort
    with world.store.lock():
        world.state = world.store.load()
        world._software()["test_reports"] = {}
        world.store.save(world.state)
    for role in prepared.deployment.spec["roles"]:
        role["config"]["task"] = member_instruction(prepared.case)
    prepared.prefix.update(version=VERSION, business_world_version=previous.VERSION, test_feedback_protocol=PAGING_VERSION,
        page_body_unicode_characters=PAGE_BODY_CHARACTERS,
        prepared_business_state_sha256=digest(json_bytes(initial_business_state(world))))
    atomic_write(Path(root) / "preparation.json", json_bytes(prepared.prefix))
    return prepared
