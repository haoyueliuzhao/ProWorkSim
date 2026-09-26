"""Fail-closed Linux Landlock/seccomp worker for the bounded software asset.

This is an OS access-control boundary, not a changed cwd. No user-supplied
command, shell, environment or host path is accepted. Requires x86_64 Linux,
Landlock ABI >= 3 and libseccomp. A fresh read-only source tree is used per run.
"""

import ctypes
import ctypes.util
import errno
import json
import os
from pathlib import Path
import platform
import resource
import secrets
import subprocess
import sys
import tempfile
import time
import types

SANDBOX_VERSION = "software-landlock-seccomp-v0.15"
LIMITS = {"wall_seconds": 20, "cpu_seconds": 10, "memory_bytes": 536870912,
          "output_bytes": 262144, "open_files": 64, "processes": 0}


def _restrict(tree):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("The frozen sandbox supports Linux x86_64 only")
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise RuntimeError("Landlock ABI >= 3 is required")
    # Handle every filesystem right supported through ABI 3, including REFER
    # and TRUNCATE. Later rights are not needed for the read-only worker.
    handled = (1 << 15) - 1

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int)]

    rules = Ruleset(handled)
    fd = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    allow = [Path(tree), Path(sys.base_prefix) / "lib" / ("python" + str(sys.version_info.major) + "." + str(sys.version_info.minor)),
             Path("/usr/lib/x86_64-linux-gnu"), Path("/usr/lib64"), Path("/etc/ld.so.cache")]
    try:
        for path in allow:
            if not path.exists():
                continue
            pfd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rights = (1 << 2) | ((1 << 3) if path.is_dir() else 0)  # READ_FILE / READ_DIR
                rule = PathRule(rights, pfd)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0) != 0:
                    raise OSError(ctypes.get_errno(), "landlock_add_rule")
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
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = seccomp.seccomp_init(0x7FFF0000)  # default ALLOW; filesystem policy is Landlock
    if not ctx:
        raise RuntimeError("seccomp_init failed")
    denied = ["socket", "socketpair", "connect", "bind", "listen", "accept", "accept4",
              "clone", "clone3", "fork", "vfork", "execve", "execveat", "ptrace",
              "process_vm_readv", "process_vm_writev", "pidfd_getfd", "mount", "umount2",
              "pivot_root", "chroot", "unshare", "setns", "bpf", "perf_event_open",
              "io_uring_setup", "open_by_handle_at", "name_to_handle_at", "userfaultfd",
              "keyctl", "add_key", "request_key", "kill", "tkill", "tgkill"]
    try:
        for name in denied:
            number = seccomp.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and seccomp.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, number, 0):
                raise RuntimeError("seccomp_rule_add failed: " + name)
        if seccomp.seccomp_load(ctx):
            raise RuntimeError("seccomp_load failed")
    finally:
        seccomp.seccomp_release(ctx)
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS["cpu_seconds"], LIMITS["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS["memory_bytes"], LIMITS["memory_bytes"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS["output_bytes"], LIMITS["output_bytes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (LIMITS["open_files"], LIMITS["open_files"]))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return {"version": SANDBOX_VERSION, "landlock_abi": abi, "filesystem": "read_only_allowlist",
            "network": "seccomp_denied", "subprocess": "seccomp_denied", "limits": LIMITS}


def _worker(spec_path):
    spec = json.loads(Path(spec_path).read_text())
    root, code = str(Path(spec["tree"]).resolve()), compile(spec["code"], "<frozen-test-driver>", "exec")
    completion_nonce = spec["completion_nonce"]
    # Load required native library before confinement; never weaken access on failure.
    import unittest
    import socket
    del unittest, socket
    ctypes.CDLL(ctypes.util.find_library("seccomp") or "libseccomp.so.2")
    del spec
    os.chdir(root)
    os.environ.clear()
    sys.dont_write_bytecode = True
    sys.path[:] = [root + "/src", root, *[p for p in sys.path if p.startswith("/usr/lib/python")]]
    isolation = _restrict(root)
    print(json.dumps({"isolation_installed": isolation}), flush=True)
    sys.argv[:] = ["frozen-tests"]
    module = types.ModuleType("__main__")
    module.__file__ = "<frozen-test-driver>"
    sys.modules["__main__"] = module
    exec(code, module.__dict__, module.__dict__)
    print(json.dumps({"driver_completed": completion_nonce}), flush=True)


def run_isolated(files, code, *, run_root):
    """Execute frozen controller test code against exactly these source bytes.

    files is an in-memory relative-path/text mapping, not an actor-chosen path.
    The test driver is outside the source tree and is loaded before confinement.
    No hidden driver file is readable via the actor's source tools.
    """
    run_root = Path(run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="isolated-", dir=run_root) as name:
        directory = Path(name)
        tree = directory / "tree"
        tree.mkdir()
        if not isinstance(files, dict) or len(files) > 200 or sum(len(v.encode()) for v in files.values()) > 2_000_000:
            raise ValueError("Source bundle exceeds the frozen bounds")
        for name, content in files.items():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or not isinstance(content, str):
                raise ValueError("Source names must be safe relative files")
            destination = tree / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        spec = directory / "driver.json"
        completion_nonce = secrets.token_hex(32)
        spec.write_text(json.dumps({"tree": str(tree), "code": code, "completion_nonce": completion_nonce}))
        started = time.monotonic()
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(["/usr/bin/python3", "-I", "-S", str(Path(__file__).resolve()), str(spec)],
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                       env={"LANG": "C.UTF-8"}, close_fds=True, start_new_session=True)
            timeout = False
            try:
                process.wait(timeout=LIMITS["wall_seconds"])
            except subprocess.TimeoutExpired:
                timeout = True
                process.kill()
                process.wait()
            output.seek(0)
            raw = output.read(LIMITS["output_bytes"] + 1)
        text = raw[:LIMITS["output_bytes"]].decode("utf-8", errors="replace")
        first, _, rest = text.partition("\n")
        try:
            isolation = json.loads(first)["isolation_installed"]
        except (ValueError, KeyError):
            isolation, rest = None, text
        completion = json.dumps({"driver_completed": completion_nonce})
        completed = rest.rstrip().endswith(completion)
        if completed:
            rest = rest[:rest.rfind(completion)]
        return {"sandbox": isolation, "executed": isolation is not None, "driver_completed": completed, "returncode": process.returncode,
                "timeout": timeout, "output": rest, "output_truncated": len(raw) > LIMITS["output_bytes"],
                "elapsed_seconds": time.monotonic() - started}


if __name__ == "__main__":
    _worker(sys.argv[1])
