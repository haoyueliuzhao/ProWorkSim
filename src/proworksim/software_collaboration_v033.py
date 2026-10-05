"""Same-root single/team development worlds with matched public obligations.

Only organization differs: one actual private work copy in S, two in T. Public
business requirements, starting code, test inputs and independent acceptance
remain paired. The observer never supplies a decomposition or hidden answer.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from . import software_collaboration_v027 as base
from . import software_collaboration_v030 as previous
from . import software_tasks_v030 as source
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .software_sandbox import LIMITS as SANDBOX_LIMITS, run_isolated
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors
from .world_core import WorldCore

VERSION = "software-collaboration-v0.33"
INTERFACE_REVISION = "same-root-organization-v0.33"
CONTRACT_VERSION = "same-root-st-complete-work-v0.33"
PURPOSE = source.PURPOSE
PROJECT, MEMBERS = previous.PROJECT, previous.MEMBERS
ROOT_GOAL_ID = previous.ROOT_GOAL_ID
CASE_IDS = TASK_IDS = ("mm-ledger-rootgoal", "mm-settings-rootgoal")
CONDITIONS = ("S", "T")
SCHEDULER = "shared-budget-fair-event-wakeup-v0.33"
TEAM_LIMITS = {"max_decisions": 128, "max_attempts": 128, "max_total_tokens": 500000, "max_test_runs": 32}
NEUTRAL_REPLACEMENTS = {
    CASE_IDS[0]: ("Two members\nhave equal tools and the same goal; create the work decomposition and ownership\nyourselves.",
                  "Active executors have equal tools and the same goal; create the work decomposition\nand ownership yourselves."),
    CASE_IDS[1]: ("Two equal members\ncreate and revise their own execution tasks, responsibility, dependencies and\nintegration;",
                  "Active executors create and revise their own execution tasks, responsibility,\ndependencies and integration;"),
}
TOOLS = copy.deepcopy(previous.TOOLS)
for _tool in TOOLS:
    if _tool["name"] == "submit_integration":
        _tool["parameters"]["required"] = [key for key in _tool["parameters"]["required"] if key != "message"]
        _tool["description"] += " message is an optional human-readable note; omitting it changes no test, version or submission requirement."
    elif _tool["name"] == "run_tests":
        _tool["description"] += " The whole episode, across all active executors, permits at most 32 actual test runs."


def material(case_id):
    if case_id not in CASE_IDS:
        raise ValueError("Only the two original O1 root goals enter the paired diagnostic")
    value = source.build_case(case_id)
    before = value["files"]["contract.md"]
    old, new = NEUTRAL_REPLACEMENTS[case_id]
    if before.count(old) != 1:
        raise ValueError("The original organization-only sentence changed before neutralization")
    contract = before.replace(old, new, 1)
    value["files"]["contract.md"] = contract
    value["root_goal"] = contract
    original_contract = copy.deepcopy(value["source_contract"])
    value["source_contract"].update(
        public_requirements=contract, requirements_sha256=digest(contract.encode()),
        original_requirements_sha256=original_contract["requirements_sha256"],
        organization_text_revision={"before": old, "after": new,
                                    "scope": "Executor-count wording only; no business requirement or hidden input changes"})
    value["initial_binding"] = {"original_contract_sha256": digest(before.encode()),
        "paired_contract_sha256": digest(contract.encode()),
        "business_source_contract": original_contract,
        "initial_code_sha256": {name: digest(text.encode()) for name, text in value["files"].items() if name != "contract.md"},
        "initial_files_sha256": digest(json_bytes(value["files"])),
        "public_driver_sha256": digest(value["files"]["test_visible.py"].encode()),
        "independent_verifier_sha256": original_contract["independent_verifier_sha256"],
        "public_checks_sha256": original_contract["public_checks_sha256"]}
    return value


def case_spec(case_id=CASE_IDS[0], *, condition="S", first_member=None, role_decision_limits=None):
    if condition not in CONDITIONS:
        raise ValueError("Execution condition must be S or T")
    value = material(case_id)
    active = [MEMBERS[0]] if condition == "S" else list(MEMBERS)
    first = active[0] if first_member is None else first_member
    limits = dict.fromkeys(active, TEAM_LIMITS["max_decisions"])
    if first not in active or role_decision_limits is not None and role_decision_limits != limits:
        raise ValueError("Each active executor may use the entire remaining shared pool; no per-member split")
    return {"version": VERSION, "case_id": case_id, "task_id": case_id, "condition": condition,
        "family": source.NAMES[case_id], "task_type": "o1_root_goal", "category": "o1_root_goal",
        "purpose": PURPOSE, "usage": PURPOSE, "split": PURPOSE, "training_eligible": False,
        "independent_confirmation_eligible": False, "active_roles": active,
        "role_decision_limits": limits, "team_limits": copy.deepcopy(TEAM_LIMITS), "first_member": first,
        "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
        "organization_level": "single_same_root" if condition == "S" else "O1",
        "editable_paths": value["editable_paths"], "source_contract": value["source_contract"],
        "initial_binding": value["initial_binding"], "root_goal": value["root_goal"],
        "max_created_tasks": previous.MAX_CREATED_TASKS, "predefined_execution_tasks": False,
        "responsibility_scope": "Autonomous task formation; centralized completion, help and delegation are allowed, never required",
        "submission_requires": ["current_fixed_patch", "current_version_public_test_execution"],
        "public_feedback_protocol": "separate_upstream_public_normal_member_and_untested",
        "forced_initial_failure_feedback": False}


def validate_case(case):
    try:
        expected = case_spec(case["case_id"], condition=case["condition"], first_member=case["first_member"],
                             role_decision_limits=case["role_decision_limits"])
    except (KeyError, TypeError) as error:
        raise ValueError("Declare the exact same-root S/T case") from error
    if case != expected:
        raise ValueError("Paired case, public requirements or team resource limits changed")
    return case


def _validate_files(case_id, files):
    expected = material(case_id)
    if set(files) != set(expected["files"]) or any(files[name] != text for name, text in expected["files"].items()
                                                   if name not in expected["editable_paths"]):
        raise ValueError("Only the same declared editable business files may change")


def run_public_tests(case_id, files, *, run_root):
    """Execute the exact original public driver against the paired contract files."""
    _validate_files(case_id, files)
    execution = run_isolated(files, source._public_driver(case_id), run_root=run_root)
    tests = source._decode(execution, "PROWORKSIM_DEVELOPMENT_PUBLIC:")
    manifest, row, directory = source._entry(case_id)
    expected = [name + "::" + function for name, functions in manifest["source"]["selected_tests"].items() for function in functions]
    expected += [item["case_id"] for item in json.loads(source._asset(row, directory, "public-checks.json"))["cases"]]
    if not isinstance(tests, list) or [item.get("test_id") for item in tests] != expected or any(type(item.get("passed")) is not bool for item in tests):
        tests = None
    groups = {}
    for name in ("upstream_regressions", "public_normal"):
        selected = [item for item in tests or [] if item["group"] == name]
        passed = tests is not None and bool(selected) and all(item["passed"] for item in selected)
        groups[name] = {"executed": tests is not None, "passed": passed, "tests": selected,
                        "status": "passed" if passed else "failed" if tests is not None else "not_tested"}
    return {"execution": execution, "tests": tests, "groups": groups,
            "passed": tests is not None and all(item["passed"] for item in tests),
            "authority": "same_original_visible_regression_and_public_normal_feedback"}


def _public_feedback(case_id, files, *, run_root):
    result = run_public_tests(case_id, files, run_root=run_root)
    groups = {name: {**copy.deepcopy(group), "passed": group["passed"] if group["executed"] else None,
                     "status": group["status"] if group["executed"] else "untested"}
              for name, group in result["groups"].items()}
    return {"groups": groups, "public_execution": result,
            "passed": all(group["passed"] is True for group in groups.values()),
            "executed": all(group["executed"] for group in groups.values())}


class TestBudget:
    """Count physical test attempts outside transactional world rollback."""
    def __init__(self, output=None):
        self.output = Path(output) if output else None
        self.records = []

    def consume(self, actor):
        if len(self.records) >= TEAM_LIMITS["max_test_runs"]:
            raise ToolRejection("The shared episode limit of 32 real run_tests calls is exhausted",
                                code="team_test_budget_exhausted", category="capability_gap")
        self.records.append({"index": len(self.records) + 1, "actor_id": actor,
                             "scope": "One accepted run_tests invocation, including failed actual execution"})
        if self.output is not None:
            atomic_write(self.output, json_bytes(self.snapshot()))

    def snapshot(self):
        return {"limit": TEAM_LIMITS["max_test_runs"], "used": len(self.records),
                "remaining": TEAM_LIMITS["max_test_runs"] - len(self.records), "records": copy.deepcopy(self.records),
                "sandbox_limits_per_execution": copy.deepcopy(SANDBOX_LIMITS),
                "maximum_executions_per_run_tests": 2,
                "scope": "At most one original public driver and one optional member script per accepted call; controller final acceptance is separately recorded and identical for S/T"}


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if project_id != PROJECT or actor not in self._software()["case"]["active_roles"]:
            raise ValueError("Only this condition's active executors may use its interface")
        specs = {item["name"]: item for item in TOOLS}
        if tool not in specs:
            raise ToolRejection("Not in the public software interface", code="tool_not_enabled", category="capability_gap")
        errors = _schema_errors(specs[tool]["parameters"], arguments)
        for name, schema in specs[tool]["parameters"].get("properties", {}).items():
            value = arguments.get(name)
            if isinstance(value, str) and len(value) > schema.get("maxLength", len(value)):
                errors.append(name + " exceeds its declared text limit")
            if isinstance(value, list) and schema.get("uniqueItems") and all(isinstance(item, str) for item in value) and len(value) != len(set(value)):
                errors.append(name + " must contain distinct items")
        if errors:
            raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
        return WorldCore._tool_project_action(self, actor, project_id, tool, arguments, interface_profile)

    def _share_fixed(self, actor, reference):
        self.state["shares"].append({"project_id": PROJECT, **reference,
            "actor_ids": list(self._software()["case"]["active_roles"]), "shared_by": actor, "at": self.state["clock"]})

    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        self.test_budget.consume(actor)
        result = _public_feedback(self._software()["case"]["case_id"], bundle["files"],
                                  run_root=self.store.root / "software-execution/public")
        member = previous._member_test_feedback(bundle["files"], run_root=self.store.root / "software-execution/member")
        result["groups"]["member_tests"] = member
        result["passed"] = result["passed"] and member["passed"] is not False
        untested = [name for name, group in result["groups"].items() if group["status"] == "untested"]
        result.update(source_reference=base._reference(artifact, version), source_sha256=digest(json_bytes(bundle)),
            files_sha256=digest(json_bytes(bundle["files"])), suite="same-original-public-and-member-v0.33",
            untested=untested + ["independent_acceptance", "full_upstream_suite"],
            scope="Same public drivers and sandbox limits for S/T; no independent acceptance during work",
            independent_acceptance="not_run_by_public_tool", fixed_submission_is_acceptance=False,
            team_test_budget=self.test_budget.snapshot())
        self._event(actor, "test", **result)
        return result

    def _action_submit_integration(self, actor, project_id, message=""):
        return super()._action_submit_integration(actor, project_id, message)


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        world = self._session._world
        case = world._software()["case"]
        value.update(interface_revision=INTERFACE_REVISION, execution_condition={
            "condition": case["condition"], "active_executors": list(case["active_roles"]),
            "private_working_copies": len(case["active_roles"]), "same_actor_shared_across_sessions": True,
            "centralized_completion_allowed": True, "preassigned_tasks_or_manager": False},
            shared_resource_limits=copy.deepcopy(TEAM_LIMITS),
            team_test_budget={key: world.test_budget.snapshot()[key] for key in ("limit", "used", "remaining")})
        value["scheduling"]["protocol"] = SCHEDULER
        callback = getattr(world, "model_budget_snapshot", None)
        if callback is not None:
            snapshot = callback()
            value["team_model_budget"] = {key: snapshot[key] for key in (
                "limits", "decisions", "attempts", "charged_tokens", "held_tokens", "remaining_decisions",
                "remaining_attempts", "available_tokens", "state_sha256")}
        return value


def build_software_collaboration_case(case, root):
    case = case_spec(case) if isinstance(case, str) else validate_case(copy.deepcopy(case))
    source_material = material(case["case_id"])
    bundle = {"files": source_material["files"], "included_patch_ids": []}
    active = case["active_roles"]
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
                "readers": [*active, "operator"], "writers": ["operator"], "data": bundle}]
    objects.extend({"alias": member, "filename": member + ".json", "kind": "json", "owner": member,
                    "readers": [member, "operator"], "writers": [member], "data": copy.deepcopy(bundle)} for member in active)
    instruction = (
        "Complete the immutable public root contract. There are no predefined execution tasks or manager. "
        "Create/revise your own tasks and claim responsibility as useful; centralized completion and mutual help are both allowed. "
        "Your execution_condition says whether one or two executors are active. All active sessions share one frozen model and ONE "
        "episode budget: 128 decisions, 128 generation attempts, 500000 actual tokens and 32 real run_tests calls in total. "
        "There is no 64-decision per-person allocation; any runnable executor may use the remaining pool. "
        "In T your files are private until published as fixed patches; integrate_patch explicitly imports a partner patch. "
        "In S there is one working copy and the full union of initially legal T business information. "
        "No reference solution or independent acceptance input is visible. Use the actual public API and complete all public requirements. "
        "write_file replaces the entire file; replace_file edits one exact match. run_tests reports the same public upstream/normal groups "
        "and optional member script. After the last edit, run_tests, publish a current fixed patch, then actively submit_integration. "
        "submit message is optional commentary; current-version tests and the fixed patch are still required. "
        "A submission is not an acceptance result. Ordinary schema/format rejection consumes an opportunity and returns feedback; "
        "it has no separate two/four-error retirement limit. staff_wait suspends until reachable addressed work or a partner patch; "
        "there is no external async producer. staff_done ends only your own opportunities. No action is automatically completed for you.")
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*active, "operator"],
        "objects": objects, "works": [], "grants": [],
        "provenance": {"kind": "synthetic", "note": "Same two public O1 business roots, paired organization condition, no predetermined decomposition."}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-" + case["condition"],
        "world": {"world_id": "software-collaboration-v033", "actors": {actor: {} for actor in (*active, "operator")},
                  "applications": ["files"], "publication_policy": "explicit",
                  "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
        "installer": "operator", "projects": [{"package": package}],
        "roles": [{"role_id": member, "actor": member, "project": PROJECT, "policy": "model", "config": {"task": instruction}}
                  for member in active], "setup": [], "events": [], "start": {"kind": "initial"},
        "boundary": {"max_opportunities": TEAM_LIMITS["max_decisions"] + len(active)}}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    world.test_budget = TestBudget(root / "team-test-budget.json")
    with world.store.lock():
        world.state = world.store.load()
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {"case": case, "tasks": {}, "patches": {}, "deliveries": [], "initial_public_feedback": None}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": PURPOSE, "preparation_credit": False,
        "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "source_contract": case["source_contract"], "initial_binding": case["initial_binding"],
        "condition": case["condition"], "actual_work_copy_count": len(active), "training_eligible": False,
        "actor_trajectories_created": False, "predefined_execution_tasks": False, "forced_initial_public_test": False}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": False,
        "independent_assessment": "assess_software_collaboration"}, prefix)
    prepared.port_factory = SoftwareCollaborationPort
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def initial_information(prepared):
    """Normalize only explicit actor/topology identifiers in actual legal views."""
    result = {}
    for member in prepared.case["active_roles"]:
        view = SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member).observe()
        _, _, bundle = prepared.world._bundle(member)
        normalized = copy.deepcopy(view)
        for key in ("role", "profile", "world_id", "instance_id", "branch_id", "actor_id",
                    "workspace_reference", "member_availability", "execution_condition"):
            normalized.pop(key, None)
        normalized["task_formation"].pop("level", None)
        normalized["scheduling"].pop("first_member", None)
        if "team_model_budget" in normalized:
            normalized["team_model_budget"].pop("state_sha256", None)
        result[member] = {"normalized_legal_observation": normalized,
            "readable_files_sha256": {name: digest(text.encode()) for name, text in sorted(bundle["files"].items())}}
    return result


def prove_initial_pair(single, team):
    if (single.case["condition"] != "S" or team.case["condition"] != "T"
            or single.case["case_id"] != team.case["case_id"] or single.case["initial_binding"] != team.case["initial_binding"]):
        raise ValueError("Initial information proof requires the same source root under actual S and T worlds")
    s, t = initial_information(single), initial_information(team)
    if set(s) != {"member_a"} or set(t) != set(MEMBERS) or any(value != s["member_a"] for value in t.values()):
        raise ValueError("Single executor must receive the union of the actual team's legal initial business information")
    return {"case_id": single.case["case_id"], "single_views": s, "team_views": t,
            "single_business_information_equals_team_union": True,
            "single_actual_work_copies": 1, "team_actual_work_copies": 2,
            "initial_binding": single.case["initial_binding"],
            "identity_projection": "Actor IDs, own version references, active-member topology and scheduling metadata are organization differences; business payload and every readable file byte are equal.",
            "scope": "Actual authorized initial observations and own readable file hashes only; no controller solution or hidden acceptance inputs"}


def software_collaboration_facts(prepared_or_state):
    value = base.software_collaboration_facts(prepared_or_state)
    value["version"] = VERSION
    return value


def acceptance_dimensions(independent, public):
    """Separate only the verifier's explicit top-level API trace from content."""
    checks = []
    for origin, rows in (("independent", independent.get("checks", [])), ("public", public.get("tests") or [])):
        for row in rows:
            if "expected" not in row:
                checks.append({"origin": origin, "id": row.get("test_id", row.get("case_id")),
                               "content_correct": row.get("passed"), "required_process_satisfied": None})
                continue
            expected, observed = row["expected"], row.get("observed")
            def content(value):
                return {key: item for key, item in value.items() if key != "source_api_used"} if isinstance(value, dict) else value
            process = (observed.get("source_api_used") == expected["source_api_used"]
                       if isinstance(observed, dict) else False) if "source_api_used" in expected else None
            checks.append({"origin": origin, "id": row.get("test_id", row.get("case_id")),
                           "content_correct": content(observed) == content(expected), "required_process_satisfied": process})
    executed = independent["execution"]["executed"] and public["execution"]["executed"]
    known = executed and bool(independent.get("checks")) and public.get("tests") is not None
    processes = [row["required_process_satisfied"] for row in checks if row["required_process_satisfied"] is not None]
    return {"content_correct": all(row["content_correct"] is True for row in checks) if known else None,
            "required_process_satisfied": all(processes) if known and processes else None,
            "dimension_checks": checks, "content_scope": "Every original expected value, exception, input-preservation and public/upstream obligation remains; only the explicitly measured top-level source_api_used map is reported separately."}


