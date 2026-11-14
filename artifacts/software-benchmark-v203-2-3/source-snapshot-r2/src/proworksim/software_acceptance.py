"""Independent software judgment lives in the trusted parent process.

The worker receives API requests only, never expected values, pass/fail code,
private group names or locators. It returns observations. Its unittest outcome
and its own claims of success have no authority over these parent comparisons.
"""
import json
from pathlib import Path

from .software_sandbox import run_isolated
from .storage import digest, json_bytes

VERSION = "software-parent-acceptance-v0.15"
MARKER = "PROWORKSIM_API_OBSERVATIONS:"
# Generic invocation/serialization adapter only: no expected result or checker.
API_DRIVER = r'''
import inspect
import json
from pathlib import Path
_emit_json = json.dumps
import marshmallow.fields as fields
from marshmallow import Schema, validate
from consumer import InventorySchema, load_inventory

def decode(value):
    if isinstance(value, dict) and set(value) == {"__bytes_hex__"}:
        return bytes.fromhex(value["__bytes_hex__"])
    return value

def invoke(request):
    operation = request["op"]
    if operation == "metadata":
        parameter = inspect.signature(fields.String).parameters.get("strip_whitespace")
        return {"module_path": str(Path(inspect.getfile(fields)).resolve().relative_to(Path.cwd())),
                "parameter": None if parameter is None else {"kind": parameter.kind.name, "default": parameter.default},
                "docstring": fields.String.__doc__}
    if operation in {"deserialize", "serialize"}:
        kwargs = dict(request.get("kwargs", {}))
        if "length" in request:
            kwargs["validate"] = validate.Length(**request["length"])
        field = getattr(fields, request.get("field", "String"))(**kwargs)
        if operation == "deserialize":
            return field.deserialize(decode(request["value"]))
        return field.serialize("v", {"v": decode(request["value"])})
    if operation == "consumer_load":
        return load_inventory(request["value"])
    if operation == "consumer_dump":
        return InventorySchema().dump(request["value"])
    if operation in {"schema_load", "nested_load"}:
        class Packet(Schema):
            code = fields.String(**request["field_kwargs"])
        if operation == "schema_load":
            return Packet().load(request["value"], partial=request.get("partial", False))
        class Envelope(Schema):
            packet = fields.Nested(Packet)
        return Envelope().load(request["value"])
    raise ValueError("Unsupported frozen API operation")

observations = []
for request in API_REQUESTS:
    try:
        observation = {"kind": "return", "value": invoke(request)}
    except Exception as error:
        observation = {"kind": "exception", "type": type(error).__module__ + "." + type(error).__name__,
                       "messages": getattr(error, "messages", None), "text": str(error)}
    observations.append(observation)
print("PROWORKSIM_API_OBSERVATIONS:" + _emit_json(observations, sort_keys=True, ensure_ascii=True, allow_nan=False))
'''


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _matches(observed, expected):
    try:
        return _matches_finite(observed, expected)
    except (ValueError, TypeError):
        return False


def _matches_finite(observed, expected):
    if not isinstance(observed, dict) or observed.get("kind") != expected["kind"]:
        return False
    if expected["kind"] == "return":
        return set(observed) == {"kind", "value"} and _canonical(observed["value"]) == _canonical(expected["value"])
    if expected["kind"] == "exception":
        return observed.get("type") == expected["type"] and (
            "messages" not in expected or _canonical(observed.get("messages")) == _canonical(expected["messages"]))
    raise ValueError("Unknown parent comparison")


def assess_api(files, *, fixture_path, run_root):
    fixture = json.loads(Path(fixture_path).read_text())
    cases = fixture["cases"]
    requests = [case["request"] for case in cases]
    # Only public API inputs cross the process boundary. Keeping expected values
    # outside this code string is essential, not a presentation convention.
    driver = "API_REQUESTS = " + repr(requests) + "\n" + API_DRIVER
    execution = run_isolated(files, driver, run_root=run_root)
    encoded = [line[len(MARKER):] for line in execution["output"].splitlines() if line.startswith(MARKER)]
    observations = None
    if execution["executed"] and execution["driver_completed"] and execution["returncode"] == 0 and len(encoded) == 1:
        try:
            parsed = json.loads(encoded[0])
            if isinstance(parsed, list) and len(parsed) == len(cases):
                observations = parsed
        except (TypeError, ValueError):
            pass
    checked = []
    for index, case in enumerate(cases):
        observed = observations[index] if observations is not None else None
        expected = case["expected"]
        if case.get("select"):
            observed = observed if isinstance(observed, dict) else {}
            selected = observed.get("value") if observed.get("kind") == "return" else None
            for key in case["select"]:
                selected = selected.get(key) if isinstance(selected, dict) else None
            observed = {"kind": "return", "value": selected} if observed.get("kind") == "return" else observed
        if case.get("comparison") == "contains":
            passed = isinstance(observed, dict) and observed.get("kind") == "return" and isinstance(observed.get("value"), str) and expected["value"] in observed["value"]
        else:
            passed = _matches(observed, expected)
        checked.append({"case_id": case["case_id"], "group": case["group"], "locator": case["locator"],
                        "symbol": case.get("symbol"), "request": case["request"], "observed": observed, "expected": expected, "passed": passed})
    groups = [{"group": name, "passed": all(row["passed"] for row in checked if row["group"] == name),
               "cases": sum(row["group"] == name for row in checked)} for name in fixture["groups"]]
    passed = observations is not None and all(row["passed"] for row in checked)
    return {"version": VERSION, "passed": passed, "executed": execution["executed"], "execution": execution,
            "case_count": len(checked), "passed_case_count": sum(row["passed"] for row in checked),
            "groups": groups, "checks": checked, "fixture_sha256": digest(Path(fixture_path).read_bytes()),
            "requests_sha256": digest(json_bytes(requests)), "driver_sha256": digest(driver.encode()),
            "expected_values_sent_to_worker": False,
            "boundary": "Untrusted child supplies API outputs; only parent compares. Visible unittest success has no correctness authority."}
