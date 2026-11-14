"""v105 PROJECT resources and repaired SDK path in explicit non-thinking mode."""
from __future__ import annotations

import copy
from types import FunctionType

from . import software_benchmark_managed_v064 as original
from .software_benchmark_budget_closure_v103 import RemainingBudgetContextTransport

REPAIR_REVISION = "v105-nonthinking-managed-cursor-sync-budget-r1"


class NonThinkingProjectOwner(original.ProjectOwner):
    def __init__(self, adapter, *, window_id, identity):
        if (adapter.limits.get("context_limit") != original.CONTEXT_LIMIT
                or adapter.maximum_output_tokens != original.MAX_OUTPUT_TOKENS
                or adapter.maximum_input_tokens != original.MAX_INPUT_TOKENS
                or adapter.thinking is not False or not isinstance(adapter.model, str)
                or not adapter.model or not isinstance(window_id, str) or not window_id
                or not isinstance(identity, dict) or not identity.get("policy_version")):
            raise ValueError("PROJECT requires the same explicit non-thinking REF resources")
        self.adapter, self.window_id, self.identity = adapter, window_id, copy.deepcopy(identity)
        self.recipe = {"max_length": original.CONTEXT_LIMIT,
                       "max_output_tokens": original.MAX_OUTPUT_TOKENS, "temperature": 1.0}
        self.transport = self


ProjectOwner = NonThinkingProjectOwner
def worker_type():
    # Only the actual SDK construction needs its pinned nullable-schema package.
    from .software_benchmark_managed_v103 import worker_type as repaired_worker
    return repaired_worker()

prepare_case = original.prepare_case


def worker_config(owner, case, *, public_initial_message):
    config = original.worker_config(owner, case, public_initial_message=public_initial_message)
    config.update(backend_id="key_free_nonthinking_broker_v105", thinking=False,
                  reasoning_effort=None, temperature=1.0)
    return config


_namespace = {**vars(original), "VERSION": REPAIR_REVISION,
              "ManagedContextTransport": RemainingBudgetContextTransport,
              "worker_type": worker_type, "worker_config": worker_config}
_build = FunctionType(original.build_runtime.__code__, _namespace,
                      original.build_runtime.__name__, original.build_runtime.__defaults__,
                      original.build_runtime.__closure__)
_build.__kwdefaults__ = original.build_runtime.__kwdefaults__


def build_runtime(*args, worker_factory=None, **kwargs):
    return _build(*args, worker_factory=worker_factory or worker_type(), **kwargs)
