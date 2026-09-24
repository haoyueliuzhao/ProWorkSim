"""Finite set reconciliation, evaluated against immutable public source tables.

This evaluator checks the submitted partition and each evidence claim directly.
It does not invoke the worker's matching algorithm, choose a winning source, or
infer professional completeness outside the declared fields and unit rules.
"""

import copy
import math

from ..evaluation import EvaluationInputError

CHECK_KIND = "reconciliation_table"
STATUSES = ("matched", "converted", "conflict", "incomparable", "missing", "ambiguous")
RECORD_FIELDS = (
    "record_id",
    "entity",
    "metric",
    "period",
    "definition",
    "currency",
    "unit",
    "value",
    "location",
)
EVIDENCE_FIELDS = ("record_id", "location", "period", "definition", "currency", "unit", "value")


def validate_check(spec):
    spec = copy.deepcopy(spec)
    allowed = {"kind", "role", "path", "sources", "left_alias", "right_alias", "policy_alias"}
    if spec.get("kind") != CHECK_KIND or set(spec) - allowed:
        raise ValueError("Invalid finite reconciliation contract fields")
    for field in ("path",):
        value = spec.get(field)
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(x, str) or not x for x in value)
        ):
            raise ValueError("Reconciliation requires nonempty JSON paths")
    aliases = []
    if not isinstance(spec.get("sources"), list) or len(spec["sources"]) != 3:
        raise ValueError("Reconciliation requires exactly two tables and one policy source")
    for source in spec["sources"]:
        if (
            not isinstance(source, dict)
            or not {"alias", "reference_path"} <= set(source)
            or set(source) - {"alias", "reference_path", "data_path"}
        ):
            raise ValueError("Invalid reconciliation source declaration")
        alias, path = source["alias"], source["reference_path"]
        if not isinstance(alias, str) or not alias or alias in aliases:
            raise ValueError("Source aliases must be distinct strings")
        if (
            not isinstance(path, list)
            or not path
            or any(not isinstance(x, str) or not x for x in path)
        ):
            raise ValueError("Source reference_path must be a JSON path")
        data_path = source.setdefault("data_path", [])
        if not isinstance(data_path, list) or any(
            not isinstance(x, str) or not x for x in data_path
        ):
            raise ValueError("Source data_path must select public JSON content")
        aliases.append(alias)
    roles = [spec.get(field) for field in ("left_alias", "right_alias", "policy_alias")]
    if len(set(roles)) != 3 or set(roles) != set(aliases):
        raise ValueError("Reconciliation source roles must identify all declared aliases")
    if "role" in spec and (not isinstance(spec["role"], str) or not spec["role"]):
        raise ValueError("Reconciliation role must be a nonempty string")
    return spec


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _same(actual, expected):
    if _number(actual) and _number(expected):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            _same(actual[k], expected[k]) for k in actual
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _validate_output(data, path):
    def require(condition, reason):
        if not condition:
            raise EvaluationInputError("structure_failure", reason)

    def strings(value):
        return isinstance(value, list) and all(isinstance(x, str) for x in value)

    def key(value):
        return strings(value) and len(value) == 2

    output = data
    for part in path:
        require(isinstance(output, dict) and part in output, "Missing delivered target path")
        output = output[part]
    require(isinstance(output, dict), "Delivered reconciliation target must be an object")
    require(
        set(output) == {"rows", "summary", "unresolved", "period", "base_unit"},
        "Delivered reconciliation fields do not match the declared shape",
    )
    require(isinstance(output["rows"], list), "Delivered reconciliation.rows must be a list")
    fields = {
        "key",
        "period",
        "status",
        "left_ids",
        "right_ids",
        "left_value",
        "right_value",
        "delta",
        "evidence",
    }
    for index, row in enumerate(output["rows"]):
        where = "Delivered reconciliation.rows[" + str(index) + "]"
        require(isinstance(row, dict), where + " must be an object")
        require(set(row) == fields, where + " fields do not match the declared shape")
        require(key(row["key"]), where + ".key must contain two strings")
        require(
            row["period"] is None or isinstance(row["period"], str),
            where + ".period must be string or null",
        )
        require(isinstance(row["status"], str), where + ".status must be a string")
        for field in ("left_ids", "right_ids"):
            require(strings(row[field]), where + "." + field + " must contain strings")
        for field in ("left_value", "right_value", "delta"):
            require(
                row[field] is None or _number(row[field]),
                where + "." + field + " must be finite number or null",
            )
        require(isinstance(row["evidence"], list), where + ".evidence must be a list")
        for evidence in row["evidence"]:
            require(
                isinstance(evidence, dict) and set(evidence) == {"alias", *EVIDENCE_FIELDS},
                where + ".evidence entries must match the evidence shape",
            )
            require(
                all(
                    isinstance(evidence[field], str)
                    for field in {"alias", *EVIDENCE_FIELDS} - {"value"}
                ),
                where + ".evidence identity fields must be strings",
            )
            require(
                evidence["value"] is None or _number(evidence["value"]),
                where + ".evidence.value must be finite number or null",
            )
    require(
        isinstance(output["summary"], dict) and set(output["summary"]) == set(STATUSES),
        "Delivered summary must declare every finite status",
    )
    require(
        all(type(value) is int and value >= 0 for value in output["summary"].values()),
        "Delivered summary counts must be nonnegative integers",
    )
    require(
        isinstance(output["unresolved"], list)
        and all(key(value) for value in output["unresolved"]),
        "Delivered unresolved must contain two-string keys",
    )
    require(
        isinstance(output["period"], str) and isinstance(output["base_unit"], str),
        "Delivered period/base_unit must be strings",
    )
    return output


