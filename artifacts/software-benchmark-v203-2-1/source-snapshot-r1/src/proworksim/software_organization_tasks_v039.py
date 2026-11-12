"""Four new, finite organization-development roots on pinned pristine schema.

The public business requirements are project-authored. The reused environment
has SWE-smith provenance; these are not original upstream issues or held-out
confirmation material. No role allocation or task decomposition is generated.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from . import software_tasks_v030 as decoding
from .software_sandbox import run_isolated
from .software_tasks_v034 import (
    PUBLIC_FEEDBACK_VERSION as PUBLIC_FEEDBACK_VERSION,
    acceptance_dimensions, comparable, exact_json_equal,
    project_public_test_feedback as project_public_test_feedback,
)
from .software_tasks_v036 import API_DRIVER
from .storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "examples/software-organization-v039"
VERSION = "software-organization-tasks-v0.39"
PARTITION_VERSION = "software-organization-source-partition-v0.39"
PURPOSE = "organization_development"
TASK_IDS = CASE_IDS = ("sc-label-index-v039", "sc-row-projection-v039",
                      "sc-record-views-v039", "sc-record-catalog-v039")
FAMILIES = {case: "light_control" if index < 2 else "cross_dependency"
            for index, case in enumerate(TASK_IDS)}
NAMES = dict.fromkeys(TASK_IDS, "schema")
CASE_PURPOSES = dict.fromkeys(TASK_IDS, PURPOSE)
MARKER = "PROWORKSIM_ORGANIZATION_V039_OBSERVATIONS:"
PUBLIC_MARKER = "PROWORKSIM_ORGANIZATION_V039_PUBLIC:"
PINNED_SCHEMA_COMMIT = "24a3045773eac497c659f24b32f24a281be9f286"
MEMBER_STARTER = "# Optional member-authored exploratory checks; no automatic discovery.\n"


def canonical_case_id(case_id):
    if case_id not in TASK_IDS:
        raise ValueError("Only the four new v039 organization-development roots are admitted")
    return case_id


def _checked_manifest(path, *, version):
    value = json.loads(path.read_text())
    expected = digest(json_bytes({key: item for key, item in value.items() if key != "sha256"}))
    if value.get("version") != version or value.get("sha256") != expected:
        raise ValueError("Frozen organization source manifest identity changed: " + str(path))
    return value


def source_partition():
    value = _checked_manifest(ASSETS / "source-partition.json", version=PARTITION_VERSION)
    if (value.get("assignments") != CASE_PURPOSES or value.get("purpose") != PURPOSE
            or value.get("training_eligible") is not False
            or value.get("independent_confirmation_eligible") is not False
            or value.get("old_results_reclassified") is not False):
        raise ValueError("New organization roots cannot cross their source purpose")
    return value


def source_manifest():
    value = _checked_manifest(ASSETS / "source-manifest.json", version=VERSION)
    environment = value["source_environment"]
    if (value.get("purpose") != PURPOSE or value.get("source_partition_sha256") != source_partition()["sha256"]
            or value.get("api_driver_sha256") != digest(API_DRIVER.encode())
            or environment.get("commit") != PINNED_SCHEMA_COMMIT
            or environment.get("purpose") != PURPOSE
            or environment.get("state") != "pristine_pinned_upstream_no_old_defect_patch"
            or [row["task_id"] for row in value["cases"]] != list(TASK_IDS)):
        raise ValueError("Frozen schema environment, driver or four-root inventory changed")
    for row in value["cases"]:
        if (row["purpose"] != PURPOSE or row["family"] != FAMILIES[row["task_id"]]
                or row.get("training_eligible") is not False
                or row.get("contribution_eligible") is not False
                or row.get("independent_confirmation_eligible") is not False
                or row.get("predefined_execution_tasks") is not False
                or row.get("initial_owners") != {} or row.get("old_business_contract_reused") is not False):
            raise ValueError("New roots must remain undecomposed organization-development contracts")
    return value


def _entry(case_id):
    case_id = canonical_case_id(case_id)
    manifest = source_manifest()
    row = next(row for row in manifest["cases"] if row["task_id"] == case_id)
    return manifest, row, ASSETS / case_id


def _asset(row, directory, name):
    raw = (directory / name).read_bytes()
    if digest(raw) != row["files_sha256"][name]:
        raise ValueError("Frozen v039 task asset changed: " + name)
    return raw.decode()


def _environment_asset(manifest, name):
    environment = manifest["source_environment"]
    raw = (ROOT / environment["source_relative_path"] / name).read_bytes()
    if digest(raw) != environment["files_sha256"][name]:
        raise ValueError("Pristine pinned schema environment changed: " + name)
    return raw.decode()


def original_files(case_id):
    manifest, _, _ = _entry(case_id)
    environment = manifest["source_environment"]
    return {name: _environment_asset(manifest, name) for name in environment["files_sha256"]
            if name != environment["upstream_test_file"]}


def _regression_driver_from(manifest):
    environment = manifest["source_environment"]
    text = _environment_asset(manifest, environment["upstream_test_file"])
    tree = ast.parse(text)
    selected, definitions = environment["selected_regressions"], []
    for test_id in selected:
        node = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == test_id.split("::")[-1])
        if node.args.args or node.decorator_list:
            raise ValueError("Only the declared fixture-free original schema regression is used")
        definitions.append(ast.get_source_segment(text, node))
    return ("from schema import Schema, SchemaError\n" + "\n\n".join(definitions)
        + "\nUPSTREAM_RESULTS = []\nfor test_id in " + repr(selected) + ":\n    try:\n"
          "        globals()[test_id.split('::')[-1]]()\n"
          "        UPSTREAM_RESULTS.append({'test_id': test_id, 'group': 'upstream_regressions', 'passed': True})\n"
          "    except Exception as error:\n"
          "        UPSTREAM_RESULTS.append({'test_id': test_id, 'group': 'upstream_regressions', 'passed': False, 'type': type(error).__name__, 'text': str(error)})\n")


def _public_driver_from(manifest, row, directory):
    cases = json.loads(_asset(row, directory, "public-checks.json"))["cases"]
    return (_regression_driver_from(manifest)
        + "\nREQUESTS = " + repr([item["request"] for item in cases]) + "\n" + API_DRIVER
        + "\nPUBLIC_EXPECTED = " + repr(cases)
        + "\nfor case, observation in zip(PUBLIC_EXPECTED, OBSERVATIONS):\n"
          "    compared = {key: value for key, value in observation.items() if key != 'source_api_trace'}\n"
          "    UPSTREAM_RESULTS.append({'test_id': case['case_id'], 'group': 'public_normal', 'requirement_group': case['group'], 'passed': exact_json_equal(compared, case['expected']), 'observed': observation, 'expected': case['expected']})\n"
          "print(" + repr(PUBLIC_MARKER) + " + json.dumps(UPSTREAM_RESULTS, sort_keys=True, allow_nan=False))\n")


def _private_driver_from(row, directory):
    cases = json.loads(_asset(row, directory, "acceptance.json"))["cases"]
    return ("REQUESTS = " + repr([item["request"] for item in cases]) + "\n" + API_DRIVER
        + "\nprint(" + repr(MARKER) + " + json.dumps(OBSERVATIONS, sort_keys=True, allow_nan=False))\n")


def _public_driver(case_id):
    manifest, row, directory = _entry(case_id)
    driver = _public_driver_from(manifest, row, directory)
    if digest(driver.encode()) != row["public_driver_sha256"]:
        raise ValueError("Frozen v039 public driver changed")
    return driver


def build_case(case_id):
    manifest, row, directory = _entry(case_id)
    environment = manifest["source_environment"]
    files = original_files(case_id)
    files.update({path: _asset(row, directory, "starter/" + path) for path in row["editable_paths"]})
    contract = _asset(row, directory, "contract.md")
    files.update({"contract.md": contract, "test_visible.py": _public_driver(case_id),
                  "test_member.py": MEMBER_STARTER})
    partition_sha = manifest["source_partition_sha256"]
    return {"version": VERSION, "task_id": case_id, "new_root": True, "family": row["family"],
        "purpose": PURPOSE, "training_eligible": False, "contribution_eligible": False,
        "independent_confirmation_eligible": False, "category": "new_organization_root_goal",
        "files": files, "editable_paths": sorted([*row["editable_paths"], "test_member.py"]),
        "root_goal": contract, "task_definitions": {}, "initial_owners": {},
        "source_partition_sha256": partition_sha,
        "source_contract": {"source_asset_ids": [row["asset_id"]],
            "source_environment_asset_ids": [environment["asset_id"]],
            "source_revision": environment["commit"], "source_environment": "schema", "purpose": PURPOSE,
            "source_manifest_sha256": manifest["sha256"], "source_partition_sha256": partition_sha,
            "requirements_sha256": row["files_sha256"]["contract.md"],
            "public_checks_sha256": row["files_sha256"]["public-checks.json"],
            "independent_verifier_sha256": row["files_sha256"]["acceptance.json"],
            "public_driver_sha256": row["public_driver_sha256"],
            "independent_driver_sha256": row["independent_driver_sha256"],
            "complete_delivery_requires": copy.deepcopy(row["complete_delivery_requires"]),
            "public_requirements": contract, "contract_symbols": copy.deepcopy(row["contract_symbols"]),
            "source_environment_reused": True, "original_environment_purpose": environment["original_environment_purpose"],
            "new_contract_pristine_pinned_environment": True, "old_defect_patch_applied": False,
            "old_contract_reused": False, "task_authorship": row["task_authorship"],
            "category": "new_organization_root_goal", "forced_initial_failure_feedback": False,
            "training_eligible": False, "independent_confirmation_eligible": False},
        "initial_binding": {"new_contract_sha256": row["files_sha256"]["contract.md"],
            "initial_files_sha256": digest(json_bytes(files)),
            "initial_application_sha256": {path: digest(files[path].encode()) for path in row["editable_paths"]},
            "public_driver_sha256": row["public_driver_sha256"],
            "independent_driver_sha256": row["independent_driver_sha256"],
            "public_checks_sha256": row["files_sha256"]["public-checks.json"],
            "independent_verifier_sha256": row["files_sha256"]["acceptance.json"],
            "source_manifest_sha256": manifest["sha256"], "source_partition_sha256": partition_sha}}


def _validate_files(case_id, files):
    case = build_case(case_id)
    if set(files) != set(case["files"]) or any(files[name] != text for name, text in case["files"].items()
            if name not in case["editable_paths"]):
        raise ValueError("Only declared editable application files may change; quality assets stay private/read-only")


def reference_solution(case_id):
    """CPU witness only, never initial material or a role prompt."""
    _, row, directory = _entry(case_id)
    files = build_case(case_id)["files"]
    files.update({path: _asset(row, directory, "reference/" + path) for path in row["editable_paths"]})
    return files


def provenance_controls(case_id):
    _, row, directory = _entry(case_id)
    controls = {}
    for kind, paths in row["control_paths"].items():
        files = reference_solution(case_id)
        files.update({path: _asset(row, directory, "controls/" + kind + "/" + path) for path in paths})
        controls[kind] = files
    return controls


def dependency_controls(case_id):
    _, row, _ = _entry(case_id)
    if row["family"] != "cross_dependency":
        raise ValueError("Partial dependency controls apply only to the two shared-product roots")
    original, joint = build_case(case_id)["files"], reference_solution(case_id)
    shared, consumers = copy.deepcopy(original), copy.deepcopy(original)
    for path in row["shared_api_paths"]:
        shared[path] = joint[path]
    for path in row["consumer_paths"]:
        consumers[path] = joint[path]
    return {"shared_api_only": shared, "consumers_only": consumers}


def run_public_tests(case_id, files, *, run_root):
    _validate_files(case_id, files)
    manifest, row, directory = _entry(case_id)
    execution = run_isolated(files, _public_driver(case_id), run_root=run_root)
    tests = decoding._decode(execution, PUBLIC_MARKER)
    expected = manifest["source_environment"]["selected_regressions"] + [
        item["case_id"] for item in json.loads(_asset(row, directory, "public-checks.json"))["cases"]]
    if (not isinstance(tests, list) or [item.get("test_id") for item in tests] != expected
            or any(type(item.get("passed")) is not bool for item in tests)):
        tests = None
    groups = {}
    for name in ("upstream_regressions", "public_normal"):
        selected = [item for item in tests or [] if item["group"] == name]
        passed = tests is not None and bool(selected) and all(item["passed"] for item in selected)
        groups[name] = {"executed": tests is not None, "passed": passed, "tests": selected,
            "status": "passed" if passed else "failed" if tests is not None else "untested"}
    return {"execution": execution, "tests": tests, "groups": groups,
        "passed": tests is not None and all(item["passed"] for item in tests),
        "authority": "new_organization_root_public_semantics_and_pinned_schema_regression"}


def assess_files(case_id, files, *, run_root):
    _validate_files(case_id, files)
    _, row, directory = _entry(case_id)
    fixture = _asset(row, directory, "acceptance.json")
    cases = json.loads(fixture)["cases"]
    driver = _private_driver_from(row, directory)
    if digest(driver.encode()) != row["independent_driver_sha256"]:
        raise ValueError("Frozen v039 independent driver changed")
    execution = run_isolated(files, driver, run_root=Path(run_root) / "independent")
    observed = decoding._decode(execution, MARKER)
    if not isinstance(observed, list) or len(observed) != len(cases):
        observed = None
    checks = [{"case_id": case["case_id"], "group": case["group"], "expected": case["expected"],
        "observed": observed[index] if observed is not None else None,
        "passed": observed is not None and exact_json_equal(comparable(observed[index]), case["expected"])}
        for index, case in enumerate(cases)]
    independent = {"version": VERSION, "task_id": case_id, "purpose": PURPOSE,
        "passed": all(item["passed"] for item in checks), "checks": checks, "execution": execution,
        "fixture_sha256": digest(fixture.encode()), "expected_values_sent_to_worker": False}
    public = run_public_tests(case_id, files, run_root=Path(run_root) / "public")
    executed = execution["executed"] and public["execution"]["executed"]
    components = {"task_private_complete_contract": independent["passed"],
                  "public_semantics_and_original_API_subset": public["passed"]}
    return {"version": VERSION, "task_id": case_id, "purpose": PURPOSE,
        "training_eligible": False, "contribution_eligible": False, "independent_confirmation_eligible": False,
        "executed": executed, "passed": executed and all(components.values()), "components": components,
        "independent_acceptance": independent, "public_acceptance": public,
        **acceptance_dimensions(independent, public),
        "scope": "New project-authored organization-development requirements; task-private inputs are not the reserved independent-confirmation pool; finite observed API calls do not prove unique causal contribution"}
