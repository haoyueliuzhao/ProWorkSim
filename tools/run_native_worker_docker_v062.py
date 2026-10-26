"""Native OpenHands tool worker inside an already isolated owned Docker actor.

Docker supplies PID, mount and network isolation. This program never creates a
namespace, performs a mount/chroot, or accesses the Docker API. Tool packages are
preloaded from a private copied runtime, then removed before repository actions
can run. The public interpreter and native tool schemas retain their old roles.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

from proworksim import software_benchmark_native_worker_v054 as native

IMPLEMENTATION = "v062-private-docker-native-worker-r1"
RUNTIME = Path("/opt/pws-runtime")
STDLIB = RUNTIME / "sysroot/usr/lib/python3.12"
PRIVATE_ROOTS = tuple(RUNTIME / name for name in ("site", "overlay", "upstream-tools", "project"))


def install_lifecycle_deadline(config):
    maximum = config.get("maximum_lifecycle_seconds")
    deadline = config.get("lifecycle_deadline")
    if (maximum not in (180, 24000) or type(maximum) is not int
            or type(deadline) not in (int, float)):
        raise ValueError("A fixed container-internal lifetime is required")
    remaining = deadline - time.monotonic()
    if not 0 < remaining <= maximum:
        raise ValueError("Owned actor lifetime is expired or exceeds the reviewed bound")
    # PID1 exit ends this container's descendant PID namespaces even if the host
    # supervisor disappears. Tool-level Exception handlers cannot swallow it.
    signal.signal(signal.SIGALRM, lambda _signum, _frame: os._exit(124))
    signal.setitimer(signal.ITIMER_REAL, remaining)


def validate_config(value):
    if (not isinstance(value, dict) or value.get("version") != IMPLEMENTATION
            or value.get("private_roots") != list(map(str, PRIVATE_ROOTS))
            or value.get("stdlib") != str(STDLIB)
            or value.get("vision_enabled") is not False):
        raise ValueError("Only the frozen private actor runtime layout is accepted")
    public = value.get("public_environment")
    if (not isinstance(public, dict) or public.get("kind") != "official_image"
            or not isinstance(public.get("environment"), dict)
            or not public.get("public_python", "").startswith("/")):
        raise ValueError("The original qualified public environment is required")
    for key, item in public["environment"].items():
        if not isinstance(key, str) or not isinstance(item, str) or "\0" in key + item:
            raise ValueError("Public environment entries must be ordinary text")
        if any(marker in item for marker in ("/data0/", "/data1/", "/home/zhuxinrui", "/opt/pws-runtime")):
            raise ValueError("Trusted host/runtime paths cannot enter repository commands")
    if public["environment"].get("PATH", "").split(":")[0] != str(Path(public["public_python"]).parent):
        raise ValueError("Public commands must use the original task interpreter")
    if (not value.get("instance_id") or value.get("official_task_admitted") is not True
            or not str(value.get("actor_image_id", "")).startswith("sha256:")
            or public.get("image_id") != value["actor_image_id"]
            or any(re.fullmatch(r"[0-9a-f]{40}", value.get(key, "")) is None
                   for key in ("baseline_head", "baseline_tree"))):
        raise ValueError("The actual sanitized actor image must be admitted by the host")
    return public


def remove_private_packages(*, runtime=RUNTIME, private_roots=PRIVATE_ROOTS):
    """Delete only the exact private copies, never a volume or public tree."""
    runtime = Path(runtime)
    expected = tuple(runtime / name for name in ("site", "overlay", "upstream-tools", "project"))
    if tuple(map(Path, private_roots)) != expected:
        raise ValueError("Only the private copied SDK directories may be removed")
    for root in (runtime, *expected):
        if root.is_symlink():
            raise ValueError("Private runtime cleanup cannot follow a symlink")
    for root in expected:
        if not root.is_dir():
            raise ValueError("Missing copied SDK directory before isolation")
        shutil.rmtree(root)
    if any(root.exists() or root.is_symlink() for root in expected):
        raise RuntimeError("Third-party SDK dependencies remain visible to actor commands")
    return {str(root): "removed_before_first_tool" for root in expected}


def seal_actor(public):
    if os.getpid() != 1 or not Path("/testbed").is_dir():
        raise RuntimeError("Native actor must be PID 1 with its isolated /testbed")
    if any(t.is_alive() for t in threading.enumerate() if t is not threading.main_thread()):
        raise RuntimeError("SDK preload created a background thread")
    for forbidden in ("site-packages", "dist-packages", "ensurepip", "requests", "sympy"):
        if (STDLIB / forbidden).exists():
            raise ValueError("Control standard library contains third-party code")
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
    if any(int(status[key].strip(), 16) for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")):
        raise RuntimeError("The Docker actor must drop all capabilities before startup")
    if status["NoNewPrivs"].strip() != "1":
        raise RuntimeError("Docker no-new-privileges is mandatory")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(4, 0, 0, 0, 0) != 0 or libc.prctl(3, 0, 0, 0, 0) != 0:
        raise RuntimeError("Cannot make the trusted native worker non-dumpable")
    removed = remove_private_packages()
    os.chdir("/testbed")
    os.environ.clear()
    os.environ.update(public["environment"])
    os.environ.update(CUDA_VISIBLE_DEVICES="", NVIDIA_VISIBLE_DEVICES="void")
    sys.path[:] = [str(STDLIB), str(STDLIB / "lib-dynload")]
    sys.path_importer_cache.clear()
    if not os.access(public["public_python"], os.X_OK):
        raise ValueError("The original public interpreter is unavailable")
    interfaces = [line.split(":", 1)[0].strip() for line in Path("/proc/net/dev").read_text().splitlines()[2:]]
    if interfaces != ["lo"] or list(Path("/dev").glob("nvidia*")):
        raise RuntimeError("Actor has a network/GPU device outside its isolated scope")
    return {"pid": os.getpid(), "uid": os.getuid(), "capabilities_all_zero": True,
        "no_new_privileges": True, "dumpable": False,
        "private_proc_pid1_root": os.readlink("/proc/1/root"),
        "network_interfaces": interfaces, "nvidia_nodes": [],
        "uid_map": Path("/proc/self/uid_map").read_text().strip(),
        "gid_map": Path("/proc/self/gid_map").read_text().strip(),
        "python_search_path": list(sys.path), "private_packages": removed,
        "namespaces": {name: os.stat("/proc/self/ns/" + name).st_ino for name in ("mnt", "pid", "net", "ipc")}}


def serve(config):
    public = validate_config(config)
    raw_public = Path("/pws/control/public-environment.json").read_bytes()
    if (hashlib.sha256(raw_public).hexdigest() != config.get("public_environment_sha256")
            or json.loads(raw_public) != public):
        raise ValueError("Copied public environment differs from its immutable source")
    identity = subprocess.run(["/usr/bin/git", "-c", "safe.directory=/testbed", "-C", "/testbed",
                              "rev-parse", "HEAD", "HEAD^{tree}"], env=public["environment"],
                             capture_output=True, timeout=30, check=True).stdout.decode().splitlines()
    dirty = subprocess.run(["/usr/bin/git", "-c", "safe.directory=/testbed", "-C", "/testbed",
                           "status", "--porcelain"], env=public["environment"],
                          capture_output=True, timeout=30, check=True).stdout
    if identity != [config["baseline_head"], config["baseline_tree"]] or dirty:
        raise ValueError("Named task volume differs from the original clean actor baseline")
    counters = {"network_attempts": 0, "weight_files_opened": 0, "gpu_device_opens": 0}
    phase = [True]
    def audit(event, args):
        if not phase[0]:
            return
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            counters["network_attempts"] += 1
            raise RuntimeError("No network during trusted native tool preload")
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            name = os.fsdecode(args[0])
            if name.endswith((".safetensors", ".gguf")) or "pytorch_model" in name:
                counters["weight_files_opened"] += 1
                raise RuntimeError("No model weights in the actor")
            if name.startswith(("/dev/nvidia", "/dev/dri/")):
                counters["gpu_device_opens"] += 1
                raise RuntimeError("No GPU in the actor")
    sys.addaudithook(audit)
    classes, definitions, sources, schemas = native.preload()
    isolation = seal_actor(public)
    phase[0] = False
    Path("/home/actor/observations").mkdir(parents=True, exist_ok=True)
    state = SimpleNamespace(workspace=SimpleNamespace(working_dir="/testbed"),
        env_observation_persistence_dir="/home/actor/observations", persistence_dir="/home/actor",
        agent=SimpleNamespace(llm=SimpleNamespace(vision_is_active=lambda: False)))
    tools = {"terminal": definitions["terminal"].create(state, terminal_type="subprocess",
              shell_path="/bin/bash", env=public["environment"])[0],
             "file_editor": definitions["file_editor"].create(state)[0],
             "task_tracker": definitions["task_tracker"].create(state)[0]}
    terminal = tools["terminal"].executor
    native.emit({"type": "ready", "version": native.VERSION, "implementation": IMPLEMENTATION,
        "isolation": isolation, "executors": {name: type(tool.executor).__module__ + "." + type(tool.executor).__name__ for name, tool in tools.items()},
        "terminal_backend": type(terminal._session.terminal).__module__ + "." + type(terminal._session.terminal).__name__,
        "official_sources": sources, "action_schemas": schemas,
        "tool_definitions": {name: {"description": tool.description,
            "annotations": tool.annotations.model_dump(mode="json") if tool.annotations else None,
            "meta": tool.meta, "openai_schema": tool.to_openai_tool(add_security_risk_prediction=True)} for name, tool in tools.items()},
        "public_environment_sha256": config["public_environment_sha256"],
        "public_environment_kind": public["kind"], "public_python": public["public_python"],
        "vision_enabled": False, "baseline": {"head": identity[0], "tree": identity[1], "working_tree_clean": True},
        "rootfs_binding": {"official_task_admitted": True,
            "kind": "official_image", "instance_id": config["instance_id"],
            "image_id": config["actor_image_id"], "admission_source": "host_verified_original_sanitized_actor_image"},
        "model_calls": 0, "trusted_preload_counters": counters})
    calls, close_identity = 0, None
    try:
        for line in sys.stdin:
            request = json.loads(line)
            identity = request.get("id")
            if set(request) == {"id", "op"} and request["op"] == "close":
                close_identity = identity
                break
            if set(request) != {"id", "tool", "action"} or request["tool"] not in classes:
                native.emit({"type": "error", "id": identity, "error": "Only official tool action JSON is accepted"})
                continue
            name = request["tool"]
            try:
                action = classes[name][0].model_validate(request["action"])
                observation = tools[name](action)
                calls += 1
                native.emit({"type": "observation", "id": identity, "tool": name,
                    "observation": observation.model_dump(mode="json"),
                    "llm_content": [item.model_dump(mode="json") for item in observation.to_llm_content]})
            except Exception as error:
                native.emit({"type": "error", "id": identity, "tool": name,
                    "error_type": type(error).__name__, "error": str(error)})
    finally:
        terminal.close()
    if close_identity is not None:
        native.emit({"type": "closed", "id": close_identity, "tool_calls": calls, "model_calls": 0,
                     "official_terminal_close_returned": True, "process_tree_quiescence_proven": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_bytes())
    install_lifecycle_deadline(config)
    serve(config)


if __name__ == "__main__":
    main()
