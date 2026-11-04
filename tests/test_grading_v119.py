"""One fresh-scope/child binding check; reuse the unchanged evaluator controls."""
from __future__ import annotations

import json
from types import SimpleNamespace

from proworksim import software_benchmark_grading_v118 as previous
from proworksim import software_benchmark_grading_v119 as grading
from proworksim.software_benchmark_candidates_v054 import write_new


def test_fresh_scope_and_real_child_command_keep_unconsumed_resource_keys(tmp_path, monkeypatch):
    calls, watchdog = [], []
    def refuse_previous(*_args, **_kwargs):
        raise AssertionError('The frozen failed deployment cannot authorize recovery work')
    monkeypatch.setattr(previous.scope, 'require_grading_allowed', refuse_previous)
    monkeypatch.setattr(grading.scope, 'require_grading_allowed',
                        lambda operation, **identity: calls.append((operation, identity)))
    monkeypatch.setattr(grading.scope, 'dispatch_view', lambda guard: SimpleNamespace(
        ROOT=grading.scope.ROOT, GRADING_ROOT=tmp_path/'grading', require_v066_allowed=guard))
    runner = grading.factory(watchdog_guard=lambda op, **identity: watchdog.append((op, identity)))
    runner.scorer.environment.tls.transport.relay_many.__globals__['_authorize']('psf__requests-1766')
    assert calls == watchdog == [('v066.transport', {'instance_id': 'psf__requests-1766'})]
    assert runner.scorer.environment.prepare.__globals__['scope'] is grading.scope
    assert runner.scorer.environment.policy.GRADING_ROOT == grading.scope.COORDINATOR_ROOT/'provider-bindings'
    assert grading.control_key('psf__requests-1766', 'gold') == 'control-v118-psf__requests-1766-gold'
    assert grading.scope.GRADING_ROOT.name == 'grading-v119'
    fixture = {'fixed_python': refuse_previous}
    exec('def run_request(request_ref, stop_event=None):\n'
         ' return fixed_python(["-m", "proworksim.software_benchmark_scorer_v066", "--request", request_ref["path"]])\n', fixture)
    runner.base.run_request = fixture['run_request']
    request = {'slot_id': 'v117:fixture__1:PROJECT:8000', 'instance_id': 'fixture__1'}
    ref = write_new(tmp_path/'request.json', request)
    command = runner.run_request(ref)
    assert command[-4:] == ['-m', 'proworksim.software_benchmark_grading_v119', '--request', ref['path']]
    assert calls[-1] == ('v119.run', request)
    cold = grading.cold_manifest.__wrapped__.__globals__
    monkeypatch.setattr(cold['subprocess'], 'run', lambda argv, **kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps({'module': argv[-2]}), stderr=''))
    grading.cold_manifest.cache_clear()
    try:
        assert grading.cold_manifest() == {'module': 'proworksim.software_benchmark_grading_v119'}
    finally:
        grading.cold_manifest.cache_clear()
    assert grading.main is grading.recovery_main
    assert grading.main.__globals__['verify_prepared_identity'] is grading.verify_prepared_identity
