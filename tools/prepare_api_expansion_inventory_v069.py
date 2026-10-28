"""Freeze a file-only handoff to unused original DeepSeek 5M identities.

The predecessor remains alive to finish its owned work.  A fresh fail-closed
admission observation is required; no service, container, or API is operated.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402

VERSION = "v069-api-5m-original-identity-handoff-r1"
BATCH_ROOT = ROOT / "runs/software-benchmark-v069/api-5m-expansion-r1"
OLD_ROOT = ROOT / "runs/software-benchmark-v068/recovery-r1"
OLD_API = OLD_ROOT / "api-coordinator"
PRIMARY_CURSOR = OLD_ROOT / "primary-coordinator/cursor.json"
INVENTORY_FILE = BATCH_ROOT / "continuation-inventory.json"
HANDOFF_FILE = BATCH_ROOT / "handoff.json"
LEDGER = ROOT / "runs/software-benchmark-v064/full-verified-r1/api-budget/ledger.sqlite3"
CLAIM_ROOTS = (ROOT / "runs/software-benchmark-v064/full-verified-r1/resource-claims",
               ROOT / "runs/software-benchmark-v066/v064-continuation-r3/resource-claims")
PAUSE_ERROR = "desired must be an integer from 1 through 64"


def load(ref):
    return json.loads(checked(ref).read_bytes())


def pause_evidence(control, progress, *, now):
    """Old v068 accepts 1..64: its desired=0 validation failure closes admission."""
    if type(control.get("desired")) is not int or control["desired"] != 0:
        raise ValueError("Predecessor admission must remain administratively paused")
    since = control.get("since_unix")
    observed = progress.get("unix")
    if (not isinstance(since, (int, float)) or not isinstance(observed, (int, float))
            or not since <= observed <= now + 5 or now - observed > 180
            or progress.get("effective_generation_limit") != 0):
        raise ValueError("A fresh post-pause zero-admission observation is required")
    configured, error = progress.get("configured_generation_limit"), progress.get("concurrency_control_error")
    if not ((configured is None and error == PAUSE_ERROR) or (configured == 0 and error is None)):
        raise ValueError("Unknown predecessor pause semantics")
    if progress.get("failure") is not None:
        raise ValueError("Shared safety stop requires separate recovery")
    return {"desired": 0, "effective_generation_limit": 0,
            "configured_generation_limit": configured, "concurrency_control_error": error,
            "since_unix": since, "observed_unix": observed,
            "semantics": "known_validation_failure_closes_new_admission"
                if error else "explicit_zero_admission",
            "existing_futures_cancelled": False}


def scheduled_slots(events_bytes):
    """Keep every ever-scheduled identity, even a later unclaimed capacity wait."""
    if events_bytes and not events_bytes.endswith(b"\n"):
        raise ValueError("Incomplete predecessor event line; retry the snapshot")
    events = [json.loads(line) for line in events_bytes.splitlines() if line]
    return {event["slot_id"] for event in events if event.get("kind") == "generation_scheduled"}


def classify_target_rows(rows, *, generation, predecessor_allowed, old_scheduled,
                         old_owned_pending, claims, requests, qualifications):
    allowed, audit = [], []
    for row in rows:
        slot = row["slot_id"]
        consumed = claims.get(row["slot_index"], [])
        request_count = requests.get(slot, 0)
        environment = qualifications.get(row["instance_id"], {}).get("status")
        if slot in old_owned_pending:
            reason = "owned_by_predecessor_unsettled_do_not_replay"
        elif slot in generation:
            reason = "preserved_original_generation_no_replay"
        elif slot in old_scheduled:
            reason = "ever_scheduled_by_predecessor_do_not_replay"
        elif consumed:
            reason = "physical_identity_consumed_without_imported_generation"
        elif request_count:
            reason = "provider_request_consumed_without_imported_generation"
        elif slot not in predecessor_allowed:
            reason = "not_in_predecessor_unused_inventory"
        elif environment == "not_qualified":
            reason = "environment_not_qualified"
        else:
            reason = "unused_original_5m_identity"
            allowed.append(slot)
        audit.append({"slot_id": slot, "slot_index": row["slot_index"],
            "condition_id": row["condition_id"], "eligible": reason == "unused_original_5m_identity",
            "reason": reason, "physical_identity_claims": consumed,
            "API_request_count": request_count, "environment_status": environment})
    return allowed, audit


def _copy_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    return reference(path)


def _source_observation(path, data):
    return {"path": str(path), "sha256_at_snapshot": hashlib.sha256(data).hexdigest(),
            "bytes_at_snapshot": len(data), "live_source_may_advance": True}


def prepare():
    if INVENTORY_FILE.exists() or HANDOFF_FILE.exists():
        raise FileExistsError("Keep the handoff immutable; use a new revision")
    snapshots = BATCH_ROOT / "handoff-snapshot-r1"
    if snapshots.exists():
        raise FileExistsError("An earlier snapshot exists; review it before a new revision")
    inventory_ref = reference(OLD_ROOT / "continuation-inventory.json")
    prior = load(inventory_ref)
    plan = load(prior["original_plan"])
    all_rows = {row["slot_id"]: row for row in plan["rows"]}
    rows = [row for row in plan["rows"] if row["model_key"] == "DEEPSEEK"
            and row["input_plus_output_tokens"] == 5_000_000]
    if (len(all_rows) != 6000 or len(rows) != 1000
            or Counter(row["arm"] for row in rows) != {"REF": 500, "PROJECT": 500}):
        raise ValueError("Require the original two 500-task 5M conditions")
    identities = {row["slot_id"] for row in rows}
    raw = {name: (OLD_API / name).read_bytes()
           for name in ("concurrency-control.json", "progress.json", "cursor.json", "events.jsonl")}
    control, progress, cursor = (json.loads(raw[name])
                                for name in ("concurrency-control.json", "progress.json", "cursor.json"))
    pause = pause_evidence(control, progress, now=time.time())
    scheduled = scheduled_slots(raw["events.jsonl"])
    if not set(cursor["active_generation"]) <= scheduled:
        raise ValueError("An active predecessor future lacks its scheduling evidence")
    if any(slot not in all_rows or all_rows[slot]["model_key"] != "DEEPSEEK" for slot in scheduled):
        raise ValueError("Predecessor scheduled a foreign identity")
    if cursor.get("failure") is not None:
        raise ValueError("Predecessor cursor reports a shared safety failure")
    primary_bytes = PRIMARY_CURSOR.read_bytes()
    primary = json.loads(primary_bytes)
    if primary.get("failure") is not None:
        raise ValueError("Primary queue reports a shared safety failure")
    qualifications = {**prior["qualifications"], **primary["qualifications"]}
    for task, item in qualifications.items():
        if item.get("status") not in {"qualified", "not_qualified"}:
            raise ValueError("Only terminal environment qualifications may be imported")
        if item["status"] == "qualified":
            checked(item["qualification"])
    # The original seed inventory and the live API cursor own different stages.
    # Only actual entries are merged; outstanding work never becomes generation=0.
    merged = {}
    for field in ("generation", "scores", "deliveries"):
        combined = {**prior[field], **cursor[field]}
        merged[field] = {slot: entry for slot, entry in combined.items() if slot in identities}
    old_pending_ids = (scheduled - set(cursor["generation"])) | set(cursor["active_generation"])
    old_owned_pending = {slot: {
        "slot_index": all_rows[slot]["slot_index"], "condition_id": all_rows[slot]["condition_id"],
        "input_plus_output_tokens": all_rows[slot]["input_plus_output_tokens"],
        "model_key": all_rows[slot]["model_key"], "owner": str(OLD_API),
        "state": "active_predecessor_future" if slot in cursor["active_generation"]
                 else "previously_scheduled_without_terminal_cursor_entry",
        "in_new_5m_target": slot in identities, "generation_record_synthesized": False,
    } for slot in sorted(old_pending_ids)}
    claims = {}
    for directory in CLAIM_ROOTS:
        for path in directory.glob("*.json"):
            match = re.fullmatch(r"(actor|controller|volume)-(\d+)\.json", path.name)
            if match:
                claims.setdefault(int(match[2]), []).append(reference(path))
    with sqlite3.connect(LEDGER.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        requests = dict(db.execute("SELECT slot_id,COUNT(*) FROM requests GROUP BY slot_id"))
        money = [dict(zip(("status", "requests", "reserved_nanoyuan", "settled_nanoyuan"), row, strict=True))
                 for row in db.execute("SELECT status,COUNT(*),SUM(reserved_nanoyuan),SUM(COALESCE(settled_nanoyuan,0)) FROM requests GROUP BY status")]
    allowed, audit = classify_target_rows(rows, generation=merged["generation"],
        predecessor_allowed=set(prior["allowed_generation_slot_ids"]), old_scheduled=scheduled,
        old_owned_pending=old_owned_pending, claims=claims, requests=requests, qualifications=qualifications)
    # Verify the existing administrative pause and the ever-scheduled set again.
    # Finishes/score events may advance; no new dispatch is permitted in between.
    if (OLD_API / "concurrency-control.json").read_bytes() != raw["concurrency-control.json"]:
        raise ValueError("Predecessor admission control changed during the handoff")
    events_after = (OLD_API / "events.jsonl").read_bytes()
    if scheduled_slots(events_after) != scheduled:
        raise ValueError("Predecessor scheduling advanced during the handoff")
    pause_after_raw = (OLD_API / "progress.json").read_bytes()
    pause_after = pause_evidence(control, json.loads(pause_after_raw), now=time.time())
    raw["events-after.jsonl"], raw["progress-after.json"] = events_after, pause_after_raw
    refs = {name: _copy_bytes(snapshots / name, data) for name, data in raw.items()}
    refs["primary-cursor.json"] = _copy_bytes(snapshots / "primary-cursor.json", primary_bytes)
    usage, usage_sources = {}, {}
    for slot in merged["generation"]:
        row = all_rows[slot]
        live_path = OLD_API / "usage-records" / f"{row['slot_index']}.json"
        if slot in cursor["generation"] and live_path.exists():
            data = live_path.read_bytes()
            record = json.loads(data)
            if record.get("slot_id") != slot or record.get("model_key") != "DEEPSEEK":
                raise ValueError("A predecessor usage record has a foreign identity")
            usage[slot] = _copy_bytes(snapshots / "usage-records" / live_path.name, data)
            usage_sources[slot] = _source_observation(live_path, data)
        elif slot in prior["usage_record_files"]:
            ref = prior["usage_record_files"][slot]
            record = load(ref)
            if record.get("slot_id") != slot:
                raise ValueError("Original usage changed logical identity")
            usage[slot] = ref
        else:
            raise ValueError("A terminal generation entry lacks its actual usage receipt: " + slot)
    ledger_observation = {"path": str(LEDGER), "read_only_transaction": True,
        "request_counts_by_slot": requests, "statuses": money,
        "cash_cap_CNY_unchanged": "1500.00", "all_conditions_remain_charged": True,
        "requests_by_model_key": dict(Counter({"DEEPSEEK": sum(requests.values())})),
        "requests_for_5m_target": sum(requests.get(slot, 0) for slot in identities),
        "requests_for_old_owned_pending": sum(requests.get(slot, 0) for slot in old_pending_ids)}
    handoff = {"version": VERSION, "created_unix": time.time(),
        "predecessor_inventory": inventory_ref, "original_plan": prior["original_plan"],
        "old_API_root": str(OLD_API), "predecessor_remains_live": True,
        "pause": pause, "pause_after": pause_after, "snapshots": refs,
        "old_scheduled_slot_ids": sorted(scheduled),
        "excluded_old_scheduled_slot_ids": sorted(scheduled),
        "old_owned_pending": old_owned_pending,
        "old_owned_active_grading": cursor["active_grading"],
        "old_owned_pending_scores": cursor["pending_scores"],
        "old_generation_history": refs["cursor.json"],
        "old_high_budget_results_preserved": True,
        "old_high_budget_new_generation_allowed": False,
        "scheduled_then_unclaimed_still_excluded": True,
        "usage_source_observations": usage_sources,
        "ledger_snapshot": ledger_observation,
        "runtime_operations": 0, "new_model_calls": 0,
        "service_or_container_changes": False, "old_files_modified": False}
    handoff_ref = write_new(HANDOFF_FILE, handoff)
    excluded = [item for item in audit if not item["eligible"]]
    counts = {"target_slots": len(rows), "eligible_generation": len(allowed),
        "preserved_generation": len(merged["generation"]),
        "preserved_generation_statuses": dict(Counter(v["status"] for v in merged["generation"].values())),
        "eligible_by_condition": dict(Counter(all_rows[slot]["condition_id"] for slot in allowed)),
        "excluded_by_reason": dict(Counter(item["reason"] for item in excluded)),
        "old_scheduled_all_budgets": len(scheduled), "old_owned_pending_all_budgets": len(old_owned_pending),
        "old_owned_pending_5m": len(identities & old_pending_ids),
        "old_active_generation": len(cursor["active_generation"]),
        "old_active_grading": len(cursor["active_grading"]),
        "old_pending_scores": len(cursor["pending_scores"]),
        "scores": len(merged["scores"]), "deliveries": len(merged["deliveries"]),
        "qualifications": dict(Counter(item["status"] for item in qualifications.values()))}
    inventory = {"version": VERSION, "original_plan": prior["original_plan"],
        "predecessor_inventory": inventory_ref, "handoff": handoff_ref,
        "target_rows": rows, "target_slot_ids": [row["slot_id"] for row in rows],
        **merged, "usage_record_files": usage, "qualifications": qualifications,
        "retry_zero_generation": {}, "allowed_generation_slot_ids": allowed,
        "allowed_generation_slot_indices": [all_rows[slot]["slot_index"] for slot in allowed],
        "continuation_slot_ids": allowed,
        "continuation_slot_indices": [all_rows[slot]["slot_index"] for slot in allowed],
        "excluded_old_scheduled_slot_ids": sorted(scheduled), "old_owned_pending": old_owned_pending,
        "excluded_target_slots": excluded, "slot_audit": audit,
        "API_ledger": str(LEDGER), "API_total_cap_CNY_unchanged": "1500.00",
        "new_API_cash_cap": False, "unused_score_jobs": [], "unused_control_requests": [],
        "old_scoring_queue_retained_by_predecessor": True,
        "exceptions": [item for item in prior.get("exceptions", []) if item.get("slot_id") in identities],
        "counts": counts, "new_model_calls": 0, "runtime_operations": 0,
        "original_files_overwritten": False}
    inventory_ref = write_new(INVENTORY_FILE, inventory)
    return {"inventory": inventory_ref, "handoff": handoff_ref, "counts": counts}


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False, indent=2))
