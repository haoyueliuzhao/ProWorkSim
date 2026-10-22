"""Read only the replacement Qwen manager and bind it to a scheduled snapshot."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/software-benchmark-v055/six-hour-monitor-r1"
PLAN = OUT / "manager-r7-plan.json"
UNIT = "proworksim-v054-formal-queue-supervision-r7.service"
QUEUE = ROOT / "runs/software-benchmark-v054/formal-queue-r1/state.json"
CST = timezone(timedelta(hours=8))


def load_plan(expected_sha):
    raw = PLAN.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("r7 supplement plan hash mismatch")
    plan = json.loads(raw)
    if plan["manager_unit"] != UNIT or plan["indices"] != [3, 4, 5, 6]:
        raise ValueError("r7 supplement scope changed")
    original = (OUT / "schedule.json").read_bytes()
    if hashlib.sha256(original).hexdigest() != plan["original_schedule_sha256"]:
        raise ValueError("original schedule identity changed")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != plan["collector"]["sha256"]:
        raise ValueError("supplement collector source changed")
    return plan


def unit_status():
    result = subprocess.run(["systemctl", "--user", "show", UNIT,
        "-p", "Id", "-p", "LoadState", "-p", "ActiveState", "-p", "SubState",
        "-p", "MainPID", "-p", "Result", "-p", "InvocationID", "-p", "ActiveEnterTimestamp",
        "-p", "ExecMainStartTimestamp"], capture_output=True, text=True, timeout=15, check=True)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def queue_status(plan):
    state = json.loads(QUEUE.read_bytes())
    now = datetime.now(timezone.utc)
    binding = state.get("supervision_host", {})
    revision = binding.get("revision", {})
    return {"path": str(QUEUE), "observed_utc": now.isoformat(),
        "status": state.get("status"), "updated_utc": state.get("updated_utc"),
        "age_seconds": (now - datetime.fromisoformat(state["updated_utc"])).total_seconds(),
        "supervision_host": binding,
        "expected_revision_binding_matches": all(revision.get(key) == value
                                                  for key, value in plan["expected_revision"].items()),
        "generation_counts": dict(Counter(row["generation"]["status"] for row in state["rows"])),
        "full_queue_hash_recomputed": False}


def original_snapshot(index, plan):
    path = OUT / f"snapshot-{index:02d}.json"
    raw = path.read_bytes()
    value = json.loads(raw)
    if value.get("index") != index or value.get("schedule_sha256") != plan["original_schedule_sha256"]:
        raise ValueError("original snapshot identity differs from scheduled index")
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "index": index, "observed_utc": value["observed_utc"],
            "original_qwen_manager": value.get("manager_units", {}).get("qwen")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=int, choices=(3, 4, 5, 6))
    parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args()
    plan = load_plan(args.plan_sha256)
    target = OUT / f"manager-r7-{args.index:02d}.json"
    if target.exists():
        raise FileExistsError("immutable manager supplement already exists")
    now = datetime.now(timezone.utc)
    value = {"version": "qwen-r7-hourly-manager-supplement-v055-r1", "index": args.index,
        "observed_utc": now.isoformat(), "observed_cst": now.astimezone(CST).isoformat(),
        "plan_sha256": args.plan_sha256, "manager_unit": UNIT, "errors": [],
        "planned_original_snapshot": str(OUT / f"snapshot-{args.index:02d}.json"),
        "original_snapshot_and_schedule_not_modified": True,
        "model_calls": 0, "job_dispatches": 0, "runtime_or_services_mutated": False}
    for name, action in (("manager", unit_status),
                         ("queue", lambda: queue_status(plan)),
                         ("original_snapshot", lambda: original_snapshot(args.index, plan))):
        try:
            value[name] = action()
        except Exception as error:
            value["errors"].append({"section": name, "error_type": type(error).__name__,
                                     "error": str(error)[:1000]})
    value["collection_finished_utc"] = datetime.now(timezone.utc).isoformat()
    with target.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"output": str(target), "observed_utc": value["observed_utc"],
                      "errors": value["errors"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
