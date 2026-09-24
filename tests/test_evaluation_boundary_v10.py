"""R0 input faults are distinct from evaluator implementation faults."""

import copy

import pytest

from proworksim.domains.reconciliation import evaluate_check
from proworksim.evaluation import combined_status
from proworksim.templates.reconciliation import content_contract, fixtures
from proworksim.workers.reconciliation import match_public_tables


def data():
    values = fixtures()
    sources = dict(
        zip(
            ("ledger", "statement", "definitions"),
            (values["left"], values["right"], values["policy"]),
        )
    )
    output = {
        "reconciliation": match_public_tables(
            values["left"], values["right"], values["policy"], "ledger", "statement"
        )
    }
    return content_contract()["content_checks"][0], output, sources


@pytest.mark.parametrize(
    "shape",
    [
        "target_null",
        "rows_null",
        "row_null",
        "key_nested",
        "ids_null",
        "evidence_null",
        "evidence_entry_null",
        "evidence_identity_nested",
        "summary_null",
        "unresolved_nested",
        "unrepresentable_integer",
    ],
)
def test_malformed_finite_delivery_has_structure_status(shape):
    spec, output, sources = data()
    target = output["reconciliation"]
    if shape == "target_null":
        output["reconciliation"] = None
    elif shape == "rows_null":
        target["rows"] = None
    elif shape == "row_null":
        target["rows"] = [None]
    elif shape == "key_nested":
        target["rows"][0]["key"] = [{}, []]
    elif shape == "ids_null":
        target["rows"][0]["left_ids"] = None
    elif shape == "evidence_null":
        target["rows"][0]["evidence"] = None
    elif shape == "evidence_entry_null":
        target["rows"][0]["evidence"] = [None]
    elif shape == "evidence_identity_nested":
        target["rows"][0]["evidence"][0]["record_id"] = {}
    elif shape == "summary_null":
        target["summary"] = None
    elif shape == "unrepresentable_integer":
        target["rows"][0]["left_value"] = 10**1000
    else:
        target["unresolved"] = [[{}, "x"]]
    before = copy.deepcopy((output, sources))
    result = evaluate_check(spec, output, sources.__getitem__)
    assert result["status"] == "structure_failure"
    assert not result["passed"]
    assert before == (output, sources)


@pytest.mark.parametrize("shape", ["table_null", "record_null", "policy_null"])
def test_unavailable_source_schema_is_not_worker_arithmetic(shape):
    spec, output, sources = data()
    if shape == "table_null":
        sources["ledger"] = None
    elif shape == "record_null":
        sources["ledger"]["records"] = [None]
    else:
        sources["definitions"] = None
    result = evaluate_check(spec, output, sources.__getitem__)
    assert result["status"] == "source_unavailable"
    assert not result["passed"]


def test_legitimate_unknown_and_wrong_numeric_claim_have_different_status():
    spec, output, sources = data()
    result = evaluate_check(spec, output, sources.__getitem__)
    assert result["status"] == "pass"
    unknown = next(row for row in output["reconciliation"]["rows"] if row["key"][1] == "unknown")
    assert unknown["left_value"] is None
    unknown["left_value"] = 0
    assert evaluate_check(spec, output, sources.__getitem__)["status"] == "content_failure"


@pytest.mark.parametrize(
    "case",
    [
        "normal",
        "business_error",
        "target_null",
        "row_null",
        "source_unavailable",
        "unassessed",
        "internal_error",
        "internal_type_error",
    ],
)
def test_real_session_boundary_and_read_only_repeated_evaluation(tmp_path, case):
    from scripts.evaluation_boundary_experiment import run_case

    report = run_case(case, tmp_path)
    assert report["construction_error"] is None, report["construction_error"]
    assert report["passed"], [check for check in report["checks"] if not check["passed"]]


def test_summary_never_turns_unobserved_target_into_pass():
    assert combined_status([]) == "unassessed"
    assert combined_status(["pass", "unassessed"]) == "unassessed"
    assert combined_status(["pass", "evaluator_error"]) == "evaluator_error"


def test_json_integer_comparison_does_not_raise_when_float_conversion_would_overflow():
    from proworksim.domains.work_product import _equal

    large = 10**1000
    assert _equal(large, large)
    assert not _equal(large, 1)
    assert not _equal(large, float("inf"))
