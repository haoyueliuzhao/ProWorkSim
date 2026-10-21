#!/usr/bin/env python3
"""Read-only, bounded observation of a kernel rollout; no model or task actions."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import statistics
import subprocess
import time

VERSION = "v054-kernel-rollout-monitor-r1"
DURATION = 1800
INTERVAL = 30
GPUS = (3, 6, 7)
STOP = False


def utc(value=None):
    return datetime.fromtimestamp(time.time() if value is None else value, timezone.utc).isoformat()


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("A timezone is required")
    return parsed.timestamp()


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def append(path, value):
    with path.open("a") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        stream.flush()


def revision(row):
    return row.get("original_execution_bindings", row.get("next_execution_bindings", {})).get("sha256", "unknown")


def first_dispatch(state, target_sha, after):
    rows = {r["slot"]["slot_id"]: r for r in state["rows"]}
    matches = []
    for dispatch in state.get("generation_dispatches", []):
        row = rows.get(dispatch.get("slot_id"), {})
        when = dispatch.get("worker_started_utc")
        if (dispatch.get("physical_gpu") == 6 and row and revision(row) == target_sha
                and when and timestamp(when) >= after):
            matches.append((timestamp(when), dispatch["slot_id"], when))
    return min(matches) if matches else None


def in_window(value, start, end):
    return start <= value < end


class OnceReader:
    """Read each immutable completion/controller artifact at most once."""
    def __init__(self):
        self.cache = {}

    def read(self, path, reference=None):
        key = str(Path(path).resolve())
        if key not in self.cache:
            try:
                data = Path(key).read_bytes()
                if reference and (hashlib.sha256(data).hexdigest() != reference["sha256"]
                                  or ("bytes" in reference and len(data) != reference["bytes"])):
                    raise ValueError("Artifact SHA or size differs")
                value = json.loads(data)
                self.cache[key] = (value, None, {"path": key,
                    "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
            except Exception as exc:
                self.cache[key] = (None, type(exc).__name__ + ": " + str(exc), {"path": key})
        return self.cache[key]


def token_totals(controller):
    ledger = controller.get("ledger", {})
    if "model" in ledger:
        ledger = ledger["model"]
        records = list(ledger.get("records", {}).values())
        usages = [r.get("charge", {}).get("reported_usage") for r in records]
        complete = (not ledger.get("integrity_failure") and not ledger.get("held_tokens")
                    and all(r.get("status") == "settled" for r in records))
        expected = ledger.get("charged_tokens")
    else:
        records = ledger.get("calls", [])
        usages = [r.get("usage") for r in records]
        complete = (ledger.get("complete_actual_tokens") is not None
                    and not ledger.get("uncertain_reserved_tokens") and not ledger.get("inflight"))
        expected = ledger.get("complete_actual_tokens")
    known = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    actual_calls = 0
    for usage in usages:
        if not isinstance(usage, dict) or not all(isinstance(usage.get(k), int) for k in known):
            complete = False
            continue
        if usage["prompt_tokens"] + usage["completion_tokens"] != usage["total_tokens"]:
            complete = False
        for key in known:
            known[key] += usage[key]
        actual_calls += 1
    complete = complete and expected == known["total_tokens"]
    return {**known, "known_usage_calls": actual_calls, "complete": complete,
            "ledger_complete_or_charged_tokens": expected,
            "missing_usage_records": len(usages) - actual_calls}


def closed_records(state, reader, start, end, gpu_filter=None):
    records, errors = [], []
    for row in state["rows"]:
        generation = row["generation"]
        if generation["status"] != "closed" or generation.get("physical_gpu") not in GPUS:
            continue
        if gpu_filter is not None and generation.get("physical_gpu") not in gpu_filter:
            continue
        worker = generation.get("worker_directory")
        if not worker:
            continue
        completion_path = Path(worker) / "completion.json"
        # Small stat filter avoids reading old large ledgers. Original completion
        # JSON timestamps, never mtimes, decide actual window membership below.
        try:
            if completion_path.stat().st_mtime < start - 2:
                continue
        except OSError as exc:
            errors.append({"slot_id": row["slot"]["slot_id"], "error": str(exc)})
            continue
        completion, error, completion_ref = reader.read(completion_path)
        if error:
            errors.append({"slot_id": row["slot"]["slot_id"], "error": error})
            continue
        try:
            closed = timestamp(completion["completed_utc"])
            opened = timestamp(completion["started_utc"])
        except (KeyError, ValueError) as exc:
            errors.append({"slot_id": row["slot"]["slot_id"], "error": str(exc)})
            continue
        if not in_window(closed, start, end):
            continue
        ledger_ref = generation.get("actual_cost_ledger") or generation.get("controller_result")
        controller, ledger_error, actual_ref = (reader.read(ledger_ref["path"], ledger_ref)
            if ledger_ref else (None, "No controller ledger reference", None))
        records.append({"slot_id": row["slot"]["slot_id"], "slot_index": row["slot"]["slot_index"],
            "arm": row["slot"]["arm"], "instance_id": row["slot"]["instance_id"],
            "gpu": generation["physical_gpu"], "revision": revision(row),
            "resident_id": generation.get("resident_id"),
            "started_utc": completion["started_utc"], "completed_utc": completion["completed_utc"],
            "wall_seconds": closed - opened, "started_before_window": opened < start,
            "worker_returncode": completion.get("returncode"),
            "tokens": token_totals(controller) if controller else None,
            "ledger_error": ledger_error, "completion": completion_ref, "controller_ledger": actual_ref})
    return records, errors


def dedupe(records):
    return list({r["slot_id"]: r for r in records}.values())


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values):
    return {"n": len(values), "min": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "p90": percentile(values, .9), "max": max(values) if values else None,
            "mean": statistics.mean(values) if values else None}


def summarize_groups(records, seconds):
    groups = defaultdict(list)
    for row in dedupe(records):
        groups[(row["gpu"], row["arm"], row["revision"])].append(row)
    result = []
    for (gpu, arm, rev), rows in sorted(groups.items()):
        tokens = [r["tokens"] for r in rows if r["tokens"] and r["tokens"]["complete"]]
        result.append({"gpu": gpu, "arm": arm, "revision": rev,
            "closed": len(rows), "closed_per_hour": len(rows) * 3600 / seconds if seconds else None,
            "window_seconds": seconds, "wall_seconds": distribution([r["wall_seconds"] for r in rows]),
            "started_before_window": sum(r["started_before_window"] for r in rows),
            "complete_token_ledgers": len(tokens), "unknown_token_ledgers": len(rows) - len(tokens),
            "known_complete_input_tokens": sum(t["prompt_tokens"] for t in tokens),
            "known_complete_output_tokens": sum(t["completion_tokens"] for t in tokens),
            "known_complete_total_tokens": sum(t["total_tokens"] for t in tokens),
            "known_complete_tokens_per_window_second": sum(t["total_tokens"] for t in tokens) / seconds if seconds else None})
    return result


def gpu_sample():
    result = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits", "--id=3,6,7"], capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:500])
    rows = []
    for line in result.stdout.strip().splitlines():
        index, uuid, utilization, used, total = [v.strip() for v in line.split(",")]
        rows.append({"gpu": int(index), "uuid": uuid, "utilization_percent": float(utilization),
                     "memory_used_mib": float(used), "memory_total_mib": float(total)})
    return rows


def gpu_summary(samples):
    result = {}
    for gpu in GPUS:
        rows = [g for sample in samples for g in sample.get("gpus", []) if g["gpu"] == gpu]
        result[str(gpu)] = {"utilization_percent": distribution([r["utilization_percent"] for r in rows]),
            "memory_used_mib": distribution([r["memory_used_mib"] for r in rows]),
            "zero_utilization_samples": sum(r["utilization_percent"] == 0 for r in rows),
            "scope": "Whole device, includes other processes; sampled utilization is not a kernel profiler."}
    return result


def save_summary(output, value):
    write(output / "summary.json", value)
    lines = ["# Kernel rollout observation", "", f"Status: {value['status']}", "",
        "This is an observation of different task cohorts, not a causal kernel speedup estimate.",
        "GPU utilization and memory include all processes on each sampled device.", ""]
    for label in ("baseline", "observed"):
        lines.extend([f"## {label}", "", "| GPU | Arm | Revision | Closed | Closed/h | Median episode seconds | Complete-ledger tokens |", "| --- | --- | --- | ---: | ---: | ---: | ---: |"])
        for group in value.get(label + "_groups", []):
            lines.append(f"| {group['gpu']} | {group['arm']} | {group['revision'][:12]} | {group['closed']} | {group['closed_per_hour']:.2f} | {group['wall_seconds']['median']:.2f} | {group['known_complete_total_tokens']} |")
        lines.append("")
    lines.extend(["Pending/running episodes are right-censored; their final token costs are not imputed.",
                  "Token/window-second counts tokens of episodes closed within the window, including work started earlier; it is not model decode tokens/second.", ""])
    (output / "summary.md").write_text("\n".join(lines))


def stop_handler(_signum, _frame):
    global STOP
    STOP = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-state", required=True, type=Path)
    parser.add_argument("--new-bindings-sha", required=True)
    parser.add_argument("--activation-utc", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--wait-timeout-seconds", type=int, default=7200)
    args = parser.parse_args()
    if len(args.new_bindings_sha) != 64 or not all(c in "0123456789abcdef" for c in args.new_bindings_sha):
        raise ValueError("An exact new bindings SHA256 is required")
    activation = timestamp(args.activation_utc)
    args.output.mkdir(parents=True, exist_ok=False)
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    self_data = Path(__file__).read_bytes()
    write(args.output / "intent.json", {"version": VERSION, "created_utc": utc(),
        "queue_state": str(args.queue_state.resolve()), "new_bindings_sha": args.new_bindings_sha,
        "activation_utc": args.activation_utc, "baseline_seconds": 2700,
        "duration_seconds": DURATION, "interval_seconds": INTERVAL, "GPU_ids": GPUS,
        "source_sha256": hashlib.sha256(self_data).hexdigest(),
        "read_only": True, "model_requests": 0, "task_mutations": 0})
    wait_deadline = time.monotonic() + args.wait_timeout_seconds
    first, state = None, None
    while not STOP and time.monotonic() < wait_deadline:
        try:
            state = json.loads(args.queue_state.read_bytes())
            first = first_dispatch(state, args.new_bindings_sha, activation)
            if first:
                break
        except Exception as exc:
            append(args.output / "errors.jsonl", {"utc": utc(), "phase": "waiting", "error": str(exc)})
        time.sleep(INTERVAL)
    if not first:
        save_summary(args.output, {"version": VERSION, "status": "stopped_before_trigger" if STOP else "trigger_timeout",
            "ended_utc": utc(), "model_requests": 0, "task_mutations": 0})
        return 1
    started, first_slot, first_utc = first
    end = started + DURATION
    reader = OnceReader()
    baseline, errors = closed_records(state, reader, activation - 2700, activation, {6})
    write(args.output / "baseline.json", {"start_utc": utc(activation - 2700),
        "end_utc": utc(activation), "records": dedupe(baseline), "errors": errors})
    write(args.output / "trigger.json", {"first_dispatch_utc": first_utc, "first_slot": first_slot,
        "detected_utc": utc(), "window_end_utc": utc(end), "detector_delay_seconds": time.time() - started})
    samples, observed = [], {}
    next_sample = started
    while not STOP and time.time() < end:
        now = time.time()
        if now < next_sample:
            time.sleep(min(INTERVAL, next_sample - now))
            continue
        sample = {"utc": utc(), "elapsed_seconds": now - started}
        try:
            state = json.loads(args.queue_state.read_bytes())
            sample["queue"] = {k: state.get(k) for k in ("status", "updated_utc", "active_generation", "active_graders", "generation_counts", "fully_closed_slots")}
            records, errors = closed_records(state, reader, started, min(time.time(), end))
            for row in records:
                if row["slot_id"] not in observed:
                    observed[row["slot_id"]] = row
                    append(args.output / "closed-episodes.jsonl", row)
            if errors:
                sample["artifact_errors"] = errors
        except Exception as exc:
            sample["queue_error"] = str(exc)
        try:
            sample["gpus"] = gpu_sample()
        except Exception as exc:
            sample["gpu_error"] = str(exc)
        samples.append(sample)
        append(args.output / "samples.jsonl", sample)
        elapsed = min(time.time(), end) - started
        summary = {"version": VERSION, "status": "observing", "started_utc": first_utc,
            "planned_end_utc": utc(end), "observed_seconds": elapsed, "samples": len(samples),
            "baseline_groups": summarize_groups(baseline, 2700),
            "observed_groups": summarize_groups(list(observed.values()), elapsed),
            "GPU_distributions": gpu_summary(samples), "model_requests": 0, "task_mutations": 0,
            "interpretation": "Different task cohorts and shared GPU; not a causal speedup estimate."}
        save_summary(args.output, summary)
        next_sample = started + (int((time.time() - started) / INTERVAL) + 1) * INTERVAL
    # One final queue read includes closures since the last 30-second GPU sample.
    try:
        state = json.loads(args.queue_state.read_bytes())
        records, errors = closed_records(state, reader, started, min(time.time(), end))
        for row in records:
            if row["slot_id"] not in observed:
                observed[row["slot_id"]] = row
                append(args.output / "closed-episodes.jsonl", row)
    except Exception as exc:
        errors = [{"error": str(exc)}]
    elapsed = min(time.time(), end) - started
    save_summary(args.output, {"version": VERSION,
        "status": "stopped_partial" if STOP else "completed", "started_utc": first_utc,
        "planned_end_utc": utc(end), "ended_utc": utc(), "observed_seconds": elapsed,
        "samples": len(samples), "baseline_groups": summarize_groups(baseline, 2700),
        "observed_groups": summarize_groups(list(observed.values()), elapsed),
        "GPU_distributions": gpu_summary(samples), "last_queue_artifact_errors": errors,
        "active_generation_at_end": state.get("active_generation") if state else None,
        "read_immutable_files": len(reader.cache), "model_requests": 0, "task_mutations": 0,
        "interpretation": "Different task cohorts and shared GPU; not a causal speedup estimate."})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
