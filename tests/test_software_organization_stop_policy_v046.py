"""Same local/global stopping scope, with exact new-capacity receipt binding."""
import copy

import pytest

from scripts import software_organization_stop_policy_v046 as policy
from tests.test_measure_organization_budget_v046 import capacity_binding, seal
from test_organization_stop_policy_v044 import fixture as old_fixture


def fixture(R=1, submitted=True):
    data = old_fixture(R=R, submitted=submitted)
    cap = capacity_binding()
    actor = cap['capacity_actor_identity']
    model = data['team_budget']['model']
    model['binding'].update(actor_identity=actor, recipe_sha256=cap['capacity_recipe_sha256'],
                            window_id='organization-v045:' + data['row']['slot_id'])
    data['row']['actor_identity'] = actor
    reservation = model['records']['model-rejected']['rejected_reservation']
    reservation.update(input_token_reservation=17000, token_reservation=19048)
    prep = reservation['preparation']
    prep.update(model['binding'], prompt_tokens=17000, context_limit=18432)
    seal(prep, 'preparation_sha256')
    data['events'][1]['payload'].update(weight_identity=actor, reservation=copy.deepcopy(reservation))
    seal(model, 'state_sha256')
    data['events'][2]['payload']['team_budget'] = copy.deepcopy(model)
    data['capacity_binding'] = cap
    return data


@pytest.mark.parametrize(('R', 'submitted'), [(0, False), (0, True), (1, True)])
def test_C18432_hard_context_continues_independent_slots_without_result_selection(R, submitted):
    data = fixture(R, submitted)
    before = copy.deepcopy(data)
    result = policy.assess_records(**data)
    assert result['decision'] == 'continue', result
    assert result['local_context_events'][0]['excess_tokens'] == 616
    assert result['context_blocked_feedback_ids'] == ['feedback-2']
    assert data == before


@pytest.mark.parametrize('change', ['missing_capacity_receipt', 'old_context', 'wrong_recipe', 'service', 'output', 'feedback_gap'])
def test_old_context_or_integrity_problems_are_never_released(change):
    data = fixture()
    model = data['team_budget']['model']
    if change == 'missing_capacity_receipt':
        data['capacity_binding'] = None
    elif change == 'old_context':
        prep = model['records']['model-rejected']['rejected_reservation']['preparation']
        prep['context_limit'] = 16384
        seal(prep, 'preparation_sha256')
    elif change == 'wrong_recipe':
        model['binding']['recipe_sha256'] = '0' * 64
    elif change in {'service', 'output'}:
        data['events'].append({'sequence': 6, 'worker_id': 'member_001',
            'kind': 'model_boundary_error' if change == 'service' else 'model_response',
            'payload': {'status': 'model_service_error', 'call_id': 'model-rejected'}})
    else:
        data['feedback']['mechanism_gate_inputs']['feedback_missing_from_first_actual_followup'] = ['feedback-2']
    seal(model, 'state_sha256')
    data['events'][2]['payload']['team_budget'] = copy.deepcopy(model)
    outcome = policy.assess_records(**data)['decision']
    assert outcome == ('measurement_pending' if change == 'missing_capacity_receipt' else 'global_pause')
