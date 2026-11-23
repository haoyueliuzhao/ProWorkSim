"""Zero-provider controls on the same managed harness used by the workers."""
import copy
import json
import pytest

from proworksim.software_osa_session_v226 import OSASession, world_view
from proworksim.software_natural_organization_world_v224_2 import register_proposal
from test_natural_coordination_v224_2 import prepare
from test_organization_world_v211 import ok, no, split
from test_organization_world_v212 import setup
from test_role_baseline_world_v141 import M1, M2

POLICY = 'a'*64

def scenario(kind='A4', work='regression', seq=1):
    return {'anomaly_id': 'observation-1','anomaly_type':kind,'status':'OPEN',
            'evidence_refs':[{'opportunity':seq,'command_id':f'cmd-{seq}','tool':'work_readiness',
                              'source_reference':{'object_id':'repo','version_id':'v1'}}],
            'affected_work':[work], 'affected_agents':[M1,M2], 'confidence':'high'}

def open_menu(session, node, p, c):
    wire=session.request(node,ok(c,M1,'dynamic_status'),remaining_tokens=3_000_000)
    return wire,json.loads(wire['messages'][-1]['content'])

def select(session, payload, operation=None):
    ids=[k for k,v in payload['available_options'].items() if v['operation']==operation]
    return session.receive('propose_response',{'option_ids':ids,'evidence_ids':[payload['anomaly']['evidence_refs'][0]['id']],
                                               'reason':'Act on the cited observation.'})

def worker_steps(candidate, c, decline=False):
    ok(c,M1,'select_arrangement',candidate_id=candidate['candidate_id'],decision='keep' if candidate['keep'] else 'attempt',reason='I selected this local response')
    receipts=[]
    for step in candidate['actions']:
        if 'arguments_from_real_receipt' in step:
            offer=receipts[-1]['offer_id']
            tool='decline_joint_arrangement' if decline else 'accept_joint_arrangement'
            args={'offer_id':offer}
            if decline:args['reason']='Other outstanding work'
            result=ok(c,step['actor'],tool,**args)
        else:
            result=ok(c,step['actor'],step['tool'],**step['arguments'])
        receipts.append(result)
    return receipts

def test_isolated_session_and_evidence_allowlist(tmp_path):
    p,c,_=prepare(tmp_path)
    split(c)
    node=scenario()
    node['worker_private_reasoning']='PRIVATE_MARKER'
    node['evidence_refs'][0]['logs']={'anything':'PRIVATE_MARKER'}
    node['evidence_refs'][0]['source_reference']['extra']='PRIVATE_MARKER'
    session=OSASession(POLICY)
    graph=ok(c,M1,'dynamic_status')
    graph['work']['regression']['private_transcript']='PRIVATE_MARKER'
    before=copy.deepcopy(graph)
    wire=session.request(node,graph,remaining_tokens=123)
    payload=json.loads(wire['messages'][-1]['content'])
    assert graph==before and 'PRIVATE_MARKER' not in json.dumps(wire)
    assert [t['function']['name'] for t in wire['tools']]==['propose_response']
    for t in ('read_file','write_file','run_tests','accept_joint_arrangement','submit_integration','change_policy'):
        with pytest.raises(PermissionError):
            session.receive(t,{})
    assert node['anomaly_id']==payload['anomaly']['anomaly_id']
    with pytest.raises(ValueError):session.receive('propose_response',{'evidence_ids':['forged'],'option_ids':[],'reason':'No evidence'})
    with pytest.raises(ValueError):session.receive('propose_response',{'evidence_ids':[],'option_ids':[],'reason':'Set parameters','theta':[1]})
    wire['tools'][0]['function']['name']='write_file'
    result=select(session,payload);result['reason']='MUTATED'
    own=OSASession(POLICY)
    clean,_=open_menu(own,node,p,c)
    assert clean['tools'][0]['function']['name']=='propose_response'
    assert json.loads(clean['messages'][-1]['content'])['own_prior_proposals']==[]
    with pytest.raises(ValueError):session.request(node,graph,remaining_tokens=100)
    second=scenario(seq=2)
    with pytest.raises(ValueError):session.request(second,graph,remaining_tokens=100)
    second['evidence_refs'][0]['source_reference']['version_id']='v2'
    _,detail=open_menu(session,second,p,c)
    assert detail['own_prior_proposals'][0]['reason']!='MUTATED'
    select(session,detail)
    with pytest.raises(ValueError):session.request(scenario(seq=3),graph,remaining_tokens=100)

