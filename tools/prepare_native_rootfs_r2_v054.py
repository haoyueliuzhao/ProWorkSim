"""Export the admitted shared Actor image, preserving its original numeric owners."""
import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_actor_v054 import ActorDocker, checked_public_task
from proworksim.software_benchmark_native_rootfs_v054 import canonical, prepare_rootfs
from proworksim.software_benchmark_scorer_v054 import file_reference
from proworksim.software_benchmark_scorer_r4_v054 import validate_mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-tasks", required=True, type=Path)
    parser.add_argument("--public-tasks-sha256", required=True)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--mapping-sha256", required=True)
    parser.add_argument("--docker-socket", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (file_reference(args.public_tasks)["sha256"] != args.public_tasks_sha256
            or file_reference(args.mapping)["sha256"] != args.mapping_sha256):
        raise ValueError("Pinned public projection or baseline mapping changed")
    rows = json.loads(args.public_tasks.read_bytes())
    if len(rows) != 500 or len({row["instance_id"] for row in rows}) != 500:
        raise ValueError("Complete frozen 500 task public panel required")
    mapping = json.loads(args.mapping.read_bytes())
    task = checked_public_task(next(row for row in rows if row["instance_id"] == mapping["instance_id"]))
    validate_mapping(mapping, instance=task, image={
        "image_id": mapping["official_image_id"], "manifest_digest": mapping["official_manifest_digest"]})
    if task["image"] != mapping["official_image_name"]:
        raise ValueError("Task original image differs from baseline mapping")
    environment = {
        "version": "software-benchmark-actor-v054-r2", "task": task,
        "baseline_mapping": file_reference(args.mapping),
        "image": {"image_id": mapping["actor_image_id"],
                  "config_digest": mapping["actor_config_digest"], "manifest_digest": None,
                  "platform": mapping["platform"], "source": "local_derived_actor_image",
                  "official_source_manifest_digest": mapping["official_manifest_digest"]},
        "actor_head": mapping["actor_head"], "actor_tree": mapping["actor_tree"],
        "public_python": mapping["public_python"],
        "public_tasks_sha256": args.public_tasks_sha256,
        "limits": {"network": "none", "cpus": 4, "memory_bytes": 16 * 1024**3,
                   "pids_limit": 16384, "public_test_timeout_seconds": 1800},
        "official_grading_image_modified": False,
    }
    path = prepare_rootfs(
        environment=environment, controller=ActorDocker(args.docker_socket),
        config_blob=mapping["actor_config_blob"], destination=args.output,
        preserve_numeric_ownership=True)
    (args.output / "environment.json").write_bytes(canonical(environment))
    print(json.dumps({"rootfs_manifest": str(path), "numeric_ownership_prepared": True,
                      "actual_native_control_passed": False, "model_calls": 0}))


if __name__ == "__main__":
    main()
