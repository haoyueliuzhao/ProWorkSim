"""Selector and actual tiny-CPU update plumbing, not a renewed model qualification."""
import copy

import pytest

from proworksim.storage import read_json
from proworksim.work_learning_diagnostics_v023 import POST_UPDATE_PAIRS, select_post_update_rows


def test_fixed_pair_selector_cannot_fill_missing_pair_with_stages_or_outcomes():
    rows = [{'task': task, 'member_id': member, 'reward': -.5, 'stage': {'label': 'before'}}
            for task, member in reversed(POST_UPDATE_PAIRS)]
    rows.insert(0, {**rows[4], 'reward': 1000, 'stage': {'label': 'after'}})
    chosen = select_post_update_rows(rows, 6)
    assert len(chosen) == 6
    assert [(rows[i]['task'], rows[i]['member_id']) for i in chosen] == list(POST_UPDATE_PAIRS)
    changed = copy.deepcopy(rows)
    for row in changed:
        row['reward'], row['stage'] = -999, {'label': 'any'}
    assert select_post_update_rows(changed, 6) == chosen
    no_a = [r for r in rows if r['task'] != 'joint_a']
    assert select_post_update_rows(no_a, 2) == []
    assert len(select_post_update_rows(no_a, 6)) == 4
    with pytest.raises(ValueError, match='at most six'):
        select_post_update_rows(rows, 7)


def test_injected_selector_is_frozen_before_step_and_post_change_is_not_gate(tmp_path):
    torch = pytest.importorskip('torch')
    from test_online_training_v13 import _features, _owner, _sample_entry

    owner = _owner(tmp_path, torch)
    owner.recipe['post_update_max_decisions'] = 6
    # Explicit tiny-CPU stress fixture: make post-change exceed the old numerical
    # gate to verify that learned change is not treated as same-parameter error.
    owner.actor_optimizer.param_groups[0]['lr'] = .1
    owner.begin_window('fixture-six-pair-selector')
    entry = _sample_entry(owner, reward=1.0)
    entry['reward']['scope'] = 'joint_a'
    observations = []

    def select_before_step(rows, maximum):
        observations.append((owner.actor_steps, owner.critic_steps))
        return select_post_update_rows(rows, maximum)

    report = owner.update_window([entry], tmp_path / 'update', feature_function=_features,
                                 post_update_selector=select_before_step)
    assert observations == [(0, 0)]
    assert report['status'] == 'updated'
    assert report['actor_optimizer_steps'] == report['critic_optimizer_steps'] == 1
    assert report['post_update_additional_actor_forwards'] == 1
    post = read_json(tmp_path / 'update/post-update-sampled-policy.json')
    assert post['selection']['frozen_before_optimizer_step'] is True
    assert post['same_parameter_probability_gate'] is False
    assert post['decisions'][0]['mean_abs_logprob_delta'] > owner.recipe['logprob_max_atol']
    assert report['behavior_probability_passed'] is True
