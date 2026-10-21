"""Prepare the fixed CPU lookahead policy or run its one bounded worker."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_prewarm_v054 import ROOT, VERSION, Prewarmer, validate_prewarm_policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--source-manifest", type=Path, required=True)
    prepare.add_argument("--queue-state", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--policy", type=Path, required=True)
    run.add_argument("--sha256", required=True)
    run.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.operation == "prepare":
        root = args.output.resolve()
        if not root.is_relative_to(ROOT / "runs/software-benchmark-v054"):
            raise ValueError("CPU preparation metadata must remain in the project runs root")
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        policy = {"version": VERSION, "root": str(root),
            "workers": 1, "maximum_unused_prepared_tasks": 2,
            "minimum_disk_free_bytes": 64 * 1024**3,
            "source_manifest": reference(args.source_manifest),
            "queue_state_path": str(args.queue_state.resolve()),
            "cache_root": str(ROOT / "runs/software-benchmark-v054/native-lazy-cache"),
            "slots": reference(ROOT / "artifacts/software-benchmark-v054/manifests/slots.json"),
            "public_tasks": reference(ROOT / "artifacts/software-benchmark-v054/source/public-tasks.json"),
            "registry": reference(ROOT / "config/v054-public-test-registry.json"),
            "stdlib": str(ROOT / "runs/software-benchmark-v054/native-binding-control/r3/REF/control-stdlib"),
            "docker_socket": "unix://" + str(ROOT / "runs/software-panel-v053/docker/docker.sock"),
            "model_loading_authorized": False, "model_generation_authorized": False,
            "formal_claims_authorized": False, "hidden_grader_authorized": False,
            "automatic_retry_failed_preparation": False,
            "selection": "Original slot order, distinct pending tasks, max two prepared with no formal consumer",
            "runtime_revision": "cpu-native-prewarm-r1"}
        item = write_new(root / "policy.json", policy)
        validate_prewarm_policy(item)
        token = hashlib.sha256(str(root).encode()).hexdigest()[:8]
        argv = ["sudo", "-n", "systemd-run", "--unit=proworksim-v054-prewarm-" + token + ".service",
            "--uid=" + str(os.getuid()), "--gid=" + str(os.getgid()),
            "--property=Restart=no", "--property=KillMode=control-group", "--property=CPUQuota=400%",
            "--property=MemoryMax=16G", "--property=TasksMax=16384",
            "--property=WorkingDirectory=" + str(ROOT),
            "--property=StandardOutput=append:" + str(root / "stdout.log"),
            "--property=StandardError=append:" + str(root / "stderr.log"),
            "--setenv=PYTHONPATH=" + str(ROOT / "src") + ":" + str(ROOT),
            "--setenv=CUDA_VISIBLE_DEVICES=", "--setenv=NVIDIA_VISIBLE_DEVICES=void",
            str(ROOT / ".venv/bin/python"), str(ROOT / "tools/run_prewarm_v054.py"),
            "run", "--policy", item["path"], "--sha256", item["sha256"]]
        launch = write_new(root / "launch.json", {"policy": item, "argv": argv,
            "automatic_start": False, "GPU_loads": 0, "formal_claims": 0})
        print(json.dumps({"policy": item, "launch": launch}))
        return 0
    item = reference(args.policy)
    if item["sha256"] != args.sha256:
        raise ValueError("CPU preparation policy changed")
    return Prewarmer(item).run(once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
