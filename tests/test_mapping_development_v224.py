import copy,json,sqlite3,math
from pathlib import Path
import pytest
from proworksim.software_mapping_selector_v224 import initialize,evaluate,update,target,distribution,SPEC,structure_descriptor
from proworksim.software_mapping_gate_v224 import assess
from proworksim.software_mapping_api_v224 import Ledger,AdmissionStopped
from test_project_relations_v217 import decision_state,proposal
from proworksim.software_organization_generator_v217 import compile_target

def setup_bank():
 s=decision_state();s.update(team_remaining_tokens=3_500_000,conflict_count=0,reason_flags={'actual_code_progress':True,'subsequent_executed_public_test':True})
 a=compile_target(s,proposal(s,True));bank={'candidates':{'KEEP':{'keep':True,'target':s['graph'],'actions':[]},'C1':a},'remaining_branch_token_limit':3_500_000};return s,bank

def test_gate_requires_actual_cases_and_does_not_require_missing_setup():
 s,_=setup_bank();events=[{'sequence':1,'kind':'organization_v213:work_performed','actor_id':'member_001'},{'sequence':2,'kind':'test','actor_id':'member_001','executed':True,'public_execution':{'execution':{'counts':{'collected':0,'passed':0}}}}]
 assert not assess(s,events)['eligible']
 events[1]['public_execution']['execution']['counts']={'collected':2,'passed':1,'failed':1}
 assert assess(s,events)['eligible']
 assert not assess(s,events,terminal=True)['eligible']
 events.append({'sequence':3,'kind':'organization_v213:work_performed','actor_id':'member_001'});assert not assess(s,events)['eligible']

def test_complete_panel_updates_really_change_later_decisions_without_mutating_policy():
 s,b=setup_bank();p=initialize();before=copy.deepcopy(p);d=evaluate(s,b,p,33);assert p==before
 assert d['probabilities']==d['reference'];u={'KEEP':-.09,'C1':.93};t=target(d,u);assert max(t['N'].values())==0 and t['q_after']['C1']>d['probabilities']['C1']
 record={'index':0,'complete':True,'decision':d,'outcomes':{'KEEP':{'legal_correct':False,'logical_tokens':4_500_000},'C1':{'legal_correct':True,'logical_tokens':3_500_000}}}
 p1=update(p,[record],'dev1');d1=evaluate(s,b,p1,33);assert p1['update']==1 and d1['probabilities']['C1']>d['probabilities']['C1']
 t1=target(d1,u);assert t1['N']['KEEP']>0 and all(x>0 for x in t1['positive_N'].values())
 p2=update(p1,[{**record,'index':2,'decision':d1}],'dev2');assert p2['update']==2 and p==before
 assert all(q>=SPEC['delta']*d1['reference'][z] for z,q in d1['probabilities'].items())

def test_partial_singleton_and_degenerate_panels_never_fake_learning():
 s,b=setup_bank();p=initialize();d=evaluate(s,b,p,1)
 for record in ({'complete':False},{'complete':True,'outcomes':{'KEEP':{}},'decision':d},{'complete':True,'outcomes':{'KEEP':{},'C1':{}},'decision':{**d,'feature_degenerate':True}}):
  got=update(p,[record],'dev1');assert got['update']==0 and got['theta']==p['theta'] and got['history'][-1]['updated'] is False
 with pytest.raises(ValueError):target(d,{'KEEP':0})

