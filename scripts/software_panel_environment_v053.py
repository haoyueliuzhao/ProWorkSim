"""CPU-only outcome-blind admission of preselected SWE-smith repository groups."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from threading import Event

from proworksim.software_panel_docker_v053 import (
    qualify_repository, source_ref, validate_backend_baseline, write_new,
)
from proworksim.software_panel_v053 import canonical_bytes, sha256


def admit(config, inventory_path, output, *, workers=4, target_repositories=20,
          allow_pull=False):
    """Process fixed contiguous batches; retain all attempted source exclusions."""
    inventory_path = Path(inventory_path)
    inventory = json.loads(inventory_path.read_bytes())
    candidates = [row for row in inventory["repositories"]
                  if row["eligible_before_environment_check"]]
    records = []
    stop_event = Event()
    if not 1 <= workers <= 16:
        raise ValueError("Admission workers must be between 1 and 16")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(candidates), workers):
            batch = candidates[start:start + workers]
            futures = {
                pool.submit(qualify_repository, config, row, allow_pull=allow_pull,
                            stop_event=stop_event): row for row in batch
            }
            batch_records = {}
            for future in as_completed(futures):
                repository = futures[future]
                try:
                    record = future.result()
                except Exception as error:
                    stop_event.set()
                    record = {
                        "repository": repository["repository"], "admitted": None,
                        "status": "unresolved_common_system_fault", "qualified_task_ids": [],
                        "reason": f"{type(error).__name__}: {error}",
                        "candidate_task_ids": repository["candidate_task_ids"],
                    }
                batch_records[repository["repository"]] = record
                print(json.dumps({
                    "repository": repository["repository"],
                    "admitted": record["admitted"], "reason": record["reason"],
                    "qualified_tasks": len(record["qualified_task_ids"]),
                    "status": record["status"],
                    "admitted_repositories_so_far": sum(
                        row["admitted"] is True
                        for row in records + list(batch_records.values())),
                }), flush=True)
            records.extend(batch_records[row["repository"]] for row in batch)
            if stop_event.is_set() or sum(row["admitted"] is True for row in records) >= target_repositories:
                break
    value = {
        "version": "software-panel-environment-v053-v1",
        "inventory": source_ref(inventory_path),
        "inventory_sha256": sha256(canonical_bytes(inventory)),
        "config_sha256": sha256(canonical_bytes(config)), "model_runs_started": 0,
        "repositories": records,
        "admitted_repository_count": sum(row["admitted"] is True for row in records),
        "target_repository_count": target_repositories,
        "ready_to_freeze": (
            not stop_event.is_set() and sum(row["admitted"] is True for row in records) >= 20),
        "paused_common_system_fault": stop_event.is_set(),
        "sampling": "fixed repository order; all ten preselected tasks required",
        "selection_uses_model_results": False, "training_started": False,
    }
    write_new(output, value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--inventory")
    parser.add_argument("--output", required=True)
    parser.add_argument("--control-task-id")
    parser.add_argument("--control-root")
    parser.add_argument("--workers", "--max-workers", dest="workers", type=int, default=4)
    parser.add_argument("--target-repositories", type=int, default=20)
    parser.add_argument("--allow-image-pull", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_bytes())
    if args.control_task_id:
        if not args.control_root:
            parser.error("--control-task-id requires --control-root")
        result = validate_backend_baseline(
            config, {"task_id": args.control_task_id}, args.control_root)
        write_new(args.output, result)
        print(json.dumps({"output": args.output, "passed": result["passed"],
                          "model_calls": result["model_calls"]}))
        return
    if not args.inventory:
        parser.error("--inventory is required for environment admission")
    result = admit(config, args.inventory, args.output, workers=args.workers,
                   target_repositories=args.target_repositories,
                   allow_pull=args.allow_image_pull)
    print(json.dumps({"output": args.output,
                      "ready_to_freeze": result["ready_to_freeze"],
                      "admitted_repository_count": result["admitted_repository_count"]}))


if __name__ == "__main__":
    main()
