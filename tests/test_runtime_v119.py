"""Only v119 startup-recovery bindings; unchanged v118 queue controls are reused."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v118 as prior_scope
from proworksim import software_benchmark_host_api_v118 as prior_host
from proworksim import software_benchmark_scope_v119 as scope
from proworksim import software_benchmark_host_api_v119 as host
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def tool(name):
    spec = importlib.util.spec_from_file_location(name+'_CPU', scope.ROOT/'tools'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('No API, Docker, service or model operations in this control')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)


def test_actual_preformal_recovery_and_only_new_deployment_paths(tmp_path, monkeypatch):
    manager = tool('run_project_rerun_v119')
    launcher = tool('launch_project_rerun_v119')
    reporting = tool('summarize_project_rerun_v119')
    plan = scope.load(reference(scope.PLAN_FILE))
    assert manager.validate_startup_recovery(plan) == reference(scope.RECOVERY_FILE)
    assert scope.BATCH_ROOT == prior_scope.BATCH_ROOT
    assert scope.LEDGER_FILE == prior_scope.LEDGER_FILE
    assert scope.API_UNIT == prior_scope.API_UNIT == 'proworksim-v118-project.service'
    assert scope.API_ROOT == scope.BATCH_ROOT/'api-coordinator-v119'
    assert scope.COORDINATOR_ROOT == scope.BATCH_ROOT/'grading-coordinator-v119'
    assert scope.GRADING_ROOT == scope.BATCH_ROOT/'grading-v119'
    assert scope.MAX_GENERATIONS == host.MAX_CONCURRENCY == 16 and scope.MAX_GRADERS == 2
    assert scope.CONSTRAINTS['maximum_containers'] == 302
    assert scope.CONSTRAINTS['maximum_named_volumes'] == 51
    assert host.QUALIFICATION == prior_host.QUALIFICATION
    assert host.NEUTRAL_SLOT == prior_host.NEUTRAL_SLOT
    assert host.NEUTRAL_CONDITION == prior_host.NEUTRAL_CONDITION
    assert host.bundle.__name__.endswith('software_benchmark_sdk_bundle_v119')
    assert manager.DeepSeekRuntime is host.DeepSeekRuntime
    from proworksim import software_benchmark_episode_v119 as episode
    assert manager.build_episode is episode.build_episode
    assert manager.build_episode.__globals__['bundle'] is host.bundle
    assert manager.build_episode.__globals__['validate_actor_ready'] is episode.validate_actor_ready
    queue = manager.queue_module()
    assert queue.execute_queue.__globals__['executors'] is manager.queue_base.executors
    assert queue.execute_queue.__globals__['policy'].AUTHORIZATION_FILE == scope.AUTH_FILE
    gate = manager.ArmHealthRamp(plan['rows'], SimpleNamespace(settled_route_witnesses=lambda: {
        'PROJECT': plan['rows'][0]['slot_id']}), lambda *_: None)
    assert gate.ceiling() == 16
    old = copy.deepcopy(plan)
    old['diagnostics'][0]['index'] = 1
    with pytest.raises(ValueError, match='new diagnostic'):
        manager.validate_startup_recovery(old)
    with pytest.raises(ValueError, match='diagnostic index'):
        manager.prepare_diagnostics(old, None, None)
    monkeypatch.setattr(scope, 'host_cpu_pool', lambda: list(range(176)))
    argv = launcher.command({**launcher.specification(), 'ownership_token': 'a'*32})
    assert argv[-2:] == [str(scope.ROOT/'tools/run_project_rerun_v119.py'), '--execute']
    assert '--unit='+scope.API_UNIT in argv and '--user' in argv
    # Read the revised report path only, without revisiting score/parser controls.
    fake_panel = write_new(tmp_path/'panel.json', {'rows': []})
    old_owner, new_owner = tmp_path/'api-coordinator', tmp_path/'api-coordinator-v119'
    old_owner.mkdir()
    new_owner.mkdir()
    write_new(old_owner/'progress.json', {'marker': 'old'})
    write_new(new_owner/'progress.json', {'marker': 'v119'})
    monkeypatch.setattr(reporting, 'ledger_snapshot', lambda _: ([], {}))
    monkeypatch.setattr(reporting, 'analyze', lambda _p, _c, _s, _b, coordinator:
                        ({'marker': coordinator['marker']}, []))
    assert reporting.run(Path(fake_panel['path']), tmp_path)['marker'] == 'v119'
    assert (tmp_path/'reporting-v119/summary.json').exists()


def test_passed_original_neutral_is_reused_only_with_identical_actual_schema_and_wire(tmp_path, monkeypatch):
    schemas = scope.load(reference(prior_host.SCHEMAS))
    old_schema = write_new(tmp_path/'old-schema.json', schemas)
    new_schema = write_new(tmp_path/'new-schema.json', {**schemas, 'version': host.VERSION,
        'runtime_bundle': {'fixture': 'deployment identity changed, schemas unchanged'}})
    monkeypatch.setattr(host, 'SCHEMAS', Path(new_schema['path']))
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path/'new-owner')
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {})
    qualification = tmp_path/'shared-qualification.json'
    monkeypatch.setattr(host, 'QUALIFICATION', qualification)
    wire, _name, _arguments = host.neutral_request('PROJECT', schemas)
    request = write_new(tmp_path/'original-neutral-request.json', {'wire': wire})
    original = {'passed': True, 'model_calls': 1, 'tools_executed': 0,
        'benchmark_tasks_used': 0, 'schema_inventory': old_schema,
        'calls': [{'arm': 'PROJECT', 'request': request}]}
    write_new(qualification, original)
    before = qualification.read_bytes()
    def refuse(*_):
        raise AssertionError('An already paid original neutral must not be called or counted again')
    assert host.qualify(SimpleNamespace(complete=refuse), refuse, scope.load(new_schema)) == original
    assert qualification.read_bytes() == before
    receipt = json.loads((scope.API_ROOT/'api-runtime/qualification-reuse.json').read_bytes())
    assert receipt['new_API_calls'] == 0 and receipt['original_neutral_slot'] == prior_host.NEUTRAL_SLOT
    changed = copy.deepcopy(scope.load(new_schema))
    changed['schemas']['PROJECT'][0]['function']['description'] += 'changed'
    with pytest.raises(ValueError, match='cannot be replayed'):
        host.qualify(SimpleNamespace(complete=refuse), refuse, changed)
    # A consumed ledger request lacking its final proof cannot create another request.
    monkeypatch.setattr(host, 'QUALIFICATION', tmp_path/'missing-result.json')
    monkeypatch.setattr(host, 'QUALIFICATION_ROOT', tmp_path/'not-entered-qualification')
    monkeypatch.setattr(host, 'usage', lambda *_: {'calls': [], 'unresolved_calls': [{'status': 'uncertain'}]})
    with pytest.raises(ValueError, match='already consumed'):
        host.qualify(SimpleNamespace(complete=refuse), lambda _: {'prompt_tokens': 256}, scope.load(new_schema))
    assert not host.QUALIFICATION_ROOT.exists()
    # The actually observed zero-use branch still permits exactly its original
    # single neutral identity, with scripted usage and no metadata request.
    monkeypatch.setattr(host, 'QUALIFICATION', host.QUALIFICATION_ROOT/'result.json')
    monkeypatch.setattr(host, 'usage', lambda *_: {'calls': [], 'unresolved_calls': []})
    auth = write_new(tmp_path/'fake-authorization.json', {'fixture_only': True})
    monkeypatch.setattr(scope, 'AUTH_FILE', Path(auth['path']))
    called = []
    def complete(wire, **identity):
        expected, name, arguments = host.neutral_request('PROJECT', scope.load(new_schema))
        assert wire == expected and identity['slot_id'] == prior_host.NEUTRAL_SLOT
        called.append(identity)
        return {'id': 'fixture-only', 'model': 'deepseek-flash',
            'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant',
                'tool_calls': [{'id': 'fixture-call', 'type': 'function', 'function': {
                    'name': name, 'arguments': json.dumps(arguments)}}]}}],
            'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
    value = host.qualify(SimpleNamespace(complete=complete), lambda _: {'prompt_tokens': 256}, scope.load(new_schema))
    assert value['model_calls'] == len(called) == 1
    assert value['actual_known_input_output_tokens'] == 281
    assert value['model']['free_metadata_requests'] == value['tools_executed'] == 0
