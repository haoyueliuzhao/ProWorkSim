"""Private scorer bindings and immutable environment equivalence controls."""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_grading_v105 as grading
from proworksim import software_benchmark_grading_environment_v066 as old_environment
from proworksim import software_benchmark_requests_tls_v066 as old_tls
from proworksim import software_benchmark_requests_offline_v066 as old_offline


def test_tls_offline_and_relay_use_only_new_private_authority():
    calls = []
    policy = SimpleNamespace(require_v066_allowed=lambda operation, **kwargs: calls.append((operation, kwargs)))
    original_policy = old_tls.policy
    original_guard = old_offline.require_v066_allowed
    value = grading.private_environment(policy)
    assert value is not old_environment and value.tls is not old_tls
    assert value.tls.EnvironmentContainer.start.__globals__['policy'] is policy
    assert value.offline.EnvironmentContainer.start.__globals__['require_v066_allowed'] is policy.require_v066_allowed
    value.tls.transport.relay_many.__globals__['_authorize']('psf__requests-1766')
    assert calls == [('v066.transport', {'instance_id': 'psf__requests-1766'})]
    assert old_tls.policy is original_policy and old_offline.require_v066_allowed is original_guard


def test_image_metadata_shortening_does_not_change_actual_environment_identity():
    original = {'instance_id': 'fixture__repo-1', 'scorer_request_base': {
        'image': {'image_id': 'sha256:' + 'a' * 64, 'unused_registry_metadata': {'tag': 'historical'}},
        'dataset': {'sha256': 'dataset'}, 'baseline_mapping': {'sha256': 'mapping'},
        'scorer_manifest': {'sha256': 'scorer'}, 'docker_socket': '/owned/socket', 'docker_cli': {'sha256': 'cli'}}}
    compact = copy.deepcopy(original)
    del compact['scorer_request_base']['image']['unused_registry_metadata']
    assert grading.environment_identity(original) == grading.environment_identity(compact)
    compact['scorer_request_base']['image']['image_id'] = 'sha256:' + 'b' * 64
    assert grading.environment_identity(original) != grading.environment_identity(compact)
    compact['scorer_request_base']['image']['image_id'] = 'latest'
    with pytest.raises(ValueError, match='immutable'):
        grading.environment_identity(compact)


def test_cold_environment_drops_api_overlay_without_mutating_parent(monkeypatch):
    monkeypatch.setenv('PYTHONPATH', '/pretend-api-tokenizer-overlay')
    monkeypatch.setenv('LD_PRELOAD', '/pretend-foreign-library')
    import os
    result = grading.clean_environment()
    assert 'PYTHONPATH' not in result and 'LD_PRELOAD' not in result
    assert os.environ['PYTHONPATH'] == '/pretend-api-tokenizer-overlay'
    assert grading.command(['--manifest'])[-3:] == ['-m', grading.MODULE, '--manifest']
