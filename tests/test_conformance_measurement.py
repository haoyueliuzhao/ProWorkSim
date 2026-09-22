"""Independent truth assertions protect E2 from two adapters sharing a bad meter."""

import copy
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("conformance_measurement_experiment")


@pytest.mark.parametrize("case_name", [
    "legal_mixed_reference_spellings", "missing_attestation", "wrong_exact_version",
    "wrong_attestation_id", "wrong_signer", "wrong_requirement_link", "wrong_work_scope",
    "wrong_credential_reference", "historical_issuance_new_requirement",
])
def test_measurement_matches_independent_truth(experiment, case_name):
    result = next(c for c in experiment.run_measurement_controls() if c["name"] == case_name)
    assert result["passed"], result


def test_both_false_projections_do_not_pass_expectation(experiment):
    projection = {"credentials": [{"credential": "C1", "formal_confirmation": False,
                                    "coordinator_signed": True}]}
    assert projection == copy.deepcopy(projection)
    assert not experiment.expected_confirmation_check(
        "withdraw_resubmit", "ConfirmGrant", projection)["passed"]


def test_measurement_mutants_trigger_the_named_assertion(experiment):
    for result in experiment.measurement_mutations():
        assert result["control_passed"] and result["injection_activated"]
        assert result["named_assertion_failed"] and result["detected"], result


def test_exact_reference_spellings_are_interchangeable(experiment):
    state, reference, _ = experiment.confirmation_fixture()
    assert experiment.formal_confirmation_fact(state, reference)
    assert experiment.formal_confirmation_fact(state, {
        "object_id": reference["artifact_id"], "version_id": reference["version_id"]})
    assert not experiment.formal_confirmation_fact(state, {
        "object_id": reference["artifact_id"], "version_id": "v2"})
