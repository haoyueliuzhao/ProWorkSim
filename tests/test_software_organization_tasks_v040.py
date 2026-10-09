"""Narrow CPU controls for inherited business contracts and real initial diagnoses."""
import ast
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path

import pytest

from proworksim import software_organization_tasks_v039 as parent
from proworksim import software_organization_tasks_v040 as source
from proworksim.storage import digest, json_bytes


@pytest.fixture(scope="module")
def controls(tmp_path_factory):
    root = Path(os.environ.get("PROWORKSIM_V040_SOURCE_CONTROL_RUN", str(tmp_path_factory.mktemp("v040-task-controls"))))
    source._INITIAL_DIAGNOSTIC_CACHE.clear()

    def run(case_id):
        initial = source.build_case(case_id)
        diagnostics = source.prepare_initial_diagnostics(case_id, root / case_id / "initial-diagnostics")
        public = source.run_public_tests(case_id, initial["files"], run_root=root / case_id / "public-rerun")
        variants = {"reference": source.reference_solution(case_id), **source.provenance_controls(case_id)}
        checked = {name: source.assess_files(case_id, files, run_root=root / case_id / name)
                   for name, files in variants.items()}
        return case_id, {"diagnostics": diagnostics, "baseline_public": public, **checked}

    with ThreadPoolExecutor(max_workers=2) as executor:
        result = dict(executor.map(run, source.CASE_IDS))
    proof = {"version": source.VERSION, "scope": "Finite CPU task and public-preparation controls only",
        "new_model_calls": 0, "gpu_used": False, "backward_calls": 0,
        "source_manifest_sha256": source.source_manifest()["sha256"],
        "actual_isolated_public_preparation_executions": 4,
        "actual_isolated_baseline_public_reruns": 2,
        "actual_reference_and_bypass_programs": 6,
        "actual_isolated_quality_executions": 12,
        "actual_isolated_executions_total": 18,
        "baseline_private_acceptance_executed": False,
        "rows": [{"case_id": case_id,
            "diagnostics": row["diagnostics"],
            "baseline_public": {"passed": row["baseline_public"]["passed"],
                "groups": {g: {"passed": v["passed"], "executed": v["executed"], "count": len(v["tests"])}
                           for g, v in row["baseline_public"]["groups"].items()}},
            "quality_controls": {name: {key: row[name][key] for key in ("executed", "passed", "content_correct", "required_process_satisfied", "process_observation_complete")}
                for name in ("reference", "library_bypass", "product_bypass")}}
            for case_id, row in result.items()]}
    root.mkdir(parents=True, exist_ok=True)
    (root / "qualification.json").write_bytes(json_bytes(proof))
    return result


@pytest.mark.parametrize("case_id", source.CASE_IDS)
def test_handoff_variant_preserves_business_inputs_apis_and_has_no_hidden_preparation_answers(case_id):
    value = source.build_case(case_id)
    original = parent.build_case(source.ORIGINAL_IDS[case_id])
    manifest, row, directory = source._entry(case_id)
    assert value["root_goal"].split("# Work and acceptance")[0] == original["root_goal"].split("# Work and acceptance")[0]
    assert value["editable_paths"] == original["editable_paths"]
    assert value["source_contract"]["contract_symbols"] == original["source_contract"]["contract_symbols"]
    assert value["source_contract"]["old_contract_reused"] is True
    assert value["new_root"] is False and value["handoff_variant"] is True
    assert value["initial_code_origin"] == "environment_preparation"
    assert value["initial_code_model_generated"] is False
    assert value["task_definitions"] == value["initial_owners"] == {}
    assert value["purpose"] == "organization_development"
    assert not value["training_eligible"] and not value["contribution_eligible"] and not value["independent_confirmation_eligible"]
    assert not any(any(word in name for word in ("acceptance", "reference", "controls", "diagnostic", "provenance")) for name in value["files"])
    assert "compatibility_gaps" not in value["source_contract"]
    assert "initial_diagnostics" not in value["source_contract"]
    for path in row["editable_paths"]:
        ast.parse(value["files"][path])
        assert "NotImplementedError" not in value["files"][path]
    for name in ("public-checks.json", "acceptance.json"):
        inherited = json.loads((parent.ASSETS / source.ORIGINAL_IDS[case_id] / name).read_text())
        variant = json.loads((directory / name).read_text())
        assert variant["cases"] == inherited["cases"]
    assert value["initial_binding"]["initial_files_sha256"] == digest(json_bytes(value["files"]))
    assert manifest["source_partition_sha256"] == source.source_partition()["sha256"]
    changed = copy.deepcopy(value["files"])
    changed["contract.md"] += "\nWeaker contract"
    with pytest.raises(ValueError, match="editable"):
        source._validate_files(case_id, changed)


