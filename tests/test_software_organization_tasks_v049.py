"""Finite source-isolation and authored-business controls; no tokenizer/model/GPU."""
from concurrent.futures import ThreadPoolExecutor
import copy
import os
from pathlib import Path

import pytest

from proworksim import software_organization_tasks_v045 as old
from proworksim import software_organization_tasks_v049 as tasks
from proworksim.storage import atomic_write, digest, json_bytes


@pytest.fixture(scope="module")
def business_controls(tmp_path_factory):
    configured = os.environ.get("PROWORKSIM_V049_TASK_CONTROL_ROOT")
    root = Path(configured) if configured else tmp_path_factory.mktemp("v049-source-controls")
    root.mkdir(parents=True, exist_ok=True)

    def run(case_id):
        folder = root / case_id
        if (folder / "business-control-receipt.json").exists():
            raise FileExistsError("Use a fresh v049 CPU receipt destination")
        initial = tasks.build_case(case_id)
        initial_public = tasks.run_public_tests(case_id, initial["files"], run_root=folder / "initial-public")
        reference = tasks.assess_files(case_id, tasks.reference_solution(case_id), run_root=folder / "reference")
        counterexamples = {name: tasks.assess_files(case_id, files, run_root=folder / name)
                          for name, files in tasks.provenance_controls(case_id).items()}
        diagnostics = tasks.prepare_initial_diagnostics(case_id, folder / "initial-diagnostics")
        executions = [initial_public["execution"]]
        for result in (reference, *counterexamples.values()):
            executions.extend(result[part]["execution"] for part in ("independent_acceptance", "public_acceptance"))
        result = {"task_id": case_id, "initial_public": initial_public, "reference": reference,
            "counterexamples": counterexamples, "initial_diagnostics": diagnostics,
            "actual_program_executions": len(executions) + diagnostics["preparation_cost"]["actual_public_driver_executions"],
            "public_driver_executions": 4, "private_driver_executions": 3,
            "initial_diagnostic_driver_executions": diagnostics["preparation_cost"]["actual_public_driver_executions"],
            "sandbox_elapsed_seconds": sum(row["elapsed_seconds"] for row in executions)
                + diagnostics["preparation_cost"]["sandbox_elapsed_seconds"],
            "new_model_calls": 0, "new_tokenizer_calls": 0, "new_gpu_calls": 0,
            "expected_values_obtained_from_reference": False}
        atomic_write(folder / "business-control-receipt.json", json_bytes(result))
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(run, tasks.DEVELOPMENT_CASE_IDS))
    summary = {"version": tasks.VERSION, "source_manifest_sha256": tasks.source_manifest()["sha256"],
        "cases": [{"task_id": row["task_id"], "initial_public_passed": row["initial_public"]["passed"],
            "reference_passed": row["reference"]["passed"],
            "counterexamples_rejected": {name: not value["passed"] for name, value in row["counterexamples"].items()},
            "receipt": str(root / row["task_id"] / "business-control-receipt.json")} for row in values],
        **{key: sum(row[key] for row in values) for key in ("actual_program_executions", "public_driver_executions",
            "private_driver_executions", "initial_diagnostic_driver_executions", "sandbox_elapsed_seconds",
            "new_model_calls", "new_tokenizer_calls", "new_gpu_calls")},
        "independent_confirmation": False, "specifications_changed_after_execution": False}
    atomic_write(root / "summary.json", json_bytes(summary))
    return {row["task_id"]: row for row in values}


def test_partition_separates_new_business_families_and_window_only_training():
    manifest, partition = tasks.source_manifest(), tasks.source_partition()
    assert tuple(tasks.TASK_LABELS.values()) == ("LA", "LB", "DA", "DB")
    assert set(tasks.FAMILIES[key] for key in tasks.TRAINING_CASE_IDS).isdisjoint(
        tasks.FAMILIES[key] for key in tasks.DEVELOPMENT_CASE_IDS)
    assert partition["external_repository_count"] == 0
    assert partition["old_results_reclassified"] is partition["old_episode_material_admitted"] is False
    assert manifest["retained_source_manifest_sha256"] == old.source_manifest()["sha256"]
    assert all(row["derived_from_training_asset_ids"] == [] for row in manifest["cases"])
    assert all(row["public_check_count"] == 6 and row["private_check_count"] == 12 for row in manifest["cases"])


@pytest.mark.parametrize("case_id", tasks.TRAINING_CASE_IDS)
def test_training_overlay_retains_original_business_bytes_and_old_flags(case_id):
    original = old.build_case(case_id)
    current = tasks.build_case(case_id)
    assert current["purpose"] == current["usage"] == "policy_training"
    assert current["training_eligible"] is True
    assert current["training_window_id"] == tasks.TRAINING_WINDOW_ID
    assert current["source_contract"]["eligibility_scope"] == "new_v049_window_records_only"
    for field in ("files", "root_goal", "initial_binding", "editable_paths", "initial_owners", "task_definitions"):
        assert current[field] == original[field]
    assert current["source_contract"]["source_asset_ids"] == original["source_contract"]["source_asset_ids"]
    assert old.build_case(case_id) == original
    assert original["training_eligible"] is False
    assert original["purpose"] == "organization_development"


