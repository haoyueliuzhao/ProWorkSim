"""Prepare one admitted public checkout without importing any hidden dataset row."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_actor_v054 import (
    ActorDocker, admission, canonical, prepare_public_source, sha256,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-tasks", required=True, type=Path)
    parser.add_argument("--public-tasks-sha256", required=True)
    parser.add_argument("--image-inventory", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--docker-socket", required=True)
    parser.add_argument("--docker-cli", default="/usr/bin/docker")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public_bytes = args.public_tasks.read_bytes()
    if sha256(public_bytes) != args.public_tasks_sha256:
        raise ValueError("Public task projection differs from the fixed source receipt")
    rows = json.loads(public_bytes)
    if len(rows) != 500 or len({row["instance_id"] for row in rows}) != 500:
        raise ValueError("The complete public 500-task projection is required")
    task = next(row for row in rows if row["instance_id"] == args.instance_id)
    inventory = json.loads(args.image_inventory.read_bytes())
    image = next(row for row in inventory["images"] if row["instance_id"] == args.instance_id)
    preflight = json.loads(args.preflight.read_bytes())
    environment = admission(task, image, preflight, limits={
        "network": "none", "cpus": 4, "memory_bytes": 16 * 1024**3,
        "pids_limit": 16384, "public_test_timeout_seconds": 1800})
    controller = ActorDocker(args.docker_socket, cli=args.docker_cli)
    manifest = prepare_public_source(environment, controller, args.output)
    environment.update({
        "public_tasks_sha256": args.public_tasks_sha256,
        "image_inventory_sha256": sha256(args.image_inventory.read_bytes()),
        "source_manifest": str(manifest),
        "source_manifest_sha256": sha256(Path(manifest).read_bytes()),
        "public_test_entry_admitted": False,
        "all_three_arms_execution_ready": False,
    })
    (args.output / "environment.json").write_bytes(canonical(environment))
    print(json.dumps({
        "instance_id": args.instance_id, "public_source_prepared": True,
        "public_test_entry_admitted": False, "native_sdk_execution_admitted": False,
        "model_calls": 0}))


if __name__ == "__main__":
    main()
