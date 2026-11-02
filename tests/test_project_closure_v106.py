"""CPU-only closure identity repair, retaining full same-version evidence rules."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_managed_v105 as managed
from proworksim import software_benchmark_project_closure_v106 as closure
from proworksim import software_benchmark_world_v064 as world
from proworksim.harness_port import HarnessPort
from proworksim.repository_sources_v054 import capture_repository, tree_manifest
from proworksim.software_benchmark_candidates_v054 import checked, read_episode_candidates
from proworksim.software_organization_runtime_v047 import DispatchDeadline

TASK = 'matplotlib__matplotlib-23476'
SLOT = 'v105:matplotlib__matplotlib-23476:DEEPSEEK_NT_PROJECT_B5000K:202611020116'


def fixture(tmp_path):
    source = tmp_path / 'public'
    source.mkdir()
    (source / 'sample.py').write_text('value = 0\n')
    manifest = capture_repository(source, tmp_path / 'snapshot', task_id=TASK,
        problem_statement='Synthetic CPU source; never a benchmark attempt.',
        source_identity={'instance_id': TASK, 'repo': 'matplotlib/matplotlib',
                         'base_commit': 'a' * 40, 'dataset_revision': 'b' * 40})
    calls = []
    def public_test(**payload):
        calls.append(copy.deepcopy(payload))
        tree = tree_manifest(payload['files'], payload['entry_metadata'])['tree_sha256']
        return {'passed': False, 'execution': {'executed': True, 'input_tree_sha256': tree},
                'groups': {'public': {'status': 'failed', 'executed': True, 'passed': False,
                                      'tests': [{'test_id': 'scripted', 'passed': False}]}}}
    prepared = managed.prepare_case(manifest, tmp_path / 'world', max_total_tokens=5_000_000,
        public_test_callback=public_test, deadline=DispatchDeadline(soft_seconds=21600, hard_seconds=23400))
    port = HarnessPort(world.SoftwareCollaborationPort(
        prepared.world.session('member_001', world.PROJECT), 'member_001'), 'member_001',
        project_id=world.PROJECT, public_sink=lambda *_: None,
        world_sink=lambda *_: None, harness_sink=lambda *_: None)
    def call(tool, **arguments):
        value = port.call(tool, request_key=f"cpu-{len(prepared.world.store.load()['software_events'])}",
                          association={}, **arguments)
        assert value['ok'], value
        return value['result']
    return prepared, call, calls


def read(ref):
    return json.loads(checked(ref).read_bytes())


def test_actual_v105_identity_exports_distinct_code_and_legal_delivery(tmp_path):
    prepared, call, calls = fixture(tmp_path)
    call('write_file', path='sample.py', text='value = 1\n')
    call('run_tests')
    call('fix_patch', task_ids=[], message='Freeze the scripted tested version')
    call('submit_integration', message='Submit that same version')
    call('write_file', path='sample.py', text='value = 2\n')
    result = closure.export_managed_closure(prepared, tmp_path / 'closed', slot_id=SLOT, sdk_closed=True)
    pair = read_episode_candidates(result['project_candidate_lock'])
    assert pair['terminal_code']['files']['sample.py'] == 'value = 2\n'
    assert pair['last_legal_delivery']['files']['sample.py'] == 'value = 1\n'
    assert len(calls) == 1  # Scripted local callback, no shell/test process.
    evidence, snapshot, baseline = (read(result[key]) for key in
        ('delivery_evidence', 'delivery_snapshot', 'baseline_snapshot'))
    assert closure.validate_delivery_evidence(evidence, snapshot, baseline)['same_tree'] is False
    tampered = copy.deepcopy(evidence)
    tampered['binding']['public_test_event']['executed'] = False
    with pytest.raises(ValueError, match='actual member/version/test'):
        closure.validate_delivery_evidence(tampered, snapshot, baseline)
    tampered = copy.deepcopy(evidence)
    tampered['model_calls_after_lock'] = 1
    with pytest.raises(ValueError, match='lock-before-score'):
        closure.validate_delivery_evidence(tampered, snapshot, baseline)


def test_zero_model_no_delivery_exports_without_inventing_delivery(tmp_path):
    prepared, _, calls = fixture(tmp_path)
    result = closure.export_managed_closure(prepared, tmp_path / 'closed', slot_id=SLOT, sdk_closed=True)
    evidence, snapshot, baseline = (read(result[key]) for key in
        ('delivery_evidence', 'delivery_snapshot', 'baseline_snapshot'))
    assert calls == []
    assert closure.validate_delivery_evidence(evidence, snapshot, baseline) == {
        'submitted': False, 'same_tree': None, 'legal_delivery_evidence': False}
    assert snapshot['candidate'] is None


@pytest.mark.parametrize('slot,task,closed', [
    (SLOT.replace('v105:', 'v064:'), TASK, True),
    (SLOT.replace('_PROJECT_', '_REF_'), TASK, True),
    (SLOT.replace('202611020116', '202611020117'), TASK, True),
    (SLOT, 'matplotlib__matplotlib-20826', True),
    (SLOT, TASK, False),
])
def test_wrong_scope_or_unclosed_rejected_before_any_candidate_write(tmp_path, slot, task, closed):
    destination = tmp_path / 'must-not-exist'
    prepared = SimpleNamespace(case={'case_id': task})
    with pytest.raises(ValueError):
        closure.export_managed_closure(prepared, destination, slot_id=slot, sdk_closed=closed)
    assert not destination.exists()


def test_fixed_identity_list_exactly_matches_original_prespecified_project_rows():
    root = Path(__file__).resolve().parents[1]
    panel = json.loads((root / 'artifacts/software-benchmark-v105/preparation-r1/panel.json').read_text())
    rows = [row for row in panel['rows'] if row['arm'] == 'PROJECT']
    assert len(rows) == len(closure.TASK_IDS) == 50
    assert tuple(panel['task_ids']) == closure.TASK_IDS
    for row in rows:
        assert closure.validate_slot_identity(row['slot_id'], row['instance_id']) == {
            key: row[key] for key in ('slot_id', 'instance_id', 'condition_id', 'seed')}
