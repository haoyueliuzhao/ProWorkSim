"""Independent CNY500 communication pilot: one physical ledger for all purposes.

C0/C1/C2 share cash; agent/condenser/compressor share each team's 5M tokens
and 512 physical attempts. Fully received transient HTTP errors can retry with
new held reservations; ambiguous transport outcomes never replay. No service
or API request starts on import. Historical deployments remain immutable.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import http.client
import json
from pathlib import Path
import random
import re
import sqlite3
import ssl
import threading
import time
from types import SimpleNamespace

from . import software_benchmark_deepseek_api_v105 as old
from .software_benchmark_candidates_v054 import checked

VERSION = "v203.2.1-passive-150-r1"
CAP_NANOYUAN = 150_000_000_000
GROUP_IDS = ("REVIEW2",)
PURPOSES = frozenset({"agent", "condenser"})
AUTHORITY_VERSION = "v203.2.1-independent-150-authority-r1"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
TEAM_TOKEN_LIMIT = 5_000_000
TEAM_ATTEMPT_LIMIT = 512
NANOYUAN = 1_000_000_000
BudgetStopped = old.BudgetStopped
PreDispatchBudgetStopped = old.PreDispatchBudgetStopped
PreDispatchConcurrencyBusy = old.PreDispatchConcurrencyBusy
APIUncertainFailure = old.APIUncertainFailure


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(
        value if isinstance(value, bytes) else canonical(value).encode()
    ).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def retry_after(value, *, wall=None):
    if not value:
        return None
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            seconds = date.timestamp() - (time.time() if wall is None else wall)
        except (ValueError, TypeError, OverflowError):
            return None
    return min(300.0, max(0.0, seconds)) if seconds < float("inf") else None


class TransportFailure(APIUncertainFailure):
    """Only allowlisted structural evidence; no bearer token or arbitrary body."""

    def __init__(self, code, *, phase, status=None, body=b"", headers=None, detail=None):
        self.http_status = status
        headers = headers or {}
        provider_code = None
        try:
            candidate = json.loads(body).get("error", {}).get("code")
            if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", candidate):
                provider_code = candidate
        except (ValueError, AttributeError, TypeError):
            pass
        self.evidence = {
            "version": VERSION,
            "error_code": code,
            "phase": phase,
            "http_status": status,
            "response_bytes": len(body),
            "response_sha256": hashlib.sha256(body).hexdigest() if body else None,
            "provider_error_code": provider_code,
            "retry_after_seconds": retry_after(headers.get("Retry-After")),
            "observed_utc": now(),
            "detail": detail or {},
            "actual_usage_known": False,
            "reserved_cost_is_actual_usage": False,
        }
        super().__init__(canonical(self.evidence))

    @property
    def retryable(self):
        return (
            self.evidence["error_code"] == "complete_http_error_response"
            and self.http_status in RETRY_STATUSES
        )


class DirectHTTPS(old.DirectHTTPS):
    """Fixed official TLS host, no proxies/redirects; preserve error phase."""

    def capture_raw(self, kind, raw, **metadata):
        capture=getattr(self,'physical_capture',None)
        if capture is not None:
            try:capture(kind,raw,getattr(self,'capture_context',{}),metadata)
            except Exception:
                self.capture_faults=getattr(self,'capture_faults',0)+1

    def request(self, method, path, payload=None):
        if (method, path) != ("POST", "/chat/completions") or not isinstance(payload, dict):
            raise ValueError("Only the fixed official completion endpoint is permitted")
        if self.cancelled.is_set():
            raise TransportFailure("cancelled_before_connect", phase="pre_connect")
        connection = http.client.HTTPSConnection(
            old.transport.HOST,
            443,
            timeout=min(10, self.timeout_seconds),
            context=ssl.create_default_context(),
        )
        with self._lock:
            if self._connection is not None:
                raise TransportFailure(
                    "concurrent_use_of_one_episode_transport", phase="pre_connect"
                )
            self._connection = connection
        phase, status, response, body = "connect", None, None, b""
        started = time.monotonic()
        try:
            connection.connect()
            connection.auto_open = False
            connection.sock.settimeout(min(60, self.timeout_seconds))
            if self.cancelled.is_set():
                raise TransportFailure("cancelled_before_send", phase="pre_send")
            phase = "send"
            self.capture_raw('HTTP_REQUEST',canonical(payload).encode())
            connection.request(
                method,
                path,
                body=canonical(payload).encode(),
                headers={
                    "Authorization": "Bearer " + self._api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": VERSION,
                },
            )
            phase = "headers"
            response = connection.getresponse()
            with self._lock:
                self._response = response
            status = response.status
            phase, chunks, size = "body", [], 0
            while True:
                if self.cancelled.is_set() or time.monotonic() - started > self.timeout_seconds:
                    raise TransportFailure("cancelled_or_wall_deadline", phase=phase, status=status)
                chunk = response.read1(min(65536, self.max_response_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > self.max_response_bytes:
                    raise TransportFailure(
                        "response_byte_bound",
                        phase=phase,
                        status=status,
                        detail={"maximum_bytes": self.max_response_bytes, "observed_bytes": size},
                    )
            body = b"".join(chunks)
            self.capture_raw('HTTP_RESPONSE',body,http_status=status)
            if getattr(response, "length", None) not in {None, 0} or (
                getattr(response, "chunked", False)
                and getattr(response, "chunk_left", None) is not None
            ):
                raise TransportFailure(
                    "incomplete_response_body", phase="body", status=status, body=body
                )
            if status != 200:
                raise TransportFailure(
                    "complete_http_error_response",
                    phase="complete_http_response",
                    status=status,
                    body=body,
                    headers={"Retry-After": response.getheader("Retry-After")},
                )
            phase = "json_decode"
            # json.loads accepts the documented non-streaming blank-line keepalives.
            try:
                result = json.loads(body)
            except (ValueError, UnicodeError) as error:
                raise TransportFailure(
                    "response_json_decode",
                    phase=phase,
                    status=status,
                    body=body,
                    detail={
                        key: getattr(error, key)
                        for key in ("lineno", "colno", "pos")
                        if hasattr(error, key)
                    },
                ) from None
            if not isinstance(result, dict):
                raise TransportFailure(
                    "response_not_json_object", phase="json_shape", status=status, body=body
                )
            return result
        except TransportFailure:
            raise
        except Exception as error:
            # The structural type/phase survives; arbitrary str(error) may contain credentials.
            raise TransportFailure(
                "transport_exception",
                phase=phase,
                status=status,
                body=body,
                detail={
                    "exception_type": type(error).__name__,
                    "exception_message_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
                },
            ) from None
        finally:
            connection.close()
            with self._lock:
                self._connection = self._response = None


def validate_payload(payload, allowed_tool_names, usage_id='agent'):
    if usage_id not in PURPOSES:
        raise ValueError('Unknown communication request purpose')
    if usage_id == 'compressor':
        if payload.get('temperature') != .2 or payload.get('max_tokens') != 512:
            raise ValueError('The frozen compressor uses temperature .2 and output512')
        if payload.get('tools') or 'tool_choice' in payload:
            raise ValueError('The compressor is not an autonomous tool-using member')
        normalized = {**payload, 'temperature': 1.0}
        old.validate_payload(normalized, ())
    else:
        old.validate_payload(payload, allowed_tool_names)
        if usage_id == 'condenser' and payload.get('tools'):
            raise ValueError('A history condenser has no tools')
    return payload


def _group(row):
    return row.get('group_id', row.get('condition'))


def _condition(row):
    return row.get('condition_id', row.get('condition'))


def group_api(group_id, ledger_path, *, max_concurrency, panel_ref, cash_authority_ref, execution_plan_ref=None):
    """Bind exactly one new500-CNY account; no parent/previous account is opened."""
    panel = json.loads(checked(panel_ref).read_text())
    authority = json.loads(checked(cash_authority_ref).read_text())
    ledger_path = Path(ledger_path).resolve()
    expected_authority = {
        'version': AUTHORITY_VERSION, 'ledger_path': str(ledger_path),
        'cap_nanoyuan': CAP_NANOYUAN, 'panel_sha256': panel_ref['sha256'],
        'approved': True,
    }
    if execution_plan_ref is not None:
        expected_authority['execution_plan_sha256'] = execution_plan_ref['sha256']
    if authority != expected_authority:
        raise ValueError('The new independent500-CNY authority must bind this panel and unique ledger')
    execution = json.loads(checked(execution_plan_ref).read_text()) if execution_plan_ref else panel
    rows = execution['rows']
    if execution_plan_ref:
        original = {r['slot_id']: r for r in panel['rows']}
        if len(rows) != len(original):
            raise ValueError('Execution plan must retain the entire fixed panel')
        for row in rows:
            source = original.get(row.get('source_preparation_slot_id',row['slot_id']))
            if source is None or any(row.get(k) != source.get(k) for k in ('condition_id','instance_id','seed','wave')):
                raise ValueError('Execution plan changed a frozen task/condition/seed/wave')
    planned = {r['slot_id']: r for r in rows}
    if len(planned) != len(rows) or group_id not in GROUP_IDS or set(map(_group, rows)) != set(GROUP_IDS):
        raise ValueError('Distinct planned C0/C1/C2 teams are required')
    if any(r.get('organization_id', 'REVIEW2') != 'REVIEW2'
           or r['fixed_members'] != ['member_001', 'member_002']
           or r.get('budget_tokens', TEAM_TOKEN_LIMIT) != TEAM_TOKEN_LIMIT for r in rows):
        raise ValueError('Every communication condition keeps the frozen REVIEW2 team')
    if type(max_concurrency) is not int or not 1 <= max_concurrency <= 2500:
        raise ValueError('Invalid provider concurrency')
    policy = {
        'version': VERSION, 'panel': panel_ref, 'execution_plan': execution_plan_ref, 'cash_authority': cash_authority_ref,
        'child_ledger_path': str(ledger_path), 'cap_nanoyuan': CAP_NANOYUAN,
        'available_nanoyuan': CAP_NANOYUAN, 'max_concurrency': max_concurrency,
        'maximum_attempts_per_logical_request': MAX_ATTEMPTS,
        'team_token_limit': TEAM_TOKEN_LIMIT, 'team_http_attempt_limit': TEAM_ATTEMPT_LIMIT,
        'uncertain_reservations_retained': True,
        'transient_attempts_are_new_metered_attempts': True,
        'window_seconds': 60, 'window_failure_threshold': 3, 'cooldown_seconds': 30,
        'single_success_clears_window': False,
        'purposes': sorted(PURPOSES), 'cash_cap_scope': 'one_passive_pilot150_account',
        'old_ledgers_read_or_modified': False,
        'compressor_transport_unknown': 'hold_upper_no_replay_raw_fallback_may_continue_same_pool',
        'agent_sampling': {'temperature': 1.0, 'top_p': 1.0, 'max_output': 32768},
        'compressor_sampling': {'temperature': .2, 'top_p': 1.0, 'max_output': 512, 'tools': []},
        'reservation_rates_nanoyuan_per_token': {'miss': 2000, 'hit': 40, 'output': 8000},
        'pricing_source': 'https://api-docs.deepseek.com/quick_start/pricing',
        'pricing_checked_date': '2026-11-12',
        'cash_settlement_basis': 'peak_tariff_upper_estimate_not_provider_invoice',
    }

    class BudgetLedger:
        def __init__(self, path=ledger_path):
            self.path = Path(path).resolve()
            if self.path != ledger_path:
                raise ValueError("This API view cannot open another ledger")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as db:
                    try:
                        row = db.execute(
                            "SELECT value FROM metadata WHERE name='policy'"
                        ).fetchone()
                    except sqlite3.DatabaseError as error:
                        raise ValueError(
                            "Existing database is not the new deployment ledger"
                        ) from error
                    if row is None or row[0] != canonical(policy):
                        raise ValueError("Refuse a different or historical ledger policy")
            with self.transaction() as db:
                db.execute('CREATE TABLE IF NOT EXISTS team_admissions(slot_id TEXT PRIMARY KEY,state TEXT NOT NULL)')
                db.execute(
                    "CREATE TABLE IF NOT EXISTS metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)"
                )
                db.execute(
                    "INSERT OR IGNORE INTO metadata VALUES('policy',?)", (canonical(policy),)
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS requests ("
                    "request_id TEXT PRIMARY KEY,logical_id TEXT NOT NULL,attempt_index INTEGER NOT NULL,"
                    "slot_id TEXT NOT NULL,member_id TEXT NOT NULL,condition TEXT NOT NULL,usage_id TEXT NOT NULL,"
                    "request_sha256 TEXT NOT NULL,status TEXT NOT NULL,reserved_nanoyuan INTEGER NOT NULL,"
                    "reserved_tokens INTEGER NOT NULL,prompt_upper_bound INTEGER NOT NULL,max_output_tokens INTEGER NOT NULL,"
                    "reserved_utc TEXT NOT NULL,settled_nanoyuan INTEGER,usage_json TEXT,response_id TEXT UNIQUE,"
                    "evidence_json TEXT,finished_utc TEXT)"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS breaker_events (request_id TEXT PRIMARY KEY,"
                    "observed REAL NOT NULL,retryable INTEGER NOT NULL)"
                )

        @contextmanager
        def transaction(self):
            with sqlite3.connect(self.path, timeout=30, isolation_level=None) as db:
                db.row_factory = sqlite3.Row
                db.execute("BEGIN IMMEDIATE")
                try:
                    yield db
                    db.execute("COMMIT")
                except BaseException:
                    db.execute("ROLLBACK")
                    raise

        def cash_admission(self, slot_id=None, *, close=False):
            with self.transaction() as db:
                if slot_id is not None and slot_id not in planned:
                    raise ValueError('Foreign team cash identity')
                if close:
                    if db.execute("SELECT 1 FROM requests WHERE slot_id=? AND status='reserved'",(slot_id,)).fetchone():
                        raise ValueError('A physically inflight team cannot release its hold')
                    db.execute("UPDATE team_admissions SET state='closed' WHERE slot_id=?", (slot_id,))
                requests=list(db.execute('SELECT * FROM requests'))
                admitted={r['slot_id'] for r in db.execute("SELECT * FROM team_admissions WHERE state='started'")}
                cost=sum(r['settled_nanoyuan'] if r['status']=='settled' else r['reserved_nanoyuan'] for r in requests)
                unused=0
                for slot in admitted:
                    accounted=sum(json.loads(r['usage_json'])['total_tokens'] if r['status']=='settled' else r['reserved_tokens'] for r in requests if r['slot_id']==slot)
                    unused+=max(0,TEAM_TOKEN_LIMIT-accounted)*8000
                if slot_id is not None and not close and slot_id not in admitted:
                    if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1',(slot_id,)).fetchone():
                        raise ValueError('Never re-admit a consumed team')
                    if cost+unused+TEAM_TOKEN_LIMIT*8000>CAP_NANOYUAN:
                        raise PreDispatchBudgetStopped('waiting_full_team_cash_reservation')
                    db.execute("INSERT INTO team_admissions VALUES(?,'started')",(slot_id,))
                    unused+=TEAM_TOKEN_LIMIT*8000
                return {'settled_or_reserved_nanoyuan':cost,'remaining_team_holds_nanoyuan':unused,
                        'available_for_new_teams_nanoyuan':CAP_NANOYUAN-cost-unused,
                        'worst_case_new_team_nanoyuan':TEAM_TOKEN_LIMIT*8000,
                        'can_start':cost+unused+TEAM_TOKEN_LIMIT*8000<=CAP_NANOYUAN,
                        'active_team_count':len(admitted)+(int(slot_id is not None and not close and slot_id not in admitted)),
                        'started_teams_not_cash_interrupted':True}

        def release_unentered(self, slot_id):
            if slot_id not in planned:
                raise ValueError('Foreign team cash identity')
            with self.transaction() as db:
                if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1',(slot_id,)).fetchone():
                    raise ValueError('Cannot release an actually attempted team as unentered')
                db.execute("DELETE FROM team_admissions WHERE slot_id=? AND state='started'",(slot_id,))
            return {'slot_id':slot_id,'released_unentered':True,'physical_requests':0}

        def reserve(
            self,
            *,
            logical_id,
            attempt_index,
            slot_id,
            member_id,
            condition,
            usage_id,
            request_sha256,
            prompt_upper_bound,
            max_output_tokens,
        ):
            row = planned.get(slot_id)
            if (
                row is None
                or _group(row) != group_id
                or condition != _condition(row)
                or member_id not in row["fixed_members"]
                or usage_id not in PURPOSES
                or group_id == "C0" and usage_id == "compressor"
            ):
                raise ValueError("Request is outside its exact planned team/member")
            prefix = slot_id + ":" + member_id + (":compressor:" if usage_id == "compressor" else ":")
            if (
                not logical_id.startswith(prefix)
                or not re.fullmatch(r"[0-9]{4}", logical_id[len(prefix) :])
                or not 1 <= int(logical_id[len(prefix) :]) <= 512
                or not 1 <= attempt_index <= MAX_ATTEMPTS
            ):
                raise ValueError("Malformed or unbounded logical request identity")
            old.contract._integer(prompt_upper_bound, "prompt_upper_bound", maximum=98304)
            old.contract._integer(max_output_tokens, "max_output_tokens", maximum=32768)
            if not max_output_tokens:
                raise ValueError("Positive output limit required")
            amount, tokens = (
                prompt_upper_bound * 2000 + max_output_tokens * 8000,
                prompt_upper_bound + max_output_tokens,
            )
            request_id = logical_id + f":http-{attempt_index}"
            with self.transaction() as db:
                if db.execute("SELECT 1 FROM metadata WHERE name='halted'").fetchone():
                    raise PreDispatchBudgetStopped("accounting_integrity_halt")
                prior = list(
                    db.execute(
                        "SELECT * FROM requests WHERE logical_id=? ORDER BY attempt_index",
                        (logical_id,),
                    )
                )
                if attempt_index != len(prior) + 1 or any(
                    x["status"] != "http_error_uncertain" for x in prior
                ):
                    raise PreDispatchBudgetStopped(
                        "logical_request_already_attempted_or_not_retryable"
                    )
                if any(x["request_sha256"] != request_sha256 or x["usage_id"] != usage_id for x in prior):
                    raise ValueError("Retry changed its exact logical request")
                total = db.execute(
                    "SELECT COALESCE(SUM(CASE WHEN status='settled' THEN settled_nanoyuan ELSE reserved_nanoyuan END),0), SUM(status='reserved') FROM requests"
                ).fetchone()
                if db.execute("SELECT 1 FROM team_admissions WHERE slot_id=? AND state='started'",(slot_id,)).fetchone() is None:
                    raise PreDispatchBudgetStopped('team_has_no_full_budget_admission')
                if (total[1] or 0) >= max_concurrency:
                    raise PreDispatchConcurrencyBusy("new_deployment_HTTP_limit")
                team = list(db.execute("SELECT * FROM requests WHERE slot_id=?", (slot_id,)))
                if any(x["status"] == "reserved" or (x["status"] == "unknown" and x["usage_id"] != "compressor") for x in team):
                    raise PreDispatchBudgetStopped("team_has_unrecoverable_or_inflight_attempt")
                accounted = sum(
                    json.loads(x["usage_json"])["total_tokens"]
                    if x["status"] == "settled"
                    else x["reserved_tokens"]
                    for x in team
                )
                if len(team) >= TEAM_ATTEMPT_LIMIT or accounted + tokens > TEAM_TOKEN_LIMIT:
                    raise PreDispatchBudgetStopped("shared_team_actual_plus_unknown_upper_limit")
                db.execute(
                    "INSERT INTO requests(request_id,logical_id,attempt_index,slot_id,member_id,condition,"
                    "usage_id,request_sha256,status,reserved_nanoyuan,reserved_tokens,prompt_upper_bound,max_output_tokens,reserved_utc) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        request_id,
                        logical_id,
                        attempt_index,
                        slot_id,
                        member_id,
                        condition,
                        usage_id,
                        request_sha256,
                        "reserved",
                        amount,
                        tokens,
                        prompt_upper_bound,
                        max_output_tokens,
                        now(),
                    ),
                )
            return request_id

        def failed(self, request_id, error):
            retryable = isinstance(error, TransportFailure) and error.retryable
            evidence = (
                error.evidence
                if isinstance(error, TransportFailure)
                else {
                    "error_code": "unexpected_client_exception",
                    "phase": "client",
                    "http_status": None,
                    "exception_type": type(error).__name__,
                    "exception_message_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
                    "actual_usage_known": False,
                    "observed_utc": now(),
                }
            )
            with self.transaction() as db:
                row = db.execute(
                    "SELECT status FROM requests WHERE request_id=?", (request_id,)
                ).fetchone()
                if row is None or row[0] != "reserved":
                    raise ValueError("Only the current live reservation may fail")
                db.execute(
                    "UPDATE requests SET status=?,evidence_json=?,finished_utc=? WHERE request_id=?",
                    (
                        "http_error_uncertain" if retryable else "unknown",
                        canonical(evidence),
                        now(),
                        request_id,
                    ),
                )
                if retryable:
                    db.execute(
                        "INSERT INTO breaker_events VALUES(?,?,1)", (request_id, time.time())
                    )
                if evidence.get("http_status") in {401, 402, 403}:
                    db.execute(
                        "INSERT OR REPLACE INTO metadata VALUES('halted','authentication_or_cash_failure')"
                    )
            return retryable

        def settle(self, request_id, body):
            # Raw response structure is classified separately from HTTP transport.
            try:
                usage = old.normalize_usage(body)
            except (ValueError, TypeError, KeyError) as error:
                code = str(error)
                safe_code = code if re.fullmatch(r"[a-z_]{1,100}", code) else type(error).__name__
                failure = TransportFailure(
                    "authoritative_usage_validation",
                    phase="settlement",
                    status=200,
                    body=canonical(body).encode(),
                    detail={"validation_code": safe_code},
                )
                self.failed(request_id, failure)
                raise failure from None
            with self.transaction() as db:
                row = db.execute(
                    "SELECT * FROM requests WHERE request_id=?", (request_id,)
                ).fetchone()
                if row is None or row["status"] != "reserved":
                    raise ValueError("Only a live request may settle once")
                duplicate = db.execute(
                    "SELECT 1 FROM requests WHERE response_id=?", (body["id"],)
                ).fetchone()
                if duplicate or usage["peak_cost_nanoyuan"] > row["reserved_nanoyuan"]:
                    reason = (
                        "duplicate_provider_identity" if duplicate else "cash_reservation_exceeded"
                    )
                    db.execute("INSERT OR REPLACE INTO metadata VALUES('halted',?)", (reason,))
                    db.execute(
                        "UPDATE requests SET status='unknown',evidence_json=?,finished_utc=? WHERE request_id=?",
                        (
                            canonical(
                                {
                                    "error_code": reason,
                                    "phase": "settlement",
                                    "http_status": 200,
                                    "response_sha256": sha(body),
                                    "usage": body["usage"],
                                }
                            ),
                            now(),
                            request_id,
                        ),
                    )
                    failure = reason
                else:
                    # New500 account intentionally grants no off-peak credit:
                    # cash is a conservative upper estimate, tokens are actual.
                    cost = usage["peak_cost_nanoyuan"]
                    db.execute(
                        "UPDATE requests SET status='settled',settled_nanoyuan=?,usage_json=?,response_id=?,finished_utc=? WHERE request_id=?",
                        (cost, canonical(body["usage"]), body["id"], now(), request_id),
                    )
                    failure = None
                    exceeded = (
                        usage["input_tokens"] > row["prompt_upper_bound"]
                        or usage["output_tokens"] > row["max_output_tokens"]
                    )
                    choices = body.get("choices")
                    valid_finish = (
                        isinstance(choices, list)
                        and len(choices) == 1
                        and isinstance(choices[0], dict)
                        and choices[0].get("finish_reason")
                        in {"stop", "length", "tool_calls", "content_filter"}
                    )
            if failure:
                raise BudgetStopped(failure)
            if exceeded:
                raise old.ProviderOutputBoundViolation(
                    "provider_tokens_exceed_experimental_reservation", body=body
                )
            if not valid_finish:
                raise old.ProviderOutputBoundViolation("provider_generation_interrupted", body=body)

        def team_snapshot(self, slot_id):
            if slot_id not in planned or _group(planned[slot_id]) != group_id:
                raise ValueError('Cannot inspect another condition/team budget')
            with self.transaction() as db:
                rows = [dict(row) for row in db.execute(
                    'SELECT * FROM requests WHERE slot_id=? ORDER BY reserved_utc,request_id', (slot_id,))]
            actual = held = 0
            per_usage, per_member = {}, {}
            for row in rows:
                target = per_usage.setdefault(row['usage_id'], {'prompt_tokens': 0, 'completion_tokens': 0,
                    'known_actual_tokens': 0, 'uncertain_reserved_tokens': 0, 'physical_attempts': 0})
                member = per_member.setdefault(row['member_id'], {'known_actual_tokens': 0, 'physical_attempts': 0})
                target['physical_attempts'] += 1
                member['physical_attempts'] += 1
                if row['status'] == 'settled':
                    usage = json.loads(row['usage_json'])
                    actual += usage['total_tokens']
                    member['known_actual_tokens'] += usage['total_tokens']
                    target['known_actual_tokens'] += usage['total_tokens']
                    for key in ('prompt_tokens', 'completion_tokens'):
                        target[key] += usage[key]
                else:
                    held += row['reserved_tokens']
                    target['uncertain_reserved_tokens'] += row['reserved_tokens']
            decisions = len({row['logical_id'] for row in rows if row['usage_id'] == 'agent'})
            return {'version': VERSION, 'team_id': slot_id, 'group_id': group_id,
                'token_limit': TEAM_TOKEN_LIMIT, 'attempt_limit': TEAM_ATTEMPT_LIMIT,
                'known_actual_tokens': actual, 'uncertain_reserved_tokens': held,
                'accounted_tokens': actual+held, 'available_tokens': max(0, TEAM_TOKEN_LIMIT-actual-held),
                'attempts': len(rows), 'decisions': decisions, 'remaining_attempts': TEAM_ATTEMPT_LIMIT-len(rows),
                'actual_usage_complete': not held, 'per_usage_id': per_usage, 'per_member': per_member,
                'inflight_count': sum(row['status'] == 'reserved' for row in rows),
                'live_reserved_tokens': sum(r['reserved_tokens'] for r in rows if r['status']=='reserved'),
                'source': 'one_shared_physical_provider_sqlite'}

        def breaker_wait(self):
            with self.transaction() as db:
                points = [
                    r[0]
                    for r in db.execute(
                        "SELECT observed FROM breaker_events WHERE observed>? ORDER BY observed",
                        (time.time() - 60,),
                    )
                ]
            return max(0.0, points[-1] + 30 - time.time()) if len(points) >= 3 else 0.0

        def snapshot(self):
            with self.transaction() as db:
                rows = list(db.execute("SELECT * FROM requests"))
            settled = sum(r["settled_nanoyuan"] for r in rows if r["status"] == "settled")
            unknown = sum(r["reserved_nanoyuan"] for r in rows if r["status"] != "settled")
            return {
                "version": VERSION,
                "settled_nanoyuan": settled,
                "reserved_or_unknown_nanoyuan": unknown,
                "remaining_nanoyuan": CAP_NANOYUAN - settled - unknown,
                "actual_usage_complete": all(r["status"] == "settled" for r in rows),
                "known_actual_tokens": sum(
                    json.loads(r["usage_json"])["total_tokens"]
                    for r in rows
                    if r["status"] == "settled"
                ),
                "unknown_tokens_upper": sum(
                    r["reserved_tokens"] for r in rows if r["status"] != "settled"
                ),
            }

    class DeepSeekClient:
        def __init__(
            self,
            *,
            api_key,
            allowed_tool_names,
            transport=None,
            timeout_seconds=1800,
            http_slots=None,
            sleep=time.sleep,
            jitter=random.random,
        ):
            self.ledger = BudgetLedger()
            self.allowed_tool_names = frozenset(allowed_tool_names)
            self.transport = transport or DirectHTTPS(api_key, timeout_seconds=timeout_seconds)
            self.http_slots = http_slots or threading.BoundedSemaphore(max_concurrency)
            self.timeout_seconds, self.sleep, self.jitter = timeout_seconds, sleep, jitter
            self._call_lock = threading.Lock()

        def fork_for_episode(self):
            if not isinstance(self.transport, DirectHTTPS):
                raise ValueError("Only the direct fixed-host transport may be forked")
            return type(self)(
                api_key=self.transport._api_key,
                allowed_tool_names=self.allowed_tool_names,
                timeout_seconds=self.timeout_seconds,
                http_slots=self.http_slots,
            )

        def wait(self, seconds, cancelled, deadline):
            if seconds <= 0:
                return
            if time.monotonic() + seconds > deadline:
                raise APIUncertainFailure("bounded_transport_recovery_deadline")
            if cancelled is not None:
                if cancelled.wait(seconds):
                    raise APIUncertainFailure("owned_team_cancelled_during_transport_backoff")
            else:
                self.sleep(seconds)

        def complete(
            self,
            request,
            *,
            request_id,
            slot_id,
            condition,
            usage_id,
            prompt_upper_bound,
            member_id,
            cancel_event=None,
        ):
            if request.get("user_id") != old.slot_user_id(slot_id + ":" + member_id, condition):
                raise ValueError("Provider cache identity changed")
            validate_payload(request, self.allowed_tool_names, usage_id)
            if not self._call_lock.acquire(blocking=False):
                raise PreDispatchConcurrencyBusy(
                    "one_client_cannot_process_simultaneous_logical_calls"
                )
            deadline = time.monotonic() + self.timeout_seconds
            dispatched = False
            try:
                for ordinal in range(1, MAX_ATTEMPTS + 1):
                    while (pause := self.ledger.breaker_wait()) > 0:
                        self.wait(pause, cancel_event, deadline)
                    while not self.http_slots.acquire(timeout=0.2):
                        if cancel_event is not None and cancel_event.is_set():
                            raise PreDispatchBudgetStopped("cancelled_before_HTTP_permit")
                        if time.monotonic() >= deadline:
                            raise PreDispatchConcurrencyBusy("HTTP_permit_wait_deadline")
                    try:
                        if time.monotonic() >= deadline:
                            raise PreDispatchConcurrencyBusy(
                                "logical_call_deadline_before_HTTP_reservation"
                            )
                        if cancel_event is not None and cancel_event.is_set():
                            raise PreDispatchBudgetStopped("cancelled_before_HTTP_reservation")
                        attempt = self.ledger.reserve(
                            logical_id=request_id,
                            attempt_index=ordinal,
                            slot_id=slot_id,
                            condition=condition,
                            member_id=member_id,
                            usage_id=usage_id,
                            request_sha256=sha(request),
                            prompt_upper_bound=prompt_upper_bound,
                            max_output_tokens=request["max_tokens"],
                        )
                        try:
                            if time.monotonic() >= deadline:
                                raise TransportFailure("deadline_before_send", phase="pre_send")
                            dispatched = True
                            if isinstance(self.transport, DirectHTTPS):
                                self.transport.timeout_seconds = max(
                                    0.01, deadline - time.monotonic()
                                )
                            self.transport.capture_context={'physical_id':attempt,'logical_id':request_id,'slot_id':slot_id,
                                'member_id':member_id,'condition':condition,'usage_id':usage_id,'attempt_index':ordinal}
                            body = self.transport.request("POST", "/chat/completions", request)
                        except Exception as error:
                            recoverable = self.ledger.failed(attempt, error)
                            if not recoverable or ordinal == MAX_ATTEMPTS:
                                raise
                            delay = max(
                                min(30.0, 2**ordinal + self.jitter()),
                                error.evidence.get("retry_after_seconds") or 0,
                            )
                        else:
                            self.ledger.settle(attempt, body)
                            return body
                    finally:
                        self.http_slots.release()
                    # No HTTP permit remains held during either local or shared backoff.
                    self.wait(delay, cancel_event, deadline)
            except (PreDispatchBudgetStopped, PreDispatchConcurrencyBusy) as error:
                if dispatched:
                    # The current retry may be unsent, but the logical call has
                    # consumed earlier attempts. Never advertise zero-call safety.
                    raise APIUncertainFailure(
                        "metered_transport_recovery_stopped:" + str(error)
                    ) from None
                raise
            finally:
                if isinstance(self.transport, DirectHTTPS):
                    self.transport.timeout_seconds = self.timeout_seconds
                self._call_lock.release()

    return SimpleNamespace(
        **{
            **vars(old),
            "VERSION": VERSION,
            "validate_payload": validate_payload,
            "POLICY": policy,
            "CAP_NANOYUAN": CAP_NANOYUAN,
            "group_id": group_id,
            "BudgetLedger": BudgetLedger,
            "DeepSeekClient": DeepSeekClient,
            "DirectHTTPS": DirectHTTPS,
            "TransportFailure": TransportFailure,
        }
    )
