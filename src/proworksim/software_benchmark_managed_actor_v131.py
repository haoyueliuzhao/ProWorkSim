"""v130 public execution plus one separately planned v131 zero-model diagnostic."""
from __future__ import annotations
import time
from .storage import digest, json_bytes
from .software_benchmark_alignment_contract_v131 import organization
from . import software_benchmark_managed_actor_v130 as previous

globals().update({key:value for key,value in vars(previous).items()
                  if not key.startswith('__') and key != 'previous'})
ManagedTransferError = previous.ManagedTransferError
PUBLIC_TEST_SELECTION_VERSION = previous.PUBLIC_TEST_SELECTION_VERSION
reconstruct_delta = previous.reconstruct_delta
selected_entry = previous.selected_entry
synchronize_tree = previous.synchronize_tree
permission_refusal = previous.permission_refusal
run_public_entry = previous.run_public_entry


class ManagedOperationSession(previous.ManagedOperationSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        expected = organization(self.config.get('organization_id'))['fixed_members']
        if self.config.get('fixed_members') != expected:
            raise ValueError('The team actor requires its exact frozen organization registry')

    def run_generation_diagnostic(self):
        """Only the one host-declared zero-model actor may start localhost probes."""
        import hashlib
        import json
        from pathlib import Path
        import subprocess
        import time
        descriptor = self.config.get('public_fixture_diagnostic')
        if descriptor is None:
            return None
        if getattr(self, '_public_fixture_diagnostic_started_v131', False):
            raise ValueError('The neutral public fixture diagnostic is not replayable')
        profile = self.public_dependency_profile_v130
        if (self.config['instance_id'] != 'psf__requests-2931'
                or self.config.get('maximum_lifecycle_seconds') != 600
                or not isinstance(profile, dict)
                or descriptor.get('version') != 'v131-private-localhost-public-fixture-diagnostic-r1'
                or descriptor.get('instance_id') != self.config['instance_id']
                or descriptor.get('profile_manifest_sha256') != profile['manifest_sha256']
                or descriptor.get('helper_path') != '/opt/pws-runtime/public-fixture-diagnostic.py'
                or descriptor.get('maximum_wall_seconds') != 90
                or descriptor.get('network_scope') != 'private_container_loopback_only'
                or descriptor.get('maximum_loopback_connections') != 32
                or descriptor.get('organization_id') != self.config.get('organization_id')
                or descriptor.get('fixed_members') != self.config.get('fixed_members')
                or descriptor.get('model_calls') != 0 or descriptor.get('hidden_material_used') is not False):
            raise ValueError('Only the exact fresh diagnostic actor/profile may execute this helper')
        helper = Path(descriptor['helper_path'])
        if helper.is_symlink() or hashlib.sha256(helper.read_bytes()).hexdigest() != descriptor['helper_sha256']:
            raise ValueError('The frozen diagnostic helper bytes differ')
        self._public_fixture_diagnostic_started_v131 = True
        timeout = min(90, self.config['lifecycle_deadline']-time.monotonic())
        if timeout <= 0:
            raise RuntimeError('The diagnostic actor lifetime has expired')
        result = {'version': descriptor['version'], 'instance_id': self.config['instance_id'],
                  'diagnostic_id': descriptor['diagnostic_id'], 'profile_manifest_sha256': profile['manifest_sha256'],
                  'passed': False, 'status': 'environment_unknown', 'model_calls': 0,
                  'organization_id':self.config['organization_id'], 'fixed_members':self.config['fixed_members'],
                  'hidden_material_used': False, 'network_scope': descriptor['network_scope']}
        try:
            child = subprocess.run([self.entry['argv'][0], '-B', str(helper), '--descriptor-json', json.dumps(descriptor)],
                cwd='/testbed', env=self.public_test_environment_v130, stdin=subprocess.DEVNULL,
                capture_output=True, timeout=timeout, check=False)
            if len(child.stdout)+len(child.stderr) > 1024**2:
                raise RuntimeError('The small fixture diagnostic exceeded its output bound')
            prefix = 'PWS_V131_PUBLIC_ENVIRONMENT_QUALIFICATION='
            records = [line[len(prefix):] for line in child.stdout.decode('utf-8', 'replace').splitlines() if line.startswith(prefix)]
            if len(records) != 1:
                raise RuntimeError('The public fixture diagnostic did not return one result')
            observed = json.loads(records[0])
            for key in ('version', 'instance_id', 'diagnostic_id', 'profile_manifest_sha256', 'model_calls', 'hidden_material_used', 'network_scope', 'organization_id', 'fixed_members'):
                if observed.get(key) != result[key]:
                    raise ValueError('The public fixture diagnostic result changed its scope')
            if observed.get('passed') is True and child.returncode != 0:
                raise ValueError('A failed helper cannot claim fixture qualification')
            result = {**observed, 'helper_returncode': child.returncode,
                      'stdout_sha256': hashlib.sha256(child.stdout).hexdigest(),
                      'stderr_sha256': hashlib.sha256(child.stderr).hexdigest()}
        except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError) as error:
            result.update(failure_kind='public_fixture_diagnostic_process_failure',
                          error={'type': type(error).__name__, 'message': str(error)})
        return result


    def execute(self, operation, payload):
        if operation != 'managed_public_test':
            return super().execute(operation, payload)
        if not self.preflight_passed or self.terminal_locked:
            raise ManagedTransferError('Selected tests require the passed preflight and an unlocked actor')
        request = payload['request']
        expected = {'version', 'instance_id', 'actor_id', 'organization_id', 'call_index', 'source_reference', 'tree_sha256',
                    'hard_deadline_monotonic', 'hidden_evaluation', 'arbitrary_command',
                    'public_test_selection_revision', 'public_test_selection'}
        if (set(request) != expected or request.get('version') != 'v131-fixed-organization-managed-world-r1'
                or request.get('actor_id') not in self.config['fixed_members']
                or request.get('organization_id') != self.config['organization_id']
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
                                      planned_argv=entry['argv'], actor_id=request['actor_id'],
                                      organization_id=request['organization_id'],
                                      managed_request_sha256=digest(json_bytes(request)))
            return result, {'operation_executed': False, 'operation_rejected_before_test': True}
        result = run_public_entry(entry, root=self.root, environment=self.public_test_environment_v130,
                                  request=request, candidate_tree_sha256=candidate['tree_sha256'])
        result['execution'].update(public_test_selection=selection,
                                  public_test_selection_revision=PUBLIC_TEST_SELECTION_VERSION,
                                  public_dependency_profile=self.public_dependency_profile_v130,
                                  actor_id=request['actor_id'], organization_id=request['organization_id'],
                                  managed_request_sha256=digest(json_bytes(request)))
        result['groups']['public_repository_tests']['tests'][0]['test_id'] = 'model-selected-public-entrypoint'
        return result, {'operation_executed': True}
