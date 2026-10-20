"""Prepare one native rootfs from a locally loaded, admitted immutable image.

This exports a disposable stopped container. It starts no repository process,
installs no SDK packages in the task filesystem, and never downloads an image.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_actor_v054 import ActorDocker, admission, sha256
from proworksim.software_benchmark_native_rootfs_v054 import prepare_rootfs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-tasks", required=True, type=Path)
    parser.add_argument("--public-tasks-sha256", required=True)
    parser.add_argument("--image-inventory", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--image-config-blob", required=True, type=Path)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--docker-socket", required=True)
    parser.add_argument("--docker-cli", default="/usr/bin/docker")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    public_bytes = args.public_tasks.read_bytes()
    if sha256(public_bytes) != args.public_tasks_sha256:
        raise ValueError("Public task projection differs from its frozen source receipt")
    rows = json.loads(public_bytes)
    if len(rows) != 500 or len({row["instance_id"] for row in rows}) != 500:
        raise ValueError("The complete 500-task public projection is required")
    task = next(row for row in rows if row["instance_id"] == args.instance_id)
    inventory = json.loads(args.image_inventory.read_bytes())
    image = next(row for row in inventory["images"] if row["instance_id"] == args.instance_id)
    environment = admission(
        task, image, json.loads(args.preflight.read_bytes()), limits={
            "network": "none", "cpus": 4, "memory_bytes": 16 * 1024**3,
            "pids_limit": 16384, "public_test_timeout_seconds": 1800})
    environment.update(
        public_tasks_sha256=args.public_tasks_sha256,
        image_inventory_sha256=sha256(args.image_inventory.read_bytes()))
    manifest = prepare_rootfs(
        environment=environment,
        controller=ActorDocker(args.docker_socket, cli=args.docker_cli),
        config_blob=args.image_config_blob, destination=args.output)
    print(json.dumps({
        "instance_id": args.instance_id, "rootfs_manifest": str(manifest),
        "rootfs_manifest_sha256": sha256(manifest.read_bytes()),
        "image_export_prepared": True, "native_real_task_control_passed": False,
        "numeric_ownership_equivalence_admitted": False,
        "native_execution_admitted": False, "model_calls": 0,
    }))


if __name__ == "__main__":
    main()
