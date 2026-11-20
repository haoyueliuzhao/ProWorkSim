import copy,json,sqlite3
import pytest
from proworksim.software_project_information_v222 import prepare_context,type_relations
from proworksim.software_organization_api_v222 import Ledger,ENVELOPE

def test_information_tiers_and_private_actor_boundary():
 state={'graph':{'work':{'work_root':{'owner':'member_001','reviewer':None,'scope':['scope'],'authors':[]}}},'project_relations':{'actor':'member_001','relations':[{'id':'e1','kind':'work_code_region','source':'work_root','target':'a.py','source_event':1,'version':{'version_id':'v1'},'fact_status':'observed','visible_to':'member_001'},{'id':'e3','kind':'work_requires_claim','source':'work_root','target':'another','fact_status':'member_claim','visible_to':'member_001'}]}}
 files={'a.py':'from b import Helper\ndef Alpha(): return Helper()\n','b.py':'def Helper(): return 1\n'};kw=dict(files=files,source_reference={'version_id':'v1'},entry_metadata={},public_query='Alpha')
 L,l=prepare_context(state,'L',**kw);G,g=prepare_context(state,'G',**kw)
 assert not L['navigation']['graph_expansion'] and G['navigation']['graph_expansion']
 assert len(L['project_relations']['relations'])==1
 assert {r['evidence_level'] for r in G['project_relations']['relations']}=={'E1','E2','E3'}
 assert all(not r.get('semantic_dependency_proven',False) for r in G['project_relations']['relations'])
 assert state['project_relations']['relations'][0].get('evidence_level') is None
 bad=copy.deepcopy(state['project_relations']);bad['relations'][0]['visible_to']='member_002'
 with pytest.raises(ValueError):type_relations(bad)
 assert g['estimated_index_object_bytes']>0

def fixture_ledger(tmp_path):
 p=tmp_path/'ledger.sqlite';c=sqlite3.connect(p);c.executescript('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE slots(id TEXT PRIMARY KEY,token_limit INTEGER,status TEXT,hold INTEGER);CREATE TABLE requests(id TEXT PRIMARY KEY,slot TEXT,status TEXT,cost INTEGER,tokens INTEGER,body TEXT,provider_id TEXT UNIQUE);CREATE TABLE block_slots(slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT);INSERT INTO meta VALUES("cap","1100000000000");');c.commit();c.close();return Ledger(p)

def settle_fake(l,slot,n):
 with l.db() as c:
  c.execute('INSERT INTO requests VALUES(?,?,"settled",?,?,NULL,?)',(slot+':req',slot,n*8000,n,slot+':provider'))
 l.close(slot)

def test_four_pair_worst_budget_stage_conservation_and_no_replay(tmp_path):
 l=fixture_ledger(tmp_path);l.reserve_panel();assert l.snapshot()['worst_exposure_CNY']==320
 for i in range(4):
  base=f'v222:task-{i:02d}:';p=base+'PREFIX';n=l.reserve_stage(p);assert n==2_000_000;l.admit(p,n);settle_fake(l,p,1_234_567)
  for z in ('L','G'):
   g=base+'GEN-'+z;n=l.reserve_stage(g);l.admit(g,n);settle_fake(l,g,12_345)
   s=base+z;n=l.reserve_stage(s);assert n+1_234_567+12_345==5_000_000;l.admit(s,n);settle_fake(l,s,n)
   with pytest.raises(ValueError):l.reserve_stage(s)
 assert l.snapshot()['worst_exposure_CNY']==320
 assert l.finish();assert l.snapshot()['worst_exposure_CNY']==(40_000_000-4*1_234_567)*.000008
 with pytest.raises(Exception):l.reserve_stage('v222:task-04:PREFIX')
 with pytest.raises(Exception):l.reserve_panel()

def test_unsettled_predecessor_does_not_unlock_and_unknown_holds(tmp_path):
 l=fixture_ledger(tmp_path);l.reserve_panel();s='v222:task-00:PREFIX';n=l.reserve_stage(s);l.admit(s,n)
 with pytest.raises(ValueError):l.reserve_stage('v222:task-00:GEN-L')
 l.reserve(s,'unknown',100);l.close(s);assert not l.finish();assert l.snapshot()['worst_exposure_CNY']==320


def test_same_schema_prompt_and_model_history_binding():
 from proworksim import software_organization_runtime_v222 as rt,software_organization_world_v222 as w
 from proworksim import software_organization_world_v221 as prior
 assert w.tool_definitions is prior.tool_definitions
 for member in ('member_001','member_002'):
  assert len(rt.member_wire_tools('FREE2',member))==57
 assert 'information_condition' not in rt.CONTRACT

def test_actual_matched_navigation_and_cost_events(tmp_path):
 from test_role_baseline_world_v141 import prepare
 from proworksim import software_organization_world_v222 as world
 p,_,_,_=prepare(tmp_path);world.attach(p,['behavior','regression'],condition='L')
 before=copy.deepcopy(p.world.dynamic())
 l=p.world._action_locate_work('member_001',world.PROJECT,query='value')
 assert not l['graph_expansion']
 p.world.information_condition='G';g=p.world._action_locate_work('member_001',world.PROJECT,query='value')
 assert g['graph_expansion'] and g['source_reference']==l['source_reference']
 events=p.world.state['software_events'][-2:]
 assert events[0]['cold_build'] and not events[1]['cold_build']
 assert events[0]['estimated_initial_index_bytes']>0 and all(e['no_workspace_change'] for e in events)
 assert p.world.dynamic()==before
