"""Real host binding for the21 separately identified API recovery attempts.

Only the explicitly amended shared450 remainder funds this deployment. The new ledger is
unique across both groups. Each physical HTTP attempt remains independently
metered; a recovered logical request can have known code and unknown cost.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
import threading
import time

from . import software_benchmark_scope_v146 as scope
from . import software_benchmark_host_api_v145 as prepared_host
from .software_benchmark_deepseek_api_v145 import canonical
from .software_benchmark_deepseek_api_v146 import group_api
from .software_benchmark_deepseek_api_v142 import PRICING, MAX_PROFILE_RESERVATION_NANOYUAN
from .software_benchmark_alignment_contract_v141 import condition
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_usage_metrics_v064 import normalize_usage_call
from .storage import digest, json_bytes

VERSION = "v146-independent-recovery-metered-host-r1"
GROUP_IDS = ("FREE2", "REVIEW2")
SCHEMAS = scope.API_ROOT / "api-runtime/member-tool-schemas-r1.json"
TOKENIZER = scope.ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
AUTHORITY = (
    scope.ROOT
    / "artifacts/software-benchmark-v145/api-deployment-preparation-r3/cash-authority.json"
)
OLD_SCHEMAS = (
    scope.ROOT
    / "runs/software-benchmark-v142/role-pilot40-r1/deployment-v143/api-coordinator/api-runtime/member-tool-schemas-r2.json"
)
ENDPOINT = "http://127.0.0.1:18219"


def validate_row(row):
    from .software_benchmark_alignment_contract_v146 import validate_plan_identity

    return validate_plan_identity(row)


@lru_cache(maxsize=2)
def api_for(group):
    if group not in GROUP_IDS:
        raise ValueError("Only the two original affected organizations may recover")
    return group_api(
        group,
        scope.LEDGER_FILES[group],
        max_concurrency=scope.MAX_GENERATIONS,
        panel_ref=reference(scope.PANEL_FILE),
        cash_authority_ref=reference(AUTHORITY),
    )


def prepare_schemas(inventory_path=None):
    """Copy the original frozen member schemas; do not change role/tool exposure."""
    # Static preparation precedes the final source seal; it performs no API,
    # service or container operation. Actual dispatch checks the frozen scope.
    original = scope.load(reference(OLD_SCHEMAS))
    if inventory_path is not None:
        inventory = scope.load(reference(inventory_path))
        if inventory.get("schemas") != original["schemas"]:
            raise ValueError("Recovery must retain the original member tool inventory")
    schemas = {group: original["schemas"][group] for group in GROUP_IDS}
    for group, members in schemas.items():
        if set(members) != set(condition(group)["fixed_members"]):
            raise ValueError("Recovery schemas changed original fixed members")
        for tools in members.values():
            names = [item.get("function", {}).get("name") for item in tools]
            if (
                not tools
                or len(names) != len(set(names))
                or None in names
                or any(item.get("type") != "function" for item in tools)
                or set(names) & {"terminal", "web_search", "browser", "fetch"}
            ):
                raise ValueError("Recovery exposes only the original managed function tools")
    return scope.retain(
        SCHEMAS,
        {
            "version": VERSION,
            "schemas": schemas,
            "original_schema_record": reference(OLD_SCHEMAS),
            "original_actual_member_inventory": original["actual_member_inventory"],
            "neutral_calls": 0,
            "host_listener": False,
            "provider_search_or_fetch": False,
            "schema_change": False,
            "transport_policy_revision": "v145-metered-transient-http-recovery-r1",
        },
    )


@contextmanager
def ledger_read(group):
    api = api_for(group)
    path = Path(scope.LEDGER_FILES[group])
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        row = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
        if row is None or row[0] != canonical(api.POLICY):
            raise ValueError("The recovery ledger belongs to a different immutable policy")
        yield db
    finally:
        db.close()


def budget_status(group):
    api = api_for(group)
    if not Path(scope.LEDGER_FILES[group]).exists():
        return {
            "group_id": group,
            "state": "qualification_pending",
            "can_start_generation": False,
            "temporary_wait": True,
            "cap_CNY": str(Decimal(api.CAP_NANOYUAN) / 10**9),
        }
    with ledger_read(group) as db:
        rows = list(db.execute("SELECT status,reserved_nanoyuan,settled_nanoyuan FROM requests"))
        halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
        failures = [
            r[0]
            for r in db.execute(
                "SELECT observed FROM breaker_events WHERE observed>? ORDER BY observed",
                (time.time() - 60,),
            )
        ]
    settled = sum(r["settled_nanoyuan"] for r in rows if r["status"] == "settled")
    inflight = sum(r["status"] == "reserved" for r in rows)
    reserved = sum(r["reserved_nanoyuan"] for r in rows if r["status"] == "reserved")
    uncertain = sum(
        r["reserved_nanoyuan"] for r in rows if r["status"] not in {"reserved", "settled"}
    )
    remaining = api.CAP_NANOYUAN - settled - reserved - uncertain
    wait = max(0.0, failures[-1] + 30 - time.time()) if len(failures) >= 3 else 0.0
    state = "ready"
    if halt or remaining < 0:
        state = "shared_halted"
    elif remaining < MAX_PROFILE_RESERVATION_NANOYUAN:
        state = "waiting_inflight_cash" if inflight else "cash_exhausted"
    elif inflight >= scope.MAX_GENERATIONS:
        state = "waiting_concurrency"
    elif wait > 0:
        state = "waiting_cooldown"

    def yuan(value):
        return str(Decimal(value) / 10**9)

    return {
        "version": VERSION,
        "group_id": group,
        "state": state,
        "can_start_generation": state == "ready",
        "temporary_wait": state.startswith("waiting_"),
        "reason": halt[0] if halt else None,
        "cash_scope": "one_remaining_child_ledger_shared_by_both_groups",
        "cap_CNY": yuan(api.CAP_NANOYUAN),
        "original_total_cap_CNY": "450",
        "remaining_CNY": yuan(remaining),
        "settled_upper_CNY": yuan(settled),
        "inflight_reserved_CNY": yuan(reserved),
        "uncertain_reserved_CNY": yuan(uncertain),
        "committed_upper_CNY": yuan(settled + reserved + uncertain),
        "inflight_count": inflight,
        "attempts": len(rows),
        "new_team_admission_reservation_CNY": yuan(MAX_PROFILE_RESERVATION_NANOYUAN),
        "existing_team_requests_use_actual_request_reservation": True,
        "ledger_path": str(scope.LEDGER_FILES[group]),
        "admission_wait_seconds": wait,
        "bounded_uncertain_requests_isolated_to_their_teams": True,
    }


def _records_for(row):
    validate_row(row)
    with ledger_read(row["organization_id"]) as db:
        records = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM requests WHERE slot_id=? ORDER BY reserved_utc,attempt_index",
                (row["slot_id"],),
            )
        ]
    for item in records:
        if (
            item["condition"] != row["condition_id"]
            or item["member_id"] not in row["fixed_members"]
        ):
            raise ValueError("Physical request lost its original team/member attribution")
    return records


def usage_for_slot(row):
    records = _records_for(row)
    settled_logical = {r["logical_id"] for r in records if r["status"] == "settled"}
    calls, unknown = [], []
    for item in records:
        common = {
            "member_id": item["member_id"],
            "organization_id": row["organization_id"],
            "logical_call_id": item["logical_id"],
            "http_attempt_index": item["attempt_index"],
        }
        if item["status"] == "settled":
            measured = normalize_usage_call(
                item["request_id"],
                item["usage_id"],
                json.loads(item["usage_json"]),
                accounted_cost_cny=str(Decimal(item["settled_nanoyuan"]) / 10**9),
            )
            calls.append({**measured, **common})
        else:
            unknown.append(
                {
                    **common,
                    "call_id": item["request_id"],
                    "purpose": item["usage_id"],
                    "reserved_tokens": item["reserved_tokens"],
                    "reserved_cost_cny": str(Decimal(item["reserved_nanoyuan"]) / 10**9),
                    "reservation_is_actual_usage": False,
                    "status": item["status"],
                    "recovered_by_later_settled_attempt": item["logical_id"] in settled_logical,
                    "failure": json.loads(item["evidence_json"]) if item["evidence_json"] else None,
                }
            )
    return {
        "calls": calls,
        "unresolved_calls": unknown,
        "usage_capture_complete": not unknown,
        "usage_source": "v146_independent_metered_physical_HTTP_ledger",
        "team_pool_not_per_member": True,
        "physical_http_attempt_count": len(records),
        "logical_request_count": len({r["logical_id"] for r in records}),
        "known_actual_tokens": sum(
            json.loads(r["usage_json"])["total_tokens"] for r in records if r["status"] == "settled"
        ),
        "unknown_tokens_upper": sum(
            r["reserved_tokens"] for r in records if r["status"] != "settled"
        ),
        "unknown_upper_is_actual_usage": False,
        "original_usage_preserved_separately": True,
    }


def recovery_queue_record(row):
    """Describe unresolved transport, never silently schedule a new episode."""
    records = _records_for(row)
    settled_logical = {r["logical_id"] for r in records if r["status"] == "settled"}
    uncertain = [r for r in records if r["status"] != "settled"]
    failed_logical = {r["logical_id"] for r in uncertain if r["logical_id"] not in settled_logical}
    failure_rows = [r for r in uncertain if r["logical_id"] in failed_logical]
    money = budget_status(row["organization_id"])
    if failure_rows and money["state"] in {"cash_exhausted", "shared_halted"}:
        classification = "cash_boundary"
    elif not failure_rows:
        classification = "billing_unknown_after_transport_recovery" if uncertain else "none"
    elif any(r["status"] == "reserved" for r in failure_rows):
        classification = "request_owner_or_settlement_incomplete"
    elif any(r["status"] == "unknown" for r in failure_rows):
        phases = {json.loads(r["evidence_json"] or "{}").get("phase") for r in failure_rows}
        classification = (
            "local_protocol_unknown"
            if phases & {"json_decode", "json_shape", "settlement"}
            else "transport_unknown"
        )
    else:
        classification = "exhausted_transient_http"
    eligible = classification in {"exhausted_transient_http", "transport_unknown"}
    return {
        "version": VERSION,
        "slot_id": row["slot_id"],
        "original_slot_id": row.get("original_slot_id"),
        "classification": classification,
        "eligible_for_independent_retry": eligible,
        "retry_eligible": eligible,
        "cash_state": money["state"],
        "automatic_episode_retry": False,
        "new_identity_and_cash_reservation_required": True,
        "requests": [
            {
                "request_id": r["request_id"],
                "logical_id": r["logical_id"],
                "attempt_index": r["attempt_index"],
                "status": r["status"],
                "failure": json.loads(r["evidence_json"] or "{}"),
                "reserved_tokens_upper": r["reserved_tokens"],
                "reserved_nanoyuan": r["reserved_nanoyuan"],
            }
            for r in uncertain
        ],
    }


class HostTeamTransport(prepared_host.HostTeamTransport):
    def post(self, path, payload):
        value = super().post(path, payload)
        if path == "/chat/completions":
            receipt = {
                "version": VERSION,
                "slot_id": self.slot_id,
                "member_id": payload["member_id"],
                "logical_call_id": payload["request_id"],
                "request_sha256": digest(json_bytes(payload["wire"])),
                "response_sha256": digest(json_bytes(value)),
                "response_id": value.get("id"),
                "usage_known": True,
                "successful_response_returned_once": True,
            }
            path = self.runtime.success_root / (digest(json_bytes(payload["request_id"])) + ".json")
            scope.retain(path, receipt)
            with self.runtime.lock:
                self.runtime.successful_routes.setdefault(self.group, set()).add(self.slot_id)
        return value


class DeepSeekRuntime:
    def __init__(self):
        self.clients, self.rows, self.schemas, self.apis = {}, {}, {}, {}
        self.counter = None
        self.http_slots = threading.BoundedSemaphore(scope.MAX_GENERATIONS)
        self.transports, self.lock = [], threading.RLock()
        self.successful_routes = {group: set() for group in GROUP_IDS}
        self.success_root = scope.API_ROOT / "api-runtime/successful-logical-responses"

    @staticmethod
    def authorize(operation, **identity):
        if operation != "v145.api.request":
            raise PermissionError("Unexpected underlying transport scope operation")
        return scope.require_allowed("v146.api.request", **identity)

    def initialize_for_run(self):
        scope.require_allowed("v146.api.request")
        plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
        self.rows = {row["slot_id"]: row for row in plan["rows"]}
        if (
            len(self.rows) != 42
            or {row["organization_id"] for row in self.rows.values()} != set(GROUP_IDS)
            or sum(row.get("recovery_round") == 1 for row in self.rows.values()) != 21
            or sum(row.get("recovery_round") == 2 for row in self.rows.values()) != 21
        ):
            raise ValueError(
                "Only the21 first and21 conditional recovery identities may be registered"
            )
        self.schemas = scope.load(reference(SCHEMAS))["schemas"]
        token_ref = reference(TOKENIZER)
        self.counter = OfficialDeepSeekCounter(
            token_ref["path"], manifest_sha256=token_ref["sha256"], reservation_margin_tokens=128
        )
        self.apis = {group: api_for(group) for group in GROUP_IDS}
        for group in GROUP_IDS:
            if Path(scope.LEDGER_FILES[group]).exists():
                with ledger_read(group) as db:
                    if db.execute("SELECT 1 FROM requests LIMIT 1").fetchone():
                        raise ValueError("A consumed recovery ledger cannot be silently restarted")
        runtime = prepared_host.runtime_for(
            apis=self.apis,
            schemas=self.schemas,
            counter=self.counter,
            authorize=self.authorize,
            api_key=self.apis[GROUP_IDS[0]].load_api_key(scope.ROOT / ".env"),
            max_concurrency=scope.MAX_GENERATIONS,
        )
        self.clients, self.http_slots = runtime.clients, runtime.http_slots
        return self

    def for_group(self, group):
        if group not in GROUP_IDS:
            raise ValueError("Unknown recovery organization")
        return GroupView(self, group)

    def transport_factory(self, row, output):
        validate_row(row)
        if self.rows.get(row["slot_id"]) != row:
            raise ValueError("Only a sealed new recovery row may obtain an API route")
        route = HostTeamTransport(self, row, output)
        with self.lock:
            self.transports.append(route)
        return route

    def cancel_group(self, group):
        with self.lock:
            routes = [route for route in self.transports if route.group == group]
        for route in routes:
            route.abort()

    def cancel_all(self):
        for group in GROUP_IDS:
            self.cancel_group(group)

    usage_for_slot = staticmethod(usage_for_slot)
    recovery_queue_record = staticmethod(recovery_queue_record)


class GroupView:
    def __init__(self, runtime, group):
        self.runtime, self.group = runtime, group

    def budget_status(self):
        return budget_status(self.group)

    def logical_resident(self):
        identity = {
            "version": VERSION,
            "model_key": "DEEPSEEK",
            "model": PRICING["model"],
            "model_revision": PRICING["documented_model_version"],
            "documented_model_version": PRICING["documented_model_version"],
            "provider_weight_revision_pinnable": False,
            "project_training_adapter_loaded": False,
            "context_limit": 131072,
            "max_output_tokens": 32768,
            "thinking": False,
            "service_admission_complete": True,
            "port": 18219,
            "endpoint": ENDPOINT,
            "host_listener": False,
            "deployment_version": VERSION,
            "organization_id": self.group,
            "tool_schema_inventory": reference(SCHEMAS),
            "ledger_path": str(scope.LEDGER_FILES[self.group]),
            "cash_cap_CNY": str(Decimal(api_for(self.group).CAP_NANOYUAN) / 10**9),
            "original_cash_cap_CNY": "450",
            "cash_cap_scope": "shared_remaining_amended450",
            "cash_authority": reference(AUTHORITY),
            "new_neutral_calls": 0,
            "provider_health_qualification": "first_actual_valid_returned_response_not_assumed_prevalidated",
            "logical_recovery_HTTP_attempts": 3,
            "new_independent_episode_identity": True,
        }
        path = scope.API_ROOT / "api-runtime" / self.group / "identity.json"
        ref = scope.retain(path, identity)
        return {
            "model_key": "DEEPSEEK",
            "endpoint": ENDPOINT,
            "api_key_file": None,
            "identity": ref,
            "identity_value": identity,
            "directory": str(path.parent),
            "logical_only_no_listener": True,
        }

    def transport_factory(self, row, output):
        if row["organization_id"] != self.group:
            raise ValueError("A group view cannot dispatch another organization")
        return self.runtime.transport_factory(row, output)

    def cancel_all(self):
        self.runtime.cancel_group(self.group)

    def settled_route_witnesses(self):
        with self.runtime.lock:
            candidates = sorted(self.runtime.successful_routes[self.group])
        return {"PROJECT": candidates[0]} if candidates else {}

    usage_for_slot = staticmethod(usage_for_slot)
    recovery_queue_record = staticmethod(recovery_queue_record)
    preparation_usage = staticmethod(
        lambda: {
            "calls": [],
            "unresolved_calls": [],
            "usage_capture_complete": True,
            "new_preparation_API_calls": 0,
        }
    )