def evaluate_check(spec, output_data, load_source):
    """Validate coverage and conclusions; return failures without mutating inputs."""
    spec = validate_check(spec)
    diagnostics = []
    result = {
        "passed": False,
        "diagnostics": diagnostics,
        "quality_scope": "Finite record coverage, comparison applicability, exact unit conversion, conflict/unknown preservation and evidence; no open financial judgment",
    }
    try:
        output = _validate_output(output_data, spec["path"])
    except EvaluationInputError as exc:
        result.update(status=exc.status)
        diagnostics.append({"issue": "delivery_structure", "reason": str(exc)})
        return result
    try:
        selected_sources = {}
        for source in spec["sources"]:
            value = load_source(source["alias"])
            for part in source["data_path"]:
                value = value[part]
            selected_sources[source["alias"]] = value
        policy = selected_sources[spec["policy_alias"]]
        if not isinstance(policy, dict) or policy.get("key_fields") != ["entity", "metric"]:
            raise ValueError("Only the declared entity/metric key is supported")
        factors = policy.get("unit_factors")
        if (
            not isinstance(factors, dict)
            or not factors
            or any(not isinstance(k, str) or not _number(v) or v <= 0 for k, v in factors.items())
        ):
            raise ValueError("Public policy requires positive finite unit factors")
        if factors.get(policy.get("base_unit")) != 1 or not isinstance(
            policy.get("reporting_period"), str
        ):
            raise ValueError("Public policy requires a base unit and reporting period")
        tables = {}
        for alias in (spec["left_alias"], spec["right_alias"]):
            table = selected_sources[alias]
            if not isinstance(table, dict):
                raise ValueError("Source table must be an object")
            records = table["records"]
            if not isinstance(records, list) or len(records) > 200:
                raise ValueError("Source table must contain at most 200 rows")
            ids = set()
            for record in records:
                if not isinstance(record, dict) or set(record) != set(RECORD_FIELDS):
                    raise ValueError("Source row does not match finite record schema")
                if any(
                    not isinstance(record[f], str) or not record[f]
                    for f in RECORD_FIELDS
                    if f != "value"
                ):
                    raise ValueError(
                        "Source identity/applicability fields must be nonempty strings"
                    )
                if record["record_id"] in ids or (
                    record["value"] is not None and not _number(record["value"])
                ):
                    raise ValueError("Source row IDs must be unique and values finite or null")
                ids.add(record["record_id"])
            tables[alias] = records
    except (KeyError, TypeError, ValueError, OSError, OverflowError) as exc:
        result.update(status="source_unavailable")
        diagnostics.append({"issue": "source_unavailable", "reason": str(exc)})
        return result
    # All container/element shapes are established above. Unexpected failures in
    # the actual checker propagate to the explicit evaluator-error boundary.
    try:
        expected_keys = {(r["entity"], r["metric"]) for records in tables.values() for r in records}
        rows = output.get("rows")
        if not isinstance(rows, list):
            raise ValueError("Delivered reconciliation.rows must be a list")
        supplied_keys = [tuple(r.get("key", [])) for r in rows]
        if len(supplied_keys) != len(set(supplied_keys)) or set(supplied_keys) != expected_keys:
            diagnostics.append(
                {
                    "issue": "coverage",
                    "expected_keys": sorted(expected_keys),
                    "actual_keys": supplied_keys,
                }
            )
        counts = dict.fromkeys(STATUSES, 0)
        unresolved = []
        allowed_row = {
            "key",
            "period",
            "status",
            "left_ids",
            "right_ids",
            "left_value",
            "right_value",
            "delta",
            "evidence",
        }
        for row, key in zip(rows, supplied_keys):
            if key not in expected_keys:
                continue
            left = [r for r in tables[spec["left_alias"]] if (r["entity"], r["metric"]) == key]
            right = [r for r in tables[spec["right_alias"]] if (r["entity"], r["metric"]) == key]
            values = {"left_value": None, "right_value": None, "delta": None, "period": None}
            if len(left) > 1 or len(right) > 1:
                status = "ambiguous"
            elif not left or not right:
                status = "missing"
            else:
                lrow, rrow = left[0], right[0]
                if lrow["period"] == rrow["period"]:
                    values["period"] = lrow["period"]
                applicable = (
                    lrow["period"] == rrow["period"] == policy["reporting_period"]
                    and lrow["definition"] == rrow["definition"]
                    and lrow["currency"] == rrow["currency"]
                    and lrow["unit"] in factors
                    and rrow["unit"] in factors
                )
                if not applicable:
                    status = "incomparable"
                elif lrow["value"] is None or rrow["value"] is None:
                    status = "missing"
                else:
                    lv = lrow["value"] * factors[lrow["unit"]]
                    rv = rrow["value"] * factors[rrow["unit"]]
                    if not _number(lv) or not _number(rv) or not _number(lv - rv):
                        raise EvaluationInputError(
                            "source_unavailable", "Normalized amount must remain finite"
                        )
                    values.update(left_value=lv, right_value=rv, delta=lv - rv)
                    status = (
                        "conflict"
                        if lv != rv
                        else ("converted" if lrow["unit"] != rrow["unit"] else "matched")
                    )
            evidence = [
                {"alias": alias, **{field: record[field] for field in EVIDENCE_FIELDS}}
                for alias, records in ((spec["left_alias"], left), (spec["right_alias"], right))
                for record in sorted(records, key=lambda x: x["record_id"])
            ]
            expected = {
                "key": list(key),
                "status": status,
                "left_ids": sorted(r["record_id"] for r in left),
                "right_ids": sorted(r["record_id"] for r in right),
                **values,
                "evidence": evidence,
            }
            # IDs and evidence describe sets; their display order is not a
            # business requirement. Sorting preserves multiplicity, so duplicate
            # matches/evidence still fail rather than disappearing in a set.
            comparable_row = copy.deepcopy(row)
            for field in ("left_ids", "right_ids"):
                comparable_row[field] = sorted(comparable_row.get(field, []))

            def evidence_order(entry):
                return entry["alias"], entry["record_id"]

            comparable_row["evidence"] = sorted(
                comparable_row.get("evidence", []), key=evidence_order
            )
            expected["evidence"] = sorted(expected["evidence"], key=evidence_order)
            if set(row) != allowed_row or not _same(comparable_row, expected):
                diagnostics.append(
                    {"issue": "row_claim", "key": list(key), "expected": expected, "actual": row}
                )
            counts[status] += 1
            if status not in {"matched", "converted"}:
                unresolved.append(list(key))
        for field, expected in (
            ("summary", counts),
            ("unresolved", sorted(unresolved)),
            ("period", policy["reporting_period"]),
            ("base_unit", policy["base_unit"]),
        ):
            actual = output.get(field)
            if field == "unresolved" and isinstance(actual, list):
                actual = sorted(actual)
            if not _same(actual, expected):
                diagnostics.append(
                    {"issue": field, "expected": expected, "actual": output.get(field)}
                )
        if set(output) != {"rows", "summary", "unresolved", "period", "base_unit"}:
            diagnostics.append({"issue": "output_schema"})
        result["passed"] = not diagnostics
        result["record_count"] = sum(len(rows_) for rows_ in tables.values())
        result["group_count"] = len(expected_keys)
        result["status"] = "pass" if result["passed"] else "content_failure"
    except EvaluationInputError as exc:
        result["status"] = exc.status
        diagnostics.append({"issue": exc.status, "reason": str(exc)})
    return result
