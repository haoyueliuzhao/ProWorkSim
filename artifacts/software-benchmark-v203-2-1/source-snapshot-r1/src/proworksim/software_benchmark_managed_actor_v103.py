"""Private actor operations with truthful, nonfatal pre-test permission refusal.

Only a PermissionError raised by synchronization after complete payload
validation is local. Transport, identity, tree-integrity and terminal-export
failures retain their original fatal semantics. No test is retried implicitly.
"""
from __future__ import annotations

import copy
import time

from . import software_benchmark_managed_actor_v064 as original
from .software_benchmark_managed_sync_v095 import synchronize_tree as repaired_sync

globals().update({key: value for key, value in vars(original).items() if not key.startswith('__')})
synchronize_tree = repaired_sync
ManagedTransferError = original.ManagedTransferError
reconstruct_delta = original.reconstruct_delta
run_public_entry = original.run_public_entry
SYNC_REVISION = 'v095-private-managed-atomic-tree-sync-r1'
REFUSAL_VERSION = 'v103-managed-pre-test-permission-refusal-r1'


def permission_refusal(error, request, candidate):
    """Report a requested tree, never claim that it was synchronized or tested."""
    return {
        'passed': False,
        'execution': {
            'executed': False,
            'input_tree_sha256': candidate['tree_sha256'],
            'source_reference': copy.deepcopy(request['source_reference']),
            'candidate_synchronized': False,
            'process_started': False,
            'hidden_evaluator': False,
            'model_supplied_command': False,
        },
        'groups': {'public_repository_tests': {
            'status': 'untested', 'executed': False, 'passed': False, 'tests': [],
            'output': 'Public tests did not start: the private checkout could not '
                      'synchronize this version. A later explicit request remains available.',
        }},
        'repository_collection_errors': [],
        'interface_refusal': {
            'version': REFUSAL_VERSION,
            'classification': 'pre_test_sync_permission_refusal',
            'error_type': type(error).__name__, 'error': str(error),
            'automatic_retry': False, 'rpc_continues': True,
            'delivery_test_evidence': False,
        },
    }


def valid_permission_refusal(operation, action, response):
    """Narrow controller-side acceptance; no arbitrary failed result is valid."""
    receipt, result = response.get('upload_receipt', {}), response.get('result', {})
    execution, refusal = result.get('execution', {}), result.get('interface_refusal', {})
    request = action.get('request', {})
    return (
        operation == 'managed_public_test'
        and receipt.get('operation_executed') is False
        and receipt.get('operation_rejected_before_test') is True
        and result.get('passed') is False
        and execution.get('executed') is False
        and execution.get('process_started') is False
        and execution.get('candidate_synchronized') is False
        and execution.get('input_tree_sha256') == action.get('candidate_tree_sha256')
        and execution.get('source_reference') == request.get('source_reference')
        and refusal.get('version') == REFUSAL_VERSION
        and refusal.get('classification') == 'pre_test_sync_permission_refusal'
        and refusal.get('automatic_retry') is False
        and refusal.get('delivery_test_evidence') is False
        and refusal.get('rpc_continues') is True
        and result.get('groups', {}).get('public_repository_tests', {}).get('status') == 'untested'
    )


class ManagedOperationSession:
    """One actor's numbered public-test attempts and final synchronization."""

    def __init__(self, *, config, baseline, entry, environment, gitlinks=(), root='/testbed'):
        self.config, self.baseline, self.entry = config, baseline, entry
        self.environment, self.gitlinks, self.root = environment, gitlinks, root
        self.test_calls, self.terminal_locked = 0, False

    def execute(self, operation, payload):
        if operation not in {'managed_public_test', 'sync_terminal'} or self.terminal_locked:
            raise ManagedTransferError('No operation after the terminal tree was locked')
        request = payload['request']
        if (request.get('instance_id') != self.config['instance_id']
                or not isinstance(request.get('source_reference'), dict)
                or set(request['source_reference']) != {'object_id', 'version_id'}
                or request.get('hidden_evaluation') is not False
                or request.get('arbitrary_command') is not False
                or type(request.get('hard_deadline_monotonic')) not in (int, float)
                or not time.monotonic() < request['hard_deadline_monotonic'] <= self.config['lifecycle_deadline']):
            raise ValueError('Managed operation lost task, version, deadline or public-only provenance')
        candidate = reconstruct_delta(self.baseline, payload, gitlinks=self.gitlinks)
        if operation == 'managed_public_test':
            if request.get('call_index') != self.test_calls + 1 or self.test_calls >= 512:
                raise ValueError('One numbered public test per accepted managed operation')
            # The world has consumed this attempt even if synchronization refuses.
            self.test_calls += 1
        try:
            synchronized = synchronize_tree(self.root, candidate, gitlinks=self.gitlinks)
        except PermissionError as error:
            if operation != 'managed_public_test':
                raise
            return permission_refusal(error, request, candidate), {
                'operation_executed': False, 'operation_rejected_before_test': True,
            }
        if operation == 'managed_public_test':
            result = run_public_entry(self.entry, root=self.root, environment=self.environment,
                                      request=request, candidate_tree_sha256=candidate['tree_sha256'])
        else:
            self.terminal_locked = True
            result = {**synchronized, 'source_reference': request['source_reference'],
                      'terminal_locked': True, 'model_can_resume': False}
        return result, {'operation_executed': True}
