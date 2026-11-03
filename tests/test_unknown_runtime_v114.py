"""Scripted recovery orchestration; no API, Docker, services or real ledger writes."""
from __future__ import annotations

from collections import Counter
import copy
import importlib.util
from pathlib import Path
import socket
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v114 as scope
from proworksim import software_benchmark_host_api_v114 as host
from proworksim import software_benchmark_grading_recovery_v114 as grading_module
from proworksim.software_benchmark_candidates_v054 import write_new


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name+'_cpu', scope.ROOT/'tools'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('External operations are forbidden in this CPU control')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)


def test_only_exact_old_qualification_is_reused_without_api(tmp_path, monkeypatch):
    old_schema = {'schemas': {'REF': [{'fixture': 'native'}], 'PROJECT': [{'fixture': 'managed'}]},
                  'tool_names': {'REF': ['finish'], 'PROJECT': ['run_tests']}, 'version': 'old'}
    ref = write_new(tmp_path/'old-schemas.json', old_schema)
    proof = write_new(tmp_path/'qualified.json', {'passed': True, 'thinking': False,
        'model_calls': 2, 'unknown_usage_calls': 0, 'schema_inventory': ref})
    monkeypatch.setattr(host, 'QUALIFICATION', Path(proof['path']))
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {'API_qualification': proof})
    class ForbiddenClient:
        def __getattr__(self, name):
            raise AssertionError('No reused qualification operation: '+name)
    current = {**old_schema, 'version': 'new-deployment-only'}
    assert host.qualify(ForbiddenClient(), ForbiddenClient(), current)['passed'] is True
    bad = copy.deepcopy(current)
    bad['schemas']['PROJECT'][0]['fixture'] = 'changed-schema'
    with pytest.raises(ValueError, match='byte-equivalent'):
        host.qualify(ForbiddenClient(), ForbiddenClient(), bad)
    assert host.DeepSeekRuntime.preparation_usage()['calls'] == []
    assert host.DeepSeekRuntime.preparation_usage()['new_preparation_API_calls'] == 0
    assert host.MAX_CONCURRENCY == 16


