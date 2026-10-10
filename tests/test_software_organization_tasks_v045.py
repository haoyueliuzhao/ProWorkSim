"""Finite authored-business CPU controls; no model, tokenizer or GPU work."""
from concurrent.futures import ThreadPoolExecutor
import copy

import pytest

from proworksim import software_organization_tasks_v045 as tasks
from proworksim.storage import atomic_write, digest, json_bytes


@pytest.fixture(scope="module")
def business_controls(tmp_path_factory):
    """Execute each necessary fixture/control once and keep all CPU receipts."""
    root = tmp_path_factory.mktemp("v045-task-business-controls")

    def run(case_id):
        folder = root / case_id
        case = tasks.build_case(case_id)
        initial = tasks.run_public_tests(case_id, case["files"], run_root=folder / "initial-public")
        reference = tasks.assess_files(case_id, tasks.reference_solution(case_id), run_root=folder / "reference")
        controls = {name: tasks.assess_files(case_id, files, run_root=folder / "controls" / name)
                    for name, files in tasks.provenance_controls(case_id).items()}
        preparation = tasks.prepare_initial_diagnostics(case_id, folder / "initial-diagnostics")
        executions = [{"kind": "initial_public", "execution": initial["execution"]}]
        for name, result in [("reference", reference), *controls.items()]:
            executions.extend({"kind": name + ":" + part, "execution": result[part]["execution"]}
                              for part in ("independent_acceptance", "public_acceptance"))
        value = {"task_id": case_id, "initial_public": initial, "reference": reference,
            "negative_controls": controls, "initial_diagnostics": preparation,
            "execution_count": len(executions), "executions": executions,
            "public_driver_executions": 2 + len(controls),
            "private_driver_executions": 1 + len(controls),
            "initial_diagnostic_driver_executions": preparation["preparation_cost"]["actual_public_driver_executions"],
            "sandbox_elapsed_seconds": sum(row["execution"]["elapsed_seconds"] for row in executions),
            "environment_diagnostic_elapsed_seconds": preparation["preparation_cost"]["sandbox_elapsed_seconds"],
            "new_model_calls": 0, "new_tokenizer_calls": 0, "new_gpu_calls": 0,
            "scope": "One initial public run, one complete-reference public/private witness, and each named counterexample once. Initial public diagnostic cache reuse is explicit and never double charged."}
        atomic_write(folder / "business-contract-control-receipt.json", json_bytes(value))
        return value

    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(run, tasks.TASK_IDS))
    summary = {"version": tasks.VERSION, "cases": [{"task_id": row["task_id"],
        "reference_passed": row["reference"]["passed"], "initial_public_passed": row["initial_public"]["passed"],
        "controls_rejected": {name: not record["passed"] for name, record in row["negative_controls"].items()},
        "receipt": str(root / row["task_id"] / "business-contract-control-receipt.json")} for row in values],
        **{key: sum(row[key] for row in values) for key in ("execution_count", "public_driver_executions",
            "private_driver_executions", "initial_diagnostic_driver_executions", "sandbox_elapsed_seconds",
            "environment_diagnostic_elapsed_seconds", "new_model_calls", "new_tokenizer_calls", "new_gpu_calls")},
        "same_contract_private_checks_are_independent_confirmation": False,
        "expected_values_computed_from_reference_output": False}
    atomic_write(root / "summary.json", json_bytes(summary))
    return {value["task_id"]: value for value in values}


def test_four_new_roots_are_two_authored_families_with_no_training_or_old_bug_claim():
    manifest, partition = tasks.source_manifest(), tasks.source_partition()
    assert tasks.CASE_IDS == tasks.TASK_IDS and tuple(tasks.TASK_LABELS.values()) == ("LA", "HA", "LB", "HB")
    assert manifest["authored_family_count"] == partition["authored_family_count"] == 2
    assert set(tasks.FAMILIES.values()) == {"event_interface", "rule_interface"}
    assert partition["independent_external_repository_count"] == 0
    assert all(partition[key] is False for key in ("training_eligible", "contribution_eligible",
        "independent_confirmation_eligible", "old_results_reclassified", "external_upstream_bug_claim"))
    assert len(manifest["cases"]) == 4


