"""Bounded native shell, confined to one disposable calibration worktree.

Unlike the existing frozen-driver sandbox this permits subprocesses. Landlock
allows file contents only in the worktree and declared runtime paths; seccomp
denies networking and cross-process control. Public tests in this native tree
are editable: final authoritative tests must be copied afresh by the host.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import selectors
import signal
import subprocess
import sys
import time
import uuid

VERSION = "v051-landlock-native-shell"
DENIED = (
    "socket", "connect", "bind", "listen",
    "ptrace", "process_vm_readv", "process_vm_writev", "pidfd_getfd", "pidfd_send_signal",
    "kill", "tkill", "tgkill", "mount", "umount2", "pivot_root", "chroot", "unshare", "setns",
    "bpf", "perf_event_open", "io_uring_setup", "open_by_handle_at", "name_to_handle_at",
    "userfaultfd", "keyctl", "add_key", "request_key", "setsid", "setpgid",
    "chmod", "fchmod", "fchmodat", "fchmodat2", "chown", "fchown", "lchown", "fchownat",
    "utime", "utimes", "futimesat", "utimensat", "setxattr", "lsetxattr", "fsetxattr",
    "removexattr", "lremovexattr", "fremovexattr", "reboot", "kexec_load", "init_module",
    "finit_module", "delete_module", "swapon", "swapoff", "sethostname", "setdomainname",
)


def process_identity(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": int(pid), "start_ticks": int(fields[19]), "pgid": int(fields[2]),
            "sid": int(fields[3]), "parent_pid": int(fields[1])}


def record_current_process(spec, spec_path):
    """Register the separate session before untrusted work can create children."""
    identity = process_identity(os.getpid())
    parent = process_identity(spec["parent_pid"])
    if (identity["pgid"] != identity["pid"] or identity["sid"] != identity["pid"]
            or identity["parent_pid"] != spec["parent_pid"]
            or parent["start_ticks"] != spec["parent_start_ticks"]):
        raise RuntimeError("Native child parent/session identity changed before execution")
    raw = Path(spec_path).read_bytes()
    record = {"version": "v051-registered-child-process", **identity,
        "parent_start_ticks": parent["start_ticks"],
        "spec": {"path": str(Path(spec_path).resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    path = Path(spec_path).parent / "process.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2))
    temporary.replace(path)
    return record


def uid_threads():
    count = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = dict(line.split(":", 1) for line in (entry / "status").read_text().splitlines() if ":" in line)
            if int(fields["Uid"].split()[0]) == os.getuid():
                count += int(fields["Threads"].strip())
        except (OSError, KeyError, ValueError):
            continue
    return count


def install(spec):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("The bounded native shell requires Linux x86_64")
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise RuntimeError("Landlock ABI >= 3 required")

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int)]

    handled = (1 << 15) - 1
    rules = Ruleset(handled)
    fd = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    read = (1 << 0) | (1 << 2) | (1 << 3)  # EXECUTE / READ_FILE / READ_DIR
    write = read | (1 << 1) | (1 << 4) | (1 << 5) | (1 << 7) | (1 << 8) | (1 << 12) | (1 << 13) | (1 << 14)
    # Regular files/directories/symlinks only, never device nodes/FIFOs/sockets.
    paths = [(Path(spec["worktree"]), write)] + [(Path(path), read) for path in spec["readonly_paths"]]
    paths += [(Path("/dev/null"), (1 << 1) | (1 << 2)), (Path("/dev/urandom"), 1 << 2)]
    try:
        for path, rights in paths:
            path = path.resolve()
            if not path.exists():
                continue
            if not path.is_dir():
                rights &= ~(1 << 3)
            pfd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(rights, pfd)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0):
                    raise OSError(ctypes.get_errno(), "landlock_add_rule:" + str(path))
            finally:
                os.close(pfd)
        if libc.prctl(38, 1, 0, 0, 0) or libc.syscall(446, fd, 0):
            raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    finally:
        os.close(fd)

    seccomp = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    seccomp.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                              ctypes.c_uint, ctypes.c_void_p]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = seccomp.seccomp_init(0x7FFF0000)
    if not ctx:
        raise RuntimeError("seccomp_init failed")
    try:
        for name in DENIED:
            number = seccomp.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and seccomp.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, number, 0):
                raise RuntimeError("seccomp_rule_add failed:" + name)
        class Comparison(ctypes.Structure):
            _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int),
                        ("datum_a", ctypes.c_uint64), ("datum_b", ctypes.c_uint64)]
        # Only anonymous local socketpairs are available. TCP sockets must have
        # been supplied as already-connected fixture FDs by the trusted host.
        pair = seccomp.seccomp_syscall_resolve_name(b"socketpair")
        cmp = Comparison(0, 1, 1, 0)  # arg0 != AF_UNIX
        if seccomp.seccomp_rule_add_array(ctx, 0x00050000 | errno.EPERM, pair, 1, ctypes.byref(cmp)):
            raise RuntimeError("socketpair family rule failed")
        clone3 = seccomp.seccomp_syscall_resolve_name(b"clone3")
        if clone3 >= 0 and seccomp.seccomp_rule_add(ctx, 0x00050000 | errno.ENOSYS, clone3, 0):
            raise RuntimeError("clone3 fallback rule failed")
        clone = seccomp.seccomp_syscall_resolve_name(b"clone")
        for flag in (0x00020000, 0x02000000, 0x04000000, 0x08000000, 0x10000000, 0x20000000, 0x40000000):
            cmp = Comparison(0, 7, flag, flag)  # forbid namespace creation flags
            if seccomp.seccomp_rule_add_array(ctx, 0x00050000 | errno.EPERM, clone, 1, ctypes.byref(cmp)):
                raise RuntimeError("clone namespace rule failed")
        if seccomp.seccomp_load(ctx):
            raise RuntimeError("seccomp_load failed")
    finally:
        seccomp.seccomp_release(ctx)
    resource.setrlimit(resource.RLIMIT_CPU, (spec["cpu_seconds"], spec["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_AS, (spec["memory_bytes"], spec["memory_bytes"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (spec["file_bytes"], spec["file_bytes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (spec["uid_thread_limit"], spec["uid_thread_limit"]))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return {"version": VERSION, "landlock_abi": abi, "network": "seccomp_denied",
            "subprocesses": "allowed_with_uid_thread_margin_and_group_cleanup"}


def _worker(path):
    spec = json.loads(Path(path).read_text())
    record_current_process(spec, path)
    # Load native seccomp library before restricting filesystem reads.
    ctypes.CDLL("libseccomp.so.2")
    os.chdir(spec["worktree"])
    os.environ.clear()
    os.environ.update(spec["env"])
    proof = install(spec)
    print(json.dumps({"isolation_installed": proof, "nonce": spec["nonce"]}), flush=True)
    os.execve("/usr/bin/bash", ["bash", "--noprofile", "--norc", "-c", spec["command"]], spec["env"])


def tree_size(root):
    count = size = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(parent) / name).is_symlink()]
        for name in files:
            path = Path(parent) / name
            try:
                if not path.is_symlink():
                    count += 1
                    size += path.stat().st_size
            except FileNotFoundError:
                continue
    return count, size


def run_bounded_shell(command, *, worktree, python_executable, python_prefix, evidence_root,
                      timeout_seconds=30, output_bytes=1048576, workspace_bytes=67108864,
                      workspace_files=5000):
    worktree, evidence_root = Path(worktree).resolve(), Path(evidence_root).resolve()
    python_executable, python_prefix = Path(python_executable).absolute(), Path(python_prefix).resolve()
    if (not worktree.is_dir() or not python_executable.exists() or not python_prefix.is_dir()
            or evidence_root == worktree or evidence_root.is_relative_to(worktree)
            or not isinstance(command, str) or not command or len(command.encode()) > 32768
            or not 0 < timeout_seconds <= 60):
        raise ValueError("Invalid bounded native command/workspace/runtime/evidence declaration")
    evidence_root.mkdir(parents=True, exist_ok=True)
    temporary = worktree / ".calibration-tmp"
    temporary.mkdir(exist_ok=True)
    call = evidence_root / ("shell-" + uuid.uuid4().hex)
    call.mkdir()
    # Runtime roots are read-only, never the parent project or original repo.
    runtime_paths = ["/usr/bin", "/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/lib64",
        "/usr/lib/python3.12", "/etc/ld.so.cache", str(python_prefix)]
    for path in runtime_paths:
        actual = Path(path).resolve()
        if actual == worktree or worktree.is_relative_to(actual):
            raise ValueError("Runtime allowlist must not expose a parent of the writable tree")
    env = {"PATH": str(python_prefix / "bin") + ":/usr/bin:/bin",
        "TMPDIR": str(temporary), "LC_ALL": "C", "LANG": "C", "TZ": "UTC",
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(worktree) + ":" + str(worktree / "src"),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
        "PAGER": "cat", "MANPAGER": "cat", "PIP_NO_INDEX": "1", "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}
    spec = {"version": VERSION, "command": command, "worktree": str(worktree),
        "parent_pid": os.getpid(), "parent_start_ticks": process_identity(os.getpid())["start_ticks"],
        "readonly_paths": runtime_paths, "env": env, "nonce": uuid.uuid4().hex,
        "cpu_seconds": max(1, int(timeout_seconds) + 1), "memory_bytes": 2147483648,
        "file_bytes": 8388608, "uid_thread_limit": uid_threads() + 32}
    spec_path = call / "spec.json"
    spec_path.write_text(json.dumps(spec))
    started = time.monotonic()
    proc = subprocess.Popen([str(python_executable), "-I", "-S", str(Path(__file__).resolve()), str(spec_path)],
        cwd=worktree, env={"PATH": "/usr/bin:/bin"}, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    data, reason, next_size = bytearray(), None, 0.0
    try:
        while selector.get_map():
            elapsed = time.monotonic() - started
            if elapsed > timeout_seconds:
                reason = "wall_timeout"
                break
            if elapsed >= next_size:
                count, size = tree_size(worktree)
                next_size = elapsed + .5
                if count > workspace_files or size > workspace_bytes:
                    reason = "workspace_resource_limit"
                    break
            for key, _ in selector.select(.05):
                chunk = os.read(key.fd, 16384)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                data.extend(chunk[:max(0, output_bytes + 8192 - len(data))])
                if len(data) >= output_bytes + 8192:
                    reason = "output_limit"
                    break
            if reason:
                break
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)
        (call / "closed.json").write_text(json.dumps({"version": VERSION, "pid": proc.pid,
            "wrapper_reaped": True, "returncode": proc.returncode, "group_cleanup_signal": "SIGKILL",
            "closed_at": time.time(), "scope": "This parent requested cleanup of the entire recorded child session group"}, indent=2))
        selector.close()
        proc.stdout.close()
    text = bytes(data).decode("utf-8", errors="replace")
    first, _, body = text.partition("\n")
    try:
        proof = json.loads(first)
    except ValueError:
        proof = {}
    installed = proof.get("nonce") == spec["nonce"] and proof.get("isolation_installed", {}).get("version") == VERSION
    if not installed:
        raise RuntimeError("Native shell isolation failed before command execution: " + text[:2000])
    result = {"output": body[:output_bytes], "returncode": proc.returncode if reason is None else -1,
        "exception_info": "" if reason is None else reason,
        "extra": {"version": VERSION, "evidence_path": str(call), "seconds": time.monotonic() - started,
            "isolation": proof["isolation_installed"], "resource_stop": reason,
            "output_truncated": len(body) > output_bytes or reason == "output_limit",
            "workspace_budget_monitor": "0.5-second sampled aggregate bound; per-file RLIMIT_FSIZE",
            "public_tests_readonly": False}}
    (call / "output.txt").write_text(text)
    (call / "result.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    _worker(sys.argv[1])
