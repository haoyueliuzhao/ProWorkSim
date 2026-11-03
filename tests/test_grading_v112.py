"""Two deployment binding controls only; the v111 scoring controls are reused."""
from __future__ import annotations

import json
from types import SimpleNamespace

from proworksim import software_benchmark_grading_v111 as prior
from proworksim import software_benchmark_grading_v112 as grading
from proworksim.software_benchmark_candidates_v054 import write_new


def test_actual_host_request_and_cold_cache_select_the_new_child_module(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(grading.scope, 'require_grading_allowed',
                        lambda operation, **identity: calls.append((operation, identity)))
    def forbidden(*_args, **_kwargs):
        raise AssertionError('The sealed v111 authority must not be called by v112')
    monkeypatch.setattr(prior.scope, 'require_grading_allowed', forbidden)
    request = {'slot_id': 'v110:fixture__repo-1:fixture:1', 'instance_id': 'fixture__repo-1'}
    ref = write_new(tmp_path/'request.json', request)
    fixture = {'fixed_python': forbidden}
    exec('def run_request(request_ref, stop_event=None):\n'
         '    return fixed_python(["-m", "proworksim.software_benchmark_scorer_v066", '
         '"--request", request_ref["path"]])\n', fixture)
    instance = SimpleNamespace(base=SimpleNamespace(run_request=fixture['run_request']))
    command = grading.Grading.run_request(instance, ref)
    assert command[-4:] == ['-m', grading.MODULE, '--request', ref['path']]
    assert grading.MODULE == 'proworksim.software_benchmark_grading_v112'
    assert calls == [('v111.run', request)]
    emitted = []
    def cold_run(argv, **kwargs):
        emitted.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({'bound_child': argv[-2]}), stderr='')
    monkeypatch.setattr(grading.cold_manifest.__wrapped__.__globals__['subprocess'], 'run', cold_run)
    grading.cold_manifest.cache_clear()
    try:
        assert grading.cold_manifest() == {'bound_child': grading.MODULE}
        assert emitted[0][0][-3:] == ['-m', grading.MODULE, '--manifest']
        assert grading.main.__globals__['score_request'] is grading.score_request
        assert grading.score_request.__globals__['scope'] is grading.scope
    finally:
        grading.cold_manifest.cache_clear()


def test_actual_factory_and_tls_guard_are_scoped_to_v112_without_old_mutation(tmp_path, monkeypatch):
    calls, watchdog = [], []
    def forbid_old(*_args, **_kwargs):
        raise AssertionError('The prior runtime cannot supply v112 authority')
    monkeypatch.setattr(prior.scope, 'require_grading_allowed', forbid_old)
    monkeypatch.setattr(grading.scope, 'require_grading_allowed',
                        lambda operation, **identity: calls.append((operation, identity)))
    def dispatch(guard):
        return SimpleNamespace(ROOT=grading.scope.ROOT, GRADING_ROOT=tmp_path/'grading',
                               require_v066_allowed=guard)
    monkeypatch.setattr(grading.scope, 'dispatch_view', dispatch)
    instance = grading.factory(watchdog_guard=lambda operation, **identity: watchdog.append((operation, identity)))
    actual = instance.scorer
    actual.environment.tls.transport.relay_many.__globals__['_authorize']('psf__requests-1766')
    expected = [('v066.transport', {'instance_id': 'psf__requests-1766'})]
    assert calls == watchdog == expected
    provider_policy = actual.environment.prepare.__globals__['policy']
    assert provider_policy.GRADING_ROOT == grading.scope.COORDINATOR_ROOT/'provider-bindings'
    assert instance.base.prepare_score.__globals__['scope'] is grading.scope
    assert actual._score.__code__ is prior.previous.original._score.__code__
    assert actual.VERSION == prior.VERSION
    assert actual.LIMITS == prior.previous.original.LIMITS
    assert grading.FRESH_CONTROL_TASKS == prior.FRESH_CONTROL_TASKS
    assert grading.prepare_environment_qualifications_local.__globals__['qualification_value'] is grading.qualification_value
    assert prior.scorer.__globals__['scope'] is prior.scope