def assess_files(case_id, files, *, run_root):
    _validate_files(case_id, files)
    root = Path(run_root)
    _, row, directory = source._entry(case_id)
    fixture = source._asset(row, directory, "acceptance.json")
    cases = json.loads(fixture)["cases"]
    requests = [copy.deepcopy(item["request"]) for item in cases]
    execution = run_isolated(files, "REQUESTS = " + repr(requests) + "\n" + source.API_DRIVER
        + "\nprint(" + repr(source.MARKER) + " + json.dumps(OBSERVATIONS, sort_keys=True, allow_nan=False))\n", run_root=root / "independent")
    observations = source._decode(execution, source.MARKER)
    if not isinstance(observations, list) or len(observations) != len(cases):
        observations = None
    checks = [{"case_id": item["case_id"], "group": item["group"],
        "passed": observations is not None and observations[index] == item["expected"],
        "expected": item["expected"], "observed": observations[index] if observations is not None else None}
        for index, item in enumerate(cases)]
    independent = {"version": source.VERSION, "task_id": case_id, "purpose": PURPOSE,
        "passed": all(item["passed"] for item in checks), "checks": checks, "execution": execution,
        "fixture_sha256": digest(fixture.encode()), "expected_values_sent_to_worker": False}
    public = run_public_tests(case_id, files, run_root=root / "public")
    executed = execution["executed"] and public["execution"]["executed"]
    components = {"independent_development_contract": independent["passed"], "public_upstream_and_normal_cases": public["passed"]}
    return {"version": CONTRACT_VERSION, "task_id": case_id, "executed": executed,
            "passed": executed and all(components.values()), "components": components,
            "independent_acceptance": independent, "public_acceptance": public,
            **acceptance_dimensions(independent, public),
            "scope": "Unchanged original independent/public acceptance conjunction, with content and required API observations separately reported"}


def assess_software_collaboration(prepared, *, run_root):
    case = validate_case(prepared.case)
    world = prepared.world
    world.state = world.store.load()
    facts = software_collaboration_facts(world.state)
    common = {"version": VERSION, "usage": PURPOSE, "purpose": PURPOSE, "training_eligible": False,
        "independent_confirmation_eligible": False, "contract_version": CONTRACT_VERSION,
        "source_contract": case["source_contract"], "condition": case["condition"]}
    if not facts["deliveries"]:
        return {**common, "status": "evaluable", "R": 0, "submitted": False, "complete_delivery": False,
                "content_correct": None, "required_process_satisfied": None,
                "reason": "No fixed integrated delivery; no hidden assessment of an unsubmitted mutable workspace"}
    delivery = facts["deliveries"][-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = assess_files(case["case_id"], bundle["files"], run_root=run_root)
    result.update(source_reference=delivery["source_reference"], files_sha256=delivery["files_sha256"])
    return {**common, **result, "version": VERSION, "status": "evaluable" if result["executed"] else "unknown",
            "R": int(result["passed"]) if result["executed"] else None,
            "complete_delivery": result["passed"] if result["executed"] else None,
            "submitted": True, "delivery": delivery}
