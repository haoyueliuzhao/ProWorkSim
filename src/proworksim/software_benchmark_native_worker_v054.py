"""Native OpenHands tool RPC worker, isolated after trusted module loading.

This dedicated process must already be PID 1 of a private PID namespace and
have private mount/network namespaces. It never runs an LLM or accepts Python
source/eval requests. Tool schemas and executors are the official 1.49.6 ones.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import pkgutil
import resource
import re
import socket
import struct
import sys
import threading
import traceback
from types import SimpleNamespace

VERSION = "software-benchmark-native-worker-v054"
CONTROL_STDLIB = "/opt/pws-control/python3.12"


def emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)


def _libc():
    return ctypes.CDLL(None, use_errno=True)


def _checked(result, operation):
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, operation + ": " + os.strerror(error))


def _mount(source, target, kind=None, flags=0, data=None):
    def raw(value):
        return value.encode() if value is not None else None
    _checked(_libc().mount(
        raw(source), raw(str(target)), raw(kind), ctypes.c_ulong(flags), raw(data)), "mount")


def _bind(source, target, *, readonly=False):
    _mount(str(source), target, flags=4096)  # MS_BIND
    if readonly:
        _mount(None, target, flags=4096 | 32 | 1 | 2 | 4)  # REMOUNT,RO,NOSUID,NODEV


def load_environment(path):
    data = Path(path).read_bytes()
    value = json.loads(data)
    if (value.get("version") != "v054-native-public-environment-v1"
            or value.get("kind") not in {"synthetic_cpu_fixture", "official_image"}):
        raise ValueError("An explicit public environment manifest is required")
    environment = value.get("environment")
    if (not isinstance(environment, dict)
            or not all(isinstance(key, str) and isinstance(item, str)
                       for key, item in environment.items())
            or not environment.get("HOME", "").startswith("/")
            or not value.get("public_python", "").startswith("/")):
        raise ValueError("Public image environment and interpreter are required")
    if environment.get("PATH", "").split(":")[0] != str(Path(value["public_python"]).parent):
        raise ValueError("Public PATH must explicitly select the admitted interpreter directory")
    for key, item in environment.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or "\0" in item:
            raise ValueError("Invalid public environment item")
        if any(path in item for path in (
                "/data0/zhuxinrui", "/data1/zhuxinrui", "/home/zhuxinrui",
                "/opt/pws-control", "resident-venv")):
            raise ValueError("Host/SDK dependency paths cannot enter the public environment")
    if value["kind"] == "official_image":
        digest = value.get("source_config_sha256", "")
        if (not re.fullmatch(r"[0-9a-f]{64}", digest)
                or value.get("image_id") != "sha256:" + digest):
            raise ValueError("Official public environment lacks the pinned image config identity")
    return value, hashlib.sha256(data).hexdigest()


def validate_rootfs(root, environment, *, preparation_only):
    if environment["kind"] == "synthetic_cpu_fixture":
        return {"kind": "synthetic_cpu_fixture", "official_task_admitted": False}
    manifest_path = Path(environment["rootfs_manifest"])
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != environment["rootfs_manifest_sha256"]:
        raise ValueError("Rootfs manifest changed after image export")
    manifest = json.loads(raw)
    if (manifest.get("version") != "v054-native-rootfs-v1"
            or Path(manifest["prepared_root"]).resolve() != Path(root).resolve()
            or manifest["image_id"] != environment["image_id"]
            or manifest["original_image_user"] != environment["original_image_user"]):
        raise ValueError("Worker rootfs differs from the pinned image/environment binding")
    admitted = (manifest.get("numeric_ownership_equivalence_admitted") is True
                and manifest.get("native_real_task_control_passed") is True)
    if not admitted and not preparation_only:
        raise ValueError("Official native rootfs lacks actual-image/UID qualification; CPU preparation only")
    return {"kind": "official_image", "rootfs_manifest_sha256": environment["rootfs_manifest_sha256"],
            "image_id": manifest["image_id"], "instance_id": manifest["instance_id"],
            "base_commit": manifest["base_commit"], "preparation_only": preparation_only,
            "official_task_admitted": admitted and not preparation_only}


def enable_private_loopback():
    # Docker --network none keeps loopback available. Preserve that capability
    # for repository tests without connecting the namespace to any host NIC.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        record = fcntl.ioctl(control, 0x8913, struct.pack("16sH14x", b"lo", 0))
        flags = struct.unpack("16sH14x", record)[1]
        fcntl.ioctl(control, 0x8914, struct.pack("16sH14x", b"lo", flags | 1))


def preload():
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    from openhands.tools.file_editor.definition import FileEditorAction
    from openhands.tools.file_editor.impl import FileEditorExecutor
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker.definition import TaskTrackerAction, TaskTrackerExecutor
    from openhands.tools.terminal.definition import TerminalAction
    from openhands.tools.terminal.impl import TerminalExecutor
    from openhands.tools.terminal import TerminalTool
    from openhands.tools.task_tracker import TaskTrackerTool

    # Encoding detectors lazily load language tables. Preload their ordinary
    # CPU modules while the trusted SDK installation is still visible.
    for package_name in ("charset_normalizer", "chardet", "encodings"):
        package = importlib.import_module(package_name)
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            if ("__main__" not in info.name and ".cli" not in info.name
                    and info.name not in {"encodings.mbcs", "encodings.oem"}):
                importlib.import_module(info.name)
    if importlib.metadata.version("openhands-sdk") != "1.49.6":
        raise ValueError("Native worker requires the frozen SDK")
    classes = {
        "terminal": (TerminalAction, TerminalExecutor),
        "file_editor": (FileEditorAction, FileEditorExecutor),
        "task_tracker": (TaskTrackerAction, TaskTrackerExecutor),
    }
    sources = {}
    for action, executor in classes.values():
        for cls in (action, executor):
            module = sys.modules[cls.__module__]
            path = Path(module.__file__)
            sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Capture official schemas before discarding dependency metadata/files.
    schemas = {name: action.model_json_schema() for name, (action, _) in classes.items()}
    definitions = {
        "terminal": TerminalTool, "file_editor": FileEditorTool, "task_tracker": TaskTrackerTool}
    return classes, definitions, sources, schemas


def enter_root(root, stdlib, public_environment):
    root, stdlib = Path(root).resolve(), Path(stdlib).resolve()
    if os.getpid() != 1:
        raise RuntimeError("Worker must be PID 1; inherited host /proc is not accepted")
    if root == Path("/") or not (root / "testbed").is_dir() or not (root / "bin/bash").is_file():
        raise ValueError("An explicit prepared rootfs with /testbed and /bin/bash is required")
    if any(name.is_alive() for name in threading.enumerate() if name is not threading.main_thread()):
        raise RuntimeError("Trusted preload created a live thread before isolation")
    forbidden = ("site-packages", "dist-packages", "ensurepip", "requests", "sympy")
    if any((stdlib / name).exists() for name in forbidden):
        raise ValueError("Control stdlib must not contain third-party/benchmark packages")
    for name in ("proc", "dev", "sys", "tmp", "testbed", "home/actor", "opt/pws-control/python3.12"):
        cursor = root
        for part in Path(name).parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError("Rootfs runtime mount/creation path traverses a symlink")
        (root / name).mkdir(parents=True, exist_ok=True)
    enable_private_loopback()
    _mount("proc", root / "proc", "proc", 1 | 2 | 4 | 8)  # read-only private PID proc
    _mount("tmpfs", root / "dev", "tmpfs", 2, "mode=755,size=8m")
    for name in ("null", "zero", "random", "urandom"):
        path = root / "dev" / name
        path.touch()
        _bind("/dev/" + name, path)
    (root / "dev/pts").mkdir()
    _mount("devpts", root / "dev/pts", "devpts", 2 | 8,
           "newinstance,ptmxmode=0666,mode=0620")
    (root / "dev/ptmx").symlink_to("pts/ptmx")
    for name, target in (("fd", "/proc/self/fd"), ("stdin", "/proc/self/fd/0"),
                         ("stdout", "/proc/self/fd/1"), ("stderr", "/proc/self/fd/2")):
        (root / "dev" / name).symlink_to(target)
    _mount("tmpfs", root / "sys", "tmpfs", 1 | 2 | 4 | 8, "mode=555,size=4k")
    _bind(stdlib, root / CONTROL_STDLIB.lstrip("/"), readonly=True)

    # No directory or dependency descriptors may survive the root transition.
    maximum = min(resource.getrlimit(resource.RLIMIT_NOFILE)[0], 1_048_576)
    os.closerange(3, int(maximum))
    os.chdir(root)
    os.chroot(".")
    os.chdir("/testbed")
    os.environ.clear()
    public = public_environment["environment"]
    os.environ.update({
        "PATH": public["PATH"], "HOME": public["HOME"],
        "USER": public.get("USER", "root"), "LOGNAME": public.get("LOGNAME", "root"),
        "LANG": public.get("LANG", "C.UTF-8"), "LC_ALL": public.get("LC_ALL", "C.UTF-8"),
        "TMPDIR": public.get("TMPDIR", "/tmp"),
        "CUDA_VISIBLE_DEVICES": "", "NVIDIA_VISIBLE_DEVICES": "void",
    })
    sys.path[:] = [CONTROL_STDLIB, CONTROL_STDLIB + "/lib-dynload"]
    # Clear import search caches referring to trusted dependency directories.
    sys.path_importer_cache.clear()
    if not os.access(public_environment["public_python"], os.X_OK):
        raise ValueError("The declared public interpreter is absent in the actual rootfs")

    libc = _libc()
    _checked(libc.prctl(38, 1, 0, 0, 0), "no_new_privileges")
    _checked(libc.prctl(4, 0, 0, 0, 0), "non_dumpable")
    for capability in range(64):
        result = libc.prctl(24, capability, 0, 0, 0)  # PR_CAPBSET_DROP
        if result != 0 and ctypes.get_errno() == errno.EINVAL:
            break
        _checked(result, "drop_capability")
    _checked(libc.prctl(47, 4, 0, 0, 0), "clear_ambient_capabilities")

    class Header(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]

    class Data(ctypes.Structure):
        _fields_ = [("effective", ctypes.c_uint32), ("permitted", ctypes.c_uint32),
                    ("inheritable", ctypes.c_uint32)]

    header = Header(0x20080522, 0)
    values = (Data * 2)()
    _checked(libc.capset(ctypes.byref(header), ctypes.byref(values)), "clear_capabilities")
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines()
                  if ":" in line)
    for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        if int(status[name].strip(), 16) != 0:
            raise RuntimeError("Worker retained a capability: " + name)
    if status["NoNewPrivs"].strip() != "1" or libc.prctl(3, 0, 0, 0, 0) != 0:
        raise RuntimeError("Worker privilege restrictions did not apply")
    return {
        "pid": os.getpid(), "uid": os.getuid(), "capabilities_all_zero": True,
        "no_new_privileges": True, "dumpable": False,
        "private_proc_pid1_root": os.readlink("/proc/1/root"),
        "network_interfaces": [line.split(":", 1)[0].strip()
                               for line in Path("/proc/net/dev").read_text().splitlines()[2:]],
        "python_search_path": list(sys.path),
        "nvidia_nodes": [str(path) for path in Path("/dev").glob("nvidia*")],
    }


def serve(root, stdlib, environment_manifest, *, vision_enabled=False, preparation_only=False):
    preload_phase = [True]
    counters = {"network_attempts": 0, "weight_files_opened": 0, "gpu_device_opens": 0}

    def audit(event, args):
        if not preload_phase[0]:
            return
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            counters["network_attempts"] += 1
            raise RuntimeError("No network during trusted tool preload")
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            path = os.fsdecode(args[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                counters["weight_files_opened"] += 1
                raise RuntimeError("No model weights during trusted tool preload")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                counters["gpu_device_opens"] += 1
                raise RuntimeError("No GPU access during trusted tool preload")

    sys.addaudithook(audit)
    public_environment, environment_sha = load_environment(environment_manifest)
    rootfs_binding = validate_rootfs(root, public_environment, preparation_only=preparation_only)
    classes, definitions, sources, schemas = preload()
    isolation = enter_root(root, stdlib, public_environment)
    preload_phase[0] = False
    Path("/home/actor/observations").mkdir(parents=True, exist_ok=True)
    # Construct official executors only after the tool-visible root is isolated.
    state = SimpleNamespace(
        workspace=SimpleNamespace(working_dir="/testbed"),
        env_observation_persistence_dir="/home/actor/observations",
        persistence_dir="/home/actor",
        agent=SimpleNamespace(llm=SimpleNamespace(vision_is_active=lambda: vision_enabled)))
    tools = {
        "terminal": definitions["terminal"].create(
            state, terminal_type="subprocess", shell_path="/bin/bash",
            env=public_environment["environment"])[0],
        "file_editor": definitions["file_editor"].create(state)[0],
        "task_tracker": definitions["task_tracker"].create(state)[0],
    }
    executors = {name: tool.executor for name, tool in tools.items()}
    terminal = executors["terminal"]
    emit({
        "type": "ready", "version": VERSION, "isolation": isolation,
        "executors": {name: type(value).__module__ + "." + type(value).__name__
                      for name, value in executors.items()},
        "terminal_backend": type(terminal._session.terminal).__module__ + "."
                            + type(terminal._session.terminal).__name__,
        "official_sources": sources, "action_schemas": schemas,
        "tool_definitions": {
            name: {
                "description": tool.description,
                "annotations": tool.annotations.model_dump(mode="json") if tool.annotations else None,
                "meta": tool.meta,
                "openai_schema": tool.to_openai_tool(add_security_risk_prediction=True),
            } for name, tool in tools.items()},
        "public_environment_sha256": environment_sha,
        "public_environment_kind": public_environment["kind"],
        "public_python": public_environment["public_python"], "vision_enabled": vision_enabled,
        "rootfs_binding": rootfs_binding,
        "model_calls": 0, "trusted_preload_counters": counters,
    })
    calls = 0
    close_identity = None
    try:
        for line in sys.stdin:
            request = json.loads(line)
            identity = request.get("id")
            if set(request) == {"id", "op"} and request["op"] == "close":
                close_identity = identity
                break
            if set(request) != {"id", "tool", "action"} or request["tool"] not in classes:
                emit({"type": "error", "id": identity, "error": "Only official tool action JSON is accepted"})
                continue
            name = request["tool"]
            try:
                action = classes[name][0].model_validate(request["action"])
                observation = tools[name](action)
                calls += 1
                emit({"type": "observation", "id": identity, "tool": name,
                      "observation": observation.model_dump(mode="json"),
                      "llm_content": [item.model_dump(mode="json")
                                      for item in observation.to_llm_content]})
            except Exception as error:
                emit({"type": "error", "id": identity, "tool": name,
                      "error_type": type(error).__name__, "error": str(error)})
    finally:
        terminal.close()
    if close_identity is not None:
        emit({"type": "closed", "id": close_identity, "tool_calls": calls, "model_calls": 0,
              "official_terminal_close_returned": True,
              "process_tree_quiescence_proven": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", required=True, type=Path)
    parser.add_argument("--stdlib", required=True, type=Path)
    parser.add_argument("--environment-manifest", required=True, type=Path)
    parser.add_argument("--vision-enabled", action="store_true")
    parser.add_argument("--preparation-only", action="store_true")
    args = parser.parse_args()
    try:
        serve(args.rootfs, args.stdlib, args.environment_manifest, vision_enabled=args.vision_enabled,
              preparation_only=args.preparation_only)
    except Exception as error:
        emit({"type": "bootstrap_error", "error_type": type(error).__name__,
              "error": str(error), "traceback": traceback.format_exc(), "model_calls": 0})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
