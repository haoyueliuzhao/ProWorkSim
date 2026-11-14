"""Independent direct Flash thinking client and the new CNY 1,500 hard ledger.

The existing v055 ledger is never migrated or reopened. Low-level direct TLS,
integer accounting helpers and conservative peak-window rules are reused without
changing their module globals. Every unknown attempt keeps its absolute-model
cash reservation; experimental input/output violations are recorded and withheld.
"""
from __future__ import annotations

import http.client
import json
from pathlib import Path
import socket
import sqlite3
import ssl
import threading
import time

from . import software_benchmark_deepseek_api_v055 as transport
from . import software_benchmark_deepseek_contract_v064 as contract

VERSION = "v064-deepseek-flash-thinking-cny1500-r1"
MODEL = "deepseek-flash"
DOCUMENTED_MODEL_VERSION = "DeepSeek-V4.1-Flash-1017"
CONTEXT_TOKENS = 131072
MAX_INPUT_TOKENS = 98304
MAX_OUTPUT_TOKENS = 32768
PROVIDER_CONTEXT_TOKENS = 1048576
PROVIDER_MAX_OUTPUT_TOKENS = 393216
PROVIDER_CONCURRENCY_LIMIT = 2500
NANOYUAN = 1_000_000_000
CAP_NANOYUAN = 1500 * NANOYUAN
MISS_NANOYUAN, HIT_NANOYUAN, OUTPUT_NANOYUAN = 2000, 40, 8000
ABSOLUTE_RESERVATION_NANOYUAN = (
    PROVIDER_CONTEXT_TOKENS * MISS_NANOYUAN
    + PROVIDER_MAX_OUTPUT_TOKENS * OUTPUT_NANOYUAN
)
POLICY = {
    **transport.POLICY,
    "version": VERSION,
    "cap_nanoyuan": CAP_NANOYUAN,
    "pricing_checked_date": "2026-10-27",
    "request_reservation_nanoyuan": ABSOLUTE_RESERVATION_NANOYUAN,
    "absolute_output_reservation_tokens": PROVIDER_MAX_OUTPUT_TOKENS,
    "experimental_context_tokens": CONTEXT_TOKENS,
    "experimental_max_input_tokens": MAX_INPUT_TOKENS,
    "experimental_max_output_tokens": MAX_OUTPUT_TOKENS,
    "thinking": {"type": "enabled"},
    "reasoning_effort": "high",
    "top_p": 0.95,
    "temperature_and_penalties": "omitted; ineffective in provider thinking mode",
    "input_output_bound_violation": "settle_known_usage_withhold_response_defer_task",
    "absolute_model_or_cash_or_identity_violation": "shared_hard_halt",
    "reasoning_is_in_completion_tokens_not_added_again": True,
    "old_ledger_migration": False,
    "preparation_and_compression_share_this_cap": True,
}
BudgetStopped = contract.BudgetStopped
ConcurrencyBusy = contract.ConcurrencyBusy
APIUncertainFailure = contract.APIUncertainFailure
ProviderOutputBoundViolation = contract.ProviderOutputBoundViolation
PreDispatchBudgetStopped = contract.PreDispatchBudgetStopped
PreDispatchConcurrencyBusy = contract.PreDispatchConcurrencyBusy
load_api_key = transport.load_api_key


