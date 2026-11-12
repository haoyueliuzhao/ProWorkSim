"""Small software collaboration world; no new agent or training runtime.

Member workspaces are private WorldCore objects. Tools expose files and diffs,
not editable bookkeeping. Published patches and deliveries pin real versions;
all authority changes and integration attempts keep their original actor.
This adapter reuses the v0.15 development source and OS execution boundary.
It does not admit that source to training or independent confirmation.
"""

import copy
import difflib
import json
from pathlib import Path
import subprocess
import tempfile

from .adapters.capabilities import encode, read
from .core.transitions import ActionFrame
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .software_acceptance import assess_api
from .software_sandbox import run_isolated
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .templates.software_maintenance import ASSETS as LEGACY_ASSETS
from .templates.software_maintenance import source_bundle
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors
from .world_core import WorldCore

VERSION = "software-collaboration-v0.27"
PROJECT = "SOFTWARE27"
MEMBERS = ("member_a", "member_b")
ASSETS = Path(__file__).resolve().parents[2] / "examples/software-collaboration-v027"
EDITABLE = frozenset({"src/marshmallow/fields.py", "consumer.py", "test_member.py"})
CASE_IDS = ("marshmallow-interface-dev", "marshmallow-integration-dev")


def _tool(name, description, properties=None, required=None):
    properties = properties or {}
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(properties) if required is None else required,
                           "additionalProperties": False}}


_TEXT = {"type": "string"}
_PATH = {"type": "string", "minLength": 1}
_MEMBER = {"type": "string", "enum": list(MEMBERS)}
TOOLS = [
    _tool("list_files", "List your private working files; published patch_id selects its fixed tree.",
          {"patch_id": _PATH}, []),
    _tool("read_file", "Read actual file lines from your workspace or a published fixed patch.",
          {"path": _PATH, "start_line": {"type": "integer", "minimum": 1},
           "max_lines": {"type": "integer", "minimum": 1, "maximum": 180}, "patch_id": _PATH},
          ["path", "start_line", "max_lines"]),
    _tool("search_file", "Search literal text in one actual working file; returns at most 30 lines.",
          {"path": _PATH, "text": _PATH}),
    _tool("replace_file", "Replace one unique exact text match in your working file; records a real version.",
          {"path": _PATH, "old": _PATH, "new": _TEXT}),
    _tool("write_file", "Write your editable working file, including test_member.py for your own tests.",
          {"path": _PATH, "text": _TEXT}),
    _tool("diff_workspace", "Read your unified diff against the shared frozen source baseline."),
    _tool("claim_task", "Atomically claim one unassigned task. Both members can claim either task.",
          {"task_id": _PATH}),
    _tool("delegate_task", "Transfer your current task responsibility without rewriting earlier actions.",
          {"task_id": _PATH, "to_member": _MEMBER}),
    _tool("declare_dependency", "Declare an acyclic task dependency. Fixing the dependent patch requires the upstream patch in this tree, or both tasks in the same patch.",
          {"task_id": _PATH, "depends_on": _PATH}),
    _tool("fix_patch", "Publish your immutable cumulative diff, version and task responsibility. Does not run tests or establish correctness.",
          {"task_ids": {"type": "array", "items": _PATH, "minItems": 1, "uniqueItems": True}, "message": _TEXT}),
    _tool("handoff_patch", "Send a published fixed patch and a message; recipient chooses when to inspect and integrate it.",
          {"patch_id": _PATH, "to_member": _MEMBER, "message": _TEXT}),
    _tool("integrate_patch", "Three-way merge a published patch into your copy. Real conflicts write conflict markers for you to repair; no automatic resolution or tests.",
          {"patch_id": _PATH}),
    _tool("run_tests", "Run fixed visible tests and optional test_member.py on this exact tree in the existing OS sandbox. Test success is feedback, not independent acceptance."),
    _tool("submit_integration", "Fix this integrated working tree for independent parent-process acceptance. Requires a real current-version test execution, not a green self-reported result.",
          {"message": _TEXT}),
]


