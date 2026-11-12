"""Continue unused 5M slots while retaining fully priced unknown API attempts."""
from __future__ import annotations

from types import SimpleNamespace

from . import software_benchmark_deepseek_runtime_v067 as wire
from . import software_benchmark_deepseek_runtime_v068 as common
from . import software_benchmark_deepseek_runtime_v069 as prior
from .software_benchmark_deepseek_budget_v072 import budget_status

VERSION = "v072-original-api-bounded-uncertainty-r1"
ROOT = prior.ROOT
BATCH_ROOT = ROOT / "runs/software-benchmark-v072/api-5m-bounded-uncertain-r1"
INVENTORY_FILE = BATCH_ROOT / "continuation-inventory.json"
IDENTITY_FILE = BATCH_ROOT / "api-coordinator/api-runtime/identity.json"
LEDGER, MAX_CONCURRENCY = prior.LEDGER, prior.MAX_CONCURRENCY

# Both admission locations require the same policy. Replacing the outer runtime
# alone would leave the frozen transport's authorization closure halting again.
_wire_view = SimpleNamespace(**vars(wire))
_wire_view.budget_status = budget_status
_preflight = prior.private_function(common.DeepSeekRuntime.read_only_preflight,
    INVENTORY_FILE=INVENTORY_FILE, select_eligible_api_rows=prior.select_eligible_api_rows, frozen=_wire_view)
_transport = prior.private_function(wire.DeepSeekRuntime.transport_factory, budget_status=budget_status)
_identity = prior.private_function(common.DeepSeekRuntime.logical_resident, VERSION=VERSION, IDENTITY_FILE=IDENTITY_FILE)


class DeepSeekRuntime(prior.DeepSeekRuntime):
    def _require_allowed(self, *, slot_id=None, instance_id=None):
        if not callable(self._scope_guard):
            raise prior.APIQualificationPending("Bounded uncertainty recovery requires its own sealed authority")
        return self._scope_guard("v072.api.request", slot_id=slot_id, instance_id=instance_id)

    def read_only_preflight(self):
        return _preflight(self)

    def transport_factory(self, row, output):
        return _transport(self, row, output)

    def logical_resident(self):
        return _identity(self)

    @staticmethod
    def budget_status():
        return budget_status()
