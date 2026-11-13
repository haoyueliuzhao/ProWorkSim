"""Read-only aggregation of the twelve original passive-pilot results and usage."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/software-benchmark-v203-2-1"
OUT = ROOT / "artifacts/software-benchmark-v203-2-1/final-report-r1"
SOURCES = {}


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    SOURCES[str(path)] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    return json.loads(raw)


def checked(ref):
    value = read(ref["path"])
    if SOURCES[ref["path"]] != ref:
        raise ValueError("An original result reference changed: " + ref["path"])
    return value


def save(name, value):
    path = OUT / name
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("Do not overwrite an existing report identity: " + name)
    path.write_bytes(raw)


def cst(timestamp):
    dt = datetime.fromtimestamp(timestamp, ZoneInfo("Asia/Shanghai")) if isinstance(timestamp, (int, float)) else datetime.fromisoformat(timestamp).astimezone(ZoneInfo("Asia/Shanghai"))
    return dt.isoformat()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    parent = BASE / "passive-pilot12-r2/api-coordinator"
    continuation = BASE / "passive-pilot10-r4/api-coordinator"
    original = read(BASE / "passive-pilot12-r2/execution-plan-r2.json")["rows"]
    rows = {}
    for folder in (parent, continuation):
        for item in read(folder / "task-outcomes.json")["rows"]:
            rows[item["slot_id"]] = item
    if len(rows) != 12 or set(rows) != {r["slot_id"] for r in original}:
        raise ValueError("The original twelve-task denominator changed")
    ledger = BASE / "passive-pilot12-r1/ledgers/pilot.sqlite"
    connection = sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        requests = [dict(r) for r in connection.execute("SELECT request_id, logical_id, attempt_index, slot_id, member_id, usage_id, status, usage_json, settled_nanoyuan, reserved_utc, finished_utc FROM requests ORDER BY reserved_utc,request_id")]
        admissions = [dict(r) for r in connection.execute("SELECT * FROM team_admissions ORDER BY slot_id")]
    finally:
        connection.close()
    if any(r["status"] != "settled" or r["usage_json"] is None or r["settled_nanoyuan"] is None for r in requests):
        raise ValueError("Incomplete usage needs an explicit unknown report")
    per_slot, per_member, per_purpose = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    records = []
    for r in requests:
        usage = json.loads(r.pop("usage_json"))
        if r["slot_id"] not in rows:
            raise ValueError("A request belongs to a non-panel task")
        values = {"requests": 1, "input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"], "cached_input_tokens": usage["prompt_cache_hit_tokens"],
            "uncached_input_tokens": usage["prompt_cache_miss_tokens"], "cash_upper_nanoyuan": r["settled_nanoyuan"]}
        if values["input_tokens"] + values["output_tokens"] != values["total_tokens"] or values["cached_input_tokens"] + values["uncached_input_tokens"] != values["input_tokens"]:
            raise ValueError("Provider usage fields do not reconcile")
        for group, key in ((per_slot, r["slot_id"]), (per_member, r["member_id"]), (per_purpose, r["usage_id"])):
            group[key].update(values)
        records.append({**r, "usage": usage})
    table = []
    for order, original_row in enumerate(original):
        r = rows[original_row["slot_id"]]
        usage = per_slot[r["slot_id"]]
        if not r["usage_complete"] or r["unresolved_requests"] != 0 or r["actual_calls"] != usage["requests"] or r["actual_tokens_known"] != usage["total_tokens"]:
            raise ValueError("Outcome and provider usage disagree")
        generation = checked(r["generation_result"])
        quiet = checked(generation["quiescence"])
        code = checked(r["code_receipt"])
        delivery = checked(r["delivery_receipt"])
        if r["generation_status"] != "closed" or r["code_status"] != "scored" or code.get("resolved") is not r["resolved"]:
            raise ValueError("A planned task lacks a normal explicit official result")
        if not quiet.get("quiescent") or not quiet.get("all_owned_objects_removed") or quiet.get("cleanup_errors"):
            raise ValueError("Generation cleanup is not fully proven")
        # Delivery may reuse the same locked code; retain the original endpoint
        # receipt and its distinct status rather than invent another score.
        if type(r["resolved"]) is not bool or type(r["legal_delivery"]) is not bool:
            raise ValueError("Missing result must not be treated as failure")
        table.append({"order": order, "slot_id": r["slot_id"], "instance_id": r["instance_id"], "repository": original_row["repo"],
            "code_passed": r["resolved"], "delivery_passed": r["legal_delivery"], "generation_status": r["generation_status"],
            **dict(usage), "cash_upper_CNY": str(Decimal(usage["cash_upper_nanoyuan"]) / Decimal(1_000_000_000)),
            "code_receipt": r["code_receipt"], "delivery_receipt": r["delivery_receipt"], "generation_result": r["generation_result"],
            "delivery_status": r["delivery_status"], "pair_cleanup_proven": True})
    totals = Counter()
    for item in per_slot.values():
        totals.update(item)
    code_count = sum(r["code_passed"] for r in table)
    delivery_count = sum(r["delivery_passed"] for r in table)
    final = read(continuation / "run-summary.json")
    summaries = {
        "version": "v203.2.1-passive-pilot-final-report-r1", "report_date": "2026-11-13", "planned": 12,
        "repositories": len({r["repository"] for r in table}), "closed": len(table), "scored_code": len(table),
        "code_passed": code_count, "code_rate": code_count / 12, "delivery_passed": delivery_count, "delivery_rate": delivery_count / 12,
        "technical_unknown_generation": 0, "technical_unknown_code": 0, "technical_unknown_delivery": 0,
        "actual_usage": dict(totals), "mean_tokens_per_team": totals["total_tokens"] / 12,
        "mean_tokens_code_passed": sum(r["total_tokens"] for r in table if r["code_passed"]) / code_count,
        "mean_tokens_code_failed": sum(r["total_tokens"] for r in table if not r["code_passed"]) / (12 - code_count),
        "all_tokens_per_successful_delivery": totals["total_tokens"] / delivery_count,
        "cash_upper_CNY": str(Decimal(totals["cash_upper_nanoyuan"]) / Decimal(1_000_000_000)),
        "cash_cap_CNY": "150.00", "cash_remaining_CNY": str(Decimal(150) - Decimal(totals["cash_upper_nanoyuan"]) / Decimal(1_000_000_000)),
        "actual_usage_by_member": {k: dict(v) for k, v in per_member.items()},
        "actual_usage_by_purpose": {k: dict(v) for k, v in per_purpose.items()},
        "physical_request_states": dict(Counter(r["status"] for r in records)),
        "physical_retries_after_first_attempt": sum(r["attempt_index"] > 1 for r in records),
        "first_API_request_CST": cst(min(r["reserved_utc"] for r in records)),
        "last_API_response_CST": cst(max(r["finished_utc"] for r in records)),
        "queue_finished_CST": cst(final["finished_unix"]),
        "all_team_admissions_closed": len(admissions) == 12 and all(r["state"] == "closed" for r in admissions),
        "original_gate_tasks_included": True, "new_model_calls": 0, "new_scoring_calls": 0,
        "model_or_role_condition_comparison": False, "records": table,
    }
    save("summary.json", summaries)
    save("provider-usage-snapshot.json", {"source_ledger": str(ledger), "requests": records, "team_admissions": admissions, "cache_already_in_input": True})
    keys = ["order", "instance_id", "repository", "code_passed", "delivery_passed", "requests", "input_tokens", "output_tokens", "total_tokens", "cash_upper_CNY"]
    with (OUT / "tasks.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(table)
    source = Path(__file__).resolve()
    raw = source.read_bytes()
    SOURCES[str(source)] = {"path": str(source), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    save("sources.json", {"files": list(SOURCES.values()), "provider_ledger_read_only": True})
    print(json.dumps({k: summaries[k] for k in ("planned", "closed", "code_passed", "delivery_passed", "actual_usage", "cash_upper_CNY", "cash_remaining_CNY", "first_API_request_CST", "last_API_response_CST", "queue_finished_CST")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
