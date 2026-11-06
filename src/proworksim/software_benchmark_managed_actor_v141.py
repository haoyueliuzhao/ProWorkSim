"""New role-baseline actor: exact roster and session-aware public test evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import time

from . import software_benchmark_managed_actor_v110 as previous
from . import software_role_baseline_contract_v141 as roles
from .software_benchmark_public_dependency_runtime_v130 import (
    validate_descriptor, effective_test_environment,
)
from .software_benchmark_public_test_evidence_v141 import (
    VERSION as RESULT_REVISION, run_public_entry as verified_run_public_entry,
)
from .software_benchmark_managed_actor_v103 import permission_refusal
from .software_benchmark_public_tests_v110 import selected_entry, contract_for_actor
from .storage import digest, json_bytes

globals().update({key: value for key, value in vars(previous).items()
                  if not key.startswith('__') and key != 'previous'})
PUBLIC_TEST_SELECTION_VERSION = 'v110-public-test-selection-r1'
ManagedTransferError = previous.ManagedTransferError
reconstruct_delta = previous.reconstruct_delta
synchronize_tree = previous.synchronize_tree
run_public_entry = verified_run_public_entry
WORLD_VERSION = 'v141-role-baseline-managed-world-r1'
PUBLIC_FILE_NAMES = {
    'public_test_library_sha256': 'public-test-library.py',
    'public_test_launcher_sha256': 'public-test.py',
    'public_test_dependency_helper_sha256': 'public-test-dependencies.py',
    'public_test_execution_sha256': 'public-test-execution.py',
    'public_test_evidence_sha256': 'public-test-evidence.py',
}


def validate_role_actor_config(config):
    spec = roles.organization(config.get('organization_id'))
    expected = {'fixed_members': spec['fixed_members'], 'member_count': spec['member_count'],
                'role_contract_version': roles.VERSION, 'role_catalog_sha256': roles.catalog_sha256(),
                'public_test_result_revision': RESULT_REVISION}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError('The actor role roster or public result implementation changed')
    if any(not isinstance(config.get(key), str) or re.fullmatch(r'[0-9a-f]{64}', config[key]) is None
           for key in (*PUBLIC_FILE_NAMES, 'public_test_contract_sha256')):
        raise ValueError('The new public runtime requires all source file bindings')
    if config.get('public_fixture_diagnostic') is not None:
        raise ValueError('No old or automatically inferred fixture diagnostic is valid in v141')
    return spec


def verify_public_runtime_files(config, root=Path('/opt/pws-runtime'),
                                contract_path=Path('/pws/control/public-test-contract.json')):
    """Called by the actual worker before ready; root injection is for CPU controls."""
    validate_role_actor_config(config)
    root = Path(root)
    observed = {}
    for key, name in PUBLIC_FILE_NAMES.items():
        path = root/name
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_mode & 0o222:
            raise ValueError('Public-test runtime files must be regular and read-only')
        if root == Path('/opt/pws-runtime') and info.st_uid != 0:
            raise ValueError('The deployed public runtime must retain its root-owned source binding')
        observed[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed[key] != config[key]:
            raise ValueError('The public-test runtime source differs from its frozen actor config')
    contract_path = Path(contract_path)
    info = contract_path.lstat()
    if contract_path.is_symlink() or not contract_path.is_file() or info.st_mode & 0o222:
        raise ValueError('The public-test contract must be a read-only regular file')
    if contract_path == Path('/pws/control/public-test-contract.json') and info.st_uid != 0:
        raise ValueError('The deployed public-test contract must retain its root owner')
    raw = contract_path.read_bytes()
    if (len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != config['public_test_contract_sha256']
            or json.loads(raw) != contract_for_actor(config)):
        raise ValueError('The actor public-test contract bytes or task binding changed')
    return observed


class ManagedOperationSession(previous.ManagedOperationSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        validate_role_actor_config(self.config)
        self.public_dependency_profile_v141 = validate_descriptor(
            self.config.get('public_test_dependencies'), instance_id=self.config['instance_id'],
            baseline_files=self.baseline['files'])
        self.public_test_environment_v141 = effective_test_environment(
            self.environment, self.public_dependency_profile_v141)

    def run_generation_diagnostic(self):
        if self.config.get('public_fixture_diagnostic') is not None:
            raise ValueError('A new explicit fixture diagnostic must be separately bound')
        return None

    def execute(self, operation, payload):
        if operation != 'managed_public_test':
            return super().execute(operation, payload)
        if not self.preflight_passed or self.terminal_locked:
            raise ManagedTransferError('Selected tests require the passed preflight and an unlocked actor')
        request = payload['request']
        expected = {'version', 'instance_id', 'actor_id', 'organization_id', 'call_index',
                    'source_reference', 'tree_sha256', 'hard_deadline_monotonic',
                    'hidden_evaluation', 'arbitrary_command',
                    'public_test_selection_revision', 'public_test_selection'}
        if (set(request) != expected or request.get('version') != WORLD_VERSION
                or request.get('actor_id') not in self.config['fixed_members']
                or request.get('organization_id') != self.config['organization_id']
                or request.get('public_test_selection_revision') != PUBLIC_TEST_SELECTION_VERSION
                or request.get('instance_id') != self.config['instance_id']
                or not isinstance(request.get('source_reference'), dict)
                or set(request['source_reference']) != {'object_id', 'version_id'}
                or request.get('hidden_evaluation') is not False or request.get('arbitrary_command') is not False
                or type(request.get('hard_deadline_monotonic')) not in (float, int)
                or not time.monotonic() < request['hard_deadline_monotonic'] <= self.config['lifecycle_deadline']
                or request.get('call_index') != self.test_calls+1 or self.test_calls >= 512):
            raise ValueError('Selected tests lost their role, source, call or lifetime identity')
        candidate = reconstruct_delta(self.baseline, payload, gitlinks=self.gitlinks)
        entry, selection = selected_entry(self.entry, request['public_test_selection'],
            files=candidate['files'], entry_metadata=candidate['entry_metadata'])
        if selection != request['public_test_selection']:
            raise ValueError('World and actor must validate the same canonical public selection')
        self.test_calls += 1
        try:
            synchronize_tree(self.root, candidate, gitlinks=self.gitlinks)
        except PermissionError as error:
            result = permission_refusal(error, request, candidate)
            result['execution'].update(public_test_selection=selection,
                public_test_selection_revision=PUBLIC_TEST_SELECTION_VERSION,
                public_test_result_revision=RESULT_REVISION, planned_argv=entry['argv'],
                actor_id=request['actor_id'], organization_id=request['organization_id'],
                managed_request_sha256=digest(json_bytes(request)))
            return result, {'operation_executed': False, 'operation_rejected_before_test': True}
        result = run_public_entry(entry, root=self.root, environment=self.public_test_environment_v141,
                                  request=request, candidate_tree_sha256=candidate['tree_sha256'])
        result['execution'].update(public_test_selection=selection,
            public_test_selection_revision=PUBLIC_TEST_SELECTION_VERSION,
            public_test_result_revision=RESULT_REVISION,
            public_dependency_profile=self.public_dependency_profile_v141,
            actor_id=request['actor_id'], organization_id=request['organization_id'],
            managed_request_sha256=digest(json_bytes(request)))
        result['groups']['public_repository_tests']['tests'][0]['test_id'] = 'model-selected-public-entrypoint'
        return result, {'operation_executed': True}
