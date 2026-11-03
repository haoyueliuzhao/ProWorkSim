"""Bounded recovery controls; old failed diagnostics are neither changed nor rerun."""
from __future__ import annotations

import importlib.util
import socket
import subprocess
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v113 as scope
from proworksim import software_benchmark_grading_v113 as grading
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def manager_module():
    path = scope.ROOT/'tools/run_aligned_interface_v113.py'
    spec = importlib.util.spec_from_file_location('v113_recovery_manager_cpu', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture(autouse=True)
def deny_external_work(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError('No network, subprocess or runtime operation in this recovery control')
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)


def test_actual_immutable_failure_and_cpu_repair_are_exactly_bound(monkeypatch):
    manager = manager_module()
    plan = scope.load(reference(scope.PLAN_FILE))
    recovery = scope.load(reference(scope.PREPARATION_RECOVERY_FILE))
    before = {arm: reference(ref['path']) for arm, ref in recovery['diagnostics'].items()}
    assert manager.validate_preparation_recovery(recovery, plan) == recovery
    assert scope.load(recovery['diagnostics']['REF'])['passed'] is True
    assert scope.load(recovery['diagnostics']['PROJECT'])['passed'] is False
    assert before == {arm: reference(ref['path']) for arm, ref in recovery['diagnostics'].items()}
    for change in ({'old_PROJECT_passed': True}, {'diagnostics_repeated': 1},
                   {'formal_attempts_previously_entered': 1}, {'model_calls': 1}):
        with pytest.raises(ValueError, match='retained zero-model'):
            manager.validate_preparation_recovery({**recovery, **change}, plan)
    original = scope.load
    monkeypatch.setattr(scope, 'load', lambda ref: (
        {**original(ref), 'formal_deadlines_unchanged': False}
        if ref == recovery['new_CPU_evidence'] else original(ref)))
    with pytest.raises(ValueError, match='deadline correction'):
        manager.validate_preparation_recovery(recovery, plan)


def test_manager_accepts_recovery_without_any_diagnostic_replay(tmp_path, monkeypatch):
    manager = manager_module()
    assert manager.build_episode.__module__.endswith('software_benchmark_episode_v113')
    assert 'prepare_diagnostics' not in manager.run.__code__.co_names
    original_plan = scope.load(reference(scope.PLAN_FILE))
    rows = original_plan['rows'][:2]
    plan = write_new(tmp_path/'plan.json', {**original_plan, 'rows': rows})
    auth = write_new(tmp_path/'auth.json', {'scripted_authority': True})
    from pathlib import Path
    for key, value in {'API_ROOT': tmp_path/'manager', 'BATCH_ROOT': tmp_path,
        'AUTH_FILE': Path(auth['path']), 'PLAN_FILE': Path(plan['path'])}.items():
        monkeypatch.setattr(scope, key, value)
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {})
    monkeypatch.setattr(scope, 'verify_host_limits', lambda: {'scripted': True})
    monkeypatch.setattr(scope, 'reserve_api_coordinator', lambda: {'scripted': True})
    released, order = [], []
    monkeypatch.setattr(scope, 'release_api_coordinator', released.append)
    monkeypatch.setattr(manager, 'validate_preparation_recovery', lambda *_: order.append('validated'))
    def never_run(*_args, **_kwargs):
        raise AssertionError('No consumed diagnostic or formal task executes in this CPU binding control')
    def build(**kwargs):
        assert kwargs == {'scope': scope, 'guard': scope.require_allowed}
        order.append('new_episode_bound')
        return SimpleNamespace(_run=never_run, run_episode=never_run)
    monkeypatch.setattr(manager, 'build_episode', build)
    class ScriptedAPI:
        def initialize_for_run(self):
            order.append('scripted_api_initialized')
        def budget_status(self):
            return {'state': 'ready', 'scripted': True}
        def preparation_usage(self):
            return {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': True}
        def cancel_all(self):
            order.append('scripted_api_closed')
    monkeypatch.setattr(manager, 'DeepSeekRuntime', ScriptedAPI)
    monkeypatch.setattr(grading, 'factory', lambda **_: SimpleNamespace(
        prepare_environment_qualifications=lambda: {'controls': [],
            'qualifications': {row['instance_id']: {'status': 'qualified'} for row in rows}}))
    def queue(pending, **kwargs):
        assert pending == rows and kwargs['initial_state'] == {} and kwargs['run_episode'] is never_run
        return {'failure': None, 'generation': {}, 'scores': {}, 'deliveries': {}, 'pending_grading_jobs': []}
    monkeypatch.setattr(manager, 'queue_module', lambda: SimpleNamespace(execute_queue=queue))
    result = manager.run()
    assert order == ['validated', 'new_episode_bound', 'scripted_api_initialized', 'scripted_api_closed']
    assert len(released) == 1 and result['imported_previous_attempts'] == 0
    receipt = scope.load(result['preparation_qualification'])
    assert receipt['diagnostics_repeated'] == receipt['additional_attempts'] == 0
    assert receipt['old_REF_passed'] is True and receipt['old_PROJECT_passed'] is False
    assert receipt['formal_PROJECT_initial_preflight_still_required'] is True