def case_spec(case_id=CASE_IDS[0]):
    if case_id not in CASE_IDS:
        raise ValueError("Unknown software development case")
    return {"version": VERSION, "case_id": case_id, "family": "marshmallow",
            "usage": "interface_dev", "split": "interface_dev", "training_eligible": False,
            "independent_confirmation_eligible": False, "active_roles": list(MEMBERS),
            "role_decision_limits": dict.fromkeys(MEMBERS, 24),
            "task_type": "producer_consumer" if case_id == CASE_IDS[0] else "cross_feature_integration",
            "source_relation": "Reused v0.15 source and development acceptance; not fresh model support or held-out evidence."}


def _material(case_id):
    bundle = source_bundle()
    bundle["files"]["contract.md"] = (ASSETS / "public" / (case_id + ".md")).read_text()
    bundle["files"]["test_member.py"] = "# Optional member-authored exploratory tests.\n"
    if case_id == CASE_IDS[1]:
        bundle["files"]["test_visible.py"] += (ASSETS / "public/casefold_visible.py").read_text()
    bundle["included_patch_ids"] = []
    return bundle


def _task_definitions(case_id):
    if case_id == CASE_IDS[0]:
        return {"string_api": "Implement optional String strip_whitespace while preserving legacy behavior.",
                "inventory_consumer": "Adapt inventory SKU loading to the optional API; preserve descriptions and dump behavior."}
    return {"whitespace": "Add optional String whitespace normalization and adapt inventory SKU loading.",
            "casefold": "Add optional String casefold normalization. Both options must compose and preserve default/dump/error behavior."}


def _package(case_id):
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json",
                "owner": "operator", "readers": [*MEMBERS, "operator"], "writers": ["operator"],
                "data": _material(case_id)}]
    for member in MEMBERS:
        objects.append({"alias": member, "filename": member + ".json", "kind": "json",
                        "owner": member, "readers": [member, "operator"], "writers": [member],
                        "data": _material(case_id)})
    return {"project_id": PROJECT, "goal": "Choose responsibilities, implement, test and integrate both software requirements.",
            "participants": [*MEMBERS, "operator"], "objects": objects, "works": [], "grants": [],
            "provenance": {"kind": "synthetic", "note": "Real pinned Marshmallow source; simulated development requirements."}}


def _reference(artifact, version):
    return {"object_id": artifact["artifact_id"], "version_id": version}


def _diff(before, after):
    return "".join("".join(difflib.unified_diff(before.get(path, "").splitlines(keepends=True),
                                               after.get(path, "").splitlines(keepends=True),
                                               fromfile="a/" + path, tofile="b/" + path))
                   for path in sorted(set(before) | set(after)) if before.get(path) != after.get(path))


def _merge_file(base, local, incoming):
    """Controller-only git diff3 on selected bytes, never an actor command."""
    if local == base or local == incoming:
        return incoming, False
    if incoming == base:
        return local, False
    with tempfile.TemporaryDirectory(prefix="proworksim-merge-") as directory:
        paths = [Path(directory) / name for name in ("local", "base", "incoming")]
        for path, value in zip(paths, (local, base, incoming), strict=True):
            path.write_text(value)
        result = subprocess.run(["git", "merge-file", "--stdout", "--diff3", "-L", "working-copy",
                                 "-L", "frozen-base", "-L", "incoming-patch", *map(str, paths)],
                                capture_output=True, text=True, timeout=10, check=False)
    if result.returncode < 0 or result.returncode > 127:
        raise ValueError("Three-way merge failed: " + result.stderr[:1000])
    return result.stdout, result.returncode != 0


