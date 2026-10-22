"""Install four finite supplementary read-only timers; keep original timers intact."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/software-benchmark-v055/six-hour-monitor-r1"
COLLECTOR = ROOT / "tools/observe_qwen_manager_r7_hourly_v055_r1.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--source-sha256", required=True)
    args = parser.parse_args()
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != args.source_sha256:
        raise ValueError("supplement deployment source changed")
    raw = (OUT / "manager-r7-plan.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.plan_sha256:
        raise ValueError("supplement plan changed")
    plan = json.loads(raw)
    if (plan["indices"] != [3, 4, 5, 6] or plan["manager_unit"] !=
            "proworksim-v054-formal-queue-supervision-r7.service"):
        raise ValueError("supplement scope changed")
    if (plan["collector"]["path"] != str(COLLECTOR) or
            hashlib.sha256(COLLECTOR.read_bytes()).hexdigest() != plan["collector"]["sha256"]):
        raise ValueError("supplement collector changed")
    original = (OUT / "schedule.json").read_bytes()
    if hashlib.sha256(original).hexdigest() != plan["original_schedule_sha256"]:
        raise ValueError("original schedule changed")
    original_samples = {row["index"]: row for row in json.loads(original)["scheduled_samples"]}
    commands = []
    for index, sample in zip(plan["indices"], plan["scheduled_samples"], strict=True):
        due = datetime.fromisoformat(sample["due_utc"])
        expected = datetime.fromisoformat(original_samples[index]["due_utc"]) + timedelta(seconds=5)
        if sample["index"] != index or due != expected:
            raise ValueError("supplement timing must be original indices 3..6 plus five seconds")
        if due <= datetime.now(timezone.utc):
            raise ValueError("supplement checkpoint is no longer in the future")
        unit = f"proworksim-v055-six-hour-monitor-r1-manager-r7-{index}"
        commands.append(["systemd-run", "--user", f"--unit={unit}", "--collect",
            f"--on-calendar={due:%Y-%m-%d %H:%M:%S} UTC", "--timer-property=AccuracySec=1s",
            f"--property=WorkingDirectory={ROOT}", "--property=CPUQuota=100%",
            "--property=MemoryMax=512M", "--property=RuntimeMaxSec=120", "--property=Restart=no",
            str(ROOT / ".venv/bin/python"), "-B", str(COLLECTOR),
            "--index", str(index), "--plan-sha256", args.plan_sha256])
    intent = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "plan_sha256": args.plan_sha256, "deployment_source_sha256": args.source_sha256,
              "commands": commands, "original_timers_changed": False,
              "action": "Four single read-only r7 manager supplements; no experimental dispatch or repair"}
    with (OUT / "manager-r7-deployment-intent.json").open("x") as stream:
        json.dump(intent, stream, indent=2)
        stream.write("\n")
    for index, command in zip(plan["indices"], commands, strict=True):
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        receipt = {"index": index, "observed_utc": datetime.now(timezone.utc).isoformat(),
                   "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        with (OUT / f"manager-r7-deployment-{index:02d}.json").open("x") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
        print(json.dumps(receipt))
        if result.returncode:
            raise RuntimeError("Supplement timer installation failed; retain any installed timers")


if __name__ == "__main__":
    main()
