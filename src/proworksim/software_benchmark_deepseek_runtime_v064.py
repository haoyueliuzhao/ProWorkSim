"""Trusted-host wiring for one qualified DeepSeek service and one CNY ledger.

Construction and status/statistics reads do not load a key or contact an API.
Only initialize_for_run opens the real client after the experiment grant passes.
The logical loopback endpoint names the private FIFO route; no listener exists.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import sqlite3

from . import software_benchmark_dispatch_v064 as policy
from . import software_benchmark_deepseek_api_v064 as api
from . import software_benchmark_sdk_bundle_v064 as sdk
from .software_benchmark_deepseek_adapter_v064 import HostDeepSeekTransport
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_usage_metrics_v064 import normalize_usage_call

ROOT = policy.ROOT
VERSION = "v064-qualified-deepseek-host-runtime-r1"
ENDPOINT = "http://127.0.0.1:18219"
LEDGER = policy.BATCH_ROOT / "api-budget/ledger.sqlite3"
QUALIFICATION = policy.BATCH_ROOT / "api-qualification/result.json"
SCHEMA_FILE = policy.BATCH_ROOT / "api-runtime/tool-schemas.json"
IDENTITY_FILE = policy.BATCH_ROOT / "api-runtime/identity.json"
PROJECT_FIXTURE = ROOT / "runs/software-benchmark-v064/project-sdk-cpu-r3"
MAX_CONCURRENCY = 64


class APIQualificationPending(RuntimeError):
    """No qualified remote service is available; Qwen work may continue."""


@lru_cache(maxsize=1)
def qualifier_module():
    name = "proworksim_v064_api_qualifier_binding"
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/qualify_deepseek_v064.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    if value.LEDGER != LEDGER or value.RUN_ROOT / "result.json" != QUALIFICATION:
        raise ValueError("Formal requests and neutral qualification must share the exact CNY1500 ledger")
    return value


def _names(schemas):
    if not isinstance(schemas, list) or not schemas:
        raise ValueError("An actual nonempty SDK function schema list is required")
    names = []
    for item in schemas:
        if not isinstance(item, dict) or item.get("type") != "function":
            raise ValueError("Only local SDK function tools may reach the API")
        name = item.get("function", {}).get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Actual SDK tool names must be unique")
        names.append(name)
    return sorted(names)


def prepare_schema_inventory():
    """Reuse completed CPU SDK observations; do not run another model/fixture."""
    sdk_ref = reference(sdk.OUTPUT / "manifest.json")
    manifest = policy.load(sdk_ref)
    if manifest.get("adapter") != reference(sdk.__file__):
        raise ValueError("The current cropped SDK bundle has not been qualified")
    interfaces = manifest["probe"]["interfaces"]
    native = list(interfaces["DEEPSEEK"]["tool_schemas"].values())
    if interfaces["DEEPSEEK"]["tool_schemas"] != interfaces["QWEN"]["tool_schemas"]:
        raise ValueError("Native model conditions must expose the same actual tools")
    result_ref = reference(PROJECT_FIXTURE / "result.json")
    result = policy.load(result_ref)
    if (result.get("passed") is not True or result.get("real_model_calls") != 0
            or result.get("actual_single_agent_SDK_runtime") is not True):
        raise ValueError("The actual managed SDK fixture is unavailable")
    request_ref = reference(PROJECT_FIXTURE / "runtime/managed-transport/request-00001/wire-request.json")
    project = policy.load(request_ref)["tools"]
    value = {"version": VERSION, "source_sdk_manifest": sdk_ref,
             "source_project_sdk_fixture": result_ref, "source_project_wire_request": request_ref,
             "schemas": {"REF": native, "PROJECT": project},
             "tool_names": {"REF": _names(native), "PROJECT": _names(project)},
             "names_are_from_real_SDK_wire_not_guessed_aliases": True,
             "model_calls": 0, "network_calls": 0}
    return policy.retain(SCHEMA_FILE, value)


@contextmanager
def _ledger_read():
    if not LEDGER.is_file():
        raise APIQualificationPending("The one shared API ledger has not been initialized")
    db = sqlite3.connect(LEDGER.as_uri()+"?mode=ro", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        row = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
        if row is None or json.loads(row[0]) != {**api.POLICY, "max_concurrency": MAX_CONCURRENCY}:
            raise ValueError("Formal API accounting must use the exact immutable CNY1500 policy")
        yield db
    finally:
        db.close()


def _cny(nanoyuan):
    return format(Decimal(nanoyuan)/Decimal(api.NANOYUAN), "f")


def budget_status():
    if not QUALIFICATION.is_file():
        return {"state": "qualification_pending", "can_start_generation": False,
                "temporary_wait": True, "monetary_scope": "CNY1500 shared with preparation"}
    qualification = policy.load(reference(QUALIFICATION))
    if qualification.get("passed") is not True:
        return {"state": "qualification_failed", "can_start_generation": False,
                "temporary_wait": False, "qualification": reference(QUALIFICATION)}
    try:
        with _ledger_read() as db:
            totals = api.BudgetLedger._totals(db)
            halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
            cooldown = db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
    except (OSError, ValueError, sqlite3.Error, APIQualificationPending) as error:
        return {"state": "shared_halted", "can_start_generation": False, "temporary_wait": False,
                "reason": "accounting_unavailable:"+type(error).__name__}
    remaining = api.CAP_NANOYUAN-totals["committed"]
    waits = api.transport.cooldown_state(cooldown[0] if cooldown else None)
    state = "ready"
    if halt or remaining < 0:
        state = "shared_halted"
    elif remaining < api.ABSOLUTE_RESERVATION_NANOYUAN:
        state = "waiting_inflight_cash" if totals["inflight"] else "cash_exhausted"
    elif (totals["inflight"] or 0) >= MAX_CONCURRENCY:
        state = "waiting_concurrency"
    elif waits["admission_wait_seconds"] > 0:
        state = "waiting_cooldown"
    return {"version": VERSION, "state": state, "can_start_generation": state == "ready",
            "temporary_wait": state.startswith("waiting_"),
            "reason": halt[0] if halt else ("cash_commitment_exceeded_cap" if remaining < 0 else None),
            "cap_CNY": "1500.00", "remaining_CNY": _cny(remaining),
            "committed_upper_CNY": _cny(totals["committed"]), "settled_upper_CNY": _cny(totals["settled"]),
            "uncertain_reserved_CNY": _cny(totals["uncertain"]), "inflight_count": totals["inflight"] or 0,
            "attempts": totals["attempts"], "ledger_path": str(LEDGER), **waits}


def _usage(slot_id, *, expected_condition=None):
    try:
        with _ledger_read() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM requests WHERE slot_id=? ORDER BY request_id", (slot_id,))]
    except APIQualificationPending:
        return {"calls": [], "unresolved_calls": [], "usage_capture_complete": False,
                "usage_source": "shared_api_ledger_not_yet_available"}
    calls, unresolved = [], []
    for row in rows:
        if expected_condition is not None and row["condition"] != expected_condition:
            raise ValueError("A shared-ledger request belongs to another condition")
        if row["usage_json"] is not None and row["settled_nanoyuan"] is not None:
            usage = json.loads(row["usage_json"])
            # Preserve an explicitly reported synonymous cached-token field.
            if "prompt_cache_hit_tokens" not in usage and isinstance(usage.get("prompt_tokens_details"), dict):
                cached = usage["prompt_tokens_details"].get("cached_tokens")
                if cached is not None:
                    usage["prompt_cache_hit_tokens"] = cached
            calls.append(normalize_usage_call(row["request_id"], row["usage_id"], usage,
                                               accounted_cost_cny=_cny(row["settled_nanoyuan"])))
        else:
            if type(row["prompt_upper_bound"]) is not int or type(row["max_output_tokens"]) is not int:
                raise ValueError("Unknown calls require their explicit original token reservation")
            unresolved.append({"call_id": row["request_id"], "purpose": row["usage_id"],
                "reserved_tokens": row["prompt_upper_bound"]+row["max_output_tokens"],
                "reserved_cost_cny": _cny(row["reserved_nanoyuan"]),
                "reservation_is_actual_usage": False, "reservation_is_provider_absolute_token_bound": False,
                "provider_absolute_context_tokens": api.PROVIDER_CONTEXT_TOKENS, "status": row["status"]})
    return {"calls": calls, "unresolved_calls": unresolved, "usage_capture_complete": not unresolved,
            "usage_source": "shared_authoritative_API_request_ledger",
            "known_withheld_response_usage_included": True}


def usage_for_slot(row):
    if row.get("model_key") != "DEEPSEEK" or not str(row.get("slot_id", "")).startswith("v064:"):
        raise ValueError("Read provider usage only for a planned new API episode")
    return _usage(row["slot_id"], expected_condition=row["condition_id"])


def preparation_usage():
    qualifier = qualifier_module()
    return _usage(qualifier.SLOT, expected_condition=qualifier.CONDITION)


class DeepSeekRuntime:
    def __init__(self):
        self.client = self.counter = None
        self.rows, self.schemas, self.qualified = None, None, None

    def initialize_for_run(self):
        policy.require_v064_allowed("v064.api.request")
        if self.client is not None:
            return self.logical_resident()
        qualifier = qualifier_module()
        if not QUALIFICATION.is_file():
            raise APIQualificationPending("The fixed neutral API qualification has not completed")
        self.qualified = policy.load(reference(QUALIFICATION))
        if (self.qualified.get("passed") is not True or self.qualified.get("model_calls") != 2
                or self.qualified.get("unknown_usage_calls") != 0
                or self.qualified.get("actual_known_input_output_tokens", 8193) > 8192):
            raise APIQualificationPending("The two neutral calls lack complete trustworthy qualification")
        preparation = policy.load(self.qualified["plan"])
        if (Path(self.qualified["plan"]["path"]).resolve() != qualifier.RUN_ROOT / "plan.json"
                or preparation.get("ledger") != str(LEDGER)
                or self.qualified.get("cash_snapshot", {}).get("ledger_path") != str(LEDGER)):
            raise ValueError("Qualification and formal execution cannot split the money budget")
        for source in preparation["sources"]:
            checked(source)
        self.schemas = policy.load(reference(SCHEMA_FILE))
        for field in ("source_sdk_manifest", "source_project_sdk_fixture", "source_project_wire_request"):
            checked(self.schemas[field])
        if (self.schemas.get("version") != VERSION
                or self.schemas["tool_names"] != {arm: _names(self.schemas["schemas"][arm]) for arm in ("REF", "PROJECT")}):
            raise ValueError("The actual model-facing tool inventory changed")
        plan = policy.load(reference(policy.PLAN_FILE))
        self.rows = {row["slot_id"]: row for row in plan["rows"] if row["model_key"] == "DEEPSEEK"}
        if len(self.rows) != 3000:
            raise ValueError("The full experiment needs exactly 3000 predetermined API episodes")
        names = set(self.schemas["tool_names"]["REF"]) | set(self.schemas["tool_names"]["PROJECT"])
        client = api.DeepSeekClient(ledger_path=LEDGER, api_key=api.load_api_key(ROOT / ".env"),
                                   allowed_tool_names=names, max_concurrency=MAX_CONCURRENCY)
        tokenizer = preparation["tokenizer_manifest"]
        counter = OfficialDeepSeekCounter(tokenizer["path"], manifest_sha256=tokenizer["sha256"],
                                         reservation_margin_tokens=preparation["counter_margin_tokens"])
        self.client, self.counter = client, counter
        return self.logical_resident()

    def logical_resident(self):
        if self.client is None or self.counter is None or self.qualified is None:
            raise APIQualificationPending("Explicit formal initialization is required before dispatch")
        identity = {"version": VERSION, "model_key": "DEEPSEEK", "model": api.MODEL,
            "model_revision": api.DOCUMENTED_MODEL_VERSION, "documented_model_version": api.DOCUMENTED_MODEL_VERSION,
            "provider_weight_revision_pinnable": False, "project_training_adapter_loaded": False,
            "context_limit": api.CONTEXT_TOKENS, "max_output_tokens": api.MAX_OUTPUT_TOKENS,
            "thinking": True, "service_admission_complete": True, "port": 18219,
            "endpoint": ENDPOINT, "host_listener": False, "deployment_version": VERSION,
            "qualification": reference(QUALIFICATION), "tool_schema_inventory": reference(SCHEMA_FILE),
            "ledger_path": str(LEDGER), "cash_cap_CNY": "1500.00"}
        identity_ref = policy.retain(IDENTITY_FILE, identity)
        return {"model_key": "DEEPSEEK", "endpoint": ENDPOINT, "api_key_file": None,
                "identity": identity_ref, "identity_value": identity,
                "directory": str(IDENTITY_FILE.parent), "logical_only_no_listener": True}

    def transport_factory(self, row, output):
        if self.client is None or self.rows is None:
            raise APIQualificationPending("Initialize the qualified host API runtime first")
        bound = self.rows.get(row.get("slot_id"))
        fields = ("slot_id", "condition_id", "instance_id", "model_key", "arm", "input_plus_output_tokens")
        if bound is None or any(row.get(key) != bound[key] for key in fields):
            raise ValueError("Only the frozen planned API model/interface/budget slot may dispatch")
        policy.require_v064_allowed("v064.api.request", slot_id=row["slot_id"], instance_id=row["instance_id"])
        allowed = set(self.schemas["tool_names"][row["arm"]])

        def authorize(payload):
            policy.require_v064_allowed("v064.api.request", slot_id=row["slot_id"], instance_id=row["instance_id"])
            prefix = row["slot_id"]+":"
            index = payload.get("request_id", "").removeprefix(prefix)
            if (payload.get("slot_id") != row["slot_id"] or payload.get("condition") != row["condition_id"]
                    or not payload.get("request_id", "").startswith(prefix) or len(index) != 4 or not index.isdigit()
                    or not 1 <= int(index) <= 512 or payload["wire"].get("max_tokens") != api.MAX_OUTPUT_TOKENS):
                raise ValueError("Broker request identity or output limit differs from the frozen slot")
            tools = payload["wire"].get("tools", [])
            actual = set(_names(tools)) if tools else set()
            if ((payload.get("usage_id") == "agent" and actual != allowed)
                    or (payload.get("usage_id") == "condenser" and tools)):
                raise ValueError("Agent/condenser tools differ from the actual frozen SDK names")
            return {"condition_id": row["condition_id"], "token_budget": row["input_plus_output_tokens"]}

        return HostDeepSeekTransport(client=self.client, counter=self.counter,
            metadata_dir=Path(output)/"host-api-counts", authorize=authorize,
            slot_id=row["slot_id"], condition_id=row["condition_id"])

    @staticmethod
    def budget_status():
        return budget_status()

    @staticmethod
    def usage_for_slot(row):
        return usage_for_slot(row)

    @staticmethod
    def preparation_usage():
        return preparation_usage()
