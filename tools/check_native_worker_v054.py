"""Finite real namespace/native-tool CPU control on a synthetic rootfs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import traceback

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("/data0/zhuxinrui/proworksim-runtime/sysroot")


def reference(path):
    data = Path(path).read_bytes()
    return {"path": str(Path(path).resolve()), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def make_root(folder):
    root, stdlib = folder / "rootfs", folder / "control-stdlib"
    root.mkdir()
    for name in ("bin", "usr/bin", "usr/lib", "usr/lib64", "etc", "testbed/sub",
                 "home/actor", "tmp", "public", "opt/pws-control/python3.12"):
        (root / name).mkdir(parents=True, exist_ok=True)
    for name in ("bash", "cat", "mkdir", "rm", "pwd", "sleep", "touch", "find",
                 "readlink", "grep", "sed", "head", "timeout", "ps", "env", "python3.12"):
        shutil.copy2(RUNTIME / "usr/bin" / name, root / "usr/bin" / name)
    (root / "bin/bash").symlink_to("../usr/bin/bash")
    (root / "bin/sh").symlink_to("../usr/bin/bash")
    (root / "usr/bin/python").symlink_to("python3.12")
    for name in ("x86_64-linux-gnu",):
        shutil.copytree(RUNTIME / "usr/lib" / name, root / "usr/lib" / name, symlinks=True)
    shutil.copytree(RUNTIME / "usr/lib64", root / "usr/lib64", symlinks=True, dirs_exist_ok=True)
    (root / "lib").symlink_to("usr/lib")
    (root / "lib64").symlink_to("usr/lib64")
    excluded = (
        "__pycache__", "site-packages", "dist-packages", "ensurepip", "test", "tests",
        "idlelib", "tkinter", "turtledemo", "*.whl",
    )
    shutil.copytree(RUNTIME / "usr/lib/python3.12", stdlib, symlinks=True,
                    ignore=shutil.ignore_patterns(*excluded))
    (root / "usr/lib/python3.12").symlink_to("../../opt/pws-control/python3.12")
    (root / "etc/passwd").write_text("root:x:0:0:actor:/home/actor:/bin/bash\n")
    (root / "etc/group").write_text("root:x:0:\n")
    (root / "etc/nsswitch.conf").write_text("passwd: files\ngroup: files\nhosts: files\n")
    (root / "public/note.txt").write_text("PUBLIC_ABSOLUTE_PATH\n")
    (root / "testbed/original.txt").write_text("public initial file\n")
    secret = folder / "outside-host-marker.txt"
    secret.write_text("SYNTHETIC_HOST_MUST_NOT_BE_READ\n")
    return root, stdlib, secret


def read_message(process, timeout=30):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout):
            raise TimeoutError("Native worker did not return an RPC record")
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("Native worker exited without an RPC record")
        return json.loads(line)


def observation_text(observation):
    return "".join(item.get("text", "") for item in observation["content"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    root, stdlib, secret = make_root(folder)
    environment = folder / "public-environment.json"
    environment.write_text(json.dumps({
        "version": "v054-native-public-environment-v1", "kind": "synthetic_cpu_fixture",
        "image_id": None, "source_config_sha256": None, "public_python": "/usr/bin/python",
        "environment": {"PATH": "/usr/bin:/bin", "HOME": "/home/actor",
                        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TMPDIR": "/tmp"},
    }, sort_keys=True, indent=2) + "\n")
    receipt = {
        "version": "v054-native-worker-cpu-control-v1", "passed": False,
        "started_utc": datetime.now(timezone.utc).isoformat(), "model_calls": 0,
        "gpu_launches": 0, "actual_verified_tasks": 0,
        "scope": "Real dedicated namespaces and unchanged official executors; synthetic rootfs",
        "source_files": [reference(ROOT / name) for name in (
            "src/proworksim/software_benchmark_native_worker_v054.py",
            "tools/run_native_worker_cpu_v054.sh", "tools/check_native_worker_v054.py")],
    }
    command = [
        str(ROOT / "tools/run_native_worker_cpu_v054.sh"),
        "--rootfs", str(root), "--stdlib", str(stdlib),
        "--environment-manifest", str(environment)]
    process = None
    transcript = []
    with (folder / "worker.stderr").open("wb") as errors:
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=errors, text=True, bufsize=1, start_new_session=True)
            ready = read_message(process)
            transcript.append(ready)
            assert ready["type"] == "ready", ready
            receipt["ready"] = ready
            assert ready["isolation"]["pid"] == 1
            assert ready["isolation"]["capabilities_all_zero"]
            assert ready["isolation"]["dumpable"] is False
            assert ready["isolation"]["nvidia_nodes"] == []
            assert ready["terminal_backend"].endswith("subprocess_terminal.SubprocessTerminal")
            counter = 0

            def call(tool, action):
                nonlocal counter
                counter += 1
                request = {"id": counter, "tool": tool, "action": action}
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
                result = read_message(process)
                transcript.append({"request": request, "response": result})
                assert result.get("id") == counter, result
                assert result["type"] == "observation", result
                return result["observation"]

            first = call("terminal", {
                "command": "cd /testbed/sub; export PWS_NATIVE_MARKER=persistent; printf payload > state.txt",
                "timeout": 10})
            assert first["exit_code"] == 0, first
            second = call("terminal", {
                "command": 'printf "%s|%s|" "$PWD" "$PWS_NATIVE_MARKER"; cat state.txt',
                "timeout": 10})
            assert "/testbed/sub|persistent|payload" in observation_text(second), second
            assert second["metadata"]["working_dir"] == "/testbed/sub", second
            for path, text in (("/testbed/a.py", "A = 1\n"), ("/testbed/sub/b.py", "B = 2\n")):
                observation = call("file_editor", {"command": "create", "path": path, "file_text": text})
                assert not observation["is_error"], observation
            changed = call("file_editor", {
                "command": "str_replace", "path": "/testbed/sub/b.py",
                "old_str": "B = 2", "new_str": "B = 3"})
            assert not changed["is_error"]
            public = call("file_editor", {"command": "view", "path": "/public/note.txt"})
            assert not public["is_error"] and "PUBLIC_ABSOLUTE_PATH" in observation_text(public)
            source = next(iter(ready["official_sources"]))
            denied = []
            for path in (str(secret), source, "/proc/1/root" + str(secret)):
                result = call("file_editor", {"command": "view", "path": path})
                assert result["is_error"] is True, result
                denied.append(path)
            probe = (
                "python - <<'PY'\n"
                "import ctypes, importlib.util, socket\n"
                "assert importlib.util.find_spec('requests') is None\n"
                "assert importlib.util.find_spec('sympy') is None\n"
                "try:\n"
                " open('/proc/1/mem','rb')\n"
                " raise AssertionError('worker memory exposed')\n"
                "except PermissionError:\n"
                " pass\n"
                "libc=ctypes.CDLL(None,use_errno=True)\n"
                "assert libc.chroot(b'/') == -1 and ctypes.get_errno() == 1\n"
                "s=socket.socket();s.settimeout(1)\n"
                "try:\n"
                " s.connect(('198.51.100.1',443))\n"
                " raise AssertionError('external network exposed')\n"
                "except OSError:\n"
                " pass\n"
                "finally:\n"
                " s.close()\n"
                "print('ISOLATION_PROBE_PASSED')\n"
                "PY"
            )
            probed = call("terminal", {"command": probe, "timeout": 10})
            assert probed["exit_code"] == 0 and "ISOLATION_PROBE_PASSED" in observation_text(probed), probed
            planned = call("task_tracker", {
                "command": "plan", "task_list": [{"title": "Synthetic public step", "status": "todo"}]})
            assert not planned["is_error"]
            viewed = call("task_tracker", {"command": "view"})
            assert viewed["task_list"][0]["title"] == "Synthetic public step"
            process.stdin.write(json.dumps({"id": counter + 1, "tool": "eval", "action": {}}) + "\n")
            process.stdin.flush()
            rejected = read_message(process)
            assert rejected["type"] == "error"
            transcript.append(rejected)
            process.stdin.write(json.dumps({"id": counter + 2, "op": "close"}) + "\n")
            process.stdin.flush()
            closed = read_message(process)
            transcript.append(closed)
            assert closed["type"] == "closed"
            assert process.wait(timeout=15) == 0
            assert (root / "testbed/a.py").read_text() == "A = 1\n"
            assert (root / "testbed/sub/b.py").read_text() == "B = 3\n"
            assert (root / "testbed/sub/state.txt").read_text() == "payload"
            assert secret.read_text() == "SYNTHETIC_HOST_MUST_NOT_BE_READ\n"
            receipt.update({
                "passed": True, "tool_calls": counter, "official_terminal_state_persisted": True,
                "absolute_path_inside_rootfs_allowed": True, "denied_outside_paths": denied,
                "host_marker_unchanged": True, "unknown_rpc_rejected": True,
                "worker_and_pty_exit_code": process.returncode,
                "network_denial_probe_attempts": 1, "external_connections": 0,
                "kernel_chroot_escape_denied": True, "worker_memory_read_denied": True,
            })
        except BaseException as error:
            receipt["error"] = {"type": type(error).__name__, "message": str(error)}
            receipt["traceback"] = traceback.format_exc()
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, 15)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, 9)
                    process.wait(timeout=10)
            receipt["ended_utc"] = datetime.now(timezone.utc).isoformat()
            (folder / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n")
            (folder / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: receipt[key] for key in ("passed", "model_calls", "gpu_launches")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
