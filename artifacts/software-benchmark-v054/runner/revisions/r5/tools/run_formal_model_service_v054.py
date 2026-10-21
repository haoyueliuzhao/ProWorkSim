"""Start one factory-built service inside its owned model cgroup; never a smoke fallback."""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402
from proworksim.software_benchmark_service_factory_v054 import (  # noqa: E402
    MODEL, capacity_admission, condition_reference, ref_arguments,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--spec-sha256", required=True)
    parser.add_argument("--host-preclaim", type=Path)
    parser.add_argument("--host-lease", type=Path, required=True)
    args = parser.parse_args()
    from proworksim.software_benchmark_lease_handoff_v054 import receive_leases, drain_own_model_cgroup
    from proworksim.software_benchmark_supervision_v054 import process_identity
    lease_owner, lease_descriptors = receive_leases(args.host_lease)
    if reference(args.spec)["sha256"] != args.spec_sha256:
        raise ValueError("Frozen service specification changed")
    spec = json.loads(args.spec.read_text())
    arm, root, short = spec["arm"], Path(spec["root"]), Path(spec["short"])
    if (spec["condition"] != condition_reference(arm)
            or spec["factory_source"] != reference(ROOT / "src/proworksim/software_benchmark_service_factory_v054.py")):
        raise ValueError("Model service condition/factory changed")
    capacity = json.loads(checked(spec["capacity_receipt"]).read_text())
    if capacity["status"] != "capacity_and_synthetic_accounting_passed":
        raise ValueError("Actual model capacity has not passed")
    if spec["capacity_admission"] != capacity_admission(arm, spec["capacity_receipt"]):
        raise ValueError("Per-mode capacity/runtime admission changed")
    from tools.prepare_model_capacity_v054 import eligible, gpu_rows, source_identity
    if source_identity() != capacity["source"]:
        raise ValueError("Existing model stat/source receipt differs from the qualified checkpoint")
    cards = [card for card in eligible(gpu_rows(), "REF" if arm == "REF" else "MATCH")
             if card["uuid"] == spec["card"]["uuid"] and card["index"] == spec["card"]["index"]]
    if len(cards) != 1:
        raise RuntimeError("The admitted physical GPU no longer meets the original free-memory gate")
    card = cards[0]
    cache = root / "cache"
    cache.mkdir()
    env = ["HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1", "HF_DATASETS_OFFLINE=1",
           "LITELLM_LOCAL_MODEL_COST_MAP=True", "VLLM_NO_USAGE_STATS=1", "DO_NOT_TRACK=1",
           "PYTORCH_CUDA_ALLOC_CONF=backend:native",
           "NO_PROXY=*", "no_proxy=*", "HTTP_PROXY=", "HTTPS_PROXY=", "ALL_PROXY=",
           "http_proxy=", "https_proxy=", "all_proxy=", "PYTHONPATH=" + str(ROOT / "src") + ":" + str(ROOT),
           "TMPDIR=" + str(cache), "VLLM_CACHE_ROOT=" + str(cache), "XDG_CACHE_HOME=" + str(cache),
           "TORCHINDUCTOR_CACHE_DIR=" + str(cache / "inductor"), "CUDA_CACHE_PATH=" + str(cache / "cuda")]
    children = []
    def interrupted(*_):
        raise SystemExit("Owned model scope stopped")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    guard_stop = threading.Event()
    def host_guard():
        while not guard_stop.wait(.2):
            try:
                alive = process_identity(lease_owner["owner"]["pid"]) == lease_owner["owner"]
            except (OSError, ValueError, ProcessLookupError):
                alive = False
            if not alive:
                os.kill(os.getpid(), signal.SIGTERM)
                return
    threading.Thread(target=host_guard, daemon=True).start()
    try:
        if arm == "REF":
            if len(str(short).encode()) + 1 + 36 > 107:
                raise ValueError("REF IPC path exceeds the actual Linux Unix-socket path limit")
            env.append("TRITON_LIBCUDA_PATH=/opt/host-nvidia")
            env.append("CUDA_HOME=/usr/local/cuda-13.0")
            env.append("VLLM_RPC_BASE_PATH=" + str(short))
            if args.host_preclaim is None:
                raise ValueError("REF needs its pre-slot singleton port reservation")
            reservation = json.loads(args.host_preclaim.read_text())
            if reservation.get("port") != 18054 or reservation.get("exclusive_REF_resident") is not True:
                raise ValueError("Invalid REF deployment reservation")
            if process_identity(reservation["host_process"]["pid"]) != reservation["host_process"]:
                raise ValueError("REF reservation owner exited")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 18054))
            if spec["REF_argv"] != ref_arguments():
                raise ValueError("REF startup parameters differ from the fixed native condition")
            command = ["/bin/bash", str(ROOT / "tools/run_ref_preparation_v054.sh"), "--write-project",
                "--gpu", str(card["index"]), "/usr/bin/env", *env,
                str(ROOT / "runs/software-benchmark-v054/ref-venv/bin/python"),
                str(ROOT / "tools/start_ref_capacity_server_v054.py"), "--api-key-file", spec["api_key_file"],
                "--", *spec["REF_argv"]]
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True)
            children.append(process)
            key = Path(spec["api_key_file"]).read_text().strip()
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("New REF process exited before readiness; no existing-service fallback")
                if process_identity(reservation["host_process"]["pid"]) != reservation["host_process"]:
                    raise RuntimeError("REF reservation owner exited during startup")
                connection = http.client.HTTPConnection("127.0.0.1", 18054, timeout=2)
                try:
                    connection.request("GET", "/v1/models", headers={"Authorization": "Bearer " + key})
                    response = connection.getresponse()
                    raw = response.read(1024**2)
                    if response.status == 200:
                        models = json.loads(raw)
                        if any(row["id"] == "raw-qwen3.5-9b-v054-ref" and row["max_model_len"] == 131072
                               for row in models["data"]):
                            break
                except (OSError, ValueError, http.client.HTTPException):
                    pass
                finally:
                    connection.close()
                time.sleep(.2)
            else:
                raise TimeoutError("REF startup timed out")
            identity = {"model_revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a", "vllm_version": "0.32.0",
                "raw_release": True, "adapter_sha256": None, "model_manifest_sha256": spec["model_manifest"]["sha256"],
                "context_limit": 131072, "max_output_tokens": 32768, "service_admission_complete": True,
                "endpoint": "http://127.0.0.1:18054", "models_response": models,
                "capacity_receipt": spec["capacity_receipt"], "started_child_pid": process.pid,
                "condition": spec["condition"], "formal_generation_requests": 0}
            write_new(root / "identity.json", identity)
        else:
            codec_args = []
            if arm == "MATCH":
                codec = subprocess.Popen([str(ROOT / "tools/run_benchmark_runtime_v054.sh"), "--write-project",
                    "/usr/bin/env", *env, "CUDA_VISIBLE_DEVICES=", "NVIDIA_VISIBLE_DEVICES=void",
                    str(ROOT / "runs/software-benchmark-v054/ref-venv/bin/python"),
                    str(ROOT / "tools/serve_match_codec_v054.py"), "--model-local", str(MODEL),
                    "--socket", str(short / "codec.sock"), "--identity-output", str(root / "codec-identity.json")],
                    stdin=subprocess.DEVNULL, start_new_session=True)
                children.append(codec)
                deadline = time.monotonic() + 120
                while not (short / "codec.sock").exists():
                    if codec.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Pinned official codec did not initialize")
                    time.sleep(.1)
                codec_args = ["--codec-socket", str(short / "codec.sock"),
                              "--codec-identity", str(root / "codec-identity.json")]
            binding = {"version": "software-learning-resources-v0.50-r3", "gpu_index": card["index"],
                       "gpu_uuid": card["uuid"], "sampled_free_mib": card["free_mib"],
                       "target_mib": min(73728, card["free_mib"] - 1024)}
            command = [str(ROOT / "tools/run_benchmark_runtime_v054.sh"), "--write-project", "--gpu", str(card["index"]),
                "/usr/bin/env", *env, "PROWORKSIM_V053_GPU_BINDING=" + json.dumps(binding),
                str(ROOT / "runs/v016-sdk/resident-venv/bin/python"),
                str(ROOT / "tools/serve_formal_owner_v054.py"), "--socket", str(short / "owner.sock"),
                "--model-local", str(MODEL), "--model-manifest", str(MODEL / "proworksim-manifest.json"),
                "--contract", spec["contract"]["path"], "--output", str(root / "owner-service"),
                "--identity-output", str(root / "identity.json"), "--verified-source-receipt",
                str(ROOT / "artifacts/software-panel-v053/model-source-receipt.json"),
                "--allow-gpu-load", "--load-admission", spec["load_admission"]["path"], *codec_args]
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True)
            children.append(process)
            deadline = time.monotonic() + 1800
            while not (root / "owner-service/service-ready.json").exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("New raw owner did not initialize")
                time.sleep(.1)
        write_new(root / "ready.json", {"ready": True, "identity": reference(root / "identity.json"),
                  "condition": spec["condition"], "observed_card": card, "generation_requests": 0})
        return process.wait()
    finally:
        guard_stop.set()
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=10)
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        write_new(root / "model-descendants-quiescence.json", drain_own_model_cgroup())
        for descriptor in lease_descriptors:
            os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
