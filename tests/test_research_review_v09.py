"""Literal truths independently authored from the report strategy."""

import copy

import pytest

from proworksim.domains.research_review import evaluate_check, validate_check
from proworksim.templates.research_review import check_spec, fixtures


def literal_report(style="prose", incomplete=False):
    values = (
        ("revenue", "Revenue", 120, "up"),
        ("cost", "Cost", None if incomplete else 70, "unknown" if incomplete else "down"),
    )
    sections = []
    for cid, label, value, trend in values:
        text = "unknown" if value is None else str(value)
        body = f"{label} in 2026H1: {text}; trend {trend}; source dataset:metrics.{cid}.value."
        if style == "compact":
            body = f"2026H1: {label} = {text} ({trend}) [dataset:metrics.{cid}.value]."
        sections.append(
            {
                "section_id": cid,
                "body": body,
                "claims": [
                    {
                        "claim_id": cid,
                        "value": value,
                        "period": "2026H1",
                        "trend": trend,
                        "source_alias": "dataset",
                        "source_path": ["metrics", cid, "value"],
                        "status": "unresolved" if value is None else "supported",
                    }
                ],
            }
        )
    return {
        "report": {
            "sections": sections
            + [
                {
                    "section_id": "free",
                    "body": "Open prose receives no quality judgment.",
                    "claims": [],
                }
            ]
        }
    }


def evaluate(data, incomplete=False):
    return evaluate_check(check_spec(), data, lambda alias: fixtures(incomplete=incomplete))


@pytest.mark.parametrize("style", ["prose", "compact"])
@pytest.mark.parametrize("incomplete", [False, True])
def test_literal_finite_report_and_explicit_unknown(style, incomplete):
    result = evaluate(literal_report(style, incomplete), incomplete)
    assert result["passed"]
    assert len(result["diagnostics"]) == 2
    assert result["unassessed"]


@pytest.mark.parametrize(
    "field,wrong",
    [
        ("value", 999),
        ("value", True),
        ("period", "1999FY"),
        ("trend", "flat"),
        ("source_alias", "wrong"),
        ("source_path", ["metrics", "cost", "value"]),
        ("status", "unresolved"),
    ],
)
def test_correct_body_does_not_excuse_wrong_metadata(field, wrong):
    data = literal_report()
    data["report"]["sections"][0]["claims"][0][field] = wrong
    result = evaluate(data)
    assert not result["passed"]
    assert result["diagnostics"][0]["body_correct"]
    assert not result["diagnostics"][0]["metadata_correct"]


@pytest.mark.parametrize(
    "old,new",
    [
        ("120", "999"),
        ("2026H1", "1999FY"),
        ("trend up", "trend down"),
        ("dataset:", "wrong:"),
        ("metrics.revenue.value", "metrics.cost.value"),
        (".", ". Additional contradictory 999."),
    ],
)
def test_correct_metadata_cannot_hide_reader_facing_error(old, new):
    data = literal_report()
    section = data["report"]["sections"][0]
    section["body"] = section["body"].replace(old, new, 1)
    result = evaluate(data)
    assert not result["passed"]
    assert result["diagnostics"][0]["metadata_correct"]
    assert not result["diagnostics"][0]["body_correct"]
    assert result["diagnostics"][1]["passed"]


def test_wrong_claim_does_not_change_other_section_or_source():
    source, report = fixtures(), literal_report()
    before_source, before_report = copy.deepcopy(source), copy.deepcopy(report)
    report["report"]["sections"][0]["body"] = (
        "Revenue in 2026H1: 999; trend up; source dataset:metrics.revenue.value."
    )
    result = evaluate_check(check_spec(), report, lambda alias: source)
    assert [r["passed"] for r in result["diagnostics"]] == [False, True]
    assert source == before_source
    assert report["report"]["sections"][1:] == before_report["report"]["sections"][1:]


