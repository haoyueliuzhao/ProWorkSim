import copy,importlib.util,json,sqlite3
from pathlib import Path
import pytest
from proworksim.software_project_navigation_v223_1 import RepositoryIndex
from proworksim.software_project_relations_v223_1 import Projection
from proworksim.software_public_feedback_v223_1 import compact
from proworksim.software_organization_api_v223_1 import Ledger,AdmissionStopped
R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('public_v2231',R/'tools/public_test_library_v223_1.py');library=importlib.util.module_from_spec(spec);spec.loader.exec_module(library)

def test_public_django_normalization_and_missing_nested_module(tmp_path):
 entry={'argv':['python','tests/runtests.py','--noinput','--parallel','1'],'cwd':'/testbed','hidden_material_used':False,'timeout_seconds':120}
 files={'tests/utils_tests/test_timezone.py':'class Example:\n def test_it(self): pass\n','tests/db_functions/__init__.py':'','tests/db_functions/datetime/test_extract_trunc.py':'','tests/utils_tests/__init__.py':''}
 for target,expected in [('tests.utils_tests.test_timezone','utils_tests.test_timezone'),('utils_tests.test_timezone.Example.test_it','utils_tests.test_timezone.Example.test_it'),('db_functions.datetime.test_extract_trunc','db_functions.datetime.test_extract_trunc')]:
  out,selection=library.selected_entry(entry,{'kind':'django','targets':[target]},files=files,entry_metadata={k:{'kind':'file'} for k in files});assert selection['targets']==[expected] and out['argv'][-1]==expected
 for bad in ('db_functions.test_datetime','utils_tests.test_timezone.Unknown','../secret','/private/tests'):
  with pytest.raises(ValueError):library.selected_entry(entry,{'kind':'django','targets':[bad]},files=files,entry_metadata={k:{'kind':'file'} for k in files})
 for path,text in files.items():p=tmp_path/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
 assert library.selected_entry(entry,{'kind':'django','targets':['tests.utils_tests.test_timezone']},root=tmp_path)[1]['targets']==['utils_tests.test_timezone']
 assert entry['argv'][-1]=='1'

def test_exact_class_symbol_not_lost_to_related_method_or_graph():
 files={'sets/contains.py':'class Contains:\n def as_set(self): raise NotImplementedError()\n','logic/boolalg.py':'class Boolean:\n def as_set(self):\n  return "as_set as_set Contains contains"\n','other.py':'from logic.boolalg import Boolean\nx=Boolean.as_set\n'}
 idx=RepositoryIndex('member_001');idx.update(files,{'version_id':'v1'})
 for use in (True,False):
  result=idx.query('Contains as_set class Contains',use_graph=use);assert result['hits'][0]['path']=='sets/contains.py' and result['hits'][0]['symbol']=='Contains'
 with pytest.raises(ValueError):idx.query('Contains',project={'actor':'member_002'})

def test_character_units_and_identity_stay_event_bound():
 p=Projection();p.apply({'sequence':1,'kind':'read','actor_id':'member_001','path':'x.py','start_character':4315,'end_character':7236,'source_reference':{'version_id':'v1'}});d=p.snapshot({},[]);r=d['relations'][0]
 assert r['details']=={'start_character':4315,'end_character':7236,'position_unit':'Unicode_characters','end_exclusive':True}
 p2=Projection();p2.restore(p.export());assert p2.snapshot({},[])==d

def test_failure_first_feedback_preserves_original_report_and_permissions():
 from proworksim.software_organization_v042 import build_test_report,test_result_page
 evidence={'sessions':[{'test_reports':[{'nodeid':f'test_{i}','outcome':'passed','phase':'call'} for i in range(100)]+[{'nodeid':'test_bad','outcome':'failed','phase':'call'}]}]}
 visible={'groups':{'public_repository_tests':{'status':'failed','output':'header\nFAILURES\nE AssertionError: expected 2 got 1','tests':[]}},'public_execution':{'execution':{'test_evidence':evidence}},'source_reference':{'object_id':'x','version_id':'v2'},'files_sha256':'sha','executed':True,'passed':False,'scope':'public','untested':[],'independent_acceptance':'not_run','fixed_submission_is_acceptance':False}
 report=build_test_report(visible,actor_id='member_001',event_identity={'world_id':'w','instance_id':'i','branch_id':'b','project_id':'p','actor_id':'member_001','test_event_sequence':5,'operation_id':'op'});original=copy.deepcopy(report);page=test_result_page(report);page['test_evidence']=evidence
 out=compact(report,page,'member_001');assert 'test_evidence' not in out and out['diagnostic_summary']['failed_tests'][0]['nodeid']=='test_bad';assert 'AssertionError' in out['diagnostic_summary']['excerpts'][0]['text']
 assert report==original and 'test_99' in report['body'];assert out['diagnostic_summary']['detail_pages']
 with pytest.raises(ValueError):compact(report,page,'member_002')

