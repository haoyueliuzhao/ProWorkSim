"""Only new continuation binding; reuse the existing evaluator mechanism checks."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_grading_v120 as prior
from proworksim import software_benchmark_grading_v121 as grading
from proworksim.software_benchmark_candidates_v054 import write_new


def test_independent_recovery_scope_child_and_no_new_controls(tmp_path, monkeypatch):
    calls = []
    def refuse_prior(*_args, **_kwargs):
        raise AssertionError('Completed prior resources cannot authorize new work')
    monkeypatch.setattr(prior.scope, 'require_grading_allowed', refuse_prior)
    monkeypatch.setattr(grading.scope, 'require_grading_allowed',
                        lambda operation, **identity: calls.append((operation, identity)))
    monkeypatch.setattr(grading.scope, 'dispatch_view', lambda guard: SimpleNamespace(
        ROOT=grading.scope.ROOT, GRADING_ROOT=tmp_path/'grading', require_v066_allowed=guard))
    runner = grading.factory()
    runner.scorer.environment.tls.transport.relay_many.__globals__['_authorize']('psf__requests-1921')
    assert calls == [('v066.transport', {'instance_id': 'psf__requests-1921'})]
    assert runner.scorer.environment.prepare.__globals__['scope'] is grading.scope
    assert runner.scorer.environment.policy.GRADING_ROOT == grading.scope.COORDINATOR_ROOT/'provider-bindings'
    with pytest.raises(PermissionError, match='creates no gold/empty'):
        grading.control_key('psf__requests-1921', 'gold')
    assert grading.FRESH_CONTROL_TASKS == frozenset()
    fixture = {'fixed_python': refuse_prior}
    exec('def run_request(request_ref, stop_event=None):\n'
         ' return fixed_python(["-m", "proworksim.software_benchmark_scorer_v066", "--request", request_ref["path"]])\n', fixture)
    runner.base.run_request = fixture['run_request']
    request = {'slot_id': 'v117:fixture__1:PROJECT:8500', 'instance_id': 'fixture__1'}
    ref = write_new(tmp_path/'request.json', request)
    assert runner.run_request(ref)[-4:] == ['-m', 'proworksim.software_benchmark_grading_v121', '--request', ref['path']]
    assert calls[-1] == ('v121.run', request)
    namespace = grading.cold_manifest.__wrapped__.__globals__
    monkeypatch.setattr(namespace['subprocess'], 'run', lambda argv, **kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps({'module': argv[-2]}), stderr=''))
    grading.cold_manifest.cache_clear()
    try:
        assert grading.cold_manifest() == {'module': 'proworksim.software_benchmark_grading_v121'}
    finally:
        grading.cold_manifest.cache_clear()
    assert grading.main.__globals__['verify_prepared_identity'] is grading.verify_prepared_identity
