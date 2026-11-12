"""Isolate unknown API outcomes only while their original full cash bound remains.

This module reads the one frozen CNY1500 ledger. It never settles, refunds,
releases, rewrites, or replays an uncertain request. Original reserve/cooldown
and hard-halt decisions remain authoritative.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
import json
import re
import sqlite3
import types

from . import software_benchmark_deepseek_api_v064 as api
from . import software_benchmark_deepseek_runtime_v064 as predecessor
from .software_benchmark_candidates_v054 import reference

VERSION = "v072-completely-reserved-uncertainty-isolation-r1"
LEDGER = predecessor.LEDGER
QUALIFICATION = predecessor.QUALIFICATION
MAX_CONCURRENCY = predecessor.MAX_CONCURRENCY
_ledger_read = predecessor._ledger_read

# This is the outer client's transport/response-processing boundary, rather
# than a whitelist of arbitrary application exceptions or new billing states.
LOCAL_UNKNOWN_ERRORS = frozenset({
    "TimeoutError", "APIUncertainFailure", "ConnectionError", "ConnectionAbortedError",
    "ConnectionResetError", "BrokenPipeError", "OSError", "SSLError", "SSLEOFError",
    "RemoteDisconnected", "IncompleteRead", "JSONDecodeError", "AttributeError",
})
ABSENT_SETTLEMENT_FIELDS = (
    "settled_nanoyuan", "settled_utc", "usage_json", "response_id", "response_model",
    "system_fingerprint", "response_sha256", "settled_peak_nanoyuan", "tariff_basis_json",
)


@lru_cache(maxsize=1)
def original_rows():
    """The complete original panel is immutable; no score enters admission."""
    planned = predecessor.policy.load(reference(predecessor.policy.PLAN_FILE))["rows"]
    rows = {row["slot_id"]: row for row in planned}
    if len(planned) != 6000 or len(rows) != 6000:
        raise ValueError("The complete original identity panel is required")
    return rows


def validate_bounded_uncertainty(db, *, rows=None):
    """Check one existing read transaction; retain every unknown reservation."""
    raw = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
    if raw is None:
        raise ValueError("missing_original_money_policy")
    policy = json.loads(raw[0])
    if policy != {**api.POLICY, "max_concurrency": MAX_CONCURRENCY}:
        raise ValueError("original_money_policy_identity_changed")
    if db.execute("SELECT 1 FROM metadata WHERE name='halted'").fetchone():
        raise ValueError("original_ledger_hard_halt")
    statuses = dict(db.execute("SELECT status,COUNT(*) FROM requests GROUP BY status"))
    if set(statuses) - {"settled", "reserved", "uncertain"}:
        raise ValueError("unsupported_request_status")
    expected = (policy["input_reservation_tokens"] * policy["peak_nanoyuan_per_token"]["miss"]
                + policy["absolute_output_reservation_tokens"] * policy["peak_nanoyuan_per_token"]["output"])
    if (expected != api.ABSOLUTE_RESERVATION_NANOYUAN
            or policy["request_reservation_nanoyuan"] != expected
            or policy["cap_nanoyuan"] != api.CAP_NANOYUAN):
        raise ValueError("absolute_provider_cash_bound_changed")
    uncertain = [dict(row) for row in db.execute("SELECT * FROM requests WHERE status='uncertain' ORDER BY request_id")]
    rows = (original_rows() if rows is None else rows) if uncertain else {}
    for item in uncertain:
        identity = item["request_id"]
        slot = item["slot_id"]
        row = rows.get(slot)
        prefix = str(slot) + ":"
        attempt = identity[len(prefix):] if isinstance(identity, str) and identity.startswith(prefix) else ""
        if (row is None or row.get("slot_id") != slot or not str(slot).startswith("v064:")
                or row.get("model_key") != "DEEPSEEK" or row.get("input_plus_output_tokens") != 5_000_000
                or row.get("condition_id") != item["condition"]
                or item["condition"] not in {"DEEPSEEK_REF_B5000K", "DEEPSEEK_PROJECT_B5000K"}
                or len(attempt) != 4 or not attempt.isdigit() or not 1 <= int(attempt) <= 512
                or item["usage_id"] not in {"agent", "condenser"}
                or re.fullmatch(r"[0-9a-f]{64}", item["request_sha256"] or "") is None):
            raise ValueError("uncertain_request_identity_not_original_5M")
        if (type(item["reserved_nanoyuan"]) is not int or item["reserved_nanoyuan"] != expected
                or type(item["max_output_tokens"]) is not int or item["max_output_tokens"] != api.MAX_OUTPUT_TOKENS
                or type(item["prompt_upper_bound"]) is not int or not 1 <= item["prompt_upper_bound"] <= api.MAX_INPUT_TOKENS
                or any(item[field] is not None for field in ABSENT_SETTLEMENT_FIELDS)):
            raise ValueError("uncertain_request_not_fully_unsettled_and_reserved")
        reserved = datetime.fromisoformat(item["reserved_utc"])
        if reserved.tzinfo is None:
            raise ValueError("uncertain_request_reservation_time_unbound")
        failure = json.loads(item["failure_json"] or "null")
        if not isinstance(failure, dict):
            raise ValueError("uncertain_failure_evidence_missing")
        http = failure.get("http_status")
        transient_http = http is None or (type(http) is int and (http in {400, 429} or 500 <= http < 600))
        if (failure.get("reason") != "attempt_not_proven_settled_no_automatic_retry"
                or failure.get("shared_system_failure") is not True
                or failure.get("error_type") not in LOCAL_UNKNOWN_ERRORS or not transient_http):
            raise ValueError("uncertain_failure_is_not_bounded_transport_or_response_processing")
        if (db.execute("SELECT 1 FROM response_observations WHERE request_id=?", (identity,)).fetchone()
                or db.execute("SELECT 1 FROM provider_protocol_events WHERE request_id=?", (identity,)).fetchone()):
            raise ValueError("uncertain_request_has_unreconciled_response_or_protocol_evidence")
    return {
        "request_statuses": statuses,
        "bounded_uncertain_count": len(uncertain),
        "bounded_uncertain_request_ids": [item["request_id"] for item in uncertain],
        "isolated_uncertain_slot_ids": sorted({item["slot_id"] for item in uncertain}),
        "bounded_uncertain_reserved_nanoyuan": expected * len(uncertain),
        "original_absolute_reservation_nanoyuan_per_request": expected,
        "uncertain_cash_reservations_retained": True,
        "unknown_usage_reclassified_as_zero": False,
        "automatic_retry": False,
    }


def _original_status_in_snapshot(db):
    @contextmanager
    def same_snapshot():
        yield db

    original = predecessor.budget_status
    namespace = {**original.__globals__, "_ledger_read": same_snapshot,
                 "QUALIFICATION": QUALIFICATION, "LEDGER": LEDGER}
    bound = types.FunctionType(original.__code__, namespace, original.__name__, original.__defaults__, original.__closure__)
    bound.__kwdefaults__ = dict(original.__kwdefaults__ or {})
    return bound()


def budget_status():
    """Use original admission and validate uncertainty in the same read snapshot."""
    value = {}
    try:
        with _ledger_read() as db:
            value = _original_status_in_snapshot(db)
            if value.get("state") != "shared_halted":
                value = {**value, **validate_bounded_uncertainty(db)}
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, predecessor.APIQualificationPending) as error:
        value = {**value, "state": "shared_halted", "can_start_generation": False,
            "temporary_wait": False, "reason": "bounded_uncertainty_validation_failed:" + str(error)}
    return {**value, "version": VERSION, "failure_scope": "API", "qwen_stop_required": False,
        "ledger_path": str(LEDGER), "cap_CNY": "1500.00", "new_cash_budget": False,
        "new_neutral_calls": 0, "ledger_records_modified": False,
        "uncertainty_validation_scope": "same_read_transaction_as_original_budget_status"}
