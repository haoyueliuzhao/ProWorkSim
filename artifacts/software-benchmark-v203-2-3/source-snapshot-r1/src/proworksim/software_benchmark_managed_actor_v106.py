"""One private baseline synchronization before any managed model or test work.

The preflight is an internal controller protocol operation, never an Agent tool.
It cannot create test/delivery evidence or lock the actor's terminal version.
"""
from __future__ import annotations

from contextlib import contextmanager
import time
from types import FunctionType

from . import software_benchmark_managed_actor_v064 as transport
from . import software_benchmark_managed_actor_v103 as repaired

globals().update({key: value for key, value in vars(repaired).items() if not key.startswith('__')})
ManagedTransferError = repaired.ManagedTransferError
reconstruct_delta = repaired.reconstruct_delta
synchronize_tree = repaired.synchronize_tree
PREFLIGHT_VERSION = 'v106-initial-baseline-sync-preflight-r1'
MANAGED_OPERATIONS = frozenset(('sync_preflight', 'managed_public_test', 'sync_terminal'))


def _private(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


# Extend only this new transport's exact operation allowlist. All size, hash,
# sequence, no-replay and deadline validation remains the original implementation.
_upload_namespace = {**vars(transport), 'MANAGED_OPERATIONS': MANAGED_OPERATIONS}
prepare_payload_upload = contextmanager(_private(transport.prepare_payload_upload.__wrapped__, _upload_namespace))


class ManagedUploadReceiver(transport.ManagedUploadReceiver):
    begin = _private(transport.ManagedUploadReceiver.begin, _upload_namespace)


def baseline_source_reference(baseline):
    return {'object_id': 'v106-initial-actor-baseline', 'version_id': baseline['tree']['tree_sha256']}


_execute_repaired = _private(repaired.ManagedOperationSession.execute, globals())


class ManagedOperationSession(repaired.ManagedOperationSession):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.preflight_attempted = self.preflight_passed = False

    def execute(self, operation, payload):
        if operation != 'sync_preflight':
            if not self.preflight_passed:
                raise ManagedTransferError('Initial baseline synchronization must pass before model work')
            return _execute_repaired(self, operation, payload)
        if self.preflight_attempted or self.test_calls or self.terminal_locked:
            raise ManagedTransferError('Baseline preflight is single-use and precedes all managed operations')
        self.preflight_attempted = True
        request = payload.get('request', {})
        if (set(request) != {'instance_id', 'source_reference', 'tree_sha256', 'hard_deadline_monotonic',
                             'hidden_evaluation', 'arbitrary_command', 'model_calls_before_preflight'}
                or request.get('instance_id') != self.config['instance_id']
                or request.get('source_reference') != baseline_source_reference(self.baseline)
                or request.get('hidden_evaluation') is not False
                or request.get('arbitrary_command') is not False
                or type(request.get('model_calls_before_preflight')) is not int
                or request['model_calls_before_preflight'] != 0
                or type(request.get('hard_deadline_monotonic')) not in (int, float)
                or not time.monotonic() < request['hard_deadline_monotonic'] <= self.config['lifecycle_deadline']):
            raise ValueError('Preflight requires the untouched original baseline before model dispatch')
        candidate = reconstruct_delta(self.baseline, payload, gitlinks=self.gitlinks)
        if (candidate['files'] != self.baseline['files']
                or candidate['entry_metadata'] != self.baseline['entry_metadata']
                or candidate['tree_sha256'] != self.baseline['tree']['tree_sha256']):
            raise ValueError('Preflight cannot synchronize a modified candidate')
        synchronized = synchronize_tree(self.root, candidate, gitlinks=self.gitlinks)
        self.preflight_passed = True
        return {**synchronized, 'preflight_version': PREFLIGHT_VERSION, 'passed': True,
                'source_reference': baseline_source_reference(self.baseline),
                'instance_id': self.config['instance_id'], 'model_calls_before_preflight': 0,
                'public_test_calls': 0, 'terminal_locked': False,
                'delivery_test_evidence': False, 'model_tools_added': False}, {'operation_executed': True}