def test_real_private_event_cannot_be_exposed_to_osa(tmp_path):
    p,c,_=prepare(tmp_path)
    split(c);ok(c,M2,'read_file',path='sample.py')
    raw=next(e for e in reversed(p.world.state['software_events']) if e['kind']=='read' and e['actor_id']==M2)
    with pytest.raises(PermissionError):world_view(p.world,[raw['sequence']],M1)
    evidence=world_view(p.world,[raw['sequence']],M2)
    assert evidence[0]['actor_id']==M2 and 'content' not in evidence[0]

@pytest.mark.parametrize('kind', ['A1','A2','A3','A4','A5'])
@pytest.mark.parametrize('operation', [None,'peer_diagnosis','transfer_remaining'])
def test_response_mechanics_on_five_scenario_labels(tmp_path,kind,operation):
    p,c,_=prepare(tmp_path)
    split(c)
    node=scenario(kind);session=OSASession(POLICY)
    _,payload=open_menu(session,node,p,c)
    from proworksim.software_anomaly_selector_v226 import evaluate, FEATURES
    before=copy.deepcopy(p.world.dynamic()['work'])
    candidate=select(session,payload,operation)
    eval_result=evaluate(node,{k:0.5 for k in FEATURES},{'KEEP':{'diagnosis':'current','actions':[]},'Z':candidate},[0.]*5)
    assert sum(eval_result['q'].values())==pytest.approx(1.0)
    assert p.world.dynamic()['work']==before
    register_proposal(p.world,candidate,{'synthetic_scenario':kind})
    assert p.world._task('regression')['owner']==M1
    receipts=worker_steps(candidate,c)
    if operation=='transfer_remaining':
        assert len(receipts)==2 and p.world._task('regression')['owner']==M2
    elif operation=='peer_diagnosis':
        assert receipts[-1]['message_sequence'] and p.world._task('regression')['owner']==M1
    else:
        assert not receipts and p.world.dynamic()['work']==before

def test_real_decline_preserves_owner(tmp_path):
    p,c,_=prepare(tmp_path);split(c)
    sess=OSASession(POLICY);_,payload=open_menu(sess,scenario('A2'),p,c)
    candidate=select(sess,payload,'transfer_remaining')
    register_proposal(p.world,candidate,{'fixture':True})
    receipts=worker_steps(candidate,c,decline=True)
    assert p.world.dynamic()['joint_offers'][receipts[0]['offer_id']]['status']=='declined'
    assert p.world._task('regression')['owner']==M1

def test_verify_responds_to_actual_missing_reviewer(tmp_path):
    p,c,_=prepare(tmp_path);split(c)
    gap=ok(c,M1,'work_readiness',task_id='regression')
    assert any(g['kind']=='independent_reviewer_missing_or_invalid' for g in gap['gaps'])
    sess=OSASession(POLICY);_,payload=open_menu(sess,scenario('A4'),p,c)
    candidate=select(sess,payload,'assign_verifier')
    register_proposal(p.world,candidate,{'fixture':True})
    worker_steps(candidate,c)
    assert p.world.dynamic()['work']['regression']['reviewer']==M2
    assert not any(g['kind']=='independent_reviewer_missing_or_invalid' for g in ok(c,M1,'work_readiness',task_id='regression')['gaps'])
    # Assignment is observed; independent verification still has to be performed.
    assert not p.world.org_state()['reviews']

