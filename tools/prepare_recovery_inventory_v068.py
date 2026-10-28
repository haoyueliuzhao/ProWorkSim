"""Merge frozen v064, R3 Qwen and v067 API evidence without replaying identities."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402

OLD = ROOT / "runs/software-benchmark-v064/full-verified-r1"
R3 = ROOT / "runs/software-benchmark-v066/v064-continuation-r3"
API = ROOT / "runs/software-benchmark-v067/api-continuation-r1"
OUTPUT = ROOT / "runs/software-benchmark-v068/recovery-r1/continuation-inventory.json"
ARTIFACTS = ROOT / "artifacts/software-benchmark-v068/merged-inventory-r1"
LEDGER = OLD / "api-budget/ledger.sqlite3"
VERSION = "v068-merged-original-panel-recovery-inventory-r1"


def load(ref):
    return json.loads(checked(ref).read_bytes())


def classify(row, entry, result, identity_refs, api_requests, environment_status):
    """Never infer an unused actor identity from missing provider requests."""
    if entry is None:
        if identity_refs or api_requests:
            return False, "unreported_consumed_identity_or_provider_request"
        if environment_status == "not_qualified":
            return False, "environment_not_qualified"
        return True, "original_slot_not_started_identity_unconsumed"
    if entry.get("status") == "closed":
        return False, "completed_original_generation_no_replay"
    if entry.get("status") == "not_started":
        return False, "preserved_environment_nonadmission" if environment_status == "not_qualified" else "unresolved_not_started_record"
    if entry.get("status") != "technical_unknown":
        return False, "unresolved_generation_state_no_retry"
    if api_requests:
        return False, "provider_request_already_consumed_no_replay"
    if identity_refs:
        return False, "physical_identity_already_consumed_no_replay"
    error = (result or {}).get("error", {})
    trace = (result or {}).get("traceback", "")
    guard_proven = (row["model_key"] == "DEEPSEEK" and error.get("type") == "RuntimeError"
        and error.get("message") == "The primary queue reports a shared safety stop"
        and "software_benchmark_api_scope_v067.py" in trace and "primary_cursor" in trace
        and result.get("model_dispatch_started") is False and result.get("model_calls") == 0)
    if guard_proven and environment_status != "not_qualified":
        return True, "proven_guard_before_run_no_identity_no_provider_request"
    return False, "technical_unknown_without_sufficient_pre_dispatch_proof"


def prepare():
    if OUTPUT.exists() or (ARTIFACTS / "slot-audit.json").exists():
        raise FileExistsError("Keep the existing recovery inventory immutable; use a new revision")
    plan_ref = reference(OLD / "plan.json")
    plan = load(plan_ref)
    rows = {row["slot_id"]: row for row in plan["rows"]}
    if len(rows) != 6000 or Counter(row["model_key"] for row in rows.values()) != {"QWEN": 3000, "DEEPSEEK": 3000}:
        raise ValueError("The complete original twelve-condition matrix is required")
    stages = [("v064", OLD, None), ("R3_QWEN", R3, "QWEN"), ("v067_API", API, "DEEPSEEK")]
    histories, generation, scores, deliveries, usage, sources, summaries = {}, {}, {}, {}, {}, [], {}
    exceptions = {}
    for label, root, model in stages:
        summary_ref = reference(root / "coordinator/run-summary.json")
        summary = load(summary_ref)
        if not isinstance(summary.get("finished_unix"), (int, float)):
            raise ValueError("A predecessor queue has not closed")
        summaries[label] = summary
        usage_ref = reference(root / "coordinator/actual-usage-records.json")
        records = load(usage_ref)["record_files"]
        sources.append({"stage": label, "summary": summary_ref, "usage_index": usage_ref,
                        "model_authority": model or "original_both_models"})
        for field, target in (("generation", generation), ("scores", scores), ("deliveries", deliveries)):
            for slot, entry in summary[field].items():
                if slot not in rows:
                    raise ValueError("A summary introduced a foreign task identity")
                if model is not None and rows[slot]["model_key"] != model:
                    continue
                target[slot] = entry
                if field == "generation":
                    histories.setdefault(slot, []).append({"summary": summary_ref, "stage": label, "entry": entry})
        for slot, ref in records.items():
            if slot not in rows:
                raise ValueError("A usage record belongs to another panel")
            if model is None or rows[slot]["model_key"] == model:
                value = load(ref)
                if value.get("slot_id") != slot or value.get("model_key") != rows[slot]["model_key"]:
                    raise ValueError("A canonical usage record has another logical identity")
                usage[slot] = ref
        for value in summary.get("exceptions", []):
            slot = value.get("slot_id")
            if slot is None or model is None or (slot in rows and rows[slot]["model_key"] == model):
                exceptions[json.dumps(value, sort_keys=True)] = value
    qualifications = summaries["R3_QWEN"]["qualifications"]
    for task, value in qualifications.items():
        if value["status"] not in {"qualified", "not_qualified"}:
            raise ValueError("Use only established R3 environment qualification states")
        if value["status"] == "qualified":
            checked(value["qualification"])
        other = summaries["v067_API"]["qualifications"].get(task)
        if other != value:
            raise ValueError("The API and primary terminal qualification snapshots disagree")
    identity_paths = {}
    for root in (OLD, R3):
        for path in (root / "resource-claims").glob("*.json"):
            match = re.fullmatch(r"(actor|controller|volume)-(\d+)\.json", path.name)
            if match:
                identity_paths.setdefault(int(match[2]), []).append(reference(path))
    with sqlite3.connect(LEDGER.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        api_counts = dict(db.execute("SELECT slot_id,COUNT(*) FROM requests GROUP BY slot_id"))
        api_statuses = dict(db.execute("SELECT status,COUNT(*) FROM requests GROUP BY status"))
    audited, allowed, zero_deferred, guard_requeued = [], [], [], []
    for row in plan["rows"]:
        slot = row["slot_id"]
        entry, result = generation.get(slot), None
        if entry and entry.get("result"):
            result = load(entry["result"])
            if (result.get("slot_id") != slot or result.get("configuration") != row["configuration"]
                    or result.get("condition_id") != row["condition_id"]):
                raise ValueError("A generation result differs from its original frozen configuration")
        ids = identity_paths.get(row["slot_index"], [])
        count = api_counts.get(slot, 0)
        env = qualifications.get(row["instance_id"], {}).get("status")
        eligible, reason = classify(row, entry, result, ids, count, env)
        audit = {"slot_id": slot, "slot_index": row["slot_index"], "model_key": row["model_key"],
            "status": entry.get("status") if entry else "not_recorded", "eligible": eligible,
            "reason": reason, "physical_identity_claims": ids, "API_request_count": count,
            "environment_status": env, "result": entry.get("result") if entry else None}
        if eligible:
            allowed.append(slot)
            if entry:
                guard_requeued.append({**audit, "prior_entries": histories[slot]})
                generation.pop(slot)
                usage.pop(slot, None)
        elif entry is None:
            if reason != "environment_not_qualified":
                raise ValueError("An unreported consumed identity requires separate recovery: " + slot)
            generation[slot] = {"status": "not_started", "entered": False,
                "not_started_reason": reason, "qualification": qualifications[row["instance_id"]]}
        if (row["model_key"] == "DEEPSEEK" and entry and entry.get("status") == "technical_unknown"
                and result and count == 0 and result.get("model_calls") == 0
                and result.get("model_dispatch_started") is False and ids):
            quiet_ref = result.get("quiescence")
            quiet = load(quiet_ref) if quiet_ref else {}
            clean = (quiet.get("quiescent") is True and quiet.get("cleanup_errors") == []
                and quiet.get("create_result_unknown") is False and quiet.get("all_owned_objects_removed") is True
                and quiet.get("retained_objects") == [])
            error = result.get("error", {})
            trace = result.get("traceback", "")
            phase = ("guard_after_environment_before_API_request" if error.get("message") ==
                "The primary queue reports a shared safety stop" and "api_transport_factory" in trace
                else "cancel_after_actor_before_controller" if error.get("message") ==
                "Capability probe cancelled before controller creation" else "other_zero_request_failure")
            zero_deferred.append({**audit, "phase": phase, "error": error, "original_quiescence": quiet_ref,
                "owned_objects_removed": clean, "actual_API_model_requests": 0,
                "original_entered_flag": entry.get("entered"),
                "entered_flag_means_environment_not_actual_model_request": True,
                "not_in_current_allowlist": True,
                "future_restoration_requires_new_physical_identity_and_explicit_new_scope": True})
        audited.append(audit)
    # Preserve usage exactly once per logical slot. Administrative API pause
    # records written by the Qwen coordinator never override the API authority.
    usage = {slot: ref for slot, ref in usage.items() if slot in generation}
    if set(generation) != set(usage):
        raise ValueError("Every preserved generation needs its deduplicated canonical usage record")
    unused_controls, completed_controls, completed_control_requests, incomplete_controls, control_audit = [], {}, {}, [], []
    for task in plan["environments"]:
        terminal = task in qualifications
        for kind in ("gold", "empty"):
            key = "control-" + task + "-" + kind
            folder = R3 / "grading" / key
            request_path = folder / "request.json"
            if not request_path.exists():
                if not terminal:
                    raise ValueError("An unqualified task lacks its unused prepared control")
                continue
            request_ref = reference(request_path)
            consumed = (R3 / "resource-claims" / (key + ".json")).exists() or (folder / "started.json").exists()
            entry = {"resource_key": key, "instance_id": task, "patch_kind": kind,
                "request": request_ref, "identity_consumed": consumed, "environment_terminal": terminal}
            trusted = False
            if consumed:
                for name in ("completion", "receipt", "quiescence"):
                    path = folder / (name + ".json")
                    entry[name] = reference(path) if path.exists() else None
                if all(entry[name] for name in ("completion", "receipt", "quiescence")):
                    completion, receipt, quiet = (load(entry[name]) for name in ("completion", "receipt", "quiescence"))
                    trusted = (completion.get("returncode") == 0 and receipt.get("status") == "official_report"
                        and type(receipt.get("resolved")) is bool and quiet.get("quiescent") is True
                        and quiet.get("cleanup_errors") == [] and quiet.get("create_result_unknown") is False)
                    if trusted and not terminal:
                        completed_controls.setdefault(task, {})[kind] = completion
                        completed_control_requests.setdefault(task, {})[kind] = request_ref
                if not trusted:
                    entry["reason"] = "consumed_control_with_incomplete_measurement_no_retry"
                    incomplete_controls.append(entry)
                else:
                    entry["reason"] = "completed_control_preserved_no_retry"
            elif terminal:
                entry["reason"] = "environment_already_terminal_do_not_append_controls"
            else:
                entry["reason"] = "unused_original_control_identity"
                unused_controls.append(request_ref)
            control_audit.append(entry)
    unused_score_jobs = []
    for slot, entry in generation.items():
        if entry["status"] != "closed" or slot in scores:
            continue
        row = rows[slot]
        key = "score-" + str(row["slot_index"])
        folder = R3 / "grading" / key
        if (R3 / "resource-claims" / (key + ".json")).exists() or (folder / "started.json").exists():
            raise ValueError("A consumed unrecorded score must not be retried")
        request = folder / "request.json"
        unused_score_jobs.append(["code", row, reference(request) if request.exists() else entry["result"], request.exists()])
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    audit_ref = write_new(ARTIFACTS / "slot-audit.json", {"version": VERSION, "sources": sources,
        "original_plan": plan_ref, "slots": audited, "prior_generation_entries": histories,
        "API_ledger_snapshot": {"path": str(LEDGER), "statuses": api_statuses, "request_counts_by_slot": api_counts,
            "read_only_transaction": True}, "controls": control_audit,
        "scope_guard_source": reference(ROOT / "src/proworksim/software_benchmark_api_scope_v067.py"),
        "API_client_reservation_before_HTTP_source": reference(ROOT / "src/proworksim/software_benchmark_deepseek_api_v064.py")})
    zero_ref = write_new(ARTIFACTS / "zero-model-deferred-recovery.json", {"version": VERSION,
        "audit": audit_ref, "deferred": zero_deferred, "guard_before_run_requeued": guard_requeued,
        "current_allowlist_includes_deferred": False, "new_generation_started": False})
    stats = {"planned": 6000, "preserved_generation": len(generation), "eligible_generation": len(allowed),
        "eligible_by_model": dict(Counter(rows[slot]["model_key"] for slot in allowed)),
        "preserved_by_model_and_status": dict(Counter(rows[slot]["model_key"] + ":" + entry["status"]
            for slot, entry in generation.items())), "scores": len(scores), "deliveries": len(deliveries),
        "qualifications": dict(Counter(value["status"] for value in qualifications.values())),
        "zero_model_deferred": len(zero_deferred), "zero_model_phases": dict(Counter(x["phase"] for x in zero_deferred)),
        "guard_before_run_requeued": len(guard_requeued), "unused_controls": len(unused_controls),
        "completed_partial_controls": sum(len(v) for v in completed_controls.values()),
        "consumed_incomplete_controls": len(incomplete_controls), "unused_score_jobs": len(unused_score_jobs)}
    value = {"version": VERSION, "original_plan": plan_ref, "predecessor_plan": plan_ref,
        "primary_plan": reference(R3 / "plan.json"), "sources": sources, "audit": audit_ref,
        "zero_model_deferred_recovery": zero_ref, "generation": generation, "scores": scores,
        "deliveries": deliveries, "qualifications": qualifications, "retry_zero_generation": {},
        "allowed_generation_slot_ids": allowed,
        "allowed_generation_slot_indices": [rows[slot]["slot_index"] for slot in allowed],
        "continuation_slot_ids": allowed, "continuation_slot_indices": [rows[slot]["slot_index"] for slot in allowed],
        "usage_record_files": usage, "API_ledger": str(LEDGER), "API_total_cap_CNY_unchanged": "1500.00",
        "new_API_cash_cap": False, "exceptions": list(exceptions.values()),
        "unused_control_requests": unused_controls, "completed_controls": completed_controls,
        "completed_control_requests": completed_control_requests, "consumed_incomplete_controls": incomplete_controls,
        "unused_score_jobs": unused_score_jobs, "counts": stats,
        "original_result_files_overwritten": False, "new_model_calls": 0, "runtime_operations": 0}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    inventory_ref = write_new(OUTPUT, value)
    summary_ref = write_new(ARTIFACTS / "summary.json", {"version": VERSION, "inventory": inventory_ref,
        "audit": audit_ref, "zero_model_deferred_recovery": zero_ref, "counts": stats,
        "preparer": reference(__file__), "old_files_modified": False,
        "API_calls": 0, "Docker_calls": 0, "GPU_operations": 0})
    return {"inventory": inventory_ref, "summary": summary_ref, "counts": stats}


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
