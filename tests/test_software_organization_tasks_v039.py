"""Narrow CPU task controls: finite quality witnesses, not model outcomes."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path

import pytest

from proworksim import software_organization_tasks_v039 as source
from proworksim.storage import digest, json_bytes


@pytest.fixture(scope="module")
def controls(tmp_path_factory):
    root = Path(os.environ.get("PROWORKSIM_V039_SOURCE_CONTROL_RUN", str(tmp_path_factory.mktemp("v039-source-controls"))))
    variants = []
    for case_id in source.CASE_IDS:
        programs = {"baseline": source.build_case(case_id)["files"],
                    "reference": source.reference_solution(case_id), **source.provenance_controls(case_id)}
        if source.FAMILIES[case_id] == "cross_dependency":
            programs.update(source.dependency_controls(case_id))
        variants.extend((case_id, name, files) for name, files in programs.items())

    def run(value):
        case_id, name, files = value
        result = source.assess_files(case_id, files, run_root=root / case_id / name)
        return case_id, name, result

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(run, variants))
    by_case = {case_id: {} for case_id in source.CASE_IDS}
    proof = []
    for case_id, name, result in results:
        by_case[case_id][name] = result
        proof.append({"case_id": case_id, "variant": name,
            **{key: result[key] for key in ("executed", "passed", "content_correct", "required_process_satisfied", "process_observation_complete")},
            "source_manifest_sha256": source.source_manifest()["sha256"],
            "execution_roots": str(root / case_id / name)})
    root.mkdir(parents=True, exist_ok=True)
    (root / "qualification.json").write_bytes(json_bytes({"version": source.VERSION,
        "purpose": source.PURPOSE, "rows": proof, "actual_program_variants": len(proof),
        "actual_isolated_executions": 2 * len(proof), "target_model_calls": 0,
        "gpu_used": False, "parameter_updates": 0,
        "scope": "Finite CPU witnesses only; no claim that a model uses these interfaces or that additional members improve work"}))
    return by_case


@pytest.mark.parametrize("case_id", source.CASE_IDS)
def test_frozen_new_purpose_and_empty_board_without_hidden_or_reference_material(case_id):
    value = source.build_case(case_id)
    manifest = source.source_manifest()
    row = next(row for row in manifest["cases"] if row["task_id"] == case_id)
    assert value["purpose"] == "organization_development"
    assert value["new_root"] is True
    assert not value["training_eligible"] and not value["contribution_eligible"] and not value["independent_confirmation_eligible"]
    assert value["task_definitions"] == value["initial_owners"] == {}
    assert row["predefined_execution_tasks"] is False
    assert row["old_business_contract_reused"] is False
    assert value["family"] == source.FAMILIES[case_id]
    assert value["files"]["contract.md"] == value["root_goal"]
    assert "No member or role is assigned" in value["root_goal"] or "no communication, role split, recruitment" in value["root_goal"]
    assert all(not any(part in name for part in ("acceptance", "reference", "controls")) for name in value["files"])
    hidden = json.loads((source.ASSETS / case_id / "acceptance.json").read_text())
    assert all(case["case_id"] not in value["files"]["test_visible.py"] for case in hidden["cases"])
    public = json.loads((source.ASSETS / case_id / "public-checks.json").read_text())
    assert not {json.dumps(case["request"], sort_keys=True) for case in hidden["cases"]} & {
        json.dumps(case["request"], sort_keys=True) for case in public["cases"]}
    assert value["initial_binding"]["initial_files_sha256"] == digest(json_bytes(value["files"]))
    assert value["initial_binding"]["public_driver_sha256"] == digest(value["files"]["test_visible.py"].encode())
    assert set(row["editable_paths"]) | {"test_member.py"} == set(value["editable_paths"])
    for path in ("contract.md", "test_visible.py", "schema/__init__.py", "acceptance.json"):
        invalid = copy.deepcopy(value["files"])
        invalid[path] = "Weaker or injected quality material"
        with pytest.raises(ValueError, match="editable"):
            source._validate_files(case_id, invalid)


def test_exact_four_root_families_pinned_schema_and_partition():
    assert source.CASE_IDS == ("sc-label-index-v039", "sc-row-projection-v039",
        "sc-record-views-v039", "sc-record-catalog-v039")
    assert list(source.FAMILIES.values()) == ["light_control", "light_control", "cross_dependency", "cross_dependency"]
    manifest, partition = source.source_manifest(), source.source_partition()
    environment = manifest["source_environment"]
    assert environment["commit"] == "24a3045773eac497c659f24b32f24a281be9f286"
    assert environment["state"] == "pristine_pinned_upstream_no_old_defect_patch"
    assert environment["original_environment_purpose"] == "contribution_development"
    assert partition["assignments"] == dict.fromkeys(source.CASE_IDS, "organization_development")
    assert partition["old_results_reclassified"] is False
    assert manifest["source_partition_sha256"] == partition["sha256"]
    assert manifest["api_driver_sha256"] == digest(source.API_DRIVER.encode())
    assert [len(row["editable_paths"]) for row in manifest["cases"]] == [2, 2, 3, 3]
    assert sum(row["public_check_count"] for row in manifest["cases"]) == 26
    assert sum(row["private_check_count"] for row in manifest["cases"]) == 32
    with pytest.raises(ValueError, match="four new"):
        source.build_case("sc-job-policy-v035-orgdev-v038")


@pytest.mark.parametrize("case_id", source.CASE_IDS)
def test_baseline_negative_complete_reference_positive(controls, case_id):
    original, reference = controls[case_id]["baseline"], controls[case_id]["reference"]
    assert original["executed"] and not original["passed"] and not original["content_correct"]
    assert reference["executed"] and reference["passed"]
    assert reference["content_correct"] and reference["required_process_satisfied"] and reference["process_observation_complete"]
    assert reference["independent_acceptance"]["expected_values_sent_to_worker"] is False
    assert reference["purpose"] == "organization_development"


@pytest.mark.parametrize("case_id", source.CASE_IDS)
def test_semantically_correct_bypasses_fail_required_observed_edges(controls, case_id):
    for name in ("library_bypass", "product_bypass"):
        result = controls[case_id][name]
        assert result["executed"] and not result["passed"]
        assert result["content_correct"] is True
        assert result["required_process_satisfied"] is False
        assert result["process_observation_complete"] is True
    product = controls[case_id]["product_bypass"]
    # This reverse control still uses the real library. It specifically omits
    # the declared shared application product, copied privately into consumers.
    for row in product["independent_acceptance"]["checks"]:
        observed = row["observed"]["source_api_used"]
        assert observed["schema.Schema.validate"] is True
        if row["group"].startswith("consumer"):
            assert any(not value for key, value in observed.items() if key != "schema.Schema.validate")


@pytest.mark.parametrize("case_id", source.CASE_IDS[2:])
def test_cross_dependencies_require_both_consumers_and_shared_product(controls, case_id):
    values = controls[case_id]
    assert not values["shared_api_only"]["passed"]
    assert not values["consumers_only"]["passed"]
    assert values["shared_api_only"]["executed"] and values["consumers_only"]["executed"]
    checks = values["reference"]["independent_acceptance"]["checks"]
    assert {row["group"] for row in checks} >= {"shared_api", "consumer_report", "consumer_query"}
    for group in ("consumer_report", "consumer_query"):
        assert all(row["passed"] for row in checks if row["group"] == group)
    # None of these root contracts requires different people to implement the edges.
    assert source.build_case(case_id)["task_definitions"] == {}
