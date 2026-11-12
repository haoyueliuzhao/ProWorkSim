"""Network boundaries for the independent DeepSeek evaluation.

The trusted client connects directly to the official TLS endpoint. Repository
commands stay in the existing private network/PID/mount namespace, without any
host credential, model client, Docker socket or network interface other than lo.
This module does not change host networking or other experiments' environments.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import time

VERSION = "v055-independent-direct-network-r1"
PROXY_NAMES = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


def direct_environment_command(command):
    """Explicit per-child settings, with no global environment mutation."""
    return ["/usr/bin/env", *[part for name in PROXY_NAMES for part in ("-u", name)],
            "NO_PROXY=*", "no_proxy=*", "PYTHON_DOTENV_DISABLED=1", *map(str, command)]


def validate_actor_ready(ready):
    isolation = ready.get("isolation", {})
    if (ready.get("type") != "ready" or isolation.get("pid") != 1
            or isolation.get("network_interfaces") != ["lo"]
            or isolation.get("capabilities_all_zero") is not True
            or isolation.get("no_new_privileges") is not True
            or isolation.get("dumpable") is not False
            or isolation.get("private_proc_pid1_root") != "/"
            or isolation.get("nvidia_nodes") != []):
        raise ValueError("Actor must have private PID/root/network, loopback only and no capabilities")
    if ready.get("rootfs_binding", {}).get("official_task_admitted") is not True:
        raise ValueError("Actor rootfs lacks existing official-image qualification")
    if any(ready.get("trusted_preload_counters", {}).get(key) != 0 for key in
           ("network_attempts", "weight_files_opened", "gpu_device_opens")):
        raise ValueError("Actor preload attempted forbidden host resource access")
    return {"version": VERSION, "actor_network": "private_netns_loopback_only",
            "actor_credentials": "environment_cleared_and_host_root_not_mounted",
            "model_route": "trusted_host_direct_tls_api.deepseek.com:443",
            "reverse_proxy": False, "search_tool": False,
            "actor_remote_search": "blocked_by_network_namespace"}


@contextmanager
def resource_semaphore(root, *, name, capacity, deadline=None, cancelled=None):
    """Crash-released, cross-process limiter; contention is waiting, not failure."""
    if not name.isidentifier() or type(capacity) is not int or capacity < 1:
        raise ValueError("Invalid shared resource semaphore")
    root = Path(root) / name
    root.mkdir(parents=True, exist_ok=True)
    held = None
    try:
        while held is None:
            if cancelled is not None and cancelled():
                raise RuntimeError("Episode closed while waiting for public-test capacity")
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Episode ended while waiting for public-test capacity")
            for index in range(capacity):
                stream = (root / str(index)).open("a")
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    stream.close()
                else:
                    held = stream
                    break
            if held is None:
                time.sleep(0.2)
        yield
    finally:
        if held is not None:
            held.close()


def host_capacity(*, maximum_load=140, reserve_memory_bytes=128 * 1024**3):
    """Read-only dispatch backpressure, in addition to per-episode cgroup limits."""
    memory = {line.split(":", 1)[0]: int(line.split()[1]) * 1024
              for line in Path("/proc/meminfo").read_text().splitlines()
              if line.startswith(("MemAvailable:", "MemTotal:"))}
    load = os.getloadavg()[0]
    return {"admit": load < maximum_load and memory["MemAvailable"] > reserve_memory_bytes,
            "load_1m": load, "memory_available_bytes": memory["MemAvailable"],
            "maximum_load_1m": maximum_load, "reserve_memory_bytes": reserve_memory_bytes}


def concurrency_limits(*, cpu_count, memory_available_bytes, legacy_generations, legacy_graders,
                       configured_generation=32, configured_scoring=4, api_concurrency=64,
                       current_generations=0):
    """Pure dispatch arithmetic; changes to capacity never kill an active worker."""
    integers = (cpu_count, memory_available_bytes, legacy_generations, legacy_graders,
                configured_generation, configured_scoring, api_concurrency, current_generations)
    if any(type(value) is not int or value < 0 for value in integers):
        raise ValueError("Nonnegative integral resource observations are required")
    worker_cpu, worker_ram = 4, 16 * 1024**3
    system_cpu, memory_reserve = 24, 128 * 1024**3
    reserved_scoring_cpu = 4 * worker_cpu
    legacy_cpu = worker_cpu * (legacy_generations + legacy_graders)
    cpu_capacity = max(0, (cpu_count - system_cpu - legacy_cpu - reserved_scoring_cpu) // worker_cpu)
    ram_capacity = max(0, (memory_available_bytes - memory_reserve) // worker_ram - 4)
    generation = min(32, configured_generation, api_concurrency, cpu_capacity, ram_capacity)
    scoring_cpu_capacity = max(0, (cpu_count - system_cpu - legacy_cpu
                                  - current_generations * worker_cpu) // worker_cpu)
    scoring_ram_capacity = max(0, (memory_available_bytes - memory_reserve) // worker_ram)
    scoring = min(4, configured_scoring, scoring_cpu_capacity, scoring_ram_capacity)
    return {"cpu_count": cpu_count, "system_cpu_reserved": system_cpu,
        "legacy_active_generations": legacy_generations, "legacy_active_graders": legacy_graders,
        "legacy_cpu_reserved": legacy_cpu, "scoring_cpu_reserved_for_generation_admission": reserved_scoring_cpu,
        "per_worker_cpu": worker_cpu, "per_worker_memory_bytes": worker_ram,
        "memory_reserve_bytes": memory_reserve, "available_memory_bytes": memory_available_bytes,
        "generation_cpu_capacity": cpu_capacity, "generation_ram_capacity": ram_capacity,
        "configured_generation_maximum": configured_generation, "hard_generation_maximum": 32,
        "global_API_concurrency": api_concurrency, "desired_generation_concurrency": generation,
        "desired_scoring_concurrency": scoring, "current_generation_workers": current_generations,
        "existing_workers_terminated_when_capacity_drops": False,
        "memory_gate_conservatively_counts_existing_worker_memory_again": True}


def disk_admission(free_bytes):
    if type(free_bytes) is not int or free_bytes < 0:
        raise ValueError("Observed free disk bytes must be a nonnegative integer")
    return {"disk_free_bytes": free_bytes, "generation_disk_floor_bytes": 100 * 1024**3,
        "preparation_disk_floor_bytes": 128 * 1024**3,
        "generation_disk_admitted": free_bytes >= 100 * 1024**3,
        "preparation_disk_admitted": free_bytes >= 128 * 1024**3,
        "low_water_stops_existing_work_or_scoring": False,
        "old_cache_or_task_data_deleted": False}
