"""Pinned real Marshmallow sources with a new simulated consumer requirement.

The software extension journals ordinary WorldCore source versions, test output,
submissions and review. Only fixed Python test commands run in the separate OS
sandbox. Private acceptance assets are never included in the installed world.
"""
import copy
import json
from pathlib import Path

from ..adapters.capabilities import encode, read
from ..core.references import VersionRef
from ..scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from ..software_sandbox import run_isolated
from ..software_acceptance import assess_api
from ..storage import atomic_write, digest, json_bytes
from ..tool_outcomes import ToolRejection
from ..work_interface import WorkInterface, _schema_errors
from ..world_core import WorldCore
from .online_work import PreparedOnlineCase

VERSION = "software-maintenance-v0.15"
ASSETS = Path(__file__).resolve().parents[3] / "examples/software-v15"
EDITABLE = {"src/marshmallow/fields.py", "consumer.py"}
WORK = "SOFTWARE::change"
CUSTOM_TOOLS = [
    {"name": "search_source", "description": "Search literal text within one indexed source file. Returns up to 30 real matching line numbers and text; no regex, shell, hidden files or suggested edits.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string", "minLength": 1}, "text": {"type": "string", "minLength": 1}}, "required": ["path", "text"], "additionalProperties": False}},
    {"name": "read_source", "description": "Read a line window of a real file in the source bundle. An optional exact source reference selects a fixed submitted version. Lists actual matching source lines; no solver or hidden tests.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string", "minLength": 1}, "start_line": {"type": "integer", "minimum": 1}, "max_lines": {"type": "integer", "minimum": 1}, "reference": {"type": "object"}}, "required": ["path", "start_line", "max_lines"], "additionalProperties": False}},
    {"name": "replace_source", "description": "Replace exactly one occurrence of old text in an editable source file. Explicitly creates a new immutable source version; never repairs or selects code for you. Only the two declared files are editable.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string", "minLength": 1}, "old": {"type": "string", "minLength": 1}, "new": {"type": "string"}}, "required": ["path", "old", "new"], "additionalProperties": False}},
    {"name": "run_tests", "description": "Run the fixed visible unittest suite against the current source bundle in an isolated read-only Python process. Write the real output and exact executed source reference to test_result. Does not reveal private acceptance, edit source, or submit.",
     "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
]


def manifest():
    return json.loads((ASSETS / "source-manifest.json").read_text())


def source_bundle():
    origin = manifest()
    files = {}
    for name, sha in origin["files"].items():
        raw = (ASSETS / "upstream" / name).read_bytes()
        if digest(raw) != sha:
            raise ValueError("Frozen upstream source hash changed: " + name)
        files[name] = raw.decode()
    for name in ("consumer.py", "test_visible.py", "contract.md"):
        files[name] = (ASSETS / "public" / name).read_text()
    return {"files": files, "upstream": {key: origin[key] for key in ("repository", "commit", "tag", "license")}}


def case_spec(case_id="marshmallow-v15-strip-implement"):
    if case_id != "marshmallow-v15-strip-implement":
        raise ValueError("Unknown software situation")
    return {"version": VERSION, "case_id": case_id, "family": "marshmallow", "pool": "development",
            "split": "development", "task": "implement", "active_roles": ["implementer"],
            "role_decision_limits": {"implementer": 18}, "source_family_count": 1,
            "source_relation": "Real pinned source, new simulated requirement. This development use is not an unseen-source test."}


def _package():
    participants = ["implementer", "reviewer", "operator"]
    objects = [
        {"alias": "source", "filename": "source.json", "owner": "implementer", "readers": participants,
         "kind": "json", "deliverable_role": "software_source", "data": source_bundle()},
        {"alias": "test_result", "filename": "test_result.json", "owner": "implementer", "readers": participants,
         "kind": "json", "deliverable_role": "software_test_result", "data": {"executed": False}},
        {"alias": "contract", "filename": "contract.json", "owner": "operator", "writers": ["operator"], "readers": participants,
         "kind": "json", "deliverable_role": "requirements", "data": {"text": (ASSETS / "public/contract.md").read_text()}},
    ]
    return {"project_id": "SOFTWARE", "goal": "Implement the explicit inventory importer compatibility request against actual Marshmallow source and submit a tested immutable patch.",
            "participants": participants, "objects": objects,
            "works": [{"work_id": "change", "owner": "implementer", "approval_policy": "review",
                       "goal": "Read contract and source, implement the opt-in behavior and consumer adaptation, execute and explicitly submit.",
                       "visible_requirements": [(ASSETS / "public/contract.md").read_text()],
                       "requirements": {"source_commit": manifest()["commit"], "editable_paths": sorted(EDITABLE),
                                        "visible_tests": "test_visible.py", "independent_acceptance": "Frozen private cases reconstruct submitted source. Visible tests are incomplete.",
                                        "public_structure": {}},
                       "deliverable_contract": {"min_files": 2, "max_files": 2,
                                                "allowed_roles": ["software_source", "software_test_result"], "allowed_kinds": ["json"]}}],
            "grants": [{"actor_id": "reviewer", "power": power, "subject": "deliverable", "work_nodes": ["change"]}
                       for power in ("review", "approve")],
            "provenance": {"kind": "synthetic", "note": "The code bytes are real pinned upstream; roles, workflow and maintenance requirement are simulated", "source_evidence_refs": [manifest()["repository"] + "/tree/" + manifest()["commit"]]}}


