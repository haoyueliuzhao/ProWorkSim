import itertools,copy
import pytest
from test_role_baseline_world_v141 import prepare as substrate,M1,M2
from test_organization_world_v211 import ok,no
from test_organization_world_v212 import setup
from proworksim import software_organization_world_v216 as world
from proworksim.harness_port import HarnessPort

def prepare(p):
 prepared,_,_,runs=substrate(p);world.attach(prepared,['behavior','regression'])
 ports={m:HarnessPort(world.Port(prepared.world.session(m,world.PROJECT),m),m,project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in (M1,M2)}
 for p in ports.values():p.tools()
 counter=itertools.count()
 def call(m,t,**a):return ports[m].call(t,request_key=f'v216-{next(counter)}',association={},**a)
 return prepared,ports,call,runs

def test_readiness_then_explicit_submit_is_terminal(tmp_path):
 p,ports,c,_=prepare(tmp_path);setup(c,'work_root');ok(c,M1,'begin_work',task_id='work_root');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'run_tests');fix=ok(c,M1,'fix_patch',task_ids=['work_root'],message='Real candidate');ok(c,M1,'complete_work',task_id='work_root',patch_id=fix['patch_id'])
 ok(c,M2,'open_patch_review',patch_id=fix['patch_id']);ok(c,M2,'run_patch_review_tests',patch_id=fix['patch_id']);ok(c,M2,'org_review_patch',patch_id=fix['patch_id'],decision='accept',reason='Actual same-version checks')
 r=ok(c,M1,'delivery_readiness');assert r['ready_to_submit'] and p.world.protocol()['terminal'] is None
 ok(c,M1,'submit_integration',message='Explicit formal submission');assert p.world.protocol()['terminal']=='DELIVERED'
 no(c,M1,'run_tests','episode_terminal');assert ok(c,M2,'delivery_readiness')['state']=='DELIVERED'

def test_proposal_is_not_consent_and_choice_can_decline(tmp_path):
 p,_,c,_=prepare(tmp_path);before=copy.deepcopy(p.world.dynamic())
 world.register_proposal(p.world,{'candidate_id':'candidate-a','keep':False,'actions':[]},{'synthetic_control':True})
 no(c,M1,'assign_verification','explicit_arrangement_choice_required',task_id='work_root',reviewer=M2,reason='Choice first')
 ok(c,M1,'select_arrangement',candidate_id='candidate-a',decision='keep',reason='Decline suggested change')
 assert p.world.dynamic()==before
 setup(c,'work_root');assert p.world.protocol()['choice']['decision']=='keep'
 no(c,M2,'abort_episode','final_integrator_required',reason='Not authorized actor')
 ok(c,M1,'abort_episode',reason='Explicit synthetic abandonment');assert p.world.protocol()['terminal']=='ABORTED'

def test_conflict_reopen_new_version_refresh_evidence_and_deliver(tmp_path):
 # Three-anchor synthetic conflict and evidence regression, zero API.
 from test_role_baseline_world_v141 import prepare as raw
 p,_,_,runs=raw(tmp_path/'three');world.attach(p,['a','b','checks']);ports={m:HarnessPort(world.Port(p.world.session(m,world.PROJECT),m),m,project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in (M1,M2)}
 for port in ports.values():port.tools()
 seq=itertools.count()
 def c(m,t,**kw):return ports[m].call(t,request_key='repair-'+str(next(seq)),association={},**kw)
 ok(c,M1,'split_work',task_id='work_root',children=[{'task_id':x,'description':x,'scope':[x]} for x in ('a','b','checks')],reason='Synthetic three obligations')
 off=ok(c,M1,'assign_work',task_id='b',to_member=M2,reason='Partner contribution');ok(c,M2,'accept_transfer',offer_id=off['offer_id'])
 for tid,owner,reviewer in [('a',M1,M2),('b',M2,M1),('checks',M1,M2)]:setup(c,tid,owner,reviewer)
 patches={}
 for tid,actor,text in [('a',M1,'value = 2\n'),('b',M2,'value = 2  # peer\n')]:
  ok(c,actor,'begin_work',task_id=tid);ok(c,actor,'write_file',path='sample.py',text=text);ok(c,actor,'run_tests');patch=ok(c,actor,'fix_patch',task_ids=[tid],message='Actual independent contribution')['patch_id'];ok(c,actor,'complete_work',task_id=tid,patch_id=patch);patches[tid]=patch
 for actor,patch in [(M2,patches['a']),(M1,patches['b'])]:
  ok(c,actor,'open_patch_review',patch_id=patch);ok(c,actor,'run_patch_review_tests',patch_id=patch);ok(c,actor,'org_review_patch',patch_id=patch,decision='accept',reason='Actual immutable checks')
 t=p.world._latest_same_version_test(M1,p.world.org_current_identity(M1));old_e=ok(c,M1,'complete_evidence',task_id='checks',requirements=['checks'],test_sequence=t['sequence'],reason='Original public evidence')
 merged=ok(c,M1,'integrate_patch',patch_id=patches['b']);assert merged['conflict_count']==1
 assert not ok(c,M1,'delivery_readiness')['ready_to_submit']
 no(c,M1,'submit_integration','unresolved_integration_conflict',message='Cannot bypass conflict')
 ok(c,M1,'reopen_work',task_id='a',reason='Resolve integration conflict');ok(c,M1,'begin_work',task_id='a');ok(c,M1,'write_file',path='sample.py',text='value = 2  # resolved\n');ok(c,M1,'run_tests');new=ok(c,M1,'fix_patch',task_ids=['a'],message='New resolved version')['patch_id'];ok(c,M1,'complete_work',task_id='a',patch_id=new)
 ok(c,M2,'open_patch_review',patch_id=new);ok(c,M2,'run_patch_review_tests',patch_id=new);ok(c,M2,'org_review_patch',patch_id=new,decision='accept',reason='Fresh repaired version')
 assert not ok(c,M1,'delivery_readiness')['ready_to_submit']
 ok(c,M1,'reopen_work',task_id='checks',reason='Evidence must match final tree');ok(c,M1,'run_tests');t=p.world._latest_same_version_test(M1,p.world.org_current_identity(M1));e=ok(c,M1,'complete_evidence',task_id='checks',requirements=['checks'],test_sequence=t['sequence'],reason='New final tree evidence')
 no(c,M2,'adopt_evidence','evidence_stale',evidence_id=old_e['evidence_id'])
 before=p.world.org_current_identity(M2);ok(c,M2,'adopt_evidence',evidence_id=e['evidence_id']);ok(c,M2,'run_tests',evidence_id=e['evidence_id']);ok(c,M2,'review_evidence',evidence_id=e['evidence_id'],decision='accept',reason='Actual final-version checks')
 assert p.world.org_current_identity(M2)==before
 assert ok(c,M1,'delivery_readiness')['ready_to_submit']
 ok(c,M1,'submit_integration',message='Explicit repaired and revalidated delivery');assert p.world.protocol()['terminal']=='DELIVERED'
 assert p.world.dynamic()['work']['a']['authors']==[M1] and p.world.dynamic()['work']['b']['authors']==[M2]