class DirectHTTPS(transport.DirectHTTPS):
    """One episode's cancellable TLS route; abort never affects another client."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cancelled = threading.Event()
        self._lock, self._connection, self._response = threading.Lock(), None, None

    def abort(self):
        self.cancelled.set()
        with self._lock:
            connection, response = self._connection, self._response
        sockets = []
        if connection is not None and connection.sock is not None:
            sockets.append(connection.sock)
        if response is not None:
            value = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
            if value is not None:
                sockets.append(value)
        for value in sockets:
            try:
                value.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if connection is not None:
            connection.close()

    def request(self, method, path, payload=None):
        if ((method, path) not in {("POST", "/chat/completions"), ("GET", "/models"),
                                  ("GET", "/user/balance")}
                or (method == "GET" and payload is not None)):
            raise ValueError("Only fixed official completion and free metadata endpoints are allowed")
        if self.cancelled.is_set():
            raise APIUncertainFailure("episode_transport_cancelled_no_replay")
        connection = http.client.HTTPSConnection(
            transport.HOST, 443, timeout=min(10, self.timeout_seconds), context=ssl.create_default_context())
        started = time.monotonic()
        with self._lock:
            if self._connection is not None:
                raise ValueError("Use a separate HTTP transport for each episode")
            self._connection = connection
        try:
            connection.connect()
            connection.auto_open = False
            connection.sock.settimeout(min(60, self.timeout_seconds))
            if self.cancelled.is_set():
                raise APIUncertainFailure("episode_transport_cancelled_no_replay")
            connection.request(method, path,
                body=None if payload is None else transport._json(payload).encode(),
                headers={"Authorization": "Bearer "+self._api_key, "Content-Type": "application/json",
                         "Accept": "application/json", "User-Agent": VERSION})
            response = connection.getresponse()
            with self._lock:
                self._response = response
            status, chunks, size = response.status, [], 0
            while True:
                if self.cancelled.is_set() or time.monotonic()-started > self.timeout_seconds:
                    raise APIUncertainFailure("direct_request_cancelled_or_wall_deadline")
                chunk = response.read1(min(65536, self.max_response_bytes+1-size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > self.max_response_bytes:
                    raise ValueError("API response exceeds fixed byte bound")
            if status != 200:
                error = APIUncertainFailure("non_200_response_no_retry_or_redirect")
                error.http_status = status
                raise error
            result = json.loads(b"".join(chunks))
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object")
            return result
        finally:
            connection.close()
            with self._lock:
                self._connection = self._response = None


slot_user_id = contract.slot_user_id
model_profile = contract.model_profile
validate_payload = contract.validate_payload
normalize_usage = contract.normalize_usage


class BudgetLedger(transport.BudgetLedger):
    """A fresh, cross-process ledger; v055 supplies only unchanged storage helpers."""

    def __init__(self, path, *, max_concurrency=64):
        if type(max_concurrency) is not int or not 1 <= max_concurrency <= PROVIDER_CONCURRENCY_LIMIT:
            raise ValueError("Concurrency exceeds the account-level provider limit")
        self.path = Path(path).resolve()
        self.max_concurrency = max_concurrency
        expected = transport._json({**POLICY, "max_concurrency": max_concurrency})
        # Reject another experiment's database before any schema or policy write.
        if self.path.exists():
            with sqlite3.connect(self.path.as_uri()+"?mode=ro", uri=True) as db:
                row = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
                if row is None or row[0] != expected:
                    raise ValueError("An existing ledger belongs to another immutable budget policy")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY,slot_id TEXT NOT NULL,condition TEXT NOT NULL,
                usage_id TEXT NOT NULL,status TEXT NOT NULL,request_sha256 TEXT NOT NULL,
                reserved_nanoyuan INTEGER NOT NULL,settled_nanoyuan INTEGER,
                max_output_tokens INTEGER NOT NULL,prompt_upper_bound INTEGER,
                reserved_utc TEXT NOT NULL,settled_utc TEXT,usage_json TEXT,response_id TEXT,
                response_model TEXT,system_fingerprint TEXT,response_sha256 TEXT,failure_json TEXT,
                settled_peak_nanoyuan INTEGER,tariff_basis_json TEXT)""")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS response_identity ON requests(response_id)")
            db.execute("""CREATE TABLE IF NOT EXISTS response_observations (
                request_id TEXT PRIMARY KEY,observed_utc TEXT NOT NULL,response_id TEXT,
                response_model TEXT,response_sha256 TEXT NOT NULL,usage_json TEXT NOT NULL,
                finish_reasons_json TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS provider_protocol_events (
                event_id TEXT PRIMARY KEY,request_id TEXT NOT NULL,observed_utc TEXT NOT NULL,
                classification TEXT NOT NULL,scope TEXT NOT NULL,details_json TEXT NOT NULL)""")
        with self._transaction() as db:
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('policy',?)", (expected,))
            if db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0] != expected:
                raise ValueError("An existing immutable budget cannot be reset or raised")

    def snapshot(self):
        with self._connect() as db:
            db.execute("BEGIN")
            totals = self._totals(db)
            halted = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
            statuses = dict(db.execute("SELECT status,COUNT(*) FROM requests GROUP BY status"))
            cooldown = db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
        remaining = CAP_NANOYUAN-totals["committed"]
        return {
            **POLICY, "ledger_path": str(self.path), "max_concurrency": self.max_concurrency,
            "remaining_cny": remaining/NANOYUAN,
            "committed_upper_cny": totals["committed"]/NANOYUAN,
            "settled_upper_cny": totals["settled"]/NANOYUAN,
            "settled_peak_equivalent_cny": totals["settled_peak"]/NANOYUAN,
            "peak_equivalent_cny": totals["peak_equivalent"]/NANOYUAN,
            "uncertain_reserved_cny": totals["uncertain"]/NANOYUAN,
            "inflight_count": totals["inflight"] or 0, "attempts": totals["attempts"],
            "statuses": statuses, "halted": halted[0] if halted else None,
            **transport.cooldown_state(cooldown[0] if cooldown else None),
            "can_admit_minimum_request": not halted and remaining >= ABSOLUTE_RESERVATION_NANOYUAN,
        }

    def reserve(self, *, request_id, slot_id, condition, usage_id, request_sha256,
                max_output_tokens, prompt_upper_bound=None):
        for name, value in (("request_id", request_id), ("slot_id", slot_id),
                            ("condition", condition), ("usage_id", usage_id)):
            if not isinstance(value, str) or not value or len(value) > 512:
                raise ValueError("Invalid request identity: "+name)
        transport._integer(max_output_tokens, "max_output_tokens", maximum=MAX_OUTPUT_TOKENS)
        if not max_output_tokens:
            raise ValueError("An explicit positive output bound is required")
        transport._integer(prompt_upper_bound, "prompt_upper_bound", maximum=MAX_INPUT_TOKENS)
        with self._transaction() as db:
            if db.execute("SELECT 1 FROM requests WHERE request_id=?", (request_id,)).fetchone():
                raise BudgetStopped("request_id_already_attempted_no_replay")
            halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
            if halt:
                raise BudgetStopped("ledger_halted:"+halt[0])
            cooldown = db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
            if transport.cooldown_state(cooldown[0] if cooldown else None)["admission_wait_seconds"] > 0:
                raise ConcurrencyBusy("shared_system_failure_cooldown_before_dispatch")
            totals = self._totals(db)
            if (totals["inflight"] or 0) >= self.max_concurrency:
                raise ConcurrencyBusy("global_request_concurrency_limit")
            if totals["committed"]+ABSOLUTE_RESERVATION_NANOYUAN > CAP_NANOYUAN:
                if totals["inflight"]:
                    raise ConcurrencyBusy("cash_reserved_by_inflight_requests")
                raise BudgetStopped("global_cny_budget_reservation_insufficient")
            db.execute("""INSERT INTO requests
                (request_id,slot_id,condition,usage_id,status,request_sha256,reserved_nanoyuan,
                 max_output_tokens,prompt_upper_bound,reserved_utc) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (request_id,slot_id,condition,usage_id,"reserved",request_sha256,
                 ABSOLUTE_RESERVATION_NANOYUAN,max_output_tokens,prompt_upper_bound,transport._now()))
        return {"request_id": request_id, "reserved_nanoyuan": ABSOLUTE_RESERVATION_NANOYUAN,
                "reserved_cny": ABSOLUTE_RESERVATION_NANOYUAN/NANOYUAN}

    def settle(self, request_id, body):
        observed = transport._now()
        hard = local = None
        cost = None
        with self._transaction() as db:
            row = db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None or row["status"] != "reserved":
                raise ValueError("Only a live request reservation can settle once")
            metadata = body if isinstance(body, dict) else {}
            choices = metadata.get("choices")
            finishes = ([item.get("finish_reason") for item in choices if isinstance(item, dict)]
                        if isinstance(choices, list) else ["invalid_choices"])
            response_id, model = metadata.get("id"), metadata.get("model")
            db.execute("INSERT INTO response_observations VALUES (?,?,?,?,?,?,?)", (
                request_id, observed, response_id if isinstance(response_id, str) else None,
                model if isinstance(model, str) else None, transport._sha(body),
                transport._json(metadata.get("usage")), transport._json(finishes)))
            try:
                normalized = normalize_usage(body)
                if db.execute("SELECT 1 FROM requests WHERE response_id=?", (response_id,)).fetchone():
                    raise ValueError("duplicate_provider_response_identity")
                if normalized["peak_cost_nanoyuan"] > row["reserved_nanoyuan"]:
                    raise ValueError("absolute_cash_reservation_exceeded")
                tariff = transport.settlement_tariff(row["reserved_utc"], observed)
                cost = (normalized["peak_cost_nanoyuan"]+tariff["divisor"]-1)//tariff["divisor"]
                if normalized["input_tokens"] > MAX_INPUT_TOKENS:
                    local = "provider_input_exceeds_experimental_context_boundary"
                elif normalized["input_tokens"] > row["prompt_upper_bound"]:
                    local = "provider_input_exceeds_frozen_prompt_reservation"
                elif normalized["output_tokens"] > row["max_output_tokens"]:
                    local = "provider_output_exceeds_requested_max_tokens"
                elif (len(finishes) != 1 or finishes[0] not in {"stop", "length", "tool_calls", "content_filter"}):
                    local = "provider_generation_interrupted"
                db.execute("""UPDATE requests SET status='settled',settled_nanoyuan=?,settled_utc=?,
                    usage_json=?,response_id=?,response_model=?,system_fingerprint=?,response_sha256=?,
                    settled_peak_nanoyuan=?,tariff_basis_json=? WHERE request_id=?""", (
                    cost, observed, transport._json(body["usage"]), response_id, model,
                    body.get("system_fingerprint"), transport._sha(body), normalized["peak_cost_nanoyuan"],
                    transport._json(tariff), request_id))
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('system_failure_streak','0')")
                db.execute("DELETE FROM metadata WHERE name='cooldown_until_utc'")
            except (ValueError, TypeError, KeyError) as error:
                hard = str(error)
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('halted',?)", (hard,))
                db.execute("UPDATE requests SET status='uncertain',failure_json=? WHERE request_id=?",
                           (transport._json({"reason": hard}), request_id))
            if hard or local:
                db.execute("INSERT INTO provider_protocol_events VALUES (?,?,?,?,?,?)", (
                    request_id+":protocol", request_id, observed, hard or local,
                    "shared" if hard else "task", transport._json({"usage_known": hard is None})))
        if hard:
            raise BudgetStopped(hard)
        if local:
            raise ProviderOutputBoundViolation(local, body=body)
        return cost/NANOYUAN


class DeepSeekClient:
    def __init__(self, *, ledger_path, api_key, allowed_tool_names, max_concurrency=64,
                 timeout_seconds=1800, transport=None):
        self.ledger = BudgetLedger(ledger_path, max_concurrency=max_concurrency)
        self.allowed_tool_names = frozenset(allowed_tool_names)
        self.transport = transport or DirectHTTPS(api_key, timeout_seconds=timeout_seconds)

    def fork_for_episode(self):
        """Share money authority, while keeping cancellation and sockets private."""
        if not isinstance(self.transport, DirectHTTPS):
            raise ValueError("Only the real fixed HTTPS transport can fork a runtime client")
        return type(self)(ledger_path=self.ledger.path, api_key=self.transport._api_key,
                          allowed_tool_names=self.allowed_tool_names,
                          max_concurrency=self.ledger.max_concurrency,
                          timeout_seconds=self.transport.timeout_seconds)

    def complete(self, request, *, request_id, slot_id, condition, usage_id="agent",
                 prompt_upper_bound=None):
        user_id = slot_user_id(slot_id, condition)
        if "user_id" in request and request["user_id"] != user_id:
            raise ValueError("Use the new per-slot and condition cache identity")
        request = {**request, "user_id": user_id}
        validate_payload(request, self.allowed_tool_names)
        try:
            self.ledger.reserve(request_id=request_id, slot_id=slot_id, condition=condition,
                                usage_id=usage_id, request_sha256=transport._sha(request),
                                max_output_tokens=request["max_tokens"], prompt_upper_bound=prompt_upper_bound)
        except ConcurrencyBusy as error:
            raise PreDispatchConcurrencyBusy(str(error)) from None
        except BudgetStopped as error:
            raise PreDispatchBudgetStopped(str(error)) from None
        try:
            body = self.transport.request("POST", "/chat/completions", request)
            self.ledger.settle(request_id, body)
            return body
        except (BudgetStopped, ProviderOutputBoundViolation):
            raise
        except BaseException as error:
            status = getattr(error, "http_status", None)
            self.ledger.uncertain(request_id, {
                "error_type": type(error).__name__, "http_status": status,
                "reason": "attempt_not_proven_settled_no_automatic_retry",
                "shared_system_failure": status in {None, 400, 429} or (type(status) is int and 500 <= status < 600),
            })
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise APIUncertainFailure("Request outcome unknown; cash reservation retained") from None

    def metadata(self, kind):
        paths = {"models": "/models", "balance": "/user/balance"}
        if kind not in paths:
            raise ValueError("Only free model and balance metadata are admitted")
        return self.transport.request("GET", paths[kind])


DirectDeepSeekClient = DeepSeekClient
