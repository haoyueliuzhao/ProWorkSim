import copy,json,itertools
import pytest
from proworksim.software_project_navigation_v221 import RepositoryIndex
from proworksim.software_public_requirement_evidence_v221 import bind_check,summarize

def test_global_discovery_graph_expansion_and_incremental_invalidation():
 files={'alpha.py':'from beta import helper\nclass Alpha:\n def run(self): return helper()\n','beta.py':'def helper(): return 2\n','test_beta.py':'from beta import helper\ndef test_helper(): assert helper() == 2\n','unseen.py':'def Alpha_missing(): return 3\n'}
 x=RepositoryIndex('m1');v1={'object_id':'own','version_id':'v1'};assert x.update(files,v1)['parsed_files']==4
 graph={'actor':'m1','relations':[]};r=x.query('Alpha',project=graph,limit=4);assert {'alpha.py','unseen.py'}<=set(h['path'] for h in r['hits']);assert any(h['path']=='beta.py' for h in r['hits'])
 assert x.update(files,v1)['parsed_files']==0
 files.pop('beta.py');files['renamed.py']='def helper(): return 4\n';v2={**v1,'version_id':'v2'};s=x.update(files,v2);assert s['parsed_files']==1 and s['removed_files']==['beta.py'];assert not any(e['target']=='beta.py' for e in x.edges)
 assert all(h['file_sha256']==x.rows[h['path']]['sha256'] for h in x.query('helper')['hits'])
 with pytest.raises(ValueError):x.query('Alpha',project={'actor':'m2','relations':[]})

def test_syntax_failure_resource_bounds_and_no_execution():
 x=RepositoryIndex('m1',file_char_limit=80);x.update({'a.py':'raise RuntimeError("must never execute")\ndef Alpha(): pass\n','bad.py':'def Broken(\n','big.py':'Alpha\n'*100,'../secret.py':'secret'}, {'version_id':'v1'})
 assert x.rows['bad.py']['parse_status']=='syntax_unresolved';assert x.rows['big.py']['truncated'];assert '../secret.py' not in x.rows
 r=x.query('Alpha',max_chars=1500);assert len(json.dumps(r,ensure_ascii=False))<=1500 and r['coverage']['skipped_files']==1

def test_passed_test_is_not_semantic_coverage_and_versions_expire():
 e={'sequence':9,'kind':'test','actor_id':'m1','executed':True,'passed':True,'source_reference':{'version_id':'v1'},'files_sha256':'f1','entry_metadata_sha256':'m1'}
 b=bind_check(actor='m1',requirement_id='scope',requirements=['scope'],test_event=e,check_path='test_a.py',source_files={'test_a.py':'assert 1'},public_input='original input',expected_result='original expected output')
 current={k:e[k] for k in ('source_reference','files_sha256','entry_metadata_sha256')};r=summarize(['scope'],[b],current);assert r['requirements'][0]['checks'][0]['status']=='executed_passed_coverage_unverified' and not r['all_requirements_semantically_verified']
 current['files_sha256']='f2';assert summarize(['scope'],[b],current)['requirements'][0]['checks'][0]['status']=='historical_version'
 with pytest.raises(ValueError):bind_check(actor='m2',requirement_id='scope',requirements=['scope'],test_event=e,check_path='test_a.py',source_files={'test_a.py':''},public_input='x',expected_result='y')

def test_real_harness_permissions_navigation_and_test_binding(tmp_path):
 from test_role_baseline_world_v141 import prepare as substrate,M1,M2
 from test_organization_world_v211 import split,ok
 from test_organization_world_v212 import setup
 from proworksim import software_organization_world_v221 as world
 from proworksim.harness_port import HarnessPort
 p,_,_,runs=substrate(tmp_path);world.attach(p,['behavior','regression'])
 ports={m:HarnessPort(world.Port(p.world.session(m,world.PROJECT),m),m,project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in (M1,M2)}
 for port in ports.values():port.tools()
 n=itertools.count()
 def c(m,t,**args):return ports[m].call(t,request_key=f'v221-{next(n)}',association={},**args)
 split(c);setup(c,'behavior');setup(c,'regression');ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'create_file',path='private_only.py',text='def PrivateUnique(): return 1\n')
 before=copy.deepcopy(p.world.dynamic());a=ok(c,M1,'locate_work',query='PrivateUnique');b=ok(c,M2,'locate_work',query='PrivateUnique');assert any(h['path']=='private_only.py' for h in a['hits']);assert all(h['path']!='private_only.py' for h in b['hits']);assert p.world.dynamic()==before
 ok(c,M1,'run_tests');event=next(e for e in reversed(p.world.state['software_events']) if e['kind']=='test')
 row=ok(c,M1,'record_public_check',requirement_id='behavior',test_sequence=event['sequence'],check_path='test_sample.py',public_input='sample.value',expected_result='equals 2');assert row['passed'] and row['semantic_coverage']=='unverified_member_claim'
 own=ok(c,M1,'public_check_status');assert own['requirements'][0]['checks'][0]['current_version'];peer=ok(c,M2,'public_check_status');assert not peer['requirements'][0]['checks']
 patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Public fixed candidate')['patch_id']
 viewed=ok(c,M2,'locate_work',query='PrivateUnique',patch_id=patch);assert any(h['path']=='private_only.py' for h in viewed['hits']);assert all(h['next_read']['arguments']['patch_id']==patch for h in viewed['hits'])
 ok(c,M2,'open_patch_review',patch_id=patch);ok(c,M2,'run_patch_review_tests',patch_id=patch)
 peer_test=next(e for e in reversed(p.world.state['software_events']) if e['kind']=='test' and e['actor_id']==M2)
 ok(c,M2,'record_public_check',requirement_id='behavior',test_sequence=peer_test['sequence'],check_path='test_sample.py',public_input='sample.value',expected_result='equals 2')
 assert ok(c,M2,'public_check_status',patch_id=patch)['requirements'][0]['checks'][0]['current_version']
 assert not ok(c,M2,'public_check_status')['requirements'][0]['checks'][0]['current_version']
 ok(c,M1,'write_file',path='sample.py',text='value = 3\n');assert ok(c,M1,'public_check_status')['requirements'][0]['checks'][0]['status']=='historical_version'
 assert len(runs)==2

def test_binary_assets_do_not_exhaust_text_index_budget():
 x=RepositoryIndex('m1',total_char_limit=100)
 stats=x.update({'a.png':'X'*10000,'src/target.py':'def Target(): return 1\n'}, {'version_id':'v1'},entry_metadata={'a.png':{'kind':'file','encoding':'base64'},'src/target.py':{'kind':'file','encoding':'utf-8'}})
 assert 'src/target.py' in x.rows and 'a.png' not in x.rows
 assert stats['skipped_files']==[{'path':'a.png','reason':'non_text_or_non_regular_entry'}]
 assert x.query('Target')['hits'][0]['path']=='src/target.py'
