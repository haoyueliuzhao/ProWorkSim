"""The offline decoder repair changes logging only and preserves evidence."""

import ast
import copy
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from proworksim import software_benchmark_diff_diagnostics_v063 as repair

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / (
    "runs/software-benchmark-v054/scorer-venv/lib/python3.12/site-packages/"
    "swebench/harness/run_evaluation.py"
)


def test_decoder_keeps_raw_bytes_and_only_escapes_invalid_utf8(tmp_path):
    decode = repair.diagnostic_decoder(tmp_path)
    valid = "diff --git a/中文.py b/中文.py\n".encode()
    invalid = b"diff --git a/raw b/raw\n+\xe0\xff\n"
    assert decode(valid, "before") == valid.decode()
    assert decode(invalid, "after") == "diff --git a/raw b/raw\n+\\xe0\\xff\n"
    assert (tmp_path / "before.diff.bin").read_bytes() == valid
    assert (tmp_path / "after.diff.bin").read_bytes() == invalid
    before = json.loads((tmp_path / "before.json").read_bytes())
    after = json.loads((tmp_path / "after.json").read_bytes())
    assert before["utf8_strict"] is True and after["utf8_strict"] is False
    assert after["sha256"] == repair._digest(invalid)
    assert after["scoring_input"] is False
    with pytest.raises(FileExistsError):
        decode(b"different", "after")


def test_transformation_is_exactly_two_diagnostic_decoders():
    source = UPSTREAM.read_bytes()
    module, provenance = repair.repair_function_ast(source)
    restored = copy.deepcopy(module.body[0])
    count = 0
    for node in ast.walk(restored):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            value = node.func.value
            if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                    and value.func.id == repair.HELPER_NAME):
                node.func.value = copy.deepcopy(repair.EXPECTED_DECODE)
                count += 1
    original = next(n for n in ast.parse(source).body
                    if isinstance(n, ast.FunctionDef) and n.name == "run_instance")
    assert count == 2
    assert ast.dump(restored) == ast.dump(original)
    assert provenance["test_or_scoring_logic_changed"] is False
    with pytest.raises(ValueError, match="source differs"):
        repair.repair_function_ast(source + b"\n")


@pytest.mark.parametrize("invalid", [False, True])
def test_official_function_reaches_same_scoring_without_mutation(tmp_path, invalid):
    """Execute the real pinned function with fake I/O, including patch/test steps."""
    harness = ModuleType("isolated_harness_fixture")
    harness.__file__ = str(UPSTREAM)
    calls, uploads, errors = [], [], []
    raw = b"unchanged diff\xe0\xff\n" if invalid else b"unchanged diff\n"
    container = SimpleNamespace(id="fake-owned-container", start=lambda: calls.append("start"))

    def command(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(exit_code=0, output=raw if cmd.endswith(" diff") else b"ok")

    container.exec_run = command
    logger = SimpleNamespace(
        info=lambda *_: None, error=lambda message: errors.append(message), log_file="fake-log",
    )
    prediction = {"instance_id": "fixture", "model_name_or_path": "candidate",
                  "model_patch": "original patch bytes\n"}
    report = {"fixture": {"resolved": False, "patch_successfully_applied": True}}

    def score(**kwargs):
        calls.append("score")
        assert kwargs["prediction"] is prediction
        assert kwargs["test_log_path"].read_text() == "same official output"
        return report

    def upload(_container, file, destination):
        uploads.append((str(destination), file.read_bytes()))

    def evaluate(*args):
        calls.append("official-tests")
        return "same official output", False, 1.25

    harness.__dict__.update(
        Path=Path, PurePosixPath=Path, json=json, RUN_EVALUATION_LOG_DIR=tmp_path / "logs",
        LOG_REPORT="report.json", LOG_TEST_OUTPUT="test_output.txt", LOG_INSTANCE="run.log",
        setup_logger=lambda *_: logger, close_logger=lambda *_: None,
        create_container=lambda *_: container, copy_to_container=upload,
        GIT_APPLY_CMDS=["git apply --verbose"], CONTAINER_PATCH_FILE="/patch.diff",
        CONTAINER_WORKDIR="/testbed", CONTAINER_USER="root", APPLY_PATCH_PASS="apply pass",
        APPLY_PATCH_FAIL="apply fail", _stage_image_assets=lambda *_: [],
        _inject_asset_restore=lambda script, _: script, exec_run_with_timeout=evaluate,
        get_eval_report=score, cleanup_container=lambda *_: calls.append("cleanup"),
        EvaluationError=RuntimeError, traceback=__import__("traceback"), run_instance="unmodified",
    )
    original_globals = dict(vars(harness))
    function, provenance = repair.make_repaired_run_instance(harness, tmp_path / "raw")
    result = function(SimpleNamespace(instance_id="fixture", eval_script="official eval\n"),
                      prediction, object(), "new-run", timeout=1800)
    assert result == ("fixture", report)
    assert calls == ["start", "git apply --verbose /patch.diff",
                     "git -c core.fileMode=false diff", "official-tests",
                     "git -c core.fileMode=false diff", "score", "cleanup"]
    assert uploads == [("/patch.diff", b"original patch bytes\n"),
                       ("/eval.sh", b"official eval\n")]
    assert not errors and dict(vars(harness)) == original_globals
    assert (tmp_path / "raw/before.diff.bin").read_bytes() == raw
    assert (tmp_path / "raw/after.diff.bin").read_bytes() == raw
    assert provenance["upstream_installation_changed"] is False
