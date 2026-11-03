"""Only installed-CA recovery evidence and new v116 runtime bindings."""
from __future__ import annotations

import ast
import importlib.util
import socket
import subprocess

import pytest

from proworksim import software_benchmark_scope_v116 as scope
from proworksim import software_benchmark_host_api_v116 as host
from proworksim import software_benchmark_host_api_v115 as prior_host
from proworksim.software_benchmark_candidates_v054 import reference


def tool(name):
    spec = importlib.util.spec_from_file_location(name+'_cpu', scope.ROOT/'tools'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('No external resource or credential operation in this binding test')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)


def test_real_created_v115_containers_need_cleanup_and_extra_specific_authority(monkeypatch):
    manager = tool('run_requests_recovery_v116')
    plan = scope.load(reference(scope.PLAN_FILE))
    recovery = scope.load(reference(scope.REQUESTS_RECOVERY_FILE))
    # A pure predicate fixture, not an on-disk grant or a call to require_allowed.
    simulated = {'status': 'approved', 'additional_object_allowance': 4,
                 'total_authorized_containers': 30, 'total_authorized_TLS_sessions': 14}
    assert manager.validate_requests_recovery(recovery, plan, simulated) == recovery
    for changed in ({}, {**simulated, 'status': 'prepared'},
                    {**simulated, 'additional_object_allowance': 0},
                    {**simulated, 'total_authorized_TLS_sessions': 10}):
        with pytest.raises(PermissionError, match='exact separate authorization'):
            manager.validate_requests_recovery(recovery, plan, changed)
    original = scope.load
    failed_claim = recovery['v115_quiescence'][0]
    monkeypatch.setattr(scope, 'load', lambda ref: {**original(ref), 'owned_container_ids': []}
                        if ref == failed_claim else original(ref))
    with pytest.raises(ValueError, match='real container creation'):
        manager.validate_requests_recovery(recovery, plan, simulated)


def test_new_scope_entrypoints_and_four_control_v116_keys(monkeypatch):
    manager = tool('run_requests_recovery_v116')
    launcher = tool('launch_requests_recovery_v116')
    reporting = tool('summarize_requests_recovery_v116')
    plan = scope.load(reference(scope.PLAN_FILE))
    rows, previous_scores = manager.validate_recovery_rows(plan)
    assert len(rows) == 4 and previous_scores == [] and len(plan['environments']) == 2
    assert manager.scope is reporting.scope is scope
    assert manager.DeepSeekRuntime is reporting.DeepSeekRuntime is host.DeepSeekRuntime
    assert manager.build_episode.__module__.endswith('software_benchmark_episode_recovery_v116')
    assert manager.grading_module.__name__.endswith('software_benchmark_grading_requests_v116')
    assert 'validate_requests_recovery' in manager.run.__code__.co_names
    assert 'validate_precreation_recovery' not in manager.run.__code__.co_names
    source = ast.parse((scope.ROOT/'tools/run_requests_recovery_v116.py').read_text())
    run = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
    expressions = [node.value for node in ast.walk(run) if isinstance(node, ast.Assign)
                   and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id == 'expected']
    assert len(expressions) == 1
    controls = eval(compile(ast.Expression(expressions[0]), '<CPU-control-keys>', 'eval'),
                    {'TLS_TASKS': manager.TLS_TASKS})
    assert controls == {f'control-v116-{task}-{kind}' for task in manager.TLS_TASKS for kind in ('gold', 'empty')}
    assert host.MAX_CONCURRENCY == prior_host.MAX_CONCURRENCY == 16 and host.api is prior_host.api
    assert host.NEUTRAL_SLOT == prior_host.NEUTRAL_SLOT
    assert host.SCHEMAS == scope.API_ROOT/'api-runtime/tool-schemas.json'
    assert scope.MAX_GENERATIONS == 4 and scope.MAX_GRADERS == 2
    assert scope.CONSTRAINTS['maximum_containers'] == 18 and scope.CASH_CAP_CNY == '350.00'
    monkeypatch.setattr(scope, 'host_cpu_pool', lambda: list(range(176)))
    specification = {**launcher.specification(), 'ownership_token': 'a'*32}
    command = launcher.command(specification)
    assert command[-2:] == [str(scope.ROOT/'tools/run_requests_recovery_v116.py'), '--execute']
    assert '--unit=proworksim-v111-aligned.service' in command