def test_descriptors_and_features_do_not_learn_task_ids():
 s,b=setup_bank();d=evaluate(s,b,initialize(),77);rename={k:'renamed_'+k for k in s['graph']['work']}
 def rg(g):
  g=copy.deepcopy(g);g['work']={rename[k]:{**w,'children':[rename[x] for x in w.get('children',[])],'depends_on':[rename[x] for x in w.get('depends_on',[])]} for k,w in g['work'].items()};g['collaboration']=[[rename[e[0]],*e[1:]] for e in g['collaboration']];return g
 ss=copy.deepcopy(s);ss['graph']=rg(s['graph'])
 for r in ss['project_relations']['relations']:
  if r['source'] in rename:r['source']=rename[r['source']]
  if r['target'] in rename:r['target']=rename[r['target']]
 bb=copy.deepcopy(b)
 for k,c in bb['candidates'].items():c['target']=rg(c['target']);assert structure_descriptor(c)==structure_descriptor(b['candidates'][k])
 dd=evaluate(ss,bb,initialize(),77);assert dd['features']==d['features'] and dd['mapping_groups']==d['mapping_groups']

def make_ledger(tmp_path):
 p=tmp_path/'ledger';c=sqlite3.connect(p);c.executescript('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE slots(id TEXT PRIMARY KEY,token_limit INTEGER,status TEXT,hold INTEGER);CREATE TABLE requests(id TEXT PRIMARY KEY,slot TEXT,status TEXT,cost INTEGER,tokens INTEGER,body TEXT,provider_id TEXT UNIQUE);CREATE TABLE block_slots(slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT);INSERT INTO meta VALUES("cap","1100000000000");INSERT INTO slots VALUES("old",1,"closed",0);INSERT INTO requests VALUES("old","old","settled",813203976320,1,NULL,"old");');c.close();return Ledger(p)
def settled(l,slot,n):
 with l.db() as c:c.execute('INSERT INTO requests VALUES(?,?,"settled",?,?,NULL,?)',(slot,slot,n*2000,n,slot))
 l.close(slot)

def test_prepare_then_atomic_panel_preserves_complete_budget_and_confirmation(tmp_path):
 l=make_ledger(tmp_path);l.reserve_batch();l.reserve_prep(0);l.reserve_prep(1)
 for i in (0,1):
  for st,n in [('PREFIX',1_000_000),('GRAPH',10000),('GENERATOR',20000)]:
   slot=f'v224:task-{i:02d}:'+st;limit=l.reserve_stage(slot);l.admit(slot,limit);settled(l,slot,n)
  assert l.finish_block(f'prep-{i}')
 remaining=3_970_000;l.reserve_panel(0,['KEEP','C1','C2'],remaining)
 with pytest.raises(AdmissionStopped):l.reserve_panel(1,['KEEP','C1','C2'],remaining)
 for z in ('KEEP','C1','C2'):
  slot='v224:task-00:'+z;l.admit(slot,remaining);settled(l,slot,2_000_000)
 assert l.finish_block('panel-0');l.reserve_panel(1,['KEEP','C1','C2'],remaining)
 assert l.snapshot()['worst_exposure_CNY']<=1000 and l.snapshot()['confirmation_preserved_CNY']==100
 with pytest.raises((ValueError,AdmissionStopped)):l.reserve_stage('v224:task-00:PREFIX')

def test_window_utility_rejects_unknown_not_treating_it_as_failure():
 s,b=setup_bank();d=evaluate(s,b,initialize(),3)
 r={'index':0,'complete':True,'decision':d,'outcomes':{'KEEP':{'legal_correct':None,'logical_tokens':100},'C1':{'legal_correct':True,'logical_tokens':100}}}
 with pytest.raises(ValueError):update(initialize(),[r],'bad')


def test_mapping_novelty_uses_group_mass_not_candidate_count_or_ids():
 s,b=setup_bank();d=evaluate(s,b,initialize(),8);d['probabilities']={'KEEP':.8,'C1':.2};d['mapping_groups']={'KEEP':(1,2),'C1':(1,2)};d['structure_groups']={'KEEP':'one','C1':'two'}
 out=target(d,{'KEEP':0.,'C1':0.});assert out['N_mapping']=={'KEEP':0.,'C1':0.}
 assert out['N_structure']['C1']==pytest.approx(math.log(.5/.2));assert out['N']['C1']==pytest.approx(.5*math.log(.5/.2))