def test_missing_is_not_zero_and_bool_is_not_a_number():
    report = literal_report(incomplete=True)
    report["report"]["sections"][1]["claims"][0]["value"] = 0
    assert not evaluate(report, incomplete=True)["passed"]
    source = fixtures()
    source["metrics"]["revenue"]["value"] = True
    result = evaluate_check(check_spec(), literal_report(), lambda alias: source)
    assert not result["passed"]
    assert "numeric" in result["error"]


def test_duplicate_and_missing_claim_sections_rejected():
    report = literal_report()
    report["report"]["sections"].append(copy.deepcopy(report["report"]["sections"][0]))
    assert not evaluate(report)["passed"]
    report = literal_report()
    report["report"]["sections"].pop(0)
    assert not evaluate(report)["passed"]


def test_cross_template_paths_are_generic_and_public():
    spec = {
        "kind": "research_report",
        "path": ["report"],
        "sources": [{"alias": "comparison", "reference_path": ["sources", "comparison"]}],
        "claims": [
            {
                "claim_id": "conflicts",
                "section_id": "findings",
                "label": "Conflicts",
                "source_alias": "comparison",
                "value_path": ["reconciliation", "summary", "conflict"],
                "period_path": ["reconciliation", "period"],
            }
        ],
    }
    source = {"reconciliation": {"summary": {"conflict": 1}, "period": "2026H1"}}
    report = {
        "report": {
            "sections": [
                {
                    "section_id": "findings",
                    "body": "Conflicts in 2026H1: 1; trend unassessed; source comparison:reconciliation.summary.conflict.",
                    "claims": [
                        {
                            "claim_id": "conflicts",
                            "value": 1,
                            "period": "2026H1",
                            "trend": "unassessed",
                            "source_alias": "comparison",
                            "source_path": ["reconciliation", "summary", "conflict"],
                            "status": "supported",
                        }
                    ],
                }
            ]
        }
    }
    assert evaluate_check(spec, report, lambda alias: source)["passed"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s["claims"].append(copy.deepcopy(s["claims"][0])),
        lambda s: s["claims"][0].update(source_alias="missing"),
        lambda s: s.update(hidden_answer=120),
    ],
)
def test_invalid_contract_rejected(mutation):
    spec = check_spec()
    mutation(spec)
    with pytest.raises(ValueError):
        validate_check(spec)


@pytest.mark.parametrize(
    "body_value,metadata_value,expected_findings",
    [("1.20e2", 120, 0), ("120.0", 120, 0), ("120", True, 1)],
)
def test_public_reviewer_handles_legal_numeric_spelling_and_rejects_bool(
    body_value, metadata_value, expected_findings
):
    from proworksim.workers.research_review import PublicReportWorker

    report = literal_report()
    section = report["report"]["sections"][0]
    section["body"] = section["body"].replace("120", body_value)
    section["claims"][0]["value"] = metadata_value
    spec = check_spec()
    binding = {"object_id": "source-object", "version_id": "v1"}

    class OpaquePort:
        def tools(self):
            return []

        def observe(self):
            return {
                "work_items": {"P::research": {"deliverable_contract": {"content_checks": [spec]}}},
                "adoptions": {"P::research::dataset": binding},
            }

        def call(self, action, **arguments):
            if action == "inspect_submission":
                result = {
                    "artifact_versions": {"report-object": "v2"},
                    "adoption_snapshot": {"P::research::dataset": binding},
                }
            elif action == "read_object":
                oid = arguments["object_id"]
                result = {
                    "reference": {"artifact_id": oid, "version_id": arguments["version_id"]},
                    "data": report if oid == "report-object" else fixtures(),
                }
            else:
                raise AssertionError("Unexpected public action " + action)
            return {"ok": True, "result": result}

    findings = PublicReportWorker(OpaquePort()).review("P::research", "submission")
    assert len(findings) == expected_findings
    assert evaluate(report)["passed"] == (expected_findings == 0)
