"""Wait up to six hours for capacity for the sole unused original model-5."""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import signal
import subprocess
import threading
import time

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim import software_benchmark_ref_resident_v066 as resident
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT = policy.ROOT
RUN_ROOT = ROOT / "runs/software-benchmark-v074/model5-capacity-watch-r1"
ARTIFACTS = ROOT / "artifacts/software-benchmark-v074/capacity-watcher-r1"
AUTH = ARTIFACTS / "authorization.json"
SPEC = ARTIFACTS / "unit.json"
UNIT = "proworksim-v074-model5-watcher.service"
VERSION = "v074-six-hour-original-model5-capacity-watcher-r1"
LAUNCHER = ROOT / "tools/launch_additional_qwen_v073.py"
LAUNCHER_AUTH = ROOT / "artifacts/software-benchmark-v073/local-expansion-r1/authorization.json"
PRIMARY_ROOT = ROOT / "runs/software-benchmark-v068/recovery-r1/primary-coordinator"
CLAIM = RUN_ROOT / "capacity-claim.json"
LEASE = policy.BATCH_ROOT / "resource-claims/active-v074-capacity-watcher.json"
RELEASE = RUN_ROOT / "capacity-released.json"
INTERVAL_SECONDS = 60
MAX_SECONDS = 6 * 60 * 60
HEARTBEAT_MAX_AGE = 180
GIB = 1024**3


def ordinary_user():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Only the existing ordinary user manager may run this watcher")


def load(ref):
    return json.loads(checked(ref).read_bytes())


def affinity():
    result = policy.host_cpu_pool()[172:173]
    if len(result) != 1:
        raise ValueError("The declared one-CPU watcher partition is unavailable")
    return result


def model5_consumed():
    return ((resident.RUNS / "model-5").exists()
            or (policy.BATCH_ROOT / "resource-claims/model-5.json").exists())


