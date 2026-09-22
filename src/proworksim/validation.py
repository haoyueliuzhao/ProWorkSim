"""Independent evaluation of pinned submissions, never exposed as a worker tool."""

import json
import math
from dataclasses import asdict

from .compiler import INPUT_CELLS, OUTPUT_CELLS, scope
from .schema import EvaluationRecord
from .spreadsheet import Spreadsheet
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


def check_citations(
    citations, expected_versions: dict, state: dict, store: Store, required=None
) -> bool:
    if not isinstance(citations, list) or not citations:
        return False
    cited = set()
    for citation in citations:
        if not isinstance(citation, dict):
            return False
        aid = citation.get("artifact_id")
        version = citation.get("version_id")
        location = citation.get("location")
        if (
            aid not in expected_versions
            or version != expected_versions[aid]
            or not isinstance(location, str)
        ):
            return False
        if aid == "financials":
            data = json.loads(store.version_path(state["artifacts"][aid], version).read_bytes())
            if location not in {f"values.{k}" for k in data["values"]}:
                return False
        elif aid == "model":
            if location not in {f"Outputs!{v}" for v in OUTPUT_CELLS.values()}:
                return False
        cited.add((aid, location))
    if required is not None:
        return set(required) <= cited
    return set(expected_versions) <= {aid for aid, _ in cited}


def evaluate_submission(
    store: Store, state: dict, spec: dict, item: dict, submission: dict | None
) -> dict:
    checks = []

    def check(name, condition, category, detail=""):
        checks.append(
            {"name": name, "passed": bool(condition), "category": category, "detail": detail}
        )

    if submission is None:
        check("submitted", False, "delivery", "No actual submission")
    else:
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
            source_version = f"v{revision + 1}"
            delivery = state["project"]["delivery"]
            facts = spec["facts"]["current" if revision == 1 else "future"]
            assumptions = scope(spec, revision)["assumptions"]
            if delivery == "short":
                model = Spreadsheet(
                    store.version_path(
                        state["artifacts"]["model"], submission["context_versions"]["model"]
                    ).read_bytes()
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
                    and check_citations(
                        answer.get("citations"),
                        {
                            "financials": source_version,
                            "model": submission["context_versions"]["model"],
                        },
                        state,
                        store,
                        required=[("model", "Outputs!B6"), ("financials", "values.diluted_eps")],
                    ),
                    "provenance",
                )
                check(
                    "existing_model_unchanged",
                    submission["context_versions"]["model"] == "v1",
                    "scope",
                )
            else:
                content = submission_bytes(store, state, submission, "model")
                model = Spreadsheet(content)
                inputs = {**facts, **assumptions}
                for name, cell in INPUT_CELLS.items():
                    check(
                        f"input:{name}",
                        close(model.value(f"Inputs!{cell}"), inputs[name]),
                        "inputs",
                    )
                expected = financial_result(inputs)
                for name, cell in OUTPUT_CELLS.items():
                    check(
                        f"output:{name}",
                        close(model.value(f"Outputs!{cell}"), expected[name]),
                        "calculation",
                    )
                deps = state["artifacts"]["model"]["versions"][pinned["model"]]["derived_from"]
                check(
                    "model_source_version",
                    {"artifact_id": "financials", "version_id": source_version} in deps,
                    "dependency",
                )
                grid = assumptions["growth_grid"]
                margins = assumptions["margin_delta_grid"]
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
                # Probe the actual submitted formulas, not saved caches or formula spelling.
                for probe_index, change in enumerate(
                    (
                        {"revenue": inputs["revenue"] * 1.13, "net_debt": inputs["net_debt"] + 17},
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
                    probe = Spreadsheet(content)
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
                if delivery == "continuous":
                    memo = json.loads(submission_bytes(store, state, submission, "memo"))
                    check("memo_period", memo.get("period") == facts["period"], "period")
                    versions = {"financials": source_version, "model": pinned["model"]}
                    check(
                        "memo_bound_versions", memo.get("source_versions") == versions, "dependency"
                    )
                    for name in OUTPUT_CELLS:
                        check(
                            f"memo:{name}",
                            close(memo.get("metrics", {}).get(name), expected[name]),
                            "consistency",
                        )
                    check(
                        "memo_citations",
                        check_citations(
                            memo.get("citations"),
                            versions,
                            state,
                            store,
                            required=[("financials", "values.revenue")],
                        ),
                        "provenance",
                    )
                    check(
                        "explanation_present",
                        isinstance(memo.get("explanation"), str)
                        and len(memo["explanation"].strip()) >= 20,
                        "explanation",
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
        evaluator_version="finance-v0.1.1",
    )
    return asdict(record)


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
