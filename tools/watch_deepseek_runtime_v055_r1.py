"""Bounded, read-only runtime samples; never dispatch jobs or call a model."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/software-benchmark-v055"
CST = timezone(timedelta(hours=8))


def sample(previous_cpu):
    raw = (RUN / "queue-r1/state.json").read_bytes()
    state = json.loads(raw)
    generation = Counter(row["generation"]["status"] for row in state["rows"])
    scores = Counter(score["status"] for row in state["rows"] for score in row["scores"])
    active = [row["generation"] for row in state["rows"] if row["generation"]["status"] == "running"]
    devices, roots, missing = Counter(), Counter(), 0
    for item in active:
        directory = Path(item["directory"])
        try:
            devices[str(directory.stat().st_dev)] += 1
            rootfs = directory / "episode/actor/rootfs"
            if rootfs.is_dir():
                roots[str(rootfs.stat().st_dev)] += 1
        except FileNotFoundError:
            missing += 1
    live = Counter()
    if active:
        result = subprocess.run(["systemctl", "--user", "show",
            *(item["unit"] for item in active), "-p", "Id", "-p", "ActiveState", "-p", "MainPID"],
            capture_output=True, text=True, timeout=10, check=True)
        for block in result.stdout.strip().split("\n\n"):
            values = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
            live[values.get("ActiveState", "unknown")] += 1
    with sqlite3.connect((RUN / "budget-r1/ledger.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=2) as db:
        db.execute("PRAGMA query_only=ON")
        api_status = dict(db.execute("SELECT status,COUNT(*) FROM requests GROUP BY status"))
        settled, holds = db.execute("""SELECT SUM(COALESCE(settled_nanoyuan,0)),
            SUM(CASE WHEN status IN ('reserved','uncertain') THEN reserved_nanoyuan ELSE 0 END)
            FROM requests""").fetchone()
        failure_statuses = {str(status): count for status, count in db.execute("""
            SELECT json_extract(failure_json,'$.http_status'),COUNT(*) FROM requests
            WHERE failure_json IS NOT NULL GROUP BY json_extract(failure_json,'$.http_status')""")}
    memory = {key: int(value.split()[0]) * 1024 for key, value in (
        line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())}
    cpu = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:9]))
    cpu_cores = None
    if previous_cpu is not None:
        delta = [current - prior for current, prior in zip(cpu, previous_cpu)]
        if sum(delta) > 0:
            cpu_cores = (sum(delta) - delta[3] - delta[4]) / sum(delta) * (os.cpu_count() or 1)
    volumes = {}
    for name, path in (("primary", ROOT), ("secondary", RUN / "secondary-volume-r1")):
        volumes[name] = {"device": path.stat().st_dev, "free_bytes": shutil.disk_usage(path).free}
    budget, capacity = state.get("budget", {}), state.get("capacity", {})
    disk = state.get("disk_reservation_status", {})
    reserved = {name: volume.get("active_peak_reserved_bytes")
                for name, volume in disk.get("volumes", {}).items()}
    now = datetime.now(timezone.utc)
    row = {"observed_cst": now.astimezone(CST).isoformat(), "state_updated_utc": state["updated_utc"],
        "state_age_seconds": (now - datetime.fromisoformat(state["updated_utc"])).total_seconds(),
        "state_sha256": hashlib.sha256(raw).hexdigest(),
        "host_revision": state.get("active_host_revision"), "generation": dict(generation),
        "official_scoring_all_endpoints": dict(scores), "worker_units": dict(live),
        "active_job_devices": dict(devices), "active_rootfs_devices": dict(roots),
        "missing_active_job_directories": missing,
        "desired_generation_concurrency": capacity.get("desired_generation_concurrency"),
        "load_average": os.getloadavg(), "memory_available_bytes": memory["MemAvailable"],
        "host_cpu_busy_cores_interval": cpu_cores, "host_cpu_count": os.cpu_count(),
        "volumes": volumes, "volume_reserved_bytes": reserved,
        "disk_metadata_error": disk.get("metadata_error"),
        "API_status_counts": api_status, "API_failure_http_status_counts": failure_statuses,
        "API_429_count": failure_statuses.get("429", 0),
        "settled_conservative_cny": (settled or 0) / 1e9,
        "committed_conservative_cny": ((settled or 0) + (holds or 0)) / 1e9,
        "API_halted": budget.get("halted"), "API_cooldown_until_utc": budget.get("cooldown_until_utc"),
        "API_admission_wait_seconds": budget.get("admission_wait_seconds"),
        "dispatch_stopped": state.get("dispatch_stopped"), "stop_reason": state.get("stop_reason"),
        "exception_reason_counts": dict(Counter(item.get("reason", item.get("kind", "unknown"))
                                                for item in state.get("exceptions", []))),
        "preparing": sum(item.get("worker", {}).get("status") == "running"
                         for item in state.get("preparation", {}).values()),
        "source_messages_scores_and_account_balance_read": False}
    return row, cpu


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    output = args.output.resolve()
    if (not output.is_relative_to(RUN) or not 60 <= args.duration_seconds <= 3600
            or not 10 <= args.interval_seconds <= 60):
        raise ValueError("Only a bounded project monitor is allowed")
    output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).read_bytes()
    (output / "started.json").write_text(json.dumps({"started_cst": datetime.now(CST).isoformat(),
        "pid": os.getpid(), "source_sha256": hashlib.sha256(source).hexdigest(),
        "duration_seconds": args.duration_seconds, "interval_seconds": args.interval_seconds,
        "read_only_inputs": True, "model_calls": 0, "job_dispatches": 0}, indent=2) + "\n")
    start, previous_cpu, count = time.monotonic(), None, 0
    fields = ["observed_cst", "closed", "technical_unknown", "running", "pending", "target",
              "primary_jobs", "secondary_jobs", "API_inflight", "API_429", "load_1m",
              "memory_available_bytes", "primary_free_bytes", "secondary_free_bytes", "API_halted"]
    with (output / "samples.jsonl").open("x", buffering=1) as stream, (output / "samples.csv").open("x", newline="") as table:
        writer = csv.DictWriter(table, fieldnames=fields)
        writer.writeheader()
        while True:
            try:
                row, previous_cpu = sample(previous_cpu)
                row["elapsed_seconds"] = time.monotonic() - start
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                devices, g = row["active_job_devices"], row["generation"]
                writer.writerow({"observed_cst": row["observed_cst"],
                    **{key: g.get(key, 0) for key in ("closed", "technical_unknown", "running", "pending")},
                    "target": row["desired_generation_concurrency"],
                    "primary_jobs": devices.get(str(row["volumes"]["primary"]["device"]), 0),
                    "secondary_jobs": devices.get(str(row["volumes"]["secondary"]["device"]), 0),
                    "API_inflight": row["API_status_counts"].get("reserved", 0), "API_429": row["API_429_count"],
                    "load_1m": row["load_average"][0], "memory_available_bytes": row["memory_available_bytes"],
                    "primary_free_bytes": row["volumes"]["primary"]["free_bytes"],
                    "secondary_free_bytes": row["volumes"]["secondary"]["free_bytes"],
                    "API_halted": row["API_halted"]})
                table.flush()
                count += 1
                print(json.dumps({"sample": count, "time": row["observed_cst"], "generation": g,
                                  "devices": devices, "API_halted": row["API_halted"]}), flush=True)
            except Exception as error:
                stream.write(json.dumps({"observed_cst": datetime.now(CST).isoformat(),
                    "monitor_error_type": type(error).__name__, "error": str(error),
                    "queue_or_workers_modified": False}) + "\n")
            left = args.duration_seconds - (time.monotonic() - start)
            if left <= 0:
                break
            time.sleep(min(args.interval_seconds, left))
    (output / "finished.json").write_text(json.dumps({"finished_cst": datetime.now(CST).isoformat(),
        "samples": count, "elapsed_seconds": time.monotonic() - start, "automatic_stop": True,
        "model_calls": 0, "job_dispatches": 0}, indent=2) + "\n")


if __name__ == "__main__":
    main()
