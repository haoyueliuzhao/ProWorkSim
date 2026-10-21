"""Versioned S1 repository tools; public tests only, no shell or model runner."""
from __future__ import annotations

import copy
from pathlib import Path, PurePosixPath
import re

from . import software_calibration_world_v051 as previous
from . import software_collaboration_v027 as original
from . import software_organization_v042 as paged
from .adapters.capabilities import encode
from .harness_policy_v040 import FORBIDDEN_TOOLS
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .software_benchmark_state_cache_v054 import CachedStateStore
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors
from .world_core import WorldCore

VERSION = "software-benchmark-world-v054-file-operations"
INTERFACE_REVISION = VERSION
PURPOSE = "software_benchmark_interface_preparation"
PROJECT, MEMBERS = previous.PROJECT, previous.MEMBERS
PAGE_FILES, PAGE_CHARACTERS, PAGE_MATCHES = 40, 4096, 20
_PATH = {"type": "string", "minLength": 1}
_CURSOR = {"type": "string", "minLength": 1}
TOOLS = copy.deepcopy(previous.TOOLS)
for _tool in TOOLS:
    if _tool["name"] in {"list_files", "read_file", "search_file", "diff_workspace"}:
        _tool["parameters"]["properties"]["cursor"] = copy.deepcopy(_CURSOR)
    if _tool["name"] == "list_files":
        _tool["description"] = "List at most40 actual current entries. Continue with next_cursor; editing invalidates cursors."
    elif _tool["name"] == "read_file":
        _tool["parameters"]["required"] = ["path"]
        _tool["description"] = "Read up to4096 characters and180 lines of an actual UTF-8 file. Continue exact text with next_cursor; no binary decoding."
    elif _tool["name"] == "search_file":
        _tool["description"] = "Search one UTF-8 file literally; at most20 matches with bounded previews. Continue with next_cursor."
    elif _tool["name"] == "diff_workspace":
        _tool["description"] = "Read one bounded page of the real cumulative change description; binary changes are identified without decoding."
    elif _tool["name"] == "write_file":
        _tool["description"] = "Replace an existing writable UTF-8 file completely within the frozen source policy; records a new version."
    elif _tool["name"] == "run_tests":
        _tool["description"] = "Run only the configured public tests on this exact version, spending one existing test opportunity. Read saved result pages without rerunning; hidden evaluation is not available."
TOOLS += [
    original._tool("create_file", "Create a new writable UTF-8 file; never overwrite a path. Parent directories are implicit.",
                   {"path": _PATH, "text": {"type": "string"}}),
    original._tool("delete_file", "Delete one existing writable file or link; preserve the immutable prior version.",
                   {"path": _PATH}),
    original._tool("rename_file", "Move one writable file or link to an absent writable path, including across directories; preserve bytes and metadata.",
                   {"path": _PATH, "new_path": _PATH}),
    original._tool("read_task", "Read the next exact page of the original public problem statement.",
                   {"cursor": _CURSOR}, []),
]


def _safe_path(path):
    parsed = PurePosixPath(path)
    if (not isinstance(path, str) or not path or parsed.is_absolute()
            or str(parsed) != path or any(p in {".", "..", ".git"} for p in parsed.parts)
            or "\\" in path or "\x00" in path):
        raise ValueError("Use a normalized repository-relative non-Git path")
    return path


def _readonly(path, policy):
    return path in policy["readonly_paths"] or any(
        path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")
        for prefix in policy["readonly_prefixes"])


def _reference(artifact, version):
    return original._reference(artifact, version)


def _cursor(identity, position):
    return str(position) + ":" + digest(json_bytes(identity))


def _position(cursor, identity, length):
    if cursor is None:
        return 0
    if (not isinstance(cursor, str) or re.fullmatch(r"[0-9]+:[0-9a-f]{64}", cursor) is None
            or cursor.split(":", 1)[1] != digest(json_bytes(identity))):
        raise ValueError("Cursor belongs to another operation or source version")
    position = int(cursor.split(":", 1)[0])
    if not 0 <= position <= length:
        raise ValueError("Cursor is outside the saved content")
    return position


