"""Independent evaluation of pinned submissions, never exposed as a worker tool."""

import json
import math
from dataclasses import asdict

from .compiler import INPUT_CELLS, OUTPUT_CELLS, scope
from .contracts import (
    LEGACY_CONTRACT_VERSION,
    LEGACY_EVALUATOR_VERSION,
    EVALUATOR_VERSION,
    citation_contract,
    required_dependencies_match,
)
from .schema import EvaluationRecord
from .basis import requirement_basis
from .lifecycle import current_id
from .audience import audience_content_defects
from .layouts import SemanticSpreadsheet, layout_for
from .storage import Store, digest, read_json


def financial_result(inputs: dict) -> dict:
    """Independent scalar reference, not a second mutable workbook."""
    revenue = inputs["revenue"] * (1 + inputs["growth"])
    operating_profit = revenue * (inputs["operating_margin"] + inputs["margin_delta"])
    income = operating_profit * (1 - inputs["tax_rate"])
    equity = income * inputs["earnings_multiple"] - inputs["net_debt"]
    return {
        "forecast_revenue": revenue,
        "operating_profit": operating_profit,
        "net_income": income,
        "equity_value": equity,
        "share_price": equity / inputs["shares"],
        "model_eps": income / inputs["shares"],
        "model_pe": equity / income,
    }


def close(actual, expected, tolerance=1e-6) -> bool:
    return (
        type(actual) in (int, float)
        and math.isfinite(actual)
        and math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance)
    )


def submission_bytes(store, state, submission, artifact_id):
    version_id = submission["artifact_versions"][artifact_id]
    artifact = state["artifacts"][artifact_id]
    return store.version_path(artifact, version_id).read_bytes()


