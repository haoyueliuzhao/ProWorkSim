"""One actual v113 binding control; no scoring rule or resource test is repeated."""
from __future__ import annotations

import json
from types import SimpleNamespace

from proworksim import software_benchmark_grading_v111 as first
from proworksim import software_benchmark_grading_v112 as prior
from proworksim import software_benchmark_grading_v113 as grading
from proworksim.software_benchmark_candidates_v054 import write_new


def test_actual_factory_host_and_cold_child_use_only_v113(tmp_path, monkeypatch):
    calls, watchdog, cold_calls = [], [], []
    def refuse_old(*_args, **_kwargs):
        raise AssertionError('A frozen old scope cannot authorize this v113 binding')
    for module in (first, prior):
        monkeypatch.setattr(module.scope, 'require_grading_allowed', refuse_old)
    monkeypatch.setattr(grading.scope, 'require_grading_allowed',
                        lambda operation, **identity: calls.append((operation, identity)))
    monkeypatch.setattr(grading.scope, 'dispatch_view', lambda guard: SimpleNamespace(
        ROOT=grading.scope.ROOT, GRADING_ROOT=tmp_path/'grading', require_v066_allowed=guard))
    instance = grading.factory(watchdog_guard=lambda operation, **identity: watchdog.append((operation, identity)))
    actual = instance.scorer
    actual.environment.tls.transport.relay_many.__globals__['_authorize']('psf__requests-1766')
    expected = [('v066.transport', {'instance_id': 'psf__requests-1766'})]
    assert calls == watchdog == expected
    assert actual.environment.prepare.__globals__['policy'].GRADING_ROOT == grading.scope.COORDINATOR_ROOT/'provider-bindings'
    assert grading.scope.COORDINATOR_ROOT.name == 'grading-coordinator-v113'
    assert instance.base.prepare_score.__globals__['scope'] is grading.scope
    fixture = {'fixed_python': refuse_old}
    exec('def run_request(request_ref, stop_event=None):\n'
         '    return fixed_python(["-m", "proworksim.software_benchmark_scorer_v066", '
         '"--request", request_ref["path"]])\n', fixture)
    instance.base.run_request = fixture['run_request']
    request = {'slot_id': 'v110:fixture__repo-1:fixture:1', 'instance_id': 'fixture__repo-1'}
    ref = write_new(tmp_path/'request.json', request)
    command = instance.run_request(ref)
    assert command[-4:] == ['-m', 'proworksim.software_benchmark_grading_v113', '--request', ref['path']]
    assert calls[-1] == ('v111.run', request)
    def cold_run(argv, **kwargs):
        cold_calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps({'module': argv[-2]}), stderr='')
    monkeypatch.setattr(grading.cold_manifest.__wrapped__.__globals__['subprocess'], 'run', cold_run)
    grading.cold_manifest.cache_clear()
    try:
        assert grading.cold_manifest() == {'module': 'proworksim.software_benchmark_grading_v113'}
        assert cold_calls[0][-3:] == ['-m', grading.MODULE, '--manifest']
    finally:
        grading.cold_manifest.cache_clear()
    assert grading.main.__globals__['score_request'] is grading.score_request
    assert grading.score_request.__globals__['scope'] is grading.scope
    assert actual._score.__code__ is first.previous.original._score.__code__
    assert actual.VERSION == first.VERSION == prior.VERSION
    assert grading.FRESH_CONTROL_TASKS == first.FRESH_CONTROL_TASKS