def _text_page(text, identity, cursor=None, *, position=None, max_lines=None):
    start = _position(cursor, identity, len(text)) if position is None else position
    end = min(len(text), start + PAGE_CHARACTERS)
    if max_lines is not None:
        lines = text[start:end].splitlines(keepends=True)
        end = start + sum(len(line) for line in lines[:max_lines])
    return {"text": text[start:end], "start_character": start, "end_character": end,
            "total_characters": len(text), "text_sha256": digest(text.encode()),
            "next_cursor": _cursor(identity, end) if end < len(text) else None}


def _bounded_rows(rows, limit=PAGE_FILES):
    selected, characters = [], 0
    for row in rows:
        cost = len(json_bytes(row).decode())
        if selected and (len(selected) >= limit or characters + cost > PAGE_CHARACTERS):
            break
        selected.append(row)
        characters += cost
    return selected


def case_spec(case_id, *, provider, condition="S1", first_member="member_001",
              role_decision_limits=None):
    case = previous.case_spec(case_id, provider=provider, condition=condition,
                              first_member=first_member, role_decision_limits=role_decision_limits)
    material = provider.build_case(case_id)
    case.update(version=VERSION, interface_revision=INTERFACE_REVISION, purpose=PURPOSE,
                usage=PURPOSE, category=PURPOSE, split=PURPOSE,
                task_type="public_repository_managed_S1", file_policy=copy.deepcopy(material["file_policy"]),
                member_test_protocol={"version": "public-repository-tests-v054",
                                      "hidden_evaluation_accessible": False},
                public_feedback_protocol="public_tests_with_exact_v042_pages")
    return case


def validate_case(case, *, provider):
    if case != case_spec(case["case_id"], provider=provider, condition=case["condition"],
                         first_member=case["first_member"], role_decision_limits=case["role_decision_limits"]):
        raise ValueError("The declared v054 source, permissions or S1 budget changed")
    return case


