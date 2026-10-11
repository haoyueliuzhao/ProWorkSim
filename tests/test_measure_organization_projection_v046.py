"""New binding controls; synthetic character projection is not model tokenization."""
import copy
import json

import pytest

from proworksim.software_context_v044 import project_software_request
from proworksim.storage import digest, json_bytes
from scripts import measure_organization_projection_v045 as old
from scripts import measure_organization_projection_v046 as new
from tests.test_measure_organization_budget_v046 import capacity_binding, seal
from test_organization_feedback_v044 import fixture as old_fixture, save


def fixture(tmp_path):
    value = old_fixture(tmp_path)
    original = copy.deepcopy(value.original)
    body = json.loads(original['messages'][1]['content'])
    body['observation']['interface_revision'] = new.PAGE_INTERFACE
    original['messages'][1]['content'] = json.dumps(body)
    selected, projection = project_software_request(original, ledger=value.ledger, member_id='member_001',
        render=lambda item: (json.dumps(item, ensure_ascii=False), None, None),
        tokenizer=lambda text, **kwargs: {'input_ids': list(range(len(text)))}, context_limit=18432)
    binding = capacity_binding()
    prep = seal({'context_limit': 18432, 'reserved_output_tokens': 2048,
        'prompt_tokens': projection['selected_prompt_tokens'], 'fits': True,
        'actor_identity': binding['capacity_actor_identity'], 'recipe_sha256': binding['capacity_recipe_sha256'],
        'window_id': 'organization-v045:fixture', 'original_request_sha256': digest(json_bytes(original)),
        'selected_request_sha256': digest(json_bytes(selected)), 'input_ids_sha256': projection['input_ids_sha256'],
        'rendered_prompt_sha256': projection['rendered_prompt_sha256']}, 'preparation_sha256')
    value.record['reservation']['preparation'] = prep
    value.record['charge']['reported_usage']['prompt_tokens'] = prep['prompt_tokens']
    value.call.update(selected_request_sha256=digest(json_bytes(selected)), input_ids_sha256=prep['input_ids_sha256'])
    for name, item in [('original-request.json', original), ('selected-request.json', selected), ('projection.json', projection)]:
        save(value.folder / name, item)
    return value, binding


def audit(value, binding):
    return new.audit_projection(value.call, value.record, value.initial, value.assignments, value.ledger, capacity_binding=binding)


def test_new_capacity_keeps_original_Gamma_lifecycle_and_page_proof(tmp_path):
    value, binding = fixture(tmp_path)
    result = audit(value, binding)
    assert result['status'] == 'verified', result['issues']
    assert result['context_limit'] == 18432 and result['reserved_output_tokens'] == 2048
    assert result['latest_complete_round_present'] is True
    assert new.PAGE_INTERFACE == old.PAGE_INTERFACE
    assert old.audit_projection(value.call, value.record, value.initial, value.assignments, value.ledger)['status'] == 'violation'


@pytest.mark.parametrize('change', ['missing_receipt', 'old_preparation', 'wrong_recipe', 'wrong_seal', 'changed_selected'])
def test_valid_world_interface_does_not_excuse_wrong_capacity_or_input(tmp_path, change):
    value, binding = fixture(tmp_path)
    prep = value.record['reservation']['preparation']
    if change == 'missing_receipt':
        binding = None
    elif change == 'old_preparation':
        prep['context_limit'] = 16384
        seal(prep, 'preparation_sha256')
    elif change == 'wrong_recipe':
        prep['recipe_sha256'] = '0' * 64
        seal(prep, 'preparation_sha256')
    elif change == 'wrong_seal':
        prep['preparation_sha256'] = '0' * 64
    else:
        selected = json.loads((value.folder / 'selected-request.json').read_text())
        selected['messages'][0]['content'] = 'Changed model-visible input'
        save(value.folder / 'selected-request.json', selected)
    assert audit(value, binding)['status'] == 'violation'
