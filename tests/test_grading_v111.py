"""Only local metadata and scripted grading controls; no Docker or live network."""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')

from proworksim import software_benchmark_grading_v111 as grading
from proworksim import software_benchmark_project_closure_v110 as closure
from proworksim import software_benchmark_requests_tls_v068 as lifecycle
from proworksim import software_benchmark_requests_tls_v066 as old_tls
from proworksim import software_benchmark_requests_offline_v066 as old_offline
from proworksim.repository_sources_v054 import tree_manifest
from proworksim.software_benchmark_alignment_contract_v110 import condition
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def make_scorer(tmp_path):
    releases, authorizations = [], []
    policy = SimpleNamespace(ROOT=grading.scope.ROOT, GRADING_ROOT=tmp_path/'grading',
        require_v066_allowed=lambda operation, **identity: authorizations.append((operation, identity)),
        release_resource=lambda claim, *, quiescent: releases.append((claim, quiescent)))
    return grading.scorer(policy, manifest_provider=lambda: {'synthetic_cpu_manifest': True}), releases, authorizations


def test_actual_private_runtime_uses_new_authority_and_tls_finish_before_cleanup(tmp_path):
    scorer, _, auth = make_scorer(tmp_path)
    old_policy, old_guard = old_tls.policy, old_offline.require_v066_allowed
    scorer.environment.tls.transport.relay_many.__globals__['_authorize']('psf__requests-1766')
    assert auth == [('v066.transport', {'instance_id': 'psf__requests-1766'})]
    assert scorer.environment.tls.run_official is lifecycle.run_official
    assert scorer._score.__globals__['environment'] is scorer.environment
    assert scorer._score.__code__ is grading.previous.original._score.__code__
    assert scorer.validate_project_delivery.__globals__['validate_delivery_evidence'] is closure.validate_delivery_evidence
    container = SimpleNamespace(id='a'*64)
    events = []
    def remove(*_args):
        events.append('remove')
    namespace = {'cleanup_container': remove, 'container': container}
    exec('def run_instance():\n    cleanup_container(None, container, None)\n    return 17\n', namespace)
    wrapper = SimpleNamespace(delegate=container, finish_transport=lambda: events.append('finish'))
    tracking = {'owned_container_ids': [container.id], 'environment_container': wrapper}
    assert scorer.environment.tls.run_official(namespace['run_instance'], tracking=tracking) == 17
    assert events == ['finish', 'remove'] and namespace['cleanup_container'] is remove
    assert tracking['tls_lifecycle']['binding_restored'] is True
    assert old_tls.policy is old_policy and old_offline.require_v066_allowed is old_guard


@pytest.mark.parametrize('physical_quiet,errors,quiet', [
    (True, ['CA final identity: unavailable'], True),
    (False, ['CA final identity: unavailable'], False),
    (True, ['Bounded transport host thread still running'], False),
])
def test_actual_cleanup_keeps_measurement_unknown_separate_from_physical_cleanup(
        tmp_path, monkeypatch, physical_quiet, errors, quiet):
    scorer, releases, _ = make_scorer(tmp_path)
    namespace = scorer.score_request.__globals__
    base = {'quiescent': physical_quiet, 'cleanup_errors': [], 'create_result_unknown': False}
    monkeypatch.setattr(namespace['original_scorer'], 'cleanup_scoring', lambda *_: copy.deepcopy(base))
    scorer.environment.tls.cleanup_transport = lambda _: errors
    result = scorer.cleanup({'resource_key': 'score-7200'}, {'environment_container': object(), 'claim': {'new': True}})
    assert result['quiescent'] is quiet and releases == [({'new': True}, quiet)]
    assert result['measurement_errors'] == [item for item in errors if item.startswith('CA final identity: ')]
    assert 'resolved' not in result


