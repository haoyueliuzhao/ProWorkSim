"""One real v056 Actor namespace/cleanup control, with zero model or grader calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from proworksim import software_benchmark_runner_v054 as host
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_network_v055 import validate_actor_ready
from proworksim.software_benchmark_owner_ipc_v054 import wire_json
from proworksim.software_benchmark_resources_v054 import create_episode_resources, release_episode_resources
from proworksim.software_benchmark_rootfs_v056 import clone_prepared_rootfs
from proworksim.software_benchmark_rootfs_io_v056 import cleanup_episode_rootfs
from proworksim.software_benchmark_supervision_v054 import (
    assert_outer_launcher_exited, claim_nonce, launch_owned, stop_owned,
)

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-receipt", type=Path, required=True)
    parser.add_argument("--stdlib", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "runs/software-benchmark-v056"):
        raise ValueError("New CPU controls require the v056 run namespace")
    output.mkdir(parents=True, exist_ok=False)
    preparation = json.loads(args.prepared_receipt.read_bytes())
    if (preparation.get("status") != "qualified" or preparation.get("slot_claimed") is not False
            or preparation.get("model_calls") != 0):
        raise ValueError("Consume an actual qualified, zero-model environment")
    environment = checked(preparation["rootfs_environment"])
    result = {"version": "v056-ref-actor-cpu-control-r1", "passed": False,
        "preparation": reference(args.prepared_receipt), "model_calls": 0, "GPU_loads": 0,
        "test_executions": 0, "grading_calls": 0, "formal_slot_claims": 0}
    resources = process = scope = None
    try:
        clone = clone_prepared_rootfs(environment, output / "actor")
        claim = claim_nonce()
        resources = create_episode_resources(claim, output)
        process, scope = launch_owned([
            str(ROOT / "tools/run_native_worker_mapped_v056.sh"),
            "--rootfs", clone["rootfs"], "--stdlib", str(args.stdlib.resolve()),
            "--environment-manifest", clone["environment_manifest"]],
            claim_id=claim, role="actor", resources=resources, runtime_seconds=180,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=(output / "worker.stderr").open("xb"))
        ready = host.read_frame(process.stdout, timeout=60)
        ready_ref = write_new(output / "worker-ready.json", ready)
        boundary = validate_actor_ready(ready)
        boundary.update(version="v056-ref-actor-cpu-control-r1", model_route="not_used")
        boundary_ref = write_new(output / "network-boundary.json", boundary)
        command = "printf 'v056-isolation-ok\\n'; test -d /testbed"
        process.stdin.write(wire_json({"id": 1, "tool": "terminal",
            "action": {"command": command, "timeout": 30}}))
        process.stdin.flush()
        response = host.read_frame(process.stdout, timeout=35)
        response_ref = write_new(output / "terminal-response.json", response)
        if response.get("observation", {}).get("exit_code") != 0 or "v056-isolation-ok" not in json.dumps(response):
            raise RuntimeError("The real isolated terminal control did not finish successfully")
        process.stdin.write(wire_json({"id": 2, "op": "close"}))
        process.stdin.flush()
        close_ref = write_new(output / "close-response.json", host.read_frame(process.stdout, timeout=10))
        stopped = stop_owned(scope)
        process.wait(timeout=20)
        assert_outer_launcher_exited(scope)
        quiet = write_new(output / "quiescence.json", {**stopped, "outer_launcher_reaped": True})
        cleanup = cleanup_episode_rootfs(clone["rootfs"], output,
            reference(clone["rootfs_manifest"]), quiet,
            [result["preparation"], ready_ref, boundary_ref, response_ref, close_ref])
        result.update(passed=True, isolation=ready["isolation"], rootfs_binding=ready["rootfs_binding"],
            original_numeric_ownership_preserved=True, cleanup=cleanup, quiescence=quiet,
            namespace_source=reference(ROOT / "tools/native_uid_bootstrap_v056.py"),
            worker_wrapper_source=reference(ROOT / "tools/run_native_worker_mapped_v056.sh"))
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if process is not None:
            try:
                stop_owned(scope)
                process.wait(timeout=20)
            except Exception as error:
                result.update(passed=False, final_stop_error=str(error))
        if resources is not None:
            try:
                result["resource_release"] = release_episode_resources(resources)
            except Exception as error:
                result.update(passed=False, resource_release_error=str(error))
        write_new(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "output": str(output),
                      **({"error": result["error"]} if "error" in result else {})}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
