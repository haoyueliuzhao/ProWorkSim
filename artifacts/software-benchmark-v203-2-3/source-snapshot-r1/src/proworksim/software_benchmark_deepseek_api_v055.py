"""Direct DeepSeek Chat Completions and a shared conservative CNY budget.

No SDK, local proxy, redirect, automatic retry, search/fetch endpoint or server
tool is used. Reservations are durable before any bytes leave the process.
Unknown outcomes retain their entire reservation; reopening this ledger never
replays a request. This is independent of the frozen v054 model pipeline.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import ssl
import time

VERSION = "software-benchmark-v055-deepseek-direct-budget-r3"
MODEL = "deepseek-flash"
DOCUMENTED_MODEL_VERSION = "DeepSeek-V4.1-Flash-1017"
HOST = "api.deepseek.com"
MAX_INPUT_RESERVATION = 1_048_576
MAX_OUTPUT_TOKENS = 393_216
NANOYUAN = 1_000_000_000
CAP_NANOYUAN = 2000 * NANOYUAN
# Official CNY peak tariffs per token, frozen 2026-10-21. Idle tariffs are half.
MISS_NANOYUAN, HIT_NANOYUAN, OUTPUT_NANOYUAN = 2000, 40, 8000
PRICING_URL = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
POLICY = {
    "version": VERSION, "model": MODEL, "cap_nanoyuan": CAP_NANOYUAN,
    "input_reservation_tokens": MAX_INPUT_RESERVATION,
    "peak_nanoyuan_per_token": {"miss": MISS_NANOYUAN, "hit": HIT_NANOYUAN,
                                "output": OUTPUT_NANOYUAN},
    "pricing_source": PRICING_URL, "pricing_checked_date": "2026-10-21",
    "cost_is_conservative_upper_estimate_not_provider_invoice": True,
    "settlement_tariff": "off_peak_half_only_if_full_guarded_interval_is_off_peak",
    "peak_utc_weekdays": [0, 1, 2, 3, 4], "peak_utc_hour_intervals": [[1, 4], [6, 10]],
    "tariff_boundary_guard_seconds": 300, "holiday_discount_inferred": False,
    "immediate_halt_http_statuses": [401, 402, 403],
    "consecutive_system_failure_cooldown_threshold": 3,
    "system_failure_cooldown_initial_seconds": 30,
    "system_failure_cooldown_max_seconds": 300,
    "system_failure_cooldown_backoff": 2,
    "system_failure_cooldown_does_not_replay_requests": True,
    "system_failure_statuses": "400,429,5xx,transport_or_invalid_protocol",
    "successful_settlement_resets_failure_streak": True,
    "successful_settlement_clears_cooldown": True,
    "unknown_outcome_releases_reservation": False, "automatic_retry": False,
}


class BudgetStopped(RuntimeError):
    """No new API request is authorized; existing CPU work may finish."""


class ConcurrencyBusy(RuntimeError):
    """No request was made; wait for a different in-flight request to finish."""


class APIUncertainFailure(RuntimeError):
    """An attempt may have been billed and its reservation remains held."""


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def cooldown_state(until_utc):
    if until_utc is None:
        return {"cooldown_until_utc": None, "admission_wait_seconds": 0.0}
    until = datetime.fromisoformat(until_utc)
    if until.tzinfo is None:
        raise ValueError("Shared cooldown must contain an unambiguous timezone")
    remaining = (until - datetime.fromisoformat(_now())).total_seconds()
    return {"cooldown_until_utc": until_utc, "admission_wait_seconds": max(0.0, remaining)}


def settlement_tariff(start_utc, end_utc):
    """Half price only when the entire guarded interval is certainly off peak."""
    basis = {"reserved_utc": start_utc, "settled_utc": end_utc,
             "guard_seconds": POLICY["tariff_boundary_guard_seconds"],
             "holiday_discount_inferred": False, "divisor": 1,
             "basis": "peak_due_to_invalid_or_unbounded_interval"}
    try:
        start, end = datetime.fromisoformat(start_utc), datetime.fromisoformat(end_utc)
        if (start.tzinfo is None or end.tzinfo is None or end < start
                or end - start > timedelta(days=7)):
            return basis
        start = start.astimezone(timezone.utc) - timedelta(seconds=300)
        end = end.astimezone(timezone.utc) + timedelta(seconds=300)
    except (TypeError, ValueError, OverflowError):
        return basis
    basis.update(guarded_start_utc=start.isoformat(), guarded_end_utc=end.isoformat())
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= end:
        if day.weekday() in POLICY["peak_utc_weekdays"]:
            for lower, upper in POLICY["peak_utc_hour_intervals"]:
                if start <= day + timedelta(hours=upper) and end >= day + timedelta(hours=lower):
                    return {**basis, "basis": "peak_interval_intersects_guarded_request"}
        day += timedelta(days=1)
    return {**basis, "divisor": 2, "basis": "entire_guarded_interval_off_peak"}


def slot_user_id(slot_id, condition):
    """Opaque stable KV-cache isolation per task-condition, without user identity."""
    return "v055-" + _sha({"slot_id": slot_id, "condition": condition})


def _integer(value, name, *, maximum=None):
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise ValueError(f"Invalid nonnegative integer: {name}")
    return value


def load_api_key(env_path=None):
    """Read only DEEPSEEK_API_KEY; never source a shell or expand other values."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if env_path is not None:
        values = []
        for line in Path(env_path).read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line or line.startswith("#"):
                continue
            name, value = line.split("=", 1)
            if name.strip() != "DEEPSEEK_API_KEY":
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values.append(value)
        if len(values) != 1:
            raise ValueError("Expected exactly one DEEPSEEK_API_KEY in the designated file")
        key = values[0]
    if not isinstance(key, str) or not key or any(char.isspace() for char in key):
        raise ValueError("Missing or invalid DEEPSEEK_API_KEY")
    return key


