"""Verify the N1 harness records fixed expectations and incomplete executions."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("work_capability_experiment")


def test_n1_runs_real_world_and_preserves_old_submission(experiment, tmp_path):
    result = experiment.run_experiment(tmp_path / "n1")
    assert result["error"] is None, result["error"]
    failed = [record for record in result["checks"] if not record["passed"]]
    assert not failed, failed
    assert result["not_executed_count"] == 0


def test_n1_construction_error_keeps_unexecuted_denominator(experiment, monkeypatch, tmp_path):
    def interrupted(evidence):
        evidence.check("one_world_two_projects", False, True)
        raise ValueError("deliberate setup failure")

    monkeypatch.setattr(experiment, "run_n1", interrupted)
    result = experiment.run_experiment(tmp_path / "failed")
    assert not result["passed"]
    assert result["error"]["error"] == "ValueError: deliberate setup failure"
    assert result["check_count"] == len(experiment.CHECKS)
    assert result["check_pass_count"] == 0
    assert result["not_executed_count"] == len(experiment.CHECKS) - 1


def test_n1_wrong_formula_result_cannot_redefine_literal_oracle(experiment, monkeypatch, tmp_path):
    original = experiment.workbook_cell

    def wrong_result(content, sheet="Report", cell="A3"):
        result = original(content, sheet, cell)
        if result["raw"] == "=SUM(A1,-A2)":
            result["cached"] = 999
        return result

    monkeypatch.setattr(experiment, "workbook_cell", wrong_result)
    result = experiment.run_experiment(tmp_path / "wrong-cache")
    by_name = {record["name"]: record for record in result["checks"]}
    assert result["error"] is None, result["error"]
    assert not by_name["legitimate_edit_new_version_formula_and_scalar"]["passed"]
    assert not by_name["recalculate_preserves_formula_and_scalar"]["passed"]
    assert by_name["xlsx_fixed_submission_content_passes"]["passed"]
