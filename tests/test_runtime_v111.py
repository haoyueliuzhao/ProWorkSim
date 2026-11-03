"""Necessary v111 orchestration controls with scripted I/O and temporary ledgers."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')

from proworksim import software_benchmark_scope_v111 as scope
from proworksim import software_benchmark_host_api_v111 as host
from proworksim import software_benchmark_grading_v111 as grading_module
from proworksim.software_benchmark_alignment_contract_v110 import condition
from proworksim.software_benchmark_candidates_v054 import reference, write_new


@pytest.fixture(autouse=True)
def no_external_work(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError('Only scripted CPU operations and temporary files are permitted')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(arm='PROJECT', index=0):
    value = condition(arm)
    task, seed = 'fixture__v111-1', 202611030111+index
    return {'slot_id': f"v110:{task}:{value['condition_id']}:{seed}", 'seed': seed,
        'slot_index': 7200+index, 'instance_id': task, 'condition_id': value['condition_id'],
        'arm': arm, 'execution_arm': arm, 'model_key': 'DEEPSEEK', 'group_id': value['group_id'],
        'thinking': False, 'generation_token_upper_bound': 5_000_000}


def test_fresh_manager_keeps_async_scoring_and_local_exceptions(tmp_path, monkeypatch):
    manager = load_file(scope.ROOT/'tools/run_aligned_interface_v111.py', 'manager_v111_cpu')
    fixture_module = load_file(scope.ROOT/'tests/test_async_queue_v082.py', 'queue_v111_fixture')
    rows = fixture_module.planned(tmp_path, count=4)
    for index, item in enumerate(rows):
        item['arm'] = 'REF' if index % 2 == 0 else 'PROJECT'
        item['group_id'] = 'DEEPSEEK-'+item['arm']
    fixture = fixture_module.Fixture(tmp_path)
    fixture.bad_preparation = rows[0]['slot_id']
    fixture.separate_delivery = True
    fixture.prepare_environment_qualifications = lambda: {
        'qualifications': {'task': {'status': 'qualified'}}, 'controls': []}
    api = fixture_module.API()
    api.initialize_for_run = api.logical_resident
    api.preparation_usage = lambda: {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': True}
    api.settled_route_witnesses = lambda: {item['arm']: item['slot_id'] for item in rows
                                         if item['slot_id'] in fixture.entered}
    api.usage_for_slot = lambda item: {'calls': ([{'call_id': item['slot_id']+':0001', 'purpose': 'agent',
        'prompt_tokens': 8, 'completion_tokens': 2, 'reasoning_tokens': 0,
        'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 8, 'accounted_cost_cny': '0'}]
        if item['slot_id'] in fixture.entered else []), 'unresolved_calls': [], 'usage_capture_complete': True}
    plan = write_new(tmp_path/'plan.json', {'rows': rows, 'environments': {'task': {}}, 'diagnostics': []})
    panel = write_new(tmp_path/'panel.json', {'rows': rows})
    auth = write_new(tmp_path/'auth.json', {'fixture': True})
    for name, value in {'PLAN_FILE': Path(plan['path']), 'PANEL_FILE': Path(panel['path']),
            'AUTH_FILE': Path(auth['path']), 'BATCH_ROOT': tmp_path, 'API_ROOT': tmp_path/'manager'}.items():
        monkeypatch.setattr(scope, name, value)
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {'fixture': True})
    monkeypatch.setattr(scope, 'verify_host_limits', lambda: {'scripted': True})
    monkeypatch.setattr(scope, 'reserve_api_coordinator', lambda: {'scripted': True})
    monkeypatch.setattr(scope, 'host_cpu_pool', lambda: list(range(176)))
    monkeypatch.setattr(scope, 'dispatch_view', lambda *_: SimpleNamespace(
        ResourceBusy=scope.ResourceBusy, physical_capacity=lambda: {
            'passed': True, 'disk_free_bytes': 2**50, 'memory_available_bytes': 2**50}))
    monkeypatch.setattr(manager.os, 'getloadavg', lambda: (0, 0, 0))
    released = []
    monkeypatch.setattr(scope, 'release_api_coordinator', released.append)
    preparation = write_new(tmp_path/'preparation.json', {'passed': True, 'fixture': True})
    monkeypatch.setattr(manager, 'prepare_diagnostics', lambda *_args: preparation)
    monkeypatch.setattr(manager, 'build_episode', lambda **_: SimpleNamespace(run_episode=fixture.episode))
    monkeypatch.setattr(manager, 'DeepSeekRuntime', lambda: api)
    monkeypatch.setattr(grading_module, 'factory', lambda **_: fixture)
    queue = manager.queue_module()
    assert queue.execute_queue.__globals__['executors'] is manager.queue_base.executors
    assert queue.executors.__globals__['__name__'] == 'contextlib'
    result = manager.run()
    assert result['failure'] is None
    assert len(result['generation']) == len(result['scores']) == 4
    assert result['scores'][rows[0]['slot_id']]['status'] == 'technical_unknown'
    assert all(fixture.calls[item['slot_id']] == 1 for item in rows)
    assert result['imported_previous_attempts'] == 0
    assert result['preparation_qualification'] == preparation
    assert len(released) == 1 and api.cancelled
    summary = scope.load(reference(scope.API_ROOT/'actual-usage-summary.json'))
    assert all(group['mean_all_planned_when_usage_complete'] == 10 for group in summary['groups'].values())
    assert not (scope.API_ROOT/'initial-pair-api-health-reused.json').exists()


def test_diagnostic_failure_never_initializes_api(tmp_path, monkeypatch):
    manager = load_file(scope.ROOT/'tools/run_aligned_interface_v111.py', 'manager_v111_fail_cpu')
    plan = write_new(tmp_path/'plan.json', {'rows': [row()], 'environments': {}, 'diagnostics': []})
    auth = write_new(tmp_path/'auth.json', {'fixture': True})
    for name, value in {'PLAN_FILE': Path(plan['path']), 'AUTH_FILE': Path(auth['path']),
                        'BATCH_ROOT': tmp_path, 'API_ROOT': tmp_path/'manager'}.items():
        monkeypatch.setattr(scope, name, value)
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {})
    monkeypatch.setattr(scope, 'verify_host_limits', lambda: {})
    monkeypatch.setattr(scope, 'reserve_api_coordinator', lambda: {})
    releases = []
    monkeypatch.setattr(scope, 'release_api_coordinator', releases.append)
    monkeypatch.setattr(manager, 'build_episode', lambda **_: object())
    api_started = []
    monkeypatch.setattr(manager, 'DeepSeekRuntime', lambda: api_started.append(True))
    with pytest.raises(ValueError, match='Two separately authorized'):
        manager.run()
    assert api_started == [] and len(releases) == 1
    assert (scope.API_ROOT/'coordinator-failure.json').is_file()


def test_new_neutral_probes_are_bounded_and_do_not_execute_tools(tmp_path, monkeypatch):
    schemas = json.loads(host.SCHEMAS.read_bytes())
    schema_ref = write_new(tmp_path/'schemas.json', schemas)
    auth = write_new(tmp_path/'auth.json', {'fixture': True})
    monkeypatch.setattr(host, 'SCHEMAS', Path(schema_ref['path']))
    monkeypatch.setattr(host, 'QUALIFICATION_ROOT', tmp_path/'qualification')
    monkeypatch.setattr(host, 'QUALIFICATION', tmp_path/'qualification/result.json')
    monkeypatch.setattr(scope, 'AUTH_FILE', Path(auth['path']))
    monkeypatch.setattr(scope, 'LEDGER_FILE', tmp_path/'fixture.sqlite')
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {})
    calls = []
    class Client:
        def metadata(self, key):
            assert key == 'balance'
            return {'is_available': True, 'balance_infos': [{'currency': 'CNY', 'total_balance': '1'}]}
        def complete(self, wire, **identity):
            arm = 'REF' if wire['tools'][0]['function']['name'] == 'finish' else 'PROJECT'
            expected, name, arguments = host.neutral_request(arm, schemas)
            assert wire == expected
            assert identity['slot_id'] == host.NEUTRAL_SLOT and identity['condition'] == host.NEUTRAL_CONDITION
            assert identity['request_id'].startswith('v111:neutral:')
            calls.append(identity)
            return {'id': f'fixture-{len(calls)}', 'model': 'deepseek-flash',
                'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
                    'tool_calls': [{'id': f'fixture-call-{len(calls)}', 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(arguments)}}]}}],
                'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                    'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
    with pytest.raises(ValueError, match='before dispatch'):
        host.qualify(Client(), lambda _: {'prompt_tokens': 4096}, schemas)
    assert calls == [] and not host.QUALIFICATION_ROOT.exists()
    result = host.qualify(Client(), lambda _: {'prompt_tokens': 256}, schemas)
    assert result['passed'] and result['actual_known_input_output_tokens'] == 562
    assert result['tools_executed'] == result['benchmark_tasks_used'] == 0
    assert len(calls) == 2
    assert host.qualify(Client(), lambda _: (_ for _ in ()).throw(AssertionError('No repeated count')), schemas) == result
    assert len(calls) == 2


def test_shared_ledger_reads_only_new_task_and_new_neutral_usage(tmp_path, monkeypatch):
    ledger = tmp_path/'ledger.sqlite'
    host.api.BudgetLedger(ledger, max_concurrency=host.MAX_CONCURRENCY)
    current = row()
    values = [(current['slot_id'], current['condition_id'], 'agent', 8, 2),
              (current['slot_id'], current['condition_id'], 'condenser', 5, 2),
              ('v105:old-task', 'old-condition', 'agent', 900, 100),
              (host.NEUTRAL_SLOT, host.NEUTRAL_CONDITION, 'preparation', 20, 10)]
    with sqlite3.connect(ledger) as db:
        for index, (slot, group, purpose, prompt, output) in enumerate(values):
            usage = json.dumps({'prompt_tokens': prompt, 'completion_tokens': output, 'total_tokens': prompt+output})
            db.execute('INSERT INTO requests (request_id,slot_id,condition,usage_id,status,request_sha256,'
                'reserved_nanoyuan,settled_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc,usage_json) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (f'fixture-{index}', slot, group, purpose, 'settled', 'a'*64, 100, 50, 100, prompt, 'fixture-time', usage))
    monkeypatch.setattr(scope, 'LEDGER_FILE', ledger)
    before = ledger.read_bytes()
    usage = host.DeepSeekRuntime.usage_for_slot(current)
    assert sum(c['prompt_tokens']+c['completion_tokens'] for c in usage['calls']) == 17
    assert {c['purpose'] for c in usage['calls']} == {'agent', 'condenser'}
    assert sum(c['prompt_tokens']+c['completion_tokens'] for c in host.DeepSeekRuntime.preparation_usage()['calls']) == 30
    with pytest.raises(ValueError):
        host.DeepSeekRuntime.usage_for_slot({**current, 'slot_id': 'v105:old-task'})
    assert ledger.read_bytes() == before
    runtime = host.DeepSeekRuntime()
    runtime.rows = {current['slot_id']: current}
    assert runtime.settled_route_witnesses() == {'PROJECT': current['slot_id']}
    assert ledger.read_bytes() == before
    summary_tool = load_file(scope.ROOT/'tools/summarize_aligned_interface_v111.py', 'summary_v111_cpu')
    panel = write_new(tmp_path/'panel.json', {'rows': [row('REF', 1), current],
        'task_ids': [current['instance_id']], 'api_total_budget_cny': '350.00'})
    monkeypatch.setattr(summary_tool, 'BATCH', tmp_path)
    summary = summary_tool.run(Path(panel['path']), tmp_path, tmp_path/'report')
    assert summary['groups']['PROJECT']['known_token_lower_bounds']['total_tokens'] == 17
    assert summary['auxiliary_requests_outside_task_means'] == 1
    assert summary['other_lifecycle_ledger_requests_excluded'] == 1
    assert ledger.read_bytes() == before


def test_health_ramp_observes_first_live_response_before_episode_completion():
    manager = load_file(scope.ROOT/'tools/run_aligned_interface_v111.py', 'ramp_v111_cpu')
    rows = [row('REF'), row('PROJECT', 1)]
    observed, receipts = {}, []
    api = SimpleNamespace(settled_route_witnesses=lambda: observed)
    gate = manager.ArmHealthRamp(rows, api, lambda *value: receipts.append(value))
    assert gate.ceiling() == 2
    observed['REF'] = rows[0]['slot_id']
    assert gate.ceiling() == 2
    observed['PROJECT'] = rows[1]['slot_id']
    assert gate.ceiling() == scope.MAX_GENERATIONS == 8
    assert len(receipts) == 1
    assert gate.ceiling() == 8 and len(receipts) == 1


def test_transport_accepts_same_pool_summary_and_rejects_changed_tools(tmp_path, monkeypatch):
    runtime = host.DeepSeekRuntime()
    current = row()
    runtime.rows = {current['slot_id']: current}
    runtime.schemas = json.loads(host.SCHEMAS.read_bytes())
    runtime.client, runtime.counter = object(), object()
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {})
    monkeypatch.setattr(host, 'HostDeepSeekTransport', lambda **values: SimpleNamespace(**values))
    transport = runtime.transport_factory(current, tmp_path)
    payload = {'slot_id': current['slot_id'], 'condition': current['condition_id'],
        'request_id': current['slot_id']+':0001', 'usage_id': 'condenser',
        'wire': {'max_tokens': 32768, 'tools': []}}
    assert transport.authorize(payload)['token_budget'] == 5_000_000
    agent = {**payload, 'usage_id': 'agent', 'wire': {'max_tokens': 32768,
        'tools': copy.deepcopy(runtime.schemas['schemas']['PROJECT'])}}
    assert transport.authorize(agent)['condition_id'] == current['condition_id']
    agent['wire']['tools'][0]['function']['description'] += ' changed'
    with pytest.raises(ValueError, match='inventory changed'):
        transport.authorize(agent)


def test_launcher_uses_new_owned_user_unit_without_launching(monkeypatch):
    monkeypatch.setattr(scope, 'host_cpu_pool', lambda: list(range(176)))
    launcher = load_file(scope.ROOT/'tools/launch_aligned_interface_v111.py', 'launcher_v111_cpu')
    spec = {**launcher.specification(), 'ownership_token': 'a'*32}
    argv = launcher.command(spec)
    assert '--user' in argv and '--unit=proworksim-v111-aligned.service' in argv
    assert argv[-2:] == [str(scope.ROOT/'tools/run_aligned_interface_v111.py'), '--execute']
    assert spec['system_parent_slice'] is None and spec['GPU_operations'] == spec['root_operations'] == 0
