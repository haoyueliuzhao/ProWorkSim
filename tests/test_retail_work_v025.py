"""Frozen exact situations, held-out usage and same-case methods."""
from proworksim.storage import read_json
from proworksim.templates import retail_collaboration_v025 as world


def test_frozen_16_material_protocol_and_no_historical_entity_overlap():
    catalog = world.registry()
    assert read_json(world.PIN_PATH.parent/'catalog.json') == catalog
    assert len(catalog['all_cases']) == 16
    assert len({c['case_id'] for c in catalog['all_cases']}) == 16
    training = catalog['training_window']
    assert training['window_id'] == 'v025-window-1'
    assert [s['task'] for s in training['slots']] == ['joint_a', 'joint_b']*8
    assert len({s['case_id'] for s in training['slots']}) == 2
    assert len({s['seed'] for s in training['slots']}) == 16
    assert catalog['training_cases'][1]['prepared_submission'] == 'wrong_count'
    assert catalog['training_cases'][1]['prepared_code_variant'] == 'compact-sql-v025-r1'
    for prefix, count, repeats in [('development', 6, 1), ('confirmation', 12, 2), ('continuation', 2, 1)]:
        slots = catalog[prefix+'_slots']
        assert len(slots) == count
        assert all(s['seed'] == s['sampling_seed'] for s in slots)
        assert len({s['repeat_index'] for s in slots}) == repeats
        if prefix != 'continuation':
            assert [s['task'] for s in slots] == ['joint_a','joint_b','maintenance']*(count//3)
            assert [c['maintenance']['expected_result_change'] for c in catalog[prefix+'_cases'][4:]] == [True, False]
    seen = {k: set() for k in ('customers','invoice_ids','source_rows')}
    manifest = read_json(world.PIN_PATH)
    excluded = dict(zip(seen, ['excluded_customers','excluded_invoices','excluded_source_rows']))
    for item in manifest['slices']:
        assert max(item['complete_invoice_rows'].values()) <= 3
        for key in seen:
            values = set(item[key])
            assert not values & (seen[key] | set(manifest[excluded[key]]))
            seen[key].update(values)
    assert all('method' not in c['business_facts'] for c in catalog['all_cases'])
    assert all(c['role_decision_limits'] == {'provider':6,'implementer':16} if c['task']=='joint_a' else c['role_decision_limits']=={'implementer':24,'reviewer':28} for c in catalog['all_cases'])
