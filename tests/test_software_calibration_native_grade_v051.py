"""Three pure CPU/fake-runner controls; no repository pytest or model work."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from proworksim.software_calibration_native_grade_v051 import canonical_grading_tree, grade_native_candidate
from proworksim.software_calibration_repo_tests_v051 import VERSION as RUNNER_VERSION
from proworksim.storage import digest, json_bytes


def test_canonical_restores_readonly_and_absent_config_but_keeps_production_add_delete():
    original = {"parse.py": "old production", "tests/test_parse.py": "original test", "README.rst": "original support"}
    candidate = {"tests/test_parse.py": "tampered", "helper.py": "new production", "conftest.py": "tampered",
        "pytest.ini": "tampered", ".pytest.ini": "tampered", "pyproject.toml": "tampered", "setup.cfg": "tampered",
        "tox.ini": "tampered", "setup.py": "tampered", "sitecustomize.py": "tampered", "new.txt": "notes"}
    before = copy.deepcopy(candidate)
    files, receipt = canonical_grading_tree(original, ["parse.py"], candidate, module="parse")
    assert files == {"tests/test_parse.py": "original test", "README.rst": "original support", "helper.py": "new production"}
    assert receipt["deleted_production_paths"] == ["parse.py"]
    assert receipt["accepted_new_production_paths"] == ["helper.py"]
    assert receipt["modified_readonly_paths"] == ["tests/test_parse.py"]
    assert receipt["deleted_readonly_paths_restored"] == ["README.rst"] and candidate == before
    empty, empty_receipt = canonical_grading_tree(original, ["parse.py"], {}, module="parse")
    assert empty == {name: text for name, text in original.items() if name != "parse.py"}
    assert empty_receipt["deleted_production_paths"] == ["parse.py"]
    package, r = canonical_grading_tree({"boltons/a.py": "old", "tests/t.py": "test"}, ["boltons/a.py"],
        {"boltons/a.py": "edit", "boltons/helper.py": "new", "boltons/conftest.py": "bad", "helper.py": "outside"}, module="boltons")
    assert package == {"boltons/a.py": "edit", "tests/t.py": "test", "boltons/helper.py": "new"}
    assert r["accepted_new_production_paths"] == ["boltons/helper.py"]
    with pytest.raises(ValueError, match="normalized"):
        canonical_grading_tree(original, ["parse.py"], {"../escape.py": "bad"}, module="parse")


def fixture_provider(mode="partial"):
    original = {"parse.py": "old", "tests/test_parse.py": "original"}
    nodes = ["tests/test_parse.py::test_a", "tests/test_parse.py::test_b"]
    calls = []

    def runner(*, files, task, run_root):
        calls.append((copy.deepcopy(files), copy.deepcopy(task)))
        assert task["initial_file_paths"] == sorted(original)
        assert task["accepted_new_production_paths"] == ["helper.py"]
        result = {"version": RUNNER_VERSION, "executed": True, "command_executed": True,
            "returncode": 1, "worker_returncode": 0, "timed_out": False, "source_unchanged": True,
            "test_integrity": True, "frozen_test_files_match": True,
            "input_files_sha256": digest(json_bytes(files)),
            "original_nodeids_sha256": hashlib.sha256(json.dumps(nodes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "tests": [{"nodeid": nodes[0], "outcome": "passed"}, {"nodeid": nodes[1], "outcome": "failed"}],
            "missing_test_ids": [], "unexpected_test_ids": [], "collection_errors": [],
            "accepted_new_production_paths": ["helper.py"], "source_attributable_collection_failure": False}
        if mode != "partial":
            result.update(returncode=4, tests=[], missing_test_ids=nodes,
                source_attributable_collection_failure=True, collection_errors=[{"attributed": True}])
        if mode == "unbound":
            result["collection_errors"] = [{"attributed": False}]
        if mode == "mismatch":
            result["input_files_sha256"] = "wrong"
        if mode == "infra":
            result["worker_returncode"] = -9
        return result

    return SimpleNamespace(runner=runner, build_case=lambda task_id: {"files": original, "editable_paths": ["parse.py"]},
        runner_spec=lambda task_id: {"task_id": task_id, "module": "parse", "nodeids": nodes,
            "frozen_test_hashes": {"tests/test_parse.py": digest(original["tests/test_parse.py"].encode())},
            "initial_production_hashes": {"parse.py": digest(original["parse.py"].encode())}}), calls


def test_grade_calls_shared_runner_once_and_binds_partial_original_denominator(tmp_path):
    provider, calls = fixture_provider()
    candidate = {"parse.py": "edit", "helper.py": "new", "tests/test_parse.py": "tampered"}
    result = grade_native_candidate(provider=provider, task_id="cal2-fake", candidate_files=candidate, run_root=tmp_path / "grade")
    assert len(calls) == 1 and calls[0][0]["tests/test_parse.py"] == "original"
    assert result["executed"] is True and result["R_code"] == 0 and result["Q_task"] == .5
    assert result["test_nodes_observed"] == 2 and result["host_final_test_executions"] == 1
    assert json.loads((tmp_path / "grade/raw-candidate-files.json").read_text()) == candidate


def test_only_bound_collection_is_code_zero_and_unrun_nodes_are_explicit(tmp_path):
    for mode in ("bound", "unbound", "mismatch", "infra"):
        provider, calls = fixture_provider(mode)
        result = grade_native_candidate(provider=provider, task_id="cal2-fake",
            candidate_files={"helper.py": "new invalid source"}, run_root=tmp_path / mode)
        assert len(calls) == 1
        assert result["executed"] is (mode == "bound")
        assert result["R_code"] == (0 if mode == "bound" else None)
        assert result["Q_task"] == (0.0 if mode == "bound" else None)
        assert result["test_nodes_observed"] == 0
        for row in result["checks"]:
            assert row["node_outcome_observed"] is False
            assert row["pytest_status"] == ("not_run_due_to_code_collection_failure" if mode == "bound" else "missing")