def test_two_live_tls_control_pairs_are_fixed_before_model_results(monkeypatch):
    called = []
    monkeypatch.setattr(grading, '_parent_qualification_value',
                        lambda task, proof, plan: called.append(task) or {'passed': True})
    for task in ('psf__requests-1766', 'psf__requests-1921'):
        with pytest.raises(ValueError, match='fresh gold/empty'):
            grading.qualification_value(task, {}, {})
    for task in ('psf__requests-2931', 'psf__requests-5414', 'astropy__astropy-14995'):
        assert grading.qualification_value(task, {}, {}) == {'passed': True}
    assert called == ['psf__requests-2931', 'psf__requests-5414', 'astropy__astropy-14995']
    assert grading.prepare_environment_qualifications_local.__globals__['qualification_value'] is grading.qualification_value


def test_new_cold_entry_and_host_grader_do_not_inherit_old_run_authority(tmp_path, monkeypatch):
    class Checked(Exception):
        pass
    calls = []
    def guard(operation, **identity):
        calls.append((operation, identity))
        raise Checked
    monkeypatch.setattr(grading.scope, 'require_grading_allowed', guard)
    request = {'slot_id': 'new-attempt', 'instance_id': 'fixture__repo-1'}
    request_ref = write_new(tmp_path/'request.json', request)
    with pytest.raises(Checked):
        grading.score_request(request)
    with pytest.raises(Checked):
        grading.Grading.run_request(SimpleNamespace(), request_ref)
    assert calls == [('v111.run', request), ('v111.run', request)]
    assert grading.main.__globals__['score_request'] is grading.score_request
    assert grading.command(['--manifest'])[-3:] == ['-m', grading.MODULE, '--manifest']
    assert grading.MODULE == 'proworksim.software_benchmark_grading_v111'


def test_delivery_validator_accepts_only_new_strategy_identity(tmp_path):
    scorer, _, _ = make_scorer(tmp_path)
    validator = scorer.validate_project_delivery.__globals__['validate_delivery_evidence']
    task, seed = 'fixture__repo-1', 2026110301
    slot = f'v110:{task}:{condition("PROJECT")["condition_id"]}:{seed}'
    baseline = {'files': {'a.py': 'x=1\n'}, 'entry_metadata': {
        'a.py': {'kind': 'file', 'encoding': 'utf-8', 'mode': '100644'}}}
    evidence = {'version': closure.VERSION, 'instance_id': task, 'slot_id': slot,
        'locked_before_grading': True, 'model_calls_after_lock': 0, 'submitted': False,
        'delivery_inventory': [], 'binding': None, 'same_tree': None,
        'baseline_tree_sha256': tree_manifest(baseline['files'], baseline['entry_metadata'])['tree_sha256']}
    snapshot = {'version': closure.VERSION, 'instance_id': task, 'slot_id': slot, 'submitted': False}
    assert validator(evidence, snapshot, baseline)['submitted'] is False
    with pytest.raises(ValueError):
        validator({**evidence, 'slot_id': slot.replace('v110:', 'v105:')}, snapshot, baseline)


def test_http_502_is_unknown_without_overwriting_the_official_result(tmp_path):
    scorer, _, _ = make_scorer(tmp_path)
    writer = scorer.score_request.__globals__['write_new']
    for index, (task, actual, expected, unknown) in enumerate([
        ('psf__requests-1766', 502, 200, True), ('psf__requests-1921', 502, 502, False),
        ('psf__requests-2931', 502, 200, False), ('psf__requests-1921', 404, 200, False),
    ]):
        folder = tmp_path/str(index)
        log = folder/'official-output/logs/run_evaluation/run/score'/task/'test_output.txt'
        log.parent.mkdir(parents=True)
        log.write_text(f'E       assert {actual} == {expected}\nE        +  where {actual} = <Response [{actual}]>.status_code\n')
        official = [task, {task: {'resolved': False}}]
        value = {'version': grading.VERSION, 'instance_id': task, 'run_id': 'run',
                 'resource_key': 'score', 'official_result': official, 'status': 'official_report',
                 'resolved': False, 'model_calls': 0, 'transport_result': None}
        writer(folder/'receipt.json', value)
        assert value['official_result'] == official
        assert (value['status'] == 'technical_unknown') is unknown
        if unknown:
            assert value['resolved'] is None
            assert value['scoring_validity']['pure_environment_fault_proven'] is False
            assert reference(log) == value['scoring_validity']['test_output']


