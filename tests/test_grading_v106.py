"""Local-only checks of the amended scorer's actual validator and cold binding."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_grading_v105 as previous
from proworksim import software_benchmark_grading_v106 as grading
from proworksim import software_benchmark_project_closure_v106 as closure
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.repository_sources_v054 import tree_manifest


def test_private_actual_delivery_validator_uses_new_identity_and_preserves_old():
    policy = SimpleNamespace(require_v066_allowed=lambda *a, **k: None,
                             GRADING_ROOT=Path('/unused-local-fixture'))
    value = grading.scorer(policy, manifest_provider=lambda: {'synthetic': True})
    validator = value.validate_project_delivery.__globals__['validate_delivery_evidence']
    assert validator is closure.validate_delivery_evidence
    assert previous.original.validate_project_delivery.__globals__['validate_delivery_evidence'] is not validator
    task = closure.TASK_IDS[0]
    slot = f'v105:{task}:{closure.CONDITION}:{closure.SEED_BASE}'
    baseline = {'files': {'a.py': 'x = 1\n'}, 'entry_metadata': {
        'a.py': {'kind': 'file', 'encoding': 'utf-8', 'mode': '100644'}}}
    evidence = {'version': closure.VERSION, 'instance_id': task, 'slot_id': slot,
        'locked_before_grading': True, 'model_calls_after_lock': 0, 'submitted': False,
        'delivery_inventory': [], 'binding': None, 'same_tree': None,
        'baseline_tree_sha256': tree_manifest(baseline['files'], baseline['entry_metadata'])['tree_sha256']}
    snapshot = {'version': closure.VERSION, 'instance_id': task, 'slot_id': slot, 'submitted': False}
    assert validator(evidence, snapshot, baseline)['submitted'] is False
    for key, wrong in [('version', 'v064'), ('instance_id', closure.TASK_IDS[1]), ('slot_id', slot.replace('v105:', 'v064:'))]:
        changed = {**evidence, key: wrong}
        with pytest.raises(ValueError):
            validator(changed, snapshot, baseline)
    assert grading.command(['--manifest'])[-3:] == ['-m', grading.MODULE, '--manifest']
    assert grading.MODULE.endswith('grading_v106')


def test_actual_request_validator_enumerates_only_two_real_lanes(tmp_path):
    """Real validation, base manifest and lease checks; no Docker/API call."""
    plan = grading.scope.load(reference(grading.scope.PLAN_FILE))
    task = next(t for t in plan['environments'] if t not in grading.previous.original.environment.TASKS)
    key = 'control-' + task + '-gold'
    config_ref = plan['environments'][task]['configuration']
    local_plan = {'environments': {task: {'configuration': config_ref}},
                  'resources': {key: copy.deepcopy(plan['resources'][key])}}
    plan_ref = write_new(tmp_path/'plan.json', local_plan)
    calls = []
    def cpu_set(role, lane):
        assert role == 'grader' and lane in (0, 1), 'A non-existent grading lane was accessed'
        calls.append(lane)
        return '0,1,2,3' if lane == 0 else '4,5,6,7'
    policy = SimpleNamespace(ROOT=grading.scope.ROOT, BATCH_ROOT=tmp_path, PLAN_FILE=Path(plan_ref['path']),
        GRADING_ROOT=tmp_path/'grading', VERSION=grading.scope.VERSION,
        __file__=grading.scope.__file__, validate_ipv4_targets=grading.scope.previous.original.validate_ipv4_targets,
        require_v066_allowed=lambda *a, **k: None, cpu_set=cpu_set)
    value = grading.scorer(policy, manifest_provider=lambda: {'synthetic_manifest_for_local_validation': True})
    namespace = value.validate_request.__globals__
    # Write only fixture metadata in pytest's temporary directory, then execute
    # the real environment/base-manifest/capacity validators with no stubs.
    value.environment.prepare.__globals__['policy'].GRADING_ROOT = tmp_path/'provider'
    value.environment.prepare()
    claim_folder = tmp_path/'resource-claims'
    claim_folder.mkdir()
    lease = claim_folder/'active-grader-0.json'
    claim = {'version': policy.VERSION, 'key': key, 'plan': plan_ref,
             'spec': {'role': 'control'}, 'lane': 0, 'lease': str(lease)}
    claim_ref = write_new(claim_folder/(key+'.json'), claim)
    lease.write_bytes(Path(claim_ref['path']).read_bytes())
    manifest_ref = write_new(tmp_path/'manifest.json', value.installation_manifest())
    request = {'version': value.VERSION, 'limits': value.LIMITS, 'plan': plan_ref,
        'resource_key': key, 'instance_id': task, 'configuration': config_ref,
        'patch_kind': 'gold', 'candidate_lock': None,
        'environment_revision': None, 'network_resolution': None,
        'scorer_manifest': manifest_ref, 'directory': str(policy.GRADING_ROOT/key),
        'cpuset_cpus': '0,1,2,3', 'capacity_claim': claim_ref}
    assert value.validate_request(request)[1]['instance_id'] == task
    assert set(calls) == {0, 1}
    assert namespace['MAX_GRADERS'] == 2
    assert value._score.__code__ is previous.original._score.__code__
    with pytest.raises(ValueError, match='four-CPU affinity'):
        value.validate_request({**request, 'cpuset_cpus': '8,9,10,11'})


def test_report_reads_new_lifecycle_and_condition_from_official_identity(tmp_path):
    spec = importlib.util.spec_from_file_location('v106_metrics_test',
        grading.scope.ROOT/'tools/summarize_interface_panel_v106.py')
    metrics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metrics)
    panel = json.loads(grading.scope.PANEL_FILE.read_bytes())
    coordinator = tmp_path/'api-coordinator-v106'
    coordinator.mkdir()
    write_new(coordinator/'progress.json', {'generation': {panel['rows'][0]['slot_id']: {'status': 'running'}}})
    result = metrics.run(grading.scope.PANEL_FILE, tmp_path)
    assert Path(result['coordinator_source']['path']).parent == coordinator
    assert result['groups'][panel['rows'][0]['arm']]['generation_states']['running'] == 1
    row = panel['rows'][0]
    folder = tmp_path/'grading'/'synthetic-score'
    folder.mkdir(parents=True)
    candidate_ref = write_new(folder/'candidate.json', {'patch_receipt': {'patch': {'bytes': 7}}})
    request = {k: row[k] for k in ('slot_id', 'instance_id')}
    request['candidate_lock'] = candidate_ref
    request_ref = write_new(folder/'request.json', request)
    identity_ref = write_new(folder/'identity.json', {**request, 'condition_id': row['condition_id'], 'request': request_ref})
    write_new(folder/'receipt.json', {**{k: row[k] for k in ('slot_id', 'instance_id', 'condition_id')},
        'identity': identity_ref, 'status': 'official_report', 'resolved': True,
        'candidate_changed': False, 'actor_feedback': False,
        'official_result': [None, {row['instance_id']: {'resolved': True, 'patch_successfully_applied': True}}]})
    write_new(folder/'completion.json', {'returncode': 0})
    write_new(folder/'quiescence.json', {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False})
    assert metrics.official_score(folder, row)['resolved'] is True
    with pytest.raises(ValueError, match='exact candidate'):
        metrics.official_score(folder, {**row, 'condition_id': 'wrong'})
