#!/usr/bin/env python3
"""Bounded 429/read-timeout supervision for the fixed v054 image batch."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import email.utils
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verified_image_prepare_v054 import save  # noqa: E402

PREPARATION = ROOT / "runs/software-benchmark-v054/images/preparation-r1"
CONTROL = ROOT / "runs/software-benchmark-v054/images/retry-supervisor-r2"
UNIT = "proworksim-v054-image-preparation-r2.service"


def epoch(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def retry_action(status, *, now_epoch, deadline, no_payload_streak, timeout_retries_used=0):
    timeout = (
        status.get("http_status") is None
        and (status.get("error_type") == "TimeoutError"
             or str(status.get("error", "")).strip().lower()
             in {"the read operation timed out", "read operation timed out"}))
    if status.get("http_status") != 429 and not timeout:
        return {"action": "blocked", "reason": "non_429_fault_no_automatic_retry"}
    if no_payload_streak >= 3:
        return {"action": "blocked", "reason": "three_consecutive_cooldowns_without_payload"}
    if timeout:
        if timeout_retries_used >= 3:
            return {"action": "blocked", "reason": "bounded_read_timeout_retry_limit_reached"}
        delay = (60, 300, 900)[timeout_retries_used]
        target = now_epoch + delay
        if target > deadline:
            return {"action": "blocked", "reason": "retry_would_exceed_96_hour_window"}
        return {"action": "schedule", "kind": "read_timeout", "backoff_seconds": delay,
                "not_before_epoch": target,
                "not_before_utc": datetime.fromtimestamp(target, timezone.utc).isoformat()}
    value = status.get("retry_after")
    try:
        paused = epoch(status["paused_at_utc"])
        if isinstance(value, str) and value.strip().isdigit():
            target = paused + int(value.strip())
        elif isinstance(value, str):
            target = email.utils.parsedate_to_datetime(value).timestamp()
        else:
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"action": "blocked", "reason": "missing_or_invalid_actual_retry_after"}
    # Even a provider value of zero cannot produce a dense retry loop.
    target = max(target, now_epoch + 60)
    if target > deadline:
        return {"action": "blocked", "reason": "retry_would_exceed_96_hour_window"}
    return {"action": "schedule", "kind": "http_429", "not_before_epoch": target,
            "not_before_utc": datetime.fromtimestamp(target, timezone.utc).isoformat()}


def one_ms_materialized_bytes(cache):
    """A progress signal, not billing: count distinct bytes attributed to 1ms."""
    total = 0
    candidates = set()
    for path in cache.iterdir():
        match = re.match(r"([0-9a-f]{64})\.blob(?:\.|$)", path.name)
        if match:
            candidates.add(match[1])
    for digest in candidates:
        blob = cache / (digest + ".blob")
        receipt_path = blob.with_name(blob.name + ".verified.json")
        prefix_path = blob.with_name(blob.name + ".part")
        prefix_receipt = blob.with_name(blob.name + ".part.json")
        prefix = json.loads(prefix_receipt.read_bytes()) if prefix_receipt.exists() else {}
        range_root = blob.with_name(blob.name + ".ranges")
        ledger_path = range_root / "ledger.json"
        ledger = json.loads(ledger_path.read_bytes()) if ledger_path.exists() else {}
        prefix_is_one_ms = prefix.get("source_url", "").startswith("https://docker.1ms.run/")
        api_prefix = 0
        for event in ledger.get("events", []):
            if (event.get("event") == "reuse_sequential_prefix"
                    and event.get("original_source_url", "").startswith("https://docker.apiba.cn/")):
                api_prefix = max(api_prefix, event["bytes"])
        if blob.exists() and receipt_path.exists():
            receipt = json.loads(receipt_path.read_bytes())
            size = blob.stat().st_size
            if receipt.get("expected_sha256") != digest or receipt.get("expected_bytes") != size:
                raise ValueError("Completed blob proof identity changed")
            kind = receipt.get("verification", "")
            if kind == "apiba_complete_download_incremental_sha256":
                continue
            if kind == "range_assembly_complete_sha256":
                total += size - api_prefix
            elif prefix_is_one_ms:
                total += size
            continue
        intervals = []
        if prefix_is_one_ms and prefix_path.exists():
            intervals.append((0, min(prefix_path.stat().st_size, prefix.get("partial_bytes", 0))))
        if range_root.exists():
            for path in range_root.glob("*.part"):
                match = re.fullmatch(r"(\d+)-(\d+)\.part", path.name)
                if match:
                    start, end = map(int, match.groups())
                    intervals.append((start, start + min(path.stat().st_size, end - start + 1)))
        right = 0
        for start, end in sorted(intervals):
            total += max(0, end - max(start, right))
            right = max(right, end)
    return total


def unit_state():
    result = subprocess.run(
        ["systemctl", "--user", "show", UNIT, "-p", "ActiveState", "-p", "SubState",
         "-p", "InvocationID", "-p", "ExecMainStartTimestampMonotonic"],
        capture_output=True, text=True, check=False)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def invocation_key(value):
    started = value.get("ExecMainStartTimestampMonotonic")
    return "start:" + started if started and started != "0" else value.get("InvocationID", "unknown")


def batch_identity():
    return hashlib.sha256((ROOT / "config/v054-verified-image-inventory.json").read_bytes()).hexdigest()


def launch(attempt):
    state = json.loads((CONTROL / "state.json").read_bytes())
    if state["inventory_sha256"] != batch_identity() or time.time() > state["deadline_epoch"]:
        raise RuntimeError("Fixed batch changed or retry window ended")
    pending = state.get("pending")
    if (not pending or pending["attempt"] != attempt
            or time.time() < pending["not_before_epoch"]
            or state["status"] == "external_blocked"):
        raise RuntimeError("No due authorized retry for this attempt")
    record_path = CONTROL / f"attempt-{attempt:04d}-start.json"
    if record_path.exists():
        return 0
    current = unit_state()
    record = {"attempt": attempt, "at_epoch": time.time(), "unit": UNIT,
              "inventory_sha256": state["inventory_sha256"],
              "one_ms_materialized_bytes_before": one_ms_materialized_bytes(PREPARATION / "blobs"),
              "active_before_launch": current.get("ActiveState")}
    if current.get("ActiveState") in ("active", "activating", "deactivating"):
        record["status"] = "existing_active_unit_not_restarted"
        save(record_path, record)
        return 0
    save(record_path, {**record, "status": "launching"})
    result = subprocess.run(["systemctl", "--user", "start", UNIT], check=False)
    record.update(status="launched" if result.returncode == 0 else "launch_failed",
                  returncode=result.returncode, invocation_id=invocation_key(unit_state()))
    save(record_path, record)
    return result.returncode


def supervise():
    CONTROL.mkdir(parents=True, exist_ok=True)
    state_path = CONTROL / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_bytes())
        if state["inventory_sha256"] != batch_identity():
            raise RuntimeError("Retry supervisor batch identity changed")
        if state["status"] in ("external_blocked", "image_preparation_closed"):
            return 2 if state["status"] == "external_blocked" else 0
    else:
        began = time.time()
        prior_path = ROOT / "runs/software-benchmark-v054/images/retry-supervisor-r1/state.json"
        prior = json.loads(prior_path.read_bytes()) if prior_path.exists() else {}
        if prior.get("scheduled_attempts", 0) or prior.get("pending"):
            raise RuntimeError("Existing scheduled retry history requires explicit migration")
        began = prior.get("started_epoch", began)
        state = {
            "schema": "proworksim.v054.image-429-timeout-retry-supervisor-r2",
            "inventory_sha256": batch_identity(), "started_epoch": began,
            "deadline_epoch": prior.get("deadline_epoch", began + 96 * 3600),
            "maximum_window_hours": 96, "prior_window_preserved": bool(prior),
            "status": "monitoring", "no_payload_streak": 0, "scheduled_attempts": 0,
            "timeout_retries_scheduled": 0, "timeout_backoff_seconds": [60, 300, 900],
            "last_handled_invocation": None, "pending": None,
            "initial_attempt_baseline_assessable": False,
            "payload_basis": "Distinct materialized bytes attributed to 1ms, including partials; excludes APIBA bytes; not a billing meter.",
            "other_source_or_inflight_streams_stopped": False, "model_calls": 0, "gpu_requests": 0,
        }
        save(state_path, state)
    while time.time() < state["deadline_epoch"]:
        current = unit_state()
        path = PREPARATION / "transport-status.json"
        live = json.loads((path if path.exists() else PREPARATION / "image-inventory.json").read_bytes())
        if live["inventory_sha256"] != state["inventory_sha256"]:
            state.update(status="external_blocked", reason="live_batch_identity_changed")
            save(state_path, state)
            return 2
        if live["status"] == "image_preparation_complete":
            state.update(status="image_preparation_closed", ended_epoch=time.time())
            save(state_path, state)
            return 0
        if current.get("ActiveState") in ("active", "activating", "deactivating"):
            state["status"] = "monitoring_active_attempt"
            save(state_path, state)
            time.sleep(30)
            continue
        invocation = invocation_key(current)
        start_record = None
        if state["pending"]:
            candidate = CONTROL / f"attempt-{state['pending']['attempt']:04d}-start.json"
            if candidate.exists():
                start_record = json.loads(candidate.read_bytes())
                if start_record.get("status") == "launch_failed":
                    state.update(status="external_blocked", reason="scheduled_unit_start_failed")
                    save(state_path, state)
                    return 2
        if invocation == state["last_handled_invocation"]:
            time.sleep(30)
            continue
        after = one_ms_materialized_bytes(PREPARATION / "blobs")
        assessable = (start_record is not None and start_record.get("status") == "launched"
                      and start_record.get("invocation_id") == invocation)
        before = start_record["one_ms_materialized_bytes_before"] if assessable else None
        if assessable and after >= before:
            state["no_payload_streak"] = state["no_payload_streak"] + 1 if after == before else 0
        action = retry_action(
            live, now_epoch=time.time(), deadline=state["deadline_epoch"],
            no_payload_streak=state["no_payload_streak"],
            timeout_retries_used=state["timeout_retries_scheduled"])
        record = {
            "invocation_id": invocation, "status": live["status"],
            "http_status": live.get("http_status"), "retry_after": live.get("retry_after"),
            "baseline_assessable": assessable, "one_ms_bytes_before": before,
            "one_ms_bytes_after": after, "no_payload_streak": state["no_payload_streak"],
            "decision": action, "observed_epoch": time.time(),
        }
        save(CONTROL / f"outcome-{time.time_ns()}.json", record)
        state["last_handled_invocation"] = invocation
        if action["action"] != "schedule":
            if state["pending"]:
                subprocess.run(["systemctl", "--user", "stop", state["pending"]["timer"]],
                               check=False, capture_output=True)
            state.update(status="external_blocked", reason=action["reason"], pending=None)
            save(state_path, state)
            return 2
        number = state["scheduled_attempts"] + 1
        timer = f"proworksim-v054-image-auto-resume-r2-{number:04d}"
        calendar = datetime.fromtimestamp(
            math.ceil(action["not_before_epoch"]), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        command = [
            "systemd-run", "--user", "--unit=" + timer, "--on-calendar=" + calendar,
            "--timer-property=Persistent=false", "--timer-property=AccuracySec=1s",
            sys.executable, "-B", str(Path(__file__).resolve()), "--launch", str(number),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        state.update(status="cooling_down", scheduled_attempts=number,
                     pending={"attempt": number, "timer": timer + ".timer", **action})
        if action["kind"] == "read_timeout":
            state["timeout_retries_scheduled"] += 1
        save(state_path, state)
        time.sleep(30)
    state.update(status="external_blocked", reason="96_hour_retry_window_ended",
                 ended_epoch=time.time())
    save(state_path, state)
    return 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", type=int)
    arguments = parser.parse_args()
    try:
        result = launch(arguments.launch) if arguments.launch else supervise()
    except Exception as error:
        CONTROL.mkdir(parents=True, exist_ok=True)
        path = CONTROL / "state.json"
        if path.exists():
            state = json.loads(path.read_bytes())
            if state.get("status") != "external_blocked":
                state.update(status="external_blocked",
                             reason="supervisor_integrity_or_execution_fault",
                             error_type=type(error).__name__, error=str(error)[:500])
                save(path, state)
        raise
    raise SystemExit(result)
