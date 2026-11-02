"""New-lifecycle callsite controls; no API, Docker or user-service operations."""
from __future__ import annotations

import importlib.util

import pytest

from proworksim import software_benchmark_scope_v105 as old
from proworksim import software_benchmark_scope_v106 as scope
from proworksim import software_benchmark_host_api_v106 as host
from proworksim import software_benchmark_episode_v106 as episode
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, scope.ROOT/'tools'/f'{name}.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def recovery_value():
    return {'version': 'v106-v105-zero-model-preparation-recovery-r1', 'diagnostics_repeated': 0,
        'old_diagnostic_2_passed': False, 'old_diagnostic_2_terminal_sync_executed': False,
        'new_PROJECT_preflight_in_own_formal_container': True,
        'diagnostic_1': reference(scope.BATCH_ROOT/'diagnostic-1/result.json'),
        'diagnostic_2': reference(scope.BATCH_ROOT/'diagnostic-2/result.json'),
        'new_closure_and_preflight_CPU_evidence': reference(scope.ROOT/
            'artifacts/software-benchmark-v106/closure-preflight-controls-r1/summary.json')}


def test_formal_pool_and_limits_unchanged_new_lifecycle_only():
    assert scope.PLAN_FILE == old.PLAN_FILE and scope.BATCH_ROOT == old.BATCH_ROOT
    assert scope.CONSTRAINTS == old.CONSTRAINTS
    assert scope.API_UNIT == old.API_UNIT
    assert scope.LEDGER_FILE == old.LEDGER_FILE
    assert scope.CLAIM_FILE != old.CLAIM_FILE and scope.LEASE_FILE != old.LEASE_FILE
    assert scope.API_ROOT != old.API_ROOT
    for function in (host.DeepSeekRuntime.initialize_for_run, host.DeepSeekRuntime.transport_factory,
                     host.DeepSeekRuntime.usage_for_slot, host.budget_status, host.ledger_read.__wrapped__):
        assert function.__globals__['scope'] is scope
    policy = scope.dispatch_view(lambda *_a, **_k: {})
    assert policy.AUTHORIZATION_FILE == scope.AUTH_FILE
    assert policy.SOURCE_INDEX_FILE == scope.SOURCE_FILE


def test_real_episode_import_provider_and_ready_use_new_bindings():
    def guard(*_a, **_k):
        return {'plan': reference(scope.PLAN_FILE)}
    impl = episode.build_episode(guard=guard)
    assert impl._run is impl.run_episode.__globals__['_run']
    assert 'software_benchmark_project_closure_v106' in impl._run.__code__.co_names
    assert 'software_benchmark_project_closure_v064' not in impl._run.__code__.co_names
    assert impl._run.__globals__['validate_actor_ready'] is episode.validate_actor_ready
    assert impl._run.__globals__['validate_preflight_receipt'] is episode.validate_preflight_receipt
    assert impl.OwnedActorPair.__init__.__globals__['policy'].AUTHORIZATION_FILE == scope.AUTH_FILE
    assert impl.runtime.__name__.endswith('_v106')


def test_preparation_recovery_keeps_old_failed_diagnostic():
    manager = load_tool('run_nonthinking_interface_v106')
    value = recovery_value()
    manager.validate_preparation_recovery(value)
    assert manager.UsageRecorder.flush.__globals__['scope'] is scope
    with pytest.raises(ValueError):
        manager.validate_preparation_recovery({**value, 'old_diagnostic_2_passed': True})
    with pytest.raises(ValueError):
        manager.validate_preparation_recovery({**value, 'diagnostics_repeated': 1})


def test_actual_ready_isolation_is_retained_with_only_new_internal_operation():
    ready = scope.load(reference(scope.BATCH_ROOT/'diagnostic-2/actor-ready.json'))
    revised = {**ready, 'managed_operations': ['sync_preflight', 'managed_public_test', 'sync_terminal'],
               'preflight_revision': episode.PREFLIGHT_VERSION}
    result = episode.validate_actor_ready(revised, arm='PROJECT',
                                         public_environment_sha256=ready['public_environment_sha256'])
    assert result['namespaces']['all_distinct'] is True
    with pytest.raises(ValueError, match='exact preflight protocol'):
        episode.validate_actor_ready(ready, arm='PROJECT',
                                     public_environment_sha256=ready['public_environment_sha256'])


def test_receipt_requires_zero_model_nonterminal_complete_baseline(tmp_path):
    proof = {'preflight_version': episode.PREFLIGHT_VERSION, 'passed': True, 'instance_id': 'task',
        'tree_sha256': 'tree', 'source_reference': {'object_id': 'v106-initial-actor-baseline', 'version_id': 'tree'},
        'exact_complete_tree': True, 'model_calls_before_preflight': 0, 'public_test_calls': 0,
        'terminal_locked': False, 'delivery_test_evidence': False, 'model_tools_added': False}
    ref = write_new(tmp_path/'proof.json', proof)
    args = ({'initial_sync_preflight': ref}, tmp_path, {'instance_id': 'task'}, {'tree': {'tree_sha256': 'tree'}},
            lambda value, _target: value)
    assert episode.validate_preflight_receipt(*args) == ref
    for number, field in enumerate(('terminal_locked', 'delivery_test_evidence', 'model_tools_added')):
        changed = write_new(tmp_path/f'bad-{number}.json', {**proof, field: True})
        with pytest.raises(ValueError):
            episode.validate_preflight_receipt({'initial_sync_preflight': changed}, *args[1:])


def test_same_owned_user_service_new_entrypoint():
    launcher = load_tool('launch_nonthinking_interface_v106')
    spec = {**launcher.specification(), 'ownership_token': 'f'*32}
    command = launcher.command(spec)
    assert '--unit='+old.API_UNIT in command
    assert command[-2:] == [str(scope.ROOT/'tools/run_nonthinking_interface_v106.py'), '--execute']
    assert launcher.SPEC.parent == scope.API_ROOT
