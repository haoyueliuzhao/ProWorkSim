"""Only new v115 precreation evidence and Requests-only manager wiring."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v115 as scope
from proworksim import software_benchmark_host_api_v115 as host
from proworksim import software_benchmark_grading_requests_v115 as grading_module
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def tool(name):
    spec = importlib.util.spec_from_file_location(name+'_cpu', scope.ROOT/'tools'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('No external operation in this Requests-only recovery check')
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)


def test_actual_zero_creation_recovery_preserves_remaining_eighteen_containers(monkeypatch):
    manager = tool('run_requests_recovery_v115')
    plan = scope.load(reference(scope.PLAN_FILE))
    recovery = scope.load(reference(scope.TLS_PRECREATION_RECOVERY_FILE))
    rows, scores = manager.validate_recovery_rows(plan)
    assert len(rows) == 4 and scores == []
    assert manager.validate_precreation_recovery(recovery, plan) == recovery
    with pytest.raises(ValueError, match='no completed rescores'):
        manager.validate_recovery_rows({**plan, 'score_recoveries': [{'do_not_read': 'completed-score'}]})
    with pytest.raises(ValueError, match='unchanged remaining quota'):
        manager.validate_precreation_recovery({**recovery, 'remaining_container_allowance': 19}, plan)
    original = scope.load
    bad_ref = recovery['failed_controls'][0]['quiescence']
    monkeypatch.setattr(scope, 'load', lambda ref: {**original(ref), 'owned_container_ids': ['unexpected']}
                        if ref == bad_ref else original(ref))
    with pytest.raises(ValueError, match='created or retained effects'):
        manager.validate_precreation_recovery(recovery, plan)


def test_manager_only_prepares_four_new_controls_and_four_first_generations(tmp_path, monkeypatch):
    manager = tool('run_requests_recovery_v115')
    assert manager.build_episode.__module__.endswith('software_benchmark_episode_recovery_v115')
    actual_plan = scope.load(reference(scope.PLAN_FILE))
    plan_ref = write_new(tmp_path/'plan.json', actual_plan)
    auth_ref = write_new(tmp_path/'auth.json', {'fixture': True})
    recovery_ref = write_new(tmp_path/'recovery.json', {'fixture': True})
    for key, value in {'PLAN_FILE': Path(plan_ref['path']), 'AUTH_FILE': Path(auth_ref['path']),
        'TLS_PRECREATION_RECOVERY_FILE': Path(recovery_ref['path']),
        'API_ROOT': tmp_path/'owner', 'BATCH_ROOT': tmp_path}.items():
        monkeypatch.setattr(scope, key, value)
    order, released, control_calls = [], [], []
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {'API_qualification': auth_ref})
    monkeypatch.setattr(scope, 'verify_host_limits', lambda: {'fixture': True})
    monkeypatch.setattr(scope, 'reserve_api_coordinator', lambda: order.append('lease') or {'fixture': True})
    monkeypatch.setattr(scope, 'release_api_coordinator', released.append)
    monkeypatch.setattr(manager, 'validate_precreation_recovery', lambda *_a: order.append('recovery_checked'))
    monkeypatch.setattr(manager, 'prepare_schemas', lambda: auth_ref)
    monkeypatch.setattr(manager, 'qualify', lambda *_a: {'passed': True})
    controls = []
    for task in manager.TLS_TASKS:
        for kind in ('gold', 'empty'):
            key = 'control-v115-'+task+'-'+kind
            directory = tmp_path/'controls'/key
            directory.mkdir(parents=True)
            controls.append(write_new(directory/'request.json', {
                'instance_id': task, 'resource_key': key, 'directory': str(directory)}))
    class Grading:
        def prepare_environment_qualifications(self):
            return {'controls': controls, 'qualifications': {}}
        def run_request(self, ref, stop_event):
            control_calls.append(scope.load(ref)['resource_key'])
            assert not stop_event.is_set()
            return {'status': 'fixture-no-Docker', 'request': ref}
        def qualify(self, task):
            assert task in manager.TLS_TASKS
            return {'status': 'qualified'}
        def prepare_score_recovery(self, *_a, **_k):
            raise AssertionError('Completed old candidates must not be read or rescored')
    monkeypatch.setattr(grading_module, 'factory', lambda **_: Grading())
    class API:
        def initialize_for_run(self):
            assert len(control_calls) == 4
            order.append('scripted_api_after_controls')
        def cancel_all(self):
            pass
        def preparation_usage(self):
            return {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': True}
        def budget_status(self):
            return {'state': 'ready', 'fixture': True}
    monkeypatch.setattr(manager, 'DeepSeekRuntime', API)
    def forbidden_generation(*_a, **_k):
        raise AssertionError('CPU binding checks do not call a model or actor')
    monkeypatch.setattr(manager, 'build_episode', lambda: SimpleNamespace(run_episode=forbidden_generation))
    def queue(rows, **kwargs):
        assert rows == actual_plan['generation_rows'] and len(rows) == 4
        assert kwargs['initial_state'] == {} and kwargs['run_episode'] is forbidden_generation
        assert kwargs['controls'] == []
        return {'failure': None, 'generation': {}, 'scores': {}, 'deliveries': {}}
    monkeypatch.setattr(manager, 'queue_module', lambda: SimpleNamespace(execute_queue=queue))
    result = manager.run()
    assert order == ['recovery_checked', 'lease', 'scripted_api_after_controls']
    assert len(control_calls) == len(set(control_calls)) == 4
    assert all(key.startswith('control-v115-') for key in control_calls)
    assert result['preserved_candidate_score_count'] == 0 and result['recovered_scores'] == {}
    assert result['first_generation_count'] == 4 and len(released) == 1
    assert host.MAX_CONCURRENCY == 16 and scope.CONSTRAINTS['maximum_containers'] == 18
    monkeypatch.setattr(scope, 'host_cpu_pool', lambda: list(range(176)))
    launcher = tool('launch_requests_recovery_v115')
    spec = {**launcher.specification(), 'ownership_token': 'a'*32}
    assert launcher.command(spec)[-2:] == [str(scope.ROOT/'tools/run_requests_recovery_v115.py'), '--execute']
    assert launcher.scope.API_UNIT == 'proworksim-v111-aligned.service'
