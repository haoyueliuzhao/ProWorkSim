"""Frozen usage and narrowly authorized maintenance tool contracts."""
import copy

import pytest

from proworksim.storage import read_json
from proworksim.templates import retail_collaboration_v023 as world
from proworksim.work_interface import (
    V14_INTERFACE, V23_MAINTENANCE_INTERFACE, tool_definitions, validate_call,
)


def test_frozen_entity_partition_quality_order_and_exact_repeats():
    catalog = world.registry()
    assert read_json(world.PIN_PATH.parent / 'catalog.json') == catalog
    manifest = read_json(world.PIN_PATH)
    assert len(catalog['evaluation_cases']) == 12
    assert len(catalog['evaluation_slots']) == 24
    assert len(catalog['training_cases']) == 16
    seen = {key: set() for key in ('customers', 'invoice_ids', 'source_rows')}
    exclusions = {'customers': 'excluded_customers', 'invoice_ids': 'excluded_invoices', 'source_rows': 'excluded_source_rows'}
    for entry in manifest['slices']:
        for key in seen:
            values = set(entry[key])
            assert not values & seen[key]
            assert not values & set(manifest[exclusions[key]])
            seen[key].update(values)
        assert max(entry['complete_invoice_rows'].values()) <= 3
    for window in catalog['training_windows']:
        slots = window['slots']
        assert [s['task'] for s in slots] == ['joint_a', 'joint_b', 'implement', 'review', 'joint_a', 'joint_b']
        assert slots[0]['case_id'] == slots[4]['case_id']
        assert slots[1]['case_id'] == slots[5]['case_id']
        assert len({s['seed'] for s in slots}) == 6
        assert all(world.case_spec(s['case_id'])['window_index'] == window['window_index'] for s in slots)
    assert [c['prepared_submission'] for c in catalog['evaluation_cases'][4:8]] == ['correct', 'wrong_count', 'wrong_amount', 'correct']
    assert [c['maintenance']['expected_result_change'] for c in catalog['evaluation_cases'][8:]] == [True, True, False, False]


def test_maintenance_version_update_tool_is_explicit_and_only_implementer():
    # Full current WorkInterface/WorldCore execution is in the archived CPU
    # witness. Here pin the exact tool/profile authorization boundary.
    core = [{'name': 'adopt_version', 'description': 'core operation', 'parameters': {
        'type': 'object', 'properties': {'alias': {'type': 'string'}, 'version_id': {'type': 'string'}, 'work_id': {'type': 'string'}},
        'required': ['alias', 'version_id'], 'additionalProperties': False}}]
    assert tool_definitions(core, V14_INTERFACE + ':implementer') == []
    assert tool_definitions(core, V23_MAINTENANCE_INTERFACE + ':reviewer') == []
    definition = tool_definitions(core, V23_MAINTENANCE_INTERFACE + ':implementer')[0]
    assert 'work_id' in definition['parameters']['required']
    with pytest.raises(ValueError):
        validate_call(core, V23_MAINTENANCE_INTERFACE + ':implementer', 'adopt_version', {'alias': 'basis', 'version_id': 'v2'})
    original = copy.deepcopy(core)
    validate_call(core, V23_MAINTENANCE_INTERFACE + ':implementer', 'adopt_version', {'alias': 'basis', 'version_id': 'v2', 'work_id': world.WORK})
    assert core == original
