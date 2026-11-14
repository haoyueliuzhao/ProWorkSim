"""Two new, low-domain-load development roots on one pinned real library.

New contracts do not revise old scores or create a second independent repository.
Reference programs are controller-only satisfiability witnesses, never prompts or
current-policy support. All executions use the established finite CPU sandbox.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from . import software_tasks_v030 as pinned
from .software_sandbox import run_isolated
from .storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "examples/software-sources-v034"
VERSION = "software-tasks-v0.34"
PURPOSE = "model_interface_development"
TASK_IDS = ("mm-directory-rootgoal-v034", "mm-name-index-rootgoal-v034")
NAMES = dict.fromkeys(TASK_IDS, "marshmallow")
MARKER = "PROWORKSIM_NEW_ROOT_OBSERVATIONS:"
PUBLIC_MARKER = "PROWORKSIM_NEW_ROOT_PUBLIC:"
PUBLIC_FEEDBACK_VERSION = "structured-public-test-feedback-v0.34"


def _entry(task_id):
    if task_id not in TASK_IDS:
        raise ValueError("Only the two frozen new development roots are admitted")
    manifest = json.loads((ASSETS / "source-manifest.json").read_text())
    row = next(row for row in manifest["cases"] if row["task_id"] == task_id)
    if row["purpose"] != PURPOSE or row["training_eligible"] is not False:
        raise ValueError("P1 development sources cannot be promoted to training")
    original = json.loads((pinned.ASSETS / "source-manifest.json").read_text())
    if manifest["source"] != original["source"]:
        raise ValueError("The actual pinned library asset changed")
    return manifest, row, ASSETS / task_id


def _asset(row, directory, name):
    raw = (directory / name).read_bytes()
    if digest(raw) != row["files_sha256"][name]:
        raise ValueError("Frozen v034 source asset changed: " + name)
    return raw.decode()


API_DRIVER = r'''
import copy
import importlib
import json

def exact_json_equal(left, right):
    return json.dumps(left, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(right, sort_keys=True, ensure_ascii=False, allow_nan=False)

def invoke(request):
    calls, restored, effects = {}, [], []
    try:
        for module_name, class_name, method_name in request.get('trace', []):
            cls = getattr(importlib.import_module(module_name), class_name)
            original = getattr(cls, method_name)
            key = '.'.join((module_name, class_name, method_name))
            calls[key] = 0
            def traced(self, *args, _original=original, _key=key, **kwargs):
                calls[_key] += 1
                try:
                    value = _original(self, *args, **kwargs)
                except Exception as error:
                    effects.append({'api': _key, 'returned': False, 'exception': type(error).__name__})
                    raise
                effects.append({'api': _key, 'returned': True, 'value': copy.deepcopy(value)})
                return value
            restored.append((cls, method_name, cls.__dict__.get(method_name)))
            setattr(cls, method_name, traced)
        arguments = copy.deepcopy(request.get('args', []))
        before = copy.deepcopy(arguments)
        try:
            target = importlib.import_module(request['module'])
            if request.get('class'):
                target = getattr(target, request['class'])()
            value = getattr(target, request['function'])(*arguments, **request.get('kwargs', {}))
            result = {'kind': 'return', 'value': value}
        except Exception as error:
            result = {'kind': 'exception', 'type': type(error).__module__ + '.' + type(error).__name__, 'text': str(error)}
        if calls:
            result['source_api_used'] = {key: count > 0 for key, count in calls.items()}
            result['source_api_observation_complete'] = True
            result['source_api_trace'] = effects
        if request.get('check_input_unchanged'):
            result['input_unchanged'] = exact_json_equal(arguments, before)
        return result
    finally:
        for cls, name, local in reversed(restored):
            if local is None:
                delattr(cls, name)
            else:
                setattr(cls, name, local)

OBSERVATIONS = []
for request in REQUESTS:
    try:
        OBSERVATIONS.append(invoke(request))
    except Exception as error:
        # Setup failure did not establish a complete API observation. No false
        # map is invented: the assessor reports completeness separately.
        OBSERVATIONS.append({'kind': 'exception', 'type': type(error).__module__ + '.' + type(error).__name__, 'text': str(error)})
'''


def exact_json_equal(left, right):
    """Preserve JSON scalar types, including integer versus float or Boolean."""
    return json.dumps(left, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(right, sort_keys=True, ensure_ascii=False, allow_nan=False)


def comparable(observation):
    return {key: value for key, value in observation.items() if key != "source_api_trace"} if isinstance(observation, dict) else observation


def _public_driver(task_id):
    _, row, directory = _entry(task_id)
    cases = json.loads(_asset(row, directory, "public-checks.json"))["cases"]
    return (pinned._upstream_driver() + "REQUESTS = " + repr([item["request"] for item in cases]) + "\n" + API_DRIVER
        + "\nPUBLIC_EXPECTED = " + repr(cases)
        + "\nfor case, observation in zip(PUBLIC_EXPECTED, OBSERVATIONS):\n"
          "    compared = {key: value for key, value in observation.items() if key != 'source_api_trace'}\n"
          "    UPSTREAM_RESULTS.append({'test_id': case['case_id'], 'group': 'public_normal', 'requirement_group': case['group'], 'passed': exact_json_equal(compared, case['expected']), 'observed': observation, 'expected': case['expected']})\n"
          "print(" + repr(PUBLIC_MARKER) + " + json.dumps(UPSTREAM_RESULTS, sort_keys=True, allow_nan=False))\n")


def build_case(task_id):
    manifest, row, directory = _entry(task_id)
    files = pinned.original_files()
    files.update({name: _asset(row, directory, "starter/" + name) for name in row["editable_paths"]})
    contract = _asset(row, directory, "contract.md")
    files.update({"contract.md": contract, "test_visible.py": _public_driver(task_id),
                  "test_member.py": "# Member-authored exploratory checks may be added here.\n"})
    return {"version": VERSION, "task_id": task_id, "purpose": PURPOSE, "training_eligible": False,
        "category": "o1_root_goal", "files": files, "editable_paths": sorted([*row["editable_paths"], "test_member.py"]),
        "root_goal": contract, "task_definitions": {}, "initial_owners": {},
        "source_contract": {"source_asset_ids": [manifest["source"]["asset_id"]],
            "source_revision": manifest["source"]["commit"],
            "source_manifest_sha256": digest((ASSETS / "source-manifest.json").read_bytes()),
            "requirements_sha256": row["files_sha256"]["contract.md"],
            "public_checks_sha256": row["files_sha256"]["public-checks.json"],
            "independent_verifier_sha256": row["files_sha256"]["acceptance.json"],
            "complete_delivery_requires": row["complete_delivery_requires"], "public_requirements": contract,
            "new_contract_same_pinned_library": True, "independent_repository_count": 1,
            "category": "o1_root_goal", "forced_initial_failure_feedback": False},
        "source_partition_sha256": digest(json_bytes(manifest["source_partition"]))}


def _validate_files(task_id, files):
    case = build_case(task_id)
    if set(files) != set(case["files"]) or any(files[name] != text for name, text in case["files"].items()
                                             if name not in case["editable_paths"]):
        raise ValueError("Only the frozen editable application files may change")


def reference_solution(task_id):
    _, row, directory = _entry(task_id)
    files = build_case(task_id)["files"]
    files.update({name: _asset(row, directory, "reference/" + name) for name in row["editable_paths"]})
    return files


def dependency_controls(task_id):
    """Four actual programs; neither unchanged side is replaced by a stub."""
    _, row, _ = _entry(task_id)
    initial, joint = build_case(task_id)["files"], reference_solution(task_id)
    shared, consumer = copy.deepcopy(initial), copy.deepcopy(initial)
    for name in row["shared_api_paths"]:
        shared[name] = joint[name]
    for name in row["consumer_paths"]:
        consumer[name] = joint[name]
    return {"original": initial, "shared_api_only": shared, "consumer_only": consumer, "joint_reference": joint}


def run_public_tests(task_id, files, *, run_root):
    _validate_files(task_id, files)
    execution = run_isolated(files, _public_driver(task_id), run_root=run_root)
    tests = pinned._decode(execution, PUBLIC_MARKER)
    manifest, row, directory = _entry(task_id)
    expected = [name + "::" + function for name, functions in manifest["source"]["selected_tests"].items() for function in functions]
    expected += [item["case_id"] for item in json.loads(_asset(row, directory, "public-checks.json"))["cases"]]
    if not isinstance(tests, list) or [item.get("test_id") for item in tests] != expected or any(type(item.get("passed")) is not bool for item in tests):
        tests = None
    groups = {}
    for name in ("upstream_regressions", "public_normal"):
        selected = [item for item in tests or [] if item["group"] == name]
        passed = tests is not None and bool(selected) and all(item["passed"] for item in selected)
        groups[name] = {"executed": tests is not None, "passed": passed, "tests": selected,
                        "status": "passed" if passed else "failed" if tests is not None else "untested"}
    return {"execution": execution, "tests": tests, "groups": groups,
            "passed": tests is not None and all(item["passed"] for item in tests),
            "authority": "new_public_semantics_and_same_pinned_upstream_subset_not_independent_acceptance"}


def _execution_summary(execution):
    """Keep execution facts and the first explicit exception, not raw stdout."""
    summary = {key: copy.deepcopy(execution[key]) for key in (
        "executed", "driver_completed", "returncode", "timeout", "error", "reason") if key in execution}
    output = execution.get("output", "")
    if isinstance(output, str):
        summary.update(raw_output_sha256=digest(output.encode()), raw_output_bytes=len(output.encode()))
        if not execution.get("driver_completed") or execution.get("returncode") not in (None, 0):
            exceptions = [(index, line) for index, line in enumerate(output.splitlines(), 1)
                          if line.split(":", 1)[0].endswith(("Error", "Exception", "Exit", "Interrupt"))]
            if exceptions:
                index, line = exceptions[0]
                summary["first_exception"] = {"raw_output_line": index, "text": line}
    return summary


def project_public_test_feedback(result):
    """Pure new-Gamma presentation of one complete raw world run_tests result.

    Input is response.result, not the outer WorldCore response. Passed values
    and detailed API traces remain only in the original archived test event.
    This is a deliberately smaller information presentation, not lossless
    duplicate removal; failed business observations are preserved in full.
    """
    if result.get("feedback_presentation", {}).get("version") == PUBLIC_FEEDBACK_VERSION:
        return copy.deepcopy(result)
    projected = {key: copy.deepcopy(value) for key, value in result.items() if key not in {"groups", "public_execution"}}
    groups = {}
    for name, group in result["groups"].items():
        if name == "member_tests":
            selected = copy.deepcopy(group)
            selected["counts"] = {"reported": int(group["executed"]), "passed": int(group["passed"] is True),
                                  "failed": int(group["passed"] is False)}
            selected["counting_scope"] = "member_script_execution"
            groups[name] = selected
            continue
        selected = {key: copy.deepcopy(group[key]) for key in ("status", "executed", "passed")}
        tests = group.get("tests")
        if isinstance(tests, list):
            selected["counts"] = {"reported": len(tests), "passed": sum(row.get("passed") is True for row in tests),
                                  "failed": sum(row.get("passed") is False for row in tests)}
            selected["tests"] = []
            for row in tests:
                shown = {"test_id": row["test_id"], "requirement_group": row.get("requirement_group", row.get("group", name)),
                         "status": "passed" if row.get("passed") is True else "failed"}
                if row.get("passed") is not True:
                    for key in ("expected", "observed"):
                        if key in row:
                            shown[key] = copy.deepcopy(comparable(row[key]))
                    for key in ("type", "text"):
                        if key in row:
                            shown[key] = copy.deepcopy(row[key])
                    observed = row.get("observed")
                    if isinstance(observed, dict) and observed.get("kind") == "exception":
                        shown["first_exception"] = {key: observed[key] for key in ("type", "text") if key in observed}
                    expected_api = row.get("expected", {}).get("source_api_used")
                    if expected_api:
                        api = observed.get("source_api_used") if isinstance(observed, dict) else None
                        complete = (isinstance(observed, dict) and observed.get("source_api_observation_complete") is True
                                    and isinstance(api, dict) and set(api) == set(expected_api)
                                    and all(type(value) is bool for value in api.values()))
                        shown["process_observation_complete"] = complete
                        shown["required_process_satisfied"] = complete and api == expected_api
                selected["tests"].append(shown)
        else:
            selected["counts"] = {"reported": int(group["executed"]), "passed": int(group["passed"] is True),
                                  "failed": int(group["passed"] is False)}
            selected["counting_scope"] = "member_script_execution" if name == "member_tests" else "reported_group_execution"
        if group.get("reason"):
            selected["reason"] = group["reason"]
        if group.get("execution") and group["passed"] is not True:
            selected["execution_failure"] = _execution_summary(group["execution"])
        groups[name] = selected
    projected["groups"] = groups
    public = result.get("public_execution", {})
    projected["public_execution"] = _execution_summary(public.get("execution", {}))
    projected["feedback_presentation"] = {"version": PUBLIC_FEEDBACK_VERSION,
        "raw_test_result_sha256": digest(json_bytes(result)), "raw_test_event_retained": True,
        "passed_item_fields": ["test_id", "requirement_group", "status"],
        "failed_business_observations_preserved": True, "public_detailed_api_trace_actor_visible": False,
        "scope": "New Gamma: group facts and passed-item summaries; full failed business observations and first exception. Full public-driver stdout, passed values and detailed API traces are retained in the original test event; member-authored test output remains visible."}
    return projected


def acceptance_dimensions(independent, public):
    checks = []
    for origin, rows in (("independent", independent.get("checks", [])), ("public", public.get("tests") or [])):
        for row in rows:
            expected, observed = row.get("expected"), row.get("observed")
            required = expected.get("source_api_used") if isinstance(expected, dict) else None
            complete = (isinstance(observed, dict) and observed.get("source_api_observation_complete") is True
                        and isinstance(observed.get("source_api_used"), dict)
                        and set(observed["source_api_used"]) == set(required)
                        and all(type(value) is bool for value in observed["source_api_used"].values())) if required else None
            def content(value):
                return {key: item for key, item in value.items() if key not in (
                    "source_api_used", "source_api_observation_complete", "source_api_trace")} if isinstance(value, dict) else value
            checks.append({"origin": origin, "id": row.get("case_id", row.get("test_id")),
                "content_correct": exact_json_equal(content(observed), content(expected)) if expected is not None else row.get("passed"),
                "required_process_satisfied": (complete and observed["source_api_used"] == required) if required else None,
                "process_observation_complete": complete,
                "process_interpretation": ("observed_api_use" if complete else "required_api_observation_missing_or_incomplete") if required else "not_required_for_this_check"})
    known = independent["execution"]["executed"] and public["execution"]["executed"] and bool(independent.get("checks")) and public.get("tests") is not None
    applicable = [row for row in checks if row["required_process_satisfied"] is not None]
    return {"content_correct": all(row["content_correct"] is True for row in checks) if known else None,
            "required_process_satisfied": all(row["required_process_satisfied"] for row in applicable) if known and applicable else None,
            "process_observation_complete": all(row["process_observation_complete"] for row in applicable) if known and applicable else None,
            "dimension_checks": checks,
            "content_scope": "All declared values, errors, ordering, duplicates, input preservation and public/upstream obligations remain; API use and observation completeness are separate evidence dimensions."}


def assess_files(task_id, files, *, run_root):
    _validate_files(task_id, files)
    _, row, directory = _entry(task_id)
    fixture = _asset(row, directory, "acceptance.json")
    cases = json.loads(fixture)["cases"]
    execution = run_isolated(files, "REQUESTS = " + repr([item["request"] for item in cases]) + "\n" + API_DRIVER
        + "\nprint(" + repr(MARKER) + " + json.dumps(OBSERVATIONS, sort_keys=True, allow_nan=False))\n", run_root=Path(run_root) / "independent")
    observed = pinned._decode(execution, MARKER)
    if not isinstance(observed, list) or len(observed) != len(cases):
        observed = None
    checks = [{"case_id": case["case_id"], "group": case["group"], "expected": case["expected"],
               "observed": observed[index] if observed is not None else None,
               "passed": observed is not None and exact_json_equal(comparable(observed[index]), case["expected"])} for index, case in enumerate(cases)]
    independent = {"version": VERSION, "task_id": task_id, "purpose": PURPOSE,
        "passed": all(item["passed"] for item in checks), "checks": checks, "execution": execution,
        "fixture_sha256": digest(fixture.encode()), "expected_values_sent_to_worker": False}
    public = run_public_tests(task_id, files, run_root=Path(run_root) / "public")
    executed = execution["executed"] and public["execution"]["executed"]
    components = {"independent_development_contract": independent["passed"], "public_upstream_and_semantics": public["passed"]}
    return {"version": VERSION, "task_id": task_id, "executed": executed, "passed": executed and all(components.values()),
            "components": components, "independent_acceptance": independent, "public_acceptance": public,
            **acceptance_dimensions(independent, public),
            "scope": "Frozen new complete contract; no old task, result, field or requirement is regraded."}
