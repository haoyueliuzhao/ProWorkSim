"""Four authored v045 business roots, clustered into two artificial families.

These are new synthetic requirements and deliberately incomplete initial code,
not discovered upstream bugs. Reference solutions and same-contract private
inputs are CPU witnesses, never member work or independent confirmation data.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import time

from . import software_tasks_v030 as decoding
from .software_sandbox import run_isolated
from .software_tasks_v034 import acceptance_dimensions, comparable, exact_json_equal
from .software_tasks_v036 import API_DRIVER
from .storage import atomic_write, digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "examples/software-organization-v045"
VERSION = "software-organization-tasks-v0.45"
PARTITION_VERSION = "software-organization-source-partition-v0.45"
PURPOSE = "organization_development"
TASK_IDS = CASE_IDS = ("sc-event-utc-boundary-la-v045", "sc-event-import-atomic-ha-v045",
                      "sc-rule-range-local-lb-v045", "sc-rule-migration-hb-v045")
TASK_LABELS = dict(zip(TASK_IDS, ("LA", "HA", "LB", "HB")))
FAMILIES = NAMES = dict(zip(TASK_IDS, ("event_interface", "event_interface", "rule_interface", "rule_interface")))
LOADS = dict(zip(TASK_IDS, ("local_maintenance", "stateful_revision", "local_maintenance", "semantic_migration")))
CASE_PURPOSES = dict.fromkeys(TASK_IDS, PURPOSE)
DIAGNOSTIC_IDS = ("diagnostic_a", "diagnostic_b")
DIAGNOSTIC_VERSION = "authored-public-diagnostic-v0.45"
DIAGNOSTIC_MARKER = "PROWORKSIM_V045_DIAGNOSTIC:"
MARKER = "PROWORKSIM_V045_OBSERVATIONS:"
PUBLIC_MARKER = "PROWORKSIM_V045_PUBLIC:"
MEMBER_STARTER = "# Optional member-authored exploratory checks; no automatic discovery.\n"
_INITIAL_DIAGNOSTIC_CACHE = {}


def canonical_case_id(case_id):
    if case_id not in TASK_IDS:
        raise ValueError("Only the four declared v045 synthetic roots are admitted")
    return case_id


def _checked_manifest(path, *, version):
    value = json.loads(path.read_text())
    if value.get("version") != version or value.get("sha256") != digest(json_bytes(
            {key: item for key, item in value.items() if key != "sha256"})):
        raise ValueError("Frozen v045 task manifest changed: " + str(path))
    return value


def source_partition():
    value = _checked_manifest(ASSETS / "source-partition.json", version=PARTITION_VERSION)
    if (value.get("assignments") != CASE_PURPOSES or value.get("families") != FAMILIES
            or value.get("authored_family_count") != 2 or value.get("external_upstream_bug_claim") is not False
            or any(value.get(k) is not False for k in ("training_eligible", "contribution_eligible",
                "independent_confirmation_eligible", "old_results_reclassified"))):
        raise ValueError("Authored roots must retain their two-family development-only provenance")
    return value


def source_manifest():
    value = _checked_manifest(ASSETS / "source-manifest.json", version=VERSION)
    if (value.get("source_partition_sha256") != source_partition()["sha256"]
            or value.get("api_driver_sha256") != digest(API_DRIVER.encode())
            or value.get("authored_family_count") != 2 or value.get("external_upstream_bug_claim") is not False
            or [row["task_id"] for row in value.get("cases", [])] != list(TASK_IDS)):
        raise ValueError("Frozen v045 source family, API driver or inventory changed")
    for row in value["cases"]:
        if (row["purpose"] != PURPOSE or row["family"] != FAMILIES[row["task_id"]]
                or row["initial_owners"] != {} or row["predefined_execution_tasks"] is not False
                or any(row.get(k) is not False for k in ("training_eligible", "contribution_eligible",
                    "independent_confirmation_eligible", "external_upstream_bug_claim"))):
            raise ValueError("Synthetic task provenance or undecomposed root contract changed")
    return value


def _entry(case_id):
    case_id = canonical_case_id(case_id)
    manifest = source_manifest()
    row = next(row for row in manifest["cases"] if row["task_id"] == case_id)
    return manifest, row, ASSETS / case_id


def _asset(row, directory, name):
    data = (directory / name).read_bytes()
    if digest(data) != row["files_sha256"][name]:
        raise ValueError("Frozen v045 task asset changed: " + name)
    return data.decode()


def _public_driver_from(manifest, row, directory):
    cases = json.loads(_asset(row, directory, "public-checks.json"))["cases"]
    return ("REQUESTS = " + repr([item["request"] for item in cases]) + "\n" + API_DRIVER
        + "\nPUBLIC_EXPECTED = " + repr(cases) + "\nRESULTS = []\n"
          "for case, observation in zip(PUBLIC_EXPECTED, OBSERVATIONS):\n"
          "    compared = {k: v for k, v in observation.items() if k != 'source_api_trace'}\n"
          "    RESULTS.append({'test_id': case['case_id'], 'group': 'upstream_regressions' if case['group'] == 'preserved_api' else 'public_normal', 'requirement_group': case['group'], 'passed': exact_json_equal(compared, case['expected']), 'observed': observation, 'expected': case['expected']})\n"
          "print(" + repr(PUBLIC_MARKER) + " + json.dumps(RESULTS, sort_keys=True, allow_nan=False))\n")


def _private_driver_from(row, directory):
    cases = json.loads(_asset(row, directory, "acceptance.json"))["cases"]
    return ("REQUESTS = " + repr([item["request"] for item in cases]) + "\n" + API_DRIVER
        + "\nprint(" + repr(MARKER) + " + json.dumps(OBSERVATIONS, sort_keys=True, allow_nan=False))\n")


def _public_driver(case_id):
    manifest, row, directory = _entry(case_id)
    driver = _public_driver_from(manifest, row, directory)
    if digest(driver.encode()) != row["public_driver_sha256"]:
        raise ValueError("Frozen v045 public driver changed")
    return driver


def build_case(case_id):
    manifest, row, directory = _entry(case_id)
    files = {path: _asset(row, directory, "initial/" + path) for path in row["editable_paths"]}
    files.update({path: _asset(row, directory, "readonly/" + path) for path in row["readonly_paths"]})
    contract = _asset(row, directory, "contract.md")
    files.update({"contract.md": contract, "test_visible.py": _public_driver(case_id), "test_member.py": MEMBER_STARTER})
    source = {"source_asset_ids": [row["asset_id"]], "source_environment_asset_ids": ["v045-authored-family:" + row["family"]],
        "source_revision": manifest["authored_against_repository_commit"], "source_environment": row["family"],
        "source_kind": "artificially_authored_bounded_business_contract", "task_authorship": row["task_authorship"],
        "external_upstream_bug_claim": False, "authored_family_count": 2, "root_count": 4,
        "source_manifest_sha256": manifest["sha256"], "source_partition_sha256": manifest["source_partition_sha256"],
        "requirements_sha256": row["files_sha256"]["contract.md"],
        "public_checks_sha256": row["files_sha256"]["public-checks.json"],
        "independent_verifier_sha256": row["files_sha256"]["acceptance.json"],
        "public_driver_sha256": row["public_driver_sha256"], "independent_driver_sha256": row["independent_driver_sha256"],
        "public_requirements": contract, "complete_delivery_requires": copy.deepcopy(row["complete_delivery_requires"]),
        "contract_symbols": copy.deepcopy(row["contract_symbols"]), "public_production_files": list(row["editable_paths"]),
        "member_test_file": "test_member.py", "readonly_support_files": list(row["readonly_paths"]),
        "initial_code_origin": "environment_preparation", "initial_code_model_generated": False,
        "initial_diagnostic_origin": "environment_initial_diagnostic", "initial_diagnostics_public_to_all_members": True,
        "forced_initial_failure_feedback": False, "purpose": PURPOSE, "training_eligible": False,
        "contribution_eligible": False, "independent_confirmation_eligible": False}
    return {"version": VERSION, "task_id": case_id, "new_root": True, "synthetic_root": True,
        "family": row["family"], "task_label": TASK_LABELS[case_id], "load_description": LOADS[case_id],
        "purpose": PURPOSE, "training_eligible": False, "contribution_eligible": False,
        "independent_confirmation_eligible": False, "category": "authored_organization_diagnostic_root",
        "files": files, "editable_paths": sorted([*row["editable_paths"], "test_member.py"]),
        "root_goal": contract, "task_definitions": {}, "initial_owners": {},
        "source_partition_sha256": manifest["source_partition_sha256"], "source_contract": source,
        "initial_binding": {"new_contract_sha256": row["files_sha256"]["contract.md"],
            "initial_files_sha256": digest(json_bytes(files)),
            "initial_application_sha256": {path: digest(files[path].encode()) for path in row["editable_paths"]},
            **{k: source[k] for k in ("public_driver_sha256", "independent_driver_sha256", "public_checks_sha256",
                "independent_verifier_sha256", "source_manifest_sha256", "source_partition_sha256")},
            "diagnostic_groups_sha256": row["files_sha256"]["diagnostic-groups.json"],
            "diagnostic_driver_sha256": copy.deepcopy(row["diagnostic_driver_sha256"])}}


def _validate_files(case_id, files):
    case = build_case(case_id)
    if set(files) != set(case["files"]) or any(files[name] != text for name, text in case["files"].items()
            if name not in case["editable_paths"]):
        raise ValueError("Only declared production files and test_member.py may change")


def reference_solution(case_id):
    _, row, directory = _entry(case_id)
    files = build_case(case_id)["files"]
    files.update({path: _asset(row, directory, "reference/" + path) for path in row["editable_paths"]})
    return files


def provenance_controls(case_id):
    _, row, directory = _entry(case_id)
    controls = {}
    for label, paths in row["control_paths"].items():
        files = reference_solution(case_id)
        files.update({path: _asset(row, directory, "controls/" + label + "/" + path) for path in paths})
        controls[label] = files
    return controls


def run_public_tests(case_id, files, *, run_root):
    _validate_files(case_id, files)
    _, row, directory = _entry(case_id)
    execution = run_isolated(files, _public_driver(case_id), run_root=run_root)
    tests = decoding._decode(execution, PUBLIC_MARKER)
    expected = [item["case_id"] for item in json.loads(_asset(row, directory, "public-checks.json"))["cases"]]
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
        "public_diagnostics": _public_diagnostics(case_id, files, tests,
            origin="member_public_test_execution", executed_driver_sha256=row["public_driver_sha256"]),
        "authority": "authored_contract_and_preserved_artificial_API_checks",
        "group_name_scope": "upstream_regressions is the inherited wire label for preserved authored API checks; no external upstream defect or suite is claimed"}


def assess_files(case_id, files, *, run_root):
    _validate_files(case_id, files)
    _, row, directory = _entry(case_id)
    fixture = _asset(row, directory, "acceptance.json")
    cases = json.loads(fixture)["cases"]
    driver = _private_driver_from(row, directory)
    if digest(driver.encode()) != row["independent_driver_sha256"]:
        raise ValueError("Frozen v045 private driver changed")
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
    components = {"task_private_complete_contract": independent["passed"], "public_preserved_API_and_contract": public["passed"]}
    return {"version": VERSION, "task_id": case_id, "purpose": PURPOSE, "training_eligible": False,
        "contribution_eligible": False, "independent_confirmation_eligible": False,
        "executed": executed, "passed": executed and all(components.values()), "components": components,
        "independent_acceptance": independent, "public_acceptance": public,
        **acceptance_dimensions(independent, public),
        "scope": "Bounded authored same-contract private checks plus public API checks; no collaboration behavior required, no independent-confirmation or causal-credit claim"}

def _diagnostic_cases(row, directory, group_id):
    if group_id not in DIAGNOSTIC_IDS:
        raise ValueError("Choose diagnostic_a or diagnostic_b")
    groups = json.loads(_asset(row, directory, "diagnostic-groups.json"))["groups"]
    cases = json.loads(_asset(row, directory, "public-checks.json"))["cases"]
    indexed = {case["case_id"]: case for case in cases}
    if (set(groups) != set(DIAGNOSTIC_IDS)
            or len(groups["diagnostic_a"]) + len(groups["diagnostic_b"]) != len(cases)
            or set(groups["diagnostic_a"]) & set(groups["diagnostic_b"])
            or set(groups["diagnostic_a"]) | set(groups["diagnostic_b"]) != set(indexed)):
        raise ValueError("The two diagnostic groups must partition the same public checks exactly")
    return [indexed[key] for key in groups[group_id]]


def _diagnostic_driver_from(row, directory, group_id):
    cases = _diagnostic_cases(row, directory, group_id)
    return ("REQUESTS = " + repr([case["request"] for case in cases]) + "\n" + API_DRIVER
        + "\nprint(" + repr(DIAGNOSTIC_MARKER) + " + json.dumps(OBSERVATIONS, sort_keys=True, allow_nan=False))\n")


def _diagnostic_record(case_id, files, group_id, tests, *, origin, executed_driver_sha256):
    """Compact public facts only: no hidden fixtures, repair plan or host path."""
    _, row, directory = _entry(case_id)
    cases = _diagnostic_cases(row, directory, group_id)
    indexed = {test["test_id"]: test for test in tests or []}
    executed = tests is not None and all(case["case_id"] in indexed for case in cases)
    visible = []
    if executed:
        for case in cases:
            test = indexed[case["case_id"]]
            item = {"test_id": case["case_id"], "passed": test["passed"]}
            if not test["passed"]:
                observed = test.get("observed")
                item.update(request=copy.deepcopy(case["request"]),
                    expected=copy.deepcopy(case["expected"]),
                    observed={key: value for key, value in observed.items() if key != "source_api_trace"}
                        if isinstance(observed, dict) else observed)
            visible.append(item)
    files_sha = digest(json_bytes(files))
    return {"version": DIAGNOSTIC_VERSION, "diagnostic_id": case_id + ":" + group_id,
        "group_id": group_id, "case_id": case_id, "origin": origin,
        "model_generated": False,
        "autonomous_discovery": False if origin == "environment_initial_diagnostic" else None,
        "files_sha256": files_sha,
        "source_binding": {"files_sha256": files_sha, "requirements_sha256": row["files_sha256"]["contract.md"],
            "public_checks_sha256": row["files_sha256"]["public-checks.json"],
            "diagnostic_driver_sha256": row["diagnostic_driver_sha256"][group_id],
            "executed_driver_sha256": executed_driver_sha256},
        "executed": executed, "passed": all(test["passed"] for test in visible) if executed else None,
        "counts": {"reported": len(visible), "passed": sum(test["passed"] for test in visible),
                   "failed": sum(not test["passed"] for test in visible)},
        "failed_test_ids": [test["test_id"] for test in visible if not test["passed"]],
        "tests": visible,
        "scope": "Observed public check facts for this exact file set. Passing cases are summarized; failed public requests and values are retained. No diagnosis-to-repair or responsibility recommendation is supplied."}


def _public_diagnostics(case_id, files, tests, *, origin, executed_driver_sha256):
    return {group: _diagnostic_record(case_id, files, group, tests, origin=origin,
        executed_driver_sha256=executed_driver_sha256) for group in DIAGNOSTIC_IDS}


def prepare_initial_diagnostics(case_id, run_root):
    """Execute public partitions once per exact key/process, with explicit reuse.

    Each worker process has its own cache. Returned diagnostics contain no host
    paths, timestamps, previous episode condition or actor history. The separate
    preparation receipt/cost records are controller provenance, not model input.
    No team run_tests counter is consumed by environment preparation.
    """
    started = time.monotonic()
    value = build_case(case_id)
    _, row, directory = _entry(case_id)
    files = value["files"]
    files_sha = digest(json_bytes(files))
    drivers = {group: _diagnostic_driver_from(row, directory, group) for group in DIAGNOSTIC_IDS}
    if any(digest(driver.encode()) != row["diagnostic_driver_sha256"][group] for group, driver in drivers.items()):
        raise ValueError("Frozen initial diagnostic driver changed")
    key = (case_id, files_sha, value["source_contract"]["source_manifest_sha256"],
        *(row["diagnostic_driver_sha256"][group] for group in DIAGNOSTIC_IDS))
    cached = _INITIAL_DIAGNOSTIC_CACHE.get(key)
    cache_reuse = False
    if cached is not None:
        path = Path(cached["receipt"]["path"])
        if path.is_file() and digest(path.read_bytes()) == cached["receipt"]["sha256"]:
            cache_reuse = True
        else:
            cached = None
    run_root = Path(run_root).resolve()
    if cached is None:
        run_root.mkdir(parents=True, exist_ok=True)
        receipt_path = run_root / "initial-diagnostic-receipt.json"
        if receipt_path.exists():
            raise FileExistsError("Initial public diagnostics require a fresh receipt destination")
        executions, diagnostics = [], {}
        for group_id in DIAGNOSTIC_IDS:
            driver = drivers[group_id]
            execution = run_isolated(files, driver, run_root=run_root / group_id)
            observations = decoding._decode(execution, DIAGNOSTIC_MARKER)
            cases = _diagnostic_cases(row, directory, group_id)
            if not isinstance(observations, list) or len(observations) != len(cases):
                observations = None
            tests = [{"test_id": case["case_id"], "expected": case["expected"], "observed": observations[index],
                "passed": exact_json_equal(comparable(observations[index]), case["expected"])}
                for index, case in enumerate(cases)] if observations is not None else None
            diagnostics[group_id] = _diagnostic_record(case_id, files, group_id, tests,
                origin="environment_initial_diagnostic", executed_driver_sha256=row["diagnostic_driver_sha256"][group_id])
            executions.append({"group_id": group_id, "driver_sha256": row["diagnostic_driver_sha256"][group_id],
                "execution": execution})
        recorded_cost = {"actual_public_driver_executions": len(executions),
            "sandbox_elapsed_seconds": sum(item["execution"]["elapsed_seconds"] for item in executions),
            "model_calls": 0, "model_output_tokens": 0, "team_run_tests_charged": 0}
        receipt = {"version": DIAGNOSTIC_VERSION, "case_id": case_id, "origin": "environment_preparation",
            "model_generated": False, "initial_files_sha256": files_sha,
            "source_manifest_sha256": value["source_contract"]["source_manifest_sha256"],
            "diagnostics": diagnostics, "executions": executions, "recorded_preparation_cost": recorded_cost,
            "scope": "Original measured public preparation; not current-member actions, autonomous discovery or private acceptance."}
        atomic_write(receipt_path, json_bytes(receipt))
        if not all(item["executed"] and item["counts"]["failed"] > 0 and item["counts"]["passed"] > 0
                   for item in diagnostics.values()):
            raise ValueError("Initial public preparation must preserve complete real passing and failing observations in both groups; receipt retained")
        cached = {"diagnostics": copy.deepcopy(diagnostics), "recorded_cost": recorded_cost,
            "receipt": {"path": str(receipt_path), "sha256": digest(receipt_path.read_bytes())}}
        _INITIAL_DIAGNOSTIC_CACHE[key] = cached
    result = {"version": DIAGNOSTIC_VERSION, "case_id": case_id,
        "initial_files_sha256": files_sha, **copy.deepcopy(cached["diagnostics"]),
        "preparation_provenance": {"origin": "environment_preparation", "model_generated": False,
            "autonomous_discovery": False, "cache_reuse": cache_reuse,
            "cache_scope": "same_process_exact_initial_files_and_frozen_public_drivers",
            "source_receipt": copy.deepcopy(cached["receipt"]),
            "source_recorded_preparation_cost": copy.deepcopy(cached["recorded_cost"]),
            "scope": "Controller-only provenance. Do not place receipt paths or earlier episode metadata in member observations."},
        "preparation_cost": {"actual_public_driver_executions": 0 if cache_reuse else 2,
            "sandbox_elapsed_seconds": 0.0 if cache_reuse else cached["recorded_cost"]["sandbox_elapsed_seconds"],
            "prepare_function_wall_seconds": time.monotonic() - started,
            "model_calls": 0, "model_output_tokens": 0, "team_run_tests_charged": 0}}
    return result
