#!/usr/bin/env python3
"""Install the six finite read-only observation timers requested by the user."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/software-benchmark-v055/six-hour-monitor-r1"
SCHEDULE_SHA = "6e60866a40b613e10999acc7ce8093b9fe983c8d12a4e5c3e2be142c213159a6"
COLLECTOR_SHA = "f3810815c329ce2158d6b836d18e04bbd00ede6c5f00022a127821c5e7e76260"
COLLECTOR = ROOT / "tools/observe_nine_conditions_hourly_v055_r1.py"


def main() -> None:
    schedule_bytes = (OUT / "schedule.json").read_bytes()
    if hashlib.sha256(schedule_bytes).hexdigest() != SCHEDULE_SHA:
        raise RuntimeError("Schedule identity changed")
    if hashlib.sha256(COLLECTOR.read_bytes()).hexdigest() != COLLECTOR_SHA:
        raise RuntimeError("Collector identity changed")
    schedule = json.loads(schedule_bytes)
    started = datetime.fromisoformat(schedule["started_utc"])
    if datetime.now(timezone.utc) >= started + timedelta(hours=1):
        raise RuntimeError("First future checkpoint is no longer in the future")
    commands = []
    for index in range(1, 7):
        due = started + timedelta(hours=index)
        unit = f"proworksim-v055-six-hour-monitor-r1-sample-{index}"
        commands.append([
            "systemd-run", "--user", f"--unit={unit}", "--collect",
            f"--on-calendar={due:%Y-%m-%d %H:%M:%S} UTC",
            "--timer-property=AccuracySec=1s",
            f"--property=WorkingDirectory={ROOT}",
            "--property=CPUQuota=100%", "--property=MemoryMax=512M",
            "--property=RuntimeMaxSec=120", "--property=Restart=no",
            str(ROOT / ".venv/bin/python"), "-B", str(COLLECTOR),
            "--index", str(index), "--schedule-sha256", SCHEDULE_SHA,
        ])
    intent = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "schedule_sha256": SCHEDULE_SHA,
        "collector_sha256": COLLECTOR_SHA,
        "commands": commands,
        "action": "Six finite read-only observations; no experiment dispatch or repair",
    }
    with (OUT / "timer-deployment-intent.json").open("x") as stream:
        json.dump(intent, stream, indent=2)
        stream.write("\n")
    for index, command in enumerate(commands, 1):
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        receipt = {
            "index": index, "observed_utc": datetime.now(timezone.utc).isoformat(),
            "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
        }
        with (OUT / f"timer-deployment-{index:02d}.json").open("x") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
        print(json.dumps(receipt))
        if result.returncode:
            raise RuntimeError(f"Timer {index} installation failed; retain prior timers")


if __name__ == "__main__":
    main()
