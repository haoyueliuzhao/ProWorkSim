"""Read-only arithmetic, provenance and stopped-run reporting controls."""
import copy
import json
from pathlib import Path

import pytest

from proworksim.storage import json_bytes
from scripts.report_credit_v024 import (
    STAGES, compare_prepared, ledger_rows, markdown, pair_evaluations, summarize,
)
from scripts.report_domain_v022 import reference

CATALOG = Path('examples/retail-collaboration-v24/catalog.json')


def row(slot, value, *, actor='actor'):
    return {**slot, 'status': 'closed', 'actor_identity': actor,
            'initial_business_state_sha256': 'initial-' + slot['case_id'],
            'assessment': {'eligible': True, 'independent_assessability': 'known',
                           'completed': value, 'work_components': {'full_responsibility': value}},
            'evaluation_guard': {'learning_unchanged': True, 'rng_restored_exactly': True}}


def test_missing_endpoints_tighten_bounds_and_invalid_identity_remains_unknown():
    catalog = json.loads(CATALOG.read_text())
    slots = catalog['evaluation_slots']
    before = [row(slot, False) for slot in slots[:7]]
    after = [row(slot, False) for slot in slots]
    before[0]['assessment'].update(completed=True, work_components={'full_responsibility': True})
    result = pair_evaluations(catalog, before, after, left_label='mc', right_label='rtg', left_actor='actor', right_actor='actor')
    assert result['overall']['known_pairs'] == 7
    assert result['overall']['mean_difference'] is None
    assert result['overall']['full_denominator_compatible_bounds'] == [-6/12, -1/12]
    bad = copy.deepcopy(after)
    bad[0]['actor_identity'] = 'another-checkpoint'
    changed = pair_evaluations(catalog, before, bad, left_label='mc', right_label='rtg', left_actor='actor', right_actor='actor')
    assert changed['pairs'][0]['right']['value'] is None
    bad[0]['initial_business_state_sha256'] = 'changed-business'
    with pytest.raises(ValueError, match='business state'):
        pair_evaluations(catalog, before, bad, left_label='mc', right_label='rtg', left_actor='actor', right_actor='actor')


def test_actual_common_admission_must_keep_tokens_masks_and_denominators():
    base = {'window_id': 'common', 'slot_count': 6, 'decisions': [{'slot_id': 's', 'member_id': 'm',
            'call_id': 'c', 'tokens': {'output_ids': [1, 2], 'mask': [1, 1]},
            'actor_denominator': 12, 'reward': .2, 'credit': {'mode': 'terminal_mc'}}]}
    rtg = copy.deepcopy(base)
    rtg['decisions'][0].update(reward=0, credit={'mode': 'joint_reward_to_go'})
    result = compare_prepared(base, rtg)
    assert result['only_target_and_credit_differ']
    assert result['target_changes'][0]['mc'] == .2 and result['target_changes'][0]['handoff_rtg'] == 0
    rtg['decisions'][0]['tokens']['mask'][0] = 0
    assert compare_prepared(base, rtg)['only_target_and_credit_differ'] is False
    assert compare_prepared(base, None)['only_target_and_credit_differ'] is None


def test_ledger_keeps_negative_reconciliation_and_detects_bad_conservation():
    reward = {'reward': 0, 'episode_id': 'episode', 'manifest_sha256': 'sha',
              'ledger': {'total': 0, 'terminal_sequence': 10, 'events': [
                  {'amount': .2, 'sequence': 5, 'settlement': 'event'},
                  {'amount': -.2, 'sequence': 10, 'settlement': 'terminal'}]}}
    entry = {'slot_id': 'slot', 'reward': reward,
             'rollout': {'reward_eligibility': copy.deepcopy(reward), 'events': [{'sequence': 5}, {'sequence': 10}]}}
    result = ledger_rows([entry])[0]
    assert result['conserved_and_located'] and result['negative_terminal_correction']
    entry['reward']['ledger']['events'][-1]['amount'] = 0
    assert not ledger_rows([entry])[0]['conserved_and_located']


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def test_ended_failed_protocol_is_closed_incomplete_and_counts_failure_cost(tmp_path):
    catalog = json.loads(CATALOG.read_text())
    root = tmp_path / 'run'
    plan_path, catalog_path = tmp_path / 'plan.json', tmp_path / 'catalog.json'
    put(catalog_path, catalog)
    put(plan_path, {'catalog': reference(catalog_path), 'internal_gpu_seconds': 129600, 'external_gpu_seconds': 0})
    source = {'code_commit': 'fixture', 'source_tree_sha256': 'fixture-source', 'code_dirty': False}
    put(root / 'supervisor.json', {'source': source, 'plan': reference(plan_path), 'status': 'closed_with_incomplete_stages', 'ended_at': 99})
    for stage in STAGES:
        state = {'attempted': False, 'status': 'not_started_endpoint_unavailable', 'ended_at': 99}
        if stage == 'eval_initial':
            state = {'attempted': True, 'status': 'stopped', 'started_at': 1, 'ended_at': 46,
                     'exit_code': -15, 'elapsed_gpu_seconds': 45}
        put(root / stage / 'state.json', state)
    report = summarize(root)
    assert report['execution_terminal'] and report['report_kind'] == 'closed_incomplete'
    assert not report['protocol_complete'] and report['planned_primary_credit_difference'] is None
    assert report['accounting']['final_gpu_seconds'] == 45
    assert report['training']['actual_new_training_episodes_closed'] == 0
    assert report['training']['actual_episode_consumptions_started'] == 0
    assert report['training']['actual_D0_prepared_comparison']['only_target_and_credit_differ'] is None
    assert 'closed_incomplete' in markdown(report)
    # An observer that has not closed cannot issue final status merely because
    # child files currently look stopped.
    current = json.loads((root / 'supervisor.json').read_text())
    current.update(status='running', ended_at=None)
    put(root / 'supervisor.json', current)
    assert summarize(root)['report_kind'] == 'snapshot'