@pytest.mark.parametrize("case_id", tasks.TASK_IDS)
def test_only_public_initial_material_is_installed_and_reference_is_a_separate_witness(case_id):
    case, reference = tasks.build_case(case_id), tasks.reference_solution(case_id)
    contract = case["source_contract"]
    assert case["task_definitions"] == case["initial_owners"] == {}
    assert case["new_root"] is True and case["synthetic_root"] is True
    assert contract["initial_code_model_generated"] is False
    assert contract["initial_diagnostics_public_to_all_members"] is True
    assert contract["authored_family_count"] == 2 and contract["root_count"] == 4
    assert set(case["editable_paths"]) == set(contract["public_production_files"]) | {"test_member.py"}
    assert set(contract["contract_symbols"]) == set(contract["public_production_files"])
    assert not {"acceptance.json", "initial-provenance.json", "source-manifest.json"} & set(case["files"])
    assert not any(name.startswith(("reference/", "controls/")) for name in case["files"])
    assert case["initial_binding"]["initial_files_sha256"] == digest(json_bytes(case["files"]))
    assert any(reference[name] != case["files"][name] for name in contract["public_production_files"])
    assert all(reference[name] == text for name, text in case["files"].items() if name not in case["editable_paths"])
    assert tasks.build_case(case_id)["files"] == case["files"]


@pytest.mark.parametrize("case_id", tasks.TASK_IDS)
def test_reference_completes_public_and_private_contract_while_initial_branch_does_not(case_id, business_controls):
    receipt = business_controls[case_id]
    assert receipt["initial_public"]["execution"]["driver_completed"] is True
    assert receipt["initial_public"]["passed"] is False
    assert receipt["initial_public"]["groups"]["upstream_regressions"]["passed"] is True
    reference = receipt["reference"]
    assert reference["executed"] and reference["passed"] and reference["content_correct"]
    assert reference["independent_acceptance"]["passed"] and reference["public_acceptance"]["passed"]
    assert reference["independent_acceptance"]["expected_values_sent_to_worker"] is False
    for name, result in receipt["negative_controls"].items():
        assert result["executed"] is True, name
        assert result["independent_acceptance"]["execution"]["driver_completed"] is True, name
        assert result["passed"] is False and result["independent_acceptance"]["passed"] is False, name


@pytest.mark.parametrize("case_id", tasks.TASK_IDS)
def test_initial_diagnostics_are_real_bounded_public_facts_not_current_member_work(case_id, business_controls):
    receipt = business_controls[case_id]
    preparation = receipt["initial_diagnostics"]
    assert preparation["initial_files_sha256"] == tasks.build_case(case_id)["initial_binding"]["initial_files_sha256"]
    assert preparation["preparation_cost"]["team_run_tests_charged"] == 0
    assert preparation["preparation_cost"]["model_calls"] == 0
    for group in tasks.DIAGNOSTIC_IDS:
        record = preparation[group]
        assert record["executed"] is True and record["model_generated"] is False
        assert record["counts"]["passed"] > 0 and record["counts"]["failed"] > 0
        assert record["origin"] == "environment_initial_diagnostic"
        assert '"path": "/' not in json_bytes(record).decode()
    assert receipt["new_model_calls"] == receipt["new_tokenizer_calls"] == receipt["new_gpu_calls"] == 0


def test_public_contract_and_readonly_support_cannot_be_changed_as_a_task_repair():
    case_id = tasks.TASK_IDS[-1]
    files = tasks.reference_solution(case_id)
    before = copy.deepcopy(files)
    for filename in ("contract.md", "test_visible.py", "rule_v1.py", "migration_probe.py"):
        changed = {**files, filename: files[filename] + "\n# changed\n"}
        with pytest.raises(ValueError, match="declared production"):
            tasks._validate_files(case_id, changed)
    assert files == before
    with pytest.raises(ValueError, match="four declared"):
        tasks.build_case("old-or-unregistered-root")