def evaluate_submission(
    store: Store, state: dict, spec: dict, item: dict, submission: dict | None
) -> dict:
    checks = []
    unassessed_checks = []
    numerical_assessment = "not_submitted"
    layout = layout_for(spec)
    output_locations = [layout.address(f"Outputs!{v}") for v in OUTPUT_CELLS.values()]

    def check(name, condition, category, detail=""):
        checks.append(
            {"name": name, "passed": bool(condition), "category": category, "detail": detail}
        )

    def unassessed(name, category):
        unassessed_checks.append(
            {
                "name": name,
                "category": category,
                "reason": "missing_applicable_approved_basis",
            }
        )

    if submission is None:
        check("submitted", False, "delivery", "No actual submission")
    else:
        numerical_assessment = "available"
        pinned = submission["artifact_versions"]
        check(
            "requirement_version",
            submission["requirement_version"] == item["requirement_version"],
            "state",
        )
        check(
            "executed_submission",
            any(
                row["action"] == "submit"
                and row["actor_id"] == "analyst"
                and row["output"].get("result", {}).get("submission_id")
                == submission["submission_id"]
                for row in state["interactions"]
            ),
            "runtime",
        )
        for aid, version_id in pinned.items():
            content = store.version_path(state["artifacts"][aid], version_id).read_bytes()
            check(
                f"file_integrity:{aid}",
                digest(content) == state["artifacts"][aid]["versions"][version_id]["sha256"],
                "runtime",
            )
        try:
            revision = item["requirement_version"]
            source_version = item.get("source_version", f"v{revision + 1}")
            delivery = state["project"]["delivery"]
            facts = spec["facts"][
                item.get("source_stage", "current" if revision == 1 else "future")
            ]
            approved = None
            if "basis" in state["artifacts"] and delivery != "short":
                approved = requirement_basis(store, state, item)
                check("approved_basis_applicable", approved is not None, "basis")
                assumptions = approved["assumptions"] if approved else None
                if approved is None:
                    numerical_assessment = "blocked_missing_approved_basis"
            else:
                assumptions = scope(spec, item.get("scenario_revision", revision))["assumptions"]
            if delivery == "short":
                model = SemanticSpreadsheet(
                    store.version_path(
                        state["artifacts"]["model"], submission["context_versions"]["model"]
                    ).read_bytes(),
                    layout,
                )
                answer = submission["answer"]
                expected = round(model.value("Outputs!B6") / facts["diluted_eps"], 2)
                check(
                    "specified_source_pe",
                    isinstance(answer, dict) and close(answer.get("pe"), expected, 1e-8),
                    "source_selection",
                )
                check(
                    "answer_citations",
                    isinstance(answer, dict)
                    and citation_contract("short", output_locations).validate(
                        answer.get("citations"),
                        {
                            "financials": source_version,
                            "model": submission["context_versions"]["model"],
                        },
                    ),
                    "provenance",
                )
                check(
                    "existing_model_unchanged",
                    submission["context_versions"]["model"] == "v1",
                    "scope",
                )
            else:
                model_version = pinned.get("model", submission["context_versions"]["model"])
                content = store.version_path(
                    state["artifacts"]["model"], model_version
                ).read_bytes()
                model = SemanticSpreadsheet(content, layout)
                inputs = {**facts, **(assumptions or {})}
                for name, cell in INPUT_CELLS.items():
                    if name not in inputs:
                        unassessed(f"input:{name}", "inputs")
                        continue
                    check(
                        f"input:{name}",
                        close(model.value(f"Inputs!{cell}"), inputs[name]),
                        "inputs",
                    )
                expected = financial_result(inputs) if assumptions is not None else None
                for name, cell in OUTPUT_CELLS.items():
                    if expected is None:
                        unassessed(f"output:{name}", "calculation")
                        continue
                    check(
                        f"output:{name}",
                        close(model.value(f"Outputs!{cell}"), expected[name]),
                        "calculation",
                    )
                deps = state["artifacts"]["model"]["versions"][model_version]["derived_from"]
                check(
                    "model_source_version",
                    {"artifact_id": "financials", "version_id": source_version} in deps,
                    "dependency",
                )
                if "basis" in state["artifacts"]:
                    check(
                        "model_basis_binding",
                        approved is not None and item.get("required_basis") in deps,
                        "basis",
                    )
                grid = assumptions["growth_grid"] if assumptions else ()
                margins = assumptions["margin_delta_grid"] if assumptions else ()
                if assumptions is None:
                    for name in (
                        "growth_header:B",
                        "growth_header:C",
                        "margin_header:2",
                        "margin_header:3",
                    ):
                        unassessed(name, "scenario")
                    for cell in ("B2", "B3", "C2", "C3"):
                        unassessed(f"scenario:{cell}", "scenario")
                for col, growth in zip("BC", grid):
                    check(
                        f"growth_header:{col}",
                        close(model.value(f"Sensitivity!{col}1"), growth),
                        "scenario",
                    )
                    for row, delta in zip((2, 3), margins):
                        check(
                            f"margin_header:{row}",
                            close(model.value(f"Sensitivity!A{row}"), delta),
                            "scenario",
                        )
                        result = financial_result(
                            {**inputs, "growth": growth, "margin_delta": delta}
                        )
                        check(
                            f"scenario:{col}{row}",
                            close(model.value(f"Sensitivity!{col}{row}"), result["share_price"]),
                            "scenario",
                        )
                if assumptions is None:
                    for probe_index in range(2):
                        unassessed(f"recomputation_probe:{probe_index}", "recalculability")
                else:
                    # Probe the actual submitted formulas, not saved caches or formula spelling.
                    for probe_index, change in enumerate(
                        (
                            {
                                "revenue": inputs["revenue"] * 1.13,
                                "net_debt": inputs["net_debt"] + 17,
                            },
                            {
                                "operating_margin": inputs["operating_margin"] + 0.017,
                                "growth": inputs["growth"] + 0.011,
                                "margin_delta": inputs["margin_delta"] + 0.009,
                                "tax_rate": 0.29,
                                "earnings_multiple": inputs["earnings_multiple"] + 2,
                                "shares": inputs["shares"] + 13,
                            },
                        )
                    ):
                        perturbed = {**inputs, **change}
                        probe = SemanticSpreadsheet(content, layout)
                        probe.update({f"Inputs!{INPUT_CELLS[k]}": v for k, v in change.items()})
                        reference = financial_result(perturbed)
                        valid = all(
                            close(probe.value(f"Outputs!{cell}"), reference[name])
                            for name, cell in OUTPUT_CELLS.items()
                        )
                        for col, growth in zip("BC", grid):
                            for row, delta in zip((2, 3), margins):
                                value = financial_result(
                                    {**perturbed, "growth": growth, "margin_delta": delta}
                                )
                                valid &= close(
                                    probe.value(f"Sensitivity!{col}{row}"), value["share_price"]
                                )
                        check(f"recomputation_probe:{probe_index}", valid, "recalculability")
                if "memo" in item["deliverables"]:
                    memo = json.loads(submission_bytes(store, state, submission, "memo"))
                    check("memo_period", memo.get("period") == facts["period"], "period")
                    versions = {"financials": source_version, "model": model_version}
                    check(
                        "memo_bound_versions", memo.get("source_versions") == versions, "dependency"
                    )
                    metadata = state["artifacts"]["memo"]["versions"][pinned["memo"]]
                    check(
                        "memo_required_dependencies",
                        required_dependencies_match(metadata["derived_from"], versions),
                        "dependency",
                    )
                    check(
                        "memo_dependency_body_agreement",
                        required_dependencies_match(
                            metadata["derived_from"], memo.get("source_versions", {})
                        )
                        and memo.get("source_versions") == versions,
                        "dependency",
                    )
                    for name in OUTPUT_CELLS:
                        if expected is None:
                            unassessed(f"memo:{name}", "consistency")
                            continue
                        check(
                            f"memo:{name}",
                            close(memo.get("metrics", {}).get(name), expected[name]),
                            "consistency",
                        )
                    check(
                        "memo_citations",
                        citation_contract("memo", output_locations).validate(
                            memo.get("citations"), versions
                        ),
                        "provenance",
                    )
                    check(
                        "explanation_present",
                        isinstance(memo.get("explanation"), str)
                        and len(memo["explanation"].strip()) >= 20,
                        "explanation",
                    )
                if "note" in item["deliverables"]:
                    note = json.loads(submission_bytes(store, state, submission, "note"))
                    brief_version = submission["context_versions"]["brief"]
                    brief = json.loads(
                        store.version_path(state["artifacts"]["brief"], brief_version).read_bytes()
                    )
                    versions = {"model": model_version, "brief": brief_version}
                    declared = state["artifacts"]["note"]["versions"][pinned["note"]][
                        "derived_from"
                    ]
                    check("note_versions", note.get("source_versions") == versions, "dependency")
                    check(
                        "note_required_dependencies",
                        required_dependencies_match(declared, versions),
                        "dependency",
                    )
                    check("note_audience", note.get("audience") == brief["audience"], "scope")
                    if state["schema_version"] == "0.3":
                        issues = audience_content_defects(
                            note.get("audience_content"), brief["audience"]
                        )
                        check("note_audience_content", not issues, "scope", "; ".join(issues))
                    if expected is None:
                        unassessed("note_price", "consistency")
                        for cell in ("B2", "B3", "C2", "C3"):
                            unassessed(f"note_scenario:{cell}", "scenario")
                    else:
                        check(
                            "note_price",
                            close(note.get("share_price"), expected["share_price"]),
                            "consistency",
                        )
                    for col, growth in zip("BC", grid):
                        for row, delta in zip((2, 3), margins):
                            value = financial_result(
                                {**inputs, "growth": growth, "margin_delta": delta}
                            )
                            check(
                                f"note_scenario:{col}{row}",
                                close(
                                    note.get("sensitivity", {}).get(f"{col}{row}"),
                                    value["share_price"],
                                ),
                                "scenario",
                            )
                for aid, version in item.get("protected_versions", {}).items():
                    check(
                        f"unaffected_artifact_unchanged:{aid}",
                        submission["context_versions"][aid] == version,
                        "scope",
                    )
        except (KeyError, ValueError, TypeError, AttributeError, ArithmeticError) as exc:
            check("readable_required_artifacts", False, "artifact", str(exc))
    passed = all(c["passed"] for c in checks)
    record = EvaluationRecord(
        instance_id=state["instance_id"],
        branch_id=state["branch_id"],
        work_item_id=item["work_item_id"],
        requirement_version=item["requirement_version"],
        submission_id=submission["submission_id"] if submission else None,
        passed=passed,
        reward=float(passed),
        checks=checks,
        uncertain=["解释的专业充分性及现实业务适用性尚未经专家评审。"],
        evaluator_version=EVALUATOR_VERSION
        if "basis" in state["artifacts"]
        else "operating-toy-v0.2"
        if spec.get("workflow")
        else LEGACY_EVALUATOR_VERSION,
    )
    result = asdict(record)
    result["numerical_assessment"] = numerical_assessment
    result["unassessed_checks"] = unassessed_checks
    if numerical_assessment == "blocked_missing_approved_basis":
        result["uncertain"].append(
            "缺少适用的已批准依据；依赖该依据的数值目标未评分，不使用隐藏规格替代确认。"
        )
    result["contract_version"] = spec.get("contract_version", LEGACY_CONTRACT_VERSION)
    result["contract_origin"] = (
        "stored" if "contract_version" in spec else "inferred_from_original_public_guide"
    )
    result["artifact_valid"] = passed
    result["currently_applicable"] = current_id(state, item["work_item_id"]) == item[
        "work_item_id"
    ] and not (submission and submission.get("invalidated"))
    result["assessment_scope"] = "pinned_submission_against_its_requirement_version"
    failed = [c for c in checks if not c["passed"]]
    basis_errors = [c["name"] for c in failed if c["category"] == "basis"]
    assumption_errors = [
        c["name"]
        for c in failed
        if c["name"]
        in {
            f"input:{name}"
            for name in (
                "growth",
                "margin_delta",
                "tax_rate",
                "earnings_multiple",
                "net_debt",
                "shares",
            )
        }
    ]
    result["root_causes"] = []
    if basis_errors:
        result["root_causes"].append(
            {"code": "approved_basis_not_applicable_or_unbound", "evidence_checks": basis_errors}
        )
    elif assumption_errors:
        result["root_causes"].append(
            {"code": "approved_assumptions_not_applied", "evidence_checks": assumption_errors}
        )
    result["propagated_failures"] = [
        c["name"]
        for c in failed
        if result["root_causes"]
        and c["category"] in ("calculation", "consistency", "recalculability")
    ]
    result["diagnostic_interpretation"] = (
        "Dependency-based grouping, not a claim about the worker's mental cause or independent capability deficits."
    )
    result["business_accepted"] = bool(
        submission and (submission.get("review") or {}).get("decision") == "accepted"
    )
    result["explanation_assessed"] = False
    result["supervision_status"] = (
        "outcome_conditioned_candidate" if passed else "rejected_artifact"
    )
    result["verified_dependencies"] = {}
    if passed and submission:
        for aid, version in submission["artifact_versions"].items():
            result["verified_dependencies"][aid] = state["artifacts"][aid]["versions"][version][
                "derived_from"
            ]
    return result


def evaluate(root, work_item_id: str | None = None) -> list[dict]:
    store = Store(root)
    with store.lock():
        state = store.load()
        spec = read_json(store.control / "spec.json")
        items = (
            [state["work_items"][work_item_id]] if work_item_id else state["work_items"].values()
        )
        records = []
        for item in items:
            submissions = item["submissions"] or [None]
            records.extend(
                evaluate_submission(store, state, spec, item, sub) for sub in submissions
            )
        keys = {(r["work_item_id"], r["submission_id"], r["evaluator_version"]) for r in records}
        state["evaluations"] = [
            r
            for r in state["evaluations"]
            if (r["work_item_id"], r["submission_id"], r["evaluator_version"]) not in keys
        ] + records
        store.save(state)
        return records