class BudgetLedger:
    """Cross-process SQLite accounting; all costs are integer nanoyuan.

    Reservations use peak tariffs; settlements use half price only when the
    entire interval plus clock/boundary protection is certainly off peak.
    Actual provider invoices may be lower; usage is retained for reconciliation.
    """

    def __init__(self, path, *, max_concurrency=64):
        if type(max_concurrency) is not int or not 1 <= max_concurrency <= 2500:
            raise ValueError("Concurrency must be within the documented account maximum")
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_concurrency = max_concurrency
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS metadata (
                       name TEXT PRIMARY KEY, value TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY, slot_id TEXT NOT NULL,
                condition TEXT NOT NULL, usage_id TEXT NOT NULL,
                status TEXT NOT NULL, request_sha256 TEXT NOT NULL,
                reserved_nanoyuan INTEGER NOT NULL, settled_nanoyuan INTEGER,
                max_output_tokens INTEGER NOT NULL, prompt_upper_bound INTEGER,
                reserved_utc TEXT NOT NULL, settled_utc TEXT,
                usage_json TEXT, response_id TEXT, response_model TEXT,
                system_fingerprint TEXT, response_sha256 TEXT, failure_json TEXT,
                settled_peak_nanoyuan INTEGER, tariff_basis_json TEXT)""")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS response_identity ON requests(response_id)")
        with self._transaction() as db:
            expected = _json({**POLICY, "max_concurrency": max_concurrency})
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('policy',?)", (expected,))
            if db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0] != expected:
                raise ValueError("Budget ledger policy differs; cannot reset or raise an existing cap")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    @staticmethod
    def _totals(db):
        row = db.execute("""SELECT
            COALESCE(SUM(COALESCE(settled_nanoyuan,reserved_nanoyuan)),0) committed,
            COALESCE(SUM(CASE WHEN status='settled' THEN settled_nanoyuan ELSE 0 END),0) settled,
            COALESCE(SUM(CASE WHEN status='settled' THEN settled_peak_nanoyuan ELSE 0 END),0) settled_peak,
            COALESCE(SUM(COALESCE(settled_peak_nanoyuan,reserved_nanoyuan)),0) peak_equivalent,
            COALESCE(SUM(CASE WHEN status='uncertain' THEN reserved_nanoyuan ELSE 0 END),0) uncertain,
            SUM(CASE WHEN status='reserved' THEN 1 ELSE 0 END) inflight,
            COUNT(*) attempts FROM requests""").fetchone()
        return dict(row)

    def snapshot(self):
        with self._connect() as db:
            db.execute("BEGIN")
            totals = self._totals(db)
            halted = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
            statuses = dict(db.execute("SELECT status,COUNT(*) FROM requests GROUP BY status"))
            streak = db.execute("SELECT value FROM metadata WHERE name='system_failure_streak'").fetchone()
            cooldown = db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
        remaining = CAP_NANOYUAN - totals["committed"]
        return {
            **POLICY, "ledger_path": str(self.path), "max_concurrency": self.max_concurrency,
            "remaining_cny": remaining / NANOYUAN,
            "committed_upper_cny": totals["committed"] / NANOYUAN,
            "settled_upper_cny": totals["settled"] / NANOYUAN,
            "settled_peak_equivalent_cny": totals["settled_peak"] / NANOYUAN,
            "peak_equivalent_cny": totals["peak_equivalent"] / NANOYUAN,
            "consecutive_system_failures": int(streak[0]) if streak else 0,
            **cooldown_state(cooldown[0] if cooldown else None),
            "uncertain_reserved_cny": totals["uncertain"] / NANOYUAN,
            "inflight_count": totals["inflight"] or 0, "attempts": totals["attempts"],
            "statuses": statuses, "halted": halted[0] if halted else None,
            "can_admit_minimum_request": not halted and remaining >= (
                MAX_INPUT_RESERVATION * MISS_NANOYUAN + OUTPUT_NANOYUAN),
        }

    def request_status(self, request_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
        return dict(row) if row is not None else None

    def reserve(self, *, request_id, slot_id, condition, usage_id, request_sha256,
                max_output_tokens, prompt_upper_bound=None):
        for name, value in (("request_id", request_id), ("slot_id", slot_id),
                            ("condition", condition), ("usage_id", usage_id)):
            if not isinstance(value, str) or not value or len(value) > 512:
                raise ValueError(f"Invalid {name}")
        _integer(max_output_tokens, "max_output_tokens", maximum=MAX_OUTPUT_TOKENS)
        if max_output_tokens == 0:
            raise ValueError("An explicit positive output bound is required")
        if prompt_upper_bound is not None:
            _integer(prompt_upper_bound, "prompt_upper_bound")
        reservation = (MAX_INPUT_RESERVATION * MISS_NANOYUAN
                       + max_output_tokens * OUTPUT_NANOYUAN)
        with self._transaction() as db:
            if db.execute("SELECT 1 FROM requests WHERE request_id=?", (request_id,)).fetchone():
                raise BudgetStopped("request_id_already_attempted_no_replay")
            halted = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
            if halted:
                raise BudgetStopped("ledger_halted:" + halted[0])
            cooldown = db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
            if cooldown_state(cooldown[0] if cooldown else None)["admission_wait_seconds"] > 0:
                raise ConcurrencyBusy("shared_system_failure_cooldown_before_dispatch")
            totals = self._totals(db)
            if (totals["inflight"] or 0) >= self.max_concurrency:
                raise ConcurrencyBusy("global_request_concurrency_limit")
            if totals["committed"] + reservation > CAP_NANOYUAN:
                raise BudgetStopped("global_cny_budget_reservation_insufficient")
            db.execute("""INSERT INTO requests
                (request_id,slot_id,condition,usage_id,status,request_sha256,
                 reserved_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                       (request_id, slot_id, condition, usage_id, "reserved", request_sha256,
                        reservation, max_output_tokens, prompt_upper_bound, _now()))
        return {"request_id": request_id, "reserved_nanoyuan": reservation,
                "reserved_cny": reservation / NANOYUAN}

    def uncertain(self, request_id, evidence):
        # Do not store exception strings: upstream failures can contain credentials.
        safe = {key: evidence[key] for key in
                ("error_type", "http_status", "reason", "shared_system_failure")
                if key in evidence}
        with self._transaction() as db:
            row = db.execute("SELECT status FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown reservation")
            if row[0] != "reserved":
                return
            db.execute("UPDATE requests SET status='uncertain',failure_json=? WHERE request_id=?",
                       (_json(safe), request_id))
            status = safe.get("http_status")
            if status in POLICY["immediate_halt_http_statuses"]:
                db.execute("INSERT OR IGNORE INTO metadata VALUES ('halted',?)",
                           (f"shared_http_{status}_authentication_or_account_failure",))
            elif safe.get("shared_system_failure") is True:
                old = db.execute("SELECT value FROM metadata WHERE name='system_failure_streak'").fetchone()
                streak = int(old[0]) + 1 if old else 1
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('system_failure_streak',?)",
                           (str(streak),))
                threshold = POLICY["consecutive_system_failure_cooldown_threshold"]
                if streak >= threshold:
                    # In-flight failures can extend backoff; none is replayed.
                    seconds = min(POLICY["system_failure_cooldown_max_seconds"],
                                  POLICY["system_failure_cooldown_initial_seconds"]
                                  * POLICY["system_failure_cooldown_backoff"] ** min(10, streak - threshold))
                    until = datetime.fromisoformat(_now()) + timedelta(seconds=seconds)
                    db.execute("INSERT OR REPLACE INTO metadata VALUES ('cooldown_until_utc',?)",
                               (until.isoformat(),))

    def settle(self, request_id, body):
        """Settle exactly once from authoritative usage, including cached tokens."""
        usage = body.get("usage")
        if not isinstance(usage, dict):
            raise ValueError("Missing authoritative API usage")
        prompt = _integer(usage.get("prompt_tokens"), "prompt_tokens", maximum=MAX_INPUT_RESERVATION)
        output = _integer(usage.get("completion_tokens"), "completion_tokens")
        total = _integer(usage.get("total_tokens"), "total_tokens")
        hit = usage.get("prompt_cache_hit_tokens")
        if hit is None:
            hit = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        hit = _integer(hit, "prompt_cache_hit_tokens", maximum=prompt)
        miss = _integer(usage.get("prompt_cache_miss_tokens", prompt - hit),
                        "prompt_cache_miss_tokens", maximum=prompt)
        alternate_hit = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", hit)
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if reasoning is not None:
            _integer(reasoning, "reasoning_tokens", maximum=output)
        if prompt != hit + miss or total != prompt + output or alternate_hit != hit:
            raise ValueError("API usage fields disagree")
        if not isinstance(body.get("id"), str) or not body["id"]:
            raise ValueError("Missing provider request identity")
        if body.get("model") not in {MODEL, DOCUMENTED_MODEL_VERSION,
                                     DOCUMENTED_MODEL_VERSION.lower()}:
            raise ValueError("Unexpected provider model identity")
        peak_cost = hit * HIT_NANOYUAN + miss * MISS_NANOYUAN + output * OUTPUT_NANOYUAN
        violation = None
        settled_utc = _now()
        with self._transaction() as db:
            row = db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None or row["status"] != "reserved":
                raise ValueError("Only a live unclosed reservation can settle")
            if output > row["max_output_tokens"] or peak_cost > row["reserved_nanoyuan"]:
                violation = "provider_usage_exceeded_authorized_request_bound"
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('halted',?)", (violation,))
                db.execute("UPDATE requests SET status='uncertain',failure_json=? WHERE request_id=?",
                           (_json({"reason": violation}), request_id))
            else:
                tariff = settlement_tariff(row["reserved_utc"], settled_utc)
                cost = (peak_cost + tariff["divisor"] - 1) // tariff["divisor"]
                db.execute("""UPDATE requests SET status='settled',settled_nanoyuan=?,
                    settled_utc=?,usage_json=?,response_id=?,response_model=?,
                    system_fingerprint=?,response_sha256=?,settled_peak_nanoyuan=?,
                    tariff_basis_json=? WHERE request_id=?""",
                           (cost, settled_utc, _json(usage), body["id"], body["model"],
                            body.get("system_fingerprint"), _sha(body), peak_cost,
                            _json(tariff), request_id))
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('system_failure_streak','0')")
                db.execute("DELETE FROM metadata WHERE name='cooldown_until_utc'")
        if violation:
            raise BudgetStopped(violation)
        return cost / NANOYUAN