class SoftwareWorldCore(WorldCore):
    """Independent extension; core lifecycle/authority/journaling stay shared."""
    def _tool_definitions(self, project_id):
        definitions = super()._tool_definitions(project_id)
        return definitions + (copy.deepcopy(CUSTOM_TOOLS) if project_id == "SOFTWARE" else [])

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in {t["name"] for t in CUSTOM_TOOLS}:
            spec = next(t for t in CUSTOM_TOOLS if t["name"] == tool)
            errors = _schema_errors(spec["parameters"], arguments)
            if errors:
                raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
            if project_id != "SOFTWARE" or actor not in {"implementer", "reviewer"}:
                raise ValueError("Software tools require an authorized software role")
            if tool not in {"read_source", "search_source"} and actor != "implementer":
                raise ValueError("Only the implementation owner can edit or execute this bounded task")
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def _bundle(self, actor, project_id, reference=None, *, write=False):
        if reference is None:
            artifact, vid = self._object(actor, project_id, alias="source", write=write)
        else:
            ref = VersionRef.from_mapping(reference)
            artifact, vid = self._object(actor, project_id, object_id=ref.object_id, version_id=ref.version_id)
            if artifact["artifact_id"] != self.state["workspaces"][project_id]["source"]:
                raise ValueError("Reference must name the installed source object")
        return artifact, vid, read("json", self.store.version_path(artifact, vid).read_bytes())

    def _action_read_source(self, actor, project_id, path, start_line, max_lines, reference=None):
        artifact, vid, bundle = self._bundle(actor, project_id, reference)
        if path not in bundle["files"] or max_lines > 180:
            raise ValueError("Choose an existing indexed file and at most 180 lines")
        lines = bundle["files"][path].splitlines()
        result = {"reference": {"object_id": artifact["artifact_id"], "version_id": vid}, "path": path,
                  "start_line": start_line, "end_line": min(start_line + max_lines - 1, len(lines)),
                  "total_lines": len(lines), "text": "\n".join(lines[start_line - 1:start_line - 1 + max_lines])}
        # Partial source exposure is recorded as ranges, never a full-file read.
        self.state["knowledge"][actor].setdefault("source_ranges", []).append({key: copy.deepcopy(value) for key, value in result.items() if key != "text"})
        self._reads.append({"artifact_id": artifact["artifact_id"], "version_id": vid, "path": path,
                            "start_line": start_line, "max_lines": max_lines})
        return result

    def _action_search_source(self, actor, project_id, path, text):
        artifact, vid, bundle = self._bundle(actor, project_id)
        if path not in bundle["files"] or len(text) > 200:
            raise ValueError("Choose an indexed source path and bounded literal text")
        matches = [{"line": i, "text": line} for i, line in enumerate(bundle["files"][path].splitlines(), 1) if text in line]
        self.state["knowledge"][actor].setdefault("source_searches", []).append({"object_id": artifact["artifact_id"], "version_id": vid, "path": path, "text": text, "lines": [m["line"] for m in matches[:30]]})
        return {"reference": {"object_id": artifact["artifact_id"], "version_id": vid}, "path": path, "matches": matches[:30], "total_matches": len(matches)}

    def _action_replace_source(self, actor, project_id, path, old, new):
        if path not in EDITABLE or not old or len(new) > 40000:
            raise ValueError("Replacement is outside the declared bounded source scope")
        artifact, vid, bundle = self._bundle(actor, project_id, write=True)
        if bundle["files"][path].count(old) != 1:
            raise ValueError("Old text must match exactly once; inspect the actual current source")
        bundle["files"][path] = bundle["files"][path].replace(old, new, 1)
        ref = self._save_content(actor, project_id, artifact, encode("json", bundle), [], WORK)
        return {"reference": ref, "path": path, "previous_version": vid, "sha256": digest(bundle["files"][path].encode())}

    def _action_run_tests(self, actor, project_id):
        artifact, vid, bundle = self._bundle(actor, project_id)
        source_ref = {"object_id": artifact["artifact_id"], "version_id": vid}
        code = "import runpy\nrunpy.run_path('test_visible.py', run_name='__main__')\n"
        result = run_isolated(bundle["files"], code, run_root=self.store.root / "software-execution")
        result.update(source_reference=source_ref, source_bundle_sha256=digest(json_bytes(bundle)), suite="visible-unittest-v0.15")
        output, _ = self._object(actor, project_id, alias="test_result", write=True)
        result["report_reference"] = self._save_content(actor, project_id, output, encode("json", result), [source_ref], WORK)
        return result


