"""Registered child-group cleanup utility, without a CAL2 launch entry point."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import time

from proworksim.storage import read_json
from scripts.software_calibration_v051 import checked, ref, write


def registered_process_identity(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rfind(")") + 2:].split()
        return {"pid": pid, "state": fields[0], "parent_pid": int(fields[1]),
            "pgid": int(fields[2]), "sid": int(fields[3]), "start_ticks": int(fields[19])}
    except (FileNotFoundError, ProcessLookupError):
        return None


def cleanup_registered_children(attempt_root, worker_pid, worker_start_ticks, *, reason):
    """Signal only source-bound independent child groups of this exact worker.

    Immutable registration permits verification after the worker has exited.
    Calling both before and after worker closure covers registration races.
    """
    root = Path(attempt_root).resolve()
    result = {"version": "v051-registered-child-cleanup", "worker_pid": worker_pid,
        "worker_start_ticks": worker_start_ticks, "reason": reason, "at": time.time(),
        "records": [], "unresolved": []}
    for path in sorted(root.rglob("process.json")):
        row = {"record": ref(path)}
        try:
            saved = read_json(path)
            if saved.get("version") != "v051-registered-child-process":
                continue
            checked(saved["spec"])
            if (saved["parent_pid"] != worker_pid
                    or saved["parent_start_ticks"] != worker_start_ticks
                    or saved["pgid"] != saved["pid"] or saved["sid"] != saved["pid"]
                    or saved["pid"] in {os.getpid(), worker_pid, os.getpgrp()}):
                raise ValueError("Registered process does not bind this worker and independent session")
            current = registered_process_identity(saved["pid"])
            row["registered"] = saved
            row["observed"] = current
            if current is None:
                row["action"] = "already_absent"
            else:
                if any(current.get(key) != saved[key] for key in ("pid", "start_ticks", "pgid", "sid")):
                    raise ValueError("Live process identity differs from immutable registration")
                try:
                    os.killpg(saved["pgid"], signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    live = registered_process_identity(saved["pid"])
                    if live is None or live.get("state") == "Z":
                        break
                    time.sleep(.05)
                live = registered_process_identity(saved["pid"])
                if live is not None and live.get("state") != "Z":
                    if any(live.get(key) != saved[key] for key in ("pid", "start_ticks", "pgid", "sid")):
                        raise ValueError("Process identity changed before escalation")
                    try:
                        os.killpg(saved["pgid"], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                row["action"] = "owned_group_terminated"
        except (KeyError, ValueError, OSError) as error:
            row["error"] = str(error)
            result["unresolved"].append(str(path))
        result["records"].append(row)
    result["passed"] = not result["unresolved"]
    target = root / ("child-cleanup-" + str(time.time_ns()) + ".json")
    write(target, result)
    return result
