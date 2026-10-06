"""New finite panel controls; no model call or training record is produced."""
import copy
import os
from pathlib import Path

import pytest

from proworksim import software_tasks_v035 as retained
from proworksim import software_tasks_v036 as source
from scripts.qualify_software_sources_v036 import qualify, source_binding


def test_retained_contracts_exact_purposes_and_private_assets_stay_separate():
    proof = source_binding()
    assert proof["root_counts"] == {"policy_training": 1, "contribution_development": 4, "independent_confirmation": 4}
    assert source.TRAINING_CASE_ID == retained.TRAINING_CASE_ID
    for case_id in source.TASK_IDS:
        case = source.build_case(case_id)
        assert case["task_definitions"] == case["initial_owners"] == {}
        assert "sampling_seed" not in case and "seed" not in case
        assert case["training_eligible"] is (case_id == source.TRAINING_CASE_ID)
        changed = copy.deepcopy(case["files"])
        changed["contract.md"] += "\nWeaker test-only condition\n"
        with pytest.raises(ValueError, match="editable"):
            source._validate_files(case_id, changed)
    assert source.API_DRIVER == retained.API_DRIVER
    assert source.project_public_test_feedback is retained.project_public_test_feedback


def test_new_and_retained_panel_actual_cpu_program_controls(tmp_path):
    output = Path(os.environ.get("PROWORKSIM_V036_SOURCE_CONTROL_RUN", str(tmp_path)))
    result = qualify(output, workers=4)
    assert result["passed"] is True and result["actual_program_variants"] == 28
    assert result["actual_isolated_program_executions"] == 56
    for name in source.NEW_CASE_IDS:
        rows = {row["variant"]: row for row in result["rows"] if row["case_id"] == name}
        assert {key: row["passed"] for key, row in rows.items()} == {
            "original": False, "shared_api_only": False, "consumer_only": False,
            "joint_reference": True, "library_bypass": False, "product_bypass": False}
        for kind in ("library_bypass", "product_bypass"):
            assert rows[kind]["content_correct"] is True
            assert rows[kind]["required_process_satisfied"] is False
            assert rows[kind]["process_observation_complete"] is True
    assert len([row for row in result["rows"] if row["variant"] == "retained_joint_reference" and row["passed"]]) == 4


def test_legacy_unallocated_roots_cannot_enter_new_panel_source_interface():
    for name in ("schema-catalog", "textfsm-record-items", "sqlparse-comparison-records", "mm-directory-rootgoal-v034"):
        with pytest.raises(ValueError, match="retained v035"):
            source.build_case(name)
