"""Selected public tests through the existing isolated managed actor protocol."""
from __future__ import annotations

import time

from . import software_benchmark_managed_actor_v106 as previous
from .software_benchmark_managed_actor_v103 import permission_refusal
from .software_benchmark_public_tests_v110 import selected_entry

globals().update({key: value for key, value in vars(previous).items() if not key.startswith('__')})
PUBLIC_TEST_SELECTION_VERSION = 'v110-public-test-selection-r1'
ManagedTransferError = previous.ManagedTransferError
reconstruct_delta = previous.reconstruct_delta
synchronize_tree = previous.synchronize_tree
run_public_entry = previous.run_public_entry


class ManagedOperationSession(previous.ManagedOperationSession):
    def execute(self, operation, payload):
        if operation != 'managed_public_test':
            return super().execute(operation, payload)
        if not self.preflight_passed or self.terminal_locked:
            raise ManagedTransferError('Selected tests require the passed preflight and an unlocked actor')
        request = payload['request']
        expected = {'version', 'instance_id', 'call_index', 'source_reference', 'tree_sha256',
                    'hard_deadline_monotonic', 'hidden_evaluation', 'arbitrary_command',
                    'public_test_selection_revision', 'public_test_selection'}
        if (set(request) != expected or request.get('version') != PUBLIC_TEST_SELECTION_VERSION
                or request.get('public_test_selection_revision') != PUBLIC_TEST_SELECTION_VERSION
                or request.get('instance_id') != self.config['instance_id']
                or not isinstance(request.get('source_reference'), dict)
                or set(request['source_reference']) != {'object_id', 'version_id'}
                or request.get('hidden_evaluation') is not False or request.get('arbitrary_command') is not False
                or type(request.get('hard_deadline_monotonic')) not in (float, int)
                or not time.monotonic() < request['hard_deadline_monotonic'] <= self.config['lifecycle_deadline']
                or request.get('call_index') != self.test_calls + 1 or self.test_calls >= 512):
            raise ValueError('Selected public tests lost their exact task, version, call or deadline')
        candidate = reconstruct_delta(self.baseline, payload, gitlinks=self.gitlinks)
        entry, selection = selected_entry(self.entry, request['public_test_selection'],
            files=candidate['files'], entry_metadata=candidate['entry_metadata'])
        if selection != request['public_test_selection']:
            raise ValueError('Actor requires the same canonical public selection validated by the world')
        self.test_calls += 1
        try:
            synchronize_tree(self.root, candidate, gitlinks=self.gitlinks)
        except PermissionError as error:
            result = permission_refusal(error, request, candidate)
            result['execution'].update(public_test_selection=selection,
                                      public_test_selection_revision=PUBLIC_TEST_SELECTION_VERSION,
                                      planned_argv=entry['argv'])
            return result, {'operation_executed': False, 'operation_rejected_before_test': True}
        result = run_public_entry(entry, root=self.root, environment=self.environment,
                                  request=request, candidate_tree_sha256=candidate['tree_sha256'])
        result['execution'].update(public_test_selection=selection,
                                  public_test_selection_revision=PUBLIC_TEST_SELECTION_VERSION)
        result['groups']['public_repository_tests']['tests'][0]['test_id'] = 'model-selected-public-entrypoint'
        return result, {'operation_executed': True}
