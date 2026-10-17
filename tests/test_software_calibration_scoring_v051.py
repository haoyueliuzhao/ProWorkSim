import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_calibration_scoring_v051 as scoring


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "artifacts/software-calibration-v051/sources/lcb-code"
PYTHON = ROOT / "runs/v016-sdk/resident-venv/bin/python"


@pytest.fixture
def official_sources():
    if not SOURCES.is_dir() or not PYTHON.is_file():
        pytest.skip("Pinned local official source bundle and NumPy CPU interpreter required")
    scoring.verify_sources(SOURCES)
    return SOURCES


def sample(inputs, outputs, fn_name=None):
    return {"input_output": json.dumps({"inputs": inputs, "outputs": outputs,
                                       "fn_name": fn_name})}


def run(raw, evaluation, tmp_path, official_sources, timeout=1):
    return scoring.score_cal1_candidate(
        raw, evaluation, source_root=official_sources, run_root=tmp_path / "grade",
        python_executable=PYTHON, per_test_seconds=timeout)


def test_exact_official_extractor_uses_last_delimiters(official_sources):
    raw = "<think>\n```python\nwrong\n```\n</think>\n```python\nright\n```"
    assert scoring.extract_official_code(raw, source_root=official_sources) == "right"
    assert scoring.extract_official_code("print(1)", source_root=official_sources) == ""


@pytest.mark.parametrize("raw,evaluation,expected", [
    ("```python\nprint(sum(map(int, input().split())))\n```",
     sample(["2 3\n", "8 5\n"], ["5\n", "13\n"]), 1),
    ("```python\nclass Solution:\n def add(self,a,b): return a+b\n```",
     sample(["2\n3", "8\n5"], ["5", "13"], "add"), 1),
    ("```python\nprint(0)\n```", sample(["2 3\n"], ["5\n"]), 0),
    ("```python\nclass Solution:\n def add(self,a,b): return a-b\n```",
     sample(["2\n3"], ["5"], "add"), 0),
    ("```python\nif bad syntax:\n```", sample(["2 3\n"], ["5\n"]), 0),
    ("print(5)", sample(["2 3\n"], ["5\n"]), 0),
])
def test_native_positive_negative_controls(raw, evaluation, expected, tmp_path, official_sources):
    result = run(raw, evaluation, tmp_path, official_sources)
    assert result["pass_at_1"] == expected, result
    assert result["sandbox"]["network"] == "seccomp_denied"
    assert result["sandbox"]["subprocess"] == "seccomp_denied"
    assert result["grading_attempts"] == 1
    assert result["candidate_generations_added"] == 0
    assert result["evaluation_sample_sha256"] == scoring._sha(scoring._json_bytes(evaluation))


def test_native_tle_is_known_incorrect(tmp_path, official_sources):
    result = run("```python\nwhile True: pass\n```", sample([""], ["1"]),
                 tmp_path, official_sources)
    assert result["pass_at_1"] == 0, result
    assert result["official_reply"]["metadata"]["error_code"] == -3
    assert result["host_wall_timeout"] is False


def test_fatal_candidate_exit_is_preserved_unknown(tmp_path, official_sources):
    result = run("```python\nimport os\nos._exit(7)\n```", sample([""], ["1"]),
                 tmp_path, official_sources)
    assert result["status"] == "technical_unknown"
    assert result["pass_at_1"] is None
    assert result["returncode"] == 7
    assert result["official_reply"] is None
    assert result["sandbox"] is not None


def test_os_denies_host_file_network_and_process_creation(tmp_path, official_sources):
    secret = tmp_path / "outside-cwd.txt"
    secret.write_text("controller-only-canary")
    code = f"""class Solution:
 def probe(self, ignored):
  import os, io, socket, ctypes
  if set(os.environ) != {{'OMP_NUM_THREADS'}}: return -1
  try:
   io.open({str(secret)!r}).read()
   return -2
  except PermissionError: pass
  try:
   socket.socket()
   return -3
  except PermissionError: pass
  libc=ctypes.CDLL(None, use_errno=True)
  if libc.fork() != -1: return -4
  if ctypes.get_errno() != 1: return -5
  return 42
"""
    result = run("```python\n" + code + "```", sample(["null"], ["42"], "probe"),
                 tmp_path, official_sources)
    assert result["pass_at_1"] == 1, result
    assert secret.read_text() == "controller-only-canary"


def test_upstream_empty_metadata_fault_is_not_rewritten(official_sources):
    path = official_sources / "lcb_runner/evaluation/compute_code_generation_metrics.py"
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "check_correctness")
    fake_process = SimpleNamespace(start=lambda: None, join=lambda **kwargs: None,
                                   is_alive=lambda: False)
    namespace = {"multiprocessing": SimpleNamespace(
        Manager=lambda: SimpleNamespace(list=list), Process=lambda **kwargs: fake_process),
        "json": json, "_temp_run": None}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    # The unchanged official code manufactures result[-1] but indexes empty
    # metadata_list. Preserve this observed upstream IndexError, not a fake R0.
    with pytest.raises(IndexError):
        namespace["check_correctness"](sample([""], ["1"]), "x", 1, debug=False)
    assert scoring.classify_official_reply(None, expected_tests=1)["pass_at_1"] is None


@pytest.mark.parametrize("reply", [
    {"runner_exception": {"type": "IndexError", "message": "list index out of range"}},
    {"results": [-2], "metadata": {"error_code": -5}},
    {"results": [True], "metadata": {}},
    {"results": [], "metadata": {}},
])
def test_missing_or_incomplete_official_records_stay_unknown(reply):
    assert scoring.classify_official_reply(reply, expected_tests=2)["pass_at_1"] is None


def test_negative_native_error_codes_are_not_truthy_successes():
    result = scoring.classify_official_reply(
        {"results": [-3], "metadata": {"error_code": -3}}, expected_tests=1)
    assert result["status"] == "official_incorrect"
    assert result["pass_at_1"] == 0


def test_source_mismatch_rejected_before_execution(tmp_path):
    with pytest.raises(ValueError, match="Pinned official scorer source changed"):
        scoring.verify_sources(tmp_path)


def test_malformed_official_test_pair_rejected():
    with pytest.raises(ValueError, match="Malformed official evaluation sample"):
        scoring._sample_count(sample(["1"], []))


def test_grading_result_cannot_be_overwritten(tmp_path, official_sources):
    (tmp_path / "grade").mkdir()
    with pytest.raises(FileExistsError):
        run("```python\nprint(1)\n```", sample([""], ["1"]),
            tmp_path, official_sources)
