import itertools
from test_role_baseline_world_v141 import prepare as substrate,M1,M2
from test_organization_world_v211 import ok,no,split
from test_organization_world_v212 import setup
from proworksim import software_organization_world_v213 as world
from proworksim.harness_port import HarnessPort

def prepare(p):
 prepared,_,_,runs=substrate(p);world.attach(prepared,['behavior','regression'])
 ports={m:HarnessPort(world.SoftwareCollaborationPort(prepared.world.session(m,world.PROJECT),m),m,project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in (M1,M2)}
 for port in ports.values():port.tools()
 counter=itertools.count()
 def call(m,t,**a):return ports[m].call(t,request_key=f'v213-{next(counter)}',association={},**a)
 return prepared,ports,call,runs

def test_divergent_private_trees_review_then_explicit_integrated_delivery(tmp_path):
 p,_,c,runs=prepare(tmp_path);split(c);setup(c,'behavior')
 offer=ok(c,M1,'assign_work',task_id='regression',to_member=M2,reason='Independent public checks');ok(c,M2,'accept_transfer',offer_id=offer['offer_id']);setup(c,'regression',M2,M1)
 ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'run_tests');a=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Behavior fix')['patch_id'];ok(c,M1,'complete_work',task_id='behavior',patch_id=a)
 ok(c,M2,'begin_work',task_id='regression');ok(c,M2,'write_file',path='test_sample.py',text='def test_value():\n    from sample import value\n    assert isinstance(value, int)\n');ok(c,M2,'run_tests');b=ok(c,M2,'fix_patch',task_ids=['regression'],message='Type validation')['patch_id'];ok(c,M2,'complete_work',task_id='regression',patch_id=b)
 before={m:p.world.org_current_identity(m) for m in (M1,M2)}
 for actor,patch in ((M2,a),(M1,b)):
  ok(c,actor,'open_patch_review',patch_id=patch)
  no(c,actor,'org_review_patch','work_test_missing',patch_id=patch,decision='accept',reason='No test cannot accept')
  ok(c,actor,'run_patch_review_tests',patch_id=patch)
  review=ok(c,actor,'org_review_patch',patch_id=patch,decision='accept',reason='Examined exact published version and real public tests')
  assert review['adoption_kind']=='explicit_immutable_review_view' and not review['main_workspace_adopted']
  assert p.world.org_current_identity(actor)==before[actor]
 no(c,M1,'submit_integration','repairable_delivery_incomplete',message='No merge yet')
 ok(c,M1,'integrate_patch',patch_id=b);ok(c,M1,'run_tests');ok(c,M1,'fix_patch',task_ids=['behavior'],message='Final fixed merge');ok(c,M1,'submit_integration',message='Both independent reviews and explicit integration')
 assert len(runs)==5
 assert p.world.dynamic()['work']['behavior']['authors']==[M1] and p.world.dynamic()['work']['regression']['authors']==[M2]

def test_failed_test_explanation_and_no_early_joint_change(tmp_path):
 p,_,c,_=prepare(tmp_path);split(c);setup(c,'behavior');setup(c,'regression')
 no(c,M1,'offer_joint_arrangement','joint_progress_required',task_id='regression',to_member=M2,reviewer=M1,mode='evidence',expected_revision=1,reason='Not actual work yet')
 ok(c,M1,'run_tests');ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 3\n')
 no(c,M1,'offer_joint_arrangement','joint_progress_required',task_id='regression',to_member=M2,reviewer=M1,mode='evidence',expected_revision=1,reason='Earlier baseline test is not after work')
 ok(c,M1,'run_tests');patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Known failing synthetic candidate')['patch_id']
 no(c,M1,'complete_work','work_test_failed',task_id='behavior',patch_id=patch)
 offer=ok(c,M1,'offer_joint_arrangement',task_id='regression',to_member=M2,reviewer=M1,mode='evidence',expected_revision=1,reason='After actual code and public test')
 ok(c,M2,'accept_joint_arrangement',offer_id=offer['offer_id'])
 assert p.world._task('regression')['owner']==M2
