"""Pinned LiveCodeBench scoring in the existing fail-closed OS sandbox.

The official extractor and ``run_test`` are used without source changes. The
official multiprocessing ``check_correctness`` envelope is replaced by one
outer process, because the sandbox denies child processes and sockets. Its
global timeout formula is retained. Missing grader replies stay unknown.

This confines filesystem/network/process access; the upstream in-process
grader is not claimed to resist adversarial Python frame introspection.
"""

import ast
from enum import Enum
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time


VERSION = "official-lcb-isolated-score-v051"
UPSTREAM_REVISION = "28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24"
SOURCE_HASHES = {
    "lcb_runner/lm_styles.py":
        "57d645b09852d2030d389cf9a14ea818396b7b0510b3e2f3f22e3d3e6792b783",
    "lcb_runner/utils/extraction_utils.py":
        "1267d1724c6d4ea6d237b907dd6b53dfc6f1787a04b1616b85c3bc8377446879",
    "lcb_runner/evaluation/testing_util.py":
        "b7cb6a8a69807bb868150a61742e25d7bb5328bbe01d514471b6ec43c9fa9ed2",
    "lcb_runner/evaluation/compute_code_generation_metrics.py":
        "073f388cc78bf0eb0ad35eaeb8bb509c0a3664963e5305d2be13d6b6eb6f3d21",
    "lcb_runner/evaluation/pass_k_utils.py":
        "6af3ee55d40f96fa06fa511bd5e43d94b19604750e82454b4b3c1f45c5199010",
}
PER_TEST_SECONDS = 6
MEMORY_BYTES = 4 * 1024**3
OUTPUT_BYTES = 1024**2
MAX_RAW_BYTES = 16 * 1024**2
MAX_SAMPLE_BYTES = 64 * 1024**2
MAX_TESTS = 1000


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def verify_sources(source_root):
    root = Path(source_root).resolve()
    for name, expected in SOURCE_HASHES.items():
        path = root / name
        if not path.is_file() or _sha(path.read_bytes()) != expected:
            raise ValueError("Pinned official scorer source changed: " + name)
    return {"revision": UPSTREAM_REVISION, "files": dict(SOURCE_HASHES)}