class DirectHTTPS:
    """A fresh TLS connection to the fixed official host, with no proxy support."""

    def __init__(self, api_key, *, timeout_seconds=1800, max_response_bytes=32 * 1024 * 1024):
        if not isinstance(api_key, str) or not api_key or any(c.isspace() for c in api_key):
            raise ValueError("Invalid API key")
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    def request(self, method, path, payload=None):
        if (method, path) not in {("POST", "/chat/completions"),
                                  ("GET", "/models"), ("GET", "/user/balance")}:
            raise ValueError("Endpoint prohibited by the independent network policy")
        if method == "GET" and payload is not None:
            raise ValueError("Metadata GET cannot contain a model request")
        connection = http.client.HTTPSConnection(
            HOST, 443, timeout=min(60, self.timeout_seconds), context=ssl.create_default_context())
        started = time.monotonic()
        try:
            connection.request(method, path,
                               body=None if payload is None else _json(payload).encode("utf-8"),
                               headers={"Authorization": "Bearer " + self._api_key,
                                        "Content-Type": "application/json",
                                        "Accept": "application/json",
                                        "User-Agent": VERSION})
            response = connection.getresponse()
            status, chunks, size = response.status, [], 0
            while True:
                if time.monotonic() - started > self.timeout_seconds:
                    raise TimeoutError("direct_request_wall_deadline")
                chunk = response.read1(min(65536, self.max_response_bytes + 1 - size))
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


