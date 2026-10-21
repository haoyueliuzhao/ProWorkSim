"""One GPU6 successor launcher; preload before exact predecessor retirement, never retry a load."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path("/data0/zhuxinrui/projects/ProWorkSim")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
    from proworksim.software_benchmark_resident_provisioner_v054 import unit_state
    from proworksim.software_benchmark_service_factory_v054 import MODEL, capacity_admission
    from proworksim.software_benchmark_supervision_v054 import process_identity
    from proworksim.storage import atomic_write, json_bytes
    spec_ref = reference(args.spec)
    if spec_ref["sha256"] != args.sha256:
        raise ValueError("Successor specification changed")
    spec = json.loads(checked(spec_ref).read_bytes())
    source_root = Path(spec["kernel_source_root"])
    if (spec.get("version") != "v054-match-resident-spec-v3" or spec["card"]["index"] != 6
            or spec.get("session_protocol") != "mp-interleave-v1" or spec.get("maximum_sessions") != 2
            or spec.get("kernel_runtime_revision") != "FP32-recurrent-distribution-v2"
            or not source_root.resolve().is_relative_to(ROOT / "runs/software-benchmark-v054/kernel-optimization-r1")
            or checked(spec["owner_entrypoint"]) != source_root / "tools/serve_kernel_interleaved_owner_v054.py"
            or not spec["unit"].startswith("proworksim-v054-resident-mp-g6-")):
        raise ValueError("Only the independent single-GPU6 kernel revision is supported")
    for field in ("kernel_plan", "dependencies_manifest", "gpu_runtime", "old_registration", "old_ready", "source_manifest"):
        checked(spec[field])
    for frozen in spec["sources"]:
        checked(frozen)
    plan = json.loads(checked(spec["kernel_plan"]).read_bytes())
    if plan["dependencies_manifest"] != spec["dependencies_manifest"]:
        raise ValueError("Model diagnostic and deployment dependency identities differ")
    dependency_files = json.loads(checked(spec["dependencies_manifest"]).read_bytes())["files"]
    for item in dependency_files:
        checked({key: item[key] for key in ("path", "sha256", "bytes")})
    capacity_admission("MATCH", spec["capacity_receipt"])
    unit = unit_state(spec["unit"])
    if (int(unit.get("MainPID", 0)) != os.getpid()
            or not unit.get("ControlGroup", "").endswith("/" + spec["unit"])):
        raise ValueError("Run the successor in its exact dedicated systemd user unit")
    root, short = Path(spec["root"]), Path(spec["short"])
    if (not root.resolve().is_relative_to(ROOT / "runs/software-benchmark-v054")
            or not short.resolve().is_relative_to(ROOT / "runs/v054-gpu")):
        raise ValueError("Private persistent paths escaped the project")
    root.mkdir(parents=True, exist_ok=True)
    short.mkdir(parents=True, exist_ok=True)
    write_new(root / "launcher-started.json", {"source_spec": spec_ref,
        "host_process": process_identity(os.getpid()), "model_load_attempts_permitted": 1,
        "old_service_signalled_by_launcher": False, "cross_process_memory_handoff_atomic": False})
    cache = root / "cache"
    cache.mkdir()
    env = ["PYTHONPATH=" + str(source_root / "src") + ":" + str(source_root) + ":" + plan["overlay_path"],
        "PYTHONDONTWRITEBYTECODE=1", "HF_HUB_OFFLINE=1", "HF_DATASETS_OFFLINE=1", "TRANSFORMERS_OFFLINE=1",
        "LITELLM_LOCAL_MODEL_COST_MAP=True", "PYTORCH_CUDA_ALLOC_CONF=backend:native",
        "TRITON_LIBCUDA_PATH=/opt/host-nvidia", "CUDA_HOME=/usr/local/cuda-13.0",
        "FLA_DISABLE_TENSOR_CACHE=1", "USE_HUB_KERNELS=NO", "TRITON_CACHE_DIR=" + str(cache / "triton"),
        "TMPDIR=" + str(cache), "XDG_CACHE_HOME=" + str(cache), "NO_PROXY=*", "no_proxy=*",
        "HTTP_PROXY=", "HTTPS_PROXY=", "ALL_PROXY=", "http_proxy=", "https_proxy=", "all_proxy="]
    children = []
    def stop(*_):
        raise SystemExit("Explicit successor shutdown")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        codec_identity = root / "codec-identity.json"
        codec = subprocess.Popen([str(ROOT / "tools/run_benchmark_runtime_v054.sh"), "--write-project",
            "/usr/bin/env", *env, "CUDA_VISIBLE_DEVICES=", "NVIDIA_VISIBLE_DEVICES=void",
            str(ROOT / "runs/software-benchmark-v054/ref-venv/bin/python"),
            str(source_root / "tools/serve_match_codec_v054.py"), "--model-local", str(MODEL),
            "--socket", str(short / "codec.sock"), "--identity-output", str(codec_identity)], start_new_session=True)
        children.append(codec)
        until = time.monotonic() + 180
        while not (short / "codec.sock").exists():
            if codec.poll() is not None or time.monotonic() >= until:
                raise RuntimeError("Independent CPU codec did not become ready")
            time.sleep(.05)
        owner_args = ["--max-sessions", "2", "--socket", str(short / "admin.sock"),
            "--model-local", str(MODEL), "--model-manifest", str(MODEL / "proworksim-manifest.json"),
            "--contract", str(checked(spec["contract"])), "--output", str(root / "owner-service"),
            "--identity-output", spec["identity_path"], "--verified-source-receipt",
            str(ROOT / "artifacts/software-panel-v053/model-source-receipt.json"),
            "--allow-gpu-load", "--load-admission", str(checked(spec["load_admission"])),
            "--resident-preparation-permit", str(checked(spec["preparation_permit"])),
            "--codec-socket", str(short / "codec.sock"), "--codec-identity", str(codec_identity)]
        guard = write_new(root / "guard-plan.json", {"version": "v054-kernel-owner-guard-r1",
            "gpu_index": 6, "gpu_uuid": spec["card"]["uuid"], "initial_buffer_mib": 512,
            "maximum_load_attempts": 1, "formal_model_calls_before_qualification": 0,
            "cross_process_memory_handoff_atomic": False, "source_spec": spec_ref,
            "old_registration": spec["old_registration"], "old_ready": spec["old_ready"],
            "kernel_plan": spec["kernel_plan"], "owner_entrypoint": spec["owner_entrypoint"],
            "source_manifest": spec["source_manifest"], "output": str(root / "guard"),
            "release_path": spec["release_path"], "release_wait_seconds": 7200,
            "owner_arguments": owner_args,
            **({"previous_failed_preparation": spec["previous_failed_preparation"]}
               if spec.get("previous_failed_preparation") is not None else {})})
        owner = subprocess.Popen(["/bin/bash", str(checked(spec["gpu_runtime"])), "--write-project", "--gpu", "6",
            "/usr/bin/env", *env, str(ROOT / "runs/v016-sdk/resident-venv/bin/python"),
            str(source_root / "tools/guard_kernel_owner_v054.py"), "--plan", guard["path"],
            "--plan-sha256", guard["sha256"]], start_new_session=True)
        children.append(owner)
        while not (root / "owner-service/service-ready.json").is_file():
            if owner.poll() is not None:
                raise RuntimeError("Successor guard exited before model readiness")
            failure = root / "guard/failure.json"
            if failure.exists():
                atomic_write(root / "status.json", json_bytes({"status": "failed_manual_action_required",
                    "source_spec": spec_ref, "failure": reference(failure), "automatic_retry": False,
                    "GPU_allocation_retained_until_explicit_stop": True}))
                return owner.wait()  # Guard waits without retry or further CUDA calls.
            time.sleep(.1)
        identity = json.loads(Path(spec["identity_path"]).read_bytes())
        kernel = identity["actor_identity"].get("kernel_runtime")
        if (not kernel or kernel["plan"] != spec["kernel_plan"]
                or json.loads(checked(kernel["qualification"]).read_bytes()).get("passed") is not True):
            raise ValueError("Successor did not qualify its explicit new numerical path")
        from tools.prepare_kernel_deployment_v054 import validate_distribution_qualifier
        validate_distribution_qualifier(json.loads(checked(kernel["qualification"]).read_bytes()))
        owned = json.loads((root / "guard/gpu-lease.json").read_bytes())
        write_new(spec["ready_path"], {"ready": True, "resident": True, "source_spec": spec_ref,
            "host_process": process_identity(os.getpid()), "gpu_index": 6, "gpu_uuid": spec["card"]["uuid"],
            "resident_id": spec["resident_id"], "pool_policy": spec["pool_policy"],
            "resource_binding": owned["binding"], "gpu_lease_held": True,
            "lease_holder": owned["host_process"], "lease_evidence": reference(root / "guard/gpu-lease.json"),
            "identity": reference(spec["identity_path"]), "admin": {"socket_path": str(short / "admin.sock")},
            "unit": spec["unit"], "invocation_id": unit["InvocationID"], "cgroup": unit["ControlGroup"],
            "session_protocol": "mp-interleave-v1", "maximum_sessions": 2,
            "owner_entrypoint": spec["owner_entrypoint"], "kernel_runtime": kernel})
        atomic_write(root / "status.json", json_bytes({"status": "ready_for_six_request_qualification",
            "source_spec": spec_ref, "ready": reference(spec["ready_path"]), "formal_admission": False}))
        return owner.wait()
    finally:
        # This block runs only on explicit shutdown or a launcher failure. It
        # never signals another unit or previous resident, only own children.
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=20)


if __name__ == "__main__":
    sys.exit(main())
