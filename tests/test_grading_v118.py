"""One new scope/child/route binding control; no Docker or original tests."""
from __future__ import annotations

import json
from types import SimpleNamespace

from proworksim import software_benchmark_grading_v113 as old
from proworksim import software_benchmark_grading_requests_v116 as tls_old
from proworksim import software_benchmark_grading_v118 as grading
from proworksim.software_benchmark_candidates_v054 import write_new


def test_new_factory_authority_and_child_with_selective_reset(tmp_path, monkeypatch):
    calls, watchdog, cold_calls = [], [], []

    def refuse_old(*_args, **_kwargs):
        raise AssertionError('Historical scope must not authorize the new PROJECT evaluation')

    for module in (old, tls_old):
        monkeypatch.setattr(module.scope, 'require_grading_allowed', refuse_old)
    monkeypatch.setattr(grading.scope, 'require_grading_allowed',
        lambda operation, **identity: calls.append((operation, identity)))
    monkeypatch.setattr(grading.scope, 'dispatch_view', lambda guard: SimpleNamespace(
        ROOT=grading.scope.ROOT, GRADING_ROOT=tmp_path/'grading', require_v066_allowed=guard))
    runner = grading.factory(watchdog_guard=lambda op, **identity: watchdog.append((op, identity)))
    actual = runner.scorer
    actual.environment.tls.transport.relay_many.__globals__['_authorize']('psf__requests-1766')
    assert calls == watchdog == [('v066.transport', {'instance_id': 'psf__requests-1766'})]
    assert actual.environment.policy.GRADING_ROOT == grading.scope.COORDINATOR_ROOT/'provider-bindings'
    assert actual.environment.prepare.__globals__['scope'] is grading.scope
    assert runner.base.prepare_score.__globals__['scope'] is grading.scope
    assert actual.validate_project_delivery.__globals__['validate_delivery_evidence'] is grading.closure.validate_delivery_evidence
    concrete = actual._v118_concrete_score
    reset = actual._v118_reset_scorer
    assert concrete.__globals__['diagnostics'] is grading.previous.original.diagnostics
    assert reset._score.__globals__['diagnostics'] is not concrete.__globals__['diagnostics']
    assert actual.score_request.__globals__['_score'] is actual._score
    # Enter the real selected _score bodies up to their baseline lookup and
    # stop before any Docker, source modification, or official evaluator call.
    entered = []
    monkeypatch.setattr(concrete.__globals__['base'], 'read_local_dataset', lambda _: {
        task: {'instance_id': task} for task in (*grading.FRESH_CONTROL_TASKS, *grading.reset_binding.reset.TASKS)})
    for name, namespace in (('concrete', concrete.__globals__), ('reset', reset._score.__globals__)):
        monkeypatch.setitem(namespace, 'load', lambda _: {})
        def lookup(mapping, *, instance, image, route=name):
            entered.append((route, instance['instance_id']))
            raise LookupError('CPU stop before original baseline validation and all execution')
        monkeypatch.setitem(namespace, 'validate_mapping', lookup)
    for task in sorted(grading.FRESH_CONTROL_TASKS | grading.reset_binding.reset.TASKS):
        try:
            actual._score({}, {}, {'instance_id': task, 'scorer_request_base': {
                'dataset': {}, 'baseline_mapping': {}, 'image': {}}}, {})
        except LookupError:
            pass
        else:
            raise AssertionError('The actual scorer must reach the bounded CPU lookup')
        assert entered[-1] == ('reset' if task in grading.reset_binding.reset.TASKS else 'concrete', task)
    fixture = {'fixed_python': refuse_old}
    exec('def run_request(request_ref, stop_event=None):\n'
         ' return fixed_python(["-m", "proworksim.software_benchmark_scorer_v066", "--request", request_ref["path"]])\n', fixture)
    runner.base.run_request = fixture['run_request']
    request = {'slot_id': 'v117:fixture__1:PROJECT:8000', 'instance_id': 'fixture__1'}
    ref = write_new(tmp_path/'request.json', request)
    command = runner.run_request(ref)
    assert command[-4:] == ['-m', 'proworksim.software_benchmark_grading_v118', '--request', ref['path']]
    assert calls[-1] == ('v118.run', request)

    def cold_run(argv, **kwargs):
        cold_calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps({'module': argv[-2]}), stderr='')

    monkeypatch.setattr(grading.cold_manifest.__wrapped__.__globals__['subprocess'], 'run', cold_run)
    grading.cold_manifest.cache_clear()
    try:
        assert grading.cold_manifest() == {'module': 'proworksim.software_benchmark_grading_v118'}
        assert cold_calls[0][-3:] == ['-m', grading.MODULE, '--manifest']
    finally:
        grading.cold_manifest.cache_clear()
    assert grading.main.__globals__['score_request'] is grading.score_request
    assert actual.VERSION == grading.VERSION and grading.scope.MAX_GRADERS == 2
