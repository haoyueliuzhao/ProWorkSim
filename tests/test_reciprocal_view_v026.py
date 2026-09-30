"""The new carrier view only factors exact duplicate public contracts."""

import copy
import json

import pytest

from proworksim.deterministic_work_v024 import DeterministicCompactWorkModelPolicy
from proworksim.reciprocal_runtime_v026 import ReciprocalCompactPolicy


def _body():
    task = 'Read your private demand, use exact references, and preserve GBP/pence distinctions.'
    goal = 'Both members produce and verify real products.'
    scope = {'preparation_credit': False, 'terms': [{'term_id': 'work', 'weight': 1.0}]}
    public_format = {'source': 'Use actual data.', 'review': 'Inspect exact fixed output.'}
    works = {}
    for role, aliases in [('maintainer', ['raw', 'demand', 'source_contract']), ('consumer', ['m_result', 'demand'])]:
        works[role] = {'goal': goal, 'owner_role': role,
                       'visible_requirements': [task] if role == 'consumer' else ['Maintain and inspect.'],
                       'requirements': {'online_scope': copy.deepcopy(scope), 'public_format': copy.deepcopy(public_format),
                                        'source_aliases': aliases, 'private_fact_already_visible': {'unit': 'GBP' if role == 'maintainer' else 'pence'}}}
    return {'role_task': task, 'observation': {'work_items': works,
                                              'messages': [{'sender': 'maintainer', 'body': 'The unit is GBP.'}],
                                              'private_input': {'selected_unit': 'GBP', 'invoice_mode': 'net_signed'}},
            'own_action_history': [{'tool': 'read_alias', 'argument_scope': {'alias': 'demand'}, 'ok': True,
                                    'arguments_sha256': 'args-digest', 'response_sha256': 'response-digest',
                                    'original_message_index': 3, 'control_status': None,
                                    'reference': {'object_id': 'demand-object', 'version_id': 'v1'}, 'submission_id': None},
                                   {'tool': 'inspect_submission', 'ok': False, 'argument_scope': {'submission_id': 'submission-3'},
                                    'control_status': 'actual_failure', 'reference': None, 'submission_id': 'submission-3'}]}


def _project(monkeypatch, body):
    tool = {'role': 'tool', 'tool_call_id': 'actual-id', 'content': '{\n  "ok": true, "result": {"unit": "GBP", "private_value": 100}\n}', 'extra': {'unchanged': True}}
    messages = [{'role': 'system', 'content': 'Actual fixed system task.'},
                {'role': 'user', 'content': json.dumps(body, ensure_ascii=False)},
                {'role': 'assistant', 'content': 'Actual assistant prose retained by parent.',
                 'tool_calls': [{'id': 'actual-id', 'function': {'name': 'read_alias', 'arguments': '{"alias":"demand"}'}}]}, tool,
                {'role': 'user', 'content': '{"public_format_feedback":{"actual":"message"}}'}]
    memory = {'selected': messages, 'unselected': {'private_original': 'not changed'}}
    original = copy.deepcopy(memory)
    inherited = {'version': 'parent-selection', 'audit_field': ['kept']}

    def parent_selection(self, value):
        assert value is memory
        return value['selected'], inherited

    monkeypatch.setattr(DeterministicCompactWorkModelPolicy, '_select_messages', parent_selection)
    policy = object.__new__(ReciprocalCompactPolicy)
    selected, audit = policy._select_messages(memory)
    assert memory == original
    assert selected[0] == original['selected'][0]
    assert selected[2:] == original['selected'][2:]
    assert selected[3]['content'].encode() == tool['content'].encode()
    assert audit['parent_selection'] == inherited
    assert audit['all_selected_tool_messages_unchanged'] is True
    return json.loads(selected[1]['content']), audit


def _restore_contracts(projected):
    result = copy.deepcopy(projected)
    obs = result['observation']
    shared = obs.pop('shared_work_contract', {})
    for work in obs['work_items'].values():
        if 'goal_reference' in work:
            assert work.pop('goal_reference') == 'observation.shared_work_contract.goal'
            work['goal'] = copy.deepcopy(shared['goal'])
        for field in ('online_scope', 'public_format'):
            req = work['requirements']
            key = field + '_reference'
            if key in req:
                assert req.pop(key) == 'observation.shared_work_contract.' + field
                req[field] = copy.deepcopy(shared[field])
        if 'visible_requirements_reference' in work:
            assert work.pop('visible_requirements_reference') == 'role_task'
            work['visible_requirements'] = [result['role_task']]
    return result


def test_duplicate_contracts_restore_exactly_without_mutating_inputs_or_tool_bytes(monkeypatch):
    body = _body()
    selected, audit = _project(monkeypatch, body)
    restored = _restore_contracts(selected)
    assert restored['observation'] == body['observation']
    assert restored['role_task'] == body['role_task']
    assert audit['changed_user_message_indices'] == [1]
    assert set(selected['observation']['shared_work_contract']) == {'goal', 'online_scope', 'public_format'}
    assert selected['own_action_history'] == [
        {'tool': 'read_alias', 'argument_scope': {'alias': 'demand'}, 'ok': True,
         'reference': {'object_id': 'demand-object', 'version_id': 'v1'}},
        {'tool': 'inspect_submission', 'ok': False, 'argument_scope': {'submission_id': 'submission-3'},
         'control_status': 'actual_failure', 'submission_id': 'submission-3'}]


@pytest.mark.parametrize('field', ['goal', 'online_scope', 'public_format'])
def test_different_public_contract_values_are_not_merged(monkeypatch, field):
    body = _body()
    works = body['observation']['work_items']
    if field == 'goal':
        works['consumer'][field] = 'This work has a different actual goal.'
    else:
        works['consumer']['requirements'][field]['extra_constraint'] = {'must_retain': True}
    selected, _ = _project(monkeypatch, body)
    assert field not in selected['observation']['shared_work_contract']
    assert _restore_contracts(selected)['observation'] == body['observation']


def test_json_boolean_and_number_are_different_contracts(monkeypatch):
    body = _body()
    body['observation']['work_items']['maintainer']['requirements']['online_scope']['typed_value'] = True
    body['observation']['work_items']['consumer']['requirements']['online_scope']['typed_value'] = 1
    selected, _ = _project(monkeypatch, body)
    assert 'online_scope' not in selected['observation'].get('shared_work_contract', {})
    restored = _restore_contracts(selected)
    scopes = [w['requirements']['online_scope'] for w in restored['observation']['work_items'].values()]
    assert type(scopes[0]['typed_value']) is bool
    assert type(scopes[1]['typed_value']) is int


def test_existing_shared_contract_namespace_is_preserved(monkeypatch):
    body = _body()
    original = {'actual_prior_fact': {'unit': 'GBP', 'source': 'already visible'}}
    body['observation']['shared_work_contract'] = original
    selected, _ = _project(monkeypatch, body)
    assert selected['observation']['shared_work_contract'] == original
    # A reserved-name collision must never erase facts or replace actual work
    # contract values with references to a different pre-existing dictionary.
    for role, work in body['observation']['work_items'].items():
        actual = selected['observation']['work_items'][role]
        assert actual['goal'] == work['goal']
        assert actual['requirements'] == work['requirements']
