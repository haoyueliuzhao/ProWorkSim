"""CPU-only new recovery identities and endpoint wiring; no grader/model starts."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_grading_recovery_v114 as grading
from proworksim import software_benchmark_grading_repairs_v114 as repairs
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def local_binding(tmp_path, monkeypatch):
    old = grading.scope.load(reference(grading.scope.BATCH_ROOT/'execution-plan-v113.json'))
    indices = {7232, 7238, 7239, 7244, 7251, 7266, 7267, 7283}
    rows = [row for row in old['rows'] if row['slot_index'] in indices]
    recovery = []
    resources = {}
    for row in rows:
        index = row['slot_index']
        resource = copy.deepcopy(old['resources'][f'score-{index}'])
        if index in grading.stopped.TASKS:
            resource['endpoint'] = grading.stopped.ENDPOINT
            key = f'score-v114-{index}'
            recovery.append({'row': row, 'kind': grading.stopped.ENDPOINT, 'endpoint': 'code',
                'result': reference(grading.stopped.OUTPUT/str(index)/'recovery-result.json')})
        elif index in grading.CLOSED_RESCORES:
            key = f'score-v114-{index}'
            recovery.append({'row': row, 'kind': 'original_locked', 'endpoint': 'code',
                'result': reference(grading.scope.BATCH_ROOT/'episodes'/str(index)/'result.json')})
        else:
            key = f'score-{index}'
        resources[key] = resource
    plan = {'rows': rows, 'resources': resources, 'score_recoveries': recovery,
            'fresh_control_tasks': sorted(grading.FRESH_CONTROL_TASKS)}
    plan_ref = write_new(tmp_path/'plan.json', plan)
    monkeypatch.setattr(grading.scope, 'PLAN_FILE', Path(plan_ref['path']))
    monkeypatch.setattr(grading.scope, 'COORDINATOR_ROOT', tmp_path/'coordinator')
    monkeypatch.setattr(grading.scope, 'GRADING_ROOT', tmp_path/'grading')
    # Environment freshness/CA authorization is independently owned by root;
    # this control does not prepare or qualify any real environment.
    monkeypatch.setattr(grading, 'environment_revision', lambda: SimpleNamespace(bind_environment=lambda value, policy: value))
    policy = SimpleNamespace(ROOT=grading.scope.ROOT, GRADING_ROOT=tmp_path/'grading',
        PLAN_FILE=grading.scope.PLAN_FILE, BATCH_ROOT=grading.scope.BATCH_ROOT,
        require_v066_allowed=lambda *_a, **_kw: None)
    scorer = grading.scorer(policy, manifest_provider=lambda: {'CPU_ONLY_manifest': True})
    evidence = []
    def qualification(ref, config, plan_id):
        assert grading.scope.load(ref) == {'CPU_ONLY_qualification_fixture': True}
        assert plan_id == plan_ref
        evidence.append(config['instance_id'])
    scorer.validate_qualification = qualification
    (grading.scope.COORDINATOR_ROOT/'qualifications').mkdir(parents=True)
    for task in {row['instance_id'] for row in rows}:
        write_new(grading.scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'), {'CPU_ONLY_qualification_fixture': True})
    scorer.environment.request_fields = lambda task: {'environment_revision': None, 'network_resolution': None}
    monkeypatch.setitem(grading._namespace, 'cold_manifest', scorer.installation_manifest)
    return grading.host(policy, scorer), scorer, plan, evidence


def test_actual_four_source_requests_preserve_primary_vs_supplemental_identity(tmp_path, monkeypatch):
    host, scorer, plan, gates = local_binding(tmp_path, monkeypatch)
    for spec in plan['score_recoveries']:
        ref = host.prepare_score_recovery(spec)
        request = grading.scope.load(ref)
        index = spec['row']['slot_index']
        _, resource, config = scorer._planned(request)
        assert request['resource_key'] == f'score-v114-{index}'
        assert request['candidate_lock'] == grading.scope.load(spec['result'])['candidate_lock']
        if spec['kind'] == grading.stopped.ENDPOINT:
            lock = grading.validate_recovery_candidate(request, resource, config, plan)
            assert lock['endpoint'] == grading.stopped.ENDPOINT
            assert request['measurement_kind'] == grading.RECOVERED_MEASUREMENT
            assert grading.scope.load(request['generation_result'])['status'] == 'technical_unknown'
            with pytest.raises(ValueError):
                scorer._planned({**request, 'measurement_kind': 'full_verified_comparison'})
            with pytest.raises(ValueError):
                grading.validate_recovery_candidate(request, {**resource, 'endpoint': 'code'}, config, plan)
        else:
            assert request['measurement_kind'] == 'full_verified_comparison'
            assert grading.scope.load(request['generation_result'])['status'] == 'closed'
            assert request['rescore_of'] == reference(grading.scope.BATCH_ROOT/'grading'/f'score-{index}'/'request.json')
    assert len(gates) == 4
    assert grading.main.__globals__['score_request'] is grading.score_request
    assert grading.Grading.__init__.__globals__['host'] is grading.host
    assert grading.command(['--manifest'])[-3:] == ['-m', grading.MODULE, '--manifest']


def test_supplemental_receipt_keeps_original_unknown_and_never_relabels_it_closed(tmp_path):
    request = {'measurement_kind': grading.RECOVERED_MEASUREMENT,
        'recovery_result': {'CPU_fixture': 'recovery'},
        'original_generation_result': {'CPU_fixture': 'original_unknown'}}
    prepared = write_new(tmp_path/'request.json', request)
    writer = grading.bind_supplemental_writer({'write_new': write_new})
    identity = {'endpoint': grading.stopped.ENDPOINT, 'request': prepared}
    identity_ref = writer(tmp_path/'identity.json', identity)
    receipt = {'endpoint': grading.stopped.ENDPOINT, 'identity': identity_ref, 'status': 'official_report', 'resolved': True}
    writer(tmp_path/'receipt.json', receipt)
    assert receipt['original_generation_status'] == 'technical_unknown'
    assert receipt['replaces_original_endpoint'] is False and receipt['model_resampling'] is False
    assert receipt['original_generation_result'] == request['original_generation_result']
    assert receipt['endpoint'] == grading.stopped.ENDPOINT and receipt['status'] == 'official_report'
    bad = write_new(tmp_path/'bad-request.json', {**request, 'measurement_kind': 'full_verified_comparison'})
    with pytest.raises(ValueError, match='masquerade'):
        writer(tmp_path/'bad'/'identity.json', {'endpoint': grading.stopped.ENDPOINT, 'request': bad})


def test_conditional_reset_passthrough_calls_the_official_factory_only_once(tmp_path, monkeypatch):
    _, scorer, _, _ = local_binding(tmp_path, monkeypatch)
    rows = [row for row in json.loads((grading.scope.ROOT/'artifacts/software-benchmark-v054/source/trusted-evaluation.json').read_bytes())
            if row['instance_id'] in repairs.reset.TASKS]
    calls, observed = [], []
    def factory(harness, directory):
        calls.append(directory)
        return lambda spec, *_a, **_kw: observed.append(spec), {'CPU_fixture': True}
    original = SimpleNamespace(make_repaired_run_instance=factory)
    scorer.diagnostics = scorer._score.__globals__['diagnostics'] = original
    bound = repairs.bind_scorer(scorer, rows, passthrough_tasks=grading.stopped.TASKS.values())
    spec = importlib.util.spec_from_file_location('v114_reuse_original_spec_builder',
        grading.scope.ROOT/'tools/check_test_reset_v099.py')
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    spec_factory, _ = previous.actual_spec_factory()
    dispatch, evidence = bound._score.__globals__['diagnostics'].make_repaired_run_instance(
        SimpleNamespace(make_test_spec=spec_factory), tmp_path/'diagnostics')
    spec = SimpleNamespace(instance_id='matplotlib__matplotlib-22865', eval_script='unchanged CPU fixture')
    dispatch(spec)
    assert observed == [spec] and calls == [tmp_path/'diagnostics']
    assert evidence['unchanged_passthrough_tasks'] == sorted(grading.stopped.TASKS.values())
    for row in rows:
        original_spec = spec_factory(row)
        original_script = original_spec.eval_script
        dispatch(original_spec)
        expected, _ = repairs.reset.repair_eval_script({**row, 'eval_script': original_script})
        assert observed[-1] is not original_spec and observed[-1].eval_script == expected
        assert original_spec.eval_script == original_script
    assert calls == [tmp_path/'diagnostics']
    with pytest.raises(ValueError, match='outside'):
        dispatch(SimpleNamespace(instance_id='unplanned__repo-1'))
