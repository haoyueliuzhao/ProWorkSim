"""A failed experiment setup must preserve its declared denominator and evidence."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("world_core_experiment")


def test_setup_failure_records_not_executed_checks(experiment, monkeypatch, tmp_path):
    def broken_setup(evidence):
        evidence.check("zero_project_world_exists", [{}, "idle"], [{}, "idle"])
        raise ValueError("package installation intentionally failed")

    monkeypatch.setitem(experiment.GROUP_RUNNERS, "M1", broken_setup)
    result = experiment.run_group(("M1", tmp_path / "failed-experiment"))
    assert result["check_count"] == len(experiment.CHECKS["M1"])
    assert result["pass_count"] == 1
    assert result["not_executed_count"] == len(experiment.CHECKS["M1"]) - 1
    assert result["error"]["error"] == "ValueError: package installation intentionally failed"
    assert not result["passed"]


def test_unrelated_equal_values_do_not_replace_expected_value(experiment, tmp_path):
    evidence = experiment.Evidence("M2", tmp_path)
    evidence.check("A_confirmation_applies_to_A", "UNASSESSED", "PASS")
    assert not evidence.checks[0]["passed"]
    with pytest.raises(AssertionError, match="repeated"):
        evidence.check("A_confirmation_applies_to_A", "PASS", "PASS")
