"""CPU-only checks of the actual TLS binding and conservative cleanup boundary."""
from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from proworksim import software_benchmark_grading_v108 as grading
from proworksim import software_benchmark_physical_cleanup_v108 as physical
from proworksim import software_benchmark_requests_tls_v068 as lifecycle
from proworksim.software_benchmark_candidates_v054 import reference


def make_scorer():
    releases = []
    policy = SimpleNamespace(require_v066_allowed=lambda *a, **k: None,
        GRADING_ROOT=Path('/unused-local-fixture'),
        release_resource=lambda claim, *, quiescent: releases.append((claim, quiescent)))
    return grading.scorer(policy, manifest_provider=lambda: {'synthetic': True}), releases


def test_actual_private_evaluator_finishes_tls_before_its_own_cleanup():
    scorer, _ = make_scorer()
    assert scorer.environment.tls.run_official is lifecycle.run_official
    assert scorer._score.__globals__['environment'] is scorer.environment
    events = []
    container = SimpleNamespace(id='a' * 64)
    def original_cleanup(*args):
        events.append('remove')
    namespace = {'cleanup_container': original_cleanup, 'container': container}
    exec('def run_instance():\n    cleanup_container(None, container, None)\n    return 17\n', namespace)
    wrapper = SimpleNamespace(delegate=container, finish_transport=lambda: events.append('finish'))
    tracking = {'owned_container_ids': [container.id], 'environment_container': wrapper}
    assert scorer.environment.tls.run_official(namespace['run_instance'], tracking=tracking) == 17
    assert events == ['finish', 'remove']
    assert namespace['cleanup_container'] is original_cleanup
    assert tracking['tls_lifecycle']['binding_restored'] is True
    assert scorer._score.__code__ is grading.previous.original._score.__code__


@pytest.mark.parametrize('physical_quiet,transport_errors,expected_quiet', [
    (True, ['CA final identity: missing object'], True),
    (False, ['CA final identity: missing object'], False),
    (True, ['Bounded transport host thread still running'], False),
])
def test_actual_cleanup_does_not_confuse_ca_measurement_with_physical_evidence(
        monkeypatch, physical_quiet, transport_errors, expected_quiet):
    scorer, releases = make_scorer()
    namespace = scorer.score_request.__globals__
    assert namespace['cleanup'] is scorer.cleanup
    base = {'quiescent': physical_quiet, 'cleanup_errors': [], 'create_result_unknown': False}
    monkeypatch.setattr(namespace['original_scorer'], 'cleanup_scoring', lambda *args: copy.deepcopy(base))
    scorer.environment.tls.cleanup_transport = lambda tracking: list(transport_errors)
    transport = {'path': '/unchanged/unknown-transport.json', 'sha256': 'unchanged'}
    result = scorer.cleanup({'resource_key': 'score-fixture'}, {
        'environment_container': object(), 'claim': {'original': True}, 'transport_result': transport})
    assert result['quiescent'] is expected_quiet
    assert releases == [({'original': True}, expected_quiet)]
    assert result['transport_result'] is transport
    assert result['measurement_errors'] == [e for e in transport_errors if e.startswith('CA final identity: ')]
    assert 'resolved' not in result


def test_fresh_exact_id_absence_is_required_without_any_docker_call():
    now = time.time()
    inputs = {'container_id': 'a' * 64, 'finished_unix': now - 1000}
    good = {'container_id': inputs['container_id'], 'exists': False, 'status': 404, 'inspected_unix': now}
    physical.validate_observation(good, inputs, now)
    for change in ({'container_id': 'b' * 64}, {'exists': True}, {'status': 200},
                   {'inspected_unix': now - 301}, {'inspected_unix': now + 10}):
        with pytest.raises(ValueError, match='fresh read-only 404'):
            physical.validate_observation({**good, **change}, inputs, now)


def test_actual_consumed_request_inputs_are_bound_but_not_released():
    for key in physical.KEYS:
        folder = physical.owner_scope.GRADING_ROOT / key
        inputs = physical.inspect_inputs(reference(folder / 'request.json'))
        assert inputs['container_id'] == physical.owner_scope.load(inputs['refs']['initial'])['container_id']
        assert physical.owner_scope.load(inputs['refs']['receipt'])['status'] == 'technical_unknown'
        assert inputs['claim']['key'] == key
    other = physical.owner_scope.GRADING_ROOT / 'score-7033/request.json'
    with pytest.raises(ValueError, match='two exact original'):
        physical.inspect_inputs(reference(other))


def test_http_502_validity_requires_an_actual_unexpected_response_assertion(tmp_path):
    scorer, _ = make_scorer()
    writer = scorer.score_request.__globals__['write_new']
    cases = [
        ('psf__requests-1766', False, 'E       assert 502 == 200\nE        +  where 502 = <Response [502]>.status_code\n', True),
        ('psf__requests-1766', False, 'E       assert 502 == 502\nE        +  where 502 = <Response [502]>.status_code\n', False),
        ('psf__requests-1766', False, 'Expected HTTP 502 is documented here; ordinary model failure\n', False),
        ('psf__requests-1766', True, 'E       assert 502 == 200\nE        +  where 502 = <Response [502]>.status_code\n', False),
        ('other-repository-task', False, 'E       assert 502 == 200\nE        +  where 502 = <Response [502]>.status_code\n', False),
    ]
    for index, (task, resolved, text, unknown) in enumerate(cases):
        folder = tmp_path / str(index)
        log = folder / 'official-output/logs/run_evaluation/run/score/task-placeholder/test_output.txt'
        log = log.parent.parent / task / log.name
        log.parent.mkdir(parents=True)
        log.write_text(text)
        official = [task, {task: {'resolved': resolved}}]
        receipt = {'version': grading.VERSION, 'instance_id': task, 'run_id': 'run',
            'resource_key': 'score', 'official_result': official, 'status': 'official_report',
            'resolved': resolved, 'model_calls': 0, 'transport_result': None}
        writer(folder / 'receipt.json', receipt)
        assert receipt['official_result'] == official
        assert (receipt['status'] == 'technical_unknown') is unknown
        if unknown:
            assert receipt['resolved'] is None
            assert receipt['scoring_validity']['pure_environment_fault_proven'] is False
