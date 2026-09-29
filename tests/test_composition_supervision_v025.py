"""Conditional branch and missing-evidence controls; no model or world replay."""
import copy
import json

import pytest

from proworksim.storage import digest
from scripts.composition_evidence_v025 import checked, maybe_decide, paired_evaluations
from scripts.evaluate_work_v022 import reference, write
from scripts.report_composition_v025 import report
from scripts.run_composition_v025 import ORDER, dependency


def test_no_support_skips_identical_branches_but_keeps_base_and_continuation(tmp_path):
    source = {'fixture': 'no model, no claimed work result'}
    support = {'selected_block': None, 'supports_by_xi': {}}
    write(tmp_path / 'support.json', support)
    write(tmp_path / 'support-complete.json', {'selected_block': None, 'source': source,
        'support': reference(tmp_path / 'support.json')})
    states = {stage: {'status': 'waiting'} for stage in ORDER}
    states['support']['status'] = 'complete'
    decision = maybe_decide(tmp_path, {'composition': {'fixture': True}}, states, source)
    assert decision['changed'] is False and decision['contribution_estimate'] is None
    assert decision['confirmation_outcomes_used'] is False
    assert dependency('train_base', tmp_path, states) == 'ready'
    for stage in ('train_probe', 'dev_base', 'dev_probe', 'train_configured', 'confirm_configured', 'next_configured'):
        assert dependency(stage, tmp_path, states) == 'not_required'
    assert dependency('confirm_base', tmp_path, states) == 'waiting'
    states['train_base']['status'] = 'complete'
    assert dependency('confirm_base', tmp_path, states) == 'ready'
    assert dependency('next_base', tmp_path, states) == 'waiting'
    states['confirm_base']['status'] = 'complete'
    assert dependency('next_base', tmp_path, states) == 'ready'
    states['support']['status'] = 'stopped'
    assert dependency('train_base', tmp_path, states) == 'unavailable_endpoint'


def test_confirmation_waits_for_development_decision_and_unknown_is_not_zero(tmp_path):
    write(tmp_path / 'support-complete.json', {'selected_block': {'task': 'joint_a'}})
    states = {stage: {'status': 'waiting'} for stage in ORDER}
    states['support']['status'] = states['train_base']['status'] = 'complete'
    assert dependency('confirm_base', tmp_path, states) == 'waiting'
    write(tmp_path / 'configuration-decision.json', {'changed': False, 'development_complete': False})
    assert dependency('confirm_base', tmp_path, states) == 'ready'
    assert dependency('train_configured', tmp_path, states) == 'not_required'
    def value(known, full):
        return {'rows': [{'slot_id': 'one', 'case_id': 'case', 'task': 'joint_a', 'seed': 1,
            'initial_business_state_sha256': 'same' if known else None,
            'outcome': {'known': known, 'value': full}}]}
    result = paired_evaluations(value(True, True), value(False, None))
    assert result['overall']['mean_difference'] is None
    assert result['overall']['full_denominator_compatible_bounds'] == [-1., 0.]
    changed = value(True, False)
    changed['rows'][0]['initial_business_state_sha256'] = 'different'
    with pytest.raises(ValueError, match='canonical'):
        paired_evaluations(value(True, True), changed)


def test_checkpoint_reference_preserves_optional_bytes_and_stopped_cost_report(tmp_path):
    blob = tmp_path / 'checkpoint-state'
    blob.write_bytes(b'CPU reference fixture')
    ref = {'path': str(blob), 'sha256': digest(blob.read_bytes()), 'bytes': blob.stat().st_size}
    assert checked(ref) == blob
    wrong = copy.deepcopy(ref)
    wrong['bytes'] += 1
    with pytest.raises(ValueError):
        checked(wrong)
    def slots(count):
        return [{'slot_id': str(i), 'case_id': 'case-'+str(i), 'task': ('joint_a','joint_b','maintenance')[i%3],
                 'seed': i+1} for i in range(count)]
    catalog = {'development_slots': slots(6), 'confirmation_slots': slots(12)}
    write(tmp_path / 'catalog.json', catalog)
    plan = {'catalog': reference(tmp_path / 'catalog.json'), 'source_pin': {'fixture': True}, 'internal_gpu_seconds': 58*3600}
    write(tmp_path / 'plan.json', plan)
    root = tmp_path / 'run'
    root.mkdir()
    write(root / 'supervisor.json', {'source': {'fixture': True}, 'plan': reference(tmp_path / 'plan.json'),
        'started_at': 0., 'ended_at': 45., 'status': 'closed_with_incomplete_stages'})
    for stage in ORDER:
        state = {'status': 'stopped' if stage == 'support' else 'not_started_endpoint_unavailable', 'ended_at': 45.}
        if stage == 'support':
            state.update(started_at=0., exit_code=1, elapsed_gpu_seconds=45.)
        write(root / stage / 'state.json', state)
    write(root / 'support/actual/resident/calls/fixture.json', {
        'status': 400, 'online_window_id': 'CPU-only', 'raw_output_ids': [],
        'response': {'error': {'code': 'context_length_exceeded'}}})
    result = report(root)
    assert result['stages']['support']['resident_calls']['observed_totals']['local_context_400'] == 1
    assert result['report_kind'] == 'closed_incomplete'
    assert result['planned_primary_composition_difference'] is None
    assert result['accounting']['final_gpu_seconds'] == 45.
    assert result['closed_new_episodes_total'] == 0
    raw = json.loads((root / 'supervisor.json').read_text())
    raw.pop('ended_at')
    raw['status']='running'
    write(root / 'supervisor.json',raw)
    assert report(root)['report_kind'] == 'snapshot'
