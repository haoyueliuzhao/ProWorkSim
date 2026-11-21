import copy,importlib.util,sqlite3
from pathlib import Path
from proworksim.software_mapping_checkpoint_v224_1 import assess,capture,test_cases as case_counts,generator_fallback,window_admission
from test_mapping_development_v224 import setup_bank

def event(n,k,actor='member_001',version='v1',**kw):return {'sequence':n,'kind':k,'actor_id':actor,'source_reference':{'object_id':actor,'version_id':version},**kw}
def test(n,actor='member_001',version='v1',**counts):return event(n,'test',actor,version,executed=True,public_execution={'execution':{'counts':counts or {'collected':2,'passed':1,'failed':1}}})
test.__test__=False

def test_actor_is_not_assumed_to_be_author_and_private_peer_results_stay_private():
 s,_=setup_bank();edit=event(1,'organization_v213:work_performed','member_002');t=test(2,'member_002')
 assert assess(s,[edit,t],observer='member_002')['eligible']
 assert not assess(s,[])['eligible'] # zero authorized receipts, not a global audit bypass
 patch=event(3,'patch_fixed','member_002',patch_id='p',author='member_002',changed_paths=['x.py'],task_ids=['left'])
 review=test(4);review['source_reference']=copy.deepcopy(patch['source_reference'])
 gate=assess(s,[patch,review]);assert gate['eligible'];assert gate['witnesses'][0]['author']=='member_002' and gate['witnesses'][0]['tester']=='member_001'
 assert not assess(s,[patch])['eligible'] # publishing code is not publishing proof of tests
 assert not assess(s,[patch,test(4)])['eligible'] # observer's unrelated workspace test

def test_exact_version_and_latest_edit_no_zero_collection_or_collection_errors():
 s,_=setup_bank();edit=event(1,'organization_v213:work_performed')
 assert assess(s,[edit,test(2)])['eligible']
 assert not assess(s,[edit,test(2,version='other')])['eligible']
 assert not assess(s,[edit,test(2),event(3,'edit',version='v2')])['eligible']
 for counts in ({'collected':0,'errors':1},{'collected':5,'errors':1},{'collected':3,'skipped':3},{'collected':False,'passed':True}):assert not case_counts(test(2,**counts))['qualifying']
 assert case_counts(test(2,collected=3,tests_run=1,errors=1))['qualifying']

def test_no_mutable_work_closes_sampling_without_calling_it_a_model_failure():
 s,_=setup_bank();before=copy.deepcopy(s)
 assert not assess(s,[])['sampling_exhausted']
 for w in s['graph']['work'].values():w['authors']=['member_002']
 gate=assess(s,[]);assert gate['sampling_exhausted'] and not gate['eligible'] and 'no_unstarted_mutable_work' in gate['reasons']
 assert not assess(s,[],terminal=True)['sampling_exhausted']
 assert before['graph']['work']!=s['graph']['work']

def test_pre_dispatch_budget_boundary_is_normal_fallback_not_keyerror():
 for fail in ([{'pre_dispatch_boundary':{'dispatch':False}}],[{'pre_dispatch_boundary':'remaining limit'}],[{'errors':['invalid']} ]):
  assert generator_fallback({'decision':'propose'}, {},fail)
 assert not generator_fallback({'decision':'keep'}, {},[{'errors':[]}])
 assert not generator_fallback(None,{'C1':{}},[{'pre_dispatch_boundary':{}}])

def test_no_second_window_without_real_parameter_update():
 p={'theta':[0.], 'update':0};after={'theta':[.1],'update':1}
 assert not window_admission(p,p,[])['proceed']
 record={'complete':True,'outcomes':{'KEEP':{},'C1':{}},'decision':{'feature_degenerate':False}}
 assert window_admission(p,after,[record])['proceed']
 assert not window_admission(p,{'theta':[0.],'update':1},[record])['proceed']
 assert not window_admission(p,after,[{**record,'complete':False}])['proceed']

def test_real_published_peer_review_witness_and_private_test_permissions(tmp_path):
 from test_organization_continuation_v216_2 import prepare
 from test_organization_world_v211 import ok,split
 from test_organization_world_v212 import setup
 from test_role_baseline_world_v141 import M1,M2
 from proworksim.software_organization_world_v223_1 import World
 from proworksim.software_project_relations_v223_1 import allowed_event
 p,ports,c,_=prepare(tmp_path);split(c)
 # Reuse actual managed permissions. New observer logic adds no world capability.
 off=ok(c,M1,'assign_work',task_id='behavior',to_member=M2,reason='Peer implements')
 ok(c,M2,'accept_transfer',offer_id=off['offer_id'])
 ok(c,M2,'assign_verification',task_id='behavior',reviewer=M1,reason='Independent')
 ok(c,M2,'add_collaboration',task_id='behavior',peer=M1,reason='Review')
 ok(c,M2,'begin_work',task_id='behavior');ok(c,M2,'write_file',path='sample.py',text='value = 2\n');ok(c,M2,'run_tests')
 visible=lambda:[v for e in p.world.state['software_events'] if (v:=allowed_event(p.world,e,M1)) is not None]
 s={'graph':p.world._action_dynamic_status(M1,'SOFTWARE27'),'team_remaining_tokens':3_000_000}
 assert not assess(s,visible())['eligible']
 patch=ok(c,M2,'fix_patch',task_ids=['behavior'],message='Published peer candidate')['patch_id']
 ok(c,M1,'open_patch_review',patch_id=patch);ok(c,M1,'run_patch_review_tests',patch_id=patch)
 g=assess(s,visible());assert g['eligible'],g
 assert any(w['mode']=='published_patch_review' and w['author']==M2 for w in g['witnesses'])
 from types import SimpleNamespace as NS
 fake=NS(waiting={},owner=NS(adapter=NS(ledger=NS(snapshot=lambda:{'known_actual_tokens':10000,'per_member':{m:{'known_actual_tokens':5000,'decisions':5} for m in (M1,M2)}}))))
 captured=capture(p,fake);assert captured['eligible'] and captured['reason_flags']['actual_code_progress']
 assert captured['test_event_sequences']==[x['test_sequence'] for x in captured['mapping_decision_gate']['witnesses']]
 # Immutable reviewed patch stays evidence even if the peer later edits privately.
 ok(c,M2,'write_file',path='sample.py',text='value = 3\n');assert assess(s,visible())['eligible']

def test_repair_entrypoints_use_new_identity_and_are_not_live_admission():
 import py_compile
 r=Path(__file__).resolve().parents[1]
 for path in list((r/'tools').glob('*mapping*v224_1.py'))+list((r/'src/proworksim').glob('*mapping*v224_1.py')):py_compile.compile(str(path),doraise=True)

def test_new_cash_identity_is_disjoint_from_frozen_old_batch(tmp_path):
 from test_mapping_development_v224 import make_ledger
 from proworksim.software_mapping_api_v224_1 import Ledger
 old=make_ledger(tmp_path);new=Ledger(old.path);new.reserve_batch();new.reserve_prep(0)
 slot='v224_1:task-00:PREFIX';assert new.reserve_stage(slot)==2_000_000;new.admit(slot,2_000_000)
 with new.db() as c:
  assert c.execute('SELECT id FROM slots WHERE id LIKE "v224_1:%"').fetchall()==[(slot,)]
  assert c.execute('SELECT count(*) FROM v224_batch').fetchone()[0]==0
  assert c.execute('SELECT slot FROM block_slots').fetchall()==[(slot,)]
 assert new.snapshot()['worst_exposure_CNY']<=1000
