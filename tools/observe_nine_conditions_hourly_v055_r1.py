"""Take one bounded, read-only nine-condition operational snapshot.

Only this monitor's immutable snapshot/summary files are written. No API call,
model load, job dispatch, rootfs traversal, payload hashing or service mutation.
The operator owns the six-hour schedule and any subsequent repairs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/software-benchmark-v055"
OUT = RUN / "six-hour-monitor-r1"
CST = timezone(timedelta(hours=8))
STATE_PATHS = {
    "qwen": ROOT / "runs/software-benchmark-v054/formal-queue-r1/state.json",
    "deepseek": RUN / "queue-r1/state.json",
}
POOL_PATH = ROOT / "runs/software-benchmark-v054/dynamic-pool-r4/provisioner-state.json"


def selected(value, keys):
    return {key: value[key] for key in keys if key in value}


def age(stamp, now):
    return (now - datetime.fromisoformat(stamp)).total_seconds() if stamp else None


def read_state(path, now):
    raw = path.read_bytes()
    value = json.loads(raw)
    return value, {"path": str(path), "bytes": len(raw),
                   "sha256": hashlib.sha256(raw).hexdigest(),
                   "updated_utc": value.get("updated_utc"),
                   "age_seconds": age(value.get("updated_utc"), now)}


def pending_class(row, preparation):
    item = preparation.get(row["slot"]["instance_id"], {})
    status = item.get("readiness", {}).get("status", row.get("environment_status"))
    if status == "failed":
        return "environment_failed"
    if item.get("worker", {}).get("status") == "running" or status == "preparing":
        return "environment_preparing"
    if status == "qualified":
        return "ready_waiting"
    return "environment_unprepared"


def score_endpoints(row):
    scores = row.get("scores", {})
    if isinstance(scores, dict):
        return scores
    result = {}
    for score in scores:
        basename = Path(score.get("request", {}).get("path", "")).name
        endpoint = {"official-code-request.json": "code",
                    "official-delivery-request.json": "delivery"}.get(basename)
        if endpoint is None:
            endpoint = "unknown_endpoint"
        if endpoint in result:
            raise ValueError("duplicate scoring endpoint in queue row")
        result[endpoint] = score
    return result


def summarize_queue(state, preparation, family):
    groups, pending, active = {}, [], []
    for row in state["rows"]:
        slot, generation = row["slot"], row["generation"]
        condition = slot.get("condition_id", slot["arm"])
        group = groups.setdefault(condition, {"planned": 0, "generation": Counter(),
            "pending_classification": Counter(), "code_score": Counter(),
            "delivery_score": Counter(), "delivery_lifecycle": Counter(),
            "observed_resolved_code": 0, "observed_resolved_delivery": 0})
        group["planned"] += 1
        group["generation"][generation["status"]] += 1
        if generation["status"] == "pending":
            classification = pending_class(row, preparation)
            group["pending_classification"][classification] += 1
            pending.append({**selected(slot, ("slot_id", "instance_id")),
                            "condition": condition, "classification": classification})
        if generation["status"] == "running":
            active.append({**selected(slot, ("slot_id", "instance_id")),
                "condition": condition, **selected(generation, (
                    "unit", "directory", "worker_directory", "dispatched_utc", "physical_gpu"))})
        endpoints = score_endpoints(row)
        for endpoint in ("code", "delivery"):
            score = endpoints.get(endpoint)
            status = (score.get("status", "unknown") if score else
                      "not_applicable" if endpoint == "delivery" and slot["arm"] != "PROJECT"
                      else "not_created")
            group[f"{endpoint}_score"][status] += 1
            if score and score.get("status") == "official_report" and score.get("resolved") is True:
                group[f"observed_resolved_{endpoint}"] += 1
        group["delivery_lifecycle"][row.get("delivery", {}).get("status", "not_recorded_in_queue_state")] += 1
    total = Counter()
    for group in groups.values():
        total.update(group["generation"])
    disk = state.get("disk_reservation_status", {})
    disk_small = selected(disk, ("observed_utc", "metadata_error", "target_volume", "active_peak_reserved_bytes"))
    disk_small["volumes"] = {name: selected(volume, (
        "device", "path", "free_bytes", "active_peak_reserved_bytes",
        "free_including_reserved_bytes", "filesystem_reserved_unavailable_bytes"))
        for name, volume in disk.get("volumes", {}).items()}
    admission = selected(state.get("last_disk_dispatch_admission", {}), (
        "kind", "instance_id", "observed_utc", "admitted", "reason", "target_volume",
        "free_bytes", "active_peak_reserved_bytes", "requested_peak_bytes",
        "minimum_remaining_bytes", "estimated_unreserved_bytes_after_launch"))
    failures = state.get("exceptions", []) if family == "deepseek" else state.get("deferred_exceptions", [])
    reason_counts = Counter(item.get("reason", item.get("kind", "unknown"))
                            for item in failures if isinstance(item, dict))
    return {"groups": groups, "generation_total": total, "pending": pending,
        "active_generation": active, "exception_reason_counts": reason_counts,
        "status": state.get("status"), "dispatch_stopped": state.get("dispatch_stopped"),
        "stop_reason": state.get("stop_reason"), "waiting": state.get("waiting"),
        "capacity": state.get("capacity"), "disk_reservations": disk_small,
        "last_disk_dispatch_admission": admission,
        "prewarm_backlog": state.get("prewarm_backlog"),
        "environment_coverage": state.get("environment_coverage"),
        "preparation_workers_running": sum(value.get("worker", {}).get("status") == "running"
                                             for value in state.get("preparation", {}).values()),
        "host_revision": state.get("active_host_revision", state.get("three_volume_host")),
        "resident_health": state.get("resident_health"),
        "pending_classification_basis": "Shared queue readiness metadata; no rootfs traversal or requalification",
        "resolved_counts_are_observed_only_not_full_panel_estimates": True}


def ledger_snapshot(now):
    path = RUN / "budget-r1/ledger.sqlite3"
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        statuses = dict(db.execute("SELECT status,COUNT(*) FROM requests GROUP BY status"))
        committed, settled, uncertain, inflight = db.execute("""SELECT
            COALESCE(SUM(COALESCE(settled_nanoyuan,reserved_nanoyuan)),0),
            COALESCE(SUM(CASE WHEN status='settled' THEN settled_nanoyuan ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN status='uncertain' THEN reserved_nanoyuan ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN status='reserved' THEN reserved_nanoyuan ELSE 0 END),0)
            FROM requests""").fetchone()
        adjustment, adjustment_count = db.execute(
            "SELECT COALESCE(SUM(amount_nanoyuan),0),COUNT(*) FROM budget_adjustments").fetchone()
        metadata = dict(db.execute("SELECT name,value FROM metadata WHERE name IN "
                                  "('policy','halted','cooldown_until_utc','system_failure_streak')"))
        policy = json.loads(metadata["policy"])
        failures = {str(status): count for status, count in db.execute("""SELECT
            json_extract(failure_json,'$.http_status'),COUNT(*) FROM requests
            WHERE failure_json IS NOT NULL GROUP BY json_extract(failure_json,'$.http_status')""")}
    if not policy.get("version", "").endswith("-r4") or policy.get("cap_nanoyuan") != 2000 * 10**9:
        raise ValueError("Unexpected provider ledger policy or budget cap")
    return {"status_counts": statuses, "failure_http_status_counts": failures,
        "http_429_count": failures.get("429", 0), "policy_version": policy["version"],
        "policy_sha256": hashlib.sha256(metadata["policy"].encode()).hexdigest(),
        "settled_cny": settled / 1e9, "committed_cny": (committed + adjustment) / 1e9,
        "uncertain_and_adjustment_hold_cny": (uncertain + adjustment) / 1e9,
        "inflight_hold_cny": inflight / 1e9, "adjustment_hold_cny": adjustment / 1e9,
        "adjustment_count": adjustment_count, "cap_cny": 2000,
        "remaining_uncommitted_cny": (2000 * 10**9 - committed - adjustment) / 1e9,
        "halted": metadata.get("halted"), "cooldown_until_utc": metadata.get("cooldown_until_utc"),
        "cooldown_remaining_seconds": max(0, -age(metadata.get("cooldown_until_utc"), now))
            if metadata.get("cooldown_until_utc") else 0,
        "system_failure_streak": int(metadata.get("system_failure_streak", 0)),
        "basis": "One read-only SQLite transaction, requests plus budget_adjustments"}


def capacity_snapshot():
    memory = {key: int(value.split()[0]) * 1024 for key, value in (
        line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())}
    cpu = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:9]))
    return {"cpu_count": os.cpu_count(), "load_average": os.getloadavg(),
            "memory_total_bytes": memory["MemTotal"], "memory_available_bytes": memory["MemAvailable"],
            "swap_total_bytes": memory["SwapTotal"], "swap_free_bytes": memory["SwapFree"],
            "cpu_ticks": cpu}


def volume_snapshot(path):
    stat = os.statvfs(path)
    return {"path": str(path), "device": path.stat().st_dev,
            "available_bytes": stat.f_bavail * stat.f_frsize,
            "free_including_reserved_bytes": stat.f_bfree * stat.f_frsize,
            "filesystem_reserved_unavailable_bytes": (stat.f_bfree - stat.f_bavail) * stat.f_frsize,
            "available_inodes": stat.f_favail}


def unit_snapshot(units):
    result = subprocess.run(["systemctl", "--user", "show", *units.values(),
        "-p", "Id", "-p", "LoadState", "-p", "ActiveState", "-p", "SubState",
        "-p", "MainPID", "-p", "Result", "-p", "InvocationID", "-p", "ActiveEnterTimestamp",
        "-p", "ExecMainStartTimestamp"], capture_output=True, text=True, timeout=15, check=True)
    values = [dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
              for block in result.stdout.strip().split("\n\n")]
    indexed = {item.get("Id"): item for item in values}
    return {role: indexed.get(unit, {"Id": unit, "observation_missing": True}) for role, unit in units.items()}


def gpu_snapshot():
    fields = ("index", "uuid", "name", "memory.total", "memory.used", "memory.free",
              "utilization.gpu", "utilization.memory")
    result = subprocess.run(["nvidia-smi", "--query-gpu=" + ",".join(fields),
        "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15, check=True)
    return [dict(zip(fields, (part.strip() for part in line.split(","))))
            for line in result.stdout.splitlines() if line.strip()]


def pool_snapshot(now):
    state, identity = read_state(POOL_PATH, now)
    return {"state": identity, "conversion": state.get("conversion"),
        "formal_slots_claimed": state.get("formal_slots_claimed"),
        "automatically_replayed_formal_episodes": state.get("automatically_replayed_formal_episodes"),
        "devices": {device: selected(item, ("resident_id", "unit", "attempt", "status",
            "created_utc", "weights_kept_resident", "model_load_attempted", "failure"))
            for device, item in state.get("devices", {}).items()}}


def interval_delta(current, previous):
    seconds = age(previous["observed_utc"], datetime.fromisoformat(current["observed_utc"]))
    result = {"elapsed_seconds": seconds, "groups": {}}
    for family, queue in current.get("queues", {}).items():
        for condition, group in queue.get("groups", {}).items():
            before = previous.get("queues", {}).get(family, {}).get("groups", {}).get(condition)
            if before is None:
                continue
            delta = {key: group["generation"].get(key, 0) - before["generation"].get(key, 0)
                     for key in ("closed", "technical_unknown", "running", "pending")}
            result["groups"][f"{family}/{condition}"] = {"generation_delta": delta,
                "closed_per_hour": delta["closed"] * 3600 / seconds if seconds > 0 else None}
    if current.get("ledger") and previous.get("ledger"):
        result["ledger"] = {key: current["ledger"][key] - previous["ledger"][key]
                            for key in ("settled_cny", "committed_cny", "http_429_count")}
    current_ticks = (current.get("capacity") or {}).get("cpu_ticks")
    previous_ticks = (previous.get("capacity") or {}).get("cpu_ticks")
    if current_ticks and previous_ticks:
        ticks = [a - b for a, b in zip(current_ticks, previous_ticks)]
        if all(value >= 0 for value in ticks) and sum(ticks) > 0:
            result["mean_host_busy_cpu_cores"] = ((sum(ticks) - ticks[3] - ticks[4]) / sum(ticks)
                                                 * current["capacity"]["cpu_count"])
    return result


def capture(snapshot, section, action):
    try:
        return action()
    except Exception as error:
        snapshot["errors"].append({"section": section, "error_type": type(error).__name__,
                                    "error": str(error)[:1000]})
        return None


def collect(index, schedule, schedule_sha256, previous=None):
    now = datetime.now(timezone.utc)
    snapshot = {"version": "nine-conditions-hourly-observation-v055-r1", "index": index,
        "observed_utc": now.isoformat(), "observed_cst": now.astimezone(CST).isoformat(),
        "schedule_sha256": schedule_sha256, "errors": [], "queues": {},
        "model_calls": 0, "job_dispatches": 0, "runtime_or_services_mutated": False}
    states, identities = {}, {}
    for family, path in STATE_PATHS.items():
        value = capture(snapshot, family + "_state", lambda p=path: read_state(p, now))
        if value is not None:
            states[family], identities[family] = value
    preparation = states.get("deepseek", {}).get("preparation", {})
    for family, state in states.items():
        value = capture(snapshot, family + "_summary", lambda s=state, f=family: summarize_queue(s, preparation, f))
        if value is not None:
            snapshot["queues"][family] = {"state": identities[family], **value}
    snapshot["ledger"] = capture(snapshot, "ledger", lambda: ledger_snapshot(now))
    snapshot["capacity"] = capture(snapshot, "capacity", capacity_snapshot)
    snapshot["volumes"] = {name: capture(snapshot, "volume_" + name, lambda p=path: volume_snapshot(p))
        for name, path in (("primary", ROOT), ("secondary", RUN / "secondary-volume-r1"),
                           ("tertiary", RUN / "tertiary-volume-r1"))}
    snapshot["manager_units"] = capture(snapshot, "manager_units", lambda: unit_snapshot(schedule["manager_units"]))
    snapshot["gpu_usage"] = capture(snapshot, "gpu_usage", gpu_snapshot)
    snapshot["resident_pool"] = capture(snapshot, "resident_pool", lambda: pool_snapshot(now))
    if previous is not None:
        snapshot["since_previous_snapshot"] = capture(snapshot, "delta", lambda: interval_delta(snapshot, previous))
    snapshot["collection_finished_utc"] = datetime.now(timezone.utc).isoformat()
    return snapshot


def summarize(snapshot):
    return {key: value for key, value in snapshot.items() if key not in ("queues", "resident_pool")} | {
        "queues": {family: {key: value for key, value in queue.items() if key not in ("pending", "active_generation", "resident_health")}
                   for family, queue in snapshot["queues"].items()},
        "resident_pool": snapshot.get("resident_pool"),
        "interpretation": "Generation completion and observed resolved counts are distinct; technical unknowns are not model failures. Rates describe only this interval."}


def write_exclusive(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=int, choices=range(7))
    parser.add_argument("--schedule-sha256", required=True)
    args = parser.parse_args()
    raw = (OUT / "schedule.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.schedule_sha256:
        raise ValueError("schedule hash mismatch")
    schedule = json.loads(raw)
    units = schedule.get("manager_units", {})
    if (not isinstance(units, dict) or len(units) != 4 or len(set(units.values())) != 4
            or any(not re.fullmatch(r"proworksim[-a-zA-Z0-9_.]+\.service", unit) for unit in units.values())):
        raise ValueError("schedule must identify four distinct exact ProWorkSim manager service names")
    target = OUT / f"snapshot-{args.index:02d}.json"
    summary = OUT / f"summary-{args.index:02d}.json"
    if target.exists() or summary.exists():
        raise FileExistsError("snapshot index already published; immutable snapshots are never overwritten")
    previous, previous_error = None, None
    if args.index:
        try:
            previous = json.loads((OUT / f"snapshot-{args.index - 1:02d}.json").read_bytes())
            if previous.get("schedule_sha256") != args.schedule_sha256:
                raise ValueError("previous snapshot belongs to another schedule")
        except Exception as error:
            previous = None
            previous_error = {"section": "previous_snapshot", "error_type": type(error).__name__,
                              "error": str(error)[:1000]}
    snapshot = collect(args.index, schedule, args.schedule_sha256, previous)
    if previous_error:
        snapshot["errors"].append(previous_error)
    write_exclusive(target, snapshot)
    write_exclusive(summary, summarize(snapshot))
    print(json.dumps({"snapshot": str(target), "summary": str(summary),
                      "observed_cst": snapshot["observed_cst"], "errors": snapshot["errors"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
