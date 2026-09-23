"""Read-only content contracts for finite JSON/XLSX work products.

The evaluator reads immutable submitted bytes and persisted XLSX value caches.
It does not invoke Spreadsheet or infer correctness from an institutional review,
adoption status label, current materialization, or a hidden answer workbook.
Scalar expected values must be declared in the contract by its author.
"""

import copy
import hashlib
import io
import json
import math

from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple

from ..core.adoption import binding_key, require_version
from ..core.references import VersionRef


_KINDS = {
    "json_field_equals",
    "xlsx_cell_equals",
    "xlsx_no_formula_errors",
    "json_matches_source_cell",
    "json_matches_source_field",
}
_COMMON = {"kind", "role"}
EVALUATOR_VERSION = "finite-products-v0.8"


def _path(value, label):
    if isinstance(value, str):
        value = value.split(".")
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(part, str) or not part for part in value)
    ):
        raise ValueError(label + " must be a nonempty JSON field path")
    return value


def _cell(check):
    if not isinstance(check.get("sheet"), str) or not check["sheet"]:
        raise ValueError("XLSX check requires a sheet name")
    cell = check.get("cell")
    if not isinstance(cell, str):
        raise ValueError("XLSX check requires a cell address")
    try:
        row, column = coordinate_to_tuple(cell)
    except (ValueError, KeyError) as exc:
        raise ValueError("Invalid XLSX cell address") from exc
    if not 1 <= row <= 2000 or not 1 <= column <= 100:
        raise ValueError("XLSX contract cell exceeds bounded capability")
    check["cell"] = cell.upper()


def validate_content_contract(contract):
    """Validate only this module's extension and preserve the base contract."""
    if not isinstance(contract, dict):
        raise ValueError("Deliverable contract must be an object")
    result = copy.deepcopy(contract)
    checks = result.setdefault("content_checks", [])
    if not isinstance(checks, list) or len(checks) > 100:
        raise ValueError("content_checks must contain at most 100 finite checks")
    for check in checks:
        if not isinstance(check, dict) or check.get("kind") not in _KINDS:
            raise ValueError("Unknown work product content check")
        kind = check["kind"]
        fields = set(_COMMON)
        if kind.startswith("json_"):
            fields.add("path")
            check["path"] = _path(check.get("path"), "path")
        if kind in {"xlsx_cell_equals", "json_matches_source_cell"}:
            fields |= {"sheet", "cell"}
            _cell(check)
        if kind.endswith("_equals"):
            fields.add("expected")
            expected = check.get("expected")
            if (
                "expected" not in check
                or type(expected) not in (str, int, float, bool, type(None))
                or (type(expected) in (int, float) and not math.isfinite(expected))
            ):
                raise ValueError("Expected content must be an explicit finite JSON scalar")
        if kind.startswith("json_matches_source_"):
            fields |= {"reference_path", "adoption_alias"}
            check["reference_path"] = _path(check.get("reference_path"), "reference_path")
            if not isinstance(check.get("adoption_alias"), str) or not check["adoption_alias"]:
                raise ValueError("Source check requires an adoption_alias")
            if kind == "json_matches_source_field":
                fields.add("source_path")
                check["source_path"] = _path(check.get("source_path"), "source_path")
        if "role" in check and (not isinstance(check["role"], str) or not check["role"]):
            raise ValueError("Content check role must be a nonempty string")
        if set(check) - fields:
            raise ValueError(
                "Unknown content check fields: " + ", ".join(sorted(set(check) - fields))
            )
    return result


def _at_path(data, path):
    for key in path:
        if not isinstance(data, dict) or key not in data:
            raise ValueError("Missing JSON path: " + ".".join(path))
        data = data[key]
    return data


