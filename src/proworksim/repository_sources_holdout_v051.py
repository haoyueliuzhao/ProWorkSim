"""Independent held-out source provider; content requires a qualified frozen manifest.

Imports perform no source access. CPU fixtures require explicit opt-in; formal
materials are never selected or repaired according to held-out model outcomes.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import uuid

from .storage import digest, json_bytes

VERSION = "holdout-repository-sources-v0.51"
PURPOSE = "held_out_checkpoint_evaluation"
HOLD_IDS = tuple(f"hold-{repo}-{number}" for repo in ("funcy", "python-slugify", "iniconfig", "dominate") for number in (1, 2))
MAX_FILES = 200
MAX_SOURCE_BYTES = 2_000_000


def _read(path):
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def _safe_files(files):
    if (not isinstance(files, dict) or not files or len(files) > MAX_FILES
            or any(not isinstance(name, str) or not isinstance(text, str) for name, text in files.items())
            or sum(len(text.encode()) for text in files.values()) > MAX_SOURCE_BYTES):
        raise ValueError("Repository file map exceeds its fixed text bounds")
    for name in files:
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or ".git" in path.parts
                or str(path) != name or not path.parts):
            raise ValueError("Only normalized relative source files without Git history are admitted")


class RepositorySources:
    def __init__(self, source_root, *, runner=None, expected_manifest_sha256=None, allow_cpu_fixture=False):
        self.root = Path(source_root).resolve()
        manifest_path = self.root / "holdout/adapter-manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        self.manifest_sha256 = digest(manifest_bytes)
        if expected_manifest_sha256 and self.manifest_sha256 != expected_manifest_sha256:
            raise ValueError("Frozen repository adapter manifest changed")
        manifest = json.loads(manifest_bytes)
        if manifest.get("version") != "v051-holdout-adapter-source-manifest-v1":
            raise ValueError("Declare the independent frozen HOLD source manifest")
        fixture = manifest.get("fixture_only") is True
        if (fixture and allow_cpu_fixture is not True) or (not fixture and allow_cpu_fixture):
            raise ValueError("CPU fixture mode and formal HOLD source mode cannot be mixed")
        if manifest.get("purpose") != PURPOSE:
            raise ValueError("The held-out evaluation purpose must be explicit")
        if not fixture and (manifest.get("source_qualification_complete") is not True
                or not manifest.get("source_access_release") or not manifest.get("common_implementation_freeze")):
            raise ValueError("Formal HOLD content requires prior source release, common freeze and completed qualification")
        self.fixture_only = fixture
        self.runner = runner
        self.cpu_python = manifest["cpu_venv_python_invocation"]
        self._cases, self.blocked_cases = {}, {}
        self.all_case_ids = tuple(row["task_id"] for row in manifest["tasks"])
        if ((not fixture and self.all_case_ids != HOLD_IDS) or (fixture and (not self.all_case_ids
                or any(not name.startswith("cpu-hold-") for name in self.all_case_ids)))
                or len(set(self.all_case_ids)) != len(self.all_case_ids)):
            raise ValueError("The fixed eight HOLD tasks or explicit synthetic fixture IDs are required")
        for row in manifest["tasks"]:
            if row["partition"] != "HOLD":
                raise ValueError("This provider cannot consume CAL material")
            if row["qualification_passed"] is not True:
                self.blocked_cases[row["task_id"]] = copy.deepcopy(row.get("blocked_reason", "qualification_not_passed"))
                continue
            initial_path = self.root / row["source_binding"]["initial_files_path"]
            initial_bytes = initial_path.read_bytes()
            if digest(initial_bytes) != row["source_binding"]["initial_files_sha256"]:
                raise ValueError("Frozen faulty-tree bytes changed")
            files = json.loads(initial_bytes)["files"]
            _safe_files(files)
            if {name: digest(text.encode()) for name, text in files.items()} != row["source_binding"]["file_sha256"]:
                raise ValueError("Frozen faulty file map changed")
            task_bytes = (self.root / row["row_path"]).read_bytes()
            if digest(task_bytes) != row["row_sha256"]:
                raise ValueError("Original dataset task row changed")
            original = json.loads(task_bytes)
            nodeids = sorted(set(original["FAIL_TO_PASS"] + original["PASS_TO_PASS"]))
            if (nodeids != row["public_test_nodeids"] or not nodeids
                    or set(original["FAIL_TO_PASS"]) & set(original["PASS_TO_PASS"])):
                raise ValueError("Complete original test denominator changed")
            if (row.get("test_engine") not in {"pytest", "native_unittest"} or not isinstance(row.get("engine_spec"), dict)
                    or not isinstance(row.get("target_modules"), list) or not row["target_modules"]):
                raise ValueError("Bind the native engine and candidate module origins")
            editable = list(row["editable_production_paths"])
            if not editable or not set(editable) <= set(files):
                raise ValueError("Declare all allowed production files")
            problem = original["problem_statement"]
            if not isinstance(problem, str) or not problem.strip():
                raise ValueError("The original problem statement is required")
            task_id = row["task_id"]
            if task_id in self._cases:
                raise ValueError("Duplicate frozen repository task")
            self._cases[task_id] = {
                "row": copy.deepcopy(row), "files": files, "editable_paths": editable,
                "problem_statement": problem, "nodeids": nodeids,
                "FAIL_TO_PASS": list(original["FAIL_TO_PASS"]), "PASS_TO_PASS": list(original["PASS_TO_PASS"]),
            }
        self.case_ids = tuple(self._cases)

    def _entry(self, case_id):
        if case_id not in self._cases:
            raise ValueError("Only a pre-frozen HOLD repository task is admitted")
        return self._cases[case_id]

    def build_case(self, case_id):
        entry = self._entry(case_id)
        row, files = entry["row"], entry["files"]
        requirements_sha = digest(entry["problem_statement"].encode())
        test_sha = digest(json_bytes(entry["nodeids"]))
        source = {
            "source_asset_ids": [row["instance_id"]],
            "source_environment_asset_ids": [row["upstream_repository"] + "@" + row["upstream_commit"]],
            "source_revision": row["upstream_commit"], "source_environment": row["upstream_repository"],
            "source_kind": "public_repository_with_swesmith_synthetic_defect",
            "task_authorship": "original_swesmith_generated_problem_statement",
            "external_upstream_bug_claim": False, "external_repository_count": 4,
            "source_manifest_sha256": self.manifest_sha256,
            "source_partition_sha256": self.manifest_sha256,
            "requirements_sha256": requirements_sha,
            "public_checks_sha256": test_sha, "independent_verifier_sha256": test_sha,
            "public_driver_sha256": test_sha, "independent_driver_sha256": test_sha,
            "driver_digest_scope": "Complete original native test-ID inventory; executor identity is recorded separately",
            "public_requirements": entry["problem_statement"],
            "complete_delivery_requires": ["original_repository_problem", "all_original_repository_tests",
                                           "current_tested_fixed_submission"],
            "contract_symbols": {}, "public_production_files": list(entry["editable_paths"]),
            "member_test_file": None,
            "readonly_support_files": sorted(set(files) - set(entry["editable_paths"])),
            "initial_code_origin": "original_upstream_plus_frozen_swesmith_defect",
            "initial_code_model_generated": False,
            "initial_diagnostic_origin": "none_no_automatic_test",
            "initial_diagnostics_public_to_all_members": True,
            "forced_initial_failure_feedback": False, "purpose": PURPOSE, "holdout_evaluation": True,
            "training_eligible": False, "contribution_eligible": False, "independent_confirmation_eligible": False,
        }
        return {
            "version": VERSION, "task_id": case_id, "family": row["upstream_repository"],
            "purpose": PURPOSE, "holdout_evaluation": True, "training_eligible": False, "contribution_eligible": False,
            "independent_confirmation_eligible": False, "category": "heldout_repository_evaluation",
            "files": copy.deepcopy(files), "editable_paths": list(entry["editable_paths"]),
            "root_goal": entry["problem_statement"], "task_definitions": {}, "initial_owners": {},
            "source_partition_sha256": self.manifest_sha256, "source_contract": source,
            "initial_binding": {"new_contract_sha256": requirements_sha,
                "initial_files_sha256": digest(json_bytes(files)),
                "initial_application_sha256": {name: digest(files[name].encode()) for name in entry["editable_paths"]},
                **{key: source[key] for key in ("public_driver_sha256", "independent_driver_sha256",
                    "public_checks_sha256", "independent_verifier_sha256", "source_manifest_sha256", "source_partition_sha256")}},
        }

    def case_spec(self, case_id):
        return self.build_case(case_id)

    def validate_files(self, case_id, files):
        entry = self._entry(case_id)
        _safe_files(files)
        if set(files) != set(entry["files"]):
            raise ValueError("Only the declared original repository file set is accepted")
        readonly = set(files) - set(entry["editable_paths"])
        if any(files[name] != entry["files"][name] for name in readonly):
            raise ValueError("Original tests, configuration and supporting source are read-only")

    def runner_spec(self, case_id):
        entry = self._entry(case_id)
        row = entry["row"]
        return {
            "version": VERSION, "task_id": case_id, "nodeids": list(entry["nodeids"]),
            "module": row["source_roots"][0].rstrip("/").removesuffix(".py"),
            "test_engine": row["test_engine"], "engine_spec": copy.deepcopy(row["engine_spec"]),
            "target_modules": list(row["target_modules"]),
            "original_test_ids": list(entry["nodeids"]),
            "config_relative_path": row["pytest_config_in_repo"],
            "cpu_python": row.get("cpu_python", self.cpu_python),
            "loopback_fixture": None,
            "source_roots": list(row["source_roots"]),
            "readonly_paths": sorted(set(entry["files"]) - set(entry["editable_paths"])),
            "frozen_test_hashes": {name: digest(text.encode()) for name, text in entry["files"].items()
                                   if name not in entry["editable_paths"]},
            "initial_production_hashes": {name: digest(entry["files"][name].encode())
                                          for name in entry["editable_paths"]},
            "source_manifest_sha256": self.manifest_sha256,
        }

    def _execute(self, case_id, files, *, run_root):
        self.validate_files(case_id, files)
        if self.runner is None:
            raise RuntimeError("No confined held-out test executor has been bound")
        execution_root = Path(run_root) / ("execution-" + uuid.uuid4().hex)
        result = self.runner(files=copy.deepcopy(files), task=self.runner_spec(case_id), run_root=execution_root)
        if not isinstance(result, dict):
            raise RuntimeError("Repository executor did not return a provenance receipt")
        expected_sha = digest(json_bytes(files))
        if result.get("input_files_sha256") != expected_sha:
            raise RuntimeError("Repository test receipt does not bind the exact candidate file map")
        tests = result.get("tests", [])
        indexed = {test["nodeid"]: test for test in tests}
        nodeids = self._entry(case_id)["nodeids"]
        common = (result.get("executed") is True and result.get("source_unchanged") is True
                  and result.get("target_origin_bound") is True
                  and result.get("original_id_bijection") is True and result.get("engine_protocol_valid") is True
                  and result.get("test_integrity") is True and len(indexed) == len(tests)
                  and set(indexed) <= set(nodeids))
        all_observed = (set(indexed) == set(nodeids)
                        and all(test.get("outcome") in ("passed", "failed", "error", "skipped") for test in tests))
        code_collection_failure = (result.get("source_attributable_collection_failure") is True
                                   and result.get("returncode") in (2, 4))
        complete = common and ((all_observed and result.get("returncode") in (0, 1)) or code_collection_failure)
        normalized = []
        for nodeid in nodeids:
            observed = nodeid in indexed
            outcome = indexed.get(nodeid, {}).get("outcome", "not_run_due_to_code_collection_failure"
                                                 if code_collection_failure else "missing")
            row = {"test_id": nodeid, "group": "repository_tests", "requirement_group": "original_repository_test",
                   "passed": outcome == "passed" if complete else None,
                   "observed": {"test_status": outcome, "node_outcome_observed": observed},
                   "node_outcome_observed": observed}
            if observed and indexed[nodeid].get("longreprtext"):
                row["text"] = indexed[nodeid]["longreprtext"]
            normalized.append(row)
        execution = {"executed": complete, "driver_completed": complete,
            "test_engine": result.get("test_engine"),
            "target_module_files": copy.deepcopy(result.get("target_module_files", {})),
            "target_origin_bound": result.get("target_origin_bound"),
            "target_imports_from_this_tree": result.get("target_imports_from_this_tree"),
            "original_id_bijection": result.get("original_id_bijection"),
            "engine_protocol_valid": result.get("engine_protocol_valid"),
            "command_executed": result.get("command_executed", result.get("executed")),
            "all_expected_tests_observed": all_observed,
            "source_attributable_collection_failure": code_collection_failure,
            "collection_errors": copy.deepcopy(result.get("collection_errors", [])),
            "missing_test_ids": sorted(set(nodeids) - set(indexed)),
            "unexpected_test_ids": sorted(set(indexed) - set(nodeids)),
            "returncode": result.get("returncode"), "timeout": result.get("timeout", False),
            "output": result.get("stdout", ""), "output_truncated": result.get("output_truncated", False),
            "elapsed_seconds": result.get("elapsed_seconds"), "isolation": result.get("isolation"),
            "input_files_sha256": expected_sha, "source_unchanged": result.get("source_unchanged"),
            "test_integrity": result.get("test_integrity"), "loopback_fixture": result.get("loopback_fixture"),
            "evidence": result.get("evidence"),
            "scope": "Original full native test-ID inventory. Candidate-bound collection failure is known code failure; unexecuted nodes remain explicit. Host/plugin/isolation faults remain unknown."}
        return normalized, execution

    def run_public_tests(self, case_id, files, *, run_root):
        tests, execution = self._execute(case_id, files, run_root=run_root)
        executed = execution["executed"]
        passed = executed and all(row["passed"] is True for row in tests)
        groups = {"repository_tests": {"executed": executed, "passed": passed if executed else None,
            "status": "passed" if passed else "failed" if executed else "untested", "tests": tests,
            "execution": execution}}
        return {"execution": execution, "tests": tests, "groups": groups, "passed": passed,
            "public_diagnostics": {}, "repository_collection_errors": execution["collection_errors"],
            "authority": "original_swesmith_repository_tests",
            "group_name_scope": "All original F2P/P2P nodes in a single public union; original labels are not exposed"}

    def assess_files(self, case_id, files, *, run_root):
        tests, execution = self._execute(case_id, files, run_root=run_root)
        executed = execution["executed"]
        passed = executed and all(row["passed"] is True for row in tests)
        entry = self._entry(case_id)
        f2p = set(entry["FAIL_TO_PASS"])
        checks = [{"case_id": row["test_id"], "group": "FAIL_TO_PASS" if row["test_id"] in f2p else "PASS_TO_PASS",
            "expected": {"test_status": "passed"}, "observed": row["observed"], "passed": row["passed"]}
                  for row in tests]
        independent = {"version": VERSION, "task_id": case_id, "passed": passed,
            "checks": checks, "execution": execution, "fixture_sha256": digest(json_bytes(entry["nodeids"])),
            "expected_values_sent_to_worker": False}
        return {"version": VERSION, "task_id": case_id, "purpose": PURPOSE, "holdout_evaluation": True, "usage": PURPOSE,
            "executed": executed, "passed": passed, "training_eligible": False,
            "contribution_eligible": False, "independent_confirmation_eligible": False,
            "components": {"all_original_repository_tests": passed, "frozen_test_source_integrity": execution["test_integrity"]},
            "observed_pass_fraction": sum(row["passed"] is True for row in tests) / len(tests) if executed else None,
            "test_nodes_observed": sum(row["node_outcome_observed"] for row in tests),
            "all_expected_tests_observed": execution["all_expected_tests_observed"],
            "measurement_scope": "Observed passed nodes / frozen original denominator; a candidate-bound collection failure contributes no proved passes for its unexecuted nodes, not a claim those node bodies ran and failed",
            "source_attributable_collection_failure": execution["source_attributable_collection_failure"],
            "independent_acceptance": independent, "public_acceptance": {"execution": execution, "passed": passed},
            "content_correct": passed if executed else None,
            "required_process_satisfied": True if executed else None,
            "process_observation_complete": executed, "dimension_checks": [],
            "scope": "Same frozen complete test set as public testing; host score groups never alter task or test code"}
