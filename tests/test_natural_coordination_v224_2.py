import copy
from proworksim.software_natural_checkpoint_v224_2 import assess,effective_alternative,effect_signature,keep_bank
from test_mapping_development_v224 import setup_bank
from test_mapping_checkpoint_v224_1 import event

def test_planning_after_actual_read_needs_no_edit_test_or_unstarted_leaf():
 s,_=setup_bank();read=event(1,'read',path='x.py',start_character=0,end_character=20)
 assert assess(s,[read])['eligible']
 for w in s['graph']['work'].values():w['authors']=['member_002']
 gate=assess(s,[read]);assert gate['eligible'] and not gate['sampling_exhausted'] and gate['remaining_unstarted_work']==[]
 assert not assess(s,[read],terminal=True)['eligible']
 assert not assess(s,[{**read,'end_character':0}])['eligible']
 assert not assess(s,[event(1,'work_message',body='I read code')])['eligible']

def test_keep_fallback_preserves_the_rest_of_five_million_not_new_budget():
 s,_=setup_bank();bank=keep_bank(s,prefix_tokens=1_980_000,source_reference={'path':'source'},checkpoint_reference={'path':'checkpoint'},reason='No supported change')
 assert bank['remaining_branch_token_limit']==3_020_000 and bank['actual_generator_tokens']==bank['shared_graph_tokens']==0
 assert set(bank['candidates'])=={'KEEP'} and bank['fallback_is_not_model_keep_endorsement']
 assert bank['candidates']['KEEP']['target']==s['graph']

def test_published_artifact_adoption_counts_as_effect_but_setup_only_does_not():
 s,_=setup_bank();a={'target':copy.deepcopy(s['graph']),'actions':[]}
 assert not effective_alternative(s,a)
 b={**a,'planned_adoptions':[{'actor':'member_001','task_id':'left','patch_id':'p1'}]}
 assert effective_alternative(s,b) and effect_signature(a)!=effect_signature(b)
 c=copy.deepcopy(a);c['target']['work']['left']['reviewer']='member_002'
 assert not effective_alternative(s,c)