class SoftwareMaintenancePort:
    def __init__(self, session, role, *, audit_dir=None, **_):
        self._session, self.role = session, role
        self.shared = WorkInterface(session, role, variant="v14", presentation="compact_v14", audit_dir=audit_dir)
        self.profile = VERSION + ":" + role

    def tools(self):
        names = {"read_alias", "read_version", "submit", "inspect_submission", "withdraw", "raise_issue", "approve", "respond_issue", "decide_issue", "wait"}
        definitions = [t for t in self.shared.tools() if t["name"] in names]
        definitions += [copy.deepcopy(t) for t in CUSTOM_TOOLS if self.role == "implementer" or t["name"] in {"read_source", "search_source"}]
        return definitions

    def observe(self):
        observation = self.shared.observe()
        artifact, _, bundle = self._session._world._bundle(self._session.actor_id, "SOFTWARE")
        observation["software_workspace"] = {"source_object_id": artifact["artifact_id"], "editable_paths": sorted(EDITABLE),
                                             "file_index": [{"path": name, "lines": len(content.splitlines())} for name, content in bundle["files"].items()],
                                             "isolation": "Landlock read-only allowlist, seccomp denies network/processes; fixed test command, 20s wall/10s CPU/512MiB."}
        return observation

    def call(self, action, request_key=None, **arguments):
        if action not in {t["name"] for t in self.tools()}:
            return {"ok": False, "error": {"message": "Not in the frozen software interface"}}
        if action in {t["name"] for t in CUSTOM_TOOLS}:
            return self._session.call(action, request_key=request_key, **arguments)
        return self.shared.call(action, request_key=request_key, **arguments)


def build_software_case(case, root):
    case = case_spec(case) if isinstance(case, str) else copy.deepcopy(case)
    if case != case_spec(case["case_id"]):
        raise ValueError("Software case differs from the frozen development declaration")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"],
            "world": {"world_id": "software-maintenance", "actors": {actor: {} for actor in ("implementer", "reviewer", "operator")},
                      "applications": ["files"], "publication_policy": "explicit",
                      "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
            "installer": "operator", "projects": [{"package": _package()}],
            "roles": [{"role_id": role, "actor": role, "project": "SOFTWARE", "policy": "model",
                       "config": {"task": "Complete the bounded software responsibility using the public contract, actual source and actual test feedback."}}
                      for role in ("implementer", "reviewer")],
            "setup": [], "events": [], "start": {"kind": "initial"}, "boundary": {"max_opportunities": 18}}
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareWorldCore(root / "world")
    prefix = {"version": VERSION, "prepared_business_state_sha256": digest(json_bytes(initial_business_state(deployment.world))),
              "source_manifest": manifest(), "preparation_credit": False}
    reward = {"version": VERSION, "project_id": "SOFTWARE", "work_id": WORK, "independent_assessment": "assess_software_submission", "training_supported": False}
    prepared = PreparedOnlineCase(deployment, case, reward, prefix)
    prepared.port_factory = SoftwareMaintenancePort
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def assess_software_submission(prepared, *, run_root):
    """Private frozen tests reconstruct exact submitted versions, not workspace."""
    world = prepared.world
    world.state = world.store.load()
    item = world.state["work_items"][WORK]
    submissions = item.get("submissions", [])
    if not submissions:
        return {"version": VERSION, "status": "evaluable", "R": 0, "submitted": False, "reason": "No actual submission"}
    submission = submissions[-1]
    if submission.get("invalidated") or submission.get("current_applicability") == "withdrawn":
        return {"version": VERSION, "status": "evaluable", "R": 0, "submitted": True,
                "submission_id": submission["submission_id"], "reason": "Latest submission is withdrawn or invalidated"}
    source_id = world.state["workspaces"]["SOFTWARE"]["source"]
    result_id = world.state["workspaces"]["SOFTWARE"]["test_result"]
    versions = submission["artifact_versions"]
    if source_id not in versions or result_id not in versions:
        return {"version": VERSION, "status": "evaluable", "R": 0, "submitted": True, "reason": "Required artifacts absent"}
    source_ref = {"object_id": source_id, "version_id": versions[source_id]}
    _, _, bundle = world._bundle("reviewer", "SOFTWARE", source_ref)
    artifact = world.state["artifacts"][result_id]
    report = read("json", world.store.version_path(artifact, versions[result_id]).read_bytes())
    result = assess_api(bundle["files"], fixture_path=ASSETS / "private/api-acceptance.json", run_root=run_root)
    current_report = report.get("source_reference") == source_ref and report.get("source_bundle_sha256") == digest(json_bytes(bundle))
    actual_execution = report.get("executed") is True and report.get("driver_completed") is True and report.get("returncode") == 0 and current_report
    correct = result["passed"] and actual_execution
    return {"version": VERSION, "status": "evaluable" if result["executed"] else "unknown", "R": int(correct) if result["executed"] else None,
            "submitted": True, "submission_id": submission["submission_id"], "source_reference": source_ref,
            "source_bundle_sha256": digest(json_bytes(bundle)), "submitted_report_matches_source": current_report,
            "submitted_visible_driver_claims_pass": actual_execution, "independent_acceptance": result,
            "scope": "One simulated maintenance requirement on pinned real source, no model-learning or source-transfer claim."}
