"""Public parse diagnostics shared by both v0.17 worker interfaces.

Only observed syntax/type failures and the supplied public schema are described.
No argument value, business answer, corrected SQL, or inferred field is supplied.
"""

import copy
import json

VERSION = "public-format-diagnostics-v0.17"


def json_type(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def exception_diagnostic(error, *, stage, field_path=None, schema_path=None, expected_type=None):
    result = {
        "stage": stage,
        "reason": "Invalid JSON syntax" if isinstance(error, json.JSONDecodeError) else str(error),
        "field_path": copy.deepcopy(field_path),
        "schema_path": copy.deepcopy(schema_path),
        "expected_type": copy.deepcopy(expected_type),
        "observed_type": None,
        "position": None,
    }
    if isinstance(error, json.JSONDecodeError):
        result.update(
            reason=error.msg,
            position={
                "offset": error.pos,
                "line": error.lineno,
                "column": error.colno,
                "scope": "the parsed parameter text" if field_path else "assistant content",
            },
        )
    return result


def schema_diagnostic(error):
    """Accept a real jsonschema ValidationError, without copying its instance/value."""
    result = {
        "stage": "public_schema",
        "reason": "Arguments violate the declared public schema constraint: "
        + str(error.validator),
        "constraint": error.validator,
        "field_path": list(error.absolute_path),
        "schema_path": list(error.absolute_schema_path),
        "expected_type": copy.deepcopy(error.validator_value)
        if error.validator == "type"
        else copy.deepcopy(error.schema.get("type"))
        if isinstance(error.schema, dict)
        else None,
        "observed_type": json_type(error.instance),
        "position": None,
    }
    if error.validator == "required" and isinstance(error.instance, dict):
        result["missing_fields"] = [
            key for key in error.validator_value if key not in error.instance
        ]
    return result


def feedback_diagnostics(body, adapter_failure, *, adapter):
    """Preserve native failure separately from a subsequent adapter rejection."""
    native = body.get("protocol_parse_error") if isinstance(body, dict) else None
    if isinstance(native, dict) and native.get("version") == VERSION:
        native_result = copy.deepcopy(native)
    elif native:
        native_result = {
            "parser": "native_parser_legacy",
            "status": "rejected",
            "failure": {
                "reason": str(native),
                "field_path": None,
                "schema_path": None,
                "expected_type": None,
                "observed_type": None,
                "position": None,
            },
        }
    else:
        native_result = {
            "parser": "native_parser",
            "status": "no_failure_reported",
            "failure": None,
        }
    return {
        "version": VERSION,
        "native_parser": native_result,
        "adapter_parser": {
            "parser": adapter,
            "status": "rejected",
            "failure": copy.deepcopy(adapter_failure),
        },
        "scope": "Public syntax and supplied schema only; unknown locations stay null. No replacement values or business answers.",
    }
