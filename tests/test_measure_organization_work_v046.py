"""The fixed work tracker gains capacity binding, not wider syntax coverage."""
import ast
import copy
import inspect
import json

import pytest

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_work_v045 as old
from scripts import measure_organization_work_v046 as new
from tests.test_measure_organization_budget_v046 import capacity_binding, fixture as budget_fixture, seal
from tests.test_measure_organization_work_v045 import Archive, ref, save
from tests.test_measure_organization_work_v045r2 import opportunity_reader


def fixture(tmp_path):
    folder = tmp_path / 'actual/episodes/fixture'
    archive = Archive(folder, condition='S1', members=1)
    initial = ref('member_001', 'v1')
    changed = archive.version('member_001', 'v2', 'def public_value(value):\n    return value + 2\n')
    archive.edit('member_001', initial, changed)
    archive.finish()
    cap = capacity_binding()
    actor = cap['capacity_actor_identity']
    result = json.loads((folder / 'slot-result.json').read_text())
    evidence = json.loads((folder / 'organization-evidence.json').read_text())
    budget = json.loads((folder / 'team-budget.json').read_text())['model']
    events = [json.loads(line) for line in (folder / 'experience.jsonl').read_text().splitlines()]
    budget['binding'] = {'actor_identity': actor, 'recipe_sha256': cap['capacity_recipe_sha256'],
                         'window_id': 'organization-v045:fixture'}
    result['actor_identity'] = actor
    for directory in (folder / 'raw-transport').glob('request-*'):
        turn = json.loads((directory / 'runner-turn.json').read_text())
        call_id = turn['association']['call_id']
        prep = json.loads((directory / 'budget-preparation.json').read_text())
        prep.update(budget['binding'], context_limit=18432)
        seal(prep, 'preparation_sha256')
        save(directory / 'budget-preparation.json', prep)
        projection = json.loads((directory / 'projection.json').read_text())
        projection['context_limit'] = 18432
        save(directory / 'projection.json', projection)
        response = json.loads((directory / 'response.json').read_text())
        response['body']['actor_identity'] = actor
        response_hash = digest(json_bytes(response['body']))
        save(directory / 'response.json', response)
        budget['records'][call_id]['reservation']['preparation'] = prep
        budget['records'][call_id]['charge']['response_body_sha256'] = response_hash
        next(a for a in evidence['original_attempts'] if a['call_id'] == call_id)['response_body_sha256'] = response_hash
    for event in events:
        payload = event['payload']
        if event['kind'] == 'model_call' and payload.get('stage') == 'started':
            payload['reservation'] = copy.deepcopy(budget['records'][payload['call_id']]['reservation'])
        if event['kind'] == new.OPPORTUNITY_VERSION:
            snapshot = payload['team_budget']
            snapshot['binding'] = copy.deepcopy(budget['binding'])
            for key in snapshot['records']:
                snapshot['records'][key] = copy.deepcopy(budget['records'][key])
    result['team_budget']['model'] = evidence['team_budget']['model'] = budget
    save(folder / 'slot-result.json', result)
    save(folder / 'organization-evidence.json', evidence)
    save(folder / 'team-budget.json', {'model': budget})
    save(folder.parent.parent / 'capacity-binding.json', cap)
    (folder / 'experience.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
    return folder


def test_work_aggregator_and_semantic_functions_stay_frozen():
    assert ast.dump(ast.parse(inspect.getsource(new.measure_episode))) == ast.dump(ast.parse(inspect.getsource(old.measure_episode)))
    for name in ('current_program_work', 'program_relations', 'current_information_work', 'information_relations'):
        assert getattr(new, name) is getattr(old, name)


def test_original_inputs_resources_and_s1_applicability_with_C18432(tmp_path):
    folder = fixture(tmp_path)
    value = new.measure_episode(folder)
    assert value['status'] == 'measured', value['measurement_gaps']
    assert value['totals']['current_program_artifacts'] == 1
    assert value['cross_member_applicability'] == 'not_applicable_no_partner'
    data = new.Evidence(folder)
    resource = data.resource(next(iter(data.calls.values())))
    assert resource['context_limit'] == 18432 and resource['hard_headroom_tokens'] == 18432 - 2048 - 8
    assert old.measure_episode(folder)['status'] == 'measurement_pending'


@pytest.mark.parametrize('change', ['missing_receipt', 'changed_profile', 'old_preparation'])
def test_work_does_not_accept_recipe_or_old_context_mix(tmp_path, change):
    folder = fixture(tmp_path)
    path = folder.parent.parent / 'capacity-binding.json'
    if change == 'missing_receipt':
        path.unlink()
    elif change == 'changed_profile':
        data = json.loads(path.read_text())
        data['capacity_inference_profile']['dtype'] = 'float32'
        save(path, data)
    else:
        path = next((folder / 'raw-transport').glob('*/budget-preparation.json'))
        prep = json.loads(path.read_text())
        prep['context_limit'] = 16384
        seal(prep, 'preparation_sha256')
        save(path, prep)
    assert new.measure_episode(folder)['status'] == 'measurement_pending'


def test_fixed_member_opportunity_uses_same_capacity_bound_original_preparation():
    data, _ = budget_fixture()
    reader = opportunity_reader(data)
    reader.__class__ = new.Evidence
    reader.capacity_binding = data['capacity_binding']
    reader._opportunities()
    resource = reader.resource({'call_id': 'new'})
    assert resource['status'] == 'recorded'
    assert resource['context_limit'] == 18432 and resource['hard_headroom_tokens'] == 3106
    assert resource['member_fixed_budget_attribution']['reason'] == 'member_fixed_budget'
    assert resource['actual_generation_started'] is False
