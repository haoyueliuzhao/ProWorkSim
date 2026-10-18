"""One shared fixed-node pytest runner with a finite real loopback FD fixture.

The original two boltons TCP tests retain all code/assertions. Only connection
establishment occurs in the host before confinement. Child creation of internet
sockets, connect/bind/listen, and external file access remain OS-denied.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import uuid
import weakref

VERSION = "v051-repository-pytest-loopback-fd"
LOOPBACK = "boltons_two_servers_v051"
TCP_COUNTS = {"test_socketutils_netstring": 4, "test_socketutils_netstring_timeout": 1}


def pytest_arguments(task, root):
    root = Path(root)
    relative = task.get("config_relative_path")
    if relative is None:
        config = root / ".calibration-empty-pytest.ini"
    else:
        if (not isinstance(relative, str) or Path(relative).is_absolute()
                or ".." in Path(relative).parts or not (root / relative).is_file()):
            raise ValueError("Original pytest configuration must be a declared repository file")
        config = root / relative
    return ["-q", "-p", "no:cacheprovider", "-p", "pytest_cov", "--rootdir", str(root),
            "-c", str(config), *task["nodeids"]]


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha_files(files):
    # Exactly proworksim.storage.json_bytes, imported only by the trusted host.
    from proworksim.storage import digest, json_bytes
    return digest(json_bytes(files))


def collection_failure_binding(terminal, *, files, task, tree, source_unchanged):
    """Attribute only a real changed production-code traceback under fixed tests."""
    frozen = task.get("frozen_test_hashes", {})
    production = task.get("initial_production_hashes", {})
    hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}
    tests_match = bool(frozen) and all(hashes.get(name) == expected for name, expected in frozen.items())
    changed = {name for name, expected in production.items() if hashes.get(name) != expected}
    initial_paths = task.get("initial_file_paths")
    accepted_new = task.get("accepted_new_production_paths", [])
    if accepted_new and not isinstance(initial_paths, list):
        raise ValueError("New production paths require the frozen initial full path inventory")
    new_paths = {name for name in accepted_new if name in files and name not in set(initial_paths or [])}
    if len(new_paths) != len(accepted_new):
        raise ValueError("Accepted new production files must actually exist and be absent initially")
    changed |= new_paths
    removed_modules = {name[:-3].replace("/", ".").removesuffix(".__init__")
                       for name in changed if name not in files and name.endswith(".py")}
    bound = []
    tree = Path(tree).resolve()
    for error in terminal.get("collection_errors", []) if terminal else []:
        paths = []
        for original in error.get("trace_paths", []):
            candidate = Path(original)
            candidate = candidate if candidate.is_absolute() else tree / candidate
            try:
                paths.append(str(candidate.resolve().relative_to(tree)))
            except ValueError:
                continue
        matched = sorted(set(paths) & changed)
        removed = ("ModuleNotFoundError" in error.get("exception_chain", [error.get("exception_type")])
                   and error.get("missing_module") in removed_modules)
        bound.append({**error, "candidate_relative_trace_paths": sorted(set(paths)),
            "changed_production_trace_paths": matched, "declared_production_module_deleted": removed,
            "attributed": bool(matched or removed)})
    # With explicit node selectors pytest 7 returns 4 (no collector) for the
    # same source import failure that returns 2 for a directory selection.
    # Neither code alone qualifies; every error must retain the source proof.
    passed = bool(terminal and terminal.get("returncode") in (2, 4) and source_unchanged
                  and tests_match and production and bound and all(row["attributed"] for row in bound))
    return {"source_attributable_collection_failure": passed,
        "frozen_test_files_match": tests_match if frozen else None,
        "changed_production_paths": sorted(changed), "collection_errors": bound,
        "accepted_new_production_paths": sorted(new_paths),
        "scope": "Only trusted pytest collection errors tied to changed/deleted declared production code with unchanged frozen tests/config; unmatched missing nodes remain unknown"}


def known_evaluation(terminal, *, worker_returncode, timed_out, source_unchanged,
                     missing, unexpected, source_attributable_collection_failure):
    if terminal is None or worker_returncode != 0 or timed_out or not source_unchanged or unexpected:
        return False
    code = terminal.get("returncode")
    return (not missing and code in (0, 1)) or (
        code in (2, 4) and source_attributable_collection_failure is True)


def _socket_fixture(spec, active):
    original_socket = socket.socket
    original_init = original_socket.__init__
    original_bind = original_socket.bind
    original_listen = original_socket.listen
    banks = {row["test"]: {**row, "clients": list(row["clients"]), "listener_used": False}
             for row in spec}
    events = []
    listeners = weakref.WeakKeyDictionary()

    def initialize(self, family=-1, type=-1, proto=-1, fileno=None):
        # Keep socket.socket itself as the real Python socket class, including
        # its inheritance protocol and the original fileno inference semantics.
        if fileno is not None:
            original_init(self, family, type, proto, fileno=fileno)
            return
        name = active[0].rsplit("::", 1)[-1] if active[0] else ""
        bank = banks.get(name)
        effective = (socket.AF_INET if family == -1 else family,
                     socket.SOCK_STREAM if type == -1 else type, 0 if proto == -1 else proto)
        if effective != (socket.AF_INET, socket.SOCK_STREAM, 0) or bank is None or bank["listener_used"]:
            # This real syscall is denied for AF_INET by seccomp, not the shim.
            original_init(self, family, type, proto)
            return
        bank["listener_used"] = True
        original_init(self, *effective, fileno=bank["listener"])
        listeners[self] = name
        events.append({"operation": "take_listener_fd", "test": active[0]})

    def bind(self, address):
        name = listeners.get(self)
        if name is None:
            return original_bind(self, address)
        if (name != active[0].rsplit("::", 1)[-1] or tuple(address) != ("127.0.0.1", 0)
                or self.getsockname()[0] != "127.0.0.1"):
            raise PermissionError("Only the fixed localhost ephemeral listener fixture is available")
        events.append({"operation": "bind_existing_localhost", "test": active[0]})

    def listen(self, backlog=0):
        name = listeners.get(self)
        if name is None:
            return original_listen(self, backlog)
        if name != active[0].rsplit("::", 1)[-1] or backlog != 100:
            raise PermissionError("The fixed original test declares backlog 100")
        events.append({"operation": "listen_existing_backlog100", "test": active[0]})

    def connect(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, *, all_errors=False):
        name = active[0].rsplit("::", 1)[-1] if active[0] else ""
        bank = banks.get(name)
        if (bank is None or tuple(address) != tuple(bank["address"]) or not bank["clients"]
                or timeout is not socket._GLOBAL_DEFAULT_TIMEOUT or source_address is not None or all_errors):
            raise PermissionError("Only the original test's finite preconnected localhost client pool is available")
        fd = bank["clients"].pop(0)
        events.append({"operation": "take_preconnected_client_fd", "test": active[0]})
        return original_socket(socket.AF_INET, socket.SOCK_STREAM, 0, fileno=fd)

    original_socket.__init__ = initialize
    original_socket.bind = bind
    original_socket.listen = listen
    socket.create_connection = connect
    events.append({"operation": "preserve_original_socket_class",
        "same_class_identity": socket.socket is original_socket,
        "socket_is_type": isinstance(socket.socket, type),
        "class_module": original_socket.__module__, "class_name": original_socket.__qualname__})
    return events


def _worker(spec_path):
    spec = json.loads(Path(spec_path).read_text())
    # The standalone CPU interpreter needs only this same frozen stdlib helper,
    # not proworksim.__init__ and unrelated application dependencies.
    helper_path = Path(__file__).resolve().with_name("software_calibration_shell_v051.py")
    helper_bytes = helper_path.read_bytes()
    helper_source = {"path": str(helper_path), "sha256": hashlib.sha256(helper_bytes).hexdigest(),
                     "bytes": len(helper_bytes)}
    if helper_source != spec["shell_helper_source"]:
        raise RuntimeError("Standalone isolation helper differs from the frozen sibling source")
    module_spec = importlib.util.spec_from_file_location("v051_repository_isolation_helper", helper_path)
    helper = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(helper)
    import pytest

    helper.record_current_process(spec, spec_path)
    root = Path(spec["worktree"])
    os.chdir(root)
    os.environ.clear()
    os.environ.update(spec["env"])
    sys.path[:0] = [str(root), str(root / "src")]
    active, rows, collected, collection_errors, exceptions = [""], {}, [], {}, {}
    events = _socket_fixture(spec["loopback_fds"], active) if spec["loopback_fds"] else []

    class Recorder:
        def pytest_collection_modifyitems(self, items):
            collected.extend(item.nodeid for item in items)

        def pytest_runtest_setup(self, item):
            active[0] = item.nodeid

        def pytest_collectreport(self, report):
            if report.failed:
                collection_errors[report.nodeid] = {"nodeid": report.nodeid,
                                                    "longreprtext": report.longreprtext}

        def pytest_exception_interact(self, node, call, report):
            if report.__class__.__name__ != "CollectReport" or call.excinfo is None:
                return
            error = call.excinfo.value
            paths = [str(entry.path) for entry in call.excinfo.traceback]
            chain = [type(error).__name__]
            missing_module = getattr(error, "name", None)
            filename = getattr(error, "filename", None)
            if isinstance(filename, str):
                paths.append(filename)
            # Pytest wraps SyntaxError in CollectError. Its ExceptionInfo cause
            # retains the actual source filename without matching message text.
            cause = getattr(error, "__cause__", None)
            seen = set()
            while cause is not None and id(cause) not in seen:
                seen.add(id(cause))
                chain.append(type(cause).__name__)
                missing_module = getattr(cause, "name", None) or missing_module
                filename = getattr(cause, "filename", None)
                if isinstance(filename, str):
                    paths.append(filename)
                traceback = cause.__traceback__
                while traceback is not None:
                    paths.append(traceback.tb_frame.f_code.co_filename)
                    traceback = traceback.tb_next
                cause = getattr(cause, "__cause__", None)
            exceptions[report.nodeid] = {"exception_type": type(error).__name__,
                "exception_chain": chain, "missing_module": missing_module, "trace_paths": sorted(set(paths))}

        def pytest_runtest_logreport(self, report):
            if report.when == "call" or report.failed or report.skipped:
                previous = rows.get(report.nodeid)
                if previous and previous["outcome"] in {"failed", "error"}:
                    return
                rows[report.nodeid] = {"nodeid": report.nodeid,
                    "outcome": "error" if report.when != "call" and report.failed else report.outcome,
                    "longreprtext": report.longreprtext if report.longrepr else "",
                    "phase": report.when}

    proof = helper.install(spec)
    args = pytest_arguments(spec, root)
    code = pytest.main(args, plugins=[Recorder()])
    result = {"version": VERSION, "nonce": spec["nonce"], "returncode": int(code),
        "tests": list(rows.values()), "collected": collected, "isolation": proof,
        "shell_helper_source": helper_source,
        "collection_errors": [{**row, **exceptions.get(node, {})} for node, row in collection_errors.items()],
        "loopback_fixture": {"policy": LOOPBACK if spec["loopback_fds"] else None,
            "connections_preestablished_by_host": bool(spec["loopback_fds"]),
            "original_test_files_modified": False, "real_kernel_TCP_send_recv_accept": True,
            "events": events}}
    print("\nV051_PYTEST_RESULT:" + json.dumps(result, ensure_ascii=False), flush=True)


def run_repository_tests(*, files, task, run_root):
    from proworksim.software_calibration_shell_v051 import uid_threads, process_identity
    if (not isinstance(files, dict) or not files or any(not isinstance(v, str) for v in files.values())
            or len(files) > 5000 or sum(len(v.encode()) for v in files.values()) > 33554432):
        raise ValueError("Declare the finite complete text repository tree")
    ids = task["nodeids"]
    if not ids or ids != sorted(set(ids)):
        raise ValueError("Freeze the exact sorted original test-node union")
    run_root = Path(run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=False)
    parent = Path("/tmp/v051c")
    parent.mkdir(exist_ok=True)
    tree = parent / str(time.time_ns())
    tree.mkdir()
    for name, text in files.items():
        path = tree / name
        if Path(name).is_absolute() or ".." in Path(name).parts or ".git" in Path(name).parts:
            raise ValueError("Only declared repository-relative source paths")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    (tree / ".calibration-empty-pytest.ini").write_text("[pytest]\n")
    (tree / ".calibration-tmp").mkdir()
    python = Path(task["cpu_python"]).absolute()
    prefix = python.parent.parent.resolve()
    host_sockets, fd_rows = [], []
    if task.get("loopback_fixture") == LOOPBACK:
        for test, count in TCP_COUNTS.items():
            if not any(node.rsplit("::", 1)[-1] == test for node in ids):
                continue
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(100)
            address = listener.getsockname()
            clients = [socket.create_connection(address) for _ in range(count)]
            host_sockets.extend([listener, *clients])
            fd_rows.append({"test": test, "listener": listener.fileno(), "address": list(address),
                            "clients": [client.fileno() for client in clients]})
    elif task.get("loopback_fixture") is not None:
        raise ValueError("Unknown network fixture is not an allowed fallback")
    helper_path = Path(__file__).resolve().with_name("software_calibration_shell_v051.py")
    helper_bytes = helper_path.read_bytes()
    spec = {"version": VERSION, "worktree": str(tree), "nodeids": ids, "nonce": uuid.uuid4().hex,
        "shell_helper_source": {"path": str(helper_path), "sha256": hashlib.sha256(helper_bytes).hexdigest(),
                                "bytes": len(helper_bytes)},
        "parent_pid": os.getpid(), "parent_start_ticks": process_identity(os.getpid())["start_ticks"],
        "config_relative_path": task.get("config_relative_path"),
        "readonly_paths": ["/usr/bin", "/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/lib64",
                           "/usr/lib/python3.12", "/etc/ld.so.cache", str(prefix)],
        "env": {"PATH": str(prefix / "bin") + ":/usr/bin:/bin", "TMPDIR": str(tree / ".calibration-tmp"),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "LC_ALL": "C.UTF-8",
            "COVERAGE_FILE": str(tree / ".calibration-tmp" / ".coverage"),
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "TZ": "UTC"},
        "cpu_seconds": 55, "memory_bytes": 4294967296, "file_bytes": 8388608,
        "uid_thread_limit": uid_threads() + 32, "loopback_fds": fd_rows}
    spec_path = run_root / "spec.json"
    spec_path.write_text(json.dumps(spec, indent=2))
    started = time.monotonic()
    raw_path = run_root / "stdout.txt"
    timed_out = False
    try:
        with raw_path.open("w") as handle:
            proc = subprocess.Popen([str(python), "-I", str(Path(__file__).resolve()), str(spec_path)],
                cwd=tree, env={"PATH": "/usr/bin:/bin", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
                stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True,
                pass_fds=tuple(sock.fileno() for sock in host_sockets))
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
                (run_root / "closed.json").write_text(json.dumps({"version": VERSION, "pid": proc.pid,
                    "wrapper_reaped": True, "returncode": proc.returncode, "group_cleanup_signal": "SIGKILL",
                    "closed_at": time.time()}, indent=2))
    finally:
        for sock in host_sockets:
            sock.close()
    raw = raw_path.read_text(errors="replace")
    terminal = None
    for line in raw.splitlines():
        if line.startswith("V051_PYTEST_RESULT:"):
            try:
                value = json.loads(line.split(":", 1)[1])
            except ValueError:
                continue
            if value.get("nonce") == spec["nonce"]:
                terminal = value
    changed = []
    for name, text in files.items():
        try:
            if (tree / name).is_symlink() or (tree / name).read_bytes() != text.encode("utf-8"):
                changed.append(name)
        except OSError:
            changed.append(name)
    tests = terminal.get("tests", []) if terminal else []
    seen = {row["nodeid"] for row in tests}
    missing, unexpected = sorted(set(ids) - seen), sorted(seen - set(ids))
    binding = collection_failure_binding(terminal, files=files, task=task, tree=tree, source_unchanged=not changed)
    command_executed = terminal is not None and not timed_out
    all_observed = not missing and not unexpected
    valid = known_evaluation(terminal, worker_returncode=proc.returncode, timed_out=timed_out,
        source_unchanged=not changed, missing=missing, unexpected=unexpected,
        source_attributable_collection_failure=binding["source_attributable_collection_failure"])
    valid = valid and terminal.get("shell_helper_source") == spec["shell_helper_source"]
    result = {"version": VERSION, "executed": valid,
        "passed": all_observed and terminal["returncode"] == 0 and all(row["outcome"] == "passed" for row in tests) if valid else None,
        "returncode": terminal.get("returncode", proc.returncode) if terminal else proc.returncode,
        "worker_returncode": proc.returncode, "tests": tests,
        "command_executed": command_executed, "all_expected_tests_observed": all_observed,
        **binding,
        "stdout": raw.split("\nV051_PYTEST_RESULT:", 1)[0], "evidence": str(run_root),
        "worktree": str(tree), "input_files_sha256": _sha_files(files),
        "source_unchanged": not changed, "changed_input_paths": sorted(changed),
        "test_integrity": not changed, "missing_test_ids": missing, "unexpected_test_ids": unexpected,
        "isolation": terminal.get("isolation") if terminal else None,
        "shell_helper_source": terminal.get("shell_helper_source") if terminal else None,
        "loopback_fixture": terminal.get("loopback_fixture") if terminal else None,
        "timed_out": timed_out, "seconds": time.monotonic() - started,
        "original_nodeids_sha256": hashlib.sha256(_json(ids)).hexdigest(),
        "scope": "Fixed original pytest nodes; real loopback connections are pre-established, not a full original container network reproduction"}
    (run_root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    _worker(sys.argv[1])