def _original_nodes(path, names, namespace):
    """Load exact upstream AST nodes while avoiding unrelated package imports."""
    tree = ast.parse(path.read_text())
    selected = [node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise ValueError("Missing original source definitions")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def extract_official_code(raw_output, *, source_root):
    if not isinstance(raw_output, str) or len(raw_output.encode()) > MAX_RAW_BYTES:
        raise ValueError("Raw generation exceeds the bounded scorer input")
    verify_sources(source_root)
    root = Path(source_root).resolve()
    namespace = _original_nodes(root / "lcb_runner/lm_styles.py", {"LMStyle"}, {"Enum": Enum})
    _original_nodes(root / "lcb_runner/utils/extraction_utils.py", {"extract_code"}, namespace)
    return namespace["extract_code"](raw_output, namespace["LMStyle"].OpenAIChat)


def _sample_count(sample):
    if not isinstance(sample, dict) or set(sample) != {"input_output"}:
        raise ValueError("Require the exact official evaluation_sample object")
    encoded = sample["input_output"]
    if not isinstance(encoded, str) or len(encoded.encode()) > MAX_SAMPLE_BYTES:
        raise ValueError("Evaluation sample exceeds its bound")
    values = json.loads(encoded)
    if (set(values) != {"inputs", "outputs", "fn_name"}
            or not isinstance(values["inputs"], list)
            or not isinstance(values["outputs"], list)
            or not 0 < len(values["inputs"]) == len(values["outputs"]) <= MAX_TESTS
            or not all(isinstance(v, str) for v in values["inputs"] + values["outputs"])
            or (values["fn_name"] is not None and not isinstance(values["fn_name"], str))):
        raise ValueError("Malformed official evaluation sample")
    return len(values["inputs"])


def classify_official_reply(reply, *, expected_tests):
    """Keep grader failures distinct from its native incorrect-program verdicts."""
    if not isinstance(reply, dict) or reply.get("runner_exception") is not None:
        return {"status": "technical_unknown", "pass_at_1": None,
                "reason": "official_runner_exception_or_missing_reply"}
    results, metadata = reply.get("results"), reply.get("metadata")
    if (not isinstance(results, list) or not results or len(results) > expected_tests
            or not all(type(x) in (bool, int, float) for x in results)
            or not isinstance(metadata, dict) or metadata.get("error_code") == -5):
        return {"status": "technical_unknown", "pass_at_1": None,
                "reason": "malformed_or_faulted_official_reply"}
    # This is the upstream pass_k_utils criterion; negative error codes are not
    # treated as truthy successes. A complete positive reply must cover all tests.
    passed = all(x > 0 for x in results)
    if passed and len(results) != expected_tests:
        return {"status": "technical_unknown", "pass_at_1": None,
                "reason": "incomplete_positive_official_reply"}
    return {"status": "passed" if passed else "official_incorrect",
            "pass_at_1": int(passed), "reason": "official_all_results_positive"}


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _worker(spec_path):
    spec = json.loads(Path(spec_path).read_text())
    source_root = Path(spec["source_root"])
    verify_sources(source_root)
    grader = _load_module(source_root / "lcb_runner/evaluation/testing_util.py",
                          "v051_official_testing_util")
    sandbox = _load_module(Path(__file__).with_name("software_sandbox.py"), "v051_os_sandbox")
    sandbox.LIMITS = spec["limits"]
    # All optional/native imports precede confinement; the existing policy fails
    # closed and denies network, process creation, host files and writable paths.
    import ctypes
    import socket
    import unittest
    del socket, unittest
    ctypes.CDLL("libseccomp.so.2")
    import numpy as np

    def native_json(value):
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        raise TypeError("Unsupported upstream response type: " + type(value).__name__)

    output = sys.stdout
    dump = json.dumps
    nonce = spec["nonce"]
    sample, code, timeout = spec["sample"], spec["code"], spec["per_test_seconds"]
    tree = spec["tree"]
    os.chdir(tree)
    os.environ.clear()
    sys.dont_write_bytecode = True
    isolation = sandbox._restrict(tree)
    output.write(dump({"isolation_installed": isolation, "nonce": nonce}) + "\n")
    output.flush()
    sys.argv[:] = ["official-livecodebench-scorer"]
    try:
        results, metadata = grader.run_test(sample, test=code, debug=False, timeout=timeout)
        reply = {"results": results, "metadata": metadata}
    except BaseException as error:
        reply = {"runner_exception": {"type": type(error).__name__, "message": str(error)}}
    output.write(dump({"official_reply": reply, "nonce": nonce}, default=native_json) + "\n")
    output.flush()


def score_cal1_candidate(raw_output, evaluation_sample, *, source_root, run_root,
                         python_executable, per_test_seconds=PER_TEST_SECONDS):
    """One candidate, one immutable sample, one isolated official grading pass.

    ``run_root`` must be new: no overwrite or silent grading retry. Production
    uses the frozen six-second per-test limit. Shorter explicit values are for
    finite CPU controls and are reported in every receipt.
    """
    if type(per_test_seconds) is not int or not 1 <= per_test_seconds <= PER_TEST_SECONDS:
        raise ValueError("The official per-test limit must be 1..6 seconds")
    source = verify_sources(source_root)
    count = _sample_count(evaluation_sample)
    code = extract_official_code(raw_output, source_root=source_root)
    root = Path(run_root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    tree = root / "empty-cwd"
    tree.mkdir()
    wall = (per_test_seconds + 1) * count + 5
    limits = {"wall_seconds": wall, "cpu_seconds": wall, "memory_bytes": MEMORY_BYTES,
              "output_bytes": OUTPUT_BYTES, "open_files": 64, "processes": 0}
    nonce = secrets.token_hex(32)
    spec = {"source_root": str(Path(source_root).resolve()), "sample": evaluation_sample,
            "code": code, "tree": str(tree), "nonce": nonce,
            "per_test_seconds": per_test_seconds, "limits": limits}
    (root / "raw-output.txt").write_text(raw_output)
    (root / "extracted-code.py").write_text(code)
    (root / "worker-spec.json").write_text(json.dumps(spec, ensure_ascii=False))
    started = time.monotonic()
    with (root / "worker-output.log").open("wb") as output:
        process = subprocess.Popen(
            [str(python_executable), "-I", str(Path(__file__).resolve()),
             "--worker", str(root / "worker-spec.json")],
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            cwd=tree, close_fds=True, start_new_session=False,
            env={"LANG": "C.UTF-8", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
                 "MKL_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        timed_out = False
        try:
            process.wait(timeout=wall)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait()
    with (root / "worker-output.log").open("rb") as output:
        raw = output.read(OUTPUT_BYTES + 1)
    events = []
    for line in raw[:OUTPUT_BYTES].decode("utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("nonce") == nonce:
            events.append(item)
    isolation = next((item["isolation_installed"] for item in events
                      if "isolation_installed" in item), None)
    replies = [item["official_reply"] for item in events if "official_reply" in item]
    reply = replies[0] if len(replies) == 1 else None
    if (not isolation or timed_out or process.returncode != 0
            or len(raw) > OUTPUT_BYTES or len(replies) != 1):
        verdict = {"status": "technical_unknown", "pass_at_1": None,
                   "reason": "isolated_grader_incomplete_or_faulted"}
    else:
        verdict = classify_official_reply(reply, expected_tests=count)
    result = {
        "version": VERSION, **verdict, "upstream": source,
        "raw_output_sha256": _sha(raw_output.encode()), "code_sha256": _sha(code.encode()),
        "evaluation_sample_sha256": _sha(_json_bytes(evaluation_sample)),
        "extraction_empty": not bool(code.strip()), "official_reply": reply,
        "official_test_count": count, "per_test_seconds": per_test_seconds,
        "sandbox": isolation, "limits": limits, "returncode": process.returncode,
        "host_wall_timeout": timed_out, "output_truncated": len(raw) > OUTPUT_BYTES,
        "elapsed_seconds": time.monotonic() - started,
        "execution_envelope": "One outer process replaces upstream Manager/child; exact run_test and timeout formula retained",
        "upstream_missing_reply_fault": "Original check_correctness indexes metadata_list[0] after empty result/global-timeout; such missing replies remain technical_unknown here",
        "candidate_generations_added": 0, "grading_attempts": 1,
    }
    (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                               allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--worker":
        raise SystemExit("Only the isolated worker entry is executable")
    _worker(sys.argv[2])