def validate_payload(payload, allowed_tool_names):
    allowed = {"model", "messages", "tools", "tool_choice", "max_tokens", "thinking",
               "reasoning_effort", "temperature", "top_p", "stream", "user_id",
               "response_format", "stop"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError("Unapproved API fields, extensions or server tools")
    if payload.get("model") != MODEL or payload.get("stream") is not False:
        raise ValueError("Only explicit nonstreaming deepseek-flash Chat Completions is admitted")
    mode = payload.get("thinking")
    if mode not in ({"type": "enabled"}, {"type": "disabled"}):
        raise ValueError("The thinking condition must be explicit")
    if mode["type"] == "enabled" and "temperature" in payload:
        raise ValueError("Thinking mode does not support temperature")
    effort = payload.get("reasoning_effort")
    if effort is not None and (mode["type"] != "enabled" or effort not in {"low", "high", "max"}):
        raise ValueError("Invalid reasoning effort for this condition")
    output = _integer(payload.get("max_tokens"), "max_tokens", maximum=MAX_OUTPUT_TOKENS)
    if not output:
        raise ValueError("An explicit positive output cap is required")
    tools = payload.get("tools", [])
    if not isinstance(tools, list):
        raise ValueError("Tools must be a frozen list")
    seen = set()
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) != {"type", "function"} or tool["type"] != "function":
            raise ValueError("Only local function schemas are admitted, never server tools")
        function = tool["function"]
        if not isinstance(function, dict) or set(function) - {"name", "description", "parameters", "strict"}:
            raise ValueError("Unapproved function schema extension")
        name = function.get("name")
        if name not in allowed_tool_names or name in seen:
            raise ValueError("Unexpected or duplicate local tool name")
        seen.add(name)
    if payload.get("tool_choice", "auto" if tools else "none") not in {"auto", "none"}:
        raise ValueError("Forced tools are not supported consistently across thinking modes")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("A nonempty message history is required")
    for message in messages:
        if (not isinstance(message, dict) or set(message) - {
                "role", "content", "name", "tool_calls", "tool_call_id", "reasoning_content"}
                or message.get("role") not in {"system", "user", "assistant", "tool"}):
            raise ValueError("Unapproved message extension or role")
        if message.get("content") is not None and not isinstance(message["content"], str):
            raise ValueError("Only text messages are admitted; no remote URLs/files/images")
        if (mode["type"] == "enabled" and tools and message.get("role") == "assistant"
                and not isinstance(message.get("reasoning_content"), str)):
            raise ValueError("Thinking tool history must preserve reasoning_content, including empty strings")
    return payload


