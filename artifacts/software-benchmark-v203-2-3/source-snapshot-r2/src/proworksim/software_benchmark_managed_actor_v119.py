"""Same managed operations; only public-test subprocesses get the frozen fixture."""
from __future__ import annotations
import copy
from . import software_benchmark_managed_actor_v110 as previous
from .software_benchmark_public_dependency_runtime_v118 import (
    validate_descriptor, effective_test_environment,
)

# Preserve the declared v110 parent: exporting its helper called "previous"
# would otherwise replace this binding with v106 and bypass selected tests.
globals().update({key: value for key, value in vars(previous).items()
                  if not key.startswith('__') and key != 'previous'})


class ManagedOperationSession(previous.ManagedOperationSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Immutable in this PID1 session; model edits to requirements/descriptor
        # never select another package, interpreter or network capability.
        self.public_dependency_profile_v118 = validate_descriptor(
            self.config.get('public_test_dependencies'), instance_id=self.config['instance_id'],
            baseline_files=self.baseline['files'])
        self.public_test_environment_v118 = effective_test_environment(
            self.environment, self.public_dependency_profile_v118)

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
        if getattr(self, '_public_fixture_diagnostic_started_v118', False):
            raise ValueError('The neutral public fixture diagnostic is not replayable')
        profile = self.public_dependency_profile_v118
        if (self.config['instance_id'] != 'psf__requests-2931'
                or self.config.get('maximum_lifecycle_seconds') != 600
                or not isinstance(profile, dict)
                or descriptor.get('version') != 'v119-private-localhost-public-fixture-diagnostic-r1'
                or descriptor.get('instance_id') != self.config['instance_id']
                or descriptor.get('profile_manifest_sha256') != profile['manifest_sha256']
                or descriptor.get('helper_path') != '/opt/pws-runtime/public-fixture-diagnostic.py'
                or descriptor.get('maximum_wall_seconds') != 90
                or descriptor.get('network_scope') != 'private_container_loopback_only'
                or descriptor.get('maximum_loopback_connections') != 32
                or descriptor.get('model_calls') != 0 or descriptor.get('hidden_material_used') is not False):
            raise ValueError('Only the exact fresh diagnostic actor/profile may execute this helper')
        helper = Path(descriptor['helper_path'])
        if helper.is_symlink() or hashlib.sha256(helper.read_bytes()).hexdigest() != descriptor['helper_sha256']:
            raise ValueError('The frozen diagnostic helper bytes differ')
        self._public_fixture_diagnostic_started_v118 = True
        timeout = min(90, self.config['lifecycle_deadline']-time.monotonic())
        if timeout <= 0:
            raise RuntimeError('The diagnostic actor lifetime has expired')
        result = {'version': descriptor['version'], 'instance_id': self.config['instance_id'],
                  'diagnostic_id': descriptor['diagnostic_id'], 'profile_manifest_sha256': profile['manifest_sha256'],
                  'passed': False, 'status': 'environment_unknown', 'model_calls': 0,
                  'hidden_material_used': False, 'network_scope': descriptor['network_scope']}
        try:
            child = subprocess.run([self.entry['argv'][0], '-B', str(helper), '--descriptor-json', json.dumps(descriptor)],
                cwd='/testbed', env=self.public_test_environment_v118, stdin=subprocess.DEVNULL,
                capture_output=True, timeout=timeout, check=False)
            if len(child.stdout)+len(child.stderr) > 1024**2:
                raise RuntimeError('The small fixture diagnostic exceeded its output bound')
            prefix = 'PWS_V118_PUBLIC_FIXTURE_QUALIFICATION='
            records = [line[len(prefix):] for line in child.stdout.decode('utf-8', 'replace').splitlines() if line.startswith(prefix)]
            if len(records) != 1:
                raise RuntimeError('The public fixture diagnostic did not return one result')
            observed = json.loads(records[0])
            for key in ('version', 'instance_id', 'diagnostic_id', 'profile_manifest_sha256', 'model_calls', 'hidden_material_used', 'network_scope'):
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
        original = self.environment
        self.environment = copy.deepcopy(self.public_test_environment_v118)
        try:
            result, receipt = super().execute(operation, payload)
        finally:
            self.environment = original
        result['execution']['public_dependency_profile'] = copy.deepcopy(self.public_dependency_profile_v118)
        return result, receipt