def _equal(actual, expected):
    """JSON equality at every depth, preserving the finite numeric contract."""
    if type(actual) in (int, float) and type(expected) in (int, float):
        return math.isfinite(actual) and math.isfinite(expected) and actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            _equal(value, expected[key]) for key, value in actual.items()
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _equal(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def _merge_json(documents):
    """Union whole top-level fields; conflicting values have no selected winner.

    A conflict remains a conflict when a third document repeats either value.
    This deliberately does not recursively merge overlapping nested objects.
    """
    values, conflicts = {}, set()
    for document in documents:
        for key, value in document.items():
            if key in values and not _equal(values[key], value):
                conflicts.add(key)
            else:
                values[key] = value
    return {key: value for key, value in values.items() if key not in conflicts}, conflicts


def _books(content):
    return (
        load_workbook(io.BytesIO(content), data_only=False),
        load_workbook(io.BytesIO(content), data_only=True),
    )


def _cached_cell(content, sheet, cell):
    raw, values = _books(content)
    if sheet not in raw.sheetnames:
        raise ValueError("Missing XLSX sheet: " + sheet)
    original, cached = raw[sheet][cell], values[sheet][cell]
    if original.data_type == "e" or cached.data_type == "e":
        raise ValueError("XLSX cell has persisted error: " + str(cached.value))
    if original.data_type == "f" and cached.value is None:
        raise ValueError("XLSX formula has no persisted value cache")
    return cached.value


def evaluate_submission(store, state, item, submission):
    """Evaluate fixed submitted versions; return all checks, exact reads and errors.

    Source-linked checks require the submission's adoption_snapshot, including
    its policy target at submission time. Later releases or adoption changes do
    not rewrite the meaning of a historical submission.
    """
    contract = validate_content_contract(
        submission["requirement_snapshot"].get("deliverable_contract", {})
    )
    reads, content_cache, errors = [], {}, []

    def read_version(aid, vid):
        key = (aid, vid)
        if key not in content_cache:
            artifact = state["artifacts"].get(aid)
            if artifact is None or vid not in artifact["versions"]:
                raise ValueError("Unknown exact content version")
            content = store.version_path(artifact, vid).read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            if sha != artifact["versions"][vid]["sha256"]:
                raise ValueError("Immutable content does not match its committed digest")
            content_cache[key] = content
            reads.append({"object_id": aid, "version_id": vid, "sha256": sha})
        return content_cache[key]

    submitted = []
    for aid, vid in submission["artifact_versions"].items():
        artifact = state["artifacts"][aid]
        try:
            content = read_version(aid, vid)
            data = json.loads(content) if artifact["kind"] == "json" else None
            if data is not None:
                if not isinstance(data, dict):
                    raise ValueError("Submitted JSON must be an object")
            submitted.append(
                {"artifact": artifact, "version_id": vid, "content": content, "data": data}
            )
        except (ValueError, OSError, KeyError) as exc:
            errors.append(str(exc))
    combined, conflicts = _merge_json(
        entry["data"] for entry in submitted if entry["data"] is not None
    )
    missing = sorted(set(contract.get("required_fields", [])) - (set(combined) | conflicts))
    checks = []
    for spec in contract["content_checks"]:
        outcome = {"kind": spec["kind"], "contract": copy.deepcopy(spec), "passed": False}
        try:
            selected = [
                entry
                for entry in submitted
                if ("role" not in spec or entry["artifact"].get("deliverable_role") == spec["role"])
            ]
            json_data, selected_conflicts = _merge_json(
                entry["data"] for entry in selected if entry["data"] is not None
            )
            kind = spec["kind"]
            if kind.startswith("json_"):
                required_roots = {spec["path"][0]}
                if "reference_path" in spec:
                    required_roots.add(spec["reference_path"][0])
                relevant_conflicts = sorted(required_roots & selected_conflicts)
                if relevant_conflicts:
                    raise ValueError("Conflicting JSON fields: " + ", ".join(relevant_conflicts))
            if kind == "json_field_equals":
                actual, expected = _at_path(json_data, spec["path"]), spec["expected"]
                outcome.update(actual=actual, expected=expected, passed=_equal(actual, expected))
            elif kind == "xlsx_cell_equals":
                candidates = [entry for entry in selected if entry["artifact"]["kind"] == "xlsx"]
                if len(candidates) != 1:
                    raise ValueError("XLSX cell contract requires exactly one matching workbook")
                actual = _cached_cell(candidates[0]["content"], spec["sheet"], spec["cell"])
                outcome.update(
                    actual=actual,
                    expected=spec["expected"],
                    passed=_equal(actual, spec["expected"]),
                )
            elif kind == "xlsx_no_formula_errors":
                candidates = [entry for entry in selected if entry["artifact"]["kind"] == "xlsx"]
                if not candidates:
                    raise ValueError("No submitted workbook for formula check")
                formula_errors = []
                for entry in candidates:
                    raw, values = _books(entry["content"])
                    for sheet in raw:
                        for row in sheet:
                            for cell in row:
                                cached = values[sheet.title][cell.coordinate]
                                if (
                                    cell.data_type == "e"
                                    or cached.data_type == "e"
                                    or (cell.data_type == "f" and cached.value is None)
                                ):
                                    formula_errors.append(
                                        {
                                            "object_id": entry["artifact"]["artifact_id"],
                                            "cell": sheet.title + "!" + cell.coordinate,
                                            "formula": cell.value,
                                            "cached": cached.value,
                                        }
                                    )
                outcome.update(formula_errors=formula_errors, passed=not formula_errors)
            else:
                reference = _at_path(json_data, spec["reference_path"])
                if not isinstance(reference, dict):
                    raise ValueError("Source reference must be an exact object/version mapping")
                ref = VersionRef.from_mapping(reference)
                key = binding_key(item["work_item_id"], spec["adoption_alias"])
                snapshots = submission.get("adoption_snapshot", {})
                adoption = snapshots.get(key)
                if adoption is None:
                    raise ValueError("UNASSESSED: submission has no adoption snapshot")
                if (adoption["object_id"], adoption["version_id"]) != (
                    ref.object_id,
                    ref.version_id,
                ):
                    raise ValueError("Content source does not match the adopted exact version")
                if (
                    adoption.get("work_id") != item["work_item_id"]
                    or adoption.get("work_ids") != [item["work_item_id"]]
                    or adoption.get("project_id") != item["project_id"]
                    or adoption.get("alias") != spec["adoption_alias"]
                    or adoption.get("requirement_version") != submission["requirement_version"]
                ):
                    raise ValueError("Adoption does not cover the evaluated work edition")
                require_version(
                    submission["requirement_snapshot"], spec["adoption_alias"],
                    adoption["version_id"], adoption["policy"],
                )
                if adoption["policy"] != "fixed":
                    target = adoption.get("target_version")
                    if target is None or ref.version_id != target:
                        raise ValueError(
                            "Content source does not match the policy target at submission"
                        )
                binding_files = []
                for entry in selected:
                    if entry["data"] is None:
                        continue
                    contributes = False
                    for path in (spec["path"], spec["reference_path"]):
                        try:
                            _at_path(entry["data"], path)
                            contributes = True
                        except ValueError:
                            pass
                    if not contributes:
                        continue
                    metadata = entry["artifact"]["versions"][entry["version_id"]]
                    dependencies = [
                        VersionRef.from_mapping(value) for value in metadata.get("derived_from", [])
                    ]
                    if ref not in dependencies:
                        raise ValueError(
                            "Contributing submitted file lacks the exact source dependency: "
                            + entry["artifact"]["artifact_id"]
                            + "@"
                            + entry["version_id"]
                        )
                    binding_files.append(
                        {
                            "object_id": entry["artifact"]["artifact_id"],
                            "version_id": entry["version_id"],
                        }
                    )
                outcome["binding_files"] = binding_files
                source = read_version(ref.object_id, ref.version_id)
                artifact = state["artifacts"][ref.object_id]
                if kind == "json_matches_source_cell":
                    if artifact["kind"] != "xlsx":
                        raise ValueError("Adopted source must be an XLSX workbook")
                    expected = _cached_cell(source, spec["sheet"], spec["cell"])
                else:
                    if artifact["kind"] != "json":
                        raise ValueError("Adopted source must be JSON")
                    expected = _at_path(json.loads(source), spec["source_path"])
                actual = _at_path(json_data, spec["path"])
                outcome.update(
                    actual=actual,
                    expected=expected,
                    source=ref.to_dict(),
                    passed=_equal(actual, expected),
                )
            if not outcome["passed"]:
                outcome.setdefault(
                    "reason", "Submitted content does not satisfy the declared contract"
                )
        except (ValueError, KeyError, OSError, TypeError) as exc:
            outcome["reason"] = str(exc)
        checks.append(outcome)
    return {
        "submission_id": submission["submission_id"],
        "evaluator_version": EVALUATOR_VERSION,
        "passed": not missing and not conflicts and not errors and all(c["passed"] for c in checks),
        "missing_fields": missing,
        "conflicting_fields": sorted(set(conflicts)),
        "checks": checks,
        "errors": errors,
        "read_set": reads,
        "scope": "finite_json_xlsx_content_contract",
        "institutional_review": copy.deepcopy(submission.get("review")),
    }
