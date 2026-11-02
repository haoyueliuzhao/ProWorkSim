"""Necessary CPU-only integration controls for the new owned runtime."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v105 as scope
from proworksim import software_benchmark_host_api_v105 as host
from proworksim import software_benchmark_deepseek_api_v105 as api
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_deepseek_contract_v105 import condition
from proworksim.software_benchmark_episode_v105 import build_episode


def tool(name):
    spec = importlib.util.spec_from_file_location('v105_test_'+name, scope.ROOT/'tools'/f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_prepared_panel_and_actual_episode_bindings():
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    def guard(*_args, **_kwargs):
        return {'plan': reference(scope.PLAN_FILE)}
    episode = build_episode(guard=guard)
    assert episode._run.__globals__['BATCH'] == scope.BATCH_ROOT
    assert episode._run.__globals__['runtime'].__name__.endswith('_v105')
    assert episode.policy.BATCH_ROOT == scope.BATCH_ROOT
    for arm in ('REF', 'PROJECT'):
        row = next(row for row in plan['rows'] if row['arm'] == arm)
        config, actual, limits = episode._row_and_config(row, False)
        assert actual == condition(arm)
        assert limits['input_plus_output_tokens'] == 5_000_000
        assert config['thinking'] is False
        changed = {**row, 'thinking': True}
        with pytest.raises(ValueError):
            episode._row_and_config(changed, False)
    diagnostic = plan['diagnostics'][0]
    row = next(row for row in plan['rows'] if row['slot_id'] == diagnostic['slot_id'])
    episode._row_and_config(row, True)


def test_new_cpu_and_memory_bounds_do_not_alias_old_dispatch():
    policy = scope.dispatch_view(lambda *_a, **_k: {})
    assert policy.BATCH_ROOT != scope.original.BATCH_ROOT
    assert scope.original.CONSTRAINTS != scope.CONSTRAINTS
    lanes = [set(map(int, scope.cpu_set('coordinator').split(',')))]
    lanes += [set(map(int, scope.cpu_set(role, index).split(',')))
              for index in range(8) for role in ('actor', 'controller')]
    lanes += [set(map(int, scope.cpu_set('grader', index).split(','))) for index in range(2)]
    assert sum(map(len, lanes)) == len(set().union(*lanes)) == 64
    assert scope.CONSTRAINTS['generation_pair_reserved_memory_bytes'] == 32*scope.GIB
    assert scope.CONSTRAINTS['maximum_combined_reserved_memory_bytes'] == 320*scope.GIB
    with pytest.raises(ValueError):
        scope.cpu_set('grader', 2)
    with pytest.raises(ValueError):
        scope.cpu_set('model', 0)


def test_grading_capacity_keeps_two_lanes(monkeypatch):
    monkeypatch.setattr(scope, 'dispatch_view', lambda: SimpleNamespace(physical_capacity=lambda: {
        'memory_available_bytes': 600*scope.GIB, 'disk_free_bytes': 1000*scope.GIB, 'passed': True}))
    active = [{'spec': {'role': 'score'}, 'reserved_cpu': 4,
               'reserved_memory_bytes': 16*scope.GIB} for _ in range(2)]
    with pytest.raises(scope.ResourceBusy, match='Both'):
        scope._budget(active, 4, 16*scope.GIB)
    result = scope._budget([], 6, 32*scope.GIB, 1)
    assert result['reserved_cpu_after'] == 14
    assert result['reserved_memory_bytes_after'] == 64*scope.GIB


def test_exact_new_authority_and_tls_scope(tmp_path, monkeypatch):
    plan_ref = reference(scope.PLAN_FILE)
    source = write_new(tmp_path/'sources.json', {'files': []})
    auth = write_new(tmp_path/'auth.json', {'version': scope.VERSION, 'status': 'approved',
        'plan': plan_ref, 'source_index': source, 'API_cash_cap_CNY': '350.00',
        'new_generation_attempts': 100, 'constraints': scope.CONSTRAINTS,
        'shared_host_configuration_changes': 0})
    monkeypatch.setattr(scope, 'AUTH_FILE', Path(auth['path']))
    monkeypatch.setattr(scope, 'SOURCE_FILE', Path(source['path']))
    scope.require_allowed('v066.resolve', instance_id='psf__requests-1766')
    task = next(task for task in scope.load(plan_ref)['environments'] if task not in scope.original.TLS_TASKS)
    with pytest.raises(PermissionError, match='two declared TLS'):
        scope.require_allowed('v066.transport', instance_id=task)
    with pytest.raises(PermissionError, match='Grading authority'):
        scope.require_grading_allowed('v066.actor.create')
    with pytest.raises(PermissionError):
        scope.require_allowed('v066.run', slot_id='old-attempt')
    with pytest.raises(PermissionError):
        scope.require_allowed('v066.model.start')


def test_api_ledger_is_independent_and_bounded(tmp_path, monkeypatch):
    ledger_path = tmp_path/'only-new.sqlite'
    monkeypatch.setattr(scope, 'LEDGER_FILE', ledger_path)
    ledger = api.BudgetLedger(ledger_path, max_concurrency=host.MAX_CONCURRENCY)
    assert ledger is not None
    state = host.budget_status()
    assert state['cap_CNY'] == '350.00'
    assert state['attempts'] == 0
    assert state['remaining_CNY'] == '350.0'
    assert host.usage('v105:fresh', 'new')['usage_capture_complete'] is True
    assert state['state'] == 'qualification_pending'


def test_transport_checks_frozen_row_and_actual_tail_cap(monkeypatch, tmp_path):
    row = {'slot_id': 'v105:test:REF:1', 'instance_id': 'test', 'condition_id': 'REF', 'arm': 'REF'}
    runtime = host.DeepSeekRuntime()
    runtime.rows = {row['slot_id']: row}
    runtime.schemas = {'tool_names': {'REF': ['execute']}}
    captured = {}
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_kw: None)
    monkeypatch.setattr(host, 'HostDeepSeekTransport', lambda **kwargs: captured.update(kwargs) or SimpleNamespace())
    runtime.transport_factory(row, tmp_path)
    wire = {'max_tokens': 17, 'tools': [{'type': 'function', 'function': {'name': 'execute'}}]}
    payload = {'request_id': row['slot_id']+':0001', 'slot_id': row['slot_id'],
               'condition': 'REF', 'usage_id': 'agent', 'wire': wire}
    assert captured['authorize'](payload)['token_budget'] == 5_000_000
    for changed in ({**payload, 'request_id': row['slot_id']+':0513'},
                    {**payload, 'wire': {**wire, 'max_tokens': 32769}},
                    {**payload, 'wire': {**wire, 'tools': []}}):
        with pytest.raises(ValueError):
            captured['authorize'](changed)
    with pytest.raises(ValueError):
        runtime.transport_factory({**row, 'arm': 'PROJECT'}, tmp_path)


@pytest.mark.parametrize('reasoning', [None, 1])
def test_neutral_mode_admission_rejects_actual_reasoning(tmp_path, monkeypatch, reasoning):
    for module, name in ((scope, 'AUTH_FILE'), (host, 'TOKENIZER')):
        path = tmp_path/name
        write_new(path, {})
        monkeypatch.setattr(module, name, path)
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_kw: {})
    monkeypatch.setattr(host, 'QUALIFICATION_ROOT', tmp_path/'qual')
    monkeypatch.setattr(host, 'QUALIFICATION', tmp_path/'qual/result.json')
    responses = []
    class Client:
        def metadata(self, kind):
            assert kind == 'balance'
            return {'balance_infos': [{'currency': 'CNY', 'total_balance': '350.00'}]}

        def complete(self, wire, **kwargs):
            number = len(responses)+1
            body = {'id': str(number), 'model': api.MODEL,
                'usage': {'prompt_tokens': 30, 'completion_tokens': 10, 'total_tokens': 40,
                          'prompt_cache_hit_tokens': 0,
                          'completion_tokens_details': {'reasoning_tokens': reasoning}},
                'choices': [{'finish_reason': 'tool_calls' if number == 1 else 'stop',
                    'message': {'role': 'assistant', 'content': None if number == 1 else 'pws-v105-ok'}}]}
            if number == 1:
                body['choices'][0]['message']['tool_calls'] = [{'id': 'call_1', 'type': 'function',
                    'function': {'name': 'probe_echo', 'arguments': '{"text":"pws-v105-ok"}'}}]
            responses.append(body)
            return body
    if reasoning:
        with pytest.raises(ValueError, match='reasoning channel'):
            host.qualify(Client(), lambda _wire: {'prompt_tokens': 30})
        assert len(responses) == 1
        assert json.loads(host.QUALIFICATION.read_text())['passed'] is False
    else:
        result = host.qualify(Client(), lambda _wire: {'prompt_tokens': 30})
        assert result['passed'] and result['model_calls'] == 2
        assert result['actual_known_input_output_tokens'] == 80


def test_launcher_only_builds_bounded_ordinary_user_command():
    launch = tool('launch_nonthinking_interface_v105')
    spec = {**launch.specification(), 'ownership_token': 'a'*32}
    argv = launch.command(spec)
    assert argv[:2] == ['systemd-run', '--user']
    for value in ('--property=MemoryMax=32G', '--property=MemorySwapMax=0',
                  '--property=CPUQuota=800%', '--property=Restart=no'):
        assert value in argv
    assert all('Slice=' not in value and value != 'sudo' for value in argv)
    assert argv[-2:] == [str(scope.ROOT/'tools/run_nonthinking_interface_v105.py'), '--execute']
    with pytest.raises(ValueError):
        launch.command({**spec, 'memory_max_bytes': 64*scope.GIB})


def test_async_queue_claim_guard_and_fifty_task_usage(tmp_path, monkeypatch):
    coordinator = tool('run_nonthinking_interface_v105')
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path/'api')
    monkeypatch.setattr(scope, 'BATCH_ROOT', tmp_path)
    queue = coordinator.queue_module()
    assert queue.policy.BATCH_ROOT == tmp_path
    store = queue.JobStore(tmp_path/'jobs')
    assert store is not None
    recorder = coordinator.UsageRecorder({'rows': [], 'groups': {'REF': {}}}, SimpleNamespace(
        budget_status=lambda: {'cap_CNY': '350'}, preparation_usage=lambda: {'calls': []}))
    row = {'slot_id': 'v105:test', 'slot_index': 7000, 'group_id': 'REF'}
    record = {'entered': True, 'generation_state': 'closed', 'code_result': False,
              'usage_capture_complete': True, 'calls': [{'prompt_tokens': 90, 'completion_tokens': 10}],
              'unresolved_calls': []}
    recorder.save_record(row, copy.deepcopy(record))
    recorder.flush(final=True)
    report = json.loads((tmp_path/'api/actual-usage-summary.json').read_text())
    group = report['groups']['REF']
    assert group['planned'] == 50 and group['mean_complete_called_tasks'] == 100
    assert group['mean_all_50_when_usage_complete'] is None


def test_initial_health_gate_cannot_backfill_before_both_routes_settle(tmp_path, monkeypatch):
    coordinator = tool('run_nonthinking_interface_v105')
    monkeypatch.setattr(scope, 'BATCH_ROOT', tmp_path)
    rows = [{'slot_id': arm, 'arm': arm, 'instance_id': 'first', 'slot_index': 7000+i}
            for i, arm in enumerate(('REF', 'PROJECT'))]
    settled, receipts = set(), []
    runtime = SimpleNamespace(usage_for_slot=lambda row: {'calls': [1] if row['slot_id'] in settled else []})
    gate = coordinator.InitialPairGate(rows, runtime, lambda *_args: receipts.append(_args))
    assert gate.ceiling() == 2
    settled.add('REF')
    (tmp_path/'episodes/7000').mkdir(parents=True)
    write_new(tmp_path/'episodes/7000/result.json', {'status': 'closed'})
    assert gate.ceiling() == 1
    settled.add('PROJECT')
    assert gate.ceiling() == 8 and len(receipts) == 1
    assert gate.ceiling() == 8 and len(receipts) == 1
