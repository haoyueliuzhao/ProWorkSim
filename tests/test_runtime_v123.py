"""Narrow deployment controls: new nine identities, amended cash, separate costs."""
from __future__ import annotations

import importlib.util
import json
import socket
import sqlite3
import subprocess

import pytest

from proworksim import software_benchmark_scope_v123 as scope
from proworksim import software_benchmark_host_api_v123 as host
from proworksim import software_benchmark_prior_completion_v123 as gate
from proworksim import software_benchmark_deepseek_api_v105 as original_api
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def tool(name):
    spec = importlib.util.spec_from_file_location(name + '_CPU', scope.ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError('CPU controls cannot use API, services, Docker, or network')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)


def test_actual_nine_binding_cash_and_prior_terminal_gate(tmp_path, monkeypatch):
    manager = tool('run_project_recovery_v123')
    launcher = tool('launch_project_recovery_v123')
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    assert manager.validate_independent_recovery(plan) == plan
    assert {row['slot_index'] for row in plan['rows']} == set(range(8600, 8609))
    assert {row['seed'] for row in plan['rows']} == set(range(20261104012300, 20261104012309))
    assert manager.build_episode.__globals__['bundle'] is host.bundle
    assert host.bundle.__name__.endswith('software_benchmark_sdk_bundle_v120')
    assert host.MAX_CONCURRENCY == 16 and scope.MAX_GENERATIONS == 8 and scope.MAX_GRADERS == 2
    assert host.api.CASH_CAP_CNY == scope.CASH_CAP_CNY == '389.7945248'
    assert host.api.CAP_NANOYUAN != original_api.CAP_NANOYUAN
    assert host.api.cash_grant == reference(scope.CASH_AMENDMENT_FILE)
    assert host.QUALIFICATION == scope.ORIGINAL_BATCH_ROOT / 'api-qualification/result.json'
    assert host.budget_status()['can_start_generation'] is True
    assert host.DeepSeekRuntime.preparation_usage()['new_preparation_API_calls'] == 0
    proof = gate.inspect_prior_completion()
    assert proof['generation_tasks_terminal'] == 27
    assert proof['scoring_attempts_terminal'] == 18 and len(proof['quiescences']) == 45
    assert proof['active_prior_claims'] == []
    assert manager.require_prior_completion is launcher.require_prior_completion is gate.require_prior_completion
    monkeypatch.setattr(scope, 'PRIOR_COMPLETION_FILE', tmp_path / 'unready.json')
    authorized = []
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: authorized.append(True))
    with pytest.raises(gate.PriorStageIncomplete):
        launcher.launch()
    with pytest.raises(gate.PriorStageIncomplete):
        manager.run()
    assert authorized == []
    spec = {**launcher.specification(), 'ownership_token': 'a' * 32}
    assert spec['unit'] == 'proworksim-v118-project.service'
    assert launcher.command(spec)[-2:] == [str(scope.ROOT / 'tools/run_project_recovery_v123.py'), '--execute']


def test_nine_reporting_keeps_prior_cash_stopped_cost_separate(tmp_path):
    reporting = tool('summarize_project_recovery_v123')
    plan = scope.load(reference(scope.PLAN_FILE))
    own = plan['rows'][0]
    ledger = tmp_path / 'api-ledger.sqlite'
    # A fixture-only old API schema; never construct the grant-bound live ledger.
    original_api.BudgetLedger(ledger, max_concurrency=16)
    records = [(own['slot_id'], own['condition_id'], 'agent', 8, 2),
               (own['original_slot_id'], own['condition_id'], 'agent', 24, 6),
               (host.NEUTRAL_SLOT, host.NEUTRAL_CONDITION, 'preparation', 5, 1)]
    with sqlite3.connect(ledger) as db:
        for i, (slot, condition, purpose, prompt, output) in enumerate(records):
            db.execute('INSERT INTO requests (request_id,slot_id,condition,usage_id,status,request_sha256,'
                'reserved_nanoyuan,settled_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc,usage_json) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (f'fixture-{i}', slot, condition, purpose, 'settled', 'a' * 64, 100, 50, 100, prompt, 'CPU',
                 json.dumps({'prompt_tokens': prompt, 'completion_tokens': output, 'total_tokens': prompt + output})))
    owner = tmp_path / 'api-coordinator'
    owner.mkdir()
    write_new(owner / 'run-summary.json', {'finished_unix': 1,
        'unentered_generation': [row['slot_id'] for row in plan['rows'][1:]]})
    folder = tmp_path / 'episodes' / str(own['slot_index'])
    folder.mkdir(parents=True)
    write_new(folder / 'result.json', {'slot_id': own['slot_id'], 'instance_id': own['instance_id'],
        'status': 'closed', 'delivery_validation': {'submitted': False}})
    before = ledger.read_bytes()
    result = reporting.run(scope.PLAN_FILE, tmp_path)
    group = result['groups']['PROJECT']
    assert group['planned'] == 9 and group['mean_actual_tokens_complete_called_subset'] == 10
    assert group['mean_actual_tokens_all_stage_tasks'] == 10 / 9
    assert group['independent_recovery_9_accuracy_if_fully_scored'] is None
    preserved = result['preserved_original_attempt_context']
    assert preserved['original_known_token_lower_bounds']['total_tokens'] == 30
    assert preserved['preserved_original_unknowns'] == 9 and preserved['original_outcomes_overwritten'] is False
    assert preserved['combined_original50_accuracy'] is None
    mapping = json.loads((tmp_path / 'reporting/original-to-recovery-mapping.json').read_bytes())
    assert len(mapping) == 9 and all(item['original_generation_status'] == 'technical_unknown' for item in mapping)
    assert all(item['new_slot_id'] != item['original_slot_id'] for item in mapping)
    assert ledger.read_bytes() == before
