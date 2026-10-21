"""GPU6 resident launcher: unchanged raw owner once, persistent allocator and physical lease."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402
from proworksim.software_benchmark_gpu_lease_v054 import GpuLease  # noqa: E402
from proworksim.software_benchmark_lease_handoff_v054 import _pidfd_open, _pidfd_kill  # noqa: E402
from proworksim.software_benchmark_match_v054 import CONTRACT  # noqa: E402
from proworksim.software_benchmark_service_factory_v054 import MODEL, capacity_admission  # noqa: E402
from proworksim.software_benchmark_supervision_v054 import process_identity  # noqa: E402
from proworksim.storage import digest, json_bytes  # noqa: E402


def wait_ready(path, process, timeout):
    until = time.monotonic() + timeout
    while not Path(path).exists():
        if process.poll() is not None or time.monotonic() >= until:
            raise RuntimeError("Persistent service failed before ready")
        time.sleep(.1)


def drain_registered_cgroup(group, unit):
    if (not group.startswith("/user.slice/") or not group.endswith("/" + unit)
            or ".." in group.split("/") or not re.fullmatch(r"proworksim-v054-resident-mp-r[0-9]+\.service", unit)):
        raise ValueError("Unexpected resident cgroup")
    while True:
        members = set()
        for path in Path("/sys/fs/cgroup" + group).rglob("cgroup.procs"):
            members.update(int(value) for value in path.read_text().split())
        members.discard(os.getpid())
        if not members:
            return
        for pid in members:
            try:
                descriptor = _pidfd_open(pid)
                try:
                    membership = Path(f"/proc/{pid}/cgroup").read_text().splitlines()
                    if any(line == "0::" + group or line.startswith("0::" + group + "/") for line in membership):
                        _pidfd_kill(descriptor)
                finally:
                    os.close(descriptor)
            except (FileNotFoundError, ProcessLookupError):
                pass
        time.sleep(.02)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    spec_ref = reference(args.spec)
    if spec_ref["sha256"] != args.sha256:
        raise ValueError("Resident startup specification changed")
    spec = json.loads(args.spec.read_text())
    if (spec["version"] != "v054-match-resident-spec-v1" or spec["card"]["index"] != 6
            or not re.fullmatch(r"proworksim-v054-resident-mp-r[0-9]+\.service", spec["unit"])):
        raise ValueError("Only the explicit GPU6 raw resident deployment is supported")
    unit = dict(line.split("=", 1) for line in subprocess.check_output([
        "systemctl", "--user", "show", spec["unit"], "--property=MainPID,InvocationID,ControlGroup"],
        text=True).splitlines())
    if int(unit["MainPID"]) != os.getpid() or not unit["ControlGroup"].endswith("/" + spec["unit"]):
        raise ValueError("Launcher must run in its exact dedicated persistent unit")
    for frozen in spec["sources"]:
        checked(frozen)
    capacity_admission("MATCH", spec["capacity_receipt"])
    from tools.prepare_model_capacity_v054 import eligible, gpu_rows, source_identity
    capacity = json.loads(checked(spec["capacity_receipt"]).read_text())
    if source_identity() != capacity["source"] or json.loads(checked(spec["contract"]).read_text()) != CONTRACT:
        raise ValueError("Original checkpoint identity or numerical contract differs")
    permit = json.loads(checked(spec["load_admission"]).read_text())
    if (permit.get("model_loading_authorized") is not True
            or permit["model_manifest"] != reference(MODEL / "proworksim-manifest.json")
            or permit["contract_sha256"] != digest(json_bytes(CONTRACT))):
        raise ValueError("A separate exact model loading permit is required")
    root, short = Path(spec["root"]).resolve(), Path(spec["short"]).resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v054") or not short.is_relative_to(ROOT / "runs/v054-gpu"):
        raise ValueError("Persistent artifacts must remain in the project runtime roots")
    root.mkdir(parents=True, exist_ok=True)
    write_new(root / "launcher-started.json", {"source_spec": spec_ref,
              "host_process": process_identity(os.getpid()), "automatic_restart": False})
    short.mkdir(parents=True, mode=0o700, exist_ok=True)
    cache = root / "cache"
    cache.mkdir()
    lease, children = None, []
    def stop(*_):
        raise SystemExit("Explicit resident shutdown")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        lease = GpuLease(spec["card"]["uuid"])
        card = next(card for card in eligible(gpu_rows(), "MATCH") if card["uuid"] == spec["card"]["uuid"])
        write_new(root / "gpu-lease.json", lease.receipt)
        binding = {"version": "software-learning-resources-v0.50-r3", "gpu_index": 6,
                   "gpu_uuid": card["uuid"], "sampled_free_mib": card["free_mib"],
                   "target_mib": min(73728, card["free_mib"] - 1024)}
        env = ["PYTHONPATH=" + str(ROOT / "src") + ":" + str(ROOT),
            "HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1", "HF_DATASETS_OFFLINE=1",
            "LITELLM_LOCAL_MODEL_COST_MAP=True", "VLLM_NO_USAGE_STATS=1", "DO_NOT_TRACK=1",
            "PYTORCH_CUDA_ALLOC_CONF=backend:native", "NO_PROXY=*", "no_proxy=*",
            "HTTP_PROXY=", "HTTPS_PROXY=", "ALL_PROXY=", "http_proxy=", "https_proxy=", "all_proxy=",
            "TMPDIR=" + str(cache), "XDG_CACHE_HOME=" + str(cache)]
        runtime = str(ROOT / "tools/run_benchmark_runtime_v054.sh")
        codec_identity = root / "codec-identity.json"
        codec = subprocess.Popen([runtime, "--write-project", "/usr/bin/env", *env,
            "CUDA_VISIBLE_DEVICES=", "NVIDIA_VISIBLE_DEVICES=void",
            str(ROOT / "runs/software-benchmark-v054/ref-venv/bin/python"),
            str(ROOT / "tools/serve_match_codec_v054.py"), "--model-local", str(MODEL),
            "--socket", str(short / "codec.sock"), "--identity-output", str(codec_identity)], start_new_session=True)
        children.append(codec)
        wait_ready(short / "codec.sock", codec, 180)
        owner = subprocess.Popen([runtime, "--write-project", "--gpu", "6", "/usr/bin/env", *env,
            "PROWORKSIM_V053_GPU_BINDING=" + json.dumps(binding),
            str(ROOT / "runs/v016-sdk/resident-venv/bin/python"),
            str(ROOT / "tools/serve_resident_owner_v054.py"), "--socket", str(short / "admin.sock"),
            "--model-local", str(MODEL), "--model-manifest", str(MODEL / "proworksim-manifest.json"),
            "--contract", spec["contract"]["path"], "--output", str(root / "owner-service"),
            "--identity-output", spec["identity_path"], "--verified-source-receipt",
            str(ROOT / "artifacts/software-panel-v053/model-source-receipt.json"),
            "--allow-gpu-load", "--load-admission", spec["load_admission"]["path"],
            *(["--resident-preparation-permit", str(checked(spec["preparation_permit"]))]
              if spec.get("preparation_permit") else []),
            "--codec-socket", str(short / "codec.sock"), "--codec-identity", str(codec_identity)], start_new_session=True)
        children.append(owner)
        wait_ready(root / "owner-service/service-ready.json", owner, 1800)
        write_new(spec["ready_path"], {"ready": True, "resident": True, "source_spec": spec_ref,
            "host_process": process_identity(os.getpid()), "gpu_index": 6, "gpu_uuid": card["uuid"],
            "gpu_lease_held": True, "identity": reference(spec["identity_path"]),
            "admin": {"socket_path": str(short / "admin.sock")}, "unit": spec["unit"],
            "invocation_id": unit["InvocationID"], "cgroup": unit["ControlGroup"]})
        return owner.wait()
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=15)
        drain_registered_cgroup(unit["ControlGroup"], spec["unit"])
        if lease is not None:
            lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