def member_instruction(case, **_):
    return (
        "Resolve the original public repository issue. You are the only executor, member_001. "
        "Use read_task for its exact pages and list_files/read_file for the current repository. "
        "Cursors bind one source version; after editing obtain new cursors. "
        "Use write_file or unique replace_file for existing UTF-8 files, create_file for a new "
        "file, delete_file or rename_file for existing writable entries. Read-only source policy "
        "remains enforced; binary/link contents are not text-editable. No shell is available. "
        "run_tests executes only public tests. After your last edit, run_tests, fix_patch(task_ids=[]), "
        "then submit_integration to preserve an explicit tested version; passing tests is not required "
        "to submit and submission is not acceptance. staff_done ends current work without creating "
        "a submission, partner or extra budget. " + paged.PAGING_INSTRUCTION
    )


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def __init__(self, root):
        # Preserve the original constructor's schema and recovery checks;
        # subsequent v054 reads use an isolated committed-state cache only.
        super().__init__(root)
        original_store = self.store
        self.store = CachedStateStore(original_store.root)
        self.store.fault_hook = original_store.fault_hook

    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in FORBIDDEN_TOOLS:
            raise ToolRejection("Controller operations remain unavailable",
                                code="forbidden_controller_request", category="policy_error",
                                context={"process_violation": True})
        if project_id != PROJECT or actor not in self.live_members():
            raise ValueError("Only the one live registered member may act")
        specs = {tool["name"]: tool for tool in TOOLS}
        if tool not in specs:
            raise ToolRejection("Not in the v054 managed interface",
                                code="tool_not_enabled", category="capability_gap")
        errors = _schema_errors(specs[tool]["parameters"], arguments)
        if errors:
            raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
        return WorldCore._tool_project_action(self, actor, project_id, tool, arguments, interface_profile)

    def _editable(self):
        _, _, bundle = self._bundle(MEMBERS[0])
        policy = self._software()["case"]["file_policy"]
        return sorted(path for path in bundle["files"] if not _readonly(path, policy))

    def _writable(self, path):
        _safe_path(path)
        if _readonly(path, self._software()["case"]["file_policy"]):
            raise ValueError("The frozen public source policy makes this path read-only")

    @staticmethod
    def _text_entry(bundle, path):
        _safe_path(path)
        if path not in bundle["files"]:
            raise ValueError("Path is absent from this source version")
        meta = bundle["entry_metadata"][path]
        if meta["kind"] != "file" or meta["encoding"] != "utf-8":
            raise ValueError("This operation supports UTF-8 regular-file contents only")
        return bundle["files"][path]

    def _save_edit(self, actor, artifact, version, before, after, *, operation, paths):
        if before == after:
            raise ValueError("The operation would not change the current version")
        self.source_provider.validate_files(
            self._software()["case"]["case_id"], after["files"],
            entry_metadata=after["entry_metadata"])
        reference = self._save_content(actor, PROJECT, artifact, encode("json", after))
        self._event(actor, "edit", operation=operation, paths=paths,
                    previous_reference=_reference(artifact, version), source_reference=reference,
                    before_sha256=digest(json_bytes(before)), after_sha256=digest(json_bytes(after)))
        return {"source_reference": reference, "operation": operation, "paths": paths[:PAGE_FILES],
                "path_count": len(paths),
                "files_sha256": digest(json_bytes(after["files"])),
                "entry_metadata_sha256": digest(json_bytes(after["entry_metadata"]))}

    def _write_file(self, actor, path, text, artifact, version, bundle):
        self._writable(path)
        self._text_entry(bundle, path)
        if not isinstance(text, str):
            raise ValueError("UTF-8 text is required")
        after = copy.deepcopy(bundle)
        after["files"][path] = text
        return self._save_edit(actor, artifact, version, bundle, after, operation="write", paths=[path])

    def _action_replace_file(self, actor, project_id, path, old, new):
        artifact, version, bundle = self._bundle(actor, write=True)
        text = self._text_entry(bundle, path)
        if not old or text.count(old) != 1:
            raise ValueError("The old text must identify one exact nonempty occurrence")
        return self._write_file(actor, path, text.replace(old, new, 1), artifact, version, bundle)

    def _action_create_file(self, actor, project_id, path, text):
        self._writable(path)
        artifact, version, bundle = self._bundle(actor, write=True)
        if path in bundle["files"]:
            raise ValueError("Creation must not overwrite an existing path")
        after = copy.deepcopy(bundle)
        after["files"][path] = text
        after["entry_metadata"][path] = {"kind": "file", "encoding": "utf-8", "mode": "100644"}
        return self._save_edit(actor, artifact, version, bundle, after, operation="create", paths=[path])

    def _action_delete_file(self, actor, project_id, path):
        self._writable(path)
        artifact, version, bundle = self._bundle(actor, write=True)
        if path not in bundle["files"]:
            raise ValueError("Deletion requires an existing entry")
        after = copy.deepcopy(bundle)
        del after["files"][path]
        del after["entry_metadata"][path]
        return self._save_edit(actor, artifact, version, bundle, after, operation="delete", paths=[path])

    def _action_rename_file(self, actor, project_id, path, new_path):
        self._writable(path)
        self._writable(new_path)
        artifact, version, bundle = self._bundle(actor, write=True)
        if path not in bundle["files"] or new_path in bundle["files"]:
            raise ValueError("Rename requires an existing source and an absent destination")
        after = copy.deepcopy(bundle)
        after["files"][new_path] = after["files"].pop(path)
        after["entry_metadata"][new_path] = after["entry_metadata"].pop(path)
        return self._save_edit(actor, artifact, version, bundle, after,
                               operation="rename", paths=[path, new_path])

    def _action_list_files(self, actor, project_id, patch_id=None, cursor=None):
        artifact, version, bundle = self._bundle(actor, patch_id=patch_id)
        reference = _reference(artifact, version)
        identity = {"tool": "list_files", "source_reference": reference}
        paths = sorted(bundle["files"])
        start = _position(cursor, identity, len(paths))
        policy = self._software()["case"]["file_policy"]
        rows = _bounded_rows({"path": p, "editable": not _readonly(p, policy),
                              **bundle["entry_metadata"][p]} for p in paths[start:])
        stop = start + len(rows)
        return {"source_reference": reference, "files": rows, "total_files": len(paths),
                "next_cursor": _cursor(identity, stop) if stop < len(paths) else None}

    def _action_read_file(self, actor, project_id, path, start_line=1, max_lines=180,
                          patch_id=None, cursor=None):
        artifact, version, bundle = self._bundle(actor, patch_id=patch_id)
        text = self._text_entry(bundle, path)
        reference = _reference(artifact, version)
        identity = {"tool": "read_file", "path": path, "source_reference": reference}
        if not 1 <= max_lines <= 180 or start_line < 1:
            raise ValueError("Use positive line positions and at most180 lines")
        position = None if cursor is not None else sum(
            len(line) for line in text.splitlines(keepends=True)[:start_line - 1])
        page = _text_page(text, identity, cursor, position=position, max_lines=max_lines)
        self._event(actor, "read", source_reference=reference, path=path,
                    start_character=page["start_character"], end_character=page["end_character"])
        return {"source_reference": reference, "path": path, **page}

    def _action_search_file(self, actor, project_id, path, text, cursor=None):
        artifact, version, bundle = self._bundle(actor)
        content = self._text_entry(bundle, path)
        if not text or len(text) > 200:
            raise ValueError("Search uses a nonempty literal of at most200 characters")
        reference = _reference(artifact, version)
        identity = {"tool": "search_file", "path": path, "text": text, "source_reference": reference}
        matches = [(i, line) for i, line in enumerate(content.splitlines(), 1) if text in line]
        start = _position(cursor, identity, len(matches))
        stop = min(start + PAGE_MATCHES, len(matches))
        rows = []
        for line_number, line in matches[start:stop]:
            offset = max(0, line.find(text) - 80)
            rows.append({"line": line_number, "text": line[offset:offset + 320],
                         "start_character_in_line": offset, "full_line_characters": len(line)})
        self._event(actor, "search", path=path, source_reference=reference,
                    matched_lines=[r["line"] for r in rows])
        return {"source_reference": reference, "matches": rows, "total_matches": len(matches),
                "next_cursor": _cursor(identity, stop) if stop < len(matches) else None}

    def _action_read_task(self, actor, project_id, cursor=None):
        artifact, version, _ = self._bundle(actor)
        reference = _reference(artifact, version)
        return {**_text_page(self._software()["case"]["root_goal"],
                            {"tool": "read_task", "source_reference": reference}, cursor),
                "source_reference": reference}

    def _action_diff_workspace(self, actor, project_id, cursor=None):
        artifact, version, bundle = self._bundle(actor)
        _, _, baseline = self._bundle(actor, baseline=True)
        before, after = {}, {}
        for path in sorted(set(baseline["files"]) | set(bundle["files"])):
            for target, source in ((before, baseline), (after, bundle)):
                if path in source["files"]:
                    meta = source["entry_metadata"][path]
                    target[path] = (source["files"][path] if meta["encoding"] == "utf-8" else
                                    f"[{meta['kind']} {meta['encoding']} sha256={digest(source['files'][path].encode())}]\n")
        reference = _reference(artifact, version)
        return {**_text_page(original._diff(before, after),
                            {"tool": "diff_workspace", "source_reference": reference}, cursor),
                "source_reference": reference}

    def _action_fix_patch(self, actor, project_id, task_ids, message):
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Fixed task IDs must be distinct")
        artifact, version, bundle = self._bundle(actor)
        base_artifact, base_version, baseline = self._bundle(actor, baseline=True)
        snapshots = {task_id: copy.deepcopy(self._task(task_id, actor)) for task_id in task_ids}
        supplied = {(task["task_id"], task["revision"]) for task in snapshots.values()}
        supplied.update((task["task_id"], task["revision"])
                        for pid in bundle["included_patch_ids"]
                        for task in self._patch(pid)["task_snapshots"].values())
        for task in snapshots.values():
            if any((tid, revision) not in supplied for tid, revision in task["dependency_revisions"].items()):
                raise ValueError("A declared prerequisite revision has not been supplied")
        old, new = baseline["files"], bundle["files"]
        added, deleted = sorted(set(new) - set(old)), sorted(set(old) - set(new))
        modified = sorted(path for path in set(old) & set(new)
                          if old[path] != new[path] or baseline["entry_metadata"][path] != bundle["entry_metadata"][path])
        changed = sorted(added + deleted + modified)
        if not changed:
            raise ValueError("No changed entry to publish")
        patch = {"patch_id": "patch-" + str(len(self._software()["patches"]) + 1),
                 "author": actor, "task_ids": task_ids, "task_snapshots": snapshots, "message": message,
                 "source_reference": _reference(artifact, version),
                 "base_reference": _reference(base_artifact, base_version),
                 "source_sha256": digest(json_bytes(bundle)), "files_sha256": digest(json_bytes(new)),
                 "entry_metadata_sha256": digest(json_bytes(bundle["entry_metadata"])),
                 "changed_paths": changed, "added_paths": added, "deleted_paths": deleted,
                 "modified_paths": modified, "diff_sha256": digest(original._diff(old, new).encode()),
                 "included_patch_ids": list(bundle["included_patch_ids"])}
        self._software()["patches"][patch["patch_id"]] = copy.deepcopy(patch)
        self._share_fixed(actor, patch["source_reference"])
        self._event(actor, "patch_fixed", **patch)
        return _patch_summary(patch)

    def _action_integrate_patch(self, actor, project_id, patch_id):
        patch = self._patch(patch_id)
        artifact, version, bundle = self._bundle(actor, write=True)
        if patch_id in bundle["included_patch_ids"]:
            raise ValueError("That fixed patch is already included")
        _, _, baseline = self._bundle(actor, reference=patch["base_reference"])
        _, _, incoming = self._bundle(actor, reference=patch["source_reference"])
        after, conflicts = copy.deepcopy(bundle), []

        def entry(tree, path):
            return ((tree["files"][path], tree["entry_metadata"][path])
                    if path in tree["files"] else None)

        for path in sorted(set(baseline["files"]) | set(bundle["files"]) | set(incoming["files"])):
            base, local, remote = (entry(tree, path) for tree in (baseline, bundle, incoming))
            if local == base or local == remote:
                merged = remote
            elif remote == base:
                merged = local
            elif (all(value is not None for value in (base, local, remote))
                  and base[1] == local[1] == remote[1]
                  and base[1]["kind"] == "file" and base[1]["encoding"] == "utf-8"):
                text, conflict = original._merge_file(base[0], local[0], remote[0])
                merged = text, local[1]
                if conflict:
                    conflicts.append(path)
            else:
                raise ToolRejection("Conflicting structural or non-text changes require explicit file operations",
                                    code="structural_merge_conflict", category="business_constraint")
            if merged is None:
                after["files"].pop(path, None)
                after["entry_metadata"].pop(path, None)
            else:
                after["files"][path], after["entry_metadata"][path] = copy.deepcopy(merged)
        after["included_patch_ids"].append(patch_id)
        result = self._save_edit(actor, artifact, version, bundle, after,
                                 operation="integrate", paths=patch["changed_paths"])
        return {**result, "patch_id": patch_id, "conflicts": conflicts[:PAGE_FILES],
                "conflict_count": len(conflicts)}

    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        self.test_budget.consume(actor)
        public = self.source_provider.run_public_tests(
            self._software()["case"]["case_id"], bundle["files"],
            entry_metadata=bundle["entry_metadata"], run_root=self.store.root / "software-execution/public")
        reference = _reference(artifact, version)
        result = {"groups": copy.deepcopy(public["groups"]), "public_execution": public,
                  "public_diagnostics": {}, "repository_collection_errors": public.get("repository_collection_errors", []),
                  "passed": public["passed"], "executed": public["execution"]["executed"],
                  "source_reference": reference, "source_sha256": digest(json_bytes(bundle)),
                  "files_sha256": digest(json_bytes(bundle["files"])),
                  "entry_metadata_sha256": digest(json_bytes(bundle["entry_metadata"])),
                  "suite": "public-repository-tests-v054",
                  "untested": [] if public["execution"]["executed"] else ["public_repository_tests"],
                  "scope": "Only the configured public test callback; no hidden evaluator",
                  "independent_acceptance": "not_run_by_public_tool",
                  "fixed_submission_is_acceptance": False, "team_test_budget": self.test_budget.snapshot()}
        event = self._event(actor, "test", **result)
        identity = {key: self.state[key] for key in ("world_id", "instance_id", "branch_id")}
        identity.update(project_id=project_id, actor_id=actor, test_event_sequence=event["sequence"],
                        operation_id=event["operation_id"])
        report = paged.build_test_report(result, actor_id=actor, event_identity=identity)
        self._software()["test_reports"][report["report_id"]] = report
        self._event(actor, "test_report_saved", report_id=report["report_id"],
                    test_event_sequence=event["sequence"], body_sha256=report["body_sha256"],
                    source_reference=reference, files_sha256=result["files_sha256"])
        return _bounded_test_page(paged.test_result_page(report))

    def _action_read_test_result(self, actor, project_id, report_id, cursor):
        return _bounded_test_page(super()._action_read_test_result(actor, project_id, report_id, cursor))

    def _action_submit_integration(self, actor, project_id, message=""):
        result = super()._action_submit_integration(actor, project_id, message)
        _, _, bundle = self._bundle(actor)
        metadata_sha = digest(json_bytes(bundle["entry_metadata"]))
        self._software()["deliveries"][-1]["entry_metadata_sha256"] = metadata_sha
        self.state["software_events"][-1]["entry_metadata_sha256"] = metadata_sha
        return {**result, "entry_metadata_sha256": metadata_sha}


