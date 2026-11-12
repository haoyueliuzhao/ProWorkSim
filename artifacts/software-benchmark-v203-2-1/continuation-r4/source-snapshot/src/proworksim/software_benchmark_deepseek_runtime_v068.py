"""API recovery using the current unconsumed inventory and original money ledger.

The qualified v067 wire/receipt adapter is reused without changing its globals.
Only the recovery authority, eligible original slots and identity path differ.
"""
from __future__ import annotations

from pathlib import Path

from . import software_benchmark_dispatch_v066 as policy
from . import software_benchmark_deepseek_runtime_v067 as frozen
from .software_benchmark_candidates_v054 import checked, reference

VERSION = "v068-original-api-recovery-r1"
ROOT = policy.ROOT
RECOVERY_ROOT = ROOT / "runs/software-benchmark-v068/recovery-r1"
INVENTORY_FILE = RECOVERY_ROOT / "continuation-inventory.json"
IDENTITY_FILE = RECOVERY_ROOT / "api-coordinator/api-runtime/identity.json"
LEDGER = frozen.LEDGER
MAX_CONCURRENCY = frozen.MAX_CONCURRENCY
APIQualificationPending = frozen.APIQualificationPending
APIUnavailable = frozen.APIUnavailable


def select_eligible_api_rows(inventory, planned, original, used, *, claims_root):
    """Exclude any prior request or consumed actor, even a zero-request actor."""
    originals = {row["slot_id"]: row for row in original}
    if len(originals) != 6000 or len(planned) != 6000 or len({row["slot_id"] for row in planned}) != 6000:
        raise ValueError("Recovery must preserve the full original six-thousand-slot panel")
    fields = ("slot_index", "slot_id", "condition_id", "instance_id", "model_key", "arm",
              "input_plus_output_tokens", "seed", "configuration")
    for row in planned:
        bound = originals.get(row["slot_id"])
        if bound is None or any(row.get(key) != bound.get(key) for key in fields):
            raise ValueError("Recovery changed an original slot or model-visible configuration")
    eligible = inventory["allowed_generation_slot_ids"]
    indices = inventory["allowed_generation_slot_indices"]
    if (len(set(eligible)) != len(eligible) or len(indices) != len(eligible)
            or set(eligible) - originals.keys()
            or set(indices) != {originals[slot]["slot_index"] for slot in eligible}
            or inventory["API_ledger"] != str(LEDGER)):
        raise ValueError("Recovery eligibility or the sole original money ledger changed")
    eligible_set = set(eligible)
    selected = {row["slot_id"]: row for row in planned
                if row["slot_id"] in eligible_set and row["model_key"] == "DEEPSEEK"}
    if used & selected.keys():
        raise ValueError("A current API-eligible slot already has request evidence")
    for row in selected.values():
        if (Path(claims_root) / f"actor-{row['slot_index']}.json").exists():
            raise ValueError("A consumed actor identity cannot be recovered or replayed")
    return selected


class DeepSeekRuntime(frozen.DeepSeekRuntime):
    def __init__(self, *, scope_guard=None, inventory_ref=None):
        super().__init__(scope_guard=scope_guard)
        self.inventory_ref = inventory_ref

    def _require_allowed(self, *, slot_id=None, instance_id=None):
        if not callable(self._scope_guard):
            raise APIQualificationPending("API recovery requires its own sealed scoped authority")
        self._scope_guard("v068.api.request", slot_id=slot_id, instance_id=instance_id)
        return policy.require_v066_allowed("v066.api.request", slot_id=slot_id, instance_id=instance_id)

    def read_only_preflight(self):
        status = frozen.budget_status()
        if status["state"] != "ready":
            raise APIUnavailable(status)
        self.qualified = policy.load(reference(frozen.QUALIFICATION))
        if (self.qualified.get("passed") is not True or self.qualified.get("model_calls") != 2
                or self.qualified.get("unknown_usage_calls") != 0
                or type(self.qualified.get("actual_known_input_output_tokens")) is not int
                or not 0 <= self.qualified["actual_known_input_output_tokens"] <= 8192):
            raise APIQualificationPending("Original neutral API qualification is incomplete")
        preparation = policy.load(self.qualified["plan"])
        if (Path(self.qualified["plan"]["path"]).resolve() != frozen.QUALIFICATION.parent / "plan.json"
                or preparation.get("ledger") != str(LEDGER)
                or self.qualified.get("cash_snapshot", {}).get("ledger_path") != str(LEDGER)):
            raise ValueError("Recovery must retain the original unique CNY1500 ledger")
        for source in preparation["sources"]:
            checked(source)
        self.preparation_usage_validation = frozen.validate_existing_preparation_usage(
            frozen.preparation_usage(), self.qualified)
        self.schemas = policy.load(frozen.prepare_schema_inventory())
        self.inventory_ref = self.inventory_ref or reference(INVENTORY_FILE)
        if Path(self.inventory_ref["path"]).resolve() != INVENTORY_FILE.resolve():
            raise ValueError("Recovery runtime received another continuation inventory")
        self.inventory = policy.load(self.inventory_ref)
        original = policy.load(reference(policy.PREDECESSOR_ROOT / "plan.json"))["rows"]
        planned = policy.load(reference(policy.PLAN_FILE))["rows"]
        with frozen._ledger_read() as db:
            used = {row[0] for row in db.execute("SELECT DISTINCT slot_id FROM requests")}
        self.rows = select_eligible_api_rows(self.inventory, planned, original, used,
            claims_root=policy.BATCH_ROOT / "resource-claims")
        names = set(self.schemas["tool_names"]["REF"]) | set(self.schemas["tool_names"]["PROJECT"])
        return {"preparation": preparation, "allowed_tool_names": names,
                "eligible_API_slots": len(self.rows), "neutral_usage": self.preparation_usage_validation}

    def logical_resident(self):
        if self.client is None or self.counter is None or self.qualified is None:
            raise APIQualificationPending("Explicit qualified API recovery initialization required")
        api = frozen.api
        identity = {"version": VERSION, "model_key": "DEEPSEEK", "model": api.MODEL,
            "model_revision": api.DOCUMENTED_MODEL_VERSION,
            "documented_model_version": api.DOCUMENTED_MODEL_VERSION,
            "provider_weight_revision_pinnable": False, "project_training_adapter_loaded": False,
            "context_limit": api.CONTEXT_TOKENS, "max_output_tokens": api.MAX_OUTPUT_TOKENS,
            "thinking": True, "service_admission_complete": True, "port": 18219,
            "endpoint": frozen.ENDPOINT, "host_listener": False, "deployment_version": VERSION,
            "qualification": reference(frozen.QUALIFICATION), "tool_schema_inventory": reference(frozen.SCHEMA_FILE),
            "continuation_inventory": self.inventory_ref,
            "ledger_path": str(LEDGER), "cash_cap_CNY": "1500.00", "new_neutral_calls": 0}
        ref = policy.retain(IDENTITY_FILE, identity)
        return {"model_key": "DEEPSEEK", "endpoint": frozen.ENDPOINT, "api_key_file": None,
            "identity": ref, "identity_value": identity, "directory": str(IDENTITY_FILE.parent),
            "logical_only_no_listener": True}

    @staticmethod
    def budget_status():
        return {**frozen.budget_status(), "version": VERSION}
