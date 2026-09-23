"""Protocol-level N2/N3 evidence: real paths and truthful incomplete runs."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("publication_consumption_experiment")


@pytest.mark.parametrize("group", ["N2", "N3"])
def test_actual_publication_and_consumption_cases(experiment, tmp_path, group):
    result = experiment.run_group((group, tmp_path / group))
    assert result["error"] is None, result["error"]
    failed = [check for check in result["checks"] if not check["passed"]]
    assert not failed, failed
    assert result["not_executed_count"] == 0


def test_incomplete_branch_is_recorded_without_passing_missing_cases(
    experiment, monkeypatch, tmp_path
):
    def stop_after_first_check(evidence):
        evidence.check("initial_adoptions_current_and_fixed_v1", True, True)
        raise ValueError("test interruption before publication branches")

    monkeypatch.setitem(experiment.RUNNERS, "N2", stop_after_first_check)
    result = experiment.run_group(("N2", tmp_path / "incomplete"))
    assert not result["passed"]
    assert result["check_pass_count"] == 1
    assert result["not_executed_count"] == len(experiment.CHECKS["N2"]) - 1
    assert result["error"]["error"] == "ValueError: test interruption before publication branches"
