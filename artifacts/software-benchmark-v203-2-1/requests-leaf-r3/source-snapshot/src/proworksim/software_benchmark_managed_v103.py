"""Future PROJECT runtime: exact cursor restoration and remaining-budget cap."""
from __future__ import annotations

from functools import cache
from types import FunctionType

from . import software_benchmark_managed_v064 as original
from . import software_benchmark_managed_v096 as repaired
from .software_benchmark_budget_closure_v103 import (
    RemainingBudgetContextTransport,
    install_worker_budget,
)

globals().update({key: value for key, value in vars(original).items() if not key.startswith('__')})
REPAIR_REVISION = 'v103-managed-cursor-budget-integration-r1'


class _CursorExecutorLifecycle:
    """Keep the repaired invocation and the pinned SDK executor close contract."""
    def __init__(self, repaired_executor):
        self.repaired_executor = repaired_executor

    def __call__(self, action, conversation=None):
        return self.repaired_executor(action, conversation)

    def close(self):
        return self.repaired_executor.delegate.close()


@cache
def worker_type():
    class IntegratedManagedWorker(repaired.worker_type()):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            try:
                install_worker_budget(self)
                agent = self.conversation.agent
                with agent._tools_lock:
                    tools = dict(agent._tools)
                    for name in self._nullable_cursor_v090['tools']:
                        tool = tools[name]
                        tools[name] = tool.set_executor(_CursorExecutorLifecycle(tool.executor))
                    object.__setattr__(agent, '_tools', tools)
            except BaseException:
                self.close()
                raise
    return IntegratedManagedWorker


_namespace = {**vars(original), 'VERSION': REPAIR_REVISION,
              'ManagedContextTransport': RemainingBudgetContextTransport,
              'worker_type': worker_type}
_build = FunctionType(original.build_runtime.__code__, _namespace,
                      original.build_runtime.__name__, original.build_runtime.__defaults__,
                      original.build_runtime.__closure__)
_build.__kwdefaults__ = original.build_runtime.__kwdefaults__


def build_runtime(*args, worker_factory=None, **kwargs):
    return _build(*args, worker_factory=worker_factory or worker_type(), **kwargs)
