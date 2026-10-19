"""Finite CPU controls for the server's selected filesystem/seccomp backend."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import signal
import socket
import subprocess
import sys
import tempfile


CHILD = r'''
import errno
import ctypes
import json
import os
from pathlib import Path
import socket
import sys

config = json.loads(sys.argv[1])
root = Path.cwd()
readonly = Path(config["readonly"])
outside = Path(config["outside"])
checks = []

def record(name, passed, **details):
    checks.append({"name": name, "passed": bool(passed), **details})

def denied(name, operation, expected_errno):
    try:
        operation()
    except OSError as error:
        record(name, error.errno in expected_errno,
               errno=error.errno, expected_errno=expected_errno)
    else:
        record(name, False, errno=None, expected_errno=expected_errno)

working = root / "allowed.txt"
working.write_text("abcdef", encoding="utf-8")
record("worktree_write_read", working.read_text(encoding="utf-8") == "abcdef")
os.truncate(working, 3)
record("worktree_truncate", working.read_text(encoding="utf-8") == "abc")
source, destination = root / "source", root / "destination"
source.mkdir()
destination.mkdir()
(source / "item.txt").write_text("rename-canary", encoding="utf-8")
(source / "item.txt").rename(destination / "item.txt")
record("worktree_cross_directory_rename",
       not (source / "item.txt").exists()
       and (destination / "item.txt").read_text(encoding="utf-8") == "rename-canary")
record("readonly_file_read", readonly.read_text(encoding="utf-8") == "readonly-canary")
readonly_errors = (errno.EACCES, errno.EROFS)
hidden_errors = (errno.EACCES, errno.ENOENT)
denied("readonly_file_write", lambda: readonly.write_text("unexpected", encoding="utf-8"), readonly_errors)
denied("readonly_file_truncate", lambda: os.truncate(readonly, 0), readonly_errors)
denied("outside_file_read", lambda: outside.read_text(encoding="utf-8"), hidden_errors)
denied("outside_file_write", lambda: outside.write_text("unexpected", encoding="utf-8"), hidden_errors)
denied("outside_file_truncate", lambda: os.truncate(outside, 0), hidden_errors)
denied("outside_file_create",
       lambda: (outside.parent / "unexpected.txt").write_text("unexpected", encoding="utf-8"),
       hidden_errors)
link = root / "outside-link"
link.symlink_to(outside)
denied("outside_symlink_read", lambda: link.read_text(encoding="utf-8"), hidden_errors)
denied("outside_symlink_truncate", lambda: os.truncate(link, 0), hidden_errors)
denied("outside_parent_traversal_read",
       lambda: (root / ".." / "outside" / "canary.txt").read_text(encoding="utf-8"), hidden_errors)
denied("host_proc_content_unavailable", lambda: Path("/proc/self/status").read_bytes(), hidden_errors)
proc_escape = Path("/proc/self/root") / str(outside).lstrip("/")
denied("proc_root_escape", lambda: proc_escape.read_bytes(), hidden_errors)

def internet_socket(family):
    with socket.socket(family, socket.SOCK_STREAM):
        pass

denied("ipv4_socket_creation", lambda: internet_socket(socket.AF_INET), (errno.EPERM,))
denied("ipv6_socket_creation", lambda: internet_socket(socket.AF_INET6), (errno.EPERM,))
libc = ctypes.CDLL(None, use_errno=True)
for name, call in (("user_namespace_escape", lambda: libc.unshare(0x10000000)),
                   ("chroot_escape", lambda: libc.chroot(b"/"))):
    ctypes.set_errno(0)
    returned = call()
    record(name, returned == -1 and ctypes.get_errno() == errno.EPERM,
           returncode=returned, errno=ctypes.get_errno(), expected_errno=errno.EPERM)
print(json.dumps({"checks": checks, "passed": all(row["passed"] for row in checks)}))
'''


FIXTURE_CHILD = r'''
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys

path = Path(sys.argv[1])
spec = json.loads(path.read_text())
module_spec = importlib.util.spec_from_file_location("fixture_shell", spec["helper_path"])
helper = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(helper)
helper.record_current_process(spec, path)
ctypes.CDLL("libseccomp.so.2")
os.chdir(spec["worktree"])
os.environ.clear()
os.environ.update(spec["env"])
row = spec["loopback_fds"][0]
listener = socket.socket(fileno=row["listener"])
client = socket.socket(fileno=row["clients"][0])
pair_row = spec["loopback_fds"][1]
inherited_left = socket.socket(fileno=pair_row["listener"])
inherited_right = socket.socket(fileno=pair_row["clients"][0])
proof = helper.install(spec)
checks = []

def exchange(name, left, right):
    left.settimeout(2)
    right.settimeout(2)
    left.sendall(b"fixture-canary")
    checks.append({"name": name, "passed": right.recv(64) == b"fixture-canary"})

with listener, client:
    listener.settimeout(2)
    accepted, _ = listener.accept()
    with accepted:
        exchange("preconnected_tcp_accept_send_receive", client, accepted)
with inherited_left, inherited_right:
    exchange("inherited_unix_socketpair", inherited_left, inherited_right)
# Anonymous local socketpairs are explicitly permitted by the original filter.
left, right = socket.socketpair()
with left, right:
    exchange("confined_unix_socketpair", left, right)
print(json.dumps({"isolation": proof, "checks": checks,
                  "passed": all(row["passed"] for row in checks)}))
'''


def load_helper():
    helper_path = Path(__file__).resolve().parents[2] / "src/proworksim/software_calibration_shell_v051.py"
    spec = importlib.util.spec_from_file_location("migration_v051_shell", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper, helper_path


def run_fixture_control(root, helper, helper_path):
    worktree = root / "fixture-worktree"
    worktree.mkdir()
    child = root / "fixture-child.py"
    child.write_text(FIXTURE_CHILD, encoding="utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener, ExitStack() as fixtures:
        pair = [fixtures.enter_context(stream) for stream in socket.socketpair()]
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname(), timeout=2) as client:
            spec = {
                "helper_path": str(helper_path), "worktree": str(worktree),
                "parent_pid": os.getpid(),
                "parent_start_ticks": helper.process_identity(os.getpid())["start_ticks"],
                "filesystem_policy": helper.filesystem_policy(),
                "readonly_paths": ["/usr/bin", "/usr/lib/x86_64-linux-gnu", "/usr/lib64",
                                   "/lib64", "/usr/lib/python3.12", "/etc/ld.so.cache"],
                "env": {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                "cpu_seconds": 10, "memory_bytes": 536870912, "file_bytes": 8388608,
                "uid_thread_limit": helper.uid_threads() + 16,
                "loopback_fds": [{"test": "synthetic_migration_tcp_fixture",
                    "listener": listener.fileno(), "clients": [client.fileno()],
                    "address": list(listener.getsockname())},
                    {"test": "synthetic_migration_socketpair_fixture", "listener": pair[0].fileno(),
                     "clients": [pair[1].fileno()]}],
            }
            spec_path = root / "fixture-spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            process = subprocess.Popen(
                [sys.executable, "-I", "-S", str(child), str(spec_path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                pass_fds=(listener.fileno(), client.fileno(), pair[0].fileno(), pair[1].fileno()),
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=15)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
    result = {"returncode": process.returncode, "stdout": stdout.decode(), "stderr": stderr.decode(),
              "spec": spec, "process": json.loads((root / "process.json").read_text()),
              "passed": False, "checks": []}
    if process.returncode == 0:
        result.update(json.loads(result["stdout"]))
    return result


def run_control(result):
    helper, helper_path = load_helper()
    source = helper_path.read_bytes()
    result["shell_helper"] = {
        "path": str(helper_path), "sha256": hashlib.sha256(source).hexdigest(), "bytes": len(source)
    }
    with tempfile.TemporaryDirectory(prefix="proworksim-server-sandbox-") as folder:
        root = Path(folder)
        worktree, runtime, outside, evidence = [root / name for name in (
            "worktree", "readonly-runtime", "outside", "evidence")]
        for path in (worktree, runtime, outside):
            path.mkdir()
        readonly_file, outside_file = runtime / "canary.txt", outside / "canary.txt"
        readonly_file.write_text("readonly-canary", encoding="utf-8")
        outside_file.write_text("outside-canary", encoding="utf-8")
        child = worktree / "probe.py"
        child.write_text(CHILD, encoding="utf-8")
        config = json.dumps({"readonly": str(readonly_file), "outside": str(outside_file)})
        command = shlex.join([sys.executable, "-I", "-S", str(child), config])
        # This scratch prefix grants a disposable external read-only canary.
        # The actual interpreter and libraries use the shell's unchanged
        # /usr/bin, /usr/lib/python3.12 and shared-library runtime grants.
        result["readonly_prefix_kind"] = "disposable_fixture_not_modified_runtime"
        execution = helper.run_bounded_shell(
            command, worktree=worktree, python_executable=sys.executable,
            python_prefix=runtime, evidence_root=evidence, timeout_seconds=15,
        )
        result["execution"] = execution
        result["backend"] = execution["extra"]["isolation"]
        call = Path(execution["extra"]["evidence_path"])
        result["shell_evidence"] = {
            name: json.loads((call / name).read_text(encoding="utf-8"))
            for name in ("spec.json", "process.json", "closed.json")
        }
        result["raw_shell_output"] = (call / "output.txt").read_text(encoding="utf-8")
        child_result = json.loads(execution["output"])
        checks = child_result["checks"]
        checks.extend([
            {"name": "readonly_canary_unchanged", "passed": readonly_file.read_text(encoding="utf-8") == "readonly-canary"},
            {"name": "outside_canary_unchanged", "passed": outside_file.read_text(encoding="utf-8") == "outside-canary"},
            {"name": "outside_file_not_created", "passed": not (outside / "unexpected.txt").exists()},
            {"name": "shell_completed", "passed": execution["returncode"] == 0 and execution["extra"]["resource_stop"] is None},
            {"name": "child_reaped", "passed": result["shell_evidence"]["closed.json"]["wrapper_reaped"] is True},
        ])
        fixture = run_fixture_control(root, helper, helper_path)
        result["inherited_network_fixture"] = fixture
        checks.extend(fixture["checks"])
        checks.append({"name": "direct_install_fixture_completed", "passed": fixture["passed"]})
        result["checks"] = checks
        result["passed"] = bool(child_result["passed"] and all(row["passed"] for row in checks))
    result["temporary_fixture_removed"] = True
    result["status"] = "passed" if result["passed"] else "failed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save the JSON receipt to a new file.")
    arguments = parser.parse_args()
    if arguments.output and arguments.output.exists():
        parser.error("--output must name a new file; existing evidence is never overwritten")
    sys.dont_write_bytecode = True
    result = {
        "version": "migration-249-server-sandbox-control-v1",
        "kernel": platform.release(), "platform": platform.system(), "machine": platform.machine(),
        "python": sys.version, "executable": sys.executable,
        "status": "blocked", "passed": False, "checks": [],
        "new_model_calls": 0, "new_gpu_execution": False, "business_tests_executed": 0,
        "scope": "Synthetic CPU shell and direct-install controls; no experiment or business-score rerun.",
    }
    try:
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            result["reason"] = "The native shell requires Linux x86_64."
        else:
            run_control(result)
    except Exception as error:
        result.update(status="failed", passed=False,
                      error={"type": type(error).__name__, "message": str(error)})
    payload = json.dumps(result, indent=2) + "\n"
    if arguments.output:
        with arguments.output.open("x", encoding="utf-8") as destination:
            destination.write(payload)
    print(payload, end="")
    return 0 if result["status"] == "passed" else 2 if result["status"] == "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
