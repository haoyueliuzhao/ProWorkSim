"""Fixed repeated situations and public presentation in the actual collector."""

from proworksim.online_collection import collect_window
from proworksim.online_signals import joint_return
from proworksim.storage import read_json
from test_online_collection_v013 import FakeOwner


def test_repeated_prepared_situation_keeps_one_exact_current_support_block(tmp_path):
    owner = FakeOwner()
    spec = {
        'window_id': owner.window_id, 'template': 'learning_work', 'interface': 'v14',
        'presentation': 'compact_v14', 'external_tick_per_sweep': 1,
        'min_class_count': 2,
        'slots': [{'slot_id': 'review-' + str(i), 'case_id': 'train-v14-f0-review',
                   'sampling_seed': 410 + i} for i in range(4)],
    }
    entries = collect_window(owner, spec, tmp_path / 'collection')
    assert [x['slot_id'] for x in entries] == [x['slot_id'] for x in spec['slots']]
    assert all(x['rollout'] is not None for x in entries)
    declarations = read_json(tmp_path / 'collection/declaration.json')
    assert len({x['xi_fingerprint'] for x in declarations['slots']}) == 1
    assert declarations['gamma_identity']['presentation'] == 'compact_v14'
    support = read_json(tmp_path / 'collection/support.json')
    assert len(support['groups']) == 1
    group = support['groups'][0]
    assert group['closed_joint_M'] == 4
    assert group['support']['blocks']['reviewer']['M'] == 4
    for entry in entries:
        assert entry['reward']['eligible'] is True
        assert entry['reward']['reward'] == 0
        assert entry['rollout']['work_validity']['components']['record']['value'] is True
        value, _ = joint_return(entry['reward'], 0, 'joint_reward_to_go', entry['rollout']['events'])
        assert value == 0
