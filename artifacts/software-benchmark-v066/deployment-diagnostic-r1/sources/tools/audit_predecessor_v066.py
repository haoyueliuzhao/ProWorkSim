#!/usr/bin/env python3
"""Read-only v064 evidence audit; writes only a new v066 preparation record."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim.software_benchmark_candidates_v054 import checked, reference  # noqa: E402

OLD = ROOT / "runs/software-benchmark-v064/full-verified-r1"
OUTPUT = ROOT / "artifacts/software-benchmark-v066/recovery-preparation-r1/predecessor-evidence.json"


def load(ref):
    return json.loads(checked(ref).read_bytes())


def audit():
    summary_ref = reference(OLD / "coordinator/run-summary.json")
    summary = load(summary_ref)
    ledger_path = OLD / "api-budget/ledger.sqlite3"
    db = sqlite3.connect(ledger_path.as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    api_counts = dict(db.execute("SELECT slot_id, COUNT(*) FROM requests GROUP BY slot_id"))
    api_statuses = dict(db.execute("SELECT status, COUNT(*) FROM requests GROUP BY status"))
    halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
    rows = []
    for path in sorted((OLD / "episodes").glob("*/result.json"), key=lambda p: int(p.parent.name)):
        ref = reference(path)
        result = load(ref)
        transport_ref = result.get("model_transport")
        bridge = load(transport_ref) if transport_ref else {}
        cleanup_ref = result.get("quiescence")
        cleanup = load(cleanup_ref) if cleanup_ref else {}
        ledger = result.get("ledger") or {}
        receipts = sorted((path.parent / "host-model-usage").glob("*.json"))
        api_requests = api_counts.get(result["slot_id"], 0)
        proven_zero_bridge = bool(bridge) and all(type(bridge.get(key)) is int and bridge[key] == 0
            for key in ("requests", "count_requests", "generation_requests", "failed_requests"))
        known_model_entry = bool(api_requests or receipts or ledger.get("attempts") or ledger.get("calls"))
        cleanup_complete = (cleanup.get("quiescent") is True
            and cleanup.get("all_owned_objects_removed") is True
            and cleanup.get("create_result_unknown") is False
            and cleanup.get("cleanup_errors") == [] and cleanup.get("retained_objects") == []
            and cleanup.get("create_result_unknown_roles") == []
            and result.get("model_bridge_thread_finished") is True)
        row = {key: result[key] for key in ("slot_id", "condition_id", "instance_id", "model_key", "seed")}
        row.update(slot_index=int(path.parent.name), result=ref, model_transport=transport_ref,
            cleanup=cleanup_ref, original_status=result["status"],
            original_model_dispatch_started=result.get("model_dispatch_started"),
            actual_host_receipt_count=len(receipts), authoritative_API_request_count=api_requests,
            controller_recorded_attempts=ledger.get("attempts"),
            bridge_request_counts={key: bridge.get(key) for key in (
                "requests", "count_requests", "generation_requests", "failed_requests")},
            confirmed_model_entry=known_model_entry,
            proven_zero_model=proven_zero_bridge and not known_model_entry,
            cleanup_complete=cleanup_complete,
            requeue_eligible=proven_zero_bridge and not known_model_entry and cleanup_complete)
        if row["requeue_eligible"]:
            ready_ref = reference(path.parent / "controller-ready.json")
            ready = load(ready_ref)
            actor_ref = reference(path.parent / "actor-ready.json")
            actor = load(actor_ref)
            if ready.get("model_calls") != 0 or ready.get("tool_calls") != 0 or actor.get("model_calls") != 0:
                raise ValueError("Zero-model readiness evidence disagrees")
            row.update(controller_ready=ready_ref, actor_ready=actor_ref,
                controller_ledger_files=[str(p.relative_to(path.parent)) for p in
                    (path.parent / "controller-output").rglob("*ledger*.json")],
                host_count_evidence_files=[str(p.relative_to(path.parent)) for p in
                    (path.parent / "host-api-counts").glob("*")])
            if row["controller_ledger_files"] or row["host_count_evidence_files"]:
                raise ValueError("Unexpected model activity evidence for a zero-request bridge")
            if result.get("writer_quiescence"):
                row["writer_quiescence"] = result["writer_quiescence"]
                writer = load(result["writer_quiescence"])
                row["controller_exit"] = [x["state"] for x in writer["writers"] if x["role"] == "controller"]
        rows.append(row)
    db.close()
    qualifications, exceptions = [], []
    for instance_id, entry in summary["qualifications"].items():
        if entry.get("status") != "qualified":
            exceptions.append({"instance_id": instance_id, **entry})
            continue
        q = load(entry["qualification"])
        if q.get("passed") is not True or q.get("instance_id") != instance_id:
            raise ValueError("Qualified predecessor entry lacks its immutable qualification")
        for control in q["controls"]:
            for name in ("receipt", "quiescence", "completion", "initial_container"):
                checked(control[name])
        qualifications.append({"instance_id": instance_id, "qualification": entry["qualification"],
            "passed": True, "controls": q["controls"], "plan": q["plan"]})
    scores = []
    for slot_id, score in summary["scores"].items():
        request = load(score["request"])
        folder = Path(score["request"]["path"]).parent
        receipt_ref = reference(folder / "receipt.json")
        receipt = load(receipt_ref)
        scores.append({"slot_id": slot_id, "instance_id": receipt["instance_id"],
            "condition_id": receipt["condition_id"], "status": receipt["status"],
            "resolved": receipt.get("resolved"), "request": score["request"],
            "receipt": receipt_ref, "completion": reference(folder / "completion.json"),
            "quiescence": reference(folder / "quiescence.json"),
            "candidate_lock": request.get("candidate_lock"), "endpoint": receipt["endpoint"]})
    deliveries = []
    for slot_id, entry in summary["deliveries"].items():
        delivery = load(entry["receipt"])
        deliveries.append({"slot_id": slot_id, **entry,
            "legal_submission": delivery.get("legal_submission"),
            "generation_result": delivery.get("generation_result"),
            "delivery_evidence": delivery.get("delivery_evidence")})
    value = {"version": "v066-read-only-predecessor-evidence-r1", "predecessor_summary": summary_ref,
        "predecessor_plan": reference(OLD / "plan.json"),
        "api_ledger_snapshot": {"path": str(ledger_path), "statuses": api_statuses,
            "halt": halt[0] if halt else None, "query_mode": "read_only_transaction",
            "API_request_counts_by_slot": api_counts, "mutable_ledger_not_frozen_as_whole_file": True},
        "assessment_rule": "Host FIFO counts before dispatch plus authoritative receipt/ledger absence, controller/actor readiness and complete owned-object cleanup. Intent flag alone is not model entry.",
        "model_bridge_source": reference(ROOT / "src/proworksim/software_benchmark_model_fifo_v064.py"),
        "episodes": rows, "requeue_slot_indices": [r["slot_index"] for r in rows if r["requeue_eligible"]],
        "requeue_slot_ids": [r["slot_id"] for r in rows if r["requeue_eligible"]],
        "entered_slot_indices_no_replay": [r["slot_index"] for r in rows if r["confirmed_model_entry"]],
        "qualified_environments": qualifications, "environment_exceptions_preserved": exceptions,
        "code_scores": scores, "delivery_endpoints": deliveries,
        "counts": {"episodes": len(rows), "qualified_environments": len(qualifications),
            "code_scores": len(scores), "delivery_endpoints": len(deliveries)},
        "original_files_modified": False, "API_calls": 0, "Docker_calls": 0, "GPU_operations": 0}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        raise FileExistsError("Retain the predecessor audit; use a new revision for changed evidence")
    OUTPUT.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return {"output": reference(OUTPUT), "counts": value["counts"], "requeue_slot_indices": value["requeue_slot_indices"]}


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False))