@pytest.mark.parametrize("case_id", tasks.DEVELOPMENT_CASE_IDS)
def test_new_development_members_only_receive_frozen_public_initial_material(case_id):
    case, reference = tasks.build_case(case_id), tasks.reference_solution(case_id)
    assert case["purpose"] == case["usage"] == "policy_development"
    assert case["training_eligible"] is case["independent_confirmation_eligible"] is False
    assert case["task_definitions"] == case["initial_owners"] == {}
    assert case["source_contract"]["derived_from_training_asset_ids"] == []
    assert case["source_contract"]["initial_code_model_generated"] is False
    assert not {"acceptance.json", "source-manifest.json", "initial-provenance.json"} & set(case["files"])
    assert not any(name.startswith(("reference/", "controls/")) for name in case["files"])
    assert case["initial_binding"]["initial_files_sha256"] == digest(json_bytes(case["files"]))
    assert any(reference[name] != case["files"][name] for name in case["source_contract"]["public_production_files"])


@pytest.mark.parametrize("case_id", tasks.DEVELOPMENT_CASE_IDS)
def test_reference_and_two_semantic_counterexamples_verify_bounded_contract(case_id, business_controls):
    receipt = business_controls[case_id]
    assert receipt["initial_public"]["execution"]["driver_completed"] is True
    assert receipt["initial_public"]["passed"] is False
    assert receipt["initial_public"]["groups"]["upstream_regressions"]["passed"] is True
    assert receipt["reference"]["passed"] is receipt["reference"]["content_correct"] is True
    assert len(receipt["counterexamples"]) == 2
    for result in receipt["counterexamples"].values():
        assert result["executed"] is True
        assert result["independent_acceptance"]["passed"] is False
        assert result["passed"] is False
    assert receipt["actual_program_executions"] == 9
    assert receipt["new_model_calls"] == receipt["new_tokenizer_calls"] == receipt["new_gpu_calls"] == 0


@pytest.mark.parametrize("case_id", tasks.DEVELOPMENT_CASE_IDS)
def test_initial_facts_are_public_observations_and_not_assigned_work(case_id, business_controls):
    value = business_controls[case_id]["initial_diagnostics"]
    assert value["preparation_cost"]["team_run_tests_charged"] == 0
    for group in tasks.DIAGNOSTIC_IDS:
        record = value[group]
        assert record["executed"] is True and record["model_generated"] is False
        assert record["counts"]["passed"] > 0 and record["counts"]["failed"] > 0
        assert record["origin"] == "environment_initial_diagnostic"
        assert '"path": "/' not in json_bytes(record).decode()


@pytest.mark.parametrize("case_id", tasks.DEVELOPMENT_CASE_IDS)
def test_public_contract_and_checks_are_immutable(case_id):
    files = tasks.reference_solution(case_id)
    before = copy.deepcopy(files)
    for name in ("contract.md", "test_visible.py"):
        with pytest.raises(ValueError, match="declared production"):
            tasks._validate_files(case_id, {**files, name: files[name] + "\n# changed\n"})
    assert files == before


def test_unregistered_root_is_not_an_alias_for_an_existing_source():
    with pytest.raises(ValueError, match="four declared"):
        tasks.build_case("renamed-LA")


def test_new_window_support_source_flags_keep_development_and_old_material_out():
    from proworksim.software_organization_v049 import case_spec

    for case_id in tasks.TRAINING_CASE_IDS:
        current, original, world_case = tasks.build_case(case_id), old.build_case(case_id), case_spec(case_id)
        assert current["contribution_eligible"] is current["source_contract"]["contribution_eligible"] is True
        assert world_case["contribution_eligible"] is world_case["source_contract"]["contribution_eligible"] is True
        assert original["contribution_eligible"] is original["source_contract"]["contribution_eligible"] is False
        assert current["files"] == original["files"] and current["initial_binding"] == original["initial_binding"]
    for case_id in tasks.DEVELOPMENT_CASE_IDS:
        current, world_case = tasks.build_case(case_id), case_spec(case_id)
        assert current["contribution_eligible"] is current["source_contract"]["contribution_eligible"] is False
        assert world_case["contribution_eligible"] is world_case["source_contract"]["contribution_eligible"] is False
        assert current["development_eligible"] is current["source_contract"]["development_eligible"] is True
        assert current["training_eligible"] is False
    for row in tasks.source_manifest()["cases"]:
        for name, sha in row["files_sha256"].items():
            assert digest((tasks.ASSETS / row["task_id"] / name).read_bytes()) == sha
