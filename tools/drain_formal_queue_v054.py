"""Explicitly stop dispatch at a sleeping tick, then drain using unchanged sources.

Only the attested queue controller is stopped. Independently owned episode,
grading and resident units are never signalled by this utility.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def write(path, value, *, exclusive=True):
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    with Path(path).open("xb" if exclusive else "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return ref(path)


def properties(unit):
    result = subprocess.run(["systemctl", "--user", "show", unit,
        "--property=MainPID,InvocationID,ControlGroup,ActiveState,SubState"],
        check=True, capture_output=True, text=True, timeout=10)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def identity(pid):
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return {"pid": pid, "start_ticks": int(fields[19])}


def boundary(state, age, wait_channel, poll=30):
    intents = [row["slot"]["slot_id"] for row in state["rows"]
               if row["generation"]["status"] == "intent"
               or any(score["status"] == "intent" for score in row["scores"].values())]
    return not intents and wait_channel == "hrtimer_nanosleep" and .5 <= age <= poll - 5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--controller-unit", required=True)
    parser.add_argument("--drain-unit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--wait-seconds", type=int, default=45)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if (not re.fullmatch(r"proworksim-v054-formal-queue-[a-z0-9-]+\.service", args.controller_unit)
            or not re.fullmatch(r"proworksim-v054-formal-drain-[a-z0-9-]+\.service", args.drain_unit)):
        raise ValueError("Only explicit v054 queue and distinct drain unit names are accepted")
    root, queue = args.repository.resolve(), args.queue.resolve()
    original_unit = properties(args.controller_unit)
    pid = int(original_unit["MainPID"])
    if pid <= 0 or original_unit["ActiveState"] != "active":
        raise ValueError("Original controller is not active")
    owner = identity(pid)
    argv = Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")
    if str(root / "tools/run_formal_queue_v054.py") not in argv or "run" not in argv:
        raise ValueError("The unit is not the expected formal queue process")
    deadline = time.monotonic() + min(60, max(1, args.wait_seconds))
    while time.monotonic() < deadline:
        before = ref(queue / "state.json")
        state = json.loads((queue / "state.json").read_bytes())
        if state["bindings"]["path"] not in argv or state["bindings"]["sha256"] not in argv:
            raise ValueError("Controller argv does not match this queue binding")
        age = time.time() - datetime.fromisoformat(state["updated_utc"]).timestamp()
        channel = Path(f"/proc/{pid}/wchan").read_text().strip()
        if boundary(state, age, channel):
            break
        time.sleep(.2)
    else:
        raise TimeoutError("No safe sleeping tick boundary; nothing was signalled")
    if not args.apply:
        print(json.dumps({"eligible": True, "controller": owner, "state": before,
                          "sleeping_tick_age_seconds": age, "model_calls": 0, "state_modified": False}))
        return 0
    if identity(pid) != owner or properties(args.controller_unit) != original_unit:
        raise ValueError("Controller invocation changed before its sleeping-boundary stop")
    os.kill(pid, signal.SIGSTOP)
    try:
        until = time.monotonic() + 2
        while time.monotonic() < until:
            status = Path(f"/proc/{pid}/status").read_text()
            if re.search(r"^State:\s+T", status, re.M):
                break
            time.sleep(.02)
        else:
            raise RuntimeError("Controller did not enter the stopped state")
        if identity(pid) != owner or ref(queue / "state.json") != before:
            raise RuntimeError("Tick advanced during stop; no drain migration was performed")
    except BaseException:
        if identity(pid) == owner:
            os.kill(pid, signal.SIGCONT)  # Only undo this tool's controller stop.
        raise
    subprocess.run(["systemctl", "--user", "stop", args.controller_unit], check=True, timeout=25)
    stopped = properties(args.controller_unit)
    if int(stopped["MainPID"]) != 0 or stopped["ActiveState"] not in {"inactive", "failed"}:
        raise RuntimeError("Controller did not stop; original workers were not touched")
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    with (queue / "controller.lock").open("a+") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if ref(queue / "state.json") != before:
            raise RuntimeError("Queue state changed before the explicit drain migration")
        snapshot = write(output / "state-before.json", (queue / "state.json").read_bytes())
        transition = write(output / "drain-request.json", {"version": "v054-explicit-operator-drain-v1",
            "created_utc": datetime.now(timezone.utc).isoformat(), "reason": args.reason,
            "previous_state": before, "snapshot": snapshot, "bindings": state["bindings"],
            "controller_unit_before": original_unit, "controller_identity": owner,
            "stopped_at_sleeping_tick": True, "sleeping_tick_age_seconds": age,
            "stopped_controller_only": True, "episode_or_resident_units_signalled": [],
            "frozen_source_changed": False, "drain_unit": args.drain_unit})
        state["status"] = "paused_operator_drain"
        state.setdefault("operator_drains", []).append(transition)
        state["updated_utc"] = datetime.now(timezone.utc).isoformat()
        after = write(output / "state-after.json", state)
        staged = queue / "state.operator-drain-writing"
        write(staged, Path(after["path"]).read_bytes())
        staged.replace(queue / "state.json")
        fd = os.open(queue, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    command = ["systemd-run", "--user", "--unit=" + args.drain_unit,
        "--property=Restart=no", "--property=WorkingDirectory=" + str(root),
        "--setenv=PYTHONPATH=" + str(root / "src") + ":" + str(root),
        str(root / ".venv/bin/python"), str(root / "tools/run_formal_queue_v054.py"),
        "run", "--bindings", state["bindings"]["path"], "--bindings-sha256", state["bindings"]["sha256"]]
    write(output / "launch-intent.json", {"argv": command, "drain_request": transition})
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    receipt = write(output / "launch.json", {"returncode": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr, "drain_request": transition,
        "new_generation_disabled": True, "source_revision": state["bindings"], "model_calls_by_helper": 0})
    print(json.dumps({"receipt": receipt, "drain_unit": args.drain_unit, "returncode": result.returncode}))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
