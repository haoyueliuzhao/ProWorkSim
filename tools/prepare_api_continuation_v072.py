"""Prepare immutable unused-5M recovery evidence without API or runtime operations."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import sqlite3
import time

from proworksim import software_benchmark_api_recovery_scope_v072 as scope
from proworksim import software_benchmark_api_expansion_scope_v069 as prior_scope
from proworksim import software_benchmark_dispatch_v066 as primary
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import atomic_write, json_bytes

VERSION = "v072-unused-5M-bounded-uncertainty-inventory-r1"
ROOT = scope.ROOT


def load(ref):
    return json.loads(checked(ref).read_bytes())


def retained_generation(prior, closed, scheduled):
    result = dict(prior)
    for slot, entry in closed.items():
        if (slot in scheduled or entry.get("entered") is True or entry.get("result")
                or entry.get("not_started_reason") == "environment_not_qualified"):
            result[slot] = entry
    return result


def prepare_inventory():
    if scope.INVENTORY_FILE.exists() or scope.HANDOFF_FILE.exists():
        raise FileExistsError("An immutable v072 inventory already exists")
    prior_ref = reference(prior_scope.INVENTORY_FILE)
    summary_ref = reference(prior_scope.API_ROOT / "run-summary.json")
    prior, summary = load(prior_ref), load(summary_ref)
    release_ref = reference(prior_scope.API_ROOT / "coordinator-capacity-released.json")
    if (summary.get("failure") is not None or prior_scope.LEASE_FILE.exists()
            or load(release_ref).get("quiescent") is not True):
        raise ValueError("The old API coordinator must be closed and its auxiliary reservation released")
    rows = load(reference(primary.PLAN_FILE))["rows"]
    target_rows = [row for row in rows if row["model_key"] == "DEEPSEEK" and row["input_plus_output_tokens"] == 5_000_000]
    if len(rows) != 6000 or len(target_rows) != 1000:
        raise ValueError("Preserve the full original plan and its two 500-task API conditions")
    targets = {row["slot_id"]: row for row in target_rows}
    events_ref = reference(prior_scope.API_ROOT / "events.jsonl")
    events = [json.loads(line) for line in checked(events_ref).read_bytes().splitlines() if line]
    scheduled = {event["slot_id"] for event in events if event.get("kind") == "generation_scheduled"}
    excluded = scheduled | set(prior["excluded_old_scheduled_slot_ids"])
    generation = retained_generation(prior["generation"], summary["generation"], scheduled)
    generation = {slot: entry for slot, entry in generation.items() if slot in targets}
    scores = {slot: entry for slot, entry in {**prior["scores"], **summary["scores"]}.items() if slot in targets}
    deliveries = {slot: entry for slot, entry in {**prior["deliveries"], **summary["deliveries"]}.items() if slot in targets}
    cursor_raw = scope.PRIMARY_CURSOR.read_bytes()
    cursor = json.loads(cursor_raw)
    if cursor.get("failure") is not None:
        raise ValueError("The independent primary reports an unresolved shared safety failure")
    ledger = primary.PREDECESSOR_ROOT / "api-budget/ledger.sqlite3"
    from proworksim.software_benchmark_deepseek_budget_v072 import budget_status, validate_bounded_uncertainty
    with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        if db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]:
            raise ValueError("All predecessor API requests must be physically closed before new preparation")
        proof = validate_bounded_uncertainty(db, rows={row["slot_id"]: row for row in rows})
        requests = dict(db.execute("SELECT slot_id,COUNT(*) FROM requests GROUP BY slot_id"))
        uncertain = [dict(row) for row in db.execute("SELECT * FROM requests WHERE status='uncertain' ORDER BY request_id")]
    status = budget_status()
    if status["state"] != "ready":
        raise ValueError("The unchanged ledger cannot currently admit a fresh request")
    claim_roots = [primary.PREDECESSOR_ROOT / "resource-claims", primary.BATCH_ROOT / "resource-claims"]
    candidate_roots = [primary.PREDECESSOR_ROOT / "episodes", primary.BATCH_ROOT / "episodes"]
    permitted = set(prior["allowed_generation_slot_ids"])
    audit, allowed = [], []
    for row in target_rows:
        slot, index = row["slot_id"], row["slot_index"]
        claims = [str(path) for folder in claim_roots for role in ("actor", "controller", "volume")
                  if (path := folder / f"{role}-{index}.json").exists()]
        candidates = [str(folder / str(index)) for folder in candidate_roots if (folder / str(index)).exists()]
        environment = cursor["qualifications"].get(row["instance_id"], {}).get("status")
        reason = ("preserved_generation" if slot in generation else "ever_scheduled_no_replay" if slot in excluded
            else "physical_identity_consumed" if claims else "candidate_or_partial_episode_exists" if candidates
            else "API_request_exists" if requests.get(slot) else "outside_prior_allowlist" if slot not in permitted
            else "environment_not_qualified" if environment == "not_qualified" else "unused_original_5M")
        if reason == "unused_original_5M":
            allowed.append(slot)
        audit.append({"slot_id": slot, "slot_index": index, "reason": reason,
            "claims": claims, "candidate_directories": candidates, "API_request_count": requests.get(slot, 0)})
    scope.BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    snapshots = scope.BATCH_ROOT / "preparation-snapshot-r1"
    snapshots.mkdir()
    (snapshots / "primary-cursor.json").write_bytes(cursor_raw)
    proof_ref = write_new(snapshots / "bounded-uncertainty.json", {"version": VERSION,
        "proof": proof, "requests": uncertain, "cash_status": status,
        "existing_records_modified": False, "fees_released": False, "automatic_retry": False})
    audit_ref = write_new(snapshots / "slot-admission-audit.json", {"version": VERSION, "rows": audit})
    old_usage = load(reference(prior_scope.API_ROOT / "actual-usage-records.json"))["record_files"]
    record_files = {}
    usage_folder = snapshots / "usage-records"
    usage_folder.mkdir()
    for slot in generation:
        ref = old_usage.get(slot) or prior["usage_record_files"].get(slot)
        if ref is not None:
            path = usage_folder / f"{targets[slot]['slot_index']}.json"
            path.write_bytes(checked(ref).read_bytes())
            record_files[slot] = reference(path)
    handoff = {"version": VERSION, "predecessor_summary": summary_ref, "predecessor_events": events_ref,
        "predecessor_auxiliary_release": release_ref, "original_inventory": prior_ref,
        "old_scheduled_slot_ids": sorted(excluded), "bounded_uncertainty": proof_ref,
        "admission_audit": audit_ref, "created_unix": time.time(), "runtime_operations": 0,
        "all_old_scheduled_consumed_or_candidate_identities_excluded": True}
    handoff_ref = write_new(scope.HANDOFF_FILE, handoff)
    inventory = {"version": VERSION, "original_plan": reference(primary.PLAN_FILE),
        "predecessor_summary": summary_ref, "predecessor_inventory": prior_ref, "handoff": handoff_ref,
        "generation": generation, "scores": scores, "deliveries": deliveries,
        "qualifications": cursor["qualifications"], "retry_zero_generation": {},
        "usage_record_files": record_files, "API_ledger": str(ledger),
        "allowed_generation_slot_ids": allowed, "allowed_generation_slot_indices": [targets[slot]["slot_index"] for slot in allowed],
        "excluded_old_scheduled_slot_ids": sorted(excluded), "old_owned_pending": {}, "unused_score_jobs": [],
        "bounded_uncertainty": proof_ref, "admission_audit": audit_ref,
        "planned_API_slots": 1000, "input_plus_output_tokens": 5_000_000,
        "new_API_cash_budget": False, "unknown_reservations_released": False}
    ref = write_new(scope.INVENTORY_FILE, inventory)
    return {"inventory": ref, "handoff": handoff_ref, "remaining": len(allowed),
        "by_arm": dict(Counter(targets[slot]["arm"] for slot in allowed)), "cash_status": status,
        "runtime_operations": 0}


def prepare_authorization():
    """Seal reviewed sources and exact unit commands; launch is a separate action."""
    if scope.AUTH_FILE.exists():
        raise FileExistsError("Never overwrite an approved recovery source seal")
    inventory = load(reference(scope.INVENTORY_FILE))
    spec = importlib.util.spec_from_file_location("v072_prepare_launcher", ROOT / "tools/launch_api_continuation_v072.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    units = launcher.prepare()
    plan = {"version": scope.VERSION, "original_plan": reference(primary.PLAN_FILE),
        "inventory": reference(scope.INVENTORY_FILE), "handoff": reference(scope.HANDOFF_FILE),
        "API_ledger": inventory["API_ledger"], "API_total_cash_cap_CNY": "1500.00",
        "combined_cpu_cap": 152, "combined_memory_cap_GiB": 832, "existing_resource_identities_only": True,
        "planned_API_slots": 1000, "input_plus_output_tokens": 5_000_000,
        "maximum_shared_actor_lanes": 18, "minimum_grader_capacity_reserved": 2,
        "prior_expansion_authorization": reference(prior_scope.AUTH_FILE),
        "new_API_cash_budget": False, "unknown_reservations_released": False,
        "unit": units["units"]["api"]["specification"]}
    plan_ref = write_new(scope.PLAN_FILE, plan)
    paths = sorted({*list((ROOT / "src/proworksim").glob("*v072*.py")),
        *list((ROOT / "tools").glob("*v072*.py")), prior_scope.SOURCE_FILE, prior_scope.AUTH_FILE,
        scope.INVENTORY_FILE, scope.HANDOFF_FILE})
    sources_ref = write_new(scope.SOURCE_FILE, {"version": scope.VERSION, "files": [reference(path) for path in paths]})
    proposal = {"version": scope.VERSION, "plan": plan_ref, "source_index": sources_ref,
        "unit": plan["unit"], "basis": "用户要求修复并继续原5M库存，普通异常不得阻停独立任务",
        "uncertain_cash_reservations_retained": True, "same_original_1500_CNY_ledger": True,
        "old_attempts_replayed": False, "Qwen_lifecycle_operations": 0,
        "runtime_operations_in_preparation": 0}
    scope.PROPOSAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    proposal_ref = write_new(scope.PROPOSAL_FILE, proposal)
    auth = {"version": scope.VERSION, "status": "approved", "plan": plan_ref,
        "primary_authorization": reference(primary.AUTHORIZATION_FILE),
        "prior_expansion_authorization": reference(prior_scope.AUTH_FILE),
        "proposal": proposal_ref, "source_index": sources_ref, "basis": proposal["basis"]}
    atomic_write(scope.AUTH_FILE, json_bytes(auth))
    return {"plan": plan_ref, "proposal": proposal_ref, "unit": plan["unit"], "runtime_operations": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--inventory", action="store_true")
    actions.add_argument("--authorize", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare_inventory() if args.inventory else prepare_authorization(), ensure_ascii=False))
