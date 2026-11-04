"""Only the new REF scope/code guard and child binding; no repeated pipeline test."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_grading_v123 as prior
from proworksim import software_benchmark_grading_v125 as grading
from proworksim.software_benchmark_candidates_v054 import write_new


def test_ref_only_guard_and_new_child_use_current_scope(tmp_path, monkeypatch):
    calls = []
    def reject_prior(*_args, **_kwargs):
        raise AssertionError('No previous runtime authority can dispatch this stage')
    monkeypatch.setattr(prior.scope, 'require_grading_allowed', reject_prior)
    monkeypatch.setattr(grading.scope, 'require_grading_allowed',
                        lambda operation, **identity: calls.append((operation, identity)))
    monkeypatch.setattr(grading.scope, 'dispatch_view', lambda guard: SimpleNamespace(
        ROOT=grading.scope.ROOT, GRADING_ROOT=tmp_path/'grading', require_v066_allowed=guard))
    runner = grading.factory()
    namespace = runner.scorer.validate_request.__globals__
    namespace['policy'].require_v066_allowed('v066.score', instance_id='psf__requests-1921')
    assert calls == [('v066.score', {'instance_id': 'psf__requests-1921'})]
    assert runner.scorer.environment.prepare.__globals__['scope'] is grading.scope
    assert runner.scorer._planned is namespace['_planned']
    assert runner.scorer.validate_candidate_request.__code__ is grading.previous.original.validate_candidate_request.__code__
    original_result = ({}, {'role': 'score', 'endpoint': 'code'},
                       {'arm': 'REF', 'slot_index': 7239, 'instance_id': 'psf__requests-1921'})
    guard_namespace = {'_planned': lambda request: original_result}
    guard = grading.bind_ref_code_validation(guard_namespace)
    assert guard({}) == original_result
    original_result[2]['arm'] = 'PROJECT'
    with pytest.raises(ValueError, match='original REF code'):
        guard({})
    original_result[2]['arm'] = 'REF'
    original_result[1]['role'] = 'delivery_score'
    original_result[1]['endpoint'] = 'delivery'
    with pytest.raises(ValueError, match='original REF code'):
        guard({})
    with pytest.raises(PermissionError, match='creates no gold/empty'):
        grading.control_key('psf__requests-1766', 'gold')
    fixture = {'fixed_python': reject_prior}
    exec('def run_request(request_ref, stop_event=None):\n'
         ' return fixed_python(["-m", "proworksim.software_benchmark_scorer_v066", "--request", request_ref["path"]])\n', fixture)
    runner.base.run_request = fixture['run_request']
    request = {'slot_id': 'v110:psf__requests-1921:DEEPSEEK_NT_REF_ALIGNED_B5000K:202611030130',
               'instance_id': 'psf__requests-1921'}
    ref = write_new(tmp_path/'request.json', request)
    assert runner.run_request(ref)[-4:] == ['-m', 'proworksim.software_benchmark_grading_v125', '--request', ref['path']]
    assert calls[-1] == ('v125.run', request)
    cold = grading.cold_manifest.__wrapped__.__globals__
    monkeypatch.setattr(cold['subprocess'], 'run', lambda argv, **kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps({'module': argv[-2]}), stderr=''))
    grading.cold_manifest.cache_clear()
    try:
        assert grading.cold_manifest() == {'module': 'proworksim.software_benchmark_grading_v125'}
    finally:
        grading.cold_manifest.cache_clear()
