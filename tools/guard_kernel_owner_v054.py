"""Preload one successor process, retain a small buffer, then load once after exact retirement.

This entry point never signals the previous resident. A host operator supplies
the separately frozen release evidence only after a single-card idle boundary.
CUDA memory handoff between processes is explicitly not atomic.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import runpy
import signal
import sys
import time


def physical_card_from_runtime(rows, plan, *, environ=None):
    """Bind namespace-local NVML enumeration to the frozen host UUID/index."""
    environ = os.environ if environ is None else environ
    if (plan.get("gpu_index") != 6
            or environ.get("CUDA_VISIBLE_DEVICES") != plan["gpu_uuid"]
            or environ.get("PROWORKSIM_HOST_GPU_DEVICES") != "6"):
        raise ValueError("Runtime visibility differs from the frozen physical GPU6 identity")
    matched = [row for row in rows if row.get("uuid") == plan["gpu_uuid"]]
    if len(matched) != 1:
        raise ValueError("Exactly one runtime NVML row must match the physical GPU UUID")
    observed = matched[0]
    if (type(observed.get("index")) is not int or not 0 <= observed["index"] < 8
            or observed.get("name") != "NVIDIA A800-SXM4-80GB"
            or type(observed.get("total_mib")) is not int or observed["total_mib"] < 81920
            or type(observed.get("free_mib")) is not int
            or not 0 <= observed["free_mib"] <= observed["total_mib"]):
        raise ValueError("Runtime GPU model, memory or NVML index is invalid")
    return {**observed, "index": plan["gpu_index"]}, dict(observed)


def validate_failed_predecessor_exit(previous_ref, previous, evidence):
    if (previous.get("version") != "v054-kernel-previous-failed-preparation-r3"
            or previous.get("one_additional_model_load_authorized") is not True
            or previous.get("maximum_additional_model_loads") != 1
            or previous.get("automatic_retry") is not False
            or previous.get("unit") != "proworksim-v054-resident-mp-g6-kernel-r5.service"
            or previous.get("protocol_revision_only") is not True
            or previous.get("kernel_implementation_unchanged") is not True
            or previous.get("original_failure_reclassified_as_pass") is not False
            or previous.get("prior_completed_generation_requests") != 2
            or previous.get("prior_known_actual_tokens") != 384
            or previous.get("cumulative_preparation_generation_upper_bound") != 97792
            or evidence.get("previous_failed_preparation") != previous_ref
            or evidence.get("unit") != previous["unit"]
            or evidence.get("invocation_id") != previous["invocation_id"]
            or evidence.get("cgroup") != previous["cgroup"]
            or not all(evidence.get(key) is True for key in (
                "unit_stopped", "cgroup_empty", "launcher_gone", "guard_gone"))):
        raise ValueError("No exact complete exit proof for the immediate failed predecessor")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args()
    from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
    from proworksim.software_benchmark_gpu_lease_v054 import GpuLease
    from proworksim.software_benchmark_supervision_v054 import process_identity
    from proworksim.software_benchmark_deployment_gpu_v054 import raw_owner_resource_binding
    from tools.prepare_model_capacity_v054 import gpu_rows
    from proworksim.storage import atomic_write, json_bytes
    plan_ref = reference(args.plan)
    if plan_ref["sha256"] != args.plan_sha256:
        raise ValueError("Successor guard plan changed")
    plan = json.loads(checked(plan_ref).read_bytes())
    if (plan.get("version") != "v054-kernel-owner-guard-r1" or plan.get("gpu_index") != 6
            or plan.get("initial_buffer_mib") != 512 or plan.get("maximum_load_attempts") != 1
            or plan.get("formal_model_calls_before_qualification") != 0
            or plan.get("cross_process_memory_handoff_atomic") is not False
            or os.environ.get("CUDA_VISIBLE_DEVICES") != plan["gpu_uuid"]
            or os.environ.get("PROWORKSIM_HOST_GPU_DEVICES") != "6"
            or os.environ.get("PYTORCH_CUDA_ALLOC_CONF") != "backend:native"):
        raise ValueError("Only the explicit GPU6 single-boundary successor is supported")
    for field in ("old_registration", "old_ready", "kernel_plan", "owner_entrypoint", "source_manifest"):
        checked(plan[field])
    ready = json.loads(checked(plan["old_ready"]).read_bytes())
    if ready["gpu_uuid"] != plan["gpu_uuid"] or ready["gpu_index"] != 6:
        raise ValueError("Predecessor physical device differs")
    root = Path(plan["output"])
    root.mkdir(parents=True, exist_ok=True)
    started = write_new(root / "guard-started.json", {"plan": plan_ref,
        "host_process": process_identity(os.getpid()), "model_load_started": False,
        "model_calls": 0, "automatic_retry": False})
    lease, buffer, model_started = None, None, False
    try:
        # Imports, module initialization and this small buffer all precede old
        # owner termination. The caller must already have suppressed GPU6 slots.
        import torch
        if torch.cuda.device_count() != 1:
            raise ValueError("Guard must see exactly the selected physical GPU")
        free, _ = torch.cuda.mem_get_info()
        card, runtime_observed = physical_card_from_runtime(gpu_rows(), plan)
        if free < 768 * 1024**2:
            raise RuntimeError("Insufficient room for the bounded successor buffer")
        buffer = torch.empty((512 * 1024**2,), dtype=torch.uint8, device="cuda")
        write_new(root / "preloaded.json", {"plan": plan_ref, "started": started,
            "host_process": process_identity(os.getpid()), "buffer_mib": 512,
            "free_before_bytes": free, "model_loads": 0, "model_calls": 0,
            "physical_gpu_index": card["index"], "runtime_nvml_index": runtime_observed["index"],
            "runtime_gpu_observation": runtime_observed,
            "cross_process_memory_handoff_atomic": False})
        until = time.monotonic() + plan.get("release_wait_seconds", 7200)
        release_path = Path(plan["release_path"])
        while not release_path.is_file():
            if time.monotonic() >= until:
                raise TimeoutError("Explicit single-resident release evidence did not arrive")
            time.sleep(.05)
        release_ref = reference(release_path)
        release = json.loads(checked(release_ref).read_bytes())
        if (release.get("version") != "v054-kernel-predecessor-release-r1"
                or release.get("guard_plan") != plan_ref
                or release.get("old_registration") != plan["old_registration"]
                or release.get("old_ready") != plan["old_ready"]
                or not all(release.get(key) is True for key in (
                    "no_active_target_episodes", "old_sessions_idle", "old_unit_stopped",
                    "old_cgroup_empty", "old_launcher_gone"))):
            raise ValueError("No exact successor release authorization")
        group = Path("/sys/fs/cgroup" + ready["cgroup"])
        if group.exists() and any(path.read_text().strip() for path in group.rglob("cgroup.procs")):
            raise ValueError("Predecessor cgroup still contains processes")
        try:
            if process_identity(ready["host_process"]["pid"]) == ready["host_process"]:
                raise ValueError("Predecessor launcher is still present")
        except (ProcessLookupError, FileNotFoundError):
            pass
        if plan.get("previous_failed_preparation") is not None:
            previous_ref = plan["previous_failed_preparation"]
            previous = json.loads(checked(previous_ref).read_bytes())
            if release.get("previous_failed_preparation") != previous_ref:
                raise ValueError("Release omitted its immediate failed predecessor")
            evidence = json.loads(checked(release["immediate_failed_predecessor_exit"]).read_bytes())
            validate_failed_predecessor_exit(previous_ref, previous, evidence)
            for field in ("failure", "preparation_audit", "preparation_closure", "launcher", "preloaded", "unit_evidence"):
                checked(previous[field])
            immediate_group = Path("/sys/fs/cgroup" + previous["cgroup"])
            if immediate_group.exists() and any(path.read_text().strip()
                    for path in immediate_group.rglob("cgroup.procs")):
                raise ValueError("Immediate failed predecessor cgroup still contains processes")
            for field in ("host_process", "guard_host_process"):
                try:
                    if process_identity(previous[field]["pid"]) == previous[field]:
                        raise ValueError("Immediate failed predecessor process is still present")
                except (ProcessLookupError, FileNotFoundError):
                    pass
        # Reuse the original physical UUID and global leases. A race is a
        # recorded fault, never a second model load or another device fallback.
        lease = GpuLease(plan["gpu_uuid"])
        card, runtime_observed = physical_card_from_runtime(gpu_rows(), plan)
        if card["free_mib"] < 46080:
            raise RuntimeError("Original free-capacity gate lost during the non-atomic handoff")
        binding = raw_owner_resource_binding(card)
        del buffer
        gc.collect()
        # Dropped small buffer remains reusable native allocator cache. The
        # original owner main performs r5 acquire_startup in this same process.
        os.environ["PROWORKSIM_V053_GPU_BINDING"] = json.dumps(binding)
        write_new(root / "gpu-lease.json", {"plan": plan_ref, "release": release_ref,
            "lease": lease.receipt, "binding": binding, "host_process": process_identity(os.getpid()),
            "physical_gpu_index": card["index"], "runtime_nvml_index": runtime_observed["index"],
            "runtime_gpu_observation": runtime_observed})
        entry = checked(plan["owner_entrypoint"])
        kernel = checked(plan["kernel_plan"])
        argv = plan["owner_arguments"]
        if (not isinstance(argv, list) or not all(isinstance(value, str) for value in argv)
                or "--allow-gpu-load" not in argv or "--kernel-plan" in argv):
            raise ValueError("Exact original owner argv is required")
        write_new(root / "load-intent.json", {"plan": plan_ref, "binding": binding,
            "old_memory_handoff_atomic": False, "automatic_retry": False, "model_load_attempt": 1})
        model_started = True
        sys.argv = [str(entry), "--kernel-plan", str(kernel), "--kernel-plan-sha256",
                    plan["kernel_plan"]["sha256"], *argv]
        runpy.run_path(str(entry), run_name="__main__")
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as error:
        atomic_write(root / "failure.json", json_bytes({"plan": plan_ref,
            "status": "failed_manual_action_required", "model_load_started": model_started,
            "model_calls": None if model_started else 0, "automatic_retry": False,
            "GPU_allocation_retained_until_explicit_stop": True,
            "error": {"type": type(error).__name__, "message": str(error)}}))
        # No further CUDA calls after an allocator/kernel error. Keep the exact
        # process and any allocation/lease until the operator explicitly stops it.
        while True:
            signal.pause()
    finally:
        if lease is not None:
            lease.close()


if __name__ == "__main__":
    main()
