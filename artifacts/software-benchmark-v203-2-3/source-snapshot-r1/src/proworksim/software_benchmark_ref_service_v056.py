"""Persistent local REF engine for the separately frozen v056 budget experiment.

Only deployment identity (GPU, port and output directory) is configurable here.
Sampling and per-task budgets remain the controller's explicit responsibility.
"""
from __future__ import annotations

from contextlib import suppress
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import threading
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_gpu_lease_v054 import GpuLease
from .software_benchmark_supervision_v054 import process_identity

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs/software-benchmark-v056"
MODEL = ROOT / "runs/assets/models/Qwen3.5-9B-c20223623576"
MODEL_REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
MANIFEST_SHA = "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6"
MODEL_NAME = "raw-qwen3.5-9b-v054-ref"
VERSION = "v056-ref-budget-resident-r1"
MINIMUM_FREE_MIB = 66560
CAPACITY = ROOT / "runs/software-benchmark-v054/model-capacity-preparation-r6/ref/receipt.json"
VLLM_METADATA = ROOT / "runs/software-benchmark-v054/ref-venv/lib/python3.12/site-packages/vllm-0.32.0.dist-info/METADATA"
UUID = re.compile(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def server_arguments(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Use an explicit unprivileged loopback port")
    return ["serve", str(MODEL), "--host", "127.0.0.1", "--port", str(port),
            "--served-model-name", MODEL_NAME, "--tensor-parallel-size", "1",
            "--dtype", "bfloat16", "--gpu-memory-utilization", "0.8",
            "--max-model-len", "131072", "--max-num-seqs", "1",
            "--no-enable-prefix-caching", "--generation-config", "vllm",
            "--language-model-only", "--enable-auto-tool-choice",
            "--tool-call-parser", "qwen3_coder", "--reasoning-parser", "qwen3"]


def validate_spec(spec):
    folder = Path(spec["root"]).resolve()
    short = Path(spec["short"]).resolve()
    if (spec.get("version") != VERSION or not folder.is_relative_to(RUNS)
            or folder == RUNS or not short.is_relative_to(ROOT / "runs/g56")
            or len(str(short).encode()) > 70
            or type(spec.get("gpu_index")) is not int or not 0 <= spec["gpu_index"] <= 7
            or UUID.fullmatch(spec.get("gpu_uuid", "")) is None
            or spec.get("endpoint") != f"http://127.0.0.1:{spec['port']}"
            or spec.get("server_arguments") != server_arguments(spec["port"])
            or spec.get("api_key_file") != str(folder / "api-key.private")
            or spec.get("minimum_free_mib") != MINIMUM_FREE_MIB
            or spec.get("model_revision") != MODEL_REVISION
            or spec.get("model_manifest", {}).get("sha256") != MANIFEST_SHA
            or spec.get("numerical_settings_changed") is not False):
        raise ValueError("REF deployment differs from the frozen numerical configuration")
    manifest = checked(spec["model_manifest"])
    if manifest != MODEL / "proworksim-manifest.json":
        raise ValueError("Unexpected original model manifest")
    for item in spec["sources"]:
        checked(item)
    capacity = json.loads(checked(spec["inherited_capacity_receipt"]).read_bytes())
    if (spec["inherited_capacity_receipt"]["path"] != str(CAPACITY)
            or capacity.get("status") != "capacity_and_synthetic_accounting_passed"
            or capacity.get("arm") != "REF"
            or capacity.get("source", {}).get("model_manifest") != spec["model_manifest"]
            or checked(spec["vllm_package_metadata"]) != VLLM_METADATA
            or "Version: 0.32.0\n" not in VLLM_METADATA.read_text()):
        raise ValueError("Original REF capacity or pinned vLLM package identity differs")
    expected = {str(ROOT / name) for name in (
        "tools/serve_ref_budget_v056.py", "tools/run_ref_preparation_v054.sh",
        "tools/start_ref_capacity_server_v054.py", "tools/run_benchmark_runtime_v054.sh",
        "tools/enter_benchmark_runtime_v054.sh")}
    expected |= {str(Path(__file__).resolve())}
    if not expected <= {item["path"] for item in spec["sources"]}:
        raise ValueError("REF deployment source seal is incomplete")
    return spec


def create_service_spec(*, directory, gpu_index, gpu_uuid, port):
    """Freeze one new resident without loading weights or allocating GPU memory."""
    folder = Path(directory).resolve()
    if not folder.is_relative_to(RUNS) or folder == RUNS:
        raise ValueError("Use a fresh v056 resident directory")
    manifest = reference(MODEL / "proworksim-manifest.json")
    if manifest["sha256"] != MANIFEST_SHA:
        raise ValueError("Raw model manifest identity changed")
    short = ROOT / "runs/g56" / secrets.token_hex(5)
    spec = {"version": VERSION, "root": str(folder), "short": str(short),
            "gpu_index": gpu_index, "gpu_uuid": gpu_uuid, "port": port,
            "endpoint": f"http://127.0.0.1:{port}",
            "api_key_file": str(folder / "api-key.private"),
            "model_revision": MODEL_REVISION, "model_manifest": manifest,
            "inherited_capacity_receipt": reference(CAPACITY),
            "vllm_package_metadata": reference(VLLM_METADATA),
            "server_arguments": server_arguments(port),
            "minimum_free_mib": MINIMUM_FREE_MIB,
            "numerical_settings_changed": False,
            "sources": [reference(ROOT / name) for name in (
                "src/proworksim/software_benchmark_ref_service_v056.py",
                "tools/serve_ref_budget_v056.py", "tools/run_ref_preparation_v054.sh",
                "tools/start_ref_capacity_server_v054.py", "tools/run_benchmark_runtime_v054.sh",
                "tools/enter_benchmark_runtime_v054.sh")],
            "model_loads_at_spec_creation": 0, "task_generation_calls": 0}
    validate_spec(spec)
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    return write_new(folder / "spec.json", spec)


def observe_card(spec):
    result = subprocess.run(["nvidia-smi", "--id=" + str(spec["gpu_index"]),
        "--query-gpu=index,uuid,name,memory.total,memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=15, check=True)
    rows = [line for line in result.stdout.splitlines() if line.strip()]
    if len(rows) != 1:
        raise ValueError("Expected one physical GPU observation")
    index, uuid, name, total, free = [value.strip() for value in rows[0].split(",")]
    if int(index) != spec["gpu_index"] or uuid != spec["gpu_uuid"] or "A800" not in name:
        raise ValueError("Physical GPU identity differs from the admitted deployment")
    return {"index": int(index), "uuid": uuid, "name": name,
            "total_mib": int(total), "free_mib": int(free),
            "capacity_available": int(total) >= 81920 and int(free) >= MINIMUM_FREE_MIB}


class EndpointLease:
    def __init__(self, port):
        folder = ROOT / "runs/g56/locks"
        folder.mkdir(parents=True, exist_ok=True)
        self.handle = (folder / f"port-{port}.lock").open("a+b")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
        except BaseException:
            self.handle.close()
            raise

    def close(self):
        self.handle.close()


def models_response(spec, key):
    connection = http.client.HTTPConnection("127.0.0.1", spec["port"], timeout=2)
    try:
        connection.request("GET", "/v1/models", headers={"Authorization": "Bearer " + key})
        response = connection.getresponse()
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024 or response.status != 200:
            return None
        value = json.loads(raw)
        if any(row.get("id") == MODEL_NAME and row.get("max_model_len") == 131072
               for row in value.get("data", [])):
            return value
        return None
    finally:
        connection.close()


def runtime_command(spec, cache):
    env = ["HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1", "HF_DATASETS_OFFLINE=1",
           "LITELLM_LOCAL_MODEL_COST_MAP=True", "VLLM_NO_USAGE_STATS=1", "DO_NOT_TRACK=1",
           "PYTORCH_CUDA_ALLOC_CONF=backend:native", "TRITON_LIBCUDA_PATH=/opt/host-nvidia",
           "CUDA_HOME=/usr/local/cuda-13.0", "VLLM_RPC_BASE_PATH=" + spec["short"],
           "NO_PROXY=*", "no_proxy=*", "HTTP_PROXY=", "HTTPS_PROXY=", "ALL_PROXY=",
           "http_proxy=", "https_proxy=", "all_proxy=",
           "PYTHONPATH=" + str(ROOT / "src") + ":" + str(ROOT),
           "TMPDIR=" + str(cache), "VLLM_CACHE_ROOT=" + str(cache),
           "XDG_CACHE_HOME=" + str(cache), "TORCHINDUCTOR_CACHE_DIR=" + str(cache / "inductor"),
           "CUDA_CACHE_PATH=" + str(cache / "cuda")]
    return ["/bin/bash", str(ROOT / "tools/run_ref_preparation_v054.sh"), "--write-project",
            "--gpu", str(spec["gpu_index"]), "/usr/bin/env", *env,
            str(ROOT / "runs/software-benchmark-v054/ref-venv/bin/python"),
            str(ROOT / "tools/start_ref_capacity_server_v054.py"),
            "--api-key-file", spec["api_key_file"], "--", *spec["server_arguments"]]


def run_service(spec_reference):
    spec = validate_spec(json.loads(checked(spec_reference).read_bytes()))
    folder = Path(spec["root"])
    if any((folder / name).exists() for name in ("ready.json", "identity.json", "api-key.private", "launch.json")):
        raise ValueError("Never restart an entered resident identity; create a fresh specification")
    card = observe_card(spec)
    if not card["capacity_available"]:
        return 75
    device = endpoint = process = None
    requested = threading.Event()
    previous_handlers = {}
    try:
        try:
            device = GpuLease(spec["gpu_uuid"])
            endpoint = EndpointLease(spec["port"])
        except (BlockingIOError, OSError):
            return 75
        card = observe_card(spec)
        if not card["capacity_available"]:
            return 75
        key = secrets.token_urlsafe(48)
        fd = os.open(spec["api_key_file"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(key + "\n")
        cache = folder / "cache"
        cache.mkdir(mode=0o700)
        Path(spec["short"]).mkdir(parents=True, mode=0o700)
        command = runtime_command(spec, cache)
        write_new(folder / "launch.json", {"version": VERSION, "specification": spec_reference,
            "card": card, "GPU_lease": device.receipt, "command": command,
            "launch_host": process_identity(os.getpid()), "other_processes_signalled": False})
        descriptors = [handle.fileno() for handle in device.handles] + [endpoint.handle.fileno()]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True,
                                   pass_fds=descriptors)
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, lambda *_: requested.set())
        until, models = time.monotonic() + 1800, None
        while time.monotonic() < until and not requested.is_set():
            if process.poll() is not None:
                raise RuntimeError("Owned REF launcher exited before readiness")
            try:
                models = models_response(spec, key)
            except (OSError, ValueError, http.client.HTTPException):
                models = None
            if models is not None:
                break
            requested.wait(0.5)
        if requested.is_set():
            return 0
        if models is None:
            raise TimeoutError("REF service did not reach authenticated readiness")
        identity = write_new(folder / "identity.json", {
            "model_revision": MODEL_REVISION, "vllm_version": "0.32.0",
            "raw_release": True, "adapter_sha256": None, "model_manifest_sha256": MANIFEST_SHA,
            "context_limit": 131072, "max_output_tokens": 32768,
            "service_admission_complete": True, "endpoint": spec["endpoint"],
            "gpu_index": spec["gpu_index"], "gpu_uuid": spec["gpu_uuid"], "port": spec["port"],
            "deployment_version": VERSION, "models_response": models,
            "resident_spec": spec_reference,
            "inherited_capacity_receipt": spec["inherited_capacity_receipt"],
            "vllm_package_metadata": spec["vllm_package_metadata"],
            "numerical_settings_changed": False,
            "readiness_is_not_new_generation_qualification": True})
        write_new(folder / "ready.json", {"version": VERSION, "ready": True,
            "identity": identity, "identity_value": json.loads(checked(identity).read_bytes()),
            "endpoint": spec["endpoint"], "api_key_file": spec["api_key_file"],
            "gpu_index": spec["gpu_index"], "gpu_uuid": spec["gpu_uuid"],
            "host_process": process_identity(os.getpid()), "resident_child_pid": process.pid,
            "GPU_lease_held": True, "endpoint_lease_held": True,
            "models_resident": True, "model_calls_at_readiness": 0})
        while not requested.wait(0.5):
            if process.poll() is not None:
                return process.returncode
        return 0
    finally:
        if process is not None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=20)
            # Retain final group cleanup for an escaped engine child after launcher exit.
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            write_new(folder / "closed.json", {"version": VERSION,
                "resident_spec": spec_reference, "owned_launcher_exit_code": process.returncode,
                "owned_process_group_stop_requested": True, "other_processes_signalled": False,
                "complete_cgroup_quiescence_requires_supervisor_receipt": True})
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if endpoint is not None:
            endpoint.close()
        if device is not None:
            device.close()
