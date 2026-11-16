import pytest
from proworksim.software_organization_decision_v203_3_1 import VERSION,validate_decision,validate_work_package

def base():
    return {'version':VERSION,'constraint_gap':'PRESENT','efficiency_opportunity':'UNKNOWN',
        'state_evidence':['known responsibility gap'],'feasibility':'INFEASIBLE',
        'action':'NO_CHANGE','reason':'remaining_budget'}

@pytest.mark.parametrize('reason',['remaining_budget','switch_cost','no_legal_alternative','insufficient_expected_gain'])
def test_known_gap_can_rationally_keep_organization(reason):
    assert validate_decision({**base(),'reason':reason})['valid']

def test_efficiency_probe_needs_no_positive_mismatch_but_requires_legality():
    row={**base(),'constraint_gap':'ABSENT','efficiency_opportunity':'UNKNOWN',
        'feasibility':'FEASIBLE','action':'INTERVENE','reason':'preregistered_probe',
        'legal_action_evidence':['frozen package'],'predicted_effect_is_established':False}
    assert validate_decision(row)['valid']
    with pytest.raises(ValueError):validate_decision({**row,'feasibility':'UNKNOWN'})
    with pytest.raises(ValueError):validate_decision({**row,'predicted_effect_is_established':True})

def test_abstention_and_infeasibility_are_not_relabelled_as_absence():
    assert validate_decision({**base(),'action':'ABSTAIN','reason':'insufficient_evidence'})['valid']
    with pytest.raises(ValueError):validate_decision({**base(),'action':'ABSTAIN'})
    with pytest.raises(ValueError):validate_decision({**base(),'state_evidence':[]})

def test_republishing_does_not_make_code_contributor_independent():
    p={'kind':'public_diagnosis','old_owner':'member_001','new_owner':'member_002',
       'delivery_member':'member_001','final_reviewer':'member_002','implementation_author':'member_001',
       'task_id':'diagnose','source_reference':{'object_id':'baseline','version_id':'v1'},
       'next_work':[{'tool':'read_file','arguments':{'path':'sample.py'}}],
       'other_member_work':'Implement only after the diagnostic result'}
    validate_work_package(p)
    with pytest.raises(ValueError):validate_work_package({**p,'implementation_author':'member_002'})
    with pytest.raises(ValueError):validate_work_package({**p,'next_work':[{'tool':'write_file'}]})
