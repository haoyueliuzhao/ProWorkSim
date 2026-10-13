"""Finite v050 source controls: authored contracts, no model or tokenizer calls."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path

import pytest

from proworksim import software_learning_sources_v050 as fresh
from proworksim import software_organization_tasks_v050 as tasks
from proworksim.storage import atomic_write, digest, json_bytes


@pytest.fixture(scope="module")
def business_controls(tmp_path_factory):
    reused = os.environ.get("PROWORKSIM_V050_TASK_CONTROL_REUSE_ROOT")
    if reused:
        root = Path(reused)
        values = {}
        for case_id in fresh.CASE_IDS:
            row = json.loads((root / case_id / "business-control-receipt.json").read_text())
            if row["task_id"] != case_id or row["source_manifest_sha256"] != fresh.source_manifest()["sha256"]:
                raise ValueError("CPU receipt source identity changed")
            values[case_id] = row
        return values
    configured = os.environ.get("PROWORKSIM_V050_TASK_CONTROL_ROOT")
    root = Path(configured) if configured else tmp_path_factory.mktemp("v050-source-controls")
    root.mkdir(parents=True, exist_ok=True)

    def run(case_id):
        folder = root / case_id
        if (folder / "business-control-receipt.json").exists():
            raise FileExistsError("Use a fresh v050 CPU receipt destination")
        initial = fresh.build_case(case_id)
        public = fresh.run_public_tests(case_id, initial["files"], run_root=folder / "initial-public")
        reference = fresh.assess_files(case_id, fresh.reference_solution(case_id), run_root=folder / "reference")
        counterexamples = {
            name: fresh.assess_files(case_id, files, run_root=folder / name)
            for name, files in fresh.provenance_controls(case_id).items()
        }
        diagnostics = fresh.prepare_initial_diagnostics(case_id, folder / "initial-diagnostics")
        executions = [public["execution"]]
        for result in (reference, *counterexamples.values()):
            executions.extend(result[key]["execution"] for key in ("independent_acceptance", "public_acceptance"))
        receipt = {
            "task_id": case_id,
            "source_manifest_sha256": fresh.source_manifest()["sha256"],
            "initial_public": public,
            "reference": reference,
            "counterexamples": counterexamples,
            "initial_diagnostics": diagnostics,
            "actual_program_executions": len(executions) + diagnostics["preparation_cost"]["actual_public_driver_executions"],
            "public_driver_executions": 4,
            "private_driver_executions": 3,
            "initial_diagnostic_driver_executions": diagnostics["preparation_cost"]["actual_public_driver_executions"],
            "sandbox_elapsed_seconds": sum(row["elapsed_seconds"] for row in executions)
                + diagnostics["preparation_cost"]["sandbox_elapsed_seconds"],
            "new_model_calls": 0,
            "new_tokenizer_calls": 0,
            "new_gpu_calls": 0,
            "expected_values_obtained_from_reference": False,
        }
        atomic_write(folder / "business-control-receipt.json", json_bytes(receipt))
        return receipt

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(run, fresh.CASE_IDS))
    summary = {
        "version": fresh.VERSION,
        "source_manifest_sha256": fresh.source_manifest()["sha256"],
        "window_source_manifest_sha256": tasks.source_manifest()["sha256"],
        "cases": [{
            "task_id": row["task_id"],
            "initial_public_passed": row["initial_public"]["passed"],
            "reference_passed": row["reference"]["passed"],
            "counterexamples_rejected": {name: not result["passed"] for name, result in row["counterexamples"].items()},
            "receipt": str(root / row["task_id"] / "business-control-receipt.json"),
        } for row in values],
        **{key: sum(row[key] for row in values) for key in (
            "actual_program_executions", "public_driver_executions", "private_driver_executions",
            "initial_diagnostic_driver_executions", "sandbox_elapsed_seconds", "new_model_calls",
            "new_tokenizer_calls", "new_gpu_calls",
        )},
        "independent_confirmation": False,
        "specifications_changed_after_execution": False,
    }
    atomic_write(root / "summary.json", json_bytes(summary))
    return {row["task_id"]: row for row in values}


def test_six_registered_roots_keep_source_and_window_roles_separate():
    manifest, partition = tasks.source_manifest(), tasks.source_partition()
    assert tuple(tasks.TASK_LABELS.values()) == ("LA", "LB", "DA", "DB", "DC", "DD")
    assert len(manifest["cases"]) == 6
    assert partition["new_development_family_count"] == partition["reused_development_family_count"] == 2
    assert partition["old_episode_material_admitted"] is False
    assert partition["independent_confirmation_eligible"] is False
    training_families = {tasks.FAMILIES[key] for key in tasks.TRAINING_CASE_IDS}
    assert training_families.isdisjoint(tasks.FAMILIES[key] for key in tasks.DEVELOPMENT_CASE_IDS)


@pytest.mark.parametrize("case_id", tasks.retained.TASK_IDS)
def test_old_four_business_roots_are_exact_bytes_with_new_registration_only(case_id):
    original = tasks.retained.build_case(case_id)
    current = tasks.build_case(case_id)
    for field in ("files", "root_goal", "initial_binding", "editable_paths", "initial_owners", "task_definitions"):
        assert current[field] == original[field]
    for field in ("source_manifest_sha256", "source_partition_sha256", "source_asset_ids", "requirements_sha256"):
        assert current["source_contract"][field] == original["source_contract"][field]
    training = case_id in tasks.TRAINING_CASE_IDS
    assert current["training_eligible"] is current["contribution_eligible"] is training
    assert current["training_window_id"] == (tasks.TRAINING_WINDOW_ID if training else None)
    assert tasks.retained.build_case(case_id) == original


@pytest.mark.parametrize("case_id", fresh.CASE_IDS)
def test_new_roots_are_development_only_public_material_without_assigned_work(case_id):
    case = tasks.build_case(case_id)
    assert case["purpose"] == case["usage"] == "policy_development"
    assert case["training_eligible"] is case["contribution_eligible"] is False
    assert case["source_contract"]["independent_confirmation_eligible"] is False
    assert case["task_definitions"] == case["initial_owners"] == {}
    assert case["source_contract"]["derived_from_training_asset_ids"] == []
    assert not {"acceptance.json", "source-manifest.json", "initial-provenance.json"} & set(case["files"])
    assert not any(path.startswith(("reference/", "controls/")) for path in case["files"])
    assert case["initial_binding"]["initial_files_sha256"] == digest(json_bytes(case["files"]))
    assert case["source_contract"]["initial_code_model_generated"] is False


@pytest.mark.parametrize("case_id", fresh.CASE_IDS)
def test_reference_passes_same_public_private_contract_and_counterexamples_fail(case_id, business_controls):
    receipt = business_controls[case_id]
    assert receipt["initial_public"]["execution"]["driver_completed"] is True
    assert receipt["initial_public"]["passed"] is False
    assert receipt["initial_public"]["groups"]["upstream_regressions"]["passed"] is True
    assert receipt["reference"]["passed"] is receipt["reference"]["content_correct"] is True
    assert len(receipt["reference"]["independent_acceptance"]["checks"]) == 16
    assert len(receipt["reference"]["public_acceptance"]["tests"]) == 8
    assert len(receipt["counterexamples"]) == 2
    for result in receipt["counterexamples"].values():
        assert result["executed"] is True
        assert result["independent_acceptance"]["passed"] is False
        assert result["passed"] is False
    assert receipt["actual_program_executions"] == 9
    assert receipt["new_model_calls"] == receipt["new_tokenizer_calls"] == receipt["new_gpu_calls"] == 0


@pytest.mark.parametrize("case_id", fresh.CASE_IDS)
def test_initial_diagnostic_groups_preserve_real_public_pass_and_failure(case_id, business_controls):
    value = business_controls[case_id]["initial_diagnostics"]
    assert value["preparation_cost"]["team_run_tests_charged"] == 0
    for group in fresh.DIAGNOSTIC_IDS:
        record = value[group]
        assert record["executed"] is True
        assert record["model_generated"] is False
        assert record["counts"]["passed"] > 0 and record["counts"]["failed"] > 0
        assert record["origin"] == "environment_initial_diagnostic"
        assert '"path": "/' not in json_bytes(record).decode()


@pytest.mark.parametrize("case_id", fresh.CASE_IDS)
def test_immutable_contract_public_tests_and_file_inventory(case_id):
    files = tasks.reference_solution(case_id)
    before = copy.deepcopy(files)
    for name in ("contract.md", "test_visible.py"):
        with pytest.raises(ValueError, match="declared production"):
            tasks._validate_files(case_id, {**files, name: files[name] + "\n# changed\n"})
    with pytest.raises(ValueError, match="declared production"):
        tasks._validate_files(case_id, {**files, "private.py": ""})
    assert files == before


def test_source_hashes_bind_all_new_contract_reference_and_counterexample_bytes():
    manifest = fresh.source_manifest()
    for row in manifest["cases"]:
        assert row["public_check_count"] == 8 and row["private_check_count"] == 16
        assert row["external_upstream_bug_claim"] is False
        assert row["derived_from_training_asset_ids"] == []
        for name, sha in row["files_sha256"].items():
            assert digest((fresh.ASSETS / row["task_id"] / name).read_bytes()) == sha


def test_unregistered_roots_do_not_alias_old_business_sources():
    with pytest.raises(ValueError, match="six predeclared"):
        tasks.build_case("renamed-LA")
    with pytest.raises(ValueError, match="two declared"):
        fresh.build_case(tasks.TRAINING_CASE_IDS[0])
