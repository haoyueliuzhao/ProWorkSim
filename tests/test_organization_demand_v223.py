import copy,json,sqlite3
import pytest
from proworksim.software_organization_demand_v223 import inspect_state,Timeline
from proworksim.software_organization_planning_v223 import add_hypotheses,historical_worker_context,tool,parse
from proworksim.software_organization_api_v223 import Ledger
from test_project_pilot_v222 import settle_fake
from test_project_relations_v217 import decision_state

def state():
 s=decision_state();s.update(reason_flags={'actual_code_progress':True,'subsequent_executed_public_test':True},team_remaining_tokens=3_000_000,conflict_count=0)
 return s

def test_demand_not_execution_and_duplicate_suppression():
 s=state();s['reason_flags']['actual_code_progress']=False;t=Timeline();a=t.update(s,s['project_relations'])
 assert a['assessment']['demand_detected'] and not a['reconsideration_event']
 s['reason_flags']['actual_code_progress']=True;b=t.update(s,s['project_relations'])
 assert b['reconsideration_event'] and not t.update(s,s['project_relations'])['reconsideration_event']
 restored=Timeline();restored.restore(t.export());assert not restored.update(s,s['project_relations'])['reconsideration_event']
 assert not inspect_state(s,terminal=True)['proposal_generation_admissible']
 s['team_remaining_tokens']=100;assert not inspect_state(s)['proposal_generation_admissible']

def test_failure_counts_and_normal_dependency_are_not_mismatch_evidence():
 s=state()
 for w in s['graph']['work'].values():w['reviewer']='member_002' if w['owner']=='member_001' else 'member_001'
 # Only one untouched package: no load-imbalance heuristic.
 s['graph']['work']['other']['owner']='member_002';s['graph']['work']['other']['reviewer']='member_001'
 s['test_failure_count']=999
 assert not inspect_state(s)['demands']
 s['graph']['work']['left']['depends_on']=['done'];s['graph']['work']['done']['owner']='member_002'
 assert not any(x['type']=='dependency_bottleneck' for x in inspect_state(s)['demands'])
 s['visible_blockages']=[{'task_id':'left','upstream_task':'done','source_receipt':{'id':'actual-blocked-action'}}]
 assert any(x['type']=='dependency_bottleneck' for x in inspect_state(s)['demands'])

def test_graph_claims_remain_e3_and_cannot_invent_private_sources():
 s=state();s['project_relations']['relations'][0]['evidence_level']='E1';r=s['project_relations']['relations'][0]
 data={'hypotheses':[{'work_ids':['left'],'evidence_ids':[r['id']],'claim':'Possible interface coupling, not proved'}]}
 result=add_hypotheses(s,data);new=result['project_relations']['relations'][-1]
 assert new['evidence_level']=='E3' and not new['semantic_dependency_proven'] and len(result['project_relations']['relations'])==len(s['project_relations']['relations'])+1
 assert result['graph']==s['graph']
 data['hypotheses'][0]['evidence_ids']=['hidden-peer-event']
 with pytest.raises(ValueError):add_hypotheses(s,data)

def test_actual_worker_history_and_identical_proposal_grammar():
 r={'physical_id':'req1','payload':{'member_id':'member_001','usage_id':'agent','wire':{'messages':[{'role':'user','content':'actually observed'}]}}}
 h=historical_worker_context(r);assert h['messages']==r['payload']['wire']['messages'];h['messages'][0]['content']='mutated';assert r['payload']['wire']['messages'][0]['content']=='actually observed'
 r['payload']['member_id']='member_002'
 with pytest.raises(ValueError):historical_worker_context(r)
 s=state();s['proposal_tool_schemas']={}
 payload={'assessment':{'decision':'keep','demand_types':['verification_gap'],'reason':'Ordinary setup suffices'},'candidates':[]}
 assert parse(json.dumps(payload),s)[0]==payload
 assert tool(s)==tool(copy.deepcopy(s))
 with pytest.raises(ValueError):parse('{"assessment":{},"assessment":{},"candidates":[]}',s)

def test_shared_graph_charged_to_both_logical_branches_paid_once(tmp_path):
 p=tmp_path/'ledger';c=sqlite3.connect(p);c.executescript('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE slots(id TEXT PRIMARY KEY,token_limit INTEGER,status TEXT,hold INTEGER);CREATE TABLE requests(id TEXT PRIMARY KEY,slot TEXT,status TEXT,cost INTEGER,tokens INTEGER,body TEXT,provider_id TEXT UNIQUE);CREATE TABLE block_slots(slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT);INSERT INTO meta VALUES("cap","1100000000000");');c.close();l=Ledger(p);l.reserve_panel()
 for i in range(4):
  b=f'v223:task-{i:02d}:'
  for suffix,n in [('PREFIX',1_234_567),('GRAPH',12345)]:
   slot=b+suffix;limit=l.reserve_stage(slot);l.admit(slot,limit);settle_fake(l,slot,n)
  for z in ('W0','W1'):
   slot=b+'GEN-'+z;limit=l.reserve_stage(slot);l.admit(slot,limit);settle_fake(l,slot,23456)
   slot=b+z;limit=l.reserve_stage(slot);assert limit+1_234_567+12345+23456==5_000_000;l.admit(slot,limit);settle_fake(l,slot,limit)
   with pytest.raises(ValueError):l.reserve_stage(slot)
 assert l.finish();assert l.snapshot()['worst_exposure_CNY']==(40_000_000-4*(1_234_567+12345))*.000008

def test_continuation_and_checkpoint_gate_wiring():
 from pathlib import Path
 r=Path(__file__).resolve().parents[1]
 s=(r/'tools/run_organization_demand_episode_v223.py').read_text()
 assert 'prefix_checkpoint_opportunities' not in s and 'precommitted_prefix_boundary' not in s
 assert "bank['shared_graph_tokens']" in s and "condition='G'" in s
 assert 'software_organization_runtime_v222_1' in s and 'historical_worker_context(doc)' in s
