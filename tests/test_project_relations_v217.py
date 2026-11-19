import copy
from types import SimpleNamespace
import pytest
from proworksim.software_project_relations_v217 import Projection,synchronize
from proworksim.software_organization_generator_v217 import compile_target
from proworksim.software_organization_selector_v217 import initialize,evaluate,update
from test_organization_planning_v216 import state as graph_state

def event(n,kind,actor='member_001',**kw):return {'sequence':n,'kind':kind,'actor_id':actor,**kw}
def test_incremental_rebuild_version_and_dependency_separation():
 events=[event(1,'organization_v213:work_started',task_id='left'),event(2,'edit',paths=['a.py'],operation_id='e',source_reference={'version_id':'v1'}),event(3,'test',executed=True,passed=True,source_reference={'version_id':'v1'}),event(4,'organization_v213:dependency_changed',task_id='left',depends_on='done',operation='add',reason='Interface needed'),event(5,'edit',paths=['a.py'],operation_id='f',source_reference={'version_id':'v2'}),event(6,'organization_v213:dependency_changed',task_id='left',depends_on='done',operation='remove',reason='Different execution order'),event(7,'integrate',patch_id='patch-1',source_reference={'version_id':'v3'},conflicts=[])]
 p=Projection();work=graph_state()['work']
 for i,e in enumerate(events):
  p.apply(e);full=Projection()
  for old in events[:i+1]:full.apply(old)
  assert p.snapshot(work,[])==full.snapshot(work,[])
 pg=p.snapshot(work,[]);assert next(r for r in pg['relations'] if r['kind']=='test_version')['validity']=='historical_version'
 assert any(r['kind']=='work_requires_claim' and r['fact_status']=='member_claim' for r in pg['relations'])
 assert any(r['kind']=='artifact_adopted' and r['details']['adoption_not_validation'] for r in pg['relations'])
 old=copy.deepcopy(pg);p.apply(events[-1]);assert p.snapshot(work,[])==old
 with pytest.raises(ValueError):p.apply({**events[-1],'patch_id':'different'})

def test_actor_filter_and_rejected_call_do_not_fabricate_work():
 class W:
  state={'software_events':[event(1,'edit','member_002',paths=['SECRET.py']),event(2,'work_message','member_002',recipient='member_001',body='Published statement')]}
  def _action_read_work_event(self,a,project,n):
   if n==1:raise ValueError('Private event')
   return self.state['software_events'][1]
  def _action_dynamic_status(self,a,p):return {'work':graph_state()['work']}
 doc=synchronize(Projection(),W(),[])
 assert 'SECRET' not in str(doc) and doc['processed_visible_events']==1
 assert any(r['kind']=='member_statement' and r['fact_status']=='member_claim' for r in doc['relations'])

def decision_state():
 g=graph_state();g['work']['left']['reviewer']=None;g['collaboration']=[e for e in g['collaboration'] if e[0]!='left']
 p=Projection();p.apply(event(1,'organization_v213:work_started',task_id='done'));p.apply(event(2,'edit',paths=['a.py'],operation_id='a',source_reference={'version_id':'v2'}));p.apply(event(3,'organization_v213:work_performed',task_id='done',operation_id='a',source_reference={'version_id':'v2'}));p.apply(event(4,'test',passed=True,executed=True,source_reference={'version_id':'v2'}))
 return {'graph':g,'project_relations':p.snapshot(g['work'],[]),'member_usage':{'member_001':{'known_actual_tokens':1_000_000},'member_002':{'known_actual_tokens':100_000}}}
def proposal(s,move=False):
 pg=s['project_relations'];return {'reason':'Set explicit verification for unfinished work','remaining_work':[{'source_task_id':k,'parts':[{'scope':w['scope'],'owner':'member_002' if move and k=='left' else w['owner'],'mode':'implementation'}]} for k,w in s['graph']['work'].items() if not w['authors']],'dependencies':[],'adoptions':[],'basis':{'graph_id':pg['graph_id'],'relation_ids':[r['id'] for r in pg['relations']],'trigger_events':[2],'need':'Unfinished verification','expected_benefit':'More reliable review','switch_cost':'Actual setup tools'}}
