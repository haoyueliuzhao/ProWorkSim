"""Read-only snapshot of the original twelve passive-pilot identities."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/software-benchmark-v203-2-1"


def read(path):
    return json.loads(path.read_text()) if path.is_file() else None


def snapshot():
    now = time.time()
    main = BASE / "passive-pilot12-r2/api-coordinator"
    leaf = BASE / "passive-requests-leaf-r3/api-coordinator"
    continuation = BASE / "passive-pilot10-r4/api-coordinator"
    progress = read(main / "progress.json") or {}
    continuation_progress = read(continuation / "progress.json") or {}
    measurement = []
    for path in sorted((main / "measurement-records").glob("*.json")):
        value = read(path)
        measurement.append({"physical_index": int(path.stem),
            "execution_state": value.get("execution_state"),
            "integrity_status": value.get("integrity", {}).get("status"),
            "dimensions": {k: v.get("status") for k, v in
                value.get("integrity", {}).get("dimensions", {}).items()},
            "reconciliation": value.get("reconciliation"), "source": str(path)})
    recovered = []
    recovery = ROOT / "artifacts/software-benchmark-v203-2-1/capture-recovery-r4"
    for path in sorted(recovery.glob("*-measurement.json")):
        value = read(path)
        recovered.append({"source": str(path), "episode_id": value.get("episode_id"),
            "integrity_status": value.get("integrity", {}).get("status"),
            "reconciliation": value.get("reconciliation")})
    outcomes = {}
    for directory in (main, continuation):
        for row in (read(directory / "task-outcomes.json") or {}).get("rows", []):
            outcomes[row["slot_id"]] = row
    ledger = BASE / "passive-pilot12-r1/ledgers/pilot.sqlite"
    db = sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    with db:
        rows = list(db.execute("SELECT slot_id, status, usage_json, settled_nanoyuan, reserved_nanoyuan FROM requests"))
    db.close()
    states, tokens, settled, unresolved, called_slots = {}, 0, 0, 0, {}
    for row in rows:
        slot = called_slots.setdefault(row["slot_id"], {"physical_calls": 0, "known_tokens": 0})
        slot["physical_calls"] += 1
        states[row["status"]] = states.get(row["status"], 0) + 1
        if row["usage_json"]:
            usage = json.loads(row["usage_json"])
            amount = int(usage["prompt_tokens"]) + int(usage["completion_tokens"])
            tokens += amount
            slot["known_tokens"] += amount
        if row["settled_nanoyuan"] is not None:
            settled += row["settled_nanoyuan"]
        elif row["status"] != "settled":
            unresolved += row["reserved_nanoyuan"]
    ca = read(BASE / "requests-ca-r3/result.json")
    return {"observed_unix": now, "planned_tasks": 12, "repository_count": 10,
        "cash_cap_CNY": "150.00", "ledger": str(ledger),
        "physical_request_states": states, "known_actual_tokens": tokens,
        "called_original_slots": called_slots,
        "settled_peak_rate_upper_CNY": settled / 1e9,
        "unresolved_request_reservation_CNY": unresolved / 1e9,
        "parent_progress_age_seconds": now - progress["unix"] if "unix" in progress else None,
        "parent_progress": progress, "parent_engineering_gate": read(main / "engineering-gate.json"),
        "parent_finalization": read(main / "coordinator-finalization.json"),
        "completed_measurements": measurement,
        "recovered_first_two_measurements": recovered,
        "recovered_engineering_gate": read(recovery / "engineering-gate.json"),
        "continuation_progress": continuation_progress or None,
        "continuation_progress_age_seconds": now - continuation_progress["unix"]
            if "unix" in continuation_progress else None,
        "continuation_finalization": read(continuation / "coordinator-finalization.json"),
        "merged_original_task_outcomes": list(outcomes.values()),
        "outcomes_available_only_after_corresponding_queue_closure": True,
        "Requests_CA_result": ca,
        "Requests_leaf_waiter": read(leaf / "waiting-status.json"),
        "Requests_leaf_held": read(leaf / "held-before-model.json"),
        "Requests_leaf_finalization": read(leaf / "coordinator-finalization.json"),
        "no_new_API_or_Docker_operations": True,
        "snapshot_not_live_process_liveness_proof": True}


if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False, indent=2))
