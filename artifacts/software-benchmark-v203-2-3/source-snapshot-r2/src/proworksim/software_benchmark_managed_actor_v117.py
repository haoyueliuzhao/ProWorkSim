"""Same managed operations; only public-test subprocesses get the frozen fixture."""
from __future__ import annotations
import copy
from . import software_benchmark_managed_actor_v110 as previous
from .software_benchmark_public_dependency_runtime_v117 import (
    validate_descriptor, effective_test_environment,
)

globals().update({key: value for key, value in vars(previous).items() if not key.startswith('__')})


class ManagedOperationSession(previous.ManagedOperationSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Immutable in this PID1 session; model edits to requirements/descriptor
        # never select another package, interpreter or network capability.
        self.public_dependency_profile_v117 = validate_descriptor(
            self.config.get('public_test_dependencies'), instance_id=self.config['instance_id'],
            baseline_files=self.baseline['files'])
        self.public_test_environment_v117 = effective_test_environment(
            self.environment, self.public_dependency_profile_v117)

    def execute(self, operation, payload):
        if operation != 'managed_public_test':
            return super().execute(operation, payload)
        original = self.environment
        self.environment = copy.deepcopy(self.public_test_environment_v117)
        try:
            result, receipt = super().execute(operation, payload)
        finally:
            self.environment = original
        result['execution']['public_dependency_profile'] = copy.deepcopy(self.public_dependency_profile_v117)
        return result, receipt
