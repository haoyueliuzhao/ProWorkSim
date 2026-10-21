"""Own model-service leases for its entire lifetime; no CUDA is imported here."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from proworksim.software_benchmark_capacity_guards_v054 import (  # noqa: E402
    check_seal, reference, require_monitor, unit_state, write,
)
from proworksim.software_benchmark_gpu_lease_v054 import GpuLease  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", required=True, type=Path)
    parser.add_argument("--launch-sha256", required=True)
    args = parser.parse_args()
    if reference(args.launch)["sha256"] != args.launch_sha256:
        raise ValueError("Model launch specification changed")
    launch = json.loads(args.launch.read_bytes())
    require_monitor(launch["monitor"]["unit"], invocation=launch["monitor"]["invocation_id"])
    own = unit_state(launch["unit"])
    if (int(own.get("MainPID", "0")) != os.getpid()
            or launch["monitor"]["unit"] not in own.get("BindsTo", "").split()
            or launch["monitor"]["unit"] not in own.get("After", "").split()):
        raise ValueError("Model lease wrapper is outside its registered bound service")
    if reference(launch["seal"]["path"]) != launch["seal"]:
        raise ValueError("Preparation seal reference changed")
    check_seal(json.loads(Path(launch["seal"]["path"]).read_bytes()))
    lock_root = ROOT / "runs/v054-gpu/locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    lease = process = None
    global_lock = (lock_root / "capacity-preparation-single-resident.lock").open("a+b")
    record = {"version": "v054-capacity-service-lease-v1", "unit": launch["unit"],
              "monitor": launch["monitor"], "model_command_started": False,
              "GPU_memory_allocated_by_lease": 0}

    def terminate(_signal, _frame):
        raise SystemExit(128 + _signal)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        fcntl.flock(global_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lease = GpuLease(launch["card"]["uuid"])
        from prepare_model_capacity_v054 import eligible, gpu_rows
        fresh = [row for row in gpu_rows() if row["uuid"] == launch["card"]["uuid"]]
        if (not eligible(fresh, launch["arm"])
                or fresh[0]["index"] != launch["card"]["index"]):
            raise RuntimeError("GPU no longer meets the original capacity threshold before model dispatch")
        record.update(status="leased", gpu_lease=lease.receipt,
                      global_preparation_lock=str(global_lock.name), maximum_preparation_residents=1,
                      observed_before_model_command=fresh[0])
        write(launch["lease_receipt"], record)
        process = subprocess.Popen(launch["command"], stdin=subprocess.DEVNULL)
        record.update(status="model_command_running", model_command_started=True, child_pid=process.pid)
        write(launch["lease_receipt"], record)
        return process.wait()
    except BaseException as error:
        record.update(status="failed_no_replay", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        record["direct_child_reaped"] = process is None or process.poll() is not None
        record["service_cgroup_quiescence_must_be_checked_by_monitor"] = True
        write(launch["lease_receipt"], record)
        if lease is not None:
            lease.close()
        global_lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
