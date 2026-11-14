"""Versioned managed repository search and explicit delivery guidance.

Only permitted in-memory source versions are searched; no shell, host walk,
hidden evaluator, automatic test, fix, or submit is introduced.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_benchmark_world_v054 as legacy
from . import software_collaboration_v027 as original
from .harness_policy_v040 import FORBIDDEN_TOOLS
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors
from .world_core import WorldCore

VERSION = "software-benchmark-world-v056-managed-search-delivery"
INTERFACE_REVISION = VERSION
PURPOSE = "software_benchmark_interface_preparation_v056"
PROJECT, MEMBERS = legacy.PROJECT, legacy.MEMBERS
SCAN_CHARACTERS, SCAN_FILES = 1_048_576, 256
RESULTS_PER_PAGE, RESULT_CHARACTERS = 20, 8192
PEER_TOOLS = frozenset({"send_message", "handoff_patch", "offer_transfer", "accept_transfer", "decline_transfer"})
_reference = original._reference
TOOLS = copy.deepcopy(legacy.TOOLS) + [
    original._tool("search_repository",
        "Search non-overlapping literal occurrences across the permitted current UTF-8 repository. "
        "An optional path_prefix selects one file/directory. A page may contain no matches and still "
        "have next_cursor: continue until complete. Editing or changing the query invalidates cursors. "
        "No shell, symlink following, binary decoding or hidden evaluator access.",
        {"text": {"type": "string", "minLength": 1, "maxLength": 200},
         "path_prefix": {"type": "string", "minLength": 1},
         "cursor": copy.deepcopy(legacy._CURSOR)}, ["text"]),
    original._tool("delivery_status",
        "Read current-version public-test, fixed-patch and legal-submission evidence plus the next "
        "explicit action. This does not run tests, publish, submit, or certify hidden acceptance.", {}, []),
]


def tool_definitions(case):
    limits = case.get("member_limits", {})
    fixed_single = limits.get("max_live_members") == 1 and limits.get("births_enabled") is False
    return [copy.deepcopy(tool) for tool in TOOLS
            if not (fixed_single and tool["name"] in PEER_TOOLS)]


def case_spec(case_id, *, provider, condition="S1", first_member="member_001",
              role_decision_limits=None):
    case = legacy.case_spec(case_id, provider=provider, condition=condition,
                            first_member=first_member, role_decision_limits=role_decision_limits)
    case.update(version=VERSION, interface_revision=VERSION, purpose=PURPOSE,
                usage=PURPOSE, category=PURPOSE, split=PURPOSE,
                managed_interface_features={"repository_literal_search": True,
                    "explicit_delivery_status": True, "hide_inapplicable_peer_tools_in_fixed_S1": True,
                    "automatic_test_fix_or_submission": False})
    return case


def validate_case(case, *, provider):
    expected = case_spec(case["case_id"], provider=provider, condition=case["condition"],
                         first_member=case["first_member"], role_decision_limits=case["role_decision_limits"])
    if case != expected:
        raise ValueError("The declared v056 source, permissions or S1 budget changed")
    return case


def member_instruction(case, **kwargs):
    return (legacy.member_instruction(case, **kwargs) +
            " search_repository locates a literal across the permitted code tree without enumerating "
            "every file first. Follow next_cursor even when a scan page has zero matches. "
            "delivery_status and the observation delivery_status show evidence for the exact displayed "
            "workspace version and the next explicit closing action. These are guidance, not automatic "
            "tests or acceptance. Task creation remains optional. In fixed S1, peer communication and "
            "ownership-transfer tools with no possible recipient are not exposed.")


class SoftwareCollaborationWorld(legacy.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return tool_definitions(self._software()["case"]) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in FORBIDDEN_TOOLS:
            raise ToolRejection("Controller operations remain unavailable",
                                code="forbidden_controller_request", category="policy_error",
                                context={"process_violation": True})
        if project_id != PROJECT or actor not in self.live_members():
            raise ValueError("Only live registered members may act")
        specs = {item["name"]: item for item in self._tool_definitions(project_id)}
        if tool not in specs:
            raise ToolRejection("Not in the v056 managed interface",
                                code="tool_not_enabled", category="capability_gap")
        errors = _schema_errors(specs[tool]["parameters"], arguments)
        if errors:
            raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
        return WorldCore._tool_project_action(self, actor, project_id, tool, arguments, interface_profile)

    def _action_search_repository(self, actor, project_id, text, path_prefix=None, cursor=None):
        if not text or len(text) > 200 or "\n" in text or "\r" in text:
            raise ValueError("Use one nonempty literal line of at most200 characters")
        prefix = None
        if path_prefix is not None:
            prefix = legacy._safe_path(path_prefix.rstrip("/"))
        artifact, version, bundle = self._bundle(actor)
        reference = _reference(artifact, version)
        identity = {"actor": actor, "tool": "search_repository", "source_reference": reference,
                    "text": text, "path_prefix": prefix}
        paths = sorted(path for path in bundle["files"]
                       if prefix is None or path == prefix or path.startswith(prefix + "/"))
        checkpoints = self._software().setdefault("repository_search_cursors", {})
        position = {"file_index": 0, "character": 0, "line": 1}
        if cursor not in (None, ""):
            checkpoint = checkpoints.get(cursor)
            if checkpoint is None or checkpoint["identity"] != identity:
                raise ValueError("Search cursor belongs to another member, query or source version")
            position = copy.deepcopy(checkpoint["position"])
        index, offset, line = position["file_index"], position["character"], position["line"]
        rows, used, scanned, visited, skipped = [], 0, 0, 0, 0
        stop = False
        while index < len(paths) and not stop and visited < SCAN_FILES and scanned < SCAN_CHARACTERS:
            path = paths[index]
            visited += 1
            meta = bundle["entry_metadata"][path]
            if meta["kind"] != "file" or meta["encoding"] != "utf-8":
                skipped += 1
                index, offset, line = index + 1, 0, 1
                continue
            content = bundle["files"][path]
            end = min(len(content), offset + SCAN_CHARACTERS - scanned)
            while offset < end:
                found = content.find(text, offset, end)
                if found < 0:
                    # Retain enough overlap for a literal spanning the next scan page.
                    resume = end if end == len(content) else max(offset, end - len(text) + 1)
                    line += content.count("\n", offset, resume)
                    scanned += end - offset
                    offset = resume
                    break
                match_line = line + content.count("\n", offset, found)
                preview_start = max(0, found - 80)
                row = {"path": path, "line": match_line, "character_offset": found,
                       "preview": content[preview_start:found + len(text) + 160],
                       "preview_start_character": preview_start}
                cost = len(json_bytes(row).decode())
                if cost > RESULT_CHARACTERS:
                    raise ValueError("Matching path metadata exceeds the bounded result page")
                if rows and (len(rows) == RESULTS_PER_PAGE or used + cost > RESULT_CHARACTERS):
                    scanned += found - offset
                    offset, line, stop = found, match_line, True
                    break
                rows.append(row)
                used += cost
                scanned += found + len(text) - offset
                offset, line = found + len(text), match_line
                if len(rows) == RESULTS_PER_PAGE:
                    stop = True
                    break
            if offset >= len(content):
                index, offset, line = index + 1, 0, 1
            elif not stop:
                # Either the character scan budget was exhausted or an overlap remains.
                stop = True
        next_cursor = None
        if index < len(paths):
            checkpoint = {"identity": identity,
                          "position": {"file_index": index, "character": offset, "line": line}}
            next_cursor = "search-" + digest(json_bytes(checkpoint))
            checkpoints[next_cursor] = checkpoint
        self._event(actor, "repository_search", source_reference=reference, text=text, path_prefix=prefix,
                    matches=[{k: row[k] for k in ("path", "line", "character_offset")} for row in rows],
                    scanned_characters=scanned, considered_files=visited, complete=next_cursor is None)
        return {"source_reference": reference, "matches": rows, "complete": next_cursor is None,
                "next_cursor": next_cursor, "scanned_characters": scanned,
                "considered_files": visited, "skipped_nontext_entries": skipped,
                "matching_file_scope": "Permitted current source only; page counts are not repository totals",
                "scan_character_limit": SCAN_CHARACTERS, "scan_file_limit": SCAN_FILES,
                "result_character_limit": RESULT_CHARACTERS}

    def _delivery_status_for_reference(self, actor, reference):
        facts = self._software()
        tests = [event for event in self.state["software_events"]
                 if event["kind"] == "test" and event["actor_id"] == actor
                 and event["source_reference"] == reference and event["executed"]]
        patches = [patch for patch in facts["patches"].values() if patch["source_reference"] == reference]
        deliveries = [delivery for delivery in facts["deliveries"]
                      if delivery["actor_id"] == actor and delivery["source_reference"] == reference]
        if deliveries:
            next_tool = "staff_done"
        elif not tests:
            next_tool = "run_tests"
        elif not patches:
            next_tool = "fix_patch"
        else:
            next_tool = "submit_integration"
        return {"source_reference": copy.deepcopy(reference), "public_test_executed": bool(tests),
                "public_test_passed": tests[-1]["passed"] if tests else None,
                "public_test_sequence": tests[-1]["sequence"] if tests else None,
                "fixed_patch_id": patches[-1]["patch_id"] if patches else None,
                "legal_delivery_id": deliveries[-1]["delivery_id"] if deliveries else None,
                "next_explicit_tool": next_tool,
                "fix_patch_arguments": {"task_ids": [], "message": "Describe this fixed version"},
                "scope": "Same-version public evidence only; submission is not official acceptance"}

    def _action_delivery_status(self, actor, project_id):
        artifact, version, _ = self._bundle(actor)
        return self._delivery_status_for_reference(actor, _reference(artifact, version))


class SoftwareCollaborationPort(legacy.SoftwareCollaborationPort):
    def observe(self):
        observation = super().observe()
        world = self._session._world
        observation.update(profile=VERSION, interface_revision=VERSION, purpose=PURPOSE)
        # The reference and retained state come from the parent's one locked snapshot;
        # no second source refresh or hidden evaluation is performed here.
        observation["delivery_status"] = world._delivery_status_for_reference(
            self.role, observation["workspace_reference"])
        observation["tool_navigation"].update(repository_search="search_repository", delivery="delivery_status")
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
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-S1-v056",
            "world": {"world_id": "software-benchmark-v056", "actors": {a: {} for a in (*MEMBERS, "operator")},
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
    world.source_provider, world.test_budget = provider, legacy.previous.TestBudget(root / "team-test-budget.json")
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
