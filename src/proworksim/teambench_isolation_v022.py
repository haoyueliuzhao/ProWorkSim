"""Unprivileged Landlock/seccomp role processes for the bounded D2 variant.

The controller alone constructs access profiles. No child may read grader state;
even the grader's re-execution of submitted Python re-enters this boundary.
This is a filesystem access-control sandbox, not a container or PID namespace.
"""
from __future__ import annotations

import ctypes
import errno
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import tempfile
import time

VERSION = "d2-landlock-role-isolation-v0.22"
READ = (1 << 2) | (1 << 3)  # READ_FILE, READ_DIR
EXECUTE = 1
WRITE = (1 << 15) - 1  # all filesystem operations through Landlock ABI 3
FILE_RW = (1 << 1) | (1 << 2) | (1 << 14)  # WRITE_FILE, READ_FILE, TRUNCATE
LIMITS = {"wall_seconds": 15, "cpu_seconds": 8, "address_space_bytes": 512 * 1024**2,
          "file_bytes": 1024**2, "capture_bytes": 128 * 1024, "open_files": 128}


def _json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def facility_probe():
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        return {"available": False, "reason": "requires Linux x86_64"}
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    try:
        ctypes.CDLL("libseccomp.so.2")
        seccomp = True
    except OSError:
        seccomp = False
    return {"available": abi >= 3 and seccomp, "landlock_abi": abi,
            "libseccomp_available": seccomp, "kernel": platform.release(),
            "uid": os.getuid(), "privilege_escalation": False}


def role_profile(root, role):
    """Profiles are made by the trusted controller, never accepted from a worker."""
    root = Path(root).resolve()
    if role not in {"planner", "executor", "verifier"}:
        raise ValueError("unsupported D2 role")
    # Runtime roots contain no benchmark secrets. No project, /home, /proc or
    # /tmp root is granted. /bin and /lib resolve into these runtime roots.
    grants = [{"path": "/usr", "rights": READ | EXECUTE},
              {"path": "/etc/ld.so.cache", "rights": 1 << 2},
              {"path": "/dev/null", "rights": (1 << 1) | (1 << 2)}]
    for path in (Path("/lib"), Path("/lib64")):
        if path.exists() and not str(path.resolve()).startswith("/usr/"):
            grants.append({"path": str(path.resolve()), "rights": READ | EXECUTE})
    grants += [{"path": str(root / "public"), "rights": READ},
               {"path": str(root / "roles" / role / "inbox"), "rights": READ},
               {"path": str(root / "roles" / role / "scratch"), "rights": WRITE},
               {"path": str(root / "roles" / role / "outbox"), "rights": WRITE}]
    if role == "executor":
        grants += [{"path": str(root / "workspace"), "rights": READ},
                   {"path": str(root / "workspace/clean.py"), "rights": FILE_RW},
                   {"path": str(root / "workspace/data/output"), "rights": WRITE}]
    elif role == "verifier":
        grants += [{"path": str(root / "workspace"), "rights": READ},
                   {"path": str(root / "roles/verifier/private"), "rights": READ}]
    else:
        grants += [{"path": str(root / "roles/planner/private"), "rights": READ}]
    # Reject replaced profile roots rather than granting a symlink target.
    for grant in grants[3:]:
        path = Path(grant["path"])
        if not path.exists() or path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError(f"sandbox grant must be an existing canonical path: {path}")
    return {"version": VERSION, "role": role, "root": str(root), "grants": grants,
            "cwd": str(root / "workspace" if role != "planner" else root / "roles/planner/scratch")}


