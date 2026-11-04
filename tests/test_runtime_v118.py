"""PROJECT-only orchestration controls; scripted I/O and temporary ledger only."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import threading
from types import SimpleNamespace

import pytest

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
from proworksim import software_benchmark_scope_v118 as scope
from proworksim import software_benchmark_host_api_v118 as host
from proworksim import software_benchmark_grading_v118 as grading_module
from proworksim.software_benchmark_alignment_contract_v117 import condition, shared_strategy
from proworksim.software_benchmark_candidates_v054 import write_new


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('Only temporary local CPU fixtures are permitted')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tool(name):
    return load(scope.ROOT/'tools'/(name+'.py'), name+'_CPU')


def row(index=0):
    config = condition('PROJECT')
    task, seed = 'fixture__v118-'+str(index), 202611040118+index
    return {'slot_id': f"v117:{task}:{config['condition_id']}:{seed}", 'slot_index': 8000+index,
        'instance_id': task, 'arm': 'PROJECT', 'execution_arm': 'PROJECT', 'seed': seed,
        'condition_id': config['condition_id'], 'group_id': config['group_id'],
        'model_key': 'DEEPSEEK', 'thinking': False, 'input_plus_output_tokens': 5_000_000,
        'generation_token_upper_bound': 5_000_000}


def sandbox_scope(tmp_path, monkeypatch, rows, diagnostics=()):
    plan = write_new(tmp_path/'plan.json', {'rows': rows,
        'environments': {value['instance_id']: {} for value in rows}, 'diagnostics': list(diagnostics)})
    panel = write_new(tmp_path/'panel.json', {'rows': rows, 'api_total_budget_cny': '350.00'})
    auth = write_new(tmp_path/'authorization.json', {'fixture_only': True})
    for name, value in {'PLAN_FILE': Path(plan['path']), 'PANEL_FILE': Path(panel['path']),
        'AUTH_FILE': Path(auth['path']), 'BATCH_ROOT': tmp_path, 'API_ROOT': tmp_path/'api-coordinator'}.items():
        monkeypatch.setattr(scope, name, value)
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {'fixture_only': True})
    monkeypatch.setattr(scope, 'validate_plan', lambda value: value)
    monkeypatch.setattr(scope, 'verify_host_limits', lambda: {'fixture_only': True})
    monkeypatch.setattr(scope, 'reserve_api_coordinator', lambda: {'fixture_only': True})
    monkeypatch.setattr(scope, 'host_cpu_pool', lambda: list(range(176)))
    monkeypatch.setattr(scope, 'dispatch_view', lambda *_: SimpleNamespace(
        ResourceBusy=scope.ResourceBusy, physical_capacity=lambda: {
            'passed': True, 'disk_free_bytes': 2**50, 'memory_available_bytes': 2**50}))
    released = []
    monkeypatch.setattr(scope, 'release_api_coordinator', released.append)
    return scope.load(plan), released


def test_project_only_actual_schemas_one_neutral_no_metadata_and_no_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(host, 'SCHEMAS', tmp_path/'schemas.json')
    schemas = scope.load(host.prepare_schemas())
    assert set(schemas['schemas']) == set(schemas['tool_names']) == {'PROJECT'}
    assert 'path_prefix' in next(item['function']['parameters']['properties'] for item in schemas['schemas']['PROJECT']
                                 if item['function']['name'] == 'list_files')
    auth = write_new(tmp_path/'auth.json', {'fixture_only': True})
    monkeypatch.setattr(scope, 'AUTH_FILE', Path(auth['path']))
    monkeypatch.setattr(scope, 'LEDGER_FILE', tmp_path/'fake-ledger.sqlite')
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {})
    monkeypatch.setattr(host, 'QUALIFICATION_ROOT', tmp_path/'qualification')
    monkeypatch.setattr(host, 'QUALIFICATION', tmp_path/'qualification/result.json')
    calls = []
    class Client:
        def metadata(self, *_):
            raise AssertionError('This deployment authorizes zero metadata requests')
        def complete(self, wire, **identity):
            expected, name, arguments = host.neutral_request('PROJECT', schemas)
            assert wire == expected and identity['slot_id'] == host.NEUTRAL_SLOT
            assert identity['request_id'].startswith('v118:neutral:project-tools:')
            calls.append(identity)
            return {'id': 'fixture-neutral', 'model': 'deepseek-flash',
                'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
                    'tool_calls': [{'id': 'fixture-call', 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(arguments)}}]}}],
                'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                    'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
    with pytest.raises(ValueError, match='before dispatch'):
        host.qualify(Client(), lambda _: {'prompt_tokens': 4096}, schemas)
    assert not calls and not host.QUALIFICATION_ROOT.exists()
    result = host.qualify(Client(), lambda _: {'prompt_tokens': 256}, schemas)
    assert result['passed'] and result['model_calls'] == 1 and len(calls) == 1
    assert result['actual_known_input_output_tokens'] == 281
    assert result['tools_executed'] == result['model']['free_metadata_requests'] == 0
    assert host.qualify(Client(), lambda _: (_ for _ in ()).throw(AssertionError('No repeated count')), schemas) == result
    with pytest.raises(ValueError, match='Only PROJECT'):
        host.neutral_request('REF', schemas)


def test_old_cash_ledger_new_project_agent_summary_and_reporting_are_separate(tmp_path, monkeypatch):
    ledger = tmp_path/'ledger.sqlite'
    host.api.BudgetLedger(ledger, max_concurrency=16)
    current = row()
    values = [(current['slot_id'], current['condition_id'], 'agent', 8, 2),
              (current['slot_id'], current['condition_id'], 'condenser', 5, 2),
              ('v110:old-project', 'old-condition', 'agent', 900, 100),
              ('v111:neutral:aligned-tools:r1', 'old-neutral', 'preparation', 900, 100),
              (host.NEUTRAL_SLOT, host.NEUTRAL_CONDITION, 'preparation', 20, 10)]
    with sqlite3.connect(ledger) as db:
        for index, (slot, group, purpose, prompt, output) in enumerate(values):
            db.execute('INSERT INTO requests (request_id,slot_id,condition,usage_id,status,request_sha256,'
                'reserved_nanoyuan,settled_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc,usage_json) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (f'fixture-{index}', slot, group, purpose, 'settled', 'a'*64, 100, 50, 100, prompt, 'fixture-time',
                 json.dumps({'prompt_tokens': prompt, 'completion_tokens': output, 'total_tokens': prompt+output})))
    monkeypatch.setattr(scope, 'LEDGER_FILE', ledger)
    before = ledger.read_bytes()
    usage = host.DeepSeekRuntime.usage_for_slot(current)
    assert sum(call['prompt_tokens']+call['completion_tokens'] for call in usage['calls']) == 17
    assert {call['purpose'] for call in usage['calls']} == {'agent', 'condenser'}
    runtime = host.DeepSeekRuntime()
    runtime.rows = {current['slot_id']: current}
    assert runtime.settled_route_witnesses() == {'PROJECT': current['slot_id']}
    with pytest.raises(ValueError):
        host.DeepSeekRuntime.usage_for_slot({**current, 'slot_id': 'v110:old-project'})
    reporting = tool('summarize_project_rerun_v118')
    panel = write_new(tmp_path/'panel.json', {'rows': [current], 'api_total_budget_cny': '350.00'})
    folder = tmp_path/'episodes'/str(current['slot_index'])
    folder.mkdir(parents=True)
    write_new(folder/'result.json', {'slot_id': current['slot_id'], 'instance_id': current['instance_id'],
        'status': 'closed', 'delivery_validation': {'submitted': False}})
    monkeypatch.setattr(reporting, 'BATCH', tmp_path)
    summary = reporting.run(Path(panel['path']), tmp_path)
    assert set(summary['groups']) == {'PROJECT'}
    group = summary['groups']['PROJECT']
    assert group['mean_actual_tokens_all_planned_tasks'] == 17
    assert group['mean_input_output_complete_called_subset'] == {'input_tokens': 13, 'output_tokens': 4, 'total_tokens': 17}
    assert summary['other_lifecycle_ledger_requests_excluded'] == 2
    assert summary['auxiliary_requests_outside_task_means'] == 1
    assert summary['paired_REF_comparison_run_in_this_batch'] is False
    assert ledger.read_bytes() == before


def test_actual_async_queue_local_error_project_live_ramp_and_new_launcher(tmp_path, monkeypatch):
    manager = tool('run_project_rerun_v118')
    fixture_module = load(scope.ROOT/'tests/test_async_queue_v082.py', 'queue_v118_fixture')
    rows = fixture_module.planned(tmp_path, count=4, arm='PROJECT')
    fixture = fixture_module.Fixture(tmp_path)
    fixture.bad_preparation = rows[0]['slot_id']
    fixture.separate_delivery = True
    fixture.prepare_environment_qualifications = lambda: {
        'qualifications': {'task': {'status': 'qualified'}}, 'controls': []}
    api = fixture_module.API()
    api.initialize_for_run = api.logical_resident
    api.preparation_usage = lambda: {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': True}
    api.settled_route_witnesses = lambda: {'PROJECT': next(iter(fixture.entered))} if fixture.entered else {}
    api.usage_for_slot = lambda item: {'calls': ([{'call_id': item['slot_id']+':0001', 'purpose': 'agent',
        'prompt_tokens': 8, 'completion_tokens': 2, 'reasoning_tokens': 0,
        'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 8, 'accounted_cost_cny': '0'}]
        if item['slot_id'] in fixture.entered else []), 'unresolved_calls': [], 'usage_capture_complete': True}
    _plan, released = sandbox_scope(tmp_path, monkeypatch, rows)
    monkeypatch.setattr(manager.os, 'getloadavg', lambda: (0, 0, 0))
    preparation = write_new(tmp_path/'preparation.json', {'passed': True, 'fixture_only': True})
    monkeypatch.setattr(manager, 'prepare_diagnostics', lambda *_args: preparation)
    monkeypatch.setattr(manager, 'build_episode', lambda **_: SimpleNamespace(run_episode=fixture.episode))
    monkeypatch.setattr(manager, 'DeepSeekRuntime', lambda: api)
    monkeypatch.setattr(grading_module, 'factory', lambda **_: fixture)
    queue = manager.queue_module()
    assert queue.execute_queue.__globals__['executors'] is manager.queue_base.executors
    gate = manager.ArmHealthRamp(rows, api, lambda *_: None)
    assert gate.ceiling() == 1
    result = manager.run()
    assert result['failure'] is None and len(result['generation']) == len(result['scores']) == 4
    assert result['scores'][rows[0]['slot_id']]['status'] == 'technical_unknown'
    assert all(fixture.calls[item['slot_id']] == 1 for item in rows)
    assert result['imported_previous_attempts'] == 0
    assert gate.ceiling() == scope.MAX_GENERATIONS == 16
    assert fixture.maximum_scores <= 2 and len(released) == 1
    launcher = tool('launch_project_rerun_v118')
    spec = {**launcher.specification(), 'ownership_token': 'a'*32}
    command = launcher.command(spec)
    assert '--unit=proworksim-v118-project.service' in command and '--user' in command
    assert command[-2:] == [str(scope.ROOT/'tools/run_project_rerun_v118.py'), '--execute']
    assert spec['memory_max_bytes'] == 32*1024**3 and spec['root_operations'] == 0


def test_single_project_diagnostic_failure_prevents_api_and_unclean_control_stops(tmp_path, monkeypatch):
    manager = tool('run_project_rerun_v118')
    current = row()
    plan, released = sandbox_scope(tmp_path, monkeypatch, [current], diagnostics=[{'index': 1, 'slot_id': current['slot_id']}])
    quiet = write_new(tmp_path/'quiet.json', {'quiescent': True, 'all_owned_objects_removed': True,
        'cleanup_errors': [], 'create_result_unknown': False, 'retained_objects': []})
    child = write_new(tmp_path/'child.json', {'model_calls': 0, 'diagnostic_passed': False,
        'actual_SDK_initialized': True, 'execution_alignment': shared_strategy()})
    failed = write_new(tmp_path/'diagnostic.json', {'passed': False, 'model_calls': 0,
        'model_dispatch_started': False, 'quiescence': quiet, 'controller_result': child})
    requested = []
    impl = SimpleNamespace(_run=lambda row, resident, **kwargs: (requested.append((row, resident, kwargs)) or failed))
    monkeypatch.setattr(manager, 'build_episode', lambda **_: impl)
    initialized = []
    monkeypatch.setattr(manager, 'DeepSeekRuntime', lambda: initialized.append(True))
    with pytest.raises(ValueError, match='zero-model'):
        manager.run()
    assert len(requested) == 1 and requested[0][0] == current
    assert requested[0][2]['diagnostic'] is True and requested[0][1] is None
    assert initialized == [] and len(released) == 1
    folder = tmp_path/'control'
    folder.mkdir()
    request = write_new(folder/'request.json', {'resource_key': 'fixture', 'directory': str(folder),
        'instance_id': 'psf__requests-1766'})
    write_new(folder/'started.json', {'fixture': True})
    fault, stop = [], threading.Event()
    def flag(reason, ref):
        fault.append((reason, ref))
        stop.set()
    wrapper = manager.SharedScoring(SimpleNamespace(run_request=lambda *_a, **_k: {'status': 'exited'},
        trustworthy_cleanup=lambda _: False), fault=flag)
    with pytest.raises(RuntimeError, match='trusted cleanup'):
        wrapper.run_request(request, stop)
    assert stop.is_set() and fault == [('unproven_scoring_cleanup', request)]
    stop.clear()
    wrapper.delegate.trustworthy_cleanup = lambda _: (_ for _ in ()).throw(ValueError('Unreadable cleanup receipt'))
    with pytest.raises(RuntimeError, match='trusted cleanup'):
        wrapper.run_request(request, stop)
    assert stop.is_set() and len(fault) == 2


def test_public_fixture_failure_blocks_only_2931_after_successful_core_diagnostic(tmp_path, monkeypatch):
    manager = tool('run_project_rerun_v118')
    current = row()
    current['instance_id'] = 'psf__requests-2931'
    # The fake episode is identity-bound by this small CPU fixture, not a real grant.
    plan, _ = sandbox_scope(tmp_path, monkeypatch, [current],
        diagnostics=[{'index': 1, 'slot_id': current['slot_id']}])
    scope.API_ROOT.mkdir()
    quiet = write_new(tmp_path/'quiet.json', {'quiescent': True, 'all_owned_objects_removed': True,
        'cleanup_errors': [], 'create_result_unknown': False, 'retained_objects': []})
    public = {'version': 'v118-private-localhost-public-fixture-diagnostic-r1',
        'instance_id': 'psf__requests-2931', 'passed': False, 'status': 'environment_unknown',
        'profile_manifest_sha256': 'a'*64, 'failure_kind': 'fixture_scripted_failure',
        'model_calls': 0, 'hidden_material_used': False}
    child = write_new(tmp_path/'child.json', {'model_calls': 0, 'diagnostic_passed': True,
        'actual_SDK_initialized': True, 'execution_alignment': shared_strategy(),
        'public_fixture_qualification': public})
    result = write_new(tmp_path/'diagnostic.json', {'passed': True, 'model_calls': 0,
        'model_dispatch_started': False, 'quiescence': quiet, 'controller_result': child})
    prepared = manager.prepare_diagnostics(plan, SimpleNamespace(_run=lambda *_a, **_k: result), threading.Event())
    assert scope.load(prepared)['passed'] is True
    values = {task: {'status': 'qualified'} for task in ('psf__requests-2931', 'other-task')}
    manager.apply_public_fixture_qualifications(values, prepared)
    assert values['psf__requests-2931']['status'] == 'not_qualified'
    assert values['psf__requests-2931']['public_fixture_diagnostic']['qualification'] == public
    assert values['psf__requests-2931']['official_qualification'] == {'status': 'qualified'}
    assert values['other-task'] == {'status': 'qualified'}
