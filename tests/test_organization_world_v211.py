"""Actual HarnessPort/WorldCore transitions and actual local pytest, no model/API."""
import itertools,copy
from pathlib import Path
from test_role_baseline_world_v141 import prepare as substrate,M1,M2
from proworksim import software_organization_world_v211 as world
from proworksim.harness_port import HarnessPort

def prepare(p):
 prepared,_,_,runs=substrate(p);world.attach(prepared,['behavior','regression'])
 ports={m:HarnessPort(world.SoftwareCollaborationPort(prepared.world.session(m,world.PROJECT),m),m,project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in (M1,M2)}
 for p in ports.values():p.tools()
 counter=itertools.count()
 def call(m,t,**a):return ports[m].call(t,request_key=f'v211-{next(counter)}',association={},**a)
 return prepared,ports,call,runs

def ok(call,m,t,**kw):
 r=call(m,t,**kw);assert r['ok'],r;return r['result']
def no(call,m,t,code,**kw):
 r=call(m,t,**kw);assert not r['ok'],r;assert r['error']['rejection']['code']==code,r;return r

def split(call):return ok(call,M1,'split_work',task_id='work_root',children=[{'task_id':'behavior','description':'Fix public behavior','scope':['behavior']},{'task_id':'regression','description':'Check regression','scope':['regression']}],reason='Two public scopes')

def test_split_transfer_partial_failure_and_owner_closure(tmp_path):
 p,ports,c,_=prepare(tmp_path);split(c)
 assert ports[M1].observe()['delivery_status']['requires_independent_review'] is True
 status=ok(c,M1,'dynamic_status');assert all(w['owner']==M1 for w in status['work'].values())
 offer=ok(c,M1,'assign_work',task_id='regression',to_member=M2,reason='Accept work explicitly')
 assert ok(c,M1,'dynamic_status')['work']['regression']['owner']==M1
 no(c,M2,'begin_work','dynamic_owner_required',task_id='regression')
 ok(c,M2,'accept_transfer',offer_id=offer['offer_id'])
 assert ok(c,M1,'dynamic_status')['work']['regression']['owner']==M2
 # Rejecting a later operation does not undo the committed owner transition.
 no(c,M1,'assign_verification','dynamic_owner_required',task_id='regression',reviewer=M2,reason='Wrong owner')
 assert ok(c,M1,'dynamic_status')['work']['regression']['owner']==M2
 no(c,M1,'split_work','dynamic_scope_conservation',task_id='behavior',children=[{'task_id':'x','description':'x','scope':['behavior']},{'task_id':'y','description':'y','scope':['behavior']}],reason='invalid duplicate')
 assert 'x' not in ok(c,M1,'dynamic_status')['work']

def test_collaboration_changes_real_message_permission(tmp_path):
 p,_,c,_=prepare(tmp_path);split(c)
 no(c,M1,'send_message','dynamic_collaboration_required',recipient=M2,task_id='behavior',body='Scoped coordination')
 ok(c,M1,'add_collaboration',task_id='behavior',peer=M2,reason='Share public diagnosis')
 sent=ok(c,M1,'send_message',recipient=M2,task_id='behavior',body='Scoped coordination')
 assert sent['message_sequence']
 ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n')
 patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Work-bound patch')
 ok(c,M1,'handoff_patch',patch_id=patch['patch_id'],to_member=M2,message='Actual work edge handoff')

def test_dependency_and_verification_change_actual_work(tmp_path):
 p,_,c,runs=prepare(tmp_path);split(c)
 off=ok(c,M1,'assign_work',task_id='regression',to_member=M2,reason='Partner implementation')
 ok(c,M2,'accept_transfer',offer_id=off['offer_id'])
 ok(c,M2,'change_dependency',task_id='regression',depends_on='behavior',operation='add',reason='Use behavior fix first')
 no(c,M2,'begin_work','dynamic_dependency_not_ready',task_id='regression')
 ok(c,M1,'assign_verification',task_id='behavior',reviewer=M2,reason='Independent author check')
 ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'run_tests')
 patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Actual implementation')
 ok(c,M1,'complete_work',task_id='behavior',patch_id=patch['patch_id'])
 no(c,M2,'begin_work','dynamic_dependency_not_ready',task_id='regression')
 ok(c,M2,'integrate_patch',patch_id=patch['patch_id']);ok(c,M2,'run_tests')
 ok(c,M2,'org_review_patch',patch_id=patch['patch_id'],decision='accept',reason='Actually adopted and tested')
 ok(c,M2,'begin_work',task_id='regression');ok(c,M2,'assign_verification',task_id='regression',reviewer=M1,reason='Cross-review partner contribution')
 ok(c,M2,'write_file',path='test_sample.py',text='def test_value():\n    from sample import value\n    assert value == 2\n    assert isinstance(value, int)\n')
 ok(c,M2,'run_tests');p2=ok(c,M2,'fix_patch',task_ids=['regression'],message='Regression contribution')
 ok(c,M2,'complete_work',task_id='regression',patch_id=p2['patch_id'])
 no(c,M2,'org_review_patch','dynamic_self_review',patch_id=p2['patch_id'],decision='accept',reason='Forbidden self review')
 ok(c,M1,'integrate_patch',patch_id=p2['patch_id']);ok(c,M1,'run_tests')
 ok(c,M1,'org_review_patch',patch_id=p2['patch_id'],decision='accept',reason='Actual contribution-level cross review')
 # Final fixed integration can bind the integrator-owned package; partner lineage remains included.
 ok(c,M1,'fix_patch',task_ids=['behavior'],message='Final integrated tree')
 delivered=ok(c,M1,'submit_integration',message='Explicit complete delivery')
 assert delivered['organization_evidence']['independent_review']['kind']=='contribution_level_cross_review'
 assert len(runs)==4
 assert p.world.dynamic()['work']['behavior']['authors']==[M1]
 assert p.world.dynamic()['work']['regression']['authors']==[M2]

def test_new_tools_preserve_schedule_and_closed_boundary(tmp_path):
 p,_,c,_=prepare(tmp_path);p.world.require_scheduled_actions=True;p.world.scheduled_member=M2
 no(c,M1,'split_work','fixed_organization_schedule',task_id='work_root',children=[{'task_id':'a','description':'a','scope':['behavior']},{'task_id':'b','description':'b','scope':['regression']}],reason='Not scheduled')
 p.world.require_scheduled_actions=False;p.world.fixed_candidates_closed=True
 no(c,M1,'dynamic_status','fixed_candidates_closed')
