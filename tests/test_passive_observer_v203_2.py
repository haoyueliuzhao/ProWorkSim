import copy,json
import pytest
from proworksim.software_passive_observer_v203_2 import PassiveRecorder,ObservedPort,observed_model_invoke,blocked_cause,digest

class Port:
    def __init__(self):self.calls=0;self.response={'ok':True,'result':{'task_id':'T','owner':'a','revision':1,'created_by':'a'}}
    def tools(self):return [{'name':'claim_task','parameters':{'type':'object'}}]
    def observe(self):return {'actor_id':'a','private':'unchanged'}
    def call(self,tool,**kwargs):self.calls+=1;return self.response

def recorder(tmp_path,**kwargs):
    r=PassiveRecorder(tmp_path,'cpu',['a','b'],**kwargs);r.initialize({'fixture':True});return r

def test_proxy_preserves_tools_observation_response_and_call_count(tmp_path):
    r=recorder(tmp_path);raw=Port();p=ObservedPort(raw,'a',r);before=copy.deepcopy(raw.tools());obs=copy.deepcopy(raw.observe())
    response=p.call('claim_task',task_id='T',request_key='one',association={'keep':'original'})
    assert response is raw.response and raw.calls==1 and p.tools()==before and p.observe()==obs
    assert r.state.tasks['T']['owner']=='a' and not r.pending

def test_logging_failure_does_not_stop_or_repeat_world_and_can_drain(tmp_path):
    r=recorder(tmp_path);raw=Port();p=ObservedPort(raw,'a',r);normal=r.writer
    def fail(row):raise OSError('CPU injected recorder unavailable')
    r.writer=fail
    assert p.call('claim_task',task_id='T',request_key='one') is raw.response
    assert raw.calls==1 and len(r.pending)==2 and r.faults and not r.state.tasks
    r.writer=normal;r.flush();assert not r.pending and raw.calls==1 and r.state.tasks['T']['owner']=='a'

def test_replay_hash_chain_and_truncated_tail_preserves_complete_prefix(tmp_path):
    r=recorder(tmp_path);p=ObservedPort(Port(),'a',r);p.call('claim_task',task_id='T',request_key='one')
    path=tmp_path/'events.jsonl';state,proof=r.replay(path,'cpu',['a','b']);assert state.snapshot()==r.state.snapshot()
    original=path.read_bytes();path.write_bytes(original+b'{"incomplete":');before=path.read_bytes();state,proof=r.replay(path,'cpu',['a','b'])
    assert proof['incomplete_tail'] and state.snapshot()==r.state.snapshot() and path.read_bytes()==before
    lines=original.splitlines();row=json.loads(lines[1]);row['record']['payload']['actor']='forged';lines[1]=json.dumps(row).encode();path.write_bytes(b'\n'.join(lines)+b'\n')
    with pytest.raises(ValueError):r.replay(path,'cpu',['a','b'])

def test_same_observation_key_idempotent(tmp_path):
    r=recorder(tmp_path);p=ObservedPort(Port(),'a',r);p.call('claim_task',task_id='T',request_key='same');count=len(r.state.events)
    p.call('claim_task',task_id='T',request_key='same');assert len(r.state.events)==count and not r.pending

def test_submission_phase_is_before_response(tmp_path):
    r=recorder(tmp_path);r.intent('a','submit_integration',{},'submit');phase=copy.deepcopy(r.state.phases['T6'])
    r.receipt('a','submit_integration',{}, {'ok':True,'result':{'delivery_id':'d','source_reference':{'object_id':'a','version_id':'v1'}}},'submit')
    assert not phase['state']['deliveries'] and phase['metadata']['future_result_included'] is False and len(r.state.deliveries)==1

def test_owner_history_not_overwritten_and_test_invalidates_on_edit(tmp_path):
    r=recorder(tmp_path);v1={'object_id':'a','version_id':'v1'};v2={'object_id':'a','version_id':'v2'}
    r.receipt('a','claim_task',{}, {'ok':True,'result':{'task_id':'T','owner':'a','revision':1,'created_by':'a'}},'claim')
    r.receipt('b','accept_transfer',{}, {'ok':True,'result':{'task_id':'T','owner':'b','revision':1,'created_by':'a'}},'accept')
    assert r.state.owner_intervals[0]['owner']=='a' and r.state.owner_intervals[0]['valid_to'] is not None and r.state.owner_intervals[1]['owner']=='b'
    r.receipt('a','run_tests',{'selection':['public']},{'ok':True,'result':{'report_id':'r','executed':True,'passed':True,'source_reference':v1}},'test')
    assert r.state.snapshot()['tests'][0]['current_effective']
    r.receipt('a','write_file',{'path':'x.py'},{'ok':True,'result':{'source_reference':v2,'paths':['x.py']}},'edit')
    assert not r.state.snapshot()['tests'][0]['current_effective']

