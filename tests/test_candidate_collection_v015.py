"""Actual new-source collector binding, without model or reward substitution."""

from pathlib import Path

import pytest

from proworksim.online_collection import collect_window
from proworksim.online_signals import joint_return
from proworksim.storage import read_json
from proworksim.templates.retail_work import assets_root
from test_online_collection_v013 import FakeOwner


def test_real_retail_pair_repetitions_keep_exact_current_xi_and_reward_contract(tmp_path):
    if not (Path(assets_root()) / 'manifest.json').is_file():
        pytest.skip('Real-source asset integration requires the pinned UCI asset package')
    owner = FakeOwner()
    spec = {'window_id': owner.window_id, 'template': 'retail_work', 'interface': 'v14',
            'presentation': 'compact_v14', 'external_tick_per_sweep': 1, 'min_class_count': 2,
            'slots': [{'slot_id': 'pair-' + str(i), 'case_id': 'uci-train-f0-pair', 'sampling_seed': 410 + i} for i in range(4)]}
    entries = collect_window(owner, spec, tmp_path / 'collection')
    assert len(entries) == 4
    declaration = read_json(tmp_path / 'collection/declaration.json')
    assert len({s['xi_fingerprint'] for s in declaration['slots']}) == 1
    groups = read_json(tmp_path / 'collection/support.json')['groups']
    assert len(groups) == 1
    assert groups[0]['closed_joint_M'] == 4
    assert set(groups[0]['support']['blocks']) == {'provider', 'implementer'}
    for entry in entries:
        assert entry['reward']['version'] == 'retail-work-reward-v0.15'
        assert entry['reward']['eligible'] and entry['reward']['reward'] == 0
        assert entry['rollout']['work_validity']['components']['record']['value'] is True
        assert joint_return(entry['reward'], 0, 'joint_reward_to_go', entry['rollout']['events'])[0] == 0