def launcher():
    spec = importlib.util.spec_from_file_location("v074_sealed_capacity_launcher", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixed_spec():
    return {"version": VERSION, "unit": UNIT, "user_id": os.getuid(),
        "source": reference(__file__), "sealed_launcher": reference(LAUNCHER),
        "sealed_launcher_authority": reference(LAUNCHER_AUTH),
        "reporting_root": str(RUN_ROOT), "cpu_affinity": affinity(),
        "CPU": 1, "memory_GiB": 4, "swap_bytes": 0, "tasks_max": 64,
        "maximum_seconds": MAX_SECONDS, "interval_seconds": INTERVAL_SECONDS,
        "restart": "no", "model_index": 5,
        "existing_units_signalled": False, "primary_model_lifecycle_owned": False}


def validate_spec(value):
    fixed = fixed_spec()
    if (set(value) != set(fixed) | {"ownership_token"}
            or any(value.get(key) != expected for key, expected in fixed.items())
            or len(value.get("ownership_token", "")) != 32
            or any(ch not in "0123456789abcdef" for ch in value["ownership_token"])):
        raise ValueError("The exact owned watcher specification changed")
    return value


def require_allowed():
    ordinary_user()
    policy.require_v066_allowed("v066.model.start")
    spec = validate_spec(load(reference(SPEC)))
    auth = load(reference(AUTH))
    if (auth.get("version") != VERSION or auth.get("status") != "approved"
            or auth.get("source") != reference(__file__)
            or auth.get("specification") != reference(SPEC)
            or auth.get("original_scope") != reference(policy.AUTHORIZATION_FILE)
            or auth.get("launcher_authority") != reference(LAUNCHER_AUTH)
            or auth.get("shared_CPU_memory_cap") != [152, 832]):
        raise PermissionError("Watcher capability authority or source binding changed")
    launcher().validate_authorization()
    return spec


def command(spec):
    validate_spec(spec)
    return ["systemd-run", "--user", "--collect", "--no-block", "--unit=" + UNIT,
        "--description=ProWorkSim v074 model5 capacity watcher " + spec["ownership_token"],
        "--setenv=PYTHONHOME=", "--setenv=PYTHONPATH=", "--setenv=LD_LIBRARY_PATH=", "--setenv=LD_PRELOAD=",
        "--property=Restart=no", "--property=KillMode=control-group", "--property=CPUQuota=100%",
        "--property=CPUAffinity=" + str(spec["cpu_affinity"][0]),
        "--property=MemoryMax=4G", "--property=MemorySwapMax=0", "--property=TasksMax=64",
        "--property=OOMPolicy=stop", "--property=RuntimeMaxSec=21600", "--property=TimeoutStopSec=120",
        "--property=WorkingDirectory=" + str(ROOT),
        "--property=StandardOutput=append:" + str(RUN_ROOT / "stdout.log"),
        "--property=StandardError=append:" + str(RUN_ROOT / "stderr.log"),
        str(ROOT / ".venv/bin/python"), "-B", str(ROOT / "tools/run_offline_scorer_v058.py"),
        str(Path(__file__).resolve()), "--execute"]


def prepare():
    """Seal files only. No GPU observation, reservation, or manager contact."""
    ordinary_user()
    policy.require_v066_allowed("v066.model.start")
    launcher().validate_authorization()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if SPEC.exists():
        spec = validate_spec(load(reference(SPEC)))
    else:
        spec = {**fixed_spec(), "ownership_token": secrets.token_hex(16)}
        write_new(SPEC, spec)
    if not AUTH.exists():
        write_new(AUTH, {"version": VERSION, "status": "approved", "prepared_unix": time.time(),
            "source": reference(__file__), "specification": reference(SPEC),
            "original_scope": reference(policy.AUTHORIZATION_FILE),
            "launcher_authority": reference(LAUNCHER_AUTH), "shared_CPU_memory_cap": [152, 832],
            "user_authorization": "中途其他显卡容量满足即可使用；仅原未消费model5，普通用户监控六小时",
            "existing_model4_restarted": False, "other_tasks_signalled": False,
            "resource_reservation": {"CPU": 1, "memory_GiB": 4, "within_original_pool": True}})
    require_allowed()
    return {"authorization": reference(AUTH), "specification": reference(SPEC),
            "command": command(spec), "GPU_queries": 0, "resources_reserved": 0, "services_started": 0}


def reserve_capacity():
    require_allowed()
    with (LEASE.parent / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CLAIM.exists() or RELEASE.exists() or LEASE.exists():
            raise ValueError("This watcher residency has already consumed its capacity identity")
        active = [load(reference(path)) for path in LEASE.parent.glob("active-*.json")]
        admission = policy._budget(active, 1, 4 * GIB)
        value = {"version": VERSION, "key": "v074-capacity-watcher",
            "spec": {"role": "auxiliary_capacity_watcher", "unit": UNIT}, "lane": None,
            "reserved_cpu": 1, "reserved_memory_bytes": 4 * GIB, "reserved_spool_bytes": 0,
            "admission": admission, "lease": str(LEASE), "authorization": reference(AUTH),
            "unit_specification": reference(SPEC), "cpu_affinity": affinity()}
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        data = policy._write_claim(CLAIM, value)
        with LEASE.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return reference(CLAIM)


def release_capacity(claim_ref):
    ordinary_user()
    if Path(claim_ref["path"]).resolve() != CLAIM.resolve():
        raise ValueError("Only this watcher claim may be released")
    value = load(claim_ref)
    if value.get("version") != VERSION or value.get("lease") != str(LEASE):
        raise ValueError("Foreign watcher capacity claim")
    with (LEASE.parent / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if RELEASE.exists():
            if load(reference(RELEASE)).get("claim") != claim_ref or LEASE.exists():
                raise ValueError("Released watcher capacity is not consistent")
            return reference(RELEASE)
        if not LEASE.exists() or LEASE.read_bytes() != checked(claim_ref).read_bytes():
            raise ValueError("Do not remove another resource's lease")
        result = write_new(RELEASE, {"version": VERSION, "claim": claim_ref,
            "quiescent": True, "other_resources_touched": False, "finished_unix": time.time()})
        LEASE.unlink()
        return result


def primary_decision(progress, cursor, *, now):
    if any(value.get("phase") in {"closed", "stopped", "stopping"} for value in (progress, cursor)):
        return "stop", "primary_ended"
    if progress.get("failure") is not None or cursor.get("failure") is not None:
        return "stop", "primary_shared_failure"
    if not cursor.get("pending_generation") and not cursor.get("active_generation"):
        return "stop", "primary_generation_finished"
    observed = progress.get("unix")
    if (not isinstance(observed, (int, float)) or not 0 <= now - observed <= HEARTBEAT_MAX_AGE
            or progress.get("phase") not in {"starting", "running", "waiting"}
            or cursor.get("phase") not in {"starting", "running", "waiting"}):
        return "wait", "primary_heartbeat_or_phase_not_healthy"
    return "attempt", "primary_generation_active_and_fresh"


def read_primary():
    try:
        progress = json.loads((PRIMARY_ROOT / "progress.json").read_bytes())
        cursor = json.loads((PRIMARY_ROOT / "cursor.json").read_bytes())
        decision, reason = primary_decision(progress, cursor, now=time.time())
        return {"decision": decision, "reason": reason, "progress_unix": progress.get("unix"),
                "progress_phase": progress.get("phase"), "cursor_phase": cursor.get("phase")}
    except (OSError, ValueError, TypeError) as error:
        return {"decision": "wait", "reason": "primary_observation_unavailable", "error": str(error)}


def monitor(*, consumed, observe_primary, attempt, stopped, record, clock=time.monotonic,
            maximum_seconds=MAX_SECONDS, interval_seconds=INTERVAL_SECONDS):
    """Pure injectable lifecycle: one model5 attempt per interval, no restarts."""
    started, attempts = clock(), 0
    while not stopped.is_set():
        if consumed():
            return {"reason": "model5_identity_consumed", "attempts": attempts}
        remaining = maximum_seconds - (clock() - started)
        if remaining <= 0:
            return {"reason": "six_hour_window_expired", "attempts": attempts}
        primary = observe_primary()
        if primary["decision"] == "stop":
            return {"reason": primary["reason"], "attempts": attempts}
        outcome = None
        if primary["decision"] == "attempt":
            outcome = attempt([5])
            attempts += 1
        record({"primary": primary, "outcome": outcome, "attempts": attempts,
                "remaining_seconds": max(0, maximum_seconds - (clock() - started))})
        if consumed():
            return {"reason": "model5_identity_consumed", "attempts": attempts}
        if outcome is not None:
            result = outcome.get("residents", {}).get("5", {})
            if result.get("status") not in {"waiting_for_capacity"}:
                return {"reason": "launcher_noncapacity_result_no_retry", "attempts": attempts, "outcome": outcome}
        remaining = maximum_seconds - (clock() - started)
        if remaining <= 0:
            return {"reason": "six_hour_window_expired", "attempts": attempts}
        stopped.wait(min(interval_seconds, remaining))
    return {"reason": "watcher_termination_requested", "attempts": attempts}


def verify_host_limits():
    paths = [line.split(":", 2)[2] for line in Path("/proc/self/cgroup").read_text().splitlines() if line.startswith("0::")]
    if len(paths) != 1 or PurePosixPath(paths[0]).name != UNIT or ".." in PurePosixPath(paths[0]).parts:
        raise PermissionError("Watcher must run in its exact ordinary-user unit")
    directory = Path("/sys/fs/cgroup") / paths[0].lstrip("/")
    observed = {name: (directory / name).read_text().strip() for name in ("memory.max", "memory.swap.max", "pids.max")}
    observed["cpu_affinity"] = sorted(os.sched_getaffinity(0))
    if (observed["memory.max"] != str(4 * GIB) or observed["memory.swap.max"] != "0"
            or observed["pids.max"] != "64" or observed["cpu_affinity"] != affinity()):
        raise ValueError("Watcher does not have its exact CPU/RAM/swap/PID limits")
    cpu = directory / "cpu.max"
    if cpu.exists():
        quota, period = cpu.read_text().strip().split()
        if not quota.isdigit() or not period.isdigit() or not 0 < int(quota) <= int(period):
            raise ValueError("Watcher CPU quota exceeds one CPU")
    return observed


def execute():
    claim_ref = reference(CLAIM)
    stopped = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stopped.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
    result = {"version": VERSION, "started_unix": time.time(), "existing_units_signalled": False}
    owns_capacity = False
    try:
        result["host_limits"] = verify_host_limits()
        if not LEASE.exists() or LEASE.read_bytes() != checked(claim_ref).read_bytes():
            raise ValueError("Watcher requires its exact live shared-pool reservation")
        owns_capacity = True
        require_allowed()
        write_new(RUN_ROOT / "execution-started.json", result)
        delegate = launcher()
        def record(value):
            atomic_write(RUN_ROOT / "progress.json", json_bytes({"version": VERSION, "unix": time.time(), **value}))
        result.update(monitor(consumed=model5_consumed, observe_primary=read_primary,
            attempt=delegate.launch, stopped=stopped, record=record))
        return result
    except Exception as error:
        result.update(reason="watcher_exception_no_retry", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        result["finished_unix"] = time.time()
        if owns_capacity:
            result["capacity_release"] = release_capacity(claim_ref)
            write_new(RUN_ROOT / "result.json", result)
        for sig, old in previous.items():
            signal.signal(sig, old)


def launch():
    spec = require_allowed()
    if model5_consumed():
        return {"status": "model5_already_consumed_watcher_not_started"}
    primary = read_primary()
    if primary["decision"] != "attempt":
        return {"status": "watcher_not_started_primary_not_healthy", "primary": primary}
    if (RUN_ROOT / "launch-intent.json").exists() or (RUN_ROOT / "execution-started.json").exists():
        raise ValueError("An entered watcher identity is not automatically restarted")
    env = resident.user_manager_environment()
    answer = subprocess.run(["systemctl", "--user", "show", UNIT, "--no-pager",
        "--property=ActiveState,MainPID"], env=env, capture_output=True, text=True, timeout=15)
    observed = dict(line.split("=", 1) for line in answer.stdout.splitlines() if "=" in line)
    if answer.returncode != 0 or observed.get("ActiveState") != "inactive" or observed.get("MainPID") != "0":
        raise ValueError("The exact watcher unit is not proved inactive")
    claim = reserve_capacity()
    argv = command(spec)
    write_new(RUN_ROOT / "launch-intent.json", {"version": VERSION, "specification": reference(SPEC),
        "authorization": reference(AUTH), "capacity_claim": claim, "command": argv,
        "primary_at_launch": primary, "inactive_unit_observation": observed})
    try:
        response = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30)
        result = {"returncode": response.returncode, "stdout": response.stdout, "stderr": response.stderr,
                  "unit": UNIT, "capacity_claim": claim, "launch_only_not_model_readiness": True}
    except Exception as error:
        result = {"unit": UNIT, "capacity_claim": claim, "status": "launch_outcome_unknown",
                  "error": {"type": type(error).__name__, "message": str(error)}}
    write_new(RUN_ROOT / "launch-result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--launch", action="store_true")
    actions.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else launch() if args.launch else execute(), ensure_ascii=False))
