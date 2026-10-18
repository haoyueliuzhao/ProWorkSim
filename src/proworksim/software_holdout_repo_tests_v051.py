"""Independent Python 3.10 HOLD executor with original IDs and bounded imports.

The only pytest iniconfig dependency is a frozen-config capability: it contains
no parser and accepts no business input. Target modules load from the candidate
under the unchanged r3 filesystem/syscall confinement. No HOLD data on import.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import runpy
import signal
import subprocess
import sys
import time
import types
import unittest
import uuid

VERSION = "v051-holdout-native-tests-v1"
RESULT_PREFIX = "V051_HOLD_RESULT:"
UNTEST_PATTERN = r"^([a-zA-Z0-9_\-,\.\s\(\)']+)\s\.{3}\s"
TARGET_PACKAGES = ("funcy", "slugify", "iniconfig", "dominate")


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def source_ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": _sha(raw), "bytes": len(raw)}


def _helper():
    path = Path(__file__).resolve().with_name("software_calibration_shell_v051.py")
    spec = importlib.util.spec_from_file_location("hold_isolation_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, source_ref(path)


def restricted_config_module(root, entries):
    """Only return precomputed data for a byte-identical readonly config path."""
    root = Path(root).resolve()
    authorized = {str((root / name).resolve()): copy.deepcopy(value) for name, value in entries.items()}
    module = types.ModuleType("iniconfig")

    class ParseError(ValueError):
        pass

    class SectionWrapper(dict):
        pass

    class IniConfig:
        def __init__(self, path, *args, **kwargs):
            absolute = str(Path(path).resolve())
            item = authorized.get(absolute)
            if args or kwargs or item is None or _sha(Path(absolute).read_bytes()) != item["sha256"]:
                raise ParseError("Only the frozen readonly pytest configuration is accessible")
            self.sections = copy.deepcopy(item["sections"])

        def __contains__(self, name):
            return name in self.sections

        def __getitem__(self, name):
            return SectionWrapper(self.sections[name])

    module.IniConfig, module.SectionWrapper, module.ParseError = IniConfig, SectionWrapper, ParseError
    module.__hold_frozen_config_only__ = True
    return module


def _target_origins(spec, root, *, loaded):
    found = {}
    for name in spec["target_modules"]:
        if loaded:
            module = sys.modules.get(name)
            value = getattr(module, "__file__", None)
        else:
            module_spec = importlib.util.find_spec(name)
            value = getattr(module_spec, "origin", None)
        path = Path(value).resolve() if value else None
        relative = str(path.relative_to(root)) if path and path.is_relative_to(root) else None
        found[name] = {"path": str(path) if path else None, "relative_path": relative,
            "sha256": _sha(path.read_bytes()) if relative and path.is_file() else None,
            "candidate_bound": relative in spec["file_sha256"] if relative else False}
    return found


def _exception(error):
    chain, paths, missing, number = [], [], None, None
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        chain.append(type(error).__name__)
        missing = getattr(error, "name", None) or missing
        number = getattr(error, "errno", None) or number
        filename = getattr(error, "filename", None)
        if isinstance(filename, str):
            paths.append(filename)
        trace = error.__traceback__
        while trace:
            paths.append(trace.tb_frame.f_code.co_filename)
            trace = trace.tb_next
        error = error.__cause__ or error.__context__
    return {"exception_chain": chain, "trace_paths": sorted(set(paths)), "missing_module": missing, "errno": number}


def parse_native_output(text):
    rows = []
    for line in text.split("\n"):
        for status, outcome in (("ok", "passed"), ("FAIL", "failed"), ("ERROR", "error")):
            match = re.match(UNTEST_PATTERN + status + "$", line)
            if match:
                rows.append({"nodeid": match.group(1), "outcome": outcome})
                break
    return rows


def _native(spec, root):
    script = spec["engine_spec"]["script"]
    argv = spec["engine_spec"]["argv"]
    if argv != ["--verbose"] or script not in spec["file_sha256"]:
        raise ValueError("The native profile must execute its original script with --verbose")
    observations, errors = [], []
    original_start = unittest.TextTestResult.startTest
    original_methods = {name: getattr(unittest.TextTestResult, name)
                        for name in ("addSuccess", "addFailure", "addError", "addSkip", "addExpectedFailure", "addUnexpectedSuccess")}

    def start(result, test):
        observations.append({"native_id": test.id(), "description": result.getDescription(test)})
        return original_start(result, test)

    def report(name):
        def record(result, test, *args):
            for row in reversed(observations):
                if row["native_id"] == test.id() and "outcome" not in row:
                    row["outcome"] = {"addSuccess": "passed", "addFailure": "failed", "addError": "error"}.get(name, "unsupported")
                    if name in ("addFailure", "addError"):
                        details = _exception(args[0][1])
                        row.update(details)
                        errors.append({"nodeid": row["description"], **details})
                    break
            return original_methods[name](result, test, *args)
        return record

    unittest.TextTestResult.startTest = start
    for name in original_methods:
        setattr(unittest.TextTestResult, name, report(name))
    output = io.StringIO()
    sys.argv = [str(root / script), *argv]
    code = 0
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            runpy.run_path(str(root / script), run_name="__main__")
        except SystemExit as error:
            code = int(error.code or 0)
    text = output.getvalue()
    print(text, end="")
    parsed = parse_native_output(text)
    # Preserve profile group(1), not a stripped or TestCase.id()-substituted ID.
    descriptions = [{"nodeid": row["description"], "outcome": row.get("outcome")} for row in observations]
    bijection = (parsed == descriptions and len({row["nodeid"] for row in parsed}) == len(parsed)
                 and sorted(row["nodeid"] for row in parsed) == spec["nodeids"])
    return {"returncode": code, "tests": parsed, "collected": [row["nodeid"] for row in parsed],
        "native_id_mapping": observations, "original_id_bijection": bijection,
        "collection_errors": [], "exceptions": errors}


def _pytest(spec, root, pytest):
    rows, collected, collection, exceptions = {}, [], {}, {}

    class Recorder:
        def pytest_collection_modifyitems(self, items):
            collected.extend(item.nodeid for item in items)

        def pytest_collectreport(self, report):
            if report.failed:
                collection[report.nodeid] = {"nodeid": report.nodeid, "longreprtext": report.longreprtext}

        def pytest_exception_interact(self, node, call, report):
            if call.excinfo:
                exceptions[report.nodeid] = {"nodeid": report.nodeid, **_exception(call.excinfo.value)}

        def pytest_runtest_logreport(self, report):
            if report.when == "call" or report.failed or report.skipped:
                previous = rows.get(report.nodeid)
                if not previous or previous["outcome"] not in {"failed", "error"}:
                    rows[report.nodeid] = {"nodeid": report.nodeid,
                        "outcome": "error" if report.when != "call" and report.failed else report.outcome,
                        "longreprtext": report.longreprtext if report.longrepr else "", "phase": report.when}

    config = root / (spec.get("config_relative_path") or ".hold-empty-pytest.ini")
    args = ["-q", "-p", "no:cacheprovider", "-p", "pytest_cov", "--rootdir", str(root), "-c", str(config), *spec["nodeids"]]
    code = pytest.main(args, plugins=[Recorder()])
    return {"returncode": int(code), "tests": list(rows.values()), "collected": collected,
        "collection_errors": [{**row, **exceptions.get(node, {})} for node, row in collection.items()],
        "exceptions": list(exceptions.values()),
        "original_id_bijection": len(collected) == len(set(collected)) and set(collected) <= set(spec["nodeids"])}


def _worker(spec_path):
    spec = json.loads(Path(spec_path).read_bytes())
    helper, helper_ref = _helper()
    if helper_ref != spec["shell_helper_source"]:
        raise RuntimeError("The frozen sibling isolation helper changed")
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError("HOLD original profile requires Python 3.10")
    helper.record_current_process(spec, spec_path)
    root = Path(spec["worktree"]).resolve()
    os.chdir(root)
    os.environ.clear()
    os.environ.update(spec["env"])
    # The engine environment contains no correct target package. Do not expose
    # host site-packages, another project source tree or reference checkout.
    absent = {name: importlib.util.find_spec(name) is None for name in TARGET_PACKAGES}
    if not all(absent.values()):
        raise RuntimeError("Candidate-readable CPU environment contains a HOLD target package")
    pytest = None
    if spec["test_engine"] == "pytest":
        sys.modules["iniconfig"] = restricted_config_module(root, spec["engine_spec"]["frozen_ini_configs"])
        import pytest
        from _pytest.config import get_config
        bootstrap = get_config()
        bootstrap._ensure_unconfigure()
        if "iniconfig" in spec["target_modules"]:
            del sys.modules["iniconfig"]
    sys.path[:0] = [str(root), str(root / "src"), *spec["dependency_paths"]]
    proof = helper.install(spec)
    origins = _target_origins(spec, root, loaded=False)
    if not all(row["candidate_bound"] for row in origins.values()):
        raise RuntimeError("Target module resolution did not select the complete candidate tree")
    result = _pytest(spec, root, pytest) if pytest else _native(spec, root)
    imported = _target_origins(spec, root, loaded=True)
    result.update({"version": VERSION, "nonce": spec["nonce"], "isolation": proof,
        "shell_helper_source": helper_ref, "target_module_files": imported,
        "target_resolution": origins, "target_origin_bound": True,
        "target_imports_from_this_tree": all(row["candidate_bound"] for row in imported.values()),
        "cpu_python_version": sys.version, "engine_protocol_valid": True,
        "installed_target_packages_absent": absent,
        "config_adapter": "frozen_readonly_path_and_bytes_only_no_parser" if pytest else None})
    print("\n" + RESULT_PREFIX + json.dumps(result, ensure_ascii=False), flush=True)


def _safe_files(files):
    if (not isinstance(files, dict) or not files or len(files) > 5000
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in files.items())
            or sum(len(v.encode()) for v in files.values()) > 33554432):
        raise ValueError("Declare the bounded complete UTF-8 repository file map")
    for name in files:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or ".git" in path.parts or str(path) != name:
            raise ValueError("Only normalized repository-relative source paths")


def _attribution(terminal, files, task, tree):
    changed = {name for name, sha in task.get("initial_production_hashes", {}).items()
               if name not in files or _sha(files[name].encode()) != sha}
    rows = []
    for error in terminal.get("exceptions", []):
        relative = set()
        for name in error.get("trace_paths", []):
            path = Path(name)
            path = path if path.is_absolute() else tree / path
            if path.resolve().is_relative_to(tree):
                relative.add(str(path.resolve().relative_to(tree)))
        rows.append({**error, "changed_production_trace_paths": sorted(relative & changed),
            "environment_fault": not bool(relative & changed) and
            (error.get("errno") in (1, 13) or any(kind in error.get("exception_chain", []) for kind in ("ModuleNotFoundError", "ImportError")))})
    indexed = {row["nodeid"]: row for row in rows}
    collection = [{**row, **indexed.get(row["nodeid"], {})} for row in terminal.get("collection_errors", [])]
    bound = bool(collection) and all(row.get("changed_production_trace_paths") and not row.get("environment_fault") for row in collection)
    return {"collection_errors": collection, "exceptions": rows,
        "environment_errors": [row for row in rows if row["environment_fault"]],
        "source_attributable_collection_failure": bound, "changed_production_paths": sorted(changed)}


def validate_environment(environment):
    """Bind every allowed engine/dependency file before starting a candidate."""
    ref = environment["environment_template"]
    if source_ref(ref["path"]) != ref:
        raise ValueError("Frozen CPU environment manifest changed")
    template = json.loads(Path(ref["path"]).read_bytes())
    for label, directory in zip(("venv", "interpreter"), template["runtime_paths"]):
        actual = {str(path.relative_to(directory)): _sha(path.read_bytes())
            for path in sorted(Path(directory).rglob("*"))
            if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts}
        if actual != template["environment_files"][label]:
            raise ValueError("Frozen CPU environment bytes changed: " + label)
    paths = environment.get("dependency_paths", [])
    if len(paths) > 1:
        raise ValueError("Only one frozen additive dependency directory is admitted")
    actual = {str(path.relative_to(paths[0])): _sha(path.read_bytes())
        for path in sorted(Path(paths[0]).rglob("*")) if path.is_file() and "__pycache__" not in path.parts} if paths else {}
    if actual != environment.get("dependency_file_sha256", {}):
        raise ValueError("Frozen business dependency bytes changed")
    if environment["runtime_paths"] != template["runtime_paths"] or environment["python_executable"] != template["python_executable"]:
        raise ValueError("Frozen interpreter/runtime path identity changed")
    return True


def run_repository_tests(*, files, task, run_root):
    _safe_files(files)
    ids = task["nodeids"]
    if not ids or ids != sorted(set(ids)) or task["test_engine"] not in {"pytest", "native_unittest"}:
        raise ValueError("Freeze the complete original native test-ID union and engine")
    environment = task["engine_spec"]["environment"]
    validate_environment(environment)
    if environment["python_minor"] != "3.10":
        raise ValueError("HOLD CPU interpreter must match the original Python 3.10 profile")
    python = Path(task["cpu_python"]).absolute()
    if source_ref(python.resolve())["sha256"] != environment["python_executable"]["sha256"]:
        raise ValueError("Frozen CPU interpreter binary changed")
    helper, helper_ref = _helper()
    run_root = Path(run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=False)
    tree = Path("/tmp") / ("v051hold-" + uuid.uuid4().hex)
    tree.mkdir()
    for name, text in sorted(files.items()):
        path = tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
    empty = "[pytest]\n"
    (tree / ".hold-empty-pytest.ini").write_bytes(empty.encode())
    (tree / ".hold-tmp").mkdir()
    engine = copy.deepcopy(task["engine_spec"])
    engine.setdefault("frozen_ini_configs", {})[".hold-empty-pytest.ini"] = {"sha256": _sha(empty.encode()), "sections": {"pytest": {}}}
    for name, entry in engine["frozen_ini_configs"].items():
        if name != ".hold-empty-pytest.ini" and (name not in files or _sha(files[name].encode()) != entry["sha256"]
                or task.get("frozen_test_hashes", {}).get(name) != entry["sha256"]):
            raise ValueError("Config capability must bind the readonly original bytes")
    dependencies = environment.get("dependency_paths", [])
    for directory in dependencies:
        if any((Path(directory) / name).exists() or (Path(directory) / (name + ".py")).exists() for name in TARGET_PACKAGES):
            raise ValueError("Business dependency directory cannot contain HOLD target source")
    spec = {"version": VERSION, "worktree": str(tree), "nodeids": ids, "nonce": uuid.uuid4().hex,
        "test_engine": task["test_engine"], "engine_spec": engine, "target_modules": task["target_modules"],
        "file_sha256": {name: _sha(text.encode()) for name, text in files.items()},
        "shell_helper_source": helper_ref, "parent_pid": os.getpid(),
        "parent_start_ticks": helper.process_identity(os.getpid())["start_ticks"],
        "config_relative_path": task.get("config_relative_path"), "dependency_paths": dependencies,
        "readonly_paths": ["/usr/bin", "/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/lib64", "/etc/ld.so.cache",
                           *environment["runtime_paths"], *dependencies],
        "env": {"PATH": str(python.parent) + ":/usr/bin:/bin", "TMPDIR": str(tree / ".hold-tmp"),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "LC_ALL": "C.UTF-8",
            "COVERAGE_FILE": str(tree / ".hold-tmp/.coverage"), "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "TZ": "UTC"},
        "cpu_seconds": 55, "memory_bytes": 4294967296, "file_bytes": 8388608, "uid_thread_limit": helper.uid_threads() + 32}
    spec_path = run_root / "spec.json"
    spec_path.write_bytes(_json(spec))
    (run_root / "input.json").write_bytes(_json({"files": files, "task": task}))
    started, timed_out = time.monotonic(), False
    with (run_root / "stdout.txt").open("w") as output:
        proc = subprocess.Popen([str(python), "-I", str(Path(__file__).resolve()), str(spec_path)], cwd=tree,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)
            (run_root / "closed.json").write_bytes(_json({"version": VERSION, "pid": proc.pid, "wrapper_reaped": True,
                "returncode": proc.returncode, "group_cleanup_signal": "SIGKILL", "closed_at": time.time()}))
    raw = (run_root / "stdout.txt").read_text(errors="replace")
    terminals = []
    for line in raw.splitlines():
        if line.startswith(RESULT_PREFIX):
            try:
                item = json.loads(line[len(RESULT_PREFIX):])
            except ValueError:
                continue
            if item.get("nonce") == spec["nonce"]:
                terminals.append(item)
    terminal = terminals[0] if len(terminals) == 1 else {}
    changed = []
    for name, text in files.items():
        try:
            if (tree / name).is_symlink() or (tree / name).read_bytes() != text.encode():
                changed.append(name)
        except OSError:
            changed.append(name)
    binding = _attribution(terminal, files, task, tree)
    tests = terminal.get("tests", [])
    seen = [row["nodeid"] for row in tests]
    missing, unexpected = sorted(set(ids) - set(seen)), sorted(set(seen) - set(ids))
    integrity = not changed and all(_sha(files.get(name, "").encode()) == sha for name, sha in task.get("frozen_test_hashes", {}).items())
    code_failure = binding["source_attributable_collection_failure"] and terminal.get("returncode") in (2, 4)
    all_observed = not missing and not unexpected and len(seen) == len(set(seen))
    valid = bool(terminal and proc.returncode == 0 and not timed_out and integrity and not binding["environment_errors"]
        and terminal.get("shell_helper_source") == helper_ref and terminal.get("target_origin_bound")
        and terminal.get("original_id_bijection") and not unexpected
        and ((all_observed and terminal.get("target_imports_from_this_tree") and terminal["returncode"] in (0, 1)) or code_failure))
    result = {**terminal, **binding, "version": VERSION, "executed": valid,
        "passed": all_observed and all(row["outcome"] == "passed" for row in tests) if valid else None,
        "command_executed": bool(terminal), "all_expected_tests_observed": all_observed, "tests": tests,
        "worker_returncode": proc.returncode, "returncode": terminal.get("returncode"),
        "stdout": raw.split("\n" + RESULT_PREFIX, 1)[0], "evidence": str(run_root), "worktree": str(tree),
        "input_files_sha256": _sha(_json(files)), "source_unchanged": not changed, "test_integrity": integrity,
        "changed_input_paths": sorted(changed), "missing_test_ids": missing, "unexpected_test_ids": unexpected,
        "test_engine": task["test_engine"], "timeout": timed_out, "elapsed_seconds": time.monotonic() - started,
        "environment": environment, "runner_source": source_ref(__file__), "original_test_ids": ids}
    (run_root / "result.json").write_bytes(_json(result))
    return result


if __name__ == "__main__":
    _worker(sys.argv[1])
