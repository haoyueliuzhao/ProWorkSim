import pytest
from test_natural_coordination_v224_2 import prepare
from test_role_baseline_world_v141 import M1,M2
from test_organization_world_v211 import ok,no
from proworksim.software_graph_controller_v228 import ControlledWorld,activate,menu,graph


def scene(tmp_path):
    p,call,_=prepare(tmp_path)
    p.world.__class__=ControlledWorld
    ok(call,M1,'read_file',path='sample.py')
    node={'anomaly_id':'fixture','anomaly_type':'A1','subject':'test_value',
          'affected_work':['work_root'],'evidence_refs':[{'opportunity':1,'tool':'read_file'}]}
    return p.world,call,node


def apply(w,n,m,key):
    return activate(w,n,M1,m,{'option':key,'evidence':['E1'],'reason':'CPU control'},origin='osa')


def test_controller_transfer_and_harness(tmp_path):
    w,c,n=scene(tmp_path);m=menu(w,n,M1)
    result=apply(w,n,m,next(k for k,x in m['options'].items() if x['op']=='transfer_unstarted'))
    assert result['changed'] and w._task('work_root')['owner']==M2
    no(c,M1,'begin_work','work_setup_incomplete',task_id='work_root')
    ok(c,M2,'begin_work',task_id='work_root')
    ok(c,M2,'write_file',path='sample.py',text='value = 2')
    no(c,M1,'accept_joint_arrangement','graph_authority',offer_id='invented')
    with pytest.raises(ValueError,match='stale'):apply(w,n,m,'K')
    assert not any(x['op']=='transfer_unstarted' for x in menu(w,n,M1)['options'].values())
    assert w.dynamic()['work']['work_root']['authors']==[M2]


def test_diagnosis_requires_real_handoff_and_allows_objections(tmp_path):
    w,c,n=scene(tmp_path);m=menu(w,n,M1)
    apply(w,n,m,next(k for k,x in m['options'].items() if x['op']=='diagnosis'))
    no(c,M2,'send_message','graph_evidence_required',recipient=M1,task_id='work_root',body='DIAG 999999 guessed')
    ok(c,M2,'read_file',path='sample.py')
    seq=next(e['sequence'] for e in reversed(w.state['software_events']) if e['actor_id']==M2 and e['kind']=='read')
    ok(c,M2,'send_message',recipient=M1,task_id='work_root',body=f'DIAG {seq} value differs from expectation')
    ok(c,M2,'send_message',recipient=M1,task_id='root_goal',body='BLOCK dependency upstream not yet adopted')
    active=ok(c,M2,'dynamic_status')['active_organization']
    assert active['duties']['work_root']['status']=='handed_off' and active['reported_blockers'][0]['kind']=='dependency'
    assert w._task('work_root')['owner']==M1 and not w.dynamic()['work']['work_root']['authors']


def test_invalid_decision_is_atomic_and_keep_keeps_graph(tmp_path):
    w,c,n=scene(tmp_path);m=menu(w,n,M1)
    before=graph(w)
    for key in ('invalid','bad-evidence'):
        with pytest.raises(ValueError):
            activate(w,n,M1,m,{'option':key,'evidence':['bad'] if key=='bad-evidence' else ['E1'],'reason':'test'},origin='osa')
        assert 'graph_control' not in w.store.load()['projects']['SOFTWARE27']['software']['protocol_v216']
    assert apply(w,n,m,'K')['changed'] is False and before==graph(w)
