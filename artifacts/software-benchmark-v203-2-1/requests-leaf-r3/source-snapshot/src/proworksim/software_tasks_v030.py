"""Bounded model/interface development cases; never allocation experience.

Six project-authored contracts use one already pinned, MIT-licensed source.
This is not an upstream benchmark score or evidence of repository diversity.
Public examples and independent acceptance requests are separate frozen assets.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

from .software_sandbox import run_isolated
from .software_sources_v027 import MEMBER_CAPABILITIES

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "examples/software-sources-v030"
VERSION = "software-tasks-v0.30"
PURPOSE = "model_interface_development"
TASK_IDS = (
    "mm-nested-order-import", "mm-event-projection", "mm-envelope-hook-repair",
    "mm-nested-error-repair", "mm-ledger-rootgoal", "mm-settings-rootgoal",
)
NAMES = dict.fromkeys(TASK_IDS, "marshmallow")
MARKER = "PROWORKSIM_DEVELOPMENT_OBSERVATIONS:"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(path):
    return json.loads(path.read_text())


def _entry(task_id):
    if task_id not in TASK_IDS:
        raise ValueError("Unknown model/interface development case")
    manifest = _json(ASSETS / "source-manifest.json")
    row = next(row for row in manifest["cases"] if row["task_id"] == task_id)
    if row["purpose"] != PURPOSE or row["training_eligible"]:
        raise ValueError("Development cases cannot become policy experience")
    return manifest, row, ASSETS / task_id


def _asset(row, directory, name):
    raw = (directory / name).read_bytes()
    if _sha(raw) != row["files_sha256"][name]:
        raise ValueError("Frozen development asset changed: " + name)
    return raw.decode()


def original_files():
    """Reuse original bytes from the existing interface-development lineage."""
    manifest = _json(ASSETS / "source-manifest.json")
    source = manifest["source"]
    directory = ROOT / source["source_relative_path"]
    files = {}
    for name, digest in source["files_sha256"].items():
        raw = (directory / name).read_bytes()
        if _sha(raw) != digest:
            raise ValueError("Pinned upstream source changed: " + name)
        files[name] = raw.decode()
    return files


def _upstream_driver():
    """Execute five exact original, fixture-free upstream test functions."""
    manifest = _json(ASSETS / "source-manifest.json")
    source = manifest["source"]
    directory = ROOT / source["source_relative_path"]
    definitions = ["from typing import NamedTuple", "import itertools",
                   "from marshmallow import Schema, fields, post_load"]
    ids = []
    for name, digest in source["regression_files_sha256"].items():
        raw = (directory / name).read_bytes()
        if _sha(raw) != digest:
            raise ValueError("Pinned upstream test changed: " + name)
        text = raw.decode()
        tree = ast.parse(text)
        selected = source["selected_tests"][name]
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "Point":
                definitions.append(ast.get_source_segment(text, node))
        for function in selected:
            node = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == function)
            if node.args.args or node.decorator_list:
                raise ValueError("Only fixture-free undecorated regressions admitted")
            definitions.append(ast.get_source_segment(text, node))
            ids.append((name + "::" + function, function))
    definitions.append("UPSTREAM_RESULTS = []")
    definitions.append("for test_id, function in " + repr(ids) + ":\n"
                       "    try:\n"
                       "        globals()[function]()\n"
                       "        UPSTREAM_RESULTS.append({'test_id': test_id, 'group': 'upstream_regressions', 'passed': True})\n"
                       "    except Exception as error:\n"
                       "        UPSTREAM_RESULTS.append({'test_id': test_id, 'group': 'upstream_regressions', 'passed': False, 'type': type(error).__name__, 'text': str(error)})")
    return "\n\n".join(definitions) + "\n"


API_DRIVER = r'''
import copy
import importlib
import json

def invoke(request):
    calls = {}
    restored = []
    for module_name, class_name, method_name in request.get('trace', []):
        cls = getattr(importlib.import_module(module_name), class_name)
        original = getattr(cls, method_name)
        key = '.'.join((module_name, class_name, method_name))
        calls[key] = 0
        def traced(self, *args, _original=original, _key=key, **kwargs):
            calls[_key] += 1
            return _original(self, *args, **kwargs)
        local = cls.__dict__.get(method_name)
        restored.append((cls, method_name, local))
        setattr(cls, method_name, traced)
    arguments = copy.deepcopy(request.get('args', []))
    before = copy.deepcopy(arguments)
    try:
        value = getattr(importlib.import_module(request['module']), request['function'])(*arguments)
        result = {'kind': 'return', 'value': value}
        if calls:
            result['source_api_used'] = {key: count > 0 for key, count in calls.items()}
        if request.get('check_input_unchanged'):
            result['input_unchanged'] = arguments == before
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
        OBSERVATIONS.append({'kind': 'exception', 'type': type(error).__module__ + '.' + type(error).__name__, 'text': str(error)})
'''


def _public_driver(task_id):
    _, row, directory = _entry(task_id)
    cases = json.loads(_asset(row, directory, "public-checks.json"))["cases"]
    return (_upstream_driver() + "REQUESTS = " + repr([case["request"] for case in cases])
            + "\n" + API_DRIVER + "\nPUBLIC_EXPECTED = " + repr(cases)
            + "\nfor case, observation in zip(PUBLIC_EXPECTED, OBSERVATIONS):\n"
              "    UPSTREAM_RESULTS.append({'test_id': case['case_id'], 'group': 'public_normal', 'passed': observation == case['expected'], 'observed': observation, 'expected': case['expected']})\n"
              "print('PROWORKSIM_DEVELOPMENT_PUBLIC:' + json.dumps(UPSTREAM_RESULTS, sort_keys=True, allow_nan=False))\n")


def build_case(task_id):
    manifest, row, directory = _entry(task_id)
    files = original_files()
    editable = []
    for name in row["editable_paths"]:
        files[name] = _asset(row, directory, "starter/" + name)
        editable.append(name)
    contract = _asset(row, directory, "contract.md")
    files["contract.md"] = contract
    files["test_visible.py"] = _public_driver(task_id)
    files["test_member.py"] = "# Member-authored exploratory checks may be added here.\n"
    editable.append("test_member.py")
    roles = ("member_a",) if row["category"] != "o1_root_goal" else ("member_a", "member_b")
    partition = manifest["source_partition"]
    return {"version": VERSION, "task_id": task_id, "purpose": PURPOSE,
            "training_eligible": False, "contribution_eligible": False,
            "independent_confirmation_eligible": False,
            "category": row["category"], "active_roles": list(roles),
            "files": files, "editable_paths": sorted(editable), "root_goal": contract,
            "task_definitions": {}, "initial_owners": {},
            "members": {role: list(MEMBER_CAPABILITIES) for role in roles},
            "source_contract": {
                "source_asset_ids": [manifest["source"]["asset_id"]],
                "source_revision": manifest["source"]["commit"],
                "source_manifest_sha256": _sha((ASSETS / "source-manifest.json").read_bytes()),
                "requirements_sha256": row["files_sha256"]["contract.md"],
                "public_checks_sha256": row["files_sha256"]["public-checks.json"],
                "independent_verifier_sha256": row["files_sha256"]["acceptance.json"],
                "complete_delivery_requires": row["complete_delivery_requires"],
                "public_requirements": contract,
                "category": row["category"],
                "forced_initial_failure_feedback": row["category"] == "repair_after_real_failure",
            },
            "source_partition_sha256": _sha(json.dumps(partition, sort_keys=True).encode()),
            "actor_trajectories_created": False}


def _validate_files(task_id, files):
    case = build_case(task_id)
    if set(files) != set(case["files"]) or any(
        value != files[name] for name, value in case["files"].items()
        if name not in case["editable_paths"]
    ):
        raise ValueError("Only public editable paths may change")


def reference_solution(task_id):
    """Controller-only satisfiability witness; never policy experience."""
    _, row, directory = _entry(task_id)
    files = build_case(task_id)["files"]
    for name in row["editable_paths"]:
        files[name] = _asset(row, directory, "reference/" + name)
    return files


def bad_controls(task_id):
    """Jointly verify the reference and task-specific incomplete alternatives."""
    _, row, directory = _entry(task_id)
    controls = json.loads(_asset(row, directory, "bad-controls.json"))
    reference = reference_solution(task_id)
    result = {"initial_workspace": build_case(task_id)["files"]}
    for item in controls:
        files = dict(reference)
        for name, value in item["replace_files"].items():
            if name not in row["editable_paths"]:
                raise ValueError("Bad control changed a frozen source path")
            files[name] = value
        result[item["control_id"]] = files
    return result


def _decode(execution, marker):
    encoded = [line[len(marker):] for line in execution["output"].splitlines()
               if line.startswith(marker)]
    if execution["executed"] and execution["driver_completed"] and execution["returncode"] == 0 and len(encoded) == 1:
        try:
            return json.loads(encoded[0])
        except ValueError:
            pass
    return None


def run_public_tests(task_id, files, *, run_root):
    _validate_files(task_id, files)
    execution = run_isolated(files, _public_driver(task_id), run_root=run_root)
    tests = _decode(execution, "PROWORKSIM_DEVELOPMENT_PUBLIC:")
    manifest, row, directory = _entry(task_id)
    expected = [name + "::" + function
                for name, functions in manifest["source"]["selected_tests"].items()
                for function in functions]
    public = json.loads(_asset(row, directory, "public-checks.json"))["cases"]
    expected += [case["case_id"] for case in public]
    if (not isinstance(tests, list) or [test.get("test_id") for test in tests] != expected
            or any(type(test.get("passed")) is not bool for test in tests)):
        tests = None
    groups = {}
    for group in ("upstream_regressions", "public_normal"):
        selected = [test for test in tests or [] if test["group"] == group]
        completed = tests is not None
        passed = completed and bool(selected) and all(test["passed"] for test in selected)
        groups[group] = {"executed": completed, "passed": passed, "tests": selected,
                         "status": "passed" if passed else "failed" if completed else "not_tested"}
    return {"execution": execution, "tests": tests, "groups": groups,
            "passed": tests is not None and all(test["passed"] for test in tests),
            "authority": "visible_regression_and_public_normal_feedback_not_independent_acceptance"}


def assess(task_id, files, *, run_root):
    """Only independent inputs cross the worker boundary; expected values stay here.

    The inherited finite API sandbox is not a defense against adversarial output
    fabrication. This development screening does not claim benchmark robustness.
    """
    _validate_files(task_id, files)
    _, row, directory = _entry(task_id)
    fixture = _asset(row, directory, "acceptance.json")
    cases = json.loads(fixture)["cases"]
    requests = [copy.deepcopy(case["request"]) for case in cases]
    execution = run_isolated(files, "REQUESTS = " + repr(requests) + "\n" + API_DRIVER
                             + "\nprint(" + repr(MARKER) + " + json.dumps(OBSERVATIONS, sort_keys=True, allow_nan=False))\n",
                             run_root=run_root)
    observations = _decode(execution, MARKER)
    if not isinstance(observations, list) or len(observations) != len(cases):
        observations = None
    checks = [{"case_id": case["case_id"], "group": case["group"],
               "passed": observations is not None and observations[index] == case["expected"],
               "expected": case["expected"],
               "observed": observations[index] if observations is not None else None}
              for index, case in enumerate(cases)]
    return {"version": VERSION, "task_id": task_id, "purpose": PURPOSE,
            "passed": all(check["passed"] for check in checks), "checks": checks,
            "execution": execution, "fixture_sha256": _sha(fixture.encode()),
            "expected_values_sent_to_worker": False, "training_trajectory": False,
            "scope": "project_derived_model_interface_cases_not_upstream_benchmark"}