def test_presented_requires_accepted_input_and_does_not_mean_read(tmp_path):
    r=recorder(tmp_path);wire={'model':'scripted','tools':[{'x':1}],'messages':[{'role':'user','content':json.dumps({'observation':{'actor_id':'b','handoffs':[{'recipient':'b','sequence':1,'patch_id':'p','source_reference':{'object_id':'a','version_id':'v2'}}]}})}]};before=copy.deepcopy(wire)
    with pytest.raises(ValueError):r.input_accepted('b','q',wire,{'id':None,'usage':None})
    def send(value):assert value is wire;return {'id':'scripted','usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}
    result=observed_model_invoke(r,'b','q',wire,send,mode='cpu_scripted')
    assert wire==before and result['id']=='scripted' and not r.state.reads
    assert r.state.events[-1]['kind']=='Handoff Presented' and r.state.events[-1]['evidence_mode']=='cpu_scripted'

@pytest.mark.parametrize('status,cause',[('model_budget_exhausted','Budget Exhaustion'),('waiting','Normal Waiting'),('model_format_feedback','Model Failure'),('unknown','Unknown')])
def test_explicit_failure_categories(status,cause):assert blocked_cause(None,{},status)==cause

def test_public_test_failure_is_not_upstream_or_org_failure(tmp_path):
    r=recorder(tmp_path);r.receipt('a','run_tests',{}, {'ok':True,'result':{'executed':True,'passed':False,'report_id':'failure','source_reference':{'object_id':'a','version_id':'v1'}}},'test')
    assert r.state.phases['T4'] and [e['kind'] for e in r.state.events]==['Test Executed']

def test_initial_contract_and_late_message_schema_are_source_bound(tmp_path):
    r=PassiveRecorder(tmp_path,'cpu',['a','b']);initial={'issue':'public issue','organization':'REVIEW2','delivery_member':'a'};r.initialize({'frozen_contract':'c'},initial)
    initial['issue']='changed_after_capture';assert r.state.phases['T0']['state']['initial_condition']['issue']=='public issue'
    r.receipt('a','send_message',{'body':'original'}, {'ok':True,'result':{'recipient':'b','message_sequence':4}},'message')
    assert r.state.events[-1]['kind']=='Message Sent' and r.state.events[-1]['presented_not_inferred']

def test_known_protocol_rejection_is_not_a_generic_organization_failure():
    response={'ok':False,'error':{'rejection':{'category':'business_constraint','code':'organization_flow'}}}
    assert blocked_cause('claim_task',response)=='Tool Failure'
    assert blocked_cause('claim_task',{'error':{'rejection':{'category':'unknown','code':'unclassified_exception'}}})=='Unknown'

def test_assessment_schema_separates_dependency_misalignment_and_action():
    from proworksim.software_assessment_schema_v203_2 import validate_assessment
    row={'dependency':'PRESENT','misalignment':'ABSENT','decision':'NO_CHANGE','dependency_types':['Artifact Dependency'],'decision_evidence':['existing_handoff_satisfied']}
    assert validate_assessment(row)['schema_valid']
    with pytest.raises(ValueError):validate_assessment({**row,'decision':'INTERVENE','intervention_types':['Reassign']})
    assert validate_assessment({'dependency':'UNKNOWN','misalignment':'UNKNOWN','decision':'ABSTAIN'})['schema_valid']
    assert validate_assessment({'dependency':'ABSENT','misalignment':'PRESENT','decision':'INTERVENE','decision_evidence':['independent_validation_gap'],
        'misalignment_types':['Validation Misalignment'],'intervention_types':['AddReviewer']})['schema_valid']

def test_review_preserves_decision_and_test_evidence_separately(tmp_path):
    r=recorder(tmp_path)
    review={'review_id':'r1','patch_id':'p1','decision':'accept','test_evidence':{'executed':True,'passed':False},'identity':{'source_reference':{'object_id':'x','version_id':'v2'}}}
    r.receipt('b','org_review_patch',{}, {'ok':True,'result':review},'review')
    assert r.state.snapshot()['reviews'][0]['review']==review
    assert not r.state.tests and r.state.events[-1]['additional_test_execution_not_inferred']
    replayed,_=r.replay(tmp_path/'events.jsonl','cpu',['a','b'])
    assert replayed.snapshot()==r.state.snapshot()
