"""Original five-million-token API slots under the separately sealed expansion."""
from __future__ import annotations

import types

from . import software_benchmark_deepseek_runtime_v068 as prior
from . import software_benchmark_dispatch_v066 as policy

VERSION = "v069-original-api-5m-expansion-r1"
ROOT = policy.ROOT
BATCH_ROOT = ROOT / "runs/software-benchmark-v069/api-5m-expansion-r1"
INVENTORY_FILE = BATCH_ROOT / "continuation-inventory.json"
IDENTITY_FILE = BATCH_ROOT / "api-coordinator/api-runtime/identity.json"
LEDGER = prior.LEDGER
MAX_CONCURRENCY = prior.MAX_CONCURRENCY
APIQualificationPending = prior.APIQualificationPending


def private_function(function, **overrides):
    """Bind trusted new scope in a private namespace; preserve frozen globals."""
    namespace = {**function.__globals__, **overrides}
    value = types.FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    value.__kwdefaults__ = dict(function.__kwdefaults__ or {})
    return value


def select_eligible_api_rows(inventory, planned, original, used, *, claims_root):
    rows = prior.select_eligible_api_rows(inventory, planned, original, used, claims_root=claims_root)
    eligible = set(inventory["allowed_generation_slot_ids"])
    excluded = set(inventory["excluded_old_scheduled_slot_ids"])
    if (set(rows) != eligible or eligible & excluded
            or any(row["input_plus_output_tokens"] != 5_000_000 for row in rows.values())):
        raise ValueError("Only unused original 5M API slots outside old scheduled ownership may enter")
    return rows


_preflight = private_function(prior.DeepSeekRuntime.read_only_preflight,
    INVENTORY_FILE=INVENTORY_FILE, select_eligible_api_rows=select_eligible_api_rows)
_identity = private_function(prior.DeepSeekRuntime.logical_resident,
    VERSION=VERSION, IDENTITY_FILE=IDENTITY_FILE)


class DeepSeekRuntime(prior.DeepSeekRuntime):
    def _require_allowed(self, *, slot_id=None, instance_id=None):
        if not callable(self._scope_guard):
            raise APIQualificationPending("The 5M expansion requires its own sealed authority")
        self._scope_guard("v069.api.request", slot_id=slot_id, instance_id=instance_id)
        return policy.require_v066_allowed("v066.api.request", slot_id=slot_id, instance_id=instance_id)

    def read_only_preflight(self):
        return _preflight(self)

    def logical_resident(self):
        return _identity(self)

    @staticmethod
    def budget_status():
        return {**prior.DeepSeekRuntime.budget_status(), "version": VERSION}