class DeepSeekClient:
    def __init__(self, *, ledger_path, api_key, allowed_tool_names,
                 max_concurrency=64, timeout_seconds=1800, transport=None):
        self.ledger = BudgetLedger(ledger_path, max_concurrency=max_concurrency)
        self.allowed_tool_names = frozenset(allowed_tool_names)
        self.transport = transport or DirectHTTPS(api_key, timeout_seconds=timeout_seconds)

    def complete(self, request, *, request_id, slot_id, condition, usage_id="agent",
                 prompt_upper_bound=None):
        expected_user_id = slot_user_id(slot_id, condition)
        if "user_id" in request and request["user_id"] != expected_user_id:
            raise ValueError("user_id must be the frozen per-slot-and-condition cache isolation key")
        request = {**request, "user_id": expected_user_id}
        validate_payload(request, self.allowed_tool_names)
        self.ledger.reserve(
            request_id=request_id, slot_id=slot_id, condition=condition, usage_id=usage_id,
            request_sha256=_sha(request), max_output_tokens=request["max_tokens"],
            prompt_upper_bound=prompt_upper_bound)
        try:
            body = self.transport.request("POST", "/chat/completions", request)
            self.ledger.settle(request_id, body)
            return body
        except BaseException as error:
            self.ledger.uncertain(request_id, {
                "error_type": type(error).__name__, "http_status": getattr(error, "http_status", None),
                "reason": "attempt_not_proven_settled_no_automatic_retry",
                "shared_system_failure": (
                    getattr(error, "http_status", None) in {None, 400, 429}
                    or (type(getattr(error, "http_status", None)) is int
                        and 500 <= error.http_status < 600)),
            })
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise APIUncertainFailure(
                f"{type(error).__name__}: request outcome uncertain; reservation retained") from None

    def metadata(self, kind):
        paths = {"models": "/models", "balance": "/user/balance"}
        if kind not in paths:
            raise ValueError("Only free model and balance metadata are allowed")
        return self.transport.request("GET", paths[kind])


def cny_balance(body):
    """Return a decimal amount without exposing credentials or account identifiers."""
    for item in body.get("balance_infos", []):
        if item.get("currency") == "CNY":
            return Decimal(item["total_balance"])
    return None