def _bounded_test_page(page):
    """Keep the exact report body/page while bounding its navigation index."""
    if "directory" not in page:
        return page
    original_directory = page["directory"]
    directory, used = [], 0
    for group in original_directory[:PAGE_MATCHES]:
        row = {key: copy.deepcopy(value) for key, value in group.items() if key != "entries"}
        row["entry_count"] = len(group.get("entries", []))
        row["entries"] = []
        for entry in group.get("entries", [])[:PAGE_MATCHES]:
            cost = len(json_bytes(entry))
            if used + cost > PAGE_CHARACTERS:
                break
            row["entries"].append(copy.deepcopy(entry))
            used += cost
        directory.append(row)
    return {**page, "directory": directory, "directory_group_count": len(original_directory),
            "directory_scope": "Bounded navigation only; exact full permitted results remain in saved body pages"}


def _patch_summary(patch):
    keys = ("patch_id", "author", "source_reference", "base_reference", "source_sha256",
            "files_sha256", "entry_metadata_sha256", "diff_sha256")
    return {**{key: copy.deepcopy(patch[key]) for key in keys},
            "changed_paths": _bounded_rows(patch["changed_paths"]),
            "changed_path_count": len(patch["changed_paths"]),
            "changed_paths_truncated": len(_bounded_rows(patch["changed_paths"])) < len(patch["changed_paths"])}


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def observe(self):
        world = self._session._world
        with world.store.lock():
            world.state = world.store.load()
            artifact, version, bundle = world._bundle(self.role)
            reference = _reference(artifact, version)
            facts, case = world._software(), world._software()["case"]
            directory = world._action_list_files(self.role, PROJECT)
            tests = [event for event in world.state["software_events"]
                     if event["kind"] == "test" and event["actor_id"] == self.role
                     and event["source_reference"] == reference]
            events = world.state["software_events"]
            messages = [event for event in events
                        if event["kind"] in {"work_message", "delegate", "task_returned"}
                        and event.get("recipient") == self.role]
            handoffs = [event for event in events if event["kind"] == "handoff"
                        and event.get("recipient") == self.role]

            def event_summary(event):
                keys = ("sequence", "kind", "actor_id", "recipient", "task_id", "patch_id",
                        "source_reference", "fixed_reference")
                return {**{key: copy.deepcopy(event[key]) for key in keys if key in event},
                        **{key: event[key][:500] for key in ("body", "message", "reason")
                           if isinstance(event.get(key), str)}}

            tasks = [{key: copy.deepcopy(task[key]) for key in
                      ("task_id", "revision", "owner", "depends_on") if key in task}
                     for task in facts["tasks"].values()]
            observation = {
                **{key: world.state[key] for key in ("world_id", "instance_id", "branch_id")},
                "role": self.role, "actor_id": self.role, "project_id": PROJECT,
                "profile": VERSION, "interface_revision": INTERFACE_REVISION,
                "logical_time": world.state["clock"], "world_status": world.state["world_status"],
                "projects": {PROJECT: {"project_id": PROJECT}}, "workspace_reference": reference,
                "contract": case["root_goal"][:PAGE_CHARACTERS],
                "root_goal": {"description": case["root_goal"][:PAGE_CHARACTERS],
                              "sha256": digest(case["root_goal"].encode()),
                              "total_characters": len(case["root_goal"]), "read_tool": "read_task"},
                "file_directory": directory, "file_count": len(bundle["files"]),
                "editable_paths": [row["path"] for row in directory["files"] if row["editable"]],
                "editable_paths_scope": "Only the first directory page; use list_files cursor for all entries",
                "source_contract_sha256": digest(json_bytes(case["source_contract"])),
                "initial_binding_sha256": digest(json_bytes(case["initial_binding"])),
                "file_policy_sha256": digest(json_bytes(case["file_policy"])),
                "source_readonly_policy": "Frozen provider checks every mutation, including destinations",
                "patches": [_patch_summary(p) for p in list(facts["patches"].values())[-6:]],
                "patch_count": len(facts["patches"]),
                "all_fixed_patches": [{"patch_id": event["patch_id"], "sequence": event["sequence"]}
                                      for event in events if event["kind"] == "patch_fixed"],
                "deliveries": [{k: copy.deepcopy(d[k]) for k in
                                ("delivery_id", "source_reference", "files_sha256", "test_sequence")}
                               for d in facts["deliveries"][-2:]],
                "delivery_count": len(facts["deliveries"]), "task_count": len(facts["tasks"]),
                "tasks": _bounded_rows(tasks), "included_patch_ids": bundle["included_patch_ids"],
                "messages": [event_summary(event) for event in messages[-4:]],
                "handoffs": [event_summary(event) for event in handoffs[-4:]],
                "older_message_sequences": [event["sequence"] for event in messages[:-4]],
                "older_handoff_sequences": [event["sequence"] for event in handoffs[:-4]],
                "member_registry": {member: {key: copy.deepcopy(value) for key, value in record.items()
                                             if key != "briefing"}
                                    for member, record in facts["registry"].items()},
                "action_error_policy": copy.deepcopy(case["action_error_policy"]),
                "scheduling": {"protocol": case["scheduling_protocol"],
                               "first_member": MEMBERS[0],
                               "done": "End current work; no replacement or synthetic event",
                               "wait": "Suspend; no hidden worker creates new work"},
                "current_version_test_coverage": (
                    {name: {key: group.get(key) for key in ("status", "executed", "passed")}
                     for name, group in tests[-1]["groups"].items()} if tests else
                    {"public_repository_tests": {"status": "untested", "executed": False, "passed": None}}),
                "shared_resource_limits": copy.deepcopy(case["team_limits"]),
                "team_test_budget": {k: world.test_budget.snapshot()[k] for k in ("limit", "used", "remaining")},
                "member_availability": world.member_availability(),
                "execution_condition": {"condition": "S1", "initial_members": list(MEMBERS),
                                        "active_executors": world.live_members(), "hidden_partners": False},
                "initial_public_feedback": None, "purpose": PURPOSE,
                "tool_navigation": {"files": "list_files", "source": "read_file", "issue": "read_task",
                                    "changes": "diff_workspace", "test_pages": "read_test_result"},
            }
            callback = getattr(world, "model_budget_snapshot", None)
            if callback is not None:
                budget = callback()
                observation["team_model_budget"] = {k: budget[k] for k in (
                    "limits", "decisions", "attempts", "charged_tokens", "held_tokens",
                    "remaining_decisions", "remaining_attempts", "available_tokens", "state_sha256")}
            return observation