def test_four_first_generations_and_four_scores_share_two_slots(tmp_path, monkeypatch):
    manager = load_tool('run_unknown_recovery_v114')
    configuration = write_new(tmp_path/'configuration.json', {'fixture': True})
    rows = [{'slot_id': ('new-' if index < 4 else 'old-')+str(index), 'slot_index': 8000+index,
        'instance_id': ('psf__requests-1766' if index < 2 else 'psf__requests-1921' if index < 4 else 'fixture-'+str(index)),
        'arm': 'REF' if index % 2 == 0 else 'PROJECT', 'model_key': 'DEEPSEEK',
        'group_id': 'REF' if index % 2 == 0 else 'PROJECT', 'configuration': configuration,
        'generation_token_upper_bound': 5_000_000} for index in range(8)]
    specs = [{'row': item, 'kind': 'original_locked' if i < 6 else 'recovered_stopped_code',
        'result': write_new(tmp_path/f'old-result-{i}.json', {'slot_id': item['slot_id'], 'model_calls': 999}),
        'endpoint': 'code'} for i, item in enumerate(rows) if i >= 4]
    plan_value = {'rows': rows, 'generation_rows': rows[:4], 'score_recoveries': specs,
                  'environments': {item['instance_id']: {} for item in rows}}
    plan = write_new(tmp_path/'plan.json', plan_value)
    auth = write_new(tmp_path/'authorization.json', {'fixture': True})
    panel = write_new(tmp_path/'panel.json', {'fixture': True})
    proof = write_new(tmp_path/'qualification.json', {'fixture': True})
    for key, value in {'PLAN_FILE': Path(plan['path']), 'AUTH_FILE': Path(auth['path']),
        'PANEL_FILE': Path(panel['path']), 'BATCH_ROOT': tmp_path, 'API_ROOT': tmp_path/'owner'}.items():
        monkeypatch.setattr(scope, key, value)
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {'API_qualification': proof})
    monkeypatch.setattr(scope, 'verify_host_limits', lambda: {'fixture': True})
    monkeypatch.setattr(scope, 'reserve_api_coordinator', lambda: {'fixture': True})
    released = []
    monkeypatch.setattr(scope, 'release_api_coordinator', released.append)
    monkeypatch.setattr(scope, 'host_cpu_pool', lambda: list(range(176)))
    monkeypatch.setattr(scope, 'dispatch_view', lambda *_a: SimpleNamespace(ResourceBusy=scope.ResourceBusy,
        physical_capacity=lambda: {'passed': True, 'disk_free_bytes': 2**50, 'memory_available_bytes': 2**50}))
    monkeypatch.setattr(manager.os, 'getloadavg', lambda: (0, 0, 0))
    monkeypatch.setattr(manager, 'prepare_schemas', lambda: proof)
    monkeypatch.setattr(manager, 'qualify', lambda *_a: {'passed': True})
    lock, old_started, all_models_started = threading.Lock(), threading.Event(), threading.Event()
    entered, model_calls, score_calls = set(), Counter(), Counter()
    active = {'all': 0, 'tls': 0, 'max': 0, 'tls_max': 0, 'controls_finished': 0, 'generation_while_old_score': False}
    done = set()
    def request(slot, task, endpoint, *, control=False):
        folder = tmp_path/'score-requests'/(slot+'-'+endpoint)
        folder.mkdir(parents=True, exist_ok=True)
        return write_new(folder/'request.json', {'slot_id': slot, 'instance_id': task, 'endpoint': endpoint,
            'control': control, 'directory': str(folder), 'resource_key': slot+'-'+endpoint})
    controls = [request('control-'+str(i), 'psf__requests-1766' if i < 2 else
        'psf__requests-1921' if i < 4 else 'fixture-control', 'control', control=True) for i in range(8)]
    class Grading:
        def prepare_environment_qualifications(self):
            return {'controls': controls, 'qualifications': {task: {'status': 'qualified'} for task in plan_value['environments']}}
        def prepare_score_recovery(self, spec):
            return request(spec['row']['slot_id'], spec['row']['instance_id'],
                           'recovered_stopped_code' if spec['kind'] == 'recovered_stopped_code' else 'code')
        def prepare_score(self, result, *, endpoint='code'):
            value = scope.load(result)
            item = next(item for item in rows if item['slot_id'] == value['slot_id'])
            return request(item['slot_id'], item['instance_id'], endpoint)
        def run_request(self, ref, stop_event):
            value = scope.load(ref)
            key = value['resource_key']
            write_new(Path(value['directory'])/'started.json', {'fixture': True})
            tls = value['instance_id'] in manager.TLS_TASKS
            with lock:
                active['all'] += 1
                active['tls'] += tls
                active['max'] = max(active['max'], active['all'])
                active['tls_max'] = max(active['tls_max'], active['tls'])
                score_calls[key] += 1
            if value['slot_id'] in {'old-4', 'old-5'}:
                old_started.set()
                assert all_models_started.wait(5), 'Slow preserved scoring must not block generation'
            time.sleep(.3 if value['slot_id'] == 'old-7' else .01)
            assert not stop_event.is_set(), 'Closing generation must not cancel an independent preserved score'
            completion = {'status': 'process_exited', 'returncode': 0, 'request': ref}
            write_new(Path(value['directory'])/'completion.json', completion)
            with lock:
                done.add(key)
                active['all'] -= 1
                active['tls'] -= tls
                active['controls_finished'] += value['control']
            if value['slot_id'] == 'old-4':
                raise ValueError('scripted local scoring exception after trustworthy cleanup')
            return completion
        def trustworthy_cleanup(self, ref):
            return scope.load(ref)['resource_key'] in done
        def delivery_disposition(self, *_args):
            return {'status': 'no_legal_delivery', 'resolved': False, 'scoring_request': None}
    grading = Grading()
    monkeypatch.setattr(grading_module, 'factory', lambda **_: grading)
    class API:
        def initialize_for_run(self):
            assert active['controls_finished'] == 8
        def logical_resident(self):
            return {'fixture': True}
        def budget_status(self):
            return {'state': 'ready', 'can_start_generation': True}
        def transport_factory(self, *_args):
            raise AssertionError('No model or network transport in this test')
        def cancel_all(self):
            pass
        def preparation_usage(self):
            return {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': True}
        def usage_for_slot(self, item):
            assert item in rows[:4], 'Score-only generations must never enter new token statistics'
            return {'calls': [{'call_id': item['slot_id']+':'+purpose, 'purpose': purpose,
                'prompt_tokens': 8, 'completion_tokens': 2, 'reasoning_tokens': 0,
                'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 8, 'accounted_cost_cny': '0'}
                for purpose in ('agent', 'condenser')] if item['slot_id'] in entered else [],
                'unresolved_calls': [], 'usage_capture_complete': True}
    api = API()
    monkeypatch.setattr(manager, 'DeepSeekRuntime', lambda: api)
    def generate(item, resident, **_kwargs):
        assert item in rows[:4] and resident == {'fixture': True}
        assert old_started.wait(5)
        with lock:
            assert active['controls_finished'] == 8
            active['generation_while_old_score'] |= active['all'] > 0
            entered.add(item['slot_id'])
            model_calls[item['slot_id']] += 1
            if len(entered) == 4:
                all_models_started.set()
        return write_new(tmp_path/(item['slot_id']+'-result.json'), {'slot_id': item['slot_id'],
            'configuration': configuration, 'status': 'closed', 'model_calls': 2,
            'ledger': {'known_actual_tokens': 20, 'complete_actual_tokens': 20,
                       'inflight': None, 'uncertain_reserved_tokens': 0},
            'quiescence': {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False}})
    monkeypatch.setattr(manager, 'build_episode', lambda: SimpleNamespace(run_episode=generate))
    result = manager.run()
    assert result['failure'] is None and len(released) == 1
    assert len(result['new_generation']['generation']) == len(result['recovered_scores']) == 4
    assert set(model_calls) == {item['slot_id'] for item in rows[:4]} and set(model_calls.values()) == {1}
    assert result['recovered_scores']['old-4']['status'] == 'technical_unknown'
    assert result['recovered_scores']['old-6']['endpoint'] == 'recovered_stopped_code'
    assert active['max'] == 2 and active['tls_max'] == 1 and active['generation_while_old_score']
    assert len(score_calls) == 16 and set(score_calls.values()) == {1}
    assert result['original_generation_count_imported'] == result['additional_neutral_calls'] == result['additional_diagnostics'] == 0
    reporting = load_tool('summarize_unknown_recovery_v114')
    monkeypatch.setattr(reporting.DeepSeekRuntime, 'usage_for_slot', staticmethod(api.usage_for_slot))
    monkeypatch.setattr(reporting, 'budget_status', api.budget_status)
    report = reporting.run(output=tmp_path/'report.json')
    assert len(report['first_generations']) == 4 and len(report['preserved_candidate_scores']) == 4
    assert sum(item['known_actual_tokens'] for item in report['first_generations']) == 80
    assert all(item['mean_actual_tokens_all_first_generations'] == 20 for item in report['generation_groups'].values())


def test_recovery_launcher_keeps_same_unit_and_shared_cash_policy(monkeypatch):
    monkeypatch.setattr(scope, 'host_cpu_pool', lambda: list(range(176)))
    launcher = load_tool('launch_unknown_recovery_v114')
    spec = {**launcher.specification(), 'ownership_token': 'a'*32}
    command = launcher.command(spec)
    assert '--unit=proworksim-v111-aligned.service' in command
    assert command[-2:] == [str(scope.ROOT/'tools/run_unknown_recovery_v114.py'), '--execute']
    assert scope.MAX_GENERATIONS == 4 and scope.MAX_GRADERS == 2 and host.MAX_CONCURRENCY == 16
    assert scope.CONSTRAINTS['maximum_combined_reserved_cpu'] == 40
    assert scope.CONSTRAINTS['maximum_combined_reserved_memory_bytes'] == 192*1024**3
    assert scope.CASH_CAP_CNY == '350.00'


def test_actual_host_initialization_binds_only_four_generation_rows(tmp_path, monkeypatch):
    schema = {'schemas': {'REF': [], 'PROJECT': []}, 'tool_names': {'REF': [], 'PROJECT': []}}
    schema_ref = write_new(tmp_path/'schemas.json', schema)
    qualification = write_new(tmp_path/'qualification.json', {'passed': True})
    tokenizer = write_new(tmp_path/'tokenizer.json', {'fixture': True})
    first = [{'slot_id': 'first-'+str(index)} for index in range(4)]
    previous = [{'slot_id': 'previous-'+str(index)} for index in range(4)]
    plan = write_new(tmp_path/'plan.json', {'rows': first+previous, 'generation_rows': first})
    monkeypatch.setattr(scope, 'PLAN_FILE', Path(plan['path']))
    monkeypatch.setattr(scope, 'LEDGER_FILE', tmp_path/'never-opened.sqlite')
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {})
    monkeypatch.setattr(host, 'SCHEMAS', Path(schema_ref['path']))
    monkeypatch.setattr(host, 'QUALIFICATION', Path(qualification['path']))
    monkeypatch.setattr(host, 'TOKENIZER', Path(tokenizer['path']))
    monkeypatch.setattr(host, 'IDENTITY', tmp_path/'identity.json')
    monkeypatch.setattr(host, 'prepare_schemas', lambda: schema_ref)
    order = []
    def reuse(client, counter, value):
        assert client is counter is None and value == schema
        order.append('qualification_reused_without_api')
        return {'passed': True}
    monkeypatch.setattr(host, 'qualify', reuse)
    def client(**kwargs):
        assert kwargs['ledger_path'] == scope.LEDGER_FILE and kwargs['max_concurrency'] == 16
        order.append('scripted_client_constructed')
        return object()
    monkeypatch.setattr(host.api, 'DeepSeekClient', client)
    monkeypatch.setattr(host.api, 'load_api_key', lambda _: 'synthetic-never-sent')
    monkeypatch.setattr(host, 'OfficialDeepSeekCounter', lambda *_a, **_k: object())
    runtime = host.DeepSeekRuntime()
    runtime.initialize_for_run()
    assert set(runtime.rows) == {row['slot_id'] for row in first}
    assert order == ['qualification_reused_without_api', 'scripted_client_constructed']
    with pytest.raises(ValueError, match='Unsealed generation row'):
        runtime.transport_factory(previous[0], tmp_path)
    assert not scope.LEDGER_FILE.exists()
