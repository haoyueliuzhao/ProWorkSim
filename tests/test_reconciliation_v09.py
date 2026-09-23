"""Finite hand-truth checks, malformed and semantically wrong deliveries."""

import copy

import pytest

from proworksim.domains.reconciliation import evaluate_check, validate_check
from proworksim.templates.reconciliation import content_contract, fixtures, literal_truth
from proworksim.workers.reconciliation import match_public_tables


def data():
    inputs = fixtures()
    sources = dict(
        zip(
            ("ledger", "statement", "definitions"),
            (inputs["left"], inputs["right"], inputs["policy"]),
        )
    )
    output = {
        "reconciliation": match_public_tables(
            inputs["left"], inputs["right"], inputs["policy"], "ledger", "statement"
        )
    }
    return content_contract()["content_checks"][0], output, sources


def test_worker_conclusions_against_independent_literal_truth():
    _, output, _ = data()
    actual = {
        row["key"][1]: {k: row[k] for k in ("status", "left_value", "right_value", "delta")}
        for row in output["reconciliation"]["rows"]
    }
    assert actual == literal_truth()
    assert output["reconciliation"]["summary"] == {
        "matched": 1,
        "converted": 1,
        "conflict": 1,
        "incomparable": 3,
        "missing": 2,
        "ambiguous": 1,
    }


def test_domain_accepts_exact_evidence_without_mutating_sources():
    spec, output, sources = data()
    old = copy.deepcopy((spec, output, sources))
    result = evaluate_check(spec, output, sources.__getitem__)
    assert result["passed"], result
    assert (spec, output, sources) == old


@pytest.mark.parametrize(
    "defect",
    [
        "omission",
        "duplicate",
        "force_difference",
        "null_to_zero",
        "pick_ambiguous",
        "invent_evidence",
        "boolean_number",
        "metadata_correct_body_wrong",
    ],
)
def test_domain_rejects_specific_wrong_products(defect):
    spec, output, sources = data()
    rows = output["reconciliation"]["rows"]
    by_metric = {row["key"][1]: row for row in rows}
    if defect == "omission":
        rows.pop()
    elif defect == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif defect == "force_difference":
        by_metric["fx"].update(status="matched", left_value=6, right_value=6, delta=0)
    elif defect == "null_to_zero":
        by_metric["unknown"].update(status="conflict", left_value=0, right_value=8, delta=-8)
    elif defect == "pick_ambiguous":
        by_metric["duplicate"].update(status="matched", left_value=7, right_value=7, delta=0)
    elif defect == "invent_evidence":
        by_metric["cost"]["evidence"][0]["location"] = "invented"
    elif defect == "boolean_number":
        output["reconciliation"]["summary"]["matched"] = True
    else:
        # Correct source references/summary never substitute for actual table cells.
        by_metric["cost"]["right_value"] = 80
    assert not evaluate_check(spec, output, sources.__getitem__)["passed"]


def test_corrected_conflict_leaves_every_other_business_row_unchanged():
    original = fixtures()
    corrected = fixtures(corrected=True)
    outputs = [
        match_public_tables(d["left"], d["right"], d["policy"], "ledger", "statement")
        for d in (original, corrected)
    ]
    for left, right in zip(outputs[0]["rows"], outputs[1]["rows"]):
        if left["key"][1] != "cost":
            assert left == right
    assert outputs[1]["summary"]["conflict"] == 0


@pytest.mark.parametrize(
    "patch", [{"left_alias": "missing"}, {"sources": []}, {"path": []}, {"execute": "python"}]
)
def test_malformed_contracts_rejected_before_runtime(patch):
    spec = content_contract()["content_checks"][0]
    with pytest.raises(ValueError):
        validate_check({**spec, **patch})


@pytest.mark.parametrize(
    "case", ["renamed_reordered_split", "unavailable_then_recovered", "review_repair"]
)
def test_actual_public_sessions_cover_organization_recovery_and_same_work_repair(tmp_path, case):
    from scripts.reconciliation_experiment import run_case

    result = run_case(case, tmp_path)
    assert result["construction_error"] is None, result["construction_error"]
    assert result["passed"], [c for c in result["checks"] if not c["passed"]]


def test_set_display_order_is_not_a_hidden_reference_solution():
    spec, output, sources = data()
    output["reconciliation"]["rows"].reverse()
    output["reconciliation"]["unresolved"].reverse()
    for row in output["reconciliation"]["rows"]:
        for field in ("left_ids", "right_ids", "evidence"):
            row[field].reverse()
    assert evaluate_check(spec, output, sources.__getitem__)["passed"]


def test_experiment_construction_failure_preserves_declared_denominator(tmp_path, monkeypatch):
    from scripts import reconciliation_experiment as experiment

    def fail_setup(ev):
        raise RuntimeError("Controlled pre-world construction failure")

    monkeypatch.setattr(experiment, "execute", fail_setup)
    result = experiment.run_case("review_repair", tmp_path)
    assert not result["passed"]
    assert "Controlled pre-world construction failure" in result["construction_error"]
    assert result["total_checks"] == result["not_executed"] == 14
    assert result["executed_checks"] == 0
    assert [c["name"] for c in result["checks"]] == list(experiment.CHECKS["review_repair"])
    assert sum(len(names) for names in experiment.CHECKS.values()) == 58
    assert all(not c["passed"] and c["not_executed"] for c in result["checks"])


def test_experiment_check_names_are_declared_and_unique(tmp_path):
    from scripts.reconciliation_experiment import Evidence

    evidence = Evidence("combined", tmp_path)
    evidence.check("public_strategy_delivers", "submitted", "submitted")
    for name in ("public_strategy_delivers", "invented_assertion"):
        with pytest.raises(AssertionError, match="Undeclared or repeated"):
            evidence.check(name, True)