def prepare(tmp_path):
 import itertools
 from test_role_baseline_world_v141 import prepare as substrate
 from proworksim import software_natural_organization_world_v224_2 as w
 from proworksim.harness_port import HarnessPort
 p,_,_,calls=substrate(tmp_path);w.attach(p,['behavior','regression'],condition='G');ports={m:HarnessPort(w.Port(p.world.session(m,w.PROJECT),m),m,project_id=w.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in ('member_001','member_002')}
 for port in ports.values():port.tools()
 n=itertools.count()
 return p,lambda m,t,**kw:ports[m].call(t,request_key='natural-'+str(next(n)),association={},**kw),calls

def test_real_joint_consent_before_any_edit_test_and_keep_guard(tmp_path):
 from test_organization_world_v211 import ok,no,split
 from test_role_baseline_world_v141 import M1,M2
 from proworksim.software_natural_organization_world_v224_2 import register_proposal
 p,c,calls=prepare(tmp_path);split(c)
 off=ok(c,M1,'offer_joint_arrangement',task_id='behavior',to_member=M2,reviewer=M1,mode='implementation',expected_revision=1,reason='Natural initial allocation')
 assert p.world._task('behavior')['owner']==M1 and not calls
 ok(c,M2,'accept_joint_arrangement',offer_id=off['offer_id']);assert p.world._task('behavior')['owner']==M2
 assert not any(e['kind'] in ('edit','test') for e in p.world.state['software_events'])
 register_proposal(p.world,{'candidate_id':'k','keep':True,'actions':[]},{'test':True});ok(c,M1,'select_arrangement',candidate_id='k',decision='keep',reason='Preserve')
 no(c,M1,'offer_joint_arrangement','kept_arrangement_frozen',task_id='regression',to_member=M2,reviewer=M1,mode='implementation',expected_revision=1,reason='Must not override KEEP')

def test_authorship_and_private_work_are_not_removed_by_timing_relaxation(tmp_path):
 from test_organization_world_v211 import ok,no,split
 from test_organization_world_v212 import setup
 from test_role_baseline_world_v141 import M1,M2
 p,c,_=prepare(tmp_path);split(c);setup(c,'behavior');ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n')
 before=copy.deepcopy(p.world.dynamic()['work']['behavior'])
 no(c,M1,'offer_joint_arrangement','joint_authored_work_unsupported',task_id='behavior',to_member=M2,reviewer=M1,mode='implementation',expected_revision=1,reason='Must preserve author')
 assert p.world.dynamic()['work']['behavior']==before

def test_sdk_contract_and_tool_surface_match_relaxed_world():
 from proworksim import software_natural_organization_runtime_v224_2 as rt
 from proworksim import software_organization_runtime_v223_1 as old
 assert 'require actual code progress followed by an executed public test' not in rt.CONTRACT
 assert 'which requires real edit/test progress' not in rt.CONTRACT
 assert len(rt.member_wire_tools('FREE2','member_001'))==len(old.member_wire_tools('FREE2','member_001'))==57
 assert 'No prior code edit or test' in next(t['function']['description'] for t in rt.member_wire_tools('FREE2','member_001') if t['function']['name']=='offer_joint_arrangement')

def test_real_compiler_accepts_adoption_only_without_unstarted_work():
 from proworksim.software_organization_generator_v217 import compile_target
 from proworksim.software_organization_planning_v223 import parse
 from proworksim.software_project_relations_v217 import identity
 import json
 s,_=setup_bank()
 for w in s['graph']['work'].values():
  if not w.get('children'):w['authors']=[w['owner']]
 rel={'id':'published-peer','kind':'work_fixed_artifact','source':'left','target':'patch-peer','source_event':9,'details':{'author':'member_002'}}
 s['project_relations']['relations'].append(rel);s['project_relations']['graph_id']=identity(s['project_relations']['relations'])
 proposal={'reason':'Adopt the visible peer candidate into the integration workspace','remaining_work':[],'dependencies':[],'adoptions':[{'actor':'member_001','patch_id':'patch-peer','task_id':'left'}],'basis':{'graph_id':s['project_relations']['graph_id'],'relation_ids':['published-peer'],'trigger_events':[9],'need':'Published contribution not adopted','expected_benefit':'Unproven integration benefit','switch_cost':'Actual adoption and checks'}}
 raw={'assessment':{'decision':'propose','demand_types':['integration_conflict'],'reason':'Visible artifact handoff'},'candidates':[proposal]};normalized,_=parse(json.dumps(raw),s);c=compile_target(s,normalized['candidates'][0]);assert effective_alternative(s,c)
 assert c['target']==s['graph'] and any(a['tool']=='integrate_patch' for a in c['actions'])
 assert all(c['target']['work'][k]['authors']==w['authors'] for k,w in s['graph']['work'].items())

def test_zero_call_preparation_stages_keep_exact_remaining_task_reservation(tmp_path):
 from test_mapping_development_v224 import make_ledger,settled
 from proworksim.software_mapping_api_v224_2 import Ledger
 l=Ledger(make_ledger(tmp_path).path);l.reserve_batch();l.reserve_prep(0)
 for st,n in [('PREFIX',1_950_000),('GRAPH',0),('GENERATOR',0)]:
  slot='v224_2:task-00:'+st;cap=l.reserve_stage(slot);l.admit(slot,cap)
  if n:settled(l,slot,n)
  else:l.close(slot)
 assert l.finish_block('prep-0');l.reserve_panel(0,['KEEP'],3_050_000)
 with l.db() as c:
  assert c.execute('SELECT token_limit FROM block_slots WHERE slot="v224_2:task-00:KEEP"').fetchone()==(3_050_000,)
  assert c.execute('SELECT count(*) FROM requests WHERE slot IN ("v224_2:task-00:GRAPH","v224_2:task-00:GENERATOR")').fetchone()==(0,)

def test_no_parameter_update_does_not_block_remaining_planned_tasks():
 from proworksim.software_natural_checkpoint_v224_2 import next_window_context
 p={'theta':[0.],'update':0};x=next_window_context(p,p,[])
 assert x['continue_planned_tasks'] and x['next_window_purpose']=='additional_observation_with_unchanged_policy' and not x['proceed']
 after={'theta':[.1],'update':1};record={'complete':True,'outcomes':{'KEEP':{},'C1':{}},'decision':{'feature_degenerate':False}}
 assert next_window_context(p,after,[record])['next_window_purpose']=='updated_policy_validation'
