"""New purpose-isolated O1 contracts on pristine, already pinned libraries.

Old defects, consumers, model-development episodes and reference trajectories are
never relabeled. The v034 exact comparison and feedback Gamma are inherited.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import textwrap

from .software_sandbox import run_isolated
from . import software_tasks_v030 as decoding
from .software_tasks_v034 import (
    PUBLIC_FEEDBACK_VERSION as PUBLIC_FEEDBACK_VERSION,
    acceptance_dimensions, comparable, exact_json_equal,
    project_public_test_feedback as project_public_test_feedback,
)
from .storage import digest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "examples/software-sources-v035"
VERSION = "software-tasks-v0.35"
PURPOSE = "policy_training"
PURPOSES = ("policy_training", "contribution_development", "independent_confirmation")
TRAINING_CASE_ID = "sp-script-inventory-v035"
CONTRIBUTION_CASE_IDS = ("sc-job-policy-v035", "sc-command-set-v035")
CONFIRMATION_CASE_IDS = ("tf-port-status-v035", "tf-batch-totals-v035")
TASK_IDS = (TRAINING_CASE_ID, *CONTRIBUTION_CASE_IDS, *CONFIRMATION_CASE_IDS)
CASE_PURPOSES = {TRAINING_CASE_ID: PURPOSE,
    **dict.fromkeys(CONTRIBUTION_CASE_IDS, "contribution_development"),
    **dict.fromkeys(CONFIRMATION_CASE_IDS, "independent_confirmation")}
NAMES = {TRAINING_CASE_ID: "sqlparse", **dict.fromkeys(CONTRIBUTION_CASE_IDS, "schema"),
         **dict.fromkeys(CONFIRMATION_CASE_IDS, "textfsm")}
MARKER = "PROWORKSIM_PURPOSE_ROOT_OBSERVATIONS:"
PUBLIC_MARKER = "PROWORKSIM_PURPOSE_ROOT_PUBLIC:"


def source_partition():
    value = json.loads((ASSETS / "source-partition.json").read_text())
    payload = {key: item for key, item in value.items() if key != "sha256"}
    expected = digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    if (value.get("sha256") != expected or value.get("assignments") != CASE_PURPOSES
            or value.get("old_contracts_reused") is not False or value.get("old_development_material_admitted") is not False):
        raise ValueError("Frozen v035 purpose partition changed")
    return value


def _entry(task_id):
    if task_id not in TASK_IDS:
        raise ValueError("Only new purpose-isolated v035 contracts are admitted")
    manifest = json.loads((ASSETS / "source-manifest.json").read_text())
    partition = source_partition()
    row = next(row for row in manifest["cases"] if row["task_id"] == task_id)
    environment = manifest["source_environments"][row["environment"]]
    if (manifest["source_partition_sha256"] != partition["sha256"]
            or row["purpose"] != CASE_PURPOSES[task_id]
            or environment["purpose"] != row["purpose"]
            or row["training_eligible"] is not (row["purpose"] == PURPOSE)):
        raise ValueError("A root or its pinned environment cannot cross the frozen purpose boundary")
    return manifest, row, ASSETS / task_id


def _asset(row, directory, name):
    raw = (directory / name).read_bytes()
    if digest(raw) != row["files_sha256"][name]:
        raise ValueError("Frozen v035 contract material changed: " + name)
    return raw.decode()


def original_files(task_id):
    manifest, row, _ = _entry(task_id)
    environment = manifest["source_environments"][row["environment"]]
    files = {}
    for name, expected in environment["files_sha256"].items():
        raw = (ROOT / environment["source_relative_path"] / name).read_bytes()
        if digest(raw) != expected:
            raise ValueError("Pristine pinned environment changed: " + name)
        if name != environment["upstream_test_file"]:
            files[name] = raw.decode()
    return files


def _regression_driver(task_id):
    manifest, row, _ = _entry(task_id)
    environment = manifest["source_environments"][row["environment"]]
    path = ROOT / environment["source_relative_path"] / environment["upstream_test_file"]
    raw = path.read_bytes()
    if digest(raw) != environment["files_sha256"][environment["upstream_test_file"]]:
        raise ValueError("Selected original API regression changed")
    text, selected = raw.decode(), environment["selected_regressions"]
    tree = ast.parse(text)
    if row["environment"] == "textfsm":
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "UnitTestFSM")
        definitions = []
        for test_id in selected:
            node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == test_id.split("::")[-1])
            definitions.append(textwrap.indent(ast.get_source_segment(text, node), "    "))
        header = "import io\nimport unittest\nimport textfsm\nclass UnitTestFSM(unittest.TestCase):\n" + "\n\n".join(definitions)
        call = "UnitTestFSM(test_id.split('::')[-1]).debug()"
    else:
        definitions = []
        for test_id in selected:
            node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == test_id.split("::")[-1])
            if node.args.args or node.decorator_list:
                raise ValueError("Only original fixture-free API tests are registered")
            definitions.append(ast.get_source_segment(text, node))
        header = ("import sqlparse\n" if row["environment"] == "sqlparse" else "from schema import Schema, SchemaError\n") + "\n\n".join(definitions)
        call = "globals()[test_id.split('::')[-1]]()"
    return header + "\nUPSTREAM_RESULTS = []\nfor test_id in " + repr(selected) + ":\n    try:\n        " + call + "\n        UPSTREAM_RESULTS.append({'test_id': test_id, 'group': 'upstream_regressions', 'passed': True})\n    except Exception as error:\n        UPSTREAM_RESULTS.append({'test_id': test_id, 'group': 'upstream_regressions', 'passed': False, 'type': type(error).__name__, 'text': str(error)})\n"


API_DRIVER = r'''
import copy
import importlib
import json
import sys

def exact_json_equal(left, right):
    return json.dumps(left, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(right, sort_keys=True, ensure_ascii=False, allow_nan=False)

def invoke(request):
    counts, targets, effects = {}, {}, []
    for module_name, attribute in request.get('trace', []):
        value = importlib.import_module(module_name)
        for part in attribute.split('.'):
            value = getattr(value, part)
        if isinstance(value, property):
            value = value.fget
        value = getattr(value, '__func__', value)
        code = getattr(value, '__code__', None)
        if code is None:
            raise ValueError('The declared API has no inspectable Python code object: ' + module_name + '.' + attribute)
        key = module_name + '.' + attribute
        counts[key] = 0
        targets.setdefault(code, []).append(key)
    target = getattr(importlib.import_module(request['module']), request['function'])
    arguments = copy.deepcopy(request.get('args', []))
    before = copy.deepcopy(arguments)
    def probe(frame, event, value):
        keys = targets.get(frame.f_code, ())
        if event == 'call':
            for key in keys:
                counts[key] += 1
        elif event == 'return':
            for key in keys:
                entry = {'api': key, 'event': 'profile_return',
                         'scope': 'A profile return event with None can also be exception unwinding; only the outer invocation determines return versus exception.'}
                try:
                    entry['value'] = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
                    entry['json_value_recorded'] = True
                except (TypeError, ValueError):
                    entry['json_value_recorded'] = False
                    entry['python_type'] = type(value).__module__ + '.' + type(value).__name__
                effects.append(entry)
    previous = sys.getprofile()
    try:
        sys.setprofile(probe)
        try:
            value = target(*arguments, **request.get('kwargs', {}))
            result = {'kind': 'return', 'value': value}
        except Exception as error:
            result = {'kind': 'exception', 'type': type(error).__module__ + '.' + type(error).__name__, 'text': str(error)}
    finally:
        sys.setprofile(previous)
    if counts:
        result['source_api_used'] = {key: count > 0 for key, count in counts.items()}
        result['source_api_observation_complete'] = True
        result['source_api_trace'] = effects
    if request.get('check_input_unchanged'):
        result['input_unchanged'] = exact_json_equal(arguments, before)
    return result

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
    return (_regression_driver(task_id) + "\nREQUESTS = " + repr([item["request"] for item in cases]) + "\n" + API_DRIVER
        + "\nPUBLIC_EXPECTED = " + repr(cases)
        + "\nfor case, observation in zip(PUBLIC_EXPECTED, OBSERVATIONS):\n"
          "    compared = {key: value for key, value in observation.items() if key != 'source_api_trace'}\n"
          "    UPSTREAM_RESULTS.append({'test_id': case['case_id'], 'group': 'public_normal', 'requirement_group': case['group'], 'passed': exact_json_equal(compared, case['expected']), 'observed': observation, 'expected': case['expected']})\n"
          "print(" + repr(PUBLIC_MARKER) + " + json.dumps(UPSTREAM_RESULTS, sort_keys=True, allow_nan=False))\n")


def build_case(task_id):
    manifest, row, directory = _entry(task_id)
    environment = manifest["source_environments"][row["environment"]]
    files = original_files(task_id)
    files.update({name: _asset(row, directory, "starter/" + name) for name in row["editable_paths"]})
    files.update({name: _asset(row, directory, "readonly/" + name) for name in row["readonly_paths"]})
    contract = _asset(row, directory, "contract.md")
    files.update({"contract.md": contract, "test_visible.py": _public_driver(task_id),
                  "test_member.py": "# Member-authored exploratory checks may be added here.\n"})
    purpose = row["purpose"]
    return {"version": VERSION, "task_id": task_id, "purpose": purpose, "training_eligible": purpose == PURPOSE,
        "contribution_eligible": purpose == "contribution_development", "independent_confirmation_eligible": purpose == "independent_confirmation",
        "category": "o1_root_goal", "files": files, "editable_paths": sorted([*row["editable_paths"], "test_member.py"]),
        "root_goal": contract, "task_definitions": {}, "initial_owners": {},
        "source_contract": {"source_asset_ids": [row["asset_id"]], "source_environment_asset_ids": [environment["asset_id"]],
            "source_revision": environment["commit"], "source_environment": row["environment"], "purpose": purpose,
            "source_manifest_sha256": digest((ASSETS / "source-manifest.json").read_bytes()),
            "source_partition_sha256": manifest["source_partition_sha256"],
            "requirements_sha256": row["files_sha256"]["contract.md"],
            "public_checks_sha256": row["files_sha256"]["public-checks.json"],
            "independent_verifier_sha256": row["files_sha256"]["acceptance.json"],
            "complete_delivery_requires": row["complete_delivery_requires"], "public_requirements": contract,
            "contract_symbols": copy.deepcopy(row["contract_symbols"]),
            "new_contract_pristine_pinned_environment": True, "old_defect_patch_applied": False,
            "old_contract_reused": False, "category": "o1_root_goal", "forced_initial_failure_feedback": False},
        "source_partition_sha256": manifest["source_partition_sha256"]}


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
    _, row, _ = _entry(task_id)
    original, joint = build_case(task_id)["files"], reference_solution(task_id)
    shared, consumer = copy.deepcopy(original), copy.deepcopy(original)
    for name in row["shared_api_paths"]:
        shared[name] = joint[name]
    for name in row["consumer_paths"]:
        consumer[name] = joint[name]
    return {"original": original, "shared_api_only": shared, "consumer_only": consumer, "joint_reference": joint}


def run_public_tests(task_id, files, *, run_root):
    _validate_files(task_id, files)
    execution = run_isolated(files, _public_driver(task_id), run_root=run_root)
    tests = decoding._decode(execution, PUBLIC_MARKER)
    manifest, row, directory = _entry(task_id)
    environment = manifest["source_environments"][row["environment"]]
    expected = environment["selected_regressions"] + [item["case_id"] for item in json.loads(_asset(row, directory, "public-checks.json"))["cases"]]
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
            "authority": "new_root_public_semantics_and_related_original_API_subset_not_task_private_acceptance"}


def assess_files(task_id, files, *, run_root):
    _validate_files(task_id, files)
    _, row, directory = _entry(task_id)
    fixture = _asset(row, directory, "acceptance.json")
    cases = json.loads(fixture)["cases"]
    execution = run_isolated(files, "REQUESTS = " + repr([item["request"] for item in cases]) + "\n" + API_DRIVER
        + "\nprint(" + repr(MARKER) + " + json.dumps(OBSERVATIONS, sort_keys=True, allow_nan=False))\n", run_root=Path(run_root) / "independent")
    observed = decoding._decode(execution, MARKER)
    if not isinstance(observed, list) or len(observed) != len(cases):
        observed = None
    checks = [{"case_id": case["case_id"], "group": case["group"], "expected": case["expected"],
               "observed": observed[index] if observed is not None else None,
               "passed": observed is not None and exact_json_equal(comparable(observed[index]), case["expected"])} for index, case in enumerate(cases)]
    independent = {"version": VERSION, "task_id": task_id, "purpose": row["purpose"],
        "passed": all(item["passed"] for item in checks), "checks": checks, "execution": execution,
        "fixture_sha256": digest(fixture.encode()), "expected_values_sent_to_worker": False}
    public = run_public_tests(task_id, files, run_root=Path(run_root) / "public")
    executed = execution["executed"] and public["execution"]["executed"]
    components = {"task_private_complete_contract": independent["passed"], "public_semantics_and_original_API_subset": public["passed"]}
    return {"version": VERSION, "task_id": task_id, "purpose": row["purpose"], "executed": executed,
            "passed": executed and all(components.values()), "components": components,
            "independent_acceptance": independent, "public_acceptance": public, **acceptance_dimensions(independent, public),
            "scope": "Complete new purpose-bound root contract; task-private checks are not the independent-confirmation material pool."}
