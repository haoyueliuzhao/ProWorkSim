"""Finite team SQL contract evaluated from exact adopted data and chosen basis.

Only public business rules are checked. Review-only audit material is a member's
information source, not an extra hidden numerical requirement on the implementer.
"""

import copy
from collections import Counter

from .executable_project import _canonical, _records

CHECK_KIND = "decision_team_sql"


def validate_check(spec):
    result = copy.deepcopy(spec)
    if set(result) - {"kind", "role", "path", "sources", "period"} or result.get("path") != [
        "tables"
    ]:
        raise ValueError("Team SQL check requires its public tables contract")
    if not isinstance(result.get("period"), str) or not result["period"]:
        raise ValueError("Team work needs an explicit public reporting period")
    sources = result.get("sources")
    if (
        not isinstance(sources, list)
        or {s.get("alias") for s in sources if isinstance(s, dict)} != {"data", "basis"}
        or len(sources) != 2
    ):
        raise ValueError("Team SQL requires exact data and business basis sources")
    if any(
        set(s) != {"alias", "reference_path"} or s["reference_path"] != ["sources", s["alias"]]
        for s in sources
    ):
        raise ValueError("Team source paths must identify their declared aliases")
    return result


def evaluate_check(spec, data, load_source):
    try:
        public = load_source("data")["tables"]
        basis = load_source("basis")["tables"]
        meta = _records(basis["basis_meta"])
        if (
            len(meta) != 1
            or meta[0]["edition"] != "approved"
            or meta[0]["period"] != spec["period"]
        ):
            return {"passed": False, "reason": "chosen_basis_not_approved_for_public_period"}
        factor = meta[0]["amount_factor"]
        if type(factor) is not int or factor <= 0:
            raise ValueError("Basis factor must be a positive integer")
        statuses = {r["status"] for r in _records(basis["allowed_statuses"])}
        rows = _records(public["transactions"])
        customers = _records(public["customers"])
        expected = []
        for customer in customers:
            eligible = [
                r
                for r in rows
                if r["customer_id"] == customer["customer_id"]
                and r["period"] == spec["period"]
                and r["status"] in statuses
            ]
            expected.append(
                {
                    "customer_id": customer["customer_id"],
                    "revenue_cents": sum(r["amount"] * factor for r in eligible),
                    "order_count": len({r["order_id"] for r in eligible}),
                }
            )
        actual = data["tables"]
        passed = set(actual) == {"metrics"} and Counter(
            _canonical(r) for r in _records(actual["metrics"])
        ) == Counter(_canonical(r) for r in expected)
        return {
            "passed": passed,
            "reason": "independent_public_team_contract",
            "expected_row_count": len(expected),
            "actual_row_count": len(actual.get("metrics", {}).get("rows", [])),
            "editable_tests_used_as_truth": False,
        }
    except (KeyError, TypeError, ValueError) as error:
        return {
            "passed": False,
            "reason": "invalid_team_sql_product_or_basis",
            "diagnostic": str(error),
        }
