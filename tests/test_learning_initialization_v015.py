import copy

import pytest

from scripts.learning_initialization_v015 import FIELDS, compare_initializations


def test_pair_requires_real_equal_components_and_only_credit_differs():
    common = {'learning_sha256': {key: 'a'*64 for key in FIELDS}, 'rng_sha256': 'b'*64,
              'actor_identity': {'policy': 'initial'}, 'base_identity': {'sha': 'registered'},
              'inference_profile': {'dtype': 'float32'}, 'recipe_except_credit': {'seed': 2026092929}}
    mc = {'participant': 'mc', 'credit_assignment': 'terminal_mc', 'common': common}
    rtg = {'participant': 'rtg', 'credit_assignment': 'joint_reward_to_go', 'common': copy.deepcopy(common)}
    assert compare_initializations(mc, rtg)['passed']
    for component in FIELDS:
        bad = copy.deepcopy(rtg)
        bad['common']['learning_sha256'][component] = 'c'*64
        with pytest.raises(ValueError, match='same actual'):
            compare_initializations(mc, bad)
    bad = copy.deepcopy(rtg)
    bad['common']['rng_sha256'] = 'c'*64
    with pytest.raises(ValueError, match='same actual'):
        compare_initializations(mc, bad)
    bad['common'] = {'learning_sha256': {}, 'rng_sha256': None}
    with pytest.raises(ValueError, match='fingerprints'):
        compare_initializations(mc, bad)


def test_actual_cpu_owner_components_are_measured_without_an_update(tmp_path):
    torch = pytest.importorskip('torch')
    from scripts.learning_initialization_v015 import actual_initial_state
    from test_online_training_v13 import _owner
    records = []
    owners = []
    for condition, credit in [('mc', 'terminal_mc'), ('rtg', 'joint_reward_to_go')]:
        torch.manual_seed(2026092929)
        owner = _owner(tmp_path, torch, name=condition)
        owner.recipe['credit_assignment'] = credit
        common, actual_credit = actual_initial_state(owner)
        records.append({'participant': condition, 'credit_assignment': actual_credit, 'common': common})
        owners.append(owner)
    assert compare_initializations(*records)['passed']
    with torch.no_grad():
        next(owners[-1].critic.parameters()).add_(1)
    records[-1]['common'], _ = actual_initial_state(owners[-1])
    with pytest.raises(ValueError, match='same actual'):
        compare_initializations(*records)
    assert all(owner.actor_steps == owner.critic_steps == 0 for owner in owners)
