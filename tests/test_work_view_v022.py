"""Source and pure-presentation controls; no model, GPU or old E replay."""
import copy
import json

import pytest

from proworksim.storage import digest, json_bytes, read_json
from proworksim.templates import retail_collaboration_v022 as template
from proworksim.work_view_v022 import CompactWorkModelPolicy, OriginalHistoryModelPolicy


def test_new_entities_rows_and_reserved_purposes_are_not_old_facts_renamed():
    pin = read_json(template.PIN_PATH)
    old_c, old_i, old_r = map(set, [pin['excluded_customers'], pin['excluded_invoices'], pin['excluded_source_rows']])
    customers, invoices, rows = set(), set(), set()
    for entry in pin['slices']:
        if not (template.DEFAULT_ASSETS / entry['path']).exists():
            pytest.skip('Pinned original UCI-derived assets are not installed')
        raw = (template.DEFAULT_ASSETS / entry['path']).read_bytes()
        assert digest(raw) == entry['sha256']
        data = json.loads(raw)
        cs, ids, rs = set(data['customers']), set(data['invoice_ids']), {r[-1] for r in data['rows']}
        assert not cs & (old_c | customers) and not ids & (old_i | invoices) and not rs & (old_r | rows)
        assert rs == set(entry['source_rows'])
        assert all(sum(row[0] == invoice for row in data['rows']) == count for invoice, count in entry['complete_invoice_rows'].items())
        customers |= cs
        invoices |= ids
        rows |= rs
    assert (len(customers), len(invoices), len(rows)) == (24, 72, 339)
    catalog = template.registry()
    assert [len(catalog[k]) for k in ('situations', 'reserved_training', 'reserved_bridge')] == [6, 4, 2]
    for key in ('situations', 'reserved_training', 'reserved_bridge'):
        assert all(c['model_training_eligible'] is False and c['source_admission'] is False for c in catalog[key])
    for i in range(6):
        pair = catalog['ordered_slots'][i * 2:i * 2 + 2]
        assert len({p['case_id'] for p in pair}) == len({p['sampling_seed'] for p in pair}) == 1
        assert [p['arm'] for p in pair] == (list(template.ARMS) if i % 2 == 0 else list(reversed(template.ARMS)))
    assert sum(sum(c['role_decision_limits'].values()) for c in catalog['situations']) == 122


def _memory():
    messages = [{'role': 'system', 'content': 'Fixed public protocol'}]
    registrations = []
    def observe():
        index = len(messages)
        messages.append({'role': 'user', 'content': json.dumps({'role_task': 'Review fixed work', 'observation': {'actor_id': 'reviewer', 'projects': {}, 'work_items': {'W': {'goal': 'Review fixed work', 'visible_requirements': ['Review fixed work', 'Keep this separate rule'], 'requirements': {'review_contract': copy.deepcopy(template.REVIEW_CONTRACT)}}}}})})
        registrations.append({'index': index, 'sha256': digest(json_bytes(messages[index]))})
    def tool(index, name, body):
        messages.append({'role': 'assistant', 'content': 'Own repeated explanation ' * 30, 'tool_calls': [{'id': str(index), 'type': 'function', 'function': {'name': name, 'arguments': '{}'}}]})
        messages.append({'role': 'tool', 'tool_call_id': str(index), 'content': json.dumps(body)})
    observe()
    tool(1, 'read_version', {'ok': True, 'result': {'reference': {'object_id': 'visible-data', 'version_id': 'v1'}, 'data': {'public_value': 'OWN_ACTUAL_READ'}}})
    observe()
    tool(2, 'read_version', {'ok': True, 'result': {'reference': {'object_id': 'visible-data', 'version_id': 'v1'}, 'data': {'public_value': 'OWN_ACTUAL_READ'}}})
    tool(3, 'staff_wait', {'status': 'worker_wait', 'world_action_executed': False})
    messages.append({'role': 'assistant', 'content': 'OWN_ACTUAL_TRUNCATED_OUTPUT'})
    messages.append({'role': 'user', 'content': json.dumps({'public_format_feedback': {'world_action_executed': False, 'reason': 'length'}})})
    observe()
    return {'messages': messages, 'observation_messages': registrations, 'rejected_assistant_messages': []}


def test_compact_preserves_exact_own_evidence_controls_and_format_history():
    memory = _memory()
    before = json_bytes(memory)
    config = {'context_policy': 'latest_observation', 'action_protocol': 'native_tools'}
    full, _ = OriginalHistoryModelPolicy(config)._select_messages(memory)
    selected, audit = CompactWorkModelPolicy(config)._select_messages(memory)
    assert json_bytes(memory) == before
    assert len(json_bytes(selected)) < len(json_bytes(full))
    selected_tools = [m for m in selected if m['role'] == 'tool']
    assert all(m in memory['messages'] for m in selected_tools)
    assert {m['tool_call_id'] for m in selected_tools} == {'2', '3'}
    wire = json_bytes(selected).decode()
    assert 'OWN_ACTUAL_READ' in wire and 'OWN_ACTUAL_TRUNCATED_OUTPUT' in wire
    assert 'public_format_feedback' in wire and 'worker_wait' in wire
    assert 'Keep this separate rule' in wire
    assert 'UNREAD_OTHER_ROLE_SECRET' not in wire
    current = json.loads(selected[-1]['content'])['observation']['work_items']['W']['requirements']['review_contract']
    assert current == template.REVIEW_CONTRACT
    assert audit['preserved_tool_result_indices']


def test_compact_rejects_unbound_tool_message_and_public_contract_is_specific():
    memory = _memory()
    memory['messages'].insert(0, {'role': 'tool', 'tool_call_id': 'other-role-call', 'content': '{}'})
    with pytest.raises(ValueError):
        CompactWorkModelPolicy({'context_policy': 'latest_observation'})._select_messages(memory)
    contract = template.REVIEW_CONTRACT
    assert 'MUST' in contract['target'] and 'result' in contract['target']
    assert contract['row_locator'] == '["tables", "metrics", "rows", i]'
    assert contract['cell_locator'] == '["tables", "metrics", "rows", i, j]'
    assert 'zero-based' in contract['indices'] and 'BOTH' in contract['evidence']
    assert '<fixed_result_object_id>' == contract['example']['object_id']
