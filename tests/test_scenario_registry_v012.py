"""Source and layout derivatives cannot masquerade as independent tests."""
import copy

import pytest

from proworksim.scenario_registry import validate_registry
from proworksim.storage import digest


def registry(tmp_path):
    (tmp_path / 'scenario.json').write_text('{}')
    row = dict(scenario_id='a', source_cluster_id='upstream', world_family_id='family',
               base_project_id='base-a', information_layout_id='holder-one', split='development',
               generator_version='g1', validator_version='v1', template_family_id='t1',
               scenario_file='scenario.json', scenario_sha256=digest(b'{}'))
    return {'version': 'situation-registry-v0.12', 'sources': {'upstream': {'kind': 'fictional_public'}},
            'situations': [row]}


def test_layout_repeat_is_one_source_family(tmp_path):
    data = registry(tmp_path)
    row = {**data['situations'][0], 'scenario_id': 'b', 'information_layout_id': 'holder-two'}
    data['situations'].append(row)
    result = validate_registry(data, root=tmp_path)
    assert (result['sources'], result['world_families'], result['exact_situations']) == (1, 1, 2)


@pytest.mark.parametrize('change', ['same_source', 'same_family'])
def test_cross_split_derivatives_rejected(tmp_path, change):
    data = registry(tmp_path)
    row = copy.deepcopy(data['situations'][0])
    row.update(scenario_id='b', split='independent_test')
    row['world_family_id' if change == 'same_source' else 'source_cluster_id'] = 'other'
    data['sources']['other'] = {}
    data['situations'].append(row)
    with pytest.raises(ValueError, match='cannot cross'):
        validate_registry(data, root=tmp_path)


def test_changed_file_does_not_keep_frozen_identity(tmp_path):
    data = registry(tmp_path)
    (tmp_path / 'scenario.json').write_text('{"changed":true}')
    with pytest.raises(ValueError, match='differs'):
        validate_registry(data, root=tmp_path)