def test_actual_frozen_request_validator_checks_only_the_two_new_owned_lanes(tmp_path):
    """Use real frozen image/scorer metadata, a local lease, and no Docker client."""
    if importlib.util.find_spec('swebench') is None:
        # The ordinary dev interpreter intentionally lacks the official scorer.
        # Use its existing unprivileged loader; never install or fetch packages.
        result = subprocess.run([sys.executable, '-B',
            str(grading.scope.ROOT/'tools/run_offline_scorer_v096.py'), '-m', 'pytest', '-q',
            str(Path(__file__).resolve())+'::'+test_actual_frozen_request_validator_checks_only_the_two_new_owned_lanes.__name__],
            cwd=grading.scope.ROOT, capture_output=True, text=True, timeout=60, check=False)
        assert result.returncode == 0, result.stdout+'\n'+result.stderr
        return
    previous_plan = grading.scope.load(reference(grading.scope.ROOT/
        'runs/software-benchmark-v105/nonthinking-interface-r1/execution-plan.json'))
    task = next(item for item in previous_plan['environments']
                if item not in grading.previous.original.environment.TASKS)
    key = 'control-'+task+'-gold'
    config_ref = previous_plan['environments'][task]['configuration']
    local_plan = {'environments': {task: {'configuration': config_ref}},
                  'resources': {key: copy.deepcopy(previous_plan['resources'][key])}}
    plan_ref = write_new(tmp_path/'plan.json', local_plan)
    lanes = []
    def cpu_set(role, lane):
        assert role == 'grader' and lane in (0, 1)
        lanes.append(lane)
        return '0,1,2,3' if lane == 0 else '4,5,6,7'
    policy = SimpleNamespace(ROOT=grading.scope.ROOT, BATCH_ROOT=tmp_path,
        PLAN_FILE=Path(plan_ref['path']), GRADING_ROOT=tmp_path/'grading', VERSION='v111-cpu-fixture',
        __file__=grading.scope.__file__, cpu_set=cpu_set,
        validate_ipv4_targets=grading.scope.original.validate_ipv4_targets,
        require_v066_allowed=lambda *_a, **_kw: None)
    scorer = grading.scorer(policy, manifest_provider=lambda: {'synthetic_cpu_manifest': True})
    scorer.environment.prepare.__globals__['policy'].GRADING_ROOT = tmp_path/'provider'
    scorer.environment.prepare()
    offline_ref = scorer.environment.request_fields('psf__requests-2931')['environment_revision']
    offline = scorer.environment.offline.validate_environment(offline_ref)
    assert offline['authorization_bound_by'].startswith('v111 plan and request')
    claims = tmp_path/'resource-claims'
    claims.mkdir()
    lease = claims/'active-grader-0.json'
    claim_ref = write_new(claims/(key+'.json'), {'version': policy.VERSION, 'key': key,
        'plan': plan_ref, 'spec': {'role': 'control'}, 'lane': 0, 'lease': str(lease)})
    lease.write_bytes(Path(claim_ref['path']).read_bytes())
    manifest_ref = write_new(tmp_path/'manifest.json', scorer.installation_manifest())
    request = {'version': scorer.VERSION, 'limits': scorer.LIMITS, 'plan': plan_ref,
        'resource_key': key, 'instance_id': task, 'configuration': config_ref,
        'patch_kind': 'gold', 'candidate_lock': None, 'environment_revision': None,
        'network_resolution': None, 'scorer_manifest': manifest_ref,
        'directory': str(policy.GRADING_ROOT/key), 'cpuset_cpus': '0,1,2,3', 'capacity_claim': claim_ref}
    assert scorer.validate_request(request)[1]['instance_id'] == task
    assert set(lanes) == {0, 1}
    assert scorer.validate_request.__globals__['MAX_GRADERS'] == 2
    with pytest.raises(ValueError, match='four-CPU affinity'):
        scorer.validate_request({**request, 'cpuset_cpus': '8,9,10,11'})
