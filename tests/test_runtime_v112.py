"""Only the 16-pair deployment bindings; v111 queue/ledger behavior is unchanged."""
from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
from types import SimpleNamespace

from proworksim import software_benchmark_scope_v111 as previous_scope
from proworksim import software_benchmark_scope_v112 as scope
from proworksim import software_benchmark_host_api_v111 as previous_host
from proworksim import software_benchmark_host_api_v112 as host
from proworksim.software_benchmark_candidates_v054 import write_new


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name+'_cpu_binding', scope.ROOT/'tools'/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_new_sixteen_pair_bindings_and_four_path_families(tmp_path, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError('This binding control cannot use external resources')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)
    monkeypatch.setattr(scope, 'host_cpu_pool', lambda: list(range(176)))
    manager = load_tool('run_aligned_interface_v112')
    launcher = load_tool('launch_aligned_interface_v112')
    reporting = load_tool('summarize_aligned_interface_v112')

    assert scope.MAX_GENERATIONS == 16 and scope.MAX_GRADERS == 2
    assert scope.CONSTRAINTS['maximum_combined_reserved_cpu'] == 112
    assert scope.CONSTRAINTS['maximum_combined_reserved_memory_bytes'] == 576*1024**3
    assert host.MAX_CONCURRENCY == previous_host.MAX_CONCURRENCY == 16
    assert host.api is previous_host.api
    assert host.NEUTRAL_SLOT == previous_host.NEUTRAL_SLOT
    # Shared original panel/objects and old cumulative cash policy; new owner records.
    assert scope.BATCH_ROOT == previous_scope.BATCH_ROOT
    assert scope.LEDGER_FILE == previous_scope.LEDGER_FILE
    assert scope.API_UNIT == previous_scope.API_UNIT == 'proworksim-v111-aligned.service'
    assert scope.API_ROOT == scope.BATCH_ROOT/'api-coordinator-v112'
    assert scope.API_ROOT != previous_scope.API_ROOT
    assert scope.PLAN_FILE == scope.BATCH_ROOT/'execution-plan-v112.json'
    assert scope.SOURCE_FILE == scope.BATCH_ROOT/'runtime-sources-v112.json'
    assert scope.AUTH_FILE.name == 'v112-concurrency-amendment.json'
    assert host.SCHEMAS == scope.API_ROOT/'api-runtime/tool-schemas.json'
    assert host.IDENTITY == scope.API_ROOT/'api-runtime/identity.json'
    assert launcher.SPEC == scope.API_ROOT/'coordinator-unit.json'
    assert host.QUALIFICATION == previous_host.QUALIFICATION

    assert manager.scope is reporting.scope is scope
    assert manager.DeepSeekRuntime is host.DeepSeekRuntime
    assert manager.build_episode.__module__.endswith('software_benchmark_episode_v110')
    for function in (host.prepare_schemas, host.DeepSeekRuntime.initialize_for_run,
                     host.DeepSeekRuntime.transport_factory, host.DeepSeekRuntime.settled_route_witnesses):
        assert function.__globals__['scope'] is scope
    queue = manager.queue_module()
    assert queue.execute_queue.__globals__['executors'] is manager.queue_base.executors
    assert queue.execute_queue.__globals__['policy'].AUTHORIZATION_FILE == scope.AUTH_FILE
    rows = [{'slot_id': 'fixture-ref', 'arm': 'REF'}, {'slot_id': 'fixture-project', 'arm': 'PROJECT'}]
    gate = manager.ArmHealthRamp(rows, SimpleNamespace(settled_route_witnesses=lambda: {
        'REF': 'fixture-ref', 'PROJECT': 'fixture-project'}), lambda *_: None)
    assert gate.ceiling() == 16
    spec = {**launcher.specification(), 'ownership_token': 'a'*32}
    command = launcher.command(spec)
    assert '--user' in command and '--unit='+scope.API_UNIT in command
    assert command[-2:] == [str(scope.ROOT/'tools/run_aligned_interface_v112.py'), '--execute']
    assert spec['cpu_quota_percent'] == 800 and spec['memory_max_bytes'] == 32*1024**3
    assert spec['root_operations'] == spec['GPU_operations'] == 0

    # Only a tiny pure reporting adapter is exercised to bind the revised path.
    panel = write_new(tmp_path/'panel.json', {'rows': []})
    (tmp_path/'api-coordinator').mkdir()
    (tmp_path/'api-coordinator-v112').mkdir()
    write_new(tmp_path/'api-coordinator'/'progress.json', {'marker': 'old-must-not-read'})
    write_new(tmp_path/'api-coordinator-v112'/'progress.json', {'marker': 'new'})
    observed = []
    monkeypatch.setattr(reporting.previous, 'ledger_snapshot', lambda path: (observed.append(path) or [], {}))
    monkeypatch.setattr(reporting.previous, 'analyze', lambda _p, _c, _s, _b, coordinator:
                        ({'coordinator_marker': coordinator['marker']}, []))
    result = reporting.run(scope.Path(panel['path']), tmp_path)
    assert result['coordinator_marker'] == 'new'
    assert json.loads((tmp_path/'reporting-v112/summary.json').read_bytes())['coordinator_marker'] == 'new'
    assert not (tmp_path/'reporting').exists()
    assert observed == [tmp_path/'api-ledger.sqlite']
