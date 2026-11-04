"""Fresh independent REF identities, exact neutral reuse and code-only prior closure."""
from __future__ import annotations

import importlib.util
import json
import socket
import sqlite3
import subprocess

import pytest

from proworksim import software_benchmark_scope_v126 as scope
from proworksim import software_benchmark_host_api_v126 as host
from proworksim import software_benchmark_prior_completion_v126 as gate
from proworksim import software_benchmark_deepseek_api_v105 as original_api
from proworksim.software_benchmark_alignment_contract_v110 import VERSION as ALIGNMENT_VERSION
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def tool(name):
    spec = importlib.util.spec_from_file_location(name + '_CPU', scope.ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError('No API, Docker, services, network or real model in this control')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)


def test_actual_original_ref_binding_neutral_reuse_and_predecessor_gate(tmp_path, monkeypatch):
    manager = tool('run_ref_independent_recovery_v126')
    launcher = tool('launch_ref_independent_recovery_v126')
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    assert manager.validate_independent_recovery(plan) == plan
    assert {row['slot_index'] for row in plan['rows']} == {8800, 8801}
    assert host.MAX_CONCURRENCY == 16 and scope.MAX_GENERATIONS == scope.MAX_GRADERS == 2
    assert host.api.CASH_CAP_CNY == scope.CASH_CAP_CNY == '389.7945248'
    assert host.bundle.__name__.endswith('software_benchmark_sdk_bundle_v126')
    source = write_new(tmp_path / 'fixture-source-index.json', {'CPU_fixture_only': True})
    authority = {'status': 'approved', 'execution_alignment_version': ALIGNMENT_VERSION,
                 'plan': reference(scope.PLAN_FILE), 'source_index': source}
    monkeypatch.setattr(scope, 'SOURCE_FILE', tmp_path / 'fixture-source-index.json')
    monkeypatch.setattr(scope, 'require_allowed', lambda *_args, **_kwargs: authority)
    runtime = manager.build_episode()
    assert runtime.runtime is host.bundle
    assert runtime.run_episode.__globals__['_run'] is runtime._run
    assert len(runtime.integration_points) == 7 and set(runtime.integration_points.values()) == {1}
    for row in plan['rows']:
        _config, condition, limits = runtime._row_and_config(row, False)
        assert condition['arm'] == 'REF' and limits['input_plus_output_tokens'] == 5_000_000
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path / 'api')
    scope.API_ROOT.mkdir()
    monkeypatch.setattr(host, 'SCHEMAS', scope.API_ROOT / 'api-runtime/tool-schemas.json')
    schemas = scope.load(host.prepare_schemas())
    proof = host.qualify(None, None, schemas)
    assert set(schemas['schemas']) == {'REF'}
    assert proof['original_REF_tokens'] == 530 and proof['new_API_calls'] == 0
    assert host.DeepSeekRuntime.preparation_usage()['new_preparation_API_calls'] == 0
    preparation = scope.load(manager.reuse_preparation(plan))
    assert preparation['model_calls'] == preparation['diagnostics_repeated'] == preparation['new_controls'] == 0
    prior = gate.inspect_prior_completion()
    assert prior['generation_tasks_terminal'] == 2 and prior['scoring_attempts_terminal'] == 2
    assert prior['delivery_required_for_prior_REF'] is False
    original_read = gate._read
    def pending_score(path):
        ref, value = original_read(path)
        if path == scope.PRIOR_API_ROOT / 'run-summary.json':
            value = {**value, 'pending_grading_jobs': ['CPU-pending-code']}
        return ref, value
    monkeypatch.setattr(gate, '_read', pending_score)
    with pytest.raises(gate.PriorStageIncomplete):
        gate.inspect_prior_completion()
    monkeypatch.setattr(gate, '_read', original_read)
    monkeypatch.setattr(scope, 'PRIOR_COMPLETION_FILE', tmp_path / 'unready.json')
    assert manager.require_prior_completion is launcher.require_prior_completion is gate.require_prior_completion
    with pytest.raises(gate.PriorStageIncomplete):
        launcher.launch()
    with pytest.raises(gate.PriorStageIncomplete):
        manager.run()
    spec = {**launcher.specification(), 'ownership_token': 'a' * 32}
    assert spec['unit'] == 'proworksim-v118-project.service'
    assert launcher.command(spec)[-2:] == [str(scope.ROOT / 'tools/run_ref_independent_recovery_v126.py'), '--execute']


def test_ref_two_task_token_summary_delivery_not_applicable(tmp_path):
    reporting = tool('summarize_ref_independent_recovery_v126')
    plan = scope.load(reference(scope.PLAN_FILE))
    own = plan['rows'][0]
    ledger = tmp_path / 'api-ledger.sqlite'
    original_api.BudgetLedger(ledger, max_concurrency=16)
    records = [(own['slot_id'], own['condition_id'], 'agent', 8, 2),
               ('other-old-called-REF', own['condition_id'], 'agent', 24, 6),
               (host.NEUTRAL_SLOT, host.NEUTRAL_CONDITION, 'preparation', 470, 60)]
    with sqlite3.connect(ledger) as db:
        for i, (slot, condition, purpose, prompt, output) in enumerate(records):
            request_id = host.NEUTRAL_SLOT + ':0001' if purpose == 'preparation' else f'fixture-{i}'
            db.execute('INSERT INTO requests (request_id,slot_id,condition,usage_id,status,request_sha256,'
                'reserved_nanoyuan,settled_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc,usage_json) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (request_id, slot, condition, purpose, 'settled', 'a' * 64, 100, 50, 100, prompt, 'CPU',
                 json.dumps({'prompt_tokens': prompt, 'completion_tokens': output, 'total_tokens': prompt + output})))
    owner = tmp_path / 'api-coordinator'
    owner.mkdir()
    write_new(owner / 'run-summary.json', {'finished_unix': 1,
        'unentered_generation': [row['slot_id'] for row in plan['rows'][1:]]})
    folder = tmp_path / 'episodes' / str(own['slot_index'])
    folder.mkdir(parents=True)
    write_new(folder / 'result.json', {'slot_id': own['slot_id'], 'instance_id': own['instance_id'],
        'status': 'closed'})
    before = ledger.read_bytes()
    result = reporting.run(scope.PLAN_FILE, tmp_path)
    group = result['groups']['REF']
    assert group['planned'] == 2 and group['mean_actual_tokens_complete_called_subset'] == 10
    assert group['mean_actual_tokens_all_stage_tasks'] == 5
    assert group['independent_recovery_2_accuracy_if_fully_scored'] is None
    assert group['delivery_passed'] is None
    assert result['new_result_endpoint'] == 'independent_REF_recovery_v126'
    assert result['original_records_overwritten'] is False
    assert result['original_REF_preparation_usage']['known_tokens'] == 530
    assert result['original_REF_preparation_usage']['new_preparation_requests'] == 0
    assert result['full_original50_accuracy'] is None and result['model_resampling'] is True
    rows = json.loads((tmp_path / 'reporting/per-task.json').read_bytes())
    assert len(rows) == 2 and all(row['delivery'] is None for row in rows)
    assert ledger.read_bytes() == before
