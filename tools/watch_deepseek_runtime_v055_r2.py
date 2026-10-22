"""Independent read-only monitor with adjustment holds and direct ledger controls.

The earlier monitor remains unchanged. New exception reasons are recorded per
sample; no request/response messages or account credentials are read.
"""
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
    devices, roots, phases, missing = Counter(), Counter(), Counter(), 0
    for item in active:
        directory = Path(item["directory"])
        try:
            devices[str(directory.stat().st_dev)] += 1
            episode = directory / "episode"
            rootfs = episode / "actor/rootfs"
            ready = (episode / "controller-ready.json").is_file()
            phases["controller_ready" if ready else "pre_controller_ready"] += 1
            if (episode / "actor/public-environment.json").is_file():
                phases["main_clone_publication_present"] += 1
            if (episode / "controller-result.json").is_file():
                phases["controller_finished"] += 1
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
        db.execute("BEGIN")
        api_status = dict(db.execute("SELECT status,COUNT(*) FROM requests GROUP BY status"))
        committed_base, settled, uncertain_base, inflight_hold = db.execute("""SELECT
            COALESCE(SUM(COALESCE(settled_nanoyuan,reserved_nanoyuan)),0),
            COALESCE(SUM(CASE WHEN status='settled' THEN settled_nanoyuan ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN status='uncertain' THEN reserved_nanoyuan ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN status='reserved' THEN reserved_nanoyuan ELSE 0 END),0)
            FROM requests""").fetchone()
        has_adjustments = bool(db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='budget_adjustments'").fetchone()[0])
        adjustments, adjustment_count = (db.execute("SELECT COALESCE(SUM(amount_nanoyuan),0),COUNT(*) FROM budget_adjustments").fetchone()
                                         if has_adjustments else (0, 0))
        metadata = dict(db.execute("SELECT name,value FROM metadata WHERE name IN ('policy','halted','cooldown_until_utc','system_failure_streak')"))
        policy = json.loads(metadata["policy"])
        if policy.get("cap_nanoyuan") != 2000 * 10**9:
            raise ValueError("Read-only monitoring found an unexpected budget cap")
        failure_statuses = {str(status): count for status, count in db.execute("""
            SELECT json_extract(failure_json,'$.http_status'),COUNT(*) FROM requests
            WHERE failure_json IS NOT NULL GROUP BY json_extract(failure_json,'$.http_status')""")}
        api_failures = [dict(zip(("request_id","slot_id","condition","status","reserved_utc","reason","http_status","error_type"), values))
            for values in db.execute("""SELECT request_id,slot_id,condition,status,reserved_utc,
                json_extract(failure_json,'$.reason'),json_extract(failure_json,'$.http_status'),
                json_extract(failure_json,'$.error_type') FROM requests WHERE failure_json IS NOT NULL""")]
    if policy.get("version", "").endswith("-r4") and not has_adjustments:
        raise ValueError("r4 ledger policy lacks the required adjustment table")
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
    capacity = state.get("capacity", {})
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
        "generation_phase_metadata_counts": dict(phases),
        "missing_active_job_directories": missing,
        "desired_generation_concurrency": capacity.get("desired_generation_concurrency"),
        "load_average": os.getloadavg(), "memory_available_bytes": memory["MemAvailable"],
        "host_cpu_busy_cores_interval": cpu_cores, "host_cpu_count": os.cpu_count(),
        "volumes": volumes, "volume_reserved_bytes": reserved,
        "disk_metadata_error": disk.get("metadata_error"),
        "API_status_counts": api_status, "API_failure_http_status_counts": failure_statuses,
        "API_429_count": failure_statuses.get("429", 0),
        "settled_conservative_cny": settled / 1e9,
        "committed_conservative_cny": (committed_base + adjustments) / 1e9,
        "request_row_committed_cny_excluding_adjustments": committed_base / 1e9,
        "adjustment_hold_cny": adjustments / 1e9, "adjustment_count": adjustment_count,
        "uncertain_reserved_cny_including_adjustments": (uncertain_base + adjustments) / 1e9,
        "inflight_reserved_cny": inflight_hold / 1e9,
        "remaining_uncommitted_cny": (policy["cap_nanoyuan"] - committed_base - adjustments) / 1e9,
        "budget_cap_cny": policy["cap_nanoyuan"] / 1e9,
        "adjustment_table_present": has_adjustments,
        "ledger_migration_status": "r4_policy_with_adjustments" if policy.get("version", "").endswith("-r4") else "not_migrated_to_r4",
        "ledger_policy_version": policy.get("version"),
        "ledger_policy_sha256": hashlib.sha256(metadata["policy"].encode()).hexdigest(),
        "budget_source": "One read-only SQLite transaction; requests plus budget_adjustments, not state cache",
        "API_halted": metadata.get("halted"), "API_cooldown_until_utc": metadata.get("cooldown_until_utc"),
        "API_admission_wait_seconds": max(0, (datetime.fromisoformat(metadata["cooldown_until_utc"]) - now).total_seconds()) if metadata.get("cooldown_until_utc") else 0,
        "API_failure_streak": int(metadata.get("system_failure_streak", "0")),
        "dispatch_stopped": state.get("dispatch_stopped"), "stop_reason": state.get("stop_reason"),
        "exception_reason_counts": dict(Counter(item.get("reason", item.get("kind", "unknown"))
                                                for item in state.get("exceptions", []))),
        "preparing": sum(item.get("worker", {}).get("status") == "running"
                         for item in state.get("preparation", {}).values()),
        "source_messages_scores_and_account_balance_read": False}
    row["_exception_inventory"] = [{key: item.get(key) for key in
        ("slot_id", "instance_id", "kind", "reason", "created_utc")} for item in state.get("exceptions", [])]
    row["_api_failure_inventory"] = api_failures
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
    seen_exceptions, seen_failures = None, None
    fields = ["observed_cst", "closed", "technical_unknown", "running", "pending", "target",
              "primary_jobs", "secondary_jobs", "API_inflight", "API_429", "load_1m",
              "memory_available_bytes", "primary_free_bytes", "secondary_free_bytes", "API_halted",
              "settled_cny", "adjustment_hold_cny", "committed_cny", "new_exception_count", "new_API_failure_count"]
    with (output / "samples.jsonl").open("x", buffering=1) as stream, (output / "samples.csv").open("x", newline="") as table:
        writer = csv.DictWriter(table, fieldnames=fields)
        writer.writeheader()
        while True:
            try:
                row, previous_cpu = sample(previous_cpu)
                row["elapsed_seconds"] = time.monotonic() - start
                exception_inventory = row.pop("_exception_inventory")
                failure_inventory = row.pop("_api_failure_inventory")
                exception_map = {hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest(): item for item in exception_inventory}
                failure_map = {hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest(): item for item in failure_inventory}
                row["new_exceptions"] = [] if seen_exceptions is None else [value for key, value in exception_map.items() if key not in seen_exceptions]
                row["new_API_failures"] = [] if seen_failures is None else [value for key, value in failure_map.items() if key not in seen_failures]
                row["baseline_exception_count"] = len(exception_inventory) if seen_exceptions is None else None
                row["baseline_API_failure_count"] = len(failure_inventory) if seen_failures is None else None
                seen_exceptions = set(exception_map) | (seen_exceptions or set())
                seen_failures = set(failure_map) | (seen_failures or set())
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
                    "API_halted": row["API_halted"], "settled_cny": row["settled_conservative_cny"],
                    "adjustment_hold_cny": row["adjustment_hold_cny"], "committed_cny": row["committed_conservative_cny"],
                    "new_exception_count": len(row["new_exceptions"]), "new_API_failure_count": len(row["new_API_failures"])})
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
