import copy

import pytest

from proworksim import software_benchmark_api_scope_v094 as scope
from proworksim.software_benchmark_candidates_v054 import reference


def test_only_two_created_zero_model_environments_get_new_physical_ids():
    inventory = scope.load(reference(scope.INVENTORY_FILE))
    plan = scope.load(reference(scope.PLAN_FILE))
    audit = scope.load(scope.require_physical_audit())
    prior = {row['slot_id']: row for row in scope.load(audit['prior_physical_inventory'])['rows']}
    assert scope.validate_complete_plan(plan, inventory) is plan
    changed, preserved = [], []
    canonical = {row['slot_id']: row for row in scope.canonical_rows()}
    for row in plan['rows']:
        before = prior[row['slot_id']]
        old = canonical[row['slot_id']]
        scope.validate_physical_mapping(row, old, scope.load(row['configuration']), scope.load(old['configuration']))
        if row != before:
            changed.append((before['slot_index'], row['slot_index']))
            assert row['physical_launch_attempt'] == 3
            assert scope.load(row['configuration']) == {**scope.load(before['configuration']),
                                                       'slot_index': row['slot_index']}
        else:
            preserved.append(row['slot_index'])
    assert sorted(changed) == [(6044, 6088), (6045, 6089)]
    assert sorted(preserved) == list(range(6046, 6088))
    assert plan['previous_created_containers'] == 4
    assert plan['previous_created_named_volumes'] == 2
    assert plan['cumulative_container_upper_bound'] == 159
    assert plan['cumulative_named_volume_upper_bound'] == 46


def test_mixed_mapping_cannot_hide_previous_Docker_cost_or_reconsume_failed_ID():
    plan = scope.load(reference(scope.PLAN_FILE))
    inventory = scope.load(reference(scope.INVENTORY_FILE))
    wrong = copy.deepcopy(plan)
    wrong['previous_created_containers'] = 0
    with pytest.raises(PermissionError):
        scope.validate_complete_plan(wrong, inventory)
    row = next(row for row in plan['rows'] if row['slot_index'] == 6088)
    original = next(old for old in scope.canonical_rows() if old['slot_id'] == row['slot_id'])
    wrong_row = {**row, 'slot_index': 6044}
    with pytest.raises(PermissionError):
        scope.validate_physical_mapping(wrong_row, original, scope.load(row['configuration']),
                                        scope.load(original['configuration']))
