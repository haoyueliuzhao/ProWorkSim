from copy import deepcopy
import pytest
from proworksim.software_graph_policy_v229 import Q0,TYPES,support,update_window,paired_value
from proworksim.software_osa_session_v226 import fingerprint


def fixture(i, phase='dev1', theta=None):
    graph={'work':{'w':{'owner':'member_001','reviewer':'member_002'}}}
    menu={'graph':graph,'base_sha256':fingerprint(graph),'anomaly':TYPES[i%4],
          'evidence':{'E1':{}},'options':{'K':{'op':'keep'},'D1':{'op':'diagnosis','task':'w','assignee':'member_002'}}}
    bank=support(menu,{'option':'D1','reason':'test','evidence':['E1']},f'cp{i}',2_500_000,Q0 if theta is None else theta)
    return {'instance_id':str(i),'phase':phase,'bank':bank,'arms':{a:{
        'checkpoint':f'cp{i}','activated_option':'K' if a=='KEEP' else 'D1','changed':a=='CHANGE','status':'closed',
        'logical_tokens':4_000_000,'legal_correct':a=='CHANGE'} for a in ('KEEP','CHANGE')}}


def test_two_full_windows_and_frozen_confirmation():
    ids=list(map(str,range(4)))
    first=update_window(Q0,[fixture(i) for i in range(4)],ids)
    assert first['fitted'] and first['theta']!=Q0 and first['by_anomaly']['A5']==[]
    assert all(v['N']=={'KEEP':0.,'CHANGE':0.} for vals in first['by_anomaly'].values() for v in vals)
    second=update_window(first['theta'],[fixture(i,'dev2',first['theta']) for i in range(4,8)],list(map(str,range(4,8))))
    assert second['fitted'] and second['by_anomaly']['A1'][0]['N']['KEEP']>0
    holdout=fixture(8,'confirm')
    assert paired_value(holdout['bank'],holdout['arms'],second['theta'])['value']>paired_value(holdout['bank'],holdout['arms'],Q0)['value']


def test_partial_stays_frozen_and_invalid_arms_are_rejected():
    p=fixture(0);ids=list(map(str,range(4)))
    assert update_window(Q0,[p],ids)['theta']==Q0
    for key,value in [('checkpoint','other'),('changed',False),('legal_correct',None),('activated_option','K')]:
        q=deepcopy(p);q['arms']['CHANGE'][key]=value
        with pytest.raises(ValueError):update_window(Q0,[q],ids)
    with pytest.raises(ValueError):update_window(Q0,[fixture(0,'confirm')],ids)


def test_osa_keep_has_no_synthetic_alternative():
    p=fixture(0)['bank']
    result=support(p['menu'],{**p['choice'],'option':'K'},'cp0',p['remaining'],Q0)
    assert result['decision']['q']=={'KEEP':1.}


def test_both_arms_use_the_real_controller_and_new_handoff_parser(tmp_path):
    from test_graph_controller_v228 import scene,M1,M2
    from test_organization_world_v211 import ok,no
    from proworksim.software_graph_controller_v228 import activate,menu
    from proworksim.software_graph_controller_v228_3 import ControlledWorld
    outcomes={}
    for name in ('KEEP','CHANGE'):
        root=tmp_path/name;root.mkdir()
        world,call,node=scene(root);world.__class__=ControlledWorld
        frozen=menu(world,node,M1)
        alt=next(k for k,v in frozen['options'].items() if v['op']=='diagnosis')
        bank=support(frozen,{'option':alt,'reason':'peer independently diagnoses','evidence':['E1']},'fixture-checkpoint',3_000_000,Q0)
        choice={**bank['choice'],'option':alt if name=='CHANGE' else 'K'}
        activated=activate(world,node,M1,frozen,choice,origin='osa')
        assert activated['changed']==(name=='CHANGE')
        no(call,M1,'assign_work','graph_authority',task_id='work_root',to_member=M2,reason='conflicting authority')
        if name=='CHANGE':
            ok(call,M2,'read_file',path='sample.py')
            seq=next(e['sequence'] for e in reversed(world.state['software_events']) if e['kind']=='read' and e['actor_id']==M2)
            ok(call,M2,'send_message',task_id='work_root',recipient=M1,body=f'DIAG {seq}: observed source value')
            assert world.protocol()['graph_control']['duties']['work_root']['status']=='handed_off'
        else:assert not world.protocol()['graph_control']['duties']
        outcomes[name]=activated['before']
    assert outcomes['KEEP']==outcomes['CHANGE']
