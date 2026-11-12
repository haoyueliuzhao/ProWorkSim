"""Pinned, bounded SWE-smith task bundles and parent-process API evaluation.

This is a task/source adapter, not another agent runtime. Original SWE-smith
mutations are applied to upstream bytes. Added consumer requirements are ours;
the original single-agent task alone is not claimed to be collaborative.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import re

from .software_acceptance import _matches
from .software_sandbox import run_isolated
from .software_sources_v027 import MEMBER_CAPABILITIES, validate_derived_tasks

ASSETS = Path(__file__).resolve().parents[2] / "examples/software-sources-v028"
VERSION = "software-tasks-v0.28"
TASK_IDS = ("sqlparse-comparison-records", "schema-catalog", "textfsm-record-items")
NAMES = dict(zip(TASK_IDS, ("sqlparse", "schema", "textfsm"), strict=True))
MARKER = "PROWORKSIM_SOURCE_OBSERVATIONS:"


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _json(path):
    return json.loads(path.read_text())


def _entry(task_id):
    if task_id not in NAMES:
        raise ValueError("Unknown pinned software source task")
    manifest = _json(ASSETS / "source-manifest.json")
    row = next(item for item in manifest["rows"] if item["name"] == NAMES[task_id])
    return row, ASSETS / row["name"]


def original_files(task_id):
    """Verify the committed source bundle before preparing any model workspace."""
    row, directory = _entry(task_id)
    files = {}
    for name, expected in row["files_sha256"].items():
        raw = (directory / "upstream" / name).read_bytes()
        if _sha(raw) != expected:
            raise ValueError("Pinned upstream source changed: " + name)
        files[name] = raw.decode()
    return files


def apply_mutation(files, patch, *, reverse=False):
    """Apply exact unified hunks in memory; reject changed context and paths."""
    result = dict(files)
    sections = re.split(r"(?=^diff --git )", patch, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        lines = section.splitlines(keepends=True)
        before = next(line[6:].strip() for line in lines if line.startswith("--- a/"))
        after = next(line[6:].strip() for line in lines if line.startswith("+++ b/"))
        if before != after or before not in result:
            raise ValueError("Only existing unchanged safe source paths are supported")
        old_lines = result[before].splitlines(keepends=True)
        output, cursor = [], 0
        starts = [i for i, line in enumerate(lines) if line.startswith("@@ ")]
        for index, start in enumerate(starts):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", lines[start])
            if match is None:
                raise ValueError("Malformed patch hunk")
            position = int(match.group(2 if reverse else 1)) - 1
            if position < cursor:
                raise ValueError("Overlapping patch hunk")
            output.extend(old_lines[cursor:position])
            cursor = position
            end = starts[index + 1] if index + 1 < len(starts) else len(lines)
            for line in lines[start + 1:end]:
                if line.startswith("\\"):
                    raise ValueError("No-newline mutations are outside this frozen subset")
                prefix, content = line[:1], line[1:]
                if prefix not in {" ", "+", "-"}:
                    raise ValueError("Malformed unified patch line")
                if reverse and prefix in {"+", "-"}:
                    prefix = "+" if prefix == "-" else "-"
                if prefix in {" ", "-"}:
                    if cursor >= len(old_lines) or old_lines[cursor] != content:
                        raise ValueError("Mutation context does not match pinned source")
                    cursor += 1
                if prefix in {" ", "+"}:
                    output.append(content)
        output.extend(old_lines[cursor:])
        result[before] = "".join(output)
    return result


def _mutation(task_id):
    row, directory = _entry(task_id)
    raw = (directory / "original-task.json").read_bytes()
    if _sha(raw) != row["task_sha256"]:
        raise ValueError("Original task changed")
    patch = json.loads(raw)["patch"]
    if (directory / "defect.patch").read_text() != patch:
        raise ValueError("Defect patch and original task differ")
    return patch


def public_test_driver(task_id):
    """Use exact upstream test bodies; no rewritten assertions or pytest stub.

    The two pytest repositories use zero-argument, undecorated functions. The
    selected TextFSM unittest methods run with their complete original class.
    This narrow subset is not the upstream full pytest/Docker harness.
    """
    row, directory = _entry(task_id)
    source = (directory / "upstream" / row["upstream_test_file"]).read_text()
    selected = row["selected_FAIL_TO_PASS"] + row["selected_PASS_TO_PASS"]
    tree = ast.parse(source)
    if row["name"] == "textfsm":
        definitions = "\n\n".join(ast.get_source_segment(source, node) for node in tree.body
                                    if isinstance(node, ast.ClassDef) and node.name == "UnitTestFSM")
        header = "import io\nimport unittest\nimport textfsm\n"
        invocation = "parts = test_id.split('::'); instance = UnitTestFSM(parts[-1]); instance.debug()"
    else:
        definitions = []
        for test_id in selected:
            name = test_id.split("::")[-1]
            node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
            if node.decorator_list or node.args.args:
                raise ValueError("Only plain no-argument upstream test functions admitted")
            definitions.append(ast.get_source_segment(source, node))
        definitions = "\n\n".join(definitions)
        header = ("import sqlparse\nfrom sqlparse import sql, tokens as T\n" if row["name"] == "sqlparse"
                  else "from schema import Schema, Optional, Literal\n")
        invocation = "globals()[test_id.split('::')[-1]]()"
    return header + definitions + "\nimport json\nresults = []\nfor test_id in " + repr(selected) + ":\n    try:\n        " + invocation + "\n        results.append({'test_id': test_id, 'passed': True})\n    except Exception as error:\n        results.append({'test_id': test_id, 'passed': False, 'type': type(error).__name__, 'text': str(error)})\nprint('PROWORKSIM_UPSTREAM_TESTS:' + json.dumps(results, sort_keys=True))\n"


def build_case(task_id):
    """Return fresh fixed files and public contracts for a two-member adapter."""
    row, directory = _entry(task_id)
    task = _json(directory / "derived-task.json")
    partition = _json(ASSETS / "source-partition.json")
    validate_derived_tasks(partition, [task])
    contract = (directory / "contract.md").read_text()
    if _sha(contract.encode()) != task["requirements_sha256"]:
        raise ValueError("Derived public contract changed")
    files = apply_mutation(original_files(task_id), _mutation(task_id))
    # Original full test modules are retained in the provenance bundle; the
    # executable visible subset is a frozen driver, with original assertions.
    files.pop(row["upstream_test_file"])
    files["test_visible.py"] = public_test_driver(task_id)
    files["contract.md"] = contract
    files["consumer.py"] = (directory / "consumer-stub.py").read_text()
    files["test_member.py"] = "# Member-authored exploratory checks may be added here.\n"
    editable = [name for name in files if name.startswith(row["name"] + "/") and name.endswith(".py")]
    return {"version": VERSION, "task_id": task_id, "purpose": row["purpose"],
            "training_eligible": row["purpose"] == "policy_training", "files": files,
            "editable_paths": sorted([*editable, "consumer.py", "test_member.py"]),
            "task_definitions": task["task_definitions"],
            "members": {m: list(MEMBER_CAPABILITIES) for m in ("member_a", "member_b")},
            "initial_owners": dict.fromkeys(task["task_definitions"]),
            "source_partition_sha256": partition["sha256"],
            "actor_trajectories_created": False}


def reference_solution(task_id):
    """Controller-only CPU witness, never a current-policy training trajectory."""
    case = build_case(task_id)
    files = apply_mutation(case["files"], _mutation(task_id), reverse=True)
    _, directory = _entry(task_id)
    files["consumer.py"] = (directory / "consumer-reference.py").read_text()
    witness = original_files(task_id)
    row, _ = _entry(task_id)
    witness.pop(row["upstream_test_file"])
    witness["consumer.py"] = files["consumer.py"]
    actual = _sha(json.dumps(witness, sort_keys=True, ensure_ascii=False).encode())
    task = _json(directory / "derived-task.json")
    if actual != task["joint_solution_witness_sha256"]:
        raise ValueError("Frozen joint solution witness changed")
    return files


def run_public_tests(task_id, files, *, run_root):
    execution = run_isolated(files, public_test_driver(task_id), run_root=run_root)
    marker = "PROWORKSIM_UPSTREAM_TESTS:"
    encoded = [line[len(marker):] for line in execution["output"].splitlines() if line.startswith(marker)]
    rows = None
    if execution["driver_completed"] and execution["returncode"] == 0 and len(encoded) == 1:
        try:
            parsed = json.loads(encoded[0])
            row, _ = _entry(task_id)
            expected_ids = row["selected_FAIL_TO_PASS"] + row["selected_PASS_TO_PASS"]
            if (isinstance(parsed, list) and len(parsed) == len(expected_ids)
                    and all(isinstance(item, dict) and item.get("test_id") == test_id
                            and type(item.get("passed")) is bool
                            for item, test_id in zip(parsed, expected_ids, strict=True))):
                rows = parsed
        except (ValueError, TypeError):
            pass
    return {"execution": execution, "tests": rows,
            "passed": rows is not None and all(row["passed"] for row in rows),
            "authority": "visible_regression_feedback_only_not_independent_acceptance"}


# No expected result, score or private label crosses this worker boundary.
API_DRIVER = r'''
import json
_emit = json.dumps

def invoke(request):
    if request['repository'] == 'sqlparse':
        if request['op'] == 'source':
            import sqlparse
            from sqlparse.sql import Comparison
            records = []
            for expression in request['value']:
                node = sqlparse.parse(expression)[0].tokens[0]
                if not isinstance(node, Comparison):
                    raise ValueError('One comparison expression required')
                records.append({'left': str(node.left), 'right': str(node.right)})
            return records
        from consumer import comparison_records
        return comparison_records(request['value'])
    if request['repository'] == 'schema':
        if request['op'] == 'source':
            from schema import Schema
            spec = request['value']
            types = {'str': str, 'int': int, 'bool': bool}
            return Schema({spec['field']: types[spec['kind']]}, name=spec['name'],
                          description=spec['description']).json_schema('urn:' + spec['name'])
        from consumer import schema_catalog
        return schema_catalog(request['value'])
    if request['repository'] == 'textfsm':
        if request['op'] == 'source':
            import io
            import textfsm
            return textfsm.TextFSM(io.StringIO(request['template'])).ParseText(request['value'])
        from consumer import record_items
        return record_items(request['value'])
    raise ValueError('Unknown fixed API')

observations = []
for request in API_REQUESTS:
    try:
        observations.append({'kind': 'return', 'value': invoke(request)})
    except Exception as error:
        observations.append({'kind': 'exception', 'type': type(error).__module__ + '.' + type(error).__name__,
                             'text': str(error)})
print('PROWORKSIM_SOURCE_OBSERVATIONS:' + _emit(observations, sort_keys=True, allow_nan=False))
'''


def assess(task_id, files, *, run_root):
    """Independent frozen API judgment with expected values retained in parent.

    OS confinement prevents host/network/process access. It does not make the
    child's reported outputs cryptographically trustworthy: adversarial output
    fabrication against this finite API remains outside this bounded task claim.
    """
    case = build_case(task_id)
    if set(files) != set(case["files"]) or any(
        content != files[name] for name, content in case["files"].items()
        if name not in case["editable_paths"]
    ):
        raise ValueError("Only public editable paths may change")
    _, directory = _entry(task_id)
    fixture_raw = (directory / "acceptance.json").read_bytes()
    task = _json(directory / "derived-task.json")
    if _sha(fixture_raw) != task["independent_verifier_sha256"]:
        raise ValueError("Frozen independent fixture changed")
    cases = json.loads(fixture_raw)["cases"]
    requests = [copy.deepcopy(item["request"]) for item in cases]
    execution = run_isolated(files, "API_REQUESTS = " + repr(requests) + "\n" + API_DRIVER,
                             run_root=run_root)
    encoded = [line[len(MARKER):] for line in execution["output"].splitlines() if line.startswith(MARKER)]
    observations = None
    if execution["executed"] and execution["driver_completed"] and execution["returncode"] == 0 and len(encoded) == 1:
        try:
            value = json.loads(encoded[0])
            if isinstance(value, list) and len(value) == len(cases):
                observations = value
        except ValueError:
            pass
    checks = [{"case_id": item["case_id"], "group": item["group"],
               "passed": observations is not None and _matches(observations[index], item["expected"]),
               "expected": item["expected"],
               "observed": observations[index] if observations is not None else None}
              for index, item in enumerate(cases)]
    return {"version": VERSION, "task_id": task_id, "passed": all(item["passed"] for item in checks),
            "checks": checks, "execution": execution, "fixture_sha256": _sha(fixture_raw),
            "expected_values_sent_to_worker": False, "training_trajectory": False,
            "scope": "frozen_source_and_consumer_API_checks_not_official_full_Docker_suite"}
