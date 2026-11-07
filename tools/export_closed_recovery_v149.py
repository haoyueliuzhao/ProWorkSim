"""Watch completed v146 outputs and repair only the proven closure identity export.

Ordinary user, serial, two allowed CPU cores and16GiB address space. No API,
Docker, original-state writes, tool replay or candidate reselection is present.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import resource
import time
import traceback

from proworksim import software_benchmark_closed_export_recovery_v149 as recovery
from proworksim.storage import atomic_write, json_bytes


def run(*, watch=False, duration_seconds=14400, interval_seconds=60, indices=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Ordinary-user offline export only")
    if duration_seconds < 1 or duration_seconds > 14400 or interval_seconds != 60:
        raise ValueError("At most four hours with sixty-second checks")
    os.nice(10)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    resource.setrlimit(resource.RLIMIT_AS, (16 * 1024**3, 16 * 1024**3))
    recovery.OUTPUT.mkdir(parents=True, exist_ok=True)
    plan = recovery.load(recovery.reference(recovery.PLAN))
    all_rows = plan["rows"]
    rows = [r for r in all_rows if indices is None or r["slot_index"] in indices]
    if not rows or len(rows) > 42 or (indices is not None and len(rows) != len(set(indices))):
        raise ValueError("Only the fixed42 exact recovery identities may be observed")
    start = time.time()
    records = {}
    lock = (recovery.OUTPUT / "watcher.lock").open("a")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    while True:
        progress_file = recovery.BATCH / "api-coordinator/progress.json"
        original_closed = (
            progress_file.exists()
            and json.loads(progress_file.read_text()).get("phase") == "closed"
        )
        for row in rows:
            index = row["slot_index"]
            if index in records:
                continue
            output = recovery.OUTPUT / str(index) / "recovery-result.json"
            if output.exists():
                records[index] = {
                    "slot_index": index,
                    "status": "exported",
                    "result": recovery.reference(output),
                }
                continue
            original = recovery.BATCH / "episodes" / str(index) / "result.json"
            if not original.exists():
                if original_closed:
                    records[index] = {
                        "slot_index": index,
                        "status": "not_entered_or_not_closed",
                        "reason": "original_queue_closed_without_a_terminal_result",
                    }
                continue
            try:
                value = json.loads(original.read_text())
                if value.get("status") == "closed":
                    records[index] = {
                        "slot_index": index,
                        "status": "original_export_already_closed",
                    }
                    continue
                child_ref = value.get("controller_result")
                child = recovery.load(child_ref) if child_ref else {}
                if child.get("error") != {
                    "type": "ValueError",
                    "message": "An exact v142 task/organization/seed identity is required",
                }:
                    records[index] = {
                        "slot_index": index,
                        "status": "not_eligible",
                        "reason": "not_the_sole_metadata_identity_export_failure",
                    }
                    continue
                result = recovery.recover(index)
                records[index] = {"slot_index": index, "status": "exported", "result": result}
                print(json.dumps(records[index]), flush=True)
            except Exception as error:
                # Preserve evidence and continue independent queue entries.
                records[index] = {
                    "slot_index": index,
                    "status": "export_error",
                    "error": {"type": type(error).__name__, "message": str(error)},
                    "traceback": traceback.format_exc()[-16000:],
                }
                print(json.dumps(records[index]), flush=True)
        complete = original_closed and len(records) == len(rows) and len(rows) == len(all_rows)
        value = {
            "version": recovery.VERSION,
            "observed_unix": time.time(),
            "complete": complete,
            "original_queue_closed": original_closed,
            "planned": len(all_rows),
            "observed_slots": len(rows),
            "processed": list(records.values()),
            "pending": [r["slot_index"] for r in rows if r["slot_index"] not in records],
            "errors": [r for r in records.values() if r["status"] == "export_error"],
            "new_api_calls": 0,
            "new_docker_objects": 0,
            "new_tool_actions": 0,
            "original_results_changed": False,
        }
        atomic_write(recovery.OUTPUT / "progress.json", json_bytes(value))
        if complete:
            recovery.write_new(recovery.OUTPUT / "summary.json", value)
            return value
        if not watch or time.time() - start >= duration_seconds:
            return value
        time.sleep(interval_seconds)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--watch", action="store_true")
    p.add_argument("--indices", nargs="+", type=int)
    p.add_argument("--duration-seconds", type=int, default=14400)
    args = p.parse_args()
    result = run(watch=args.watch, duration_seconds=args.duration_seconds, indices=args.indices)
    print(
        json.dumps(
            {
                "complete": result["complete"],
                "processed": len(result["processed"]),
                "pending": result["pending"],
                "errors": result["errors"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