class SoftwareCollaborationWorld(WorldCore):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _action_frame(self, actor, action, arguments):
        frame = super()._action_frame(actor, action, arguments)
        return ActionFrame(frame.name, frame.paths + (("software_events",),), frame.derived_paths,
                           frame.immutable_submission_extensions, frame.append_only_extensions + ("software_events",))

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if project_id != PROJECT or actor not in MEMBERS:
            raise ValueError("Only the two bound software members may use this interface")
        specs = {entry["name"]: entry for entry in TOOLS}
        if tool not in specs:
            raise ToolRejection("Not in the software interface", code="tool_not_enabled", category="capability_gap")
        errors = _schema_errors(specs[tool]["parameters"], arguments)
        if errors:
            raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def _software(self):
        return self.state["projects"][PROJECT]["software"]

    def _event(self, actor, kind, **facts):
        event = {"sequence": len(self.state["software_events"]) + 1, "actor_id": actor,
                 "kind": kind, "logical_time": self.state["clock"],
                 "operation_id": self._operation_context["operation_id"],
                 "action_id": "action-" + str(len(self.state["interactions"]) + 1),
                 "responsibility_snapshot": {key: value["owner"] for key, value in self._software()["tasks"].items()},
                 **copy.deepcopy(facts)}
        self.state["software_events"].append(event)
        return event

    def _bundle(self, actor, *, patch_id=None, reference=None, write=False, baseline=False):
        if patch_id is not None:
            reference = self._patch(patch_id)["source_reference"]
        if reference is not None:
            artifact, version = self._object(actor, PROJECT, object_id=reference["object_id"],
                                             version_id=reference["version_id"], write=write)
        else:
            artifact, version = self._object(actor, PROJECT, alias="baseline" if baseline else actor, write=write)
        return artifact, version, read("json", self.store.version_path(artifact, version).read_bytes())

    def _patch(self, patch_id):
        patch = self._software()["patches"].get(patch_id)
        if patch is None:
            raise ValueError("Unknown published patch")
        return patch

    def _task(self, task_id, actor=None):
        task = self._software()["tasks"].get(task_id)
        if task is None:
            raise ValueError("Unknown task")
        if actor is not None and task["owner"] != actor:
            raise ValueError("Only the current task owner may perform this task operation")
        return task

    def _share_fixed(self, actor, reference):
        self.state["shares"].append({"project_id": PROJECT, **reference,
                                     "actor_ids": list(MEMBERS), "shared_by": actor,
                                     "at": self.state["clock"]})

    def _action_list_files(self, actor, project_id, patch_id=None):
        artifact, version, bundle = self._bundle(actor, patch_id=patch_id)
        return {"source_reference": _reference(artifact, version), "files":
                [{"path": path, "lines": len(value.splitlines()), "editable": path in EDITABLE}
                 for path, value in sorted(bundle["files"].items())]}

    def _action_read_file(self, actor, project_id, path, start_line, max_lines, patch_id=None):
        artifact, version, bundle = self._bundle(actor, patch_id=patch_id)
        if path not in bundle["files"]:
            raise ValueError("Path must be an indexed working file")
        self._reads.append({"artifact_id": artifact["artifact_id"], "version_id": version,
                            "path": path, "start_line": start_line, "max_lines": max_lines})
        lines = bundle["files"][path].splitlines()
        self._event(actor, "read", source_reference=_reference(artifact, version), path=path,
                    start_line=start_line, max_lines=max_lines, patch_id=patch_id)
        return {"source_reference": _reference(artifact, version), "path": path,
                "text": "\n".join(lines[start_line - 1:start_line - 1 + max_lines]), "total_lines": len(lines)}

    def _action_search_file(self, actor, project_id, path, text):
        artifact, version, bundle = self._bundle(actor)
        if path not in bundle["files"] or len(text) > 200:
            raise ValueError("Choose one indexed path and bounded literal text")
        matches = [{"line": i, "text": line} for i, line in enumerate(bundle["files"][path].splitlines(), 1) if text in line]
        self._event(actor, "search", source_reference=_reference(artifact, version), path=path,
                    matched_lines=[item["line"] for item in matches[:30]])
        return {"source_reference": _reference(artifact, version), "matches": matches[:30], "total_matches": len(matches)}

    def _write_file(self, actor, path, text, artifact, version, bundle):
        if path not in EDITABLE or not isinstance(text, str) or len(text.encode()) > 300_000:
            raise ValueError("Write must target a declared editable file within the byte limit")
        before = bundle["files"][path]
        if before == text:
            raise ValueError("File content did not change")
        bundle["files"][path] = text
        reference = self._save_content(actor, PROJECT, artifact, encode("json", bundle))
        self._event(actor, "edit", path=path, previous_reference=_reference(artifact, version),
                    source_reference=reference, before_sha256=digest(before.encode()), after_sha256=digest(text.encode()))
        return {"source_reference": reference, "path": path, "sha256": digest(text.encode())}

    def _action_replace_file(self, actor, project_id, path, old, new):
        artifact, version, bundle = self._bundle(actor, write=True)
        if path not in EDITABLE or bundle["files"][path].count(old) != 1:
            raise ValueError("Choose an editable path and an exact unique old text")
        return self._write_file(actor, path, bundle["files"][path].replace(old, new, 1), artifact, version, bundle)

    def _action_write_file(self, actor, project_id, path, text):
        artifact, version, bundle = self._bundle(actor, write=True)
        return self._write_file(actor, path, text, artifact, version, bundle)

    def _action_diff_workspace(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        _, _, baseline = self._bundle(actor, baseline=True)
        return {"source_reference": _reference(artifact, version), "diff": _diff(baseline["files"], bundle["files"])}

    def _action_claim_task(self, actor, project_id, task_id):
        task = self._task(task_id)
        if task["owner"] is not None:
            raise ValueError("Task has already been claimed")
        task["owner"] = actor
        self._event(actor, "claim", task_id=task_id, previous_owner=None, owner=actor)
        return copy.deepcopy(task)

    def _action_delegate_task(self, actor, project_id, task_id, to_member):
        task = self._task(task_id, actor)
        if to_member == actor:
            raise ValueError("Delegate to the other stable member")
        task["owner"] = to_member
        self._event(actor, "delegate", task_id=task_id, previous_owner=actor, owner=to_member)
        return copy.deepcopy(task)

    def _action_declare_dependency(self, actor, project_id, task_id, depends_on):
        task = self._task(task_id, actor)
        self._task(depends_on)
        pending = [depends_on]
        visited = set()
        while pending:
            key = pending.pop()
            if key == task_id:
                raise ValueError("Task dependency must be acyclic")
            if key not in visited:
                visited.add(key)
                pending.extend(self._task(key)["depends_on"])
        if depends_on in task["depends_on"]:
            raise ValueError("Dependency already declared")
        task["depends_on"].append(depends_on)
        self._event(actor, "dependency_declared", task_id=task_id, depends_on=depends_on)
        return copy.deepcopy(task)

    def _action_fix_patch(self, actor, project_id, task_ids, message):
        artifact, version, bundle = self._bundle(actor)
        base_artifact, base_version, baseline = self._bundle(actor, baseline=True)
        included = bundle["included_patch_ids"]
        supplied_tasks = {task for pid in included for task in self._patch(pid)["task_ids"]}
        for task_id in task_ids:
            task = self._task(task_id, actor)
            if not set(task["depends_on"]) <= supplied_tasks | set(task_ids):
                raise ValueError("Declared dependency needs its fixed patch integrated into this tree")
        changed = [path for path in sorted(EDITABLE) if baseline["files"][path] != bundle["files"][path]]
        if not changed:
            raise ValueError("No changed file to publish")
        patch_id = "patch-" + str(len(self._software()["patches"]) + 1)
        patch = {"patch_id": patch_id, "author": actor, "task_ids": list(task_ids), "message": message,
                 "source_reference": _reference(artifact, version), "base_reference": _reference(base_artifact, base_version),
                 "source_sha256": digest(json_bytes(bundle)), "files_sha256": digest(json_bytes(bundle["files"])),
                 "changed_paths": changed, "diff_sha256": digest(_diff(baseline["files"], bundle["files"]).encode()),
                 "included_patch_ids": list(included)}
        self._software()["patches"][patch_id] = patch
        self._share_fixed(actor, patch["source_reference"])
        self._event(actor, "patch_fixed", **patch)
        return copy.deepcopy(patch)

    def _action_handoff_patch(self, actor, project_id, patch_id, to_member, message):
        patch = self._patch(patch_id)
        if to_member == actor:
            raise ValueError("Handoff recipient must be the other member")
        event = self._event(actor, "handoff", patch_id=patch_id, recipient=to_member, message=message,
                            source_reference=patch["source_reference"])
        return {"handoff_sequence": event["sequence"], "patch_id": patch_id, "recipient": to_member}

    def _action_integrate_patch(self, actor, project_id, patch_id):
        patch = self._patch(patch_id)
        artifact, version, bundle = self._bundle(actor, write=True)
        if patch_id in bundle["included_patch_ids"]:
            raise ValueError("This fixed patch has already been integrated")
        _, _, incoming = self._bundle(actor, patch_id=patch_id)
        _, _, baseline = self._bundle(actor, reference=patch["base_reference"])
        conflicts = []
        for path in patch["changed_paths"]:
            merged, conflict = _merge_file(baseline["files"][path], bundle["files"][path], incoming["files"][path])
            bundle["files"][path] = merged
            if conflict:
                conflicts.append(path)
        bundle["included_patch_ids"] = sorted(set(bundle["included_patch_ids"]) | {patch_id} | set(patch["included_patch_ids"]))
        # The source object cannot depend on itself; same-member historical
        # versions remain in the immutable integration event instead.
        dependencies = [self._patch(pid)["source_reference"] for pid in bundle["included_patch_ids"]
                        if self._patch(pid)["source_reference"]["object_id"] != artifact["artifact_id"]]
        reference = self._save_content(actor, PROJECT, artifact, encode("json", bundle), dependencies)
        event = self._event(actor, "integrate", patch_id=patch_id, input_reference=patch["source_reference"],
                            previous_reference=_reference(artifact, version), source_reference=reference,
                            source_sha256=digest(json_bytes(bundle)), files_sha256=digest(json_bytes(bundle["files"])),
                            conflicts=conflicts, status="conflict_markers_written" if conflicts else "merged",
                            included_patch_ids=bundle["included_patch_ids"])
        return {key: copy.deepcopy(event[key]) for key in ("source_reference", "conflicts", "status", "included_patch_ids")}

    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        code = "import runpy\nrunpy.run_path('test_visible.py', run_name='__main__')\nrunpy.run_path('test_member.py', run_name='__main__')\n"
        result = run_isolated(bundle["files"], code, run_root=self.store.root / "software-execution")
        result.update(source_reference=_reference(artifact, version), source_sha256=digest(json_bytes(bundle)),
                      files_sha256=digest(json_bytes(bundle["files"])), suite="visible-and-member-v0.27")
        self._event(actor, "test", **result)
        return result

    def _action_submit_integration(self, actor, project_id, message):
        artifact, version, bundle = self._bundle(actor)
        reference = _reference(artifact, version)
        matching = [event for event in self.state["software_events"] if event["kind"] == "test"
                    and event["actor_id"] == actor and event["source_reference"] == reference and event["executed"]]
        if not matching:
            raise ValueError("Run real tests on this exact working version before submitting")
        if not any(self._patch(pid)["source_reference"] == reference for pid in self._software()["patches"]):
            raise ValueError("Publish a fixed patch of this exact working version before submitting")
        delivery = {"delivery_id": "delivery-" + str(len(self._software()["deliveries"]) + 1),
                    "actor_id": actor, "source_reference": reference, "source_sha256": digest(json_bytes(bundle)),
                    "files_sha256": digest(json_bytes(bundle["files"])), "included_patch_ids": bundle["included_patch_ids"],
                    "test_sequence": matching[-1]["sequence"], "message": message}
        self._software()["deliveries"].append(copy.deepcopy(delivery))
        self._share_fixed(actor, reference)
        self._event(actor, "submit", **{key: value for key, value in delivery.items() if key != "actor_id"})
        return delivery


class SoftwareCollaborationPort:
    """tools/observe/call is the existing capture_port/StaffRuntime contract."""
    def __init__(self, session, role, **_):
        if role not in MEMBERS or session.actor_id != role or session.project_id != PROJECT:
            raise ValueError("Software member identity must match the trusted session")
        self._session, self.role = session, role
        self.profile = VERSION + ":" + role

    def tools(self):
        return self._session.tools()

    def observe(self):
        world = self._session._world
        with world.store.lock():
            world.state = world.store.load()
            artifact, version, bundle = world._bundle(self.role)
            facts = world._software()
            return {"role": self.role, "project_id": PROJECT, "profile": self.profile,
                    "world_id": world.state["world_id"], "instance_id": world.state["instance_id"],
                    "branch_id": world.state["branch_id"], "actor_id": self.role,
                    "logical_time": world.state["clock"], "world_status": world.state["world_status"],
                    "projects": {PROJECT: {"project_id": PROJECT}},
                    "contract": bundle["files"]["contract.md"], "workspace_reference": _reference(artifact, version),
                    "editable_paths": sorted(EDITABLE), "included_patch_ids": bundle["included_patch_ids"],
                    "tasks": copy.deepcopy(facts["tasks"]), "patches": copy.deepcopy(list(facts["patches"].values())),
                    "deliveries": copy.deepcopy(facts["deliveries"]),
                    "handoffs": [copy.deepcopy(event) for event in world.state["software_events"]
                                 if event["kind"] == "handoff" and event["recipient"] == self.role],
                    "isolation": "Private managed file versions; fixed tests in existing read-only Landlock/seccomp worker."}

    def call(self, action, request_key=None, **arguments):
        return self._session.call(action, request_key=request_key, **arguments)


def build_software_collaboration_case(case, root):
    case = case_spec(case) if isinstance(case, str) else copy.deepcopy(case)
    if case != case_spec(case["case_id"]):
        raise ValueError("Case differs from frozen interface development declaration")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"],
            "world": {"world_id": "software-collaboration-v027", "actors": {actor: {} for actor in (*MEMBERS, "operator")},
                      "applications": ["files"], "publication_policy": "explicit",
                      "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
            "installer": "operator", "projects": [{"package": _package(case["case_id"])}],
            "roles": [{"role_id": member, "actor": member, "project": PROJECT, "policy": "model",
                       "config": {"task": "Choose responsibilities and perform the public software collaboration work."}} for member in MEMBERS],
            "setup": [], "events": [], "start": {"kind": "initial"}, "boundary": {"max_opportunities": 48}}
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    with world.store.lock():
        world.state = world.store.load()
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {
            "case": case, "tasks": {key: {"task_id": key, "description": text, "owner": None, "depends_on": []}
                                    for key, text in _task_definitions(case["case_id"]).items()},
            "patches": {}, "deliveries": []}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": "interface_dev", "preparation_credit": False,
              "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
              "source_reused_from": "software-maintenance-v0.15", "training_eligible": False}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": False,
                                 "independent_assessment": "assess_software_collaboration"}, prefix)
    prepared.port_factory = SoftwareCollaborationPort
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def software_collaboration_facts(prepared_or_state):
    """Public provenance for the mapper; accepts a persisted episode state too.

    These facts record attempted integration, not proven semantic dependence.
    Consumers must bind operation IDs to WorldCore receipts and raw captures.
    """
    if isinstance(prepared_or_state, dict):
        state = prepared_or_state
    else:
        state = prepared_or_state.world.store.load()
    return {"version": VERSION, **copy.deepcopy(state["projects"][PROJECT]["software"]),
            "events": copy.deepcopy(state.get("software_events", []))}


