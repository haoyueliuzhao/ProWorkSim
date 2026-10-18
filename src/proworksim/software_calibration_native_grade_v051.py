"""CAL-2 R terminal grading under frozen original tests; no P/U permission change."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

from .software_calibration_repo_tests_v051 import VERSION as RUNNER_VERSION
from .storage import atomic_write, digest, json_bytes

VERSION = "v051-native-authoritative-grading-v1"
CONFIG_NAMES = frozenset({"conftest.py", "pytest.ini", ".pytest.ini", "pyproject.toml",
    "setup.cfg", "setup.py", "tox.ini", "noxfile.py", "sitecustomize.py", "usercustomize.py", "pytest.py"})


def _validate_files(files, *, allow_empty=False):
    if (not isinstance(files, dict) or (not files and not allow_empty) or len(files) > 5000
            or any(not isinstance(name, str) or not isinstance(text, str) for name, text in files.items())
            or sum(len(text.encode()) for text in files.values()) > 33554432):
        raise ValueError("A finite complete text candidate is required")
    for name in files:
        path = PurePosixPath(name)
        if (not path.parts or path.is_absolute() or str(path) != name or ".." in path.parts
                or ".git" in path.parts or "\\" in name or "\x00" in name):
            raise ValueError("Candidate paths must be normalized repository-relative files")


def _new_production(name, module):
    path = PurePosixPath(name)
    if path.name in CONFIG_NAMES or path.suffix != ".py" or not path.stem.isidentifier():
        return False
    if module == "boltons":
        return len(path.parts) >= 2 and path.parts[0] == "boltons" and all(p.isidentifier() for p in path.parts[:-1])
    return module in {"parse", "xmltodict"} and len(path.parts) == 1


def canonical_grading_tree(initial_files, editable_paths, candidate_files, *, module):
    """Restore original readonly bytes/absence; retain declared production edits."""
    _validate_files(initial_files)
    _validate_files(candidate_files, allow_empty=True)
    if module not in {"boltons", "parse", "xmltodict"}:
        raise ValueError("Only the frozen CAL-2 repository modules are admitted")
    if (not isinstance(editable_paths, (list, tuple)) or not editable_paths
            or len(set(editable_paths)) != len(editable_paths) or not set(editable_paths) <= set(initial_files)
            or any(not _new_production(name, module) for name in editable_paths)):
        raise ValueError("Bind the original declared production path inventory")
    editable = set(editable_paths)
    readonly = set(initial_files) - editable
    files = {name: text for name, text in initial_files.items() if name in readonly}
    files.update({name: candidate_files[name] for name in editable if name in candidate_files})
    new = sorted(set(candidate_files) - set(initial_files))
    accepted = [name for name in new if _new_production(name, module)]
    files.update({name: candidate_files[name] for name in accepted})
    _validate_files(files)
    receipt = {"version": VERSION, "module": module,
        "initial_files_sha256": digest(json_bytes(initial_files)),
        "candidate_files_sha256": digest(json_bytes(candidate_files)),
        "grading_files_sha256": digest(json_bytes(files)),
        "accepted_new_production_paths": accepted,
        "deleted_production_paths": sorted(editable - set(candidate_files)),
        "modified_readonly_paths": sorted(name for name in readonly if name in candidate_files and candidate_files[name] != initial_files[name]),
        "deleted_readonly_paths_restored": sorted(readonly - set(candidate_files)),
        "excluded_new_paths": sorted(set(new) - set(accepted)),
        "restored_readonly_paths": sorted(readonly), "original_candidate_modified": False,
        "new_production_rule": "Existing production edits/deletions; new identifier-named .py within boltons/ or top-level parse/xmltodict helper; reserved pytest/config/startup names excluded",
        "reserved_new_names": sorted(CONFIG_NAMES),
        "original_configuration_absence_restored": True,
        "scope": "R-only authoritative grading tree. Raw candidate retained separately; no P/U permission change."}
    return files, receipt


def _outcomes(execution, *, files, task):
    nodes = task["nodeids"]
    tests = execution.get("tests", [])
    indexed = {row.get("nodeid"): row for row in tests if isinstance(row, dict)}
    expected_node_sha = hashlib.sha256(json.dumps(nodes, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    common = (execution.get("version") == RUNNER_VERSION
        and execution.get("input_files_sha256") == digest(json_bytes(files))
        and execution.get("original_nodeids_sha256") == expected_node_sha
        and execution.get("executed") is execution.get("command_executed") is True
        and execution.get("worker_returncode") == 0 and execution.get("timed_out") is False
        and execution.get("source_unchanged") is execution.get("test_integrity") is True
        and execution.get("frozen_test_files_match") is True
        and not execution.get("unexpected_test_ids") and len(indexed) == len(tests)
        and set(indexed) <= set(nodes)
        and execution.get("missing_test_ids") == sorted(set(nodes) - set(indexed)))
    full = set(indexed) == set(nodes) and all(row.get("outcome") in {"passed", "failed", "error", "skipped"} for row in tests)
    errors = execution.get("collection_errors", [])
    source_failure = (execution.get("source_attributable_collection_failure") is True
        and execution.get("returncode") in (2, 4) and bool(errors)
        and all(row.get("attributed") is True for row in errors)
        and execution.get("accepted_new_production_paths") == task["accepted_new_production_paths"])
    known = bool(common and ((full and execution.get("returncode") in (0, 1)) or source_failure))
    checks = [{"nodeid": node, "node_outcome_observed": node in indexed,
        "pytest_status": indexed[node]["outcome"] if node in indexed else
            "not_run_due_to_code_collection_failure" if known and source_failure else "missing",
        "passed": indexed.get(node, {}).get("outcome") == "passed" if known else None} for node in nodes]
    passed = sum(row["passed"] is True for row in checks)
    return {"executed": known, "R_code": int(full and passed == len(nodes) and execution.get("returncode") == 0) if known else None,
        "Q_task": passed / len(nodes) if known else None, "tests_passed": passed if known else None,
        "tests_total": len(nodes), "test_nodes_observed": len(indexed), "all_expected_tests_observed": full,
        "source_attributable_collection_failure": bool(known and source_failure), "checks": checks,
        "technical_unknown_reason": None if known else "Original runner, candidate, tests, termination or collection provenance incomplete",
        "measurement_scope": "Observed passed nodes / original frozen denominator. Unexecuted collection nodes contribute no proved passes; they are not claimed to have run."}


def grade_native_candidate(*, provider, task_id, candidate_files, run_root):
    """One immutable terminal assessment using the same injected shared runner."""
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=False)
    atomic_write(root / "raw-candidate-files.json", json_bytes(candidate_files))
    execution, canonical, score = None, None, None
    try:
        case = provider.build_case(task_id)
        task = provider.runner_spec(task_id)
        files, canonical = canonical_grading_tree(case["files"], case["editable_paths"], candidate_files, module=task["module"])
        task.update(initial_file_paths=sorted(case["files"]), accepted_new_production_paths=canonical["accepted_new_production_paths"])
        if task["nodeids"] != sorted(set(task["nodeids"])) or not task["nodeids"] or not callable(provider.runner):
            raise ValueError("The frozen sorted original node union and shared runner are required")
        if any(digest(files.get(name, "").encode()) != value for name, value in task["frozen_test_hashes"].items()):
            raise ValueError("Restored original test/config source binding differs")
        atomic_write(root / "grading-files.json", json_bytes(files))
        atomic_write(root / "canonical-tree-receipt.json", json_bytes(canonical))
        atomic_write(root / "runner-task.json", json_bytes(task))
        execution = provider.runner(files=copy.deepcopy(files), task=copy.deepcopy(task), run_root=root / "execution")
        atomic_write(root / "runner-receipt.json", json_bytes(execution))
        score = _outcomes(execution, files=files, task=task)
    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as error:
        score = {"executed": False, "R_code": None, "Q_task": None,
                 "technical_unknown_reason": {"type": type(error).__name__, "message": str(error)}}
    result = {"version": VERSION, "task_id": task_id, "endpoint": "terminal_working_tree_code_correctness", **score,
        "canonical_tree": canonical, "execution": execution,
        "candidate_files": str((root / "raw-candidate-files.json").resolve()),
        "grading_files": str((root / "grading-files.json").resolve()) if canonical else None,
        "candidate_files_sha256": digest(json_bytes(candidate_files)),
        "grading_files_sha256": canonical["grading_files_sha256"] if canonical else None,
        "host_final_test_executions": int(isinstance(execution, dict) and execution.get("command_executed") is True),
        "host_final_evaluation_attempts": 1, "actual_model_calls": 0,
        "scope": "Original native working tree and authoritative grading tree retained separately; no automatic retry, extra model feedback or project submit reinterpretation"}
    atomic_write(root / "terminal-code-assessment.json", json_bytes(result))
    return result