def test_no_transfer_plan_and_graph_binding_then_two_real_selector_updates():
 s=decision_state();a=compile_target(s,proposal(s));assert not any(x['op']=='JOINT_ASSIGN' for x in a['operations'])
 b=compile_target(s,proposal(s,True));assert a['candidate_id']!=b['candidate_id']
 bad=proposal(s);bad['basis']['relation_ids']=['invented']
 with pytest.raises(ValueError):compile_target(s,bad)
 bank={'candidates':{'KEEP':{'target':s['graph'],'actions':[]},'C1':a,'C2':b},'remaining_branch_token_limit':3_000_000}
 q0=initialize();d1=evaluate(s,bank,q0,123)
 record={'index':0,'decision':d1,'outcomes':{z:{'legal_correct':z=='C2','logical_tokens':4_900_000} for z in bank['candidates']}}
 q1=update(q0,[record],'dev1');d2=evaluate(s,bank,q1,123);assert d2['probabilities']['P_CN']!=d1['probabilities']['P_CN']
 assert q1['theta']['P_C'] is not q1['theta']['L_CN']
 record2={**record,'index':1,'decision':d2};q2=update(q1,[record2],'dev2');assert q2['update']==2 and [x['window'] for x in q2['fit_history']]==['dev1','dev2']
 before=copy.deepcopy(q2);evaluate(s,bank,q2,999);assert q2==before

def test_budget_amendment_and_complete_candidate_cash(tmp_path):
 from proworksim.software_organization_api_v217 import Ledger
 l=Ledger(tmp_path/'ledger');assert l.snapshot()['cap_CNY']==1100
 l.reserve_block('all',{'v217:t:KEEP':3_000_000,'v217:t:C1':3_000_000,'v217:t:C2':3_000_000},'dev1')
 assert l.snapshot()['phase_estimated_exposure_CNY']['development']==22.5
 assert l.snapshot()['confirmation_plan_reserved_CNY']==392
 with pytest.raises(ValueError):l.reserve_block('dup',{'v217:t:KEEP':3_000_000},'dev1')

def test_real_managed_receipts_produce_permission_bounded_graph(tmp_path):
 from test_organization_continuation_v216_2 import prepare
 from test_organization_world_v211 import ok,split
 from test_organization_world_v212 import setup
 from test_role_baseline_world_v141 import M1,M2
 p,_,c,_=prepare(tmp_path);split(c);setup(c,'behavior');setup(c,'regression')
 ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'run_tests')
 projection=Projection(M1);before=copy.deepcopy(p.world.state)
 doc=synchronize(projection,p.world,[])
 assert p.world.state==before
 assert any(r['kind']=='work_code_region' and r['source']=='behavior' for r in doc['relations'])
 assert any(r['kind']=='test_version' and r['details']['passed'] and r['validity']=='current' for r in doc['relations'])
 rebuilt=synchronize(Projection(M1),p.world,[]);assert rebuilt==doc
 restored=Projection(M1);restored.restore(projection.export());assert synchronize(restored,p.world,[])==doc

def test_real_integration_receipt_binds_patch_id_without_fake_private_adoption(tmp_path):
 from test_organization_continuation_v216_2 import prepare
 from test_organization_world_v211 import ok,split
 from test_organization_world_v212 import setup
 from test_role_baseline_world_v141 import M1,M2
 p,_,c,_=prepare(tmp_path);split(c);setup(c,'behavior');setup(c,'regression')
 ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'run_tests')
 patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Published real source')['patch_id']
 result=c(M2,'integrate_patch',patch_id=patch)
 projection=Projection(M2);outcome={'worker_id':M2,'decision':{'action':'integrate_patch','arguments':{'patch_id':patch}},'response':result}
 projection.record_outcome(outcome,p.world.state['software_events']);doc=synchronize(projection,p.world,[])
 assert any(r['kind']=='artifact_adopted' and r['source']==patch for r in doc['relations'])
 outsider=Projection(M1);outsider.record_outcome(outcome,p.world.state['software_events']);assert not outsider.relations
 rejected=Projection(M2);outcome['response']={'ok':False};rejected.record_outcome(outcome,p.world.state['software_events']);assert not rejected.relations
