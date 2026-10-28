"""Continue the original API experiment without resetting money or model state.

Only new, never-generated v064 slot identities are eligible. The controller
bundle, Flash thinking wire format, official tokenizer and CNY1500 ledger are
the original ones. This module changes trusted-host dispatch scope only.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import threading
import weakref

from . import software_benchmark_dispatch_v066 as policy
from . import software_benchmark_deepseek_runtime_v064 as predecessor
from . import software_benchmark_deepseek_api_v064 as api
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_deepseek_adapter_v064 import HostDeepSeekTransport
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from .software_benchmark_usage_metrics_v064 import validate_call

VERSION = "v067-qualified-v064-deepseek-api-sidecar-r1"
ROOT = policy.ROOT
ENDPOINT = predecessor.ENDPOINT
LEDGER = predecessor.LEDGER
QUALIFICATION = predecessor.QUALIFICATION
SCHEMA_FILE = predecessor.SCHEMA_FILE
SIDECAR_ROOT = ROOT / "runs/software-benchmark-v067/api-continuation-r1"
IDENTITY_FILE = SIDECAR_ROOT / "api-runtime/identity.json"
MAX_CONCURRENCY = predecessor.MAX_CONCURRENCY
APIQualificationPending = predecessor.APIQualificationPending
_ledger_read = predecessor._ledger_read
usage_for_slot = predecessor.usage_for_slot
preparation_usage = predecessor.preparation_usage


class APIUnavailable(APIQualificationPending):
    """Stop only API admission; preserve independent Qwen and grading work."""

    def __init__(self, status):
        super().__init__("API continuation unavailable: " + str(status.get("state")))
        self.api_status = status
        self.failure_scope = "API"


def budget_status():
    """Read the unique old ledger; unpriced requests pause only this provider."""
    try:
        value = predecessor.budget_status()
        if value["state"] not in {"qualification_pending", "qualification_failed"}:
            with _ledger_read() as db:
                statuses = dict(db.execute("SELECT status,COUNT(*) FROM requests GROUP BY status"))
            value["request_statuses"] = statuses
            # Reserved is an active request; uncertain is an unpriced completed
            # attempt and must not be hidden by the available cash balance.
            if statuses.get("uncertain", 0) or set(statuses) - {"settled", "reserved", "uncertain"}:
                value.update(state="shared_halted", can_start_generation=False,
                    temporary_wait=False, reason="API_usage_or_provider_outcome_unknown")
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, APIQualificationPending) as error:
        value = {"state": "shared_halted", "can_start_generation": False,
            "temporary_wait": False, "reason": "API_accounting_unavailable:" + type(error).__name__}
    return {**value, "version": VERSION, "failure_scope": "API", "qwen_stop_required": False,
        "ledger_path": str(LEDGER), "cap_CNY": "1500.00", "new_cash_budget": False,
        "new_neutral_calls": 0}


def prepare_schema_inventory():
    """Validate and reference the frozen inventory without rewriting it."""
    ref = reference(SCHEMA_FILE)
    value = policy.load(ref)
    for field in ("source_sdk_manifest", "source_project_sdk_fixture", "source_project_wire_request"):
        checked(value[field])
    if (value.get("version") != predecessor.VERSION or value["tool_names"] != {
            arm: predecessor._names(value["schemas"][arm]) for arm in ("REF", "PROJECT")}):
        raise ValueError("The original real SDK tool inventory changed")
    return ref


def validate_existing_preparation_usage(neutral, qualification):
    """Validate canonical settled receipts; sum the two explicit token parts."""
    expected = qualification.get("actual_known_input_output_tokens")
    if (neutral.get("usage_capture_complete") is not True or neutral.get("unresolved_calls") != []
            or not isinstance(neutral.get("calls"), list) or len(neutral["calls"]) != 2
            or type(expected) is not int or not 0 <= expected <= 8192):
        raise APIQualificationPending("The original neutral receipts no longer match qualification")
    try:
        calls = [validate_call(call) for call in neutral["calls"]]
    except (TypeError, ValueError, KeyError) as error:
        raise APIQualificationPending("Neutral usage requires explicit trustworthy canonical token fields") from error
    if (len({call["call_id"] for call in calls}) != 2
            or any(call["purpose"] != "preparation" for call in calls)):
        raise APIQualificationPending("The neutral receipt identities are duplicated or changed")
    prompt = sum(call["prompt_tokens"] for call in calls)
    completion = sum(call["completion_tokens"] for call in calls)
    if prompt + completion != expected:
        raise APIQualificationPending("The original neutral token total differs from qualification")
    return {"calls": 2, "prompt_tokens": prompt, "completion_tokens": completion,
            "actual_input_plus_output_tokens": prompt + completion,
            "canonical_call_ids": [call["call_id"] for call in calls],
            "usage_capture_complete": True, "new_API_calls": 0}


class DeepSeekRuntime:
    def __init__(self, *, scope_guard=None):
        self.client = self.counter = None
        self.rows = self.schemas = self.qualified = self.inventory = None
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._transports = weakref.WeakSet()
        self._claimed_slots = set()
        self._scope_guard = scope_guard

    def _require_allowed(self, *, slot_id=None, instance_id=None):
        if not callable(self._scope_guard):
            raise APIQualificationPending("The new API sidecar requires its own explicit scoped guard")
        self._scope_guard("v067.api.request", slot_id=slot_id, instance_id=instance_id)
        return policy.require_v066_allowed("v066.api.request", slot_id=slot_id, instance_id=instance_id)

    def read_only_preflight(self):
        """Validate existing records through the client boundary, without keys or writes."""
        status = budget_status()
        if status["state"] != "ready":
            raise APIUnavailable(status)
        self.qualified = policy.load(reference(QUALIFICATION))
        if (self.qualified.get("passed") is not True or self.qualified.get("model_calls") != 2
                or self.qualified.get("unknown_usage_calls") != 0
                or type(self.qualified.get("actual_known_input_output_tokens")) is not int
                or not 0 <= self.qualified["actual_known_input_output_tokens"] <= 8192):
            raise APIQualificationPending("Reuse requires the original two complete neutral API calls")
        preparation = policy.load(self.qualified["plan"])
        if (Path(self.qualified["plan"]["path"]).resolve() != QUALIFICATION.parent / "plan.json"
                or preparation.get("ledger") != str(LEDGER)
                or self.qualified.get("cash_snapshot", {}).get("ledger_path") != str(LEDGER)):
            raise ValueError("Continuation must retain the original unique CNY1500 ledger")
        for source in preparation["sources"]:
            checked(source)
        # The neutral receipts remain authoritative and are not replayed.
        neutral = preparation_usage()
        self.preparation_usage_validation = validate_existing_preparation_usage(neutral, self.qualified)
        self.schemas = policy.load(prepare_schema_inventory())
        self.inventory = policy.load(reference(policy.RESUME_FILE))
        if self.inventory["original_plan"] != reference(policy.PREDECESSOR_ROOT / "plan.json"):
            raise ValueError("Continuation must reference the unchanged original plan")
        checked(self.inventory["predecessor_evidence"])
        planned = policy.load(reference(policy.PLAN_FILE))["rows"]
        original = policy.load(self.inventory["original_plan"])["rows"]
        original_by_id = {row["slot_id"]: row for row in original}
        fields = ("slot_index", "slot_id", "condition_id", "instance_id", "model_key", "arm",
                  "input_plus_output_tokens", "seed", "configuration")
        if len(original_by_id) != 6000 or len(planned) != 6000:
            raise ValueError("The original complete six-thousand-slot plan is required")
        for row in planned:
            bound = original_by_id.get(row["slot_id"])
            if bound is None or any(row.get(key) != bound.get(key) for key in fields):
                raise ValueError("Continuation changed a logical experiment slot")
        eligible = self.inventory["continuation_slot_ids"]
        indices = self.inventory["continuation_slot_indices"]
        if (len(set(eligible)) != len(eligible) or len(indices) != len(eligible)
                or set(indices) != {original_by_id[slot]["slot_index"] for slot in eligible}):
            raise ValueError("Continuation inventory identities disagree")
        self.rows = {row["slot_id"]: row for row in planned
                     if row["slot_id"] in set(eligible) and row["model_key"] == "DEEPSEEK"}
        with _ledger_read() as db:
            used = {row[0] for row in db.execute("SELECT DISTINCT slot_id FROM requests")}
        if used & self.rows.keys():
            raise ValueError("An API slot with any prior request cannot be replayed")
        names = set(self.schemas["tool_names"]["REF"]) | set(self.schemas["tool_names"]["PROJECT"])
        return {"preparation": preparation, "allowed_tool_names": names,
                "eligible_API_slots": len(self.rows), "neutral_usage": self.preparation_usage_validation}

    def initialize_for_run(self):
        self._require_allowed()
        if self.client is not None:
            return self.logical_resident()
        checked_preparation = self.read_only_preflight()
        preparation = checked_preparation["preparation"]
        names = checked_preparation["allowed_tool_names"]
        tokenizer = preparation["tokenizer_manifest"]
        counter = OfficialDeepSeekCounter(tokenizer["path"], manifest_sha256=tokenizer["sha256"],
            reservation_margin_tokens=preparation["counter_margin_tokens"])
        # Initialization is the only key-loading operation. Constructors and
        # statistics remain read-only, and no metadata or neutral call is made.
        client = api.DeepSeekClient(ledger_path=LEDGER, api_key=api.load_api_key(ROOT / ".env"),
            allowed_tool_names=names, max_concurrency=MAX_CONCURRENCY)
        self.client, self.counter = client, counter
        return self.logical_resident()

    def logical_resident(self):
        if self.client is None or self.counter is None or self.qualified is None:
            raise APIQualificationPending("Explicit qualified continuation initialization required")
        identity = {"version": VERSION, "model_key": "DEEPSEEK", "model": api.MODEL,
            "model_revision": api.DOCUMENTED_MODEL_VERSION,
            "documented_model_version": api.DOCUMENTED_MODEL_VERSION,
            "provider_weight_revision_pinnable": False, "project_training_adapter_loaded": False,
            "context_limit": api.CONTEXT_TOKENS, "max_output_tokens": api.MAX_OUTPUT_TOKENS,
            "thinking": True, "service_admission_complete": True, "port": 18219,
            "endpoint": ENDPOINT, "host_listener": False, "deployment_version": VERSION,
            "qualification": reference(QUALIFICATION), "tool_schema_inventory": reference(SCHEMA_FILE),
            "continuation_inventory": reference(policy.RESUME_FILE),
            "ledger_path": str(LEDGER), "cash_cap_CNY": "1500.00", "new_neutral_calls": 0}
        ref = policy.retain(IDENTITY_FILE, identity)
        return {"model_key": "DEEPSEEK", "endpoint": ENDPOINT, "api_key_file": None,
            "identity": ref, "identity_value": identity, "directory": str(IDENTITY_FILE.parent),
            "logical_only_no_listener": True}

    def transport_factory(self, row, output):
        if self.client is None or self.rows is None:
            raise APIQualificationPending("Initialize the qualified host API continuation first")
        bound = self.rows.get(row.get("slot_id"))
        fields = ("slot_id", "slot_index", "condition_id", "instance_id", "model_key", "arm",
                  "input_plus_output_tokens", "seed", "configuration")
        if bound is None or any(row.get(key) != bound.get(key) for key in fields):
            raise ValueError("Only an eligible unchanged original API slot may dispatch")
        self._require_allowed(slot_id=row["slot_id"], instance_id=row["instance_id"])
        with _ledger_read() as db:
            if db.execute("SELECT 1 FROM requests WHERE slot_id=? LIMIT 1", (row["slot_id"],)).fetchone():
                raise ValueError("Existing API request evidence forbids replay")
        allowed = set(self.schemas["tool_names"][row["arm"]])

        def authorize(payload):
            self._require_allowed(slot_id=row["slot_id"], instance_id=row["instance_id"])
            if self._cancelled.is_set():
                raise api.PreDispatchBudgetStopped("API_provider_dispatch_stopped_before_HTTP")
            status = budget_status()
            if not status["can_start_generation"]:
                kind = api.PreDispatchConcurrencyBusy if status["temporary_wait"] else api.PreDispatchBudgetStopped
                raise kind("API_provider_admission:" + status["state"])
            prefix = row["slot_id"] + ":"
            index = payload.get("request_id", "").removeprefix(prefix)
            if (payload.get("slot_id") != row["slot_id"] or payload.get("condition") != row["condition_id"]
                    or not payload.get("request_id", "").startswith(prefix) or len(index) != 4 or not index.isdigit()
                    or not 1 <= int(index) <= 512 or payload["wire"].get("max_tokens") != api.MAX_OUTPUT_TOKENS):
                raise ValueError("Broker request differs from the original slot identity or output bound")
            tools = payload["wire"].get("tools", [])
            actual = set(predecessor._names(tools)) if tools else set()
            if ((payload.get("usage_id") == "agent" and actual != allowed)
                    or (payload.get("usage_id") == "condenser" and tools)):
                raise ValueError("Agent/condenser tools changed from the frozen real SDK schemas")
            return {"condition_id": row["condition_id"], "token_budget": row["input_plus_output_tokens"]}

        with self._lock:
            if self._cancelled.is_set():
                raise api.PreDispatchBudgetStopped("API_provider_dispatch_stopped_before_HTTP")
            if row["slot_id"] in self._claimed_slots:
                raise ValueError("A continuation API slot can have only one fresh broker")
            value = HostDeepSeekTransport(client=self.client, counter=self.counter,
                metadata_dir=Path(output) / "host-api-counts", authorize=authorize,
                slot_id=row["slot_id"], condition_id=row["condition_id"])
            self._claimed_slots.add(row["slot_id"])
            self._transports.add(value)
        return value

    def cancel_all(self):
        """Cancel only this API runtime's private sockets; never Qwen/services."""
        with self._lock:
            self._cancelled.set()
            transports = list(self._transports)
        failures = []
        for transport in transports:
            try:
                transport.abort()
            except Exception as error:
                failures.append({"slot_id": transport.slot_id, "error_type": type(error).__name__})
        return {"failure_scope": "API", "transports_signalled": len(transports), "errors": failures,
            "qwen_touched": False, "money_reservations_released": False}

    @staticmethod
    def budget_status():
        return budget_status()

    @staticmethod
    def usage_for_slot(row):
        return usage_for_slot(row)

    @staticmethod
    def preparation_usage():
        return preparation_usage()
