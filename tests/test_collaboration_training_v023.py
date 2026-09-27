"""New six-slot contracts using explicit CPU token fixtures, never model work data."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.collaboration_training_v023 import (
    training_admission, validate_window_declaration,
)
from proworksim.online_training import prepare_window, recipe_config
from proworksim.storage import json_bytes, read_json
from proworksim.templates import retail_collaboration_v023 as world
from proworksim.work_learning_diagnostics_v023 import summarize_work_signals
from scripts.learning_pilot_v023 import collect_window
from test_collaboration_training_v022 import ExplicitSyntheticTokenTransport


@pytest.fixture(scope='module')
def projected_window(tmp_path_factory):
    if not world.PIN_PATH.exists() or not (world.DEFAULT_ASSETS / 'manifest.json').exists():
        pytest.skip('Pinned new v023 source materials are required; no synthetic source fallback')
    root = tmp_path_factory.mktemp('v023-six-slot-projection')
    catalog = world.registry()
    spec = catalog['training_windows'][0]
    class FixtureOwner(ExplicitSyntheticTokenTransport):
        recipe = recipe_config({'max_length': 16384, 'max_output_tokens': 2048,
                                'post_update_max_decisions': 6})

        def begin_window(self, window_id):
            self.window_id = window_id
            self.seeds = []
            return self.freeze_identity()

        def reseed(self, seed, *, label):
            self.seeds.append((seed, label))
            slot = next(s for s in spec['slots'] if s['slot_id'] == label)
            self.task, self.counters = slot['task'], {}

    owner = FixtureOwner()
    admission = training_admission(catalog, world.PIN_PATH)
    entries, progress = collect_window(owner, catalog, spec, admission, root, world.DEFAULT_ASSETS)
    proofs = [read_json(root / slot['slot_id'] / 'projection.json') for slot in spec['slots']]
    declaration = read_json(root / 'declaration.json')
    assert owner.seeds == [(slot['sampling_seed'], slot['slot_id']) for slot in spec['slots']]
    assert all(row['status'] == 'closed' for row in progress)
    return SimpleNamespace(root=root, owner=owner, entries=entries, proofs=proofs,
                           admission=admission, declaration=declaration)


def test_new_six_slot_denominator_keeps_actual_repetitions_and_missing_slot(projected_window):
    f = projected_window
    prepared = prepare_window(f.entries, f.owner.freeze_identity(), f.owner.window_id, f.owner.recipe)
    assert len(prepared['slots']) == prepared['slot_count'] == 6
    assert all(p['has_complete_trainable_actual_members'] for p in f.proofs)
    assert [e['reward']['scope'] for e in f.entries] == ['joint_a', 'joint_b', 'implement', 'review', 'joint_a', 'joint_b']
    assert len({e['rollout']['rollout_id'] for e in f.entries}) == 6
    assert f.entries[0]['rollout']['window']['xi_id'] == f.entries[4]['rollout']['window']['xi_id']
    assert f.entries[1]['rollout']['window']['xi_id'] == f.entries[5]['rollout']['window']['xi_id']
    for row in prepared['decisions']:
        index = [e['slot_id'] for e in f.entries].index(row['slot_id'])
        view = f.proofs[index]['member_views'][row['member_id']]
        assert row['actor_denominator'] == 6 * len(f.entries[index]['active_members']) * view['own_action_tokens']
        assert row['critic_denominator'] == 6 * len(f.entries[index]['active_members']) * len(view['decisions'])
    missing = copy.deepcopy(f.entries)
    missing[-1]['rollout'] = missing[-1]['reward'] = None
    partial = prepare_window(missing, f.owner.freeze_identity(), f.owner.window_id, f.owner.recipe)
    assert partial['slot_count'] == 6
    assert partial['slots'][-1]['exclusions'] == ['episode_or_reward_record_missing']
    original = {r['call_id']: r['actor_denominator'] for r in prepared['decisions']}
    assert all(r['actor_denominator'] == original[r['call_id']] for r in partial['decisions'])
    shortened = copy.deepcopy(f.declaration)
    shortened['slots'].pop()
    with pytest.raises(ValueError, match='six-slot'):
        validate_window_declaration(shortened, f.admission)
    replaced = copy.deepcopy(f.declaration)
    replaced['slots'][0]['xi_id'] = world.registry()['evaluation_cases'][0]['case_id']
    with pytest.raises(ValueError, match='order/cases'):
        validate_window_declaration(replaced, f.admission)

    shortened_roles = copy.deepcopy(f.declaration)
    shortened_roles['slots'][3]['policies']['reviewer']['config']['budget']['max_decisions'] = 4
    with pytest.raises(ValueError, match='Full responsibility'):
        validate_window_declaration(shortened_roles, f.admission)


def test_work_diagnostics_preserve_components_and_signed_actual_actions(projected_window, tmp_path):
    f = projected_window
    admitted = prepare_window(f.entries, f.owner.freeze_identity(), f.owner.window_id, f.owner.recipe)
    advantages = [(.2, -.1, 0)[i % 3] for i, _ in enumerate(admitted['decisions'])]
    values = [row['reward'] - a for row, a in zip(admitted['decisions'], advantages)]
    (tmp_path / 'admission.json').write_bytes(json_bytes(admitted))
    (tmp_path / 'report.json').write_bytes(json_bytes({'status': 'explicit_CPU_numeric_fixture',
        'old_critic_values': values, 'advantages': advantages,
        'actor_optimizer_steps': 0, 'critic_optimizer_steps': 0}))
    result = summarize_work_signals(f.entries, tmp_path)
    assert all(result['advantages'][k] for k in ('positive', 'negative', 'zero'))
    assert result['advantages']['unknown'] == 0
    assert result['extra_model_calls'] == result['extra_actor_forwards'] == 0
    assert sum(g['decisions'] for g in result['groups']) == len(admitted['decisions'])
    assert any('basis_delivery' in d['realized_action_stages'] for d in result['decisions'])
    assert all(d['reward_components'] == f.entries[[e['slot_id'] for e in f.entries].index(d['slot_id'])]['reward']['components']
               for d in result['decisions'])
    (tmp_path / 'report.json').write_bytes(json_bytes({'status': 'zero_step_probability_mismatch'}))
    unavailable = summarize_work_signals(f.entries, tmp_path)
    assert unavailable['status'] == 'advantages_unavailable'
    assert unavailable['advantages']['unknown'] == len(admitted['decisions'])
    assert unavailable['advantages']['zero'] == 0
    assert read_json(tmp_path / 'work-signal-diagnostics.json')['update_status'] == 'zero_step_probability_mismatch'
