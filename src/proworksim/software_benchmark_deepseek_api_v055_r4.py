"""Absolute-model cash reservations and task-local output-bound violations.

The HTTP payload, requested max_tokens, direct transport and scientific limits
are unchanged. A response exceeding its requested output limit is never returned
to the Agent. Cash accounting retains authoritative metadata even on rejection.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from . import software_benchmark_deepseek_api_v055 as old

VERSION = "software-benchmark-v055-deepseek-direct-budget-r4"
MODEL = old.MODEL
NANOYUAN = old.NANOYUAN
CAP_NANOYUAN = old.CAP_NANOYUAN
MAX_INPUT_RESERVATION = old.MAX_INPUT_RESERVATION
MAX_OUTPUT_TOKENS = old.MAX_OUTPUT_TOKENS
ABSOLUTE_RESERVATION_NANOYUAN = (MAX_INPUT_RESERVATION * old.MISS_NANOYUAN
                                + MAX_OUTPUT_TOKENS * old.OUTPUT_NANOYUAN)
POLICY = {**old.POLICY, "version": VERSION,
    "absolute_output_reservation_tokens": MAX_OUTPUT_TOKENS,
    "request_reservation_nanoyuan": ABSOLUTE_RESERVATION_NANOYUAN,
    "payload_max_tokens_unchanged": True,
    "valid_usage_output_above_request_limit": "settle_fee_withhold_response_defer_task",
    "absolute_model_or_cash_or_identity_violation": "shared_hard_halt",
    "response_usage_identity_sha_recorded_before_validation": True,
    "historical_unknown_supplemental_holds_included_in_cap": True,
    "absolute_model_cap_is_documented_bound_not_measured_unknown_usage": True}
BudgetStopped = old.BudgetStopped
ConcurrencyBusy = old.ConcurrencyBusy
APIUncertainFailure = old.APIUncertainFailure
DirectHTTPS = old.DirectHTTPS
load_api_key = old.load_api_key
_LEGACY_LEDGER = old.BudgetLedger


class ProviderOutputBoundViolation(RuntimeError):
    """Fee is known, but the scientifically invalid response is withheld."""


def policy_text(max_concurrency=64):
    return old._json({**POLICY, "max_concurrency": max_concurrency})


def create_extension_tables(db):
    """Called only by the explicit migration, never by a normal API client."""
    db.execute("""CREATE TABLE budget_adjustments (
        adjustment_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
        amount_nanoyuan INTEGER NOT NULL CHECK(amount_nanoyuan>=0),
        reason TEXT NOT NULL, created_utc TEXT NOT NULL, evidence_json TEXT NOT NULL)""")
    db.execute("""CREATE TABLE response_observations (
        request_id TEXT PRIMARY KEY, observed_utc TEXT NOT NULL,
        response_id TEXT, response_model TEXT, response_sha256 TEXT NOT NULL,
        usage_json TEXT NOT NULL, finish_reasons_json TEXT NOT NULL)""")
    db.execute("""CREATE TABLE provider_protocol_events (
        event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, observed_utc TEXT NOT NULL,
        classification TEXT NOT NULL, scope TEXT NOT NULL, details_json TEXT NOT NULL)""")
    db.execute("""CREATE TABLE budget_policy_migrations (
        migration_id TEXT PRIMARY KEY, created_utc TEXT NOT NULL,
        previous_policy_json TEXT NOT NULL, new_policy_json TEXT NOT NULL,
        previous_halt TEXT, evidence_json TEXT NOT NULL)""")


def rows_sha256(db, table, order):
    allowed = {("requests", "request_id"), ("budget_adjustments", "adjustment_id")}
    if (table, order) not in allowed:
        raise ValueError("Only fixed audit tables may be fingerprinted")
    result = hashlib.sha256()
    for row in db.execute(f"SELECT * FROM {table} ORDER BY {order}"):
        result.update((old._json(dict(row)) + "\n").encode("utf-8"))
    return result.hexdigest()


def ledger_fingerprint(db):
    """Use under a caller-owned read/write transaction and sqlite3.Row factory."""
    policy_row = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
    raw_policy = policy_row[0]
    policy = json.loads(raw_policy)
    requests = db.execute("""SELECT COUNT(*) count,
        COALESCE(SUM(COALESCE(settled_nanoyuan,reserved_nanoyuan)),0) committed,
        COALESCE(SUM(status='reserved'),0) reserved_count FROM requests""").fetchone()
    adjustment_exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='budget_adjustments'").fetchone()
    amount = db.execute("SELECT COALESCE(SUM(amount_nanoyuan),0) FROM budget_adjustments").fetchone()[0] if adjustment_exists else 0
    halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
    return {"requests_sha256": rows_sha256(db, "requests", "request_id"),
        "request_count": requests["count"], "policy_raw_sha256": hashlib.sha256(raw_policy.encode()).hexdigest(),
        "adjustments_sha256": rows_sha256(db, "budget_adjustments", "adjustment_id") if adjustment_exists else None,
        "adjustments_nanoyuan": amount, "requests_committed_nanoyuan": requests["committed"],
        "committed_nanoyuan": requests["committed"] + amount, "reserved_count": requests["reserved_count"],
        "halted": halt[0] if halt else None, "cap_nanoyuan": policy["cap_nanoyuan"],
        "max_concurrency": policy["max_concurrency"]}


def _usage(body):
    usage = body.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("missing_authoritative_usage")
    prompt = old._integer(usage.get("prompt_tokens"), "prompt_tokens", maximum=MAX_INPUT_RESERVATION)
    output = old._integer(usage.get("completion_tokens"), "completion_tokens", maximum=MAX_OUTPUT_TOKENS)
    total = old._integer(usage.get("total_tokens"), "total_tokens")
    hit = usage.get("prompt_cache_hit_tokens")
    if hit is None:
        hit = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    hit = old._integer(hit, "prompt_cache_hit_tokens", maximum=prompt)
    miss = old._integer(usage.get("prompt_cache_miss_tokens", prompt-hit), "prompt_cache_miss_tokens", maximum=prompt)
    alternate = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", hit)
    old._integer(alternate, "alternate_cached_tokens", maximum=prompt)
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if reasoning is not None:
        old._integer(reasoning, "reasoning_tokens", maximum=output)
    if prompt != hit+miss or total != prompt+output or alternate != hit:
        raise ValueError("usage_partitions_disagree")
    if not isinstance(body.get("id"), str) or not body["id"]:
        raise ValueError("missing_provider_response_identity")
    if body.get("model") not in {old.MODEL, old.DOCUMENTED_MODEL_VERSION, old.DOCUMENTED_MODEL_VERSION.lower()}:
        raise ValueError("unexpected_provider_model_identity")
    if body.get("system_fingerprint") is not None and not isinstance(body["system_fingerprint"], str):
        raise ValueError("invalid_provider_system_fingerprint")
    return usage, output, hit*old.HIT_NANOYUAN + miss*old.MISS_NANOYUAN + output*old.OUTPUT_NANOYUAN


class BudgetLedger(_LEGACY_LEDGER):
    def __init__(self, path, *, max_concurrency=64):
        if type(max_concurrency) is not int or max_concurrency != 64:
            raise ValueError("The frozen shared API concurrency remains exactly 64")
        self.path = Path(path).resolve()
        self.max_concurrency = max_concurrency
        if not self.path.is_file():
            raise ValueError("An explicitly migrated existing budget ledger is required")
        with self._connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
            if row is None or row[0] != policy_text(max_concurrency):
                raise ValueError("Budget r4 requires the explicit sealed policy migration")
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"requests", "budget_adjustments", "response_observations", "provider_protocol_events", "budget_policy_migrations"} <= tables:
                raise ValueError("Migrated budget accounting tables are incomplete")

    @staticmethod
    def _totals(db):
        totals = _LEGACY_LEDGER._totals(db)
        amount = db.execute("SELECT COALESCE(SUM(amount_nanoyuan),0) FROM budget_adjustments").fetchone()[0]
        totals["adjustments"] = amount
        for name in ("committed", "peak_equivalent", "uncertain"):
            totals[name] += amount
        return totals

    def snapshot(self):
        with self._connect() as db:
            db.execute("BEGIN")
            totals = self._totals(db)
            halted = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
            statuses = dict(db.execute("SELECT status,COUNT(*) FROM requests GROUP BY status"))
            streak = db.execute("SELECT value FROM metadata WHERE name='system_failure_streak'").fetchone()
            cooldown = db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
        remaining = CAP_NANOYUAN-totals["committed"]
        return {**POLICY, "ledger_path": str(self.path), "max_concurrency": self.max_concurrency,
            "remaining_cny": remaining/NANOYUAN, "committed_upper_cny": totals["committed"]/NANOYUAN,
            "settled_upper_cny": totals["settled"]/NANOYUAN,
            "settled_peak_equivalent_cny": totals["settled_peak"]/NANOYUAN,
            "peak_equivalent_cny": totals["peak_equivalent"]/NANOYUAN,
            "uncertain_reserved_cny": totals["uncertain"]/NANOYUAN,
            "historical_supplemental_holds_cny": totals["adjustments"]/NANOYUAN,
            "consecutive_system_failures": int(streak[0]) if streak else 0,
            **old.cooldown_state(cooldown[0] if cooldown else None),
            "inflight_count": totals["inflight"] or 0, "attempts": totals["attempts"],
            "statuses": statuses, "halted": halted[0] if halted else None,
            "can_admit_minimum_request": not halted and remaining >= ABSOLUTE_RESERVATION_NANOYUAN}

    def reserve(self, *, request_id, slot_id, condition, usage_id, request_sha256,
                max_output_tokens, prompt_upper_bound=None):
        for name, value in (("request_id",request_id),("slot_id",slot_id),("condition",condition),("usage_id",usage_id)):
            if not isinstance(value,str) or not value or len(value)>512:
                raise ValueError("Invalid request identity: "+name)
        old._integer(max_output_tokens,"max_output_tokens",maximum=MAX_OUTPUT_TOKENS)
        if max_output_tokens == 0:
            raise ValueError("An explicit positive output bound is required")
        if prompt_upper_bound is not None:
            old._integer(prompt_upper_bound,"prompt_upper_bound")
        with self._transaction() as db:
            if db.execute("SELECT 1 FROM requests WHERE request_id=?",(request_id,)).fetchone():
                raise BudgetStopped("request_id_already_attempted_no_replay")
            halt=db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
            if halt:
                raise BudgetStopped("ledger_halted:"+halt[0])
            cooldown=db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
            if old.cooldown_state(cooldown[0] if cooldown else None)["admission_wait_seconds"]>0:
                raise ConcurrencyBusy("shared_system_failure_cooldown_before_dispatch")
            totals=self._totals(db)
            if (totals["inflight"] or 0)>=self.max_concurrency:
                raise ConcurrencyBusy("global_request_concurrency_limit")
            if totals["committed"]+ABSOLUTE_RESERVATION_NANOYUAN>CAP_NANOYUAN:
                raise BudgetStopped("global_cny_budget_reservation_insufficient")
            db.execute("""INSERT INTO requests
                (request_id,slot_id,condition,usage_id,status,request_sha256,
                 reserved_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",(request_id,slot_id,condition,usage_id,"reserved",request_sha256,
                    ABSOLUTE_RESERVATION_NANOYUAN,max_output_tokens,prompt_upper_bound,old._now()))
        return {"request_id":request_id,"reserved_nanoyuan":ABSOLUTE_RESERVATION_NANOYUAN,
                "reserved_cny":ABSOLUTE_RESERVATION_NANOYUAN/NANOYUAN}

    def settle(self,request_id,body):
        observed=old._now()
        response_sha=old._sha(body)
        hard=None; local=None; cost=None
        with self._transaction() as db:
            row=db.execute("SELECT * FROM requests WHERE request_id=?",(request_id,)).fetchone()
            if row is None or row["status"]!="reserved":
                raise ValueError("Only one live reservation can settle")
            metadata_body=body if isinstance(body,dict) else {}
            identity=metadata_body.get("id");model=metadata_body.get("model")
            choices=metadata_body.get("choices")
            finishes=([choice.get("finish_reason") for choice in choices if isinstance(choice,dict)]
                      if isinstance(choices,list) else ["invalid_or_missing_choices_container"])
            db.execute("INSERT INTO response_observations VALUES (?,?,?,?,?,?,?)",(
                request_id,observed,identity if isinstance(identity,str) else None,
                model if isinstance(model,str) else None,response_sha,old._json(metadata_body.get("usage")),
                old._json(finishes)))
            try:
                usage,output,peak_cost=_usage(body)
            except (ValueError,KeyError,TypeError,AttributeError) as error:
                hard="provider_absolute_usage_or_identity_integrity_failure"
                detail={"reason":hard,"validation_error_type":type(error).__name__,"response_metadata_retained":True}
            else:
                if peak_cost>row["reserved_nanoyuan"]:
                    hard="provider_charge_exceeded_cash_reservation"
                    detail={"reason":hard,"peak_nanoyuan":peak_cost,"reserved_nanoyuan":row["reserved_nanoyuan"]}
                elif self._totals(db)["committed"]>CAP_NANOYUAN:
                    hard="shared_committed_budget_exceeded_cap"
                    detail={"reason":hard}
                elif db.execute("SELECT 1 FROM requests WHERE response_id=? AND request_id!=?",(identity,request_id)).fetchone():
                    hard="duplicate_provider_response_identity"
                    detail={"reason":hard}
                else:
                    tariff=old.settlement_tariff(row["reserved_utc"],observed)
                    cost=(peak_cost+tariff["divisor"]-1)//tariff["divisor"]
                    if output>row["max_output_tokens"]:
                        local="provider_output_exceeded_requested_max_tokens"
                    detail={"reason":local,"requested_max_tokens":row["max_output_tokens"],
                            "completion_tokens":output,"response_withheld_from_agent":bool(local)}
                    db.execute("""UPDATE requests SET status='settled',settled_nanoyuan=?,settled_utc=?,usage_json=?,
                        response_id=?,response_model=?,system_fingerprint=?,response_sha256=?,settled_peak_nanoyuan=?,
                        tariff_basis_json=?,failure_json=? WHERE request_id=?""",(cost,observed,old._json(usage),
                            identity,model,body.get("system_fingerprint"),response_sha,peak_cost,old._json(tariff),
                            old._json(detail) if local else None,request_id))
                    db.execute("INSERT OR REPLACE INTO metadata VALUES ('system_failure_streak','0')")
                    db.execute("DELETE FROM metadata WHERE name='cooldown_until_utc'")
            if hard:
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('halted',?)",(hard,))
                db.execute("UPDATE requests SET status='uncertain',failure_json=? WHERE request_id=?",(old._json(detail),request_id))
            if hard or local:
                db.execute("INSERT INTO provider_protocol_events VALUES (?,?,?,?,?,?)",(
                    request_id+":protocol",request_id,observed,hard or local,"shared" if hard else "task",old._json(detail)))
        if hard:
            raise BudgetStopped(hard)
        if local:
            raise ProviderOutputBoundViolation(local)
        return cost/NANOYUAN


class DeepSeekClient(old.DeepSeekClient):
    """Reuse exact old payload validation/network and response-withholding path."""
    def __init__(self, *, ledger_path, api_key, allowed_tool_names, max_concurrency=64,
                 timeout_seconds=1800, transport=None):
        self.ledger=BudgetLedger(ledger_path,max_concurrency=max_concurrency)
        self.allowed_tool_names=frozenset(allowed_tool_names)
        self.transport=transport or DirectHTTPS(api_key,timeout_seconds=timeout_seconds)


DirectDeepSeekClient = DeepSeekClient