def test_authored_work_not_offered_for_transfer(tmp_path):
    p,c,_=prepare(tmp_path);split(c);setup(c,'behavior')
    ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n')
    sess=OSASession(POLICY);_,payload=open_menu(sess,scenario('A1','behavior'),p,c)
    assert not any(o['operation']=='transfer_remaining' for o in payload['available_options'].values())

def test_a1_real_failed_edits_allow_diagnosis_of_authored_work(tmp_path):
    p,c,_=prepare(tmp_path);split(c);setup(c,'behavior')
    ok(c,M1,'begin_work',task_id='behavior')
    for v in (4,5):
        ok(c,M1,'write_file',path='sample.py',text=f'value = {v}\n')
        ok(c,M1,'run_tests')
    events=[e for e in p.world.state['software_events'] if e['kind']=='test' and e['actor_id']==M1]
    assert len(events)==2 and all(e['executed'] and not e['passed'] for e in events)
    assert events[0]['source_reference']!=events[1]['source_reference']
    node=scenario('A1','behavior');node['evidence_refs']=world_view(p.world,[e['sequence'] for e in events],M1)
    sess=OSASession(POLICY);_,payload=open_menu(sess,node,p,c)
    candidate=select(sess,payload,'peer_diagnosis')
    register_proposal(p.world,candidate,{'fixture':True});receipts=worker_steps(candidate,c)
    assert receipts[-1]['message_sequence'] and p.world.dynamic()['work']['behavior']['authors']==[M1]

def test_a2_real_block_and_explicit_upstream_adoption(tmp_path):
    p,c,_=prepare(tmp_path);split(c);setup(c,'behavior')
    ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'run_tests')
    patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Visible upstream version')['patch_id']
    ok(c,M1,'complete_work',task_id='behavior',patch_id=patch)
    off=ok(c,M1,'offer_joint_arrangement',task_id='regression',to_member=M2,reviewer=M1,mode='implementation',expected_revision=1,reason='Other owner')
    ok(c,M2,'accept_joint_arrangement',offer_id=off['offer_id'])
    ok(c,M2,'add_collaboration',task_id='regression',peer=M1,reason='Cross-check')
    ok(c,M2,'change_dependency',task_id='regression',depends_on='behavior',operation='add',reason='Requires actual fix')
    readiness=c(M2,'work_readiness',task_id='regression')
    assert readiness['ok'] and any(g['kind']=='upstream_patch_not_adopted' for g in readiness['result']['gaps'])
    node=scenario('A2');node['evidence_refs']=[{'command_id':readiness['command_id'],'kind':'upstream_patch_not_adopted','patch_id':patch}]
    sess=OSASession(POLICY);wire=sess.request(node,ok(c,M2,'dynamic_status'),remaining_tokens=4_000_000)
    candidate=select(sess,json.loads(wire['messages'][-1]['content']),'adopt_upstream')
    assert len(candidate['actions'])==1 and candidate['actions'][0]['arguments']['patch_id']==patch
    register_proposal(p.world,candidate,{'fixture':True});worker_steps(candidate,c)
    assert ok(c,M2,'work_readiness',task_id='regression')['ready']

@pytest.mark.parametrize('op',['focus_delivery','independent_close_check'])
def test_delivery_level_response_on_unscoped_a5(tmp_path,op):
    p,c,_=prepare(tmp_path)
    node=scenario('A5');node.update(affected_work=[],subject='delivery_ready')
    sess=OSASession(POLICY);_,payload=open_menu(sess,node,p,c);candidate=select(sess,payload,op)
    register_proposal(p.world,candidate,{'fixture':True});receipts=worker_steps(candidate,c)
    assert receipts[0]['message_sequence'] and 'ready_to_submit' in receipts[1]
    assert not p.world.protocol()['terminal']
