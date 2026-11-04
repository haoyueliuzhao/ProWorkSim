"""Read-only payload admission and test-only environment scope; no test process."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_managed_actor_v117 as actor
from proworksim import software_benchmark_public_dependency_runtime_v117 as dependencies
from proworksim import software_benchmark_runtime_inputs_v117 as inputs
from proworksim.software_benchmark_candidates_v054 import checked

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT/'artifacts/software-benchmark-v117/public-dependencies-r1'


def original_baseline():
    manifest = json.loads((PAYLOAD/'manifest.json').read_bytes())
    source_path = checked(manifest['original_source_manifest'])
    source = json.loads(source_path.read_bytes())
    tree_ref = dict(source['tasks'][0]['initial_tree'])
    tree_ref['path'] = str(source_path.parent/tree_ref['path'])
    return manifest, json.loads(checked(tree_ref).read_bytes())


def test_public_payload_binds_original_baseline_and_actual_ready_receipt():
    manifest, baseline = original_baseline()
    task = manifest['instance_id']
    descriptor = inputs.public_dependency_descriptor(task)
    profile = dependencies.validate_descriptor(descriptor, instance_id=task,
        baseline_files=baseline['files'], root=PAYLOAD)
    expected = {'instance_id': task, 'public_test_dependencies': descriptor,
                'public_test_contract_sha256': 'a'*64}
    ready = {'public_test_selection_revision': 'v110-public-test-selection-r1',
        'public_test_contract_sha256': 'a'*64, 'public_dependency_admission_checked': True,
        'public_dependency_profile': profile}
    inputs.validate_actor_selection(ready, expected)
    with pytest.raises(ValueError, match='same public dependency'):
        inputs.validate_actor_selection({**ready, 'public_dependency_profile':
            {**profile, 'manifest_sha256': 'b'*64}}, expected)
    changed = {**baseline['files'], 'requirements.txt': baseline['files']['requirements.txt']+'\n'}
    with pytest.raises(ValueError, match='original public baseline'):
        dependencies.validate_descriptor(descriptor, instance_id=task, baseline_files=changed, root=PAYLOAD)


def test_only_public_test_receives_overlay_and_original_environment_restores_on_error(monkeypatch):
    manifest, baseline = original_baseline()
    descriptor = inputs.public_dependency_descriptor(manifest['instance_id'])
    validate = dependencies.validate_descriptor
    monkeypatch.setattr(actor, 'validate_descriptor',
        lambda value, **kwargs: validate(value, root=PAYLOAD, **kwargs))
    environment = {'PATH': '/original/bin:/usr/bin', 'CONDA_PREFIX': '/original'}
    session = actor.ManagedOperationSession(config={'instance_id': manifest['instance_id'],
        'public_test_dependencies': descriptor}, baseline=baseline, entry={}, environment=environment)
    observed = []

    def parent_execute(self, operation, payload):
        observed.append((operation, copy.deepcopy(self.environment)))
        if payload.get('raise'):
            raise RuntimeError('scripted public runner failure')
        return {'execution': {}}, {'scripted': True}

    monkeypatch.setattr(actor.previous.ManagedOperationSession, 'execute', parent_execute)
    session.execute('sync_preflight', {})
    result, _ = session.execute('managed_public_test', {})
    assert observed[0][1] == environment
    assert observed[1][1] == dependencies.effective_test_environment(environment, session.public_dependency_profile_v117)
    assert result['execution']['public_dependency_profile'] == session.public_dependency_profile_v117
    assert session.environment is environment and 'PYTHONPATH' not in environment
    with pytest.raises(RuntimeError, match='scripted'):
        session.execute('managed_public_test', {'raise': True})
    assert session.environment is environment and 'PYTHONPATH' not in environment