def _acceptance_fixture(case_id, run_root):
    if case_id == CASE_IDS[0]:
        return LEGACY_ASSETS / "private/api-acceptance.json"
    base = json.loads((LEGACY_ASSETS / "private/api-acceptance.json").read_text())
    extra = json.loads((ASSETS / "private/casefold-acceptance.json").read_text())
    base["groups"] += extra["groups"]
    base["cases"] += extra["cases"]
    destination = Path(run_root) / "combined-parent-fixture.json"
    atomic_write(destination, json_bytes(base))
    return destination


def assess_software_collaboration(prepared, *, run_root):
    """Assess the latest fixed integrated tree, never patch-average scores."""
    world = prepared.world
    world.state = world.store.load()
    facts = software_collaboration_facts(world.state)
    if not facts["deliveries"]:
        return {"version": VERSION, "status": "evaluable", "R": 0, "submitted": False,
                "reason": "No fixed integrated delivery", "usage": "interface_dev"}
    delivery = facts["deliveries"][-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = assess_api(bundle["files"], fixture_path=_acceptance_fixture(prepared.case["case_id"], run_root), run_root=run_root)
    return {"version": VERSION, "status": "evaluable" if result["executed"] else "unknown",
            "R": int(result["passed"]) if result["executed"] else None, "submitted": True,
            "delivery": delivery, "independent_acceptance": result, "usage": "interface_dev",
            "training_eligible": False, "independent_confirmation_eligible": False,
            "scope": "Independent parent judgment of one combined fixed tree; reused development tests, not a held-out algorithm result."}
