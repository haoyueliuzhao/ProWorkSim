"""New-source WorldCore binding with a frozen, conjunctive work contract.

Reuses the v0.28.1 work interface and private immutable workspace mechanism.
Only source binding, editable paths and complete-delivery assessment are new.
The finite consumer-call probes establish observed API calls during consumer
execution, not arbitrary anti-gaming or unique causal dependence guarantees.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from . import software_collaboration_v027 as base
from . import software_collaboration_v028 as interface
from . import software_tasks_v028 as source
from .adapters.capabilities import encode
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .software_acceptance import _matches
from .software_sandbox import run_isolated
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase

VERSION = "software-collaboration-v0.29"
INTERFACE_REVISION = interface.INTERFACE_REVISION
PROJECT = interface.PROJECT
MEMBERS = interface.MEMBERS
TASK_IDS = CASE_IDS = source.TASK_IDS
SCHEDULER = interface.SCHEDULER
CONTRACT_VERSION = "source-work-validity-v0.29"
CONTRACT_ROOTS = {
    CASE_IDS[0]: {"sqlparse/sql.py": ["Comparison.left", "Comparison.right"],
                  "consumer.py": ["comparison_records"]},
    CASE_IDS[1]: {"schema/__init__.py": ["Schema.description", "Schema.json_schema"],
                  "consumer.py": ["schema_catalog"]},
    CASE_IDS[2]: {"textfsm/parser.py": ["TextFSMOptions.List.OnSaveRecord", "TextFSM.ParseText"],
                  "consumer.py": ["record_items"]},
}
TOOLS = copy.deepcopy(interface.TOOLS)
for _tool in TOOLS:
    if _tool["name"] == "write_file":
        _tool["description"] = (
            "Replace the ENTIRE declared editable file with text; include all code to retain. "
            "Use replace_file for a local unique-text edit. test_member.py holds your own tests.")
    if _tool["name"] == "run_tests":
        _tool["description"] = (
            "Execute the frozen selected upstream regressions plus optional test_member.py on this exact tree. "
            "Inspect passed and tests; a completed test driver alone does not mean all checks passed. "
            "Feedback does not establish independent complete-delivery acceptance.")


def _source_contract(task_id, material):
    row, directory = source._entry(task_id)
    task = json.loads((directory / "derived-task.json").read_text())
    return {"version": CONTRACT_VERSION, "task_id": task_id, "purpose": material["purpose"],
            "source_asset_id": row["asset_id"], "source_asset_ids": [row["asset_id"]],
            "upstream_commit": row["commit"], "original_task_sha256": row["task_sha256"],
            "source_partition_sha256": material["source_partition_sha256"],
            "baseline_files_sha256": digest(json_bytes(material["files"])),
            "contract_sha256": task["requirements_sha256"],
            "acceptance_fixture_sha256": task["independent_verifier_sha256"],
            "selected_upstream_tests": row["selected_FAIL_TO_PASS"] + row["selected_PASS_TO_PASS"],
            "contract_roots": copy.deepcopy(CONTRACT_ROOTS[task_id]),
            "complete_delivery_requires": ["independent_source_and_consumer_api",
                                           "selected_upstream_regressions", "consumer_api_calls_observed"],
            "consumer_call_probe": "profile_fixed_api_code_objects_during_nonempty_consumer_requests",
            "probe_scope": "finite_observed_calls_and_outputs_not_arbitrary_anti_gaming_or_causal_proof",
            "official_full_suite": False, "two_member_participation_required": False}


def case_spec(case_id=CASE_IDS[0], *, first_member=MEMBERS[0], role_decision_limits=None):
    material = source.build_case(case_id)
    if first_member not in MEMBERS:
        raise ValueError("The first opportunity must belong to one stable member")
    limits = dict.fromkeys(MEMBERS, 48) if role_decision_limits is None else copy.deepcopy(role_decision_limits)
    if (not isinstance(limits, dict) or set(limits) != set(MEMBERS)
            or any(type(value) is not int or not 1 <= value <= 128 for value in limits.values())):
        raise ValueError("Freeze a finite decision limit from 1 to 128 for each member")
    purpose = material["purpose"]
    return {"version": VERSION, "case_id": case_id, "task_id": case_id,
            "family": source.NAMES[case_id], "task_type": "producer_consumer",
            "purpose": purpose, "usage": purpose, "split": purpose,
            "training_eligible": purpose == "policy_training",
            "independent_confirmation_eligible": purpose == "independent_confirmation",
            "active_roles": list(MEMBERS), "role_decision_limits": limits,
            "first_member": first_member, "scheduling_protocol": SCHEDULER,
            "interface_revision": INTERFACE_REVISION,
            "editable_paths": copy.deepcopy(material["editable_paths"]),
            "source_contract": _source_contract(case_id, material),
            "responsibility_scope": "Autonomous claiming/transfer of library and consumer tasks; either member may integrate both",
            "source_relation": "Pinned SWE-smith library mutation plus project-derived consumer; purposes isolated by repository"}


def validate_case(case):
    if not isinstance(case, dict):
        raise ValueError("Case must be the frozen v0.29 source declaration")
    try:
        expected = case_spec(case["case_id"], first_member=case["first_member"],
                             role_decision_limits=case["role_decision_limits"])
    except (KeyError, TypeError) as error:
        raise ValueError("Case must be the frozen v0.29 source declaration") from error
    if case != expected:
        raise ValueError("Case differs from the frozen v0.29 source/purpose declaration")
    return case


class SoftwareCollaborationWorld(interface.SoftwareCollaborationWorld):
    def _editable(self):
        return self._software()["case"]["editable_paths"]

    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _action_list_files(self, actor, project_id, patch_id=None):
        artifact, version, bundle = self._bundle(actor, patch_id=patch_id)
        return {"source_reference": base._reference(artifact, version), "files": [
            {"path": path, "lines": len(value.splitlines()), "editable": path in self._editable()}
            for path, value in sorted(bundle["files"].items())]}

    def _write_file(self, actor, path, text, artifact, version, bundle):
        if path not in self._editable() or not isinstance(text, str) or len(text.encode()) > 300_000:
            raise ValueError("Write must target a declared editable file within the byte limit")
        before = bundle["files"][path]
        if before == text:
            raise ValueError("File content did not change")
        bundle["files"][path] = text
        reference = self._save_content(actor, PROJECT, artifact, encode("json", bundle))
        self._event(actor, "edit", path=path, previous_reference=base._reference(artifact, version),
                    source_reference=reference, before_sha256=digest(before.encode()), after_sha256=digest(text.encode()))
        return {"source_reference": reference, "path": path, "sha256": digest(text.encode())}

    def _action_replace_file(self, actor, project_id, path, old, new):
        artifact, version, bundle = self._bundle(actor, write=True)
        if path not in self._editable() or bundle["files"][path].count(old) != 1:
            raise ValueError("Choose an editable path and an exact unique old text")
        return self._write_file(actor, path, bundle["files"][path].replace(old, new, 1), artifact, version, bundle)

    def _action_fix_patch(self, actor, project_id, task_ids, message):
        artifact, version, bundle = self._bundle(actor)
        base_artifact, base_version, baseline = self._bundle(actor, baseline=True)
        included = bundle["included_patch_ids"]
        supplied = {task for patch_id in included for task in self._patch(patch_id)["task_ids"]}
        for task_id in task_ids:
            task = self._task(task_id, actor)
            if not set(task["depends_on"]) <= supplied | set(task_ids):
                raise ValueError("Declared dependency needs its fixed patch integrated into this tree")
        changed = [path for path in sorted(self._editable()) if baseline["files"][path] != bundle["files"][path]]
        if not changed:
            raise ValueError("No changed file to publish")
        patch_id = "patch-" + str(len(self._software()["patches"]) + 1)
        patch = {"patch_id": patch_id, "author": actor, "task_ids": list(task_ids), "message": message,
                 "source_reference": base._reference(artifact, version),
                 "base_reference": base._reference(base_artifact, base_version),
                 "source_sha256": digest(json_bytes(bundle)), "files_sha256": digest(json_bytes(bundle["files"])),
                 "changed_paths": changed, "diff_sha256": digest(base._diff(baseline["files"], bundle["files"]).encode()),
                 "included_patch_ids": list(included)}
        self._software()["patches"][patch_id] = patch
        self._share_fixed(actor, patch["source_reference"])
        self._event(actor, "patch_fixed", **patch)
        return copy.deepcopy(patch)

    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        task_id = self._software()["case"]["task_id"]
        code = source.public_test_driver(task_id) + "\nimport runpy\nrunpy.run_path('test_member.py', run_name='__main__')\n"
        result = run_isolated(bundle["files"], code, run_root=self.store.root / "software-execution")
        tests = _regression_rows(task_id, result)
        result.update(source_reference=base._reference(artifact, version), source_sha256=digest(json_bytes(bundle)),
                      files_sha256=digest(json_bytes(bundle["files"])), suite="selected-upstream-and-member-v0.29",
                      tests=tests, passed=tests is not None and all(row["passed"] for row in tests))
        self._event(actor, "test", **result)
        return result


class SoftwareCollaborationPort(interface.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        observation = super().observe()
        world = self._session._world
        case = world._software()["case"]
        observation.update(editable_paths=copy.deepcopy(case["editable_paths"]),
                           acceptance_contract={
                               "requirements": copy.deepcopy(case["source_contract"]["complete_delivery_requires"]),
                               "scope": "Fixed finite API outputs, selected upstream regressions and observed consumer API calls; not the full upstream suite"})
        return observation


def _regression_rows(task_id, execution):
    marker = "PROWORKSIM_UPSTREAM_TESTS:"
    lines = [line[len(marker):] for line in execution["output"].splitlines() if line.startswith(marker)]
    if not execution["driver_completed"] or execution["returncode"] != 0 or len(lines) != 1:
        return None
    try:
        rows = json.loads(lines[0])
        manifest, _ = source._entry(task_id)
        ids = manifest["selected_FAIL_TO_PASS"] + manifest["selected_PASS_TO_PASS"]
        if (isinstance(rows, list) and len(rows) == len(ids)
                and all(isinstance(row, dict) and row.get("test_id") == test_id and type(row.get("passed")) is bool
                        for row, test_id in zip(rows, ids, strict=True))):
            return rows
    except (ValueError, TypeError):
        pass
    return None


def build_software_collaboration_case(case, root):
    case = case_spec(case) if isinstance(case, str) else validate_case(copy.deepcopy(case))
    material = source.build_case(case["task_id"])
    bundle = {"files": material["files"], "included_patch_ids": []}
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json",
                "owner": "operator", "readers": [*MEMBERS, "operator"], "writers": ["operator"], "data": bundle}]
    objects.extend({"alias": member, "filename": member + ".json", "kind": "json", "owner": member,
                    "readers": [member, "operator"], "writers": [member], "data": copy.deepcopy(bundle)} for member in MEMBERS)
    package = {"project_id": PROJECT, "goal": "Repair the library and deliver its working consumer; choose responsibilities yourselves.",
               "participants": [*MEMBERS, "operator"], "objects": objects, "works": [], "grants": [],
               "provenance": {"kind": "synthetic", "note": "Pinned real upstream mutation; project-derived consumer contract."}}
    task = ("Collaborate on the public software requirements. Both members can implement, integrate and test. "
            "Choose among library_repair and consumer_export; claim_task is atomic. send_message permits negotiation. "
            "delegate_task notifies an available partner, who may return_task. staff_wait suspends until addressed work "
            "or a partner patch; staff_done permanently ends only your own opportunities. A published partner patch "
            "must be imported explicitly with integrate_patch. Resolve conflicts yourselves. write_file replaces the "
            "entire file; use replace_file for local edits. After your last edit, run_tests, publish a current fixed "
            "patch and submit_integration. Neither test completion nor a message is a fixed delivery.")
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"],
            "world": {"world_id": "software-collaboration-v029", "actors": {actor: {} for actor in (*MEMBERS, "operator")},
                      "applications": ["files"], "publication_policy": "explicit",
                      "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
            "installer": "operator", "projects": [{"package": package}],
            "roles": [{"role_id": member, "actor": member, "project": PROJECT, "policy": "model", "config": {"task": task}}
                      for member in MEMBERS], "setup": [], "events": [], "start": {"kind": "initial"},
            "boundary": {"max_opportunities": sum(case["role_decision_limits"].values()) + len(MEMBERS)}}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    with world.store.lock():
        world.state = world.store.load()
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {
            "case": case, "tasks": {key: {"task_id": key, "description": value, "owner": None, "depends_on": []}
                                    for key, value in material["task_definitions"].items()}, "patches": {}, "deliveries": []}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": case["purpose"], "preparation_credit": False,
              "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
              "source_contract": copy.deepcopy(case["source_contract"]), "training_eligible": case["training_eligible"],
              "actor_trajectories_created": False}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": case["training_eligible"],
                                 "independent_assessment": "assess_software_collaboration"}, prefix)
    prepared.port_factory = SoftwareCollaborationPort
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def software_collaboration_facts(prepared_or_state):
    facts = base.software_collaboration_facts(prepared_or_state)
    facts["version"] = VERSION
    return facts


# No expected outputs cross this boundary. The tracer captures only calls to the
# actual API code objects imported from the same immutable delivery tree, while
# its public consumer function is on stack. It does not replace these APIs.
CONSUMER_CALL_DRIVER = r'''
import json
import sys
_emit = json.dumps
if TASK_ID == 'sqlparse-comparison-records':
    import sqlparse
    from sqlparse.sql import Comparison
    targets = {'sqlparse.parse': sqlparse.parse, 'Comparison.left': Comparison.left.fget,
               'Comparison.right': Comparison.right.fget}
    import consumer
    invoke = consumer.comparison_records
elif TASK_ID == 'schema-catalog':
    from schema import Schema
    targets = {'Schema.__init__': Schema.__init__, 'Schema.description': Schema.description.fget,
               'Schema.json_schema': Schema.json_schema}
    import consumer
    invoke = consumer.schema_catalog
else:
    from textfsm import TextFSM
    from textfsm.parser import TextFSMOptions
    targets = {'TextFSM.__init__': TextFSM.__init__, 'TextFSM.ParseText': TextFSM.ParseText,
               'TextFSMOptions.List.OnSaveRecord': TextFSMOptions.List.OnSaveRecord}
    import consumer
    invoke = consumer.record_items
codes = {fn.__code__: name for name, fn in targets.items()}
consumer_code = invoke.__code__
rows = []
for request in PROBE_REQUESTS:
    counts = {name: 0 for name in targets}
    def record(frame, event, arg):
        if event == 'call' and frame.f_code in codes:
            caller = frame.f_back
            while caller is not None and caller.f_code is not consumer_code:
                caller = caller.f_back
            if caller is not None:
                counts[codes[frame.f_code]] += 1
    sys.setprofile(record)
    try:
        observation = {'kind': 'return', 'value': invoke(request['value'])}
    except Exception as error:
        observation = {'kind': 'exception', 'type': type(error).__module__ + '.' + type(error).__name__, 'text': str(error)}
    finally:
        sys.setprofile(None)
    rows.append({'case_id': request['case_id'], 'calls': counts, 'observed': observation})
print('PROWORKSIM_CONSUMER_CALLS:' + _emit(rows, sort_keys=True, allow_nan=False))
'''


def observe_consumer_api(task_id, files, *, run_root):
    """Check actual consumer-stack API calls and outputs for fixed nonempty inputs."""
    _, directory = source._entry(task_id)
    raw = (directory / "acceptance.json").read_bytes()
    material = source.build_case(task_id)
    contract = _source_contract(task_id, material)
    if digest(raw) != contract["acceptance_fixture_sha256"]:
        raise ValueError("Frozen independent fixture changed")
    cases = [row for row in json.loads(raw)["cases"] if row["group"] == "consumer" and row["request"]["value"]]
    requests = [{"case_id": row["case_id"], "value": copy.deepcopy(row["request"]["value"])} for row in cases]
    code = "TASK_ID = " + repr(task_id) + "\nPROBE_REQUESTS = " + repr(requests) + "\n" + CONSUMER_CALL_DRIVER
    execution = run_isolated(files, code, run_root=run_root)
    marker = "PROWORKSIM_CONSUMER_CALLS:"
    lines = [line[len(marker):] for line in execution["output"].splitlines() if line.startswith(marker)]
    rows = None
    if execution["driver_completed"] and execution["returncode"] == 0 and len(lines) == 1:
        try:
            parsed = json.loads(lines[0])
            if (isinstance(parsed, list) and len(parsed) == len(cases)
                    and all(isinstance(row, dict) and row.get("case_id") == case["case_id"]
                            for row, case in zip(parsed, cases, strict=True))):
                rows = parsed
        except (ValueError, TypeError):
            pass
    required = {
        CASE_IDS[0]: ["sqlparse.parse", "Comparison.left", "Comparison.right"],
        CASE_IDS[1]: ["Schema.__init__", "Schema.description", "Schema.json_schema"],
        CASE_IDS[2]: ["TextFSM.__init__", "TextFSM.ParseText", "TextFSMOptions.List.OnSaveRecord"],
    }[task_id]
    checks = []
    for index, case in enumerate(cases):
        row = rows[index] if rows is not None else {}
        calls = row.get("calls", {})
        observed = row.get("observed")
        called = isinstance(calls, dict) and all(type(calls.get(name)) is int and calls[name] > 0 for name in required)
        checks.append({"case_id": case["case_id"], "calls": calls, "required_apis": required,
                       "observed": observed, "api_calls_observed": called,
                       "passed": called and observed is not None and _matches(observed, case["expected"])})
    return {"version": CONTRACT_VERSION, "task_id": task_id, "passed": bool(checks) and all(row["passed"] for row in checks),
            "checks": checks, "execution": execution, "expected_values_sent_to_worker": False,
            "driver_sha256": digest(CONSUMER_CALL_DRIVER.encode()),
            "scope": contract["probe_scope"]}


def assess_files(task_id, files, *, run_root):
    """Conjunction of independent API, pinned regressions and consumer API use."""
    root = Path(run_root)
    api = source.assess(task_id, files, run_root=root / "api")
    regression = source.run_public_tests(task_id, files, run_root=root / "regression")
    calls = observe_consumer_api(task_id, files, run_root=root / "consumer-api-calls")
    executed = all(row["execution"]["executed"] for row in (api, regression, calls))
    api["executed"] = api["execution"]["executed"]
    components = {"independent_source_and_consumer_api": api["passed"],
                  "selected_upstream_regressions": regression["passed"], "consumer_api_calls_observed": calls["passed"]}
    return {"version": CONTRACT_VERSION, "task_id": task_id, "executed": executed,
            "passed": executed and all(components.values()), "components": components,
            "independent_acceptance": {
                "version": CONTRACT_VERSION, "executed": executed,
                "passed": executed and all(components.values()), "components": components,
                "scope": "finite_conjunctive_contract_not_single_api_boolean"},
            "api_acceptance": api, "regression_acceptance": regression,
            "consumer_api_observation": calls, "scope": "finite_conjunctive_contract_not_official_full_suite"}


def assess_software_collaboration(prepared, *, run_root):
    """Judge the latest immutable delivery, preserving failures and unknowns."""
    case = validate_case(prepared.case)
    world = prepared.world
    world.state = world.store.load()
    facts = software_collaboration_facts(world.state)
    common = {"version": VERSION, "usage": case["purpose"], "purpose": case["purpose"],
              "training_eligible": case["training_eligible"],
              "independent_confirmation_eligible": case["independent_confirmation_eligible"],
              "contract_version": CONTRACT_VERSION, "source_contract": copy.deepcopy(case["source_contract"])}
    if not facts["deliveries"]:
        return {**common, "status": "evaluable", "R": 0, "submitted": False, "reason": "No fixed integrated delivery"}
    delivery = facts["deliveries"][-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = assess_files(case["task_id"], bundle["files"], run_root=run_root)
    for key in ("independent_acceptance", "api_acceptance", "regression_acceptance", "consumer_api_observation"):
        result[key]["source_reference"] = copy.deepcopy(delivery["source_reference"])
        result[key]["files_sha256"] = delivery["files_sha256"]
    return {**common, **result, "version": VERSION, "status": "evaluable" if result["executed"] else "unknown",
            "R": int(result["passed"]) if result["executed"] else None, "submitted": True, "delivery": delivery}
