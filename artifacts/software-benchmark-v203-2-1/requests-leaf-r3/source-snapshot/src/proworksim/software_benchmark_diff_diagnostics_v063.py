"""Lossless raw capture for two non-semantic upstream git-diff diagnostics.

Build a private function copy; never edit the installed harness or its globals.
Only the two known diagnostic decoders change. Candidate application, test
execution, test-output decoding and resolved classification remain upstream code.
"""

from __future__ import annotations

import __future__
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import ModuleType

VERSION = "v063-git-diff-diagnostic-decode-r1"
UPSTREAM_SHA256 = "39b7e95f726df65c67f19f8d79a0f5f10f9d9e12e224076c8cb011851d060016"
HELPER_NAME = "_v063_capture_diagnostic_diff"
STAGES = {"git_diff_output_before": "before", "git_diff_output_after": "after"}
EXPECTED_DECODE = ast.parse(
    'container.exec_run("git -c core.fileMode=false diff", '
    'workdir=CONTAINER_WORKDIR).output.decode("utf-8")',
    mode="eval",
).body


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def diagnostic_decoder(directory: Path):
    """Retain the exact bytes, using escaping only when UTF-8 is invalid."""
    directory = Path(directory)

    def decode(raw: bytes, stage: str) -> str:
        if type(raw) is not bytes or stage not in STAGES.values():
            raise ValueError("Only the two byte-valued git-diff diagnostics are supported")
        metadata = {
            "version": VERSION,
            "stage": stage,
            "bytes": len(raw),
            "sha256": _digest(raw),
            "utf8_strict": True,
            "decode_errors": "strict",
            "scoring_input": False,
        }
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            text = raw.decode("utf-8", "backslashreplace")
            metadata.update(
                utf8_strict=False,
                decode_errors="backslashreplace",
                first_invalid_span=[error.start, error.end],
                first_invalid_reason=error.reason,
            )
        # Exclusive writes prevent overwriting diagnostic evidence on replay.
        with (directory / f"{stage}.diff.bin").open("xb") as stream:
            stream.write(raw)
        with (directory / f"{stage}.json").open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return text

    return decode


def repair_function_ast(source: bytes) -> tuple[ast.Module, dict]:
    """Verify the pinned source, then replace exactly two diagnostic decoders."""
    if _digest(source) != UPSTREAM_SHA256:
        raise ValueError("The upstream harness source differs from the reviewed version")
    parsed = ast.parse(source.decode("utf-8", "strict"))
    matches = [
        node for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_instance"
    ]
    if len(matches) != 1:
        raise ValueError("Expected one upstream run_instance function")
    original = matches[0]
    function = copy.deepcopy(original)
    changed = []
    expected = ast.dump(EXPECTED_DECODE, include_attributes=False)
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in STAGES:
            continue
        value = node.value
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "strip"
            and not value.args and not value.keywords
            and ast.dump(value.func.value, include_attributes=False) == expected
        ):
            raise ValueError("The reviewed diagnostic assignment shape changed")
        decode = value.func.value
        value.func.value = ast.copy_location(
            ast.Call(
                func=ast.Name(id=HELPER_NAME, ctx=ast.Load()),
                args=[decode.func.value, ast.Constant(value=STAGES[target.id])],
                keywords=[],
            ),
            decode,
        )
        changed.append(target.id)
    if sorted(changed) != sorted(STAGES):
        raise ValueError("Expected exactly the before/after git-diff diagnostic assignments")
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    return module, {
        "version": VERSION,
        "upstream_sha256": UPSTREAM_SHA256,
        "changed_assignments": changed,
        "original_function_ast_sha256": _digest(ast.dump(original).encode()),
        "repaired_function_ast_sha256": _digest(ast.dump(function).encode()),
        "candidate_bytes_changed": False,
        "test_or_scoring_logic_changed": False,
        "upstream_installation_changed": False,
        "raw_diagnostics_preserved": True,
    }


def make_repaired_run_instance(harness: ModuleType, directory: Path):
    """Return (private upstream function copy, provenance); no Docker operations."""
    source = Path(harness.__file__).resolve()
    module, provenance = repair_function_ast(source.read_bytes())
    namespace = dict(vars(harness))
    if HELPER_NAME in namespace:
        raise ValueError("Unexpected pre-existing diagnostic repair helper")
    directory = Path(directory).resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    namespace[HELPER_NAME] = diagnostic_decoder(directory)
    code = compile(
        module, str(source) + "::" + VERSION, "exec",
        flags=__future__.annotations.compiler_flag, dont_inherit=True,
    )
    exec(code, namespace)
    provenance.update(upstream_path=str(source), raw_diagnostic_directory=str(directory))
    return namespace["run_instance"], provenance