@pytest.mark.parametrize("case_id", source.CASE_IDS)
def test_two_actual_public_diagnoses_reproduce_baseline_results_without_a_repair_plan(controls, case_id):
    row = controls[case_id]
    prepared, public = row["diagnostics"], row["baseline_public"]
    assert public["passed"] is False
    assert public["groups"]["upstream_regressions"]["passed"] is True
    assert public["groups"]["public_normal"]["executed"] is True
    assert any(test["passed"] for test in public["groups"]["public_normal"]["tests"])
    assert prepared["preparation_cost"]["actual_public_driver_executions"] == 2
    assert prepared["preparation_cost"]["team_run_tests_charged"] == 0
    assert prepared["preparation_cost"]["model_calls"] == 0
    assert prepared["preparation_provenance"]["cache_reuse"] is False
    expected_fails = ({"diagnostic_a": ["report-group-order"], "diagnostic_b": ["query-original-positions"]}
        if case_id == source.CASE_IDS[0] else
        {"diagnostic_a": ["catalog-first-last", "catalog-table"], "diagnostic_b": ["catalog-query-repeats"]})
    for group in source.DIAGNOSTIC_IDS:
        initial, rerun = prepared[group], public["public_diagnostics"][group]
        assert initial["diagnostic_id"] == case_id + ":" + group == rerun["diagnostic_id"]
        assert initial["origin"] == "environment_initial_diagnostic"
        assert initial["model_generated"] is initial["autonomous_discovery"] is False
        assert rerun["origin"] == "member_public_test_execution"
        assert initial["executed"] is True and initial["passed"] is False
        assert initial["counts"]["passed"] > 0 and initial["counts"]["failed"] > 0
        assert initial["failed_test_ids"] == expected_fails[group]
        for key in ("files_sha256", "tests", "counts", "failed_test_ids"):
            assert initial[key] == rerun[key]
        rendered = json.dumps(initial)
        assert "source_api_trace" not in rendered and "receipt" not in rendered
        assert "/tmp/" not in rendered and str(source.ROOT) not in rendered
        assert "compatibility_gaps" not in rendered and "reference/" not in rendered
        assert "repair_plan" not in initial and "assigned_member" not in initial


@pytest.mark.parametrize("case_id", source.CASE_IDS)
def test_complete_reference_passes_and_api_product_reverse_controls_remain_effective(controls, case_id):
    variants = controls[case_id]
    reference = variants["reference"]
    assert reference["executed"] is True and reference["passed"] is True
    assert reference["content_correct"] and reference["required_process_satisfied"] and reference["process_observation_complete"]
    assert all(value["passed"] for value in reference["public_acceptance"]["public_diagnostics"].values())
    for kind in ("library_bypass", "product_bypass"):
        result = variants[kind]
        assert result["executed"] and not result["passed"]
        assert result["content_correct"] is True and result["required_process_satisfied"] is False
        assert result["process_observation_complete"] is True
    for check in variants["product_bypass"]["independent_acceptance"]["checks"]:
        used = check["observed"]["source_api_used"]
        assert used["schema.Schema.validate"] is True
        if check["group"].startswith("consumer"):
            assert any(not value for key, value in used.items() if key != "schema.Schema.validate")


@pytest.mark.parametrize("case_id", source.CASE_IDS)
def test_exact_preparation_cache_reuse_has_zero_new_executions_and_no_caller_metadata(controls, tmp_path, monkeypatch, case_id):
    prepared = controls[case_id]["diagnostics"]

    def no_execution(*args, **kwargs):
        raise AssertionError("Reusing an exact initial preparation must not rerun public checks")

    monkeypatch.setattr(source, "run_isolated", no_execution)
    second = source.prepare_initial_diagnostics(case_id, tmp_path / "second-use")
    assert second["preparation_provenance"]["cache_reuse"] is True
    assert second["preparation_cost"]["actual_public_driver_executions"] == 0
    assert second["preparation_cost"]["sandbox_elapsed_seconds"] == 0
    assert second["preparation_cost"]["team_run_tests_charged"] == 0
    assert second["preparation_provenance"]["source_recorded_preparation_cost"]["actual_public_driver_executions"] == 2
    assert second["preparation_provenance"]["source_receipt"] == prepared["preparation_provenance"]["source_receipt"]
    assert all(second[group] == prepared[group] for group in source.DIAGNOSTIC_IDS)
    second["diagnostic_a"]["source_reference"] = {"object_id": "caller-world", "version_id": "v999"}
    second["diagnostic_a"]["tests"][0]["passed"] = "caller mutation"
    third = source.prepare_initial_diagnostics(case_id, tmp_path / "third-use")
    assert "source_reference" not in third["diagnostic_a"]
    assert type(third["diagnostic_a"]["tests"][0]["passed"]) is bool
    assert all(third[group] == prepared[group] for group in source.DIAGNOSTIC_IDS)