def build_software_collaboration_case(case, root, *, provider):
    case = case_spec(case, provider=provider) if isinstance(case, str) else validate_case(case, provider=provider)
    if provider.runner is None:
        raise ValueError("A public-only execution callback must be bound explicitly")
    material = provider.build_case(case["case_id"])
    bundle = {"files": material["files"], "entry_metadata": material["entry_metadata"],
              "included_patch_ids": []}
    provider.validate_files(case["case_id"], bundle["files"], entry_metadata=bundle["entry_metadata"])
    objects = [
        {"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
         "readers": [*MEMBERS, "operator"], "writers": ["operator"], "data": bundle},
        {"alias": MEMBERS[0], "filename": MEMBERS[0] + ".json", "kind": "json", "owner": MEMBERS[0],
         "readers": [MEMBERS[0], "operator"], "writers": [MEMBERS[0]], "data": copy.deepcopy(bundle)},
    ]
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*MEMBERS, "operator"],
               "objects": objects, "works": [], "grants": [],
               "provenance": {"kind": "reconstructed", "note": "Declared public baseline only; no answer or hidden grading material"}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-S1-v054",
            "world": {"world_id": "software-benchmark-v054", "actors": {a: {} for a in (*MEMBERS, "operator")},
                      "applications": ["files"], "publication_policy": "explicit",
                      "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
            "installer": "operator", "projects": [{"package": package}],
            "roles": [{"role_id": MEMBERS[0], "actor": MEMBERS[0], "project": PROJECT, "policy": "model",
                       "config": {"task": member_instruction(case)}}],
            "setup": [], "events": [], "start": {"kind": "initial"}, "boundary": {"max_opportunities": 129}}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    world.source_provider, world.test_budget = provider, previous.TestBudget(root / "team-test-budget.json")
    with world.store.lock():
        world.state = world.store.load()
        artifact, version, _ = world._bundle(MEMBERS[0], baseline=True)
        reference = _reference(artifact, version)
        world.state["shares"].append({"project_id": PROJECT, **reference, "actor_ids": list(MEMBERS),
                                     "shared_by": "operator", "at": world.state["clock"]})
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {
            "case": case, "tasks": {}, "patches": {}, "deliveries": [], "test_reports": {},
            "initial_public_feedback": None, "transfer_offers": {}, "initial_diagnostics": {},
            "initial_diagnostic_assignments": {MEMBERS[0]: []},
            "registry": {MEMBERS[0]: {"member_id": MEMBERS[0], "birth_index": 1, "status": "live",
                                    "born_by": None, "origin": "initial_configuration", "briefing": "",
                                    "model_generated_briefing": False,
                                    "initial_source_reference": reference, "initial_patch_id": None,
                                    "replaces": None, "birth_sequence": 0, "private_history_copied": False}},
        }
        world.store.save(world.state)
    prefix = {"version": VERSION, "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
              "source_contract_sha256": digest(json_bytes(case["source_contract"])),
              "initial_binding_sha256": digest(json_bytes(case["initial_binding"])),
              "model_calls": 0, "test_executions": 0, "hidden_evaluation_calls": 0}
    prepared = PreparedOnlineCase(deployment, case, {
        "version": VERSION, "training_supported": False, "purpose": PURPOSE,
        "source_partition_sha256": provider.manifest_sha256,
        "runtime_process_contract": case["process_contract"]}, prefix)
    prepared.port_factory, prepared.source_provider = SoftwareCollaborationPort, provider
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared
