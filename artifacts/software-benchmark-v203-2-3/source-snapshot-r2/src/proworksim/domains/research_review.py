"""Finite report assertions over immutable JSON sources.

The reader-facing body of every contracted section is checked in full, using two
public sentence grammars. Free prose in other sections is deliberately unassessed.
An institutional review or an issue status never supplies a content answer.
"""

import copy
import math
import re

CHECK_KIND = "research_report"
NUMBER = r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?"
UNASSESSED = ["Professional completeness, argument quality, style and uncontracted prose"]


def _path(value, label):
    if (
        not isinstance(value, list)
        or not value
        or any(
            not isinstance(part, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in value
        )
    ):
        raise ValueError(label + " requires a nonempty finite JSON key path")
    return list(value)


def validate_check(spec):
    result = copy.deepcopy(spec)
    if not isinstance(result, dict) or result.get("kind") != CHECK_KIND:
        raise ValueError("Invalid research report check")
    if set(result) - {"kind", "path", "sources", "claims", "role"}:
        raise ValueError("Unknown research report check fields")
    result["path"] = _path(result.get("path"), "report path")
    sources = result.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 8:
        raise ValueError("Report requires one to eight declared sources")
    aliases = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"alias", "reference_path"}:
            raise ValueError("Invalid report source declaration")
        alias = source["alias"]
        if (
            not isinstance(alias, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", alias)
            or alias in aliases
        ):
            raise ValueError("Report aliases must be distinct finite identifiers")
        aliases.add(alias)
        source["reference_path"] = _path(source["reference_path"], "reference_path")
    claims = result.get("claims")
    if not isinstance(claims, list) or not 1 <= len(claims) <= 20:
        raise ValueError("Report requires one to twenty explicit claims")
    ids, sections = set(), set()
    for claim in claims:
        required = {"claim_id", "section_id", "label", "source_alias", "value_path", "period_path"}
        if (
            not isinstance(claim, dict)
            or not required <= set(claim)
            or set(claim) - required - {"previous_path"}
        ):
            raise ValueError("Invalid report claim declaration")
        for field, occupied in (("claim_id", ids), ("section_id", sections)):
            value = claim[field]
            if not isinstance(value, str) or not value or value in occupied:
                raise ValueError("Report claim and section identities must be distinct")
            occupied.add(value)
        label = claim["label"]
        if not isinstance(label, str) or not label.strip() or any(c in label for c in ";:[]\n\r"):
            raise ValueError("Report label must be safe finite sentence text")
        if claim["source_alias"] not in aliases:
            raise ValueError("Report claim source is undeclared")
        for field in ("value_path", "period_path", "previous_path"):
            if field in claim:
                claim[field] = _path(claim[field], field)
    return result


def _at(data, path):
    for key in path:
        if not isinstance(data, dict) or key not in data:
            raise ValueError("Source/report path missing: " + ".".join(path))
        data = data[key]
    return data


def _numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def _parse_body(body, label):
    if not isinstance(body, str):
        return None
    number = "(?P<value>unknown|" + NUMBER + ")"
    trend = r"(?P<trend>up|down|flat|unknown|unassessed)"
    citation = r"(?P<alias>[A-Za-z0-9_-]+):(?P<path>[A-Za-z0-9_.-]+)"
    patterns = [
        re.escape(label)
        + r" in (?P<period>[^;\n]+): "
        + number
        + "; trend "
        + trend
        + "; source "
        + citation
        + r"\.",
        r"(?P<period>[^:\n]+): "
        + re.escape(label)
        + " = "
        + number
        + r" \("
        + trend
        + r"\) \["
        + citation
        + r"\]\.",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, body)
        if match:
            data = match.groupdict()
            data["value"] = None if data["value"] == "unknown" else float(data["value"])
            data["path"] = data["path"].split(".")
            return data
    return None


def evaluate_check(spec, output_data, load_source):
    spec = validate_check(spec)
    diagnostics = []
    try:
        report = _at(output_data, spec["path"])
        sections = report["sections"]
        if not isinstance(sections, list) or any(not isinstance(s, dict) for s in sections):
            raise ValueError("Report sections must be objects")
        section_ids = [s.get("section_id") for s in sections]
        if any(not isinstance(s, str) for s in section_ids) or len(set(section_ids)) != len(
            section_ids
        ):
            raise ValueError("Report section identities must be unique")
        by_id = {s["section_id"]: s for s in sections}
        sources = {item["alias"]: load_source(item["alias"]) for item in spec["sources"]}
        for contract in spec["claims"]:
            claim_id, section_id = contract["claim_id"], contract["section_id"]
            source = sources[contract["source_alias"]]
            value = _at(source, contract["value_path"])
            period = _at(source, contract["period_path"])
            if value is not None and not _numeric(value):
                raise ValueError("Report source value must be numeric or explicitly null")
            if not isinstance(period, str) or not period or any(c in period for c in ";:[]\n\r"):
                raise ValueError("Report source period must be explicit finite text")
            previous = (
                _at(source, contract["previous_path"]) if "previous_path" in contract else None
            )
            if previous is not None and not _numeric(previous):
                raise ValueError("Report baseline must be numeric or explicitly null")
            trend = "unknown" if value is None else "unassessed"
            if value is not None and "previous_path" in contract:
                trend = (
                    "unknown"
                    if previous is None
                    else "up"
                    if value > previous
                    else "down"
                    if value < previous
                    else "flat"
                )
            expected = {
                "claim_id": claim_id,
                "value": value,
                "period": period,
                "trend": trend,
                "source_alias": contract["source_alias"],
                "source_path": contract["value_path"],
                "status": "unresolved" if value is None else "supported",
            }
            section = by_id.get(section_id, {})
            claims = section.get("claims")
            metadata = claims[0] if isinstance(claims, list) and len(claims) == 1 else None
            metadata_ok = (
                isinstance(metadata, dict)
                and set(metadata) == set(expected)
                and all(
                    (
                        metadata[key] is None
                        if val is None
                        else _numeric(metadata[key]) and metadata[key] == val
                        if _numeric(val)
                        else type(metadata[key]) is type(val) and metadata[key] == val
                    )
                    for key, val in expected.items()
                )
            )
            parsed = _parse_body(section.get("body"), contract["label"])
            body_ok = (
                parsed is not None
                and parsed["value"] == value
                and parsed["period"] == period
                and parsed["trend"] == trend
                and parsed["alias"] == contract["source_alias"]
                and parsed["path"] == contract["value_path"]
            )
            diagnostics.append(
                {
                    "claim_id": claim_id,
                    "section_id": section_id,
                    "location": [*spec["path"], "sections", section_id, "body"],
                    "passed": bool(metadata_ok and body_ok),
                    "metadata_correct": bool(metadata_ok),
                    "body_correct": bool(body_ok),
                    "expected": expected,
                    "actual_metadata": metadata,
                    "actual_body": section.get("body"),
                    "parsed_body": parsed,
                }
            )
    except (KeyError, TypeError, ValueError) as error:
        return {
            "passed": False,
            "diagnostics": diagnostics,
            "error": str(error),
            "unassessed": UNASSESSED,
        }
    return {
        "passed": all(row["passed"] for row in diagnostics),
        "diagnostics": diagnostics,
        "unassessed": UNASSESSED,
    }