def test_full_pair_cash_release_does_not_wait_for_all_prefixes(tmp_path):
 path=tmp_path/'l';c=sqlite3.connect(path);c.executescript('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE slots(id TEXT PRIMARY KEY,token_limit INTEGER,status TEXT,hold INTEGER);CREATE TABLE requests(id TEXT PRIMARY KEY,slot TEXT,status TEXT,cost INTEGER,tokens INTEGER,body TEXT,provider_id TEXT UNIQUE);CREATE TABLE block_slots(slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT);INSERT INTO meta VALUES("cap","1100000000000");INSERT INTO slots VALUES("old",5000000,"closed",0);INSERT INTO requests VALUES("old","old","settled",782196896880,1,NULL,"old");');c.close();l=Ledger(path);l.reserve_panel()
 for i in range(3):l.reserve_pair(i)
 with pytest.raises(AdmissionStopped):l.reserve_pair(3)
 slot='v223.1:task-00:PREFIX';n=l.reserve_stage(slot);l.admit(slot,n)
 with l.db() as c:c.execute('INSERT INTO requests VALUES("p",?,"settled",1000000000,100000,NULL,"p")',(slot,))
 l.close(slot);assert l.finish_pair(0);l.reserve_pair(3)
 assert l.snapshot()['worst_exposure_CNY']<1100 and l.active_pairs()==3
 with pytest.raises((ValueError,AdmissionStopped)):l.reserve_stage(slot)

def test_frozen_worker_schema_and_repaired_handoff_surface(tmp_path):
 from proworksim import software_organization_runtime_v223_1 as rt
 for m in ('member_001','member_002'):assert len(rt.member_wire_tools('FREE2',m))==57
 assert 'assign_work (or offer_transfer)' in rt.CONTRACT
 from test_role_baseline_world_v141 import prepare
 from proworksim import software_organization_world_v223_1 as w
 p,_,_,_=prepare(tmp_path);w.attach(p,['behavior','regression'],condition='G')
 assessment={'decision':'keep','demand_types':['verification_gap'],'reason':'Use the existing owner; no transfer needed'}
 w.register_proposal(p.world,{'candidate_id':'k','keep':True,'actions':[],'decision_assessment':assessment},{'synthetic':True})
 view=w.Port(p.world.session('member_001',w.PROJECT),'member_001').observe()
 assert view['organization_decision_explanation']['reason']==assessment['reason'] and 'KEEP/DEFER' in view['organization_decision_explanation']['execution_boundary']


def test_settled_shared_prefix_releases_worst_reservation_while_pair_runs(tmp_path):
 path=tmp_path/'l';c=sqlite3.connect(path);c.executescript('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE slots(id TEXT PRIMARY KEY,token_limit INTEGER,status TEXT,hold INTEGER);CREATE TABLE requests(id TEXT PRIMARY KEY,slot TEXT,status TEXT,cost INTEGER,tokens INTEGER,body TEXT,provider_id TEXT UNIQUE);CREATE TABLE block_slots(slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT);INSERT INTO meta VALUES("cap","1100000000000");INSERT INTO slots VALUES("old",5000000,"closed",0);INSERT INTO requests VALUES("old","old","settled",782196896880,1,NULL,"old");');c.close();l=Ledger(path);l.reserve_panel()
 for i in range(3):l.reserve_pair(i)
 with pytest.raises(AdmissionStopped):l.reserve_pair(3)
 slot='v223.1:task-00:PREFIX';limit=l.reserve_stage(slot);l.admit(slot,limit)
 with l.db() as c:c.execute('INSERT INTO requests VALUES("p",?,"settled",30000000,200000,NULL,"p")',(slot,))
 l.reserve_pair(3);assert l.active_pairs()==4 and l.snapshot()['worst_exposure_CNY']<1100
 # An uncertain request does not release another shared-prefix allowance.
 before=l.snapshot()['worst_exposure_CNY'];l.reserve(slot,'unknown',100000);assert l.snapshot()['worst_exposure_CNY']==before