def _restrict(profile):
    available = facility_probe()
    if not available["available"]:
        raise RuntimeError("required Landlock/seccomp facility unavailable")
    libc = ctypes.CDLL(None, use_errno=True)
    seccomp = ctypes.CDLL("libseccomp.so.2", use_errno=True)

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int)]

    rules = Ruleset(WRITE)
    descriptor = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    try:
        for grant in profile["grants"]:
            pfd = os.open(grant["path"], os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                rule = PathRule(grant["rights"], pfd)
                if libc.syscall(445, descriptor, 1, ctypes.byref(rule), 0):
                    raise OSError(ctypes.get_errno(), "landlock_add_rule")
            finally:
                os.close(pfd)
        if libc.prctl(38, 1, 0, 0, 0) or libc.syscall(446, descriptor, 0):
            raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    finally:
        os.close(descriptor)
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    context = seccomp.seccomp_init(0x7FFF0000)
    if not context:
        raise RuntimeError("seccomp_init failed")
    # Shell/fork/exec remain available, but inherit filesystem restrictions.
    # No sockets (including UNIX), cross-process memory/FD access, privilege
    # changes or escape to another process group/session are allowed.
    denied = ["socket", "socketpair", "connect", "bind", "listen", "accept", "accept4",
              "ptrace", "process_vm_readv", "process_vm_writev", "pidfd_getfd",
              "mount", "umount2", "pivot_root", "chroot", "unshare", "setns",
              "bpf", "perf_event_open", "io_uring_setup", "open_by_handle_at",
              "name_to_handle_at", "userfaultfd", "keyctl", "add_key", "request_key",
              "kill", "tkill", "tgkill", "setsid", "setpgid", "mknod", "mknodat",
              "setuid", "setgid", "setreuid", "setregid", "setresuid", "setresgid",
              "setfsuid", "setfsgid", "setgroups", "capset", "ioctl",
              "chmod", "fchmod", "fchmodat", "fchmodat2", "chown", "fchown", "lchown", "fchownat",
              "utime", "utimes", "futimesat", "utimensat", "setxattr", "lsetxattr", "fsetxattr",
              "removexattr", "lremovexattr", "fremovexattr"]
    try:
        for name in denied:
            number = seccomp.seccomp_syscall_resolve_name(name.encode())
            blocked_errno = errno.ENOTTY if name == "ioctl" else errno.EPERM
            if number >= 0 and seccomp.seccomp_rule_add(context, 0x00050000 | blocked_errno, number, 0):
                raise RuntimeError("seccomp_rule_add failed: " + name)
        if seccomp.seccomp_load(context):
            raise RuntimeError("seccomp_load failed")
    finally:
        seccomp.seccomp_release(context)
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS["cpu_seconds"], LIMITS["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS["address_space_bytes"], LIMITS["address_space_bytes"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS["file_bytes"], LIMITS["file_bytes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (LIMITS["open_files"], LIMITS["open_files"]))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return {**available, "version": VERSION, "filesystem": "kernel_landlock_allowlist",
            "network": "seccomp_socket_family_denied", "shell_inherits_restrictions": True,
            "pid_namespace": False, "limits": LIMITS}


def _worker(spec_path):
    spec = json.loads(Path(spec_path).read_text())
    profile, command = spec["profile"], spec["command"]
    os.chdir(profile["cwd"])
    os.environ.clear()
    os.environ.update({"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                       "TMPDIR": str(Path(profile["root"]) / "roles" / profile["role"] / "scratch"),
                       "PYTHONDONTWRITEBYTECODE": "1"})
    isolation = _restrict(profile)
    print(json.dumps({"isolation_installed": isolation}), flush=True)
    os.execv(command[0], command)


def run_role(root, role, command, *, log):
    """Execute a controller-declared command in a fresh unprivileged process.

    This fixture interface is not attached to a model adapter or arbitrary job
    server. The OS rules apply even if the declared command spawns a shell.
    """
    if not command or command[0] not in {"/usr/bin/python3", "/usr/bin/bash", "/usr/bin/cat"}:
        raise ValueError("entry executable outside fixed fixture interface")
    profile = role_profile(root, role)
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    spec = log.with_suffix(".spec.json")
    _json(spec, {"profile": profile, "command": command})
    started = time.monotonic()
    with tempfile.TemporaryFile() as capture:
        process = subprocess.Popen(["/usr/bin/python3", "-I", "-S", str(Path(__file__).resolve()),
                                    "worker", str(spec)], stdin=subprocess.DEVNULL, stdout=capture,
                                   stderr=subprocess.STDOUT, env={"LANG": "C.UTF-8"},
                                   close_fds=True, start_new_session=True)
        timed_out = False
        try:
            process.wait(timeout=LIMITS["wall_seconds"])
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            # All descendants inherit a denied setsid/setpgid; terminate only
            # our newly created process group, including any leftover child.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        capture.seek(0)
        raw = capture.read(LIMITS["capture_bytes"] + 1)
    text = raw[:LIMITS["capture_bytes"]].decode(errors="replace")
    first, _, rest = text.partition("\n")
    try:
        isolation = json.loads(first)["isolation_installed"]
    except (ValueError, KeyError):
        isolation, rest = None, text
    report = {"version": VERSION, "role": role, "command": command,
              "isolation": isolation, "returncode": process.returncode,
              "timeout": timed_out, "output": rest, "output_truncated": len(raw) > LIMITS["capture_bytes"],
              "elapsed_seconds": time.monotonic() - started, "profile": profile}
    _json(log, report)
    return report


def grader_dispatch(root, argv, log):
    """Trusted native-grader dispatch: submitted code never inherits gold access."""
    if argv == ["clean.py"]:
        result = run_role(root, "executor", ["/usr/bin/python3", "-I", "-B", "-S", "clean.py"], log=log)
        print(result["output"], end="")
        return result["returncode"] if result["isolation"] else 126
    # The only other python3 form used by the fixed, hashed grader.
    if len(argv) >= 2 and argv[0] == "-c":
        os.execv("/usr/bin/python3", ["/usr/bin/python3", "-I", "-B", "-S", *argv])
    raise ValueError("native grader requested an unexpected Python command")


if __name__ == "__main__":
    if sys.argv[1] == "worker":
        _worker(sys.argv[2])
    elif sys.argv[1] == "grader-dispatch":
        raise SystemExit(grader_dispatch(sys.argv[2], sys.argv[4:], sys.argv[3]))
    else:
        raise ValueError("unknown trusted entry")
