"""Necessary repair paths through actual HarnessPort, with actual public pytest."""
import itertools
from test_role_baseline_world_v141 import prepare as substrate,M1,M2
from test_organization_world_v211 import ok,no,split
from proworksim import software_organization_world_v212 as world
from proworksim.harness_port import HarnessPort

def prepare(p):
 prepared,_,_,runs=substrate(p);world.attach(prepared,['behavior','regression'])
 ports={m:HarnessPort(world.SoftwareCollaborationPort(prepared.world.session(m,world.PROJECT),m),m,project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in (M1,M2)}
 for port in ports.values():port.tools()
 counter=itertools.count()
 def call(m,t,**a):return ports[m].call(t,request_key=f'v212-{next(counter)}',association={},**a)
 return prepared,ports,call,runs

def setup(c,tid,owner=M1,reviewer=M2):
 ok(c,owner,'assign_verification',task_id=tid,reviewer=reviewer,reason='Independent verification')
 ok(c,owner,'add_collaboration',task_id=tid,peer=reviewer,reason='Explicit exchange')

def test_repair_and_evidence_end_to_end(tmp_path):
 p,ports,c,runs=prepare(tmp_path);split(c)
 no(c,M1,'begin_work','work_setup_incomplete',task_id='behavior')
 setup(c,'behavior');setup(c,'regression')
 ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'run_tests')
 patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='First actual candidate')['patch_id']
 ok(c,M1,'complete_work',task_id='behavior',patch_id=patch)
 joint=ok(c,M1,'offer_joint_arrangement',task_id='regression',to_member=M2,reviewer=M1,mode='evidence',expected_revision=1,reason='After actual progress, swap untouched remaining package')
 assert p.world._task('regression')['owner']==M1
 ok(c,M2,'accept_joint_arrangement',offer_id=joint['offer_id'])
 assert p.world._task('regression')['owner']==M2
 ok(c,M2,'integrate_patch',patch_id=patch);ok(c,M2,'run_tests')
 ok(c,M2,'org_review_patch',patch_id=patch,decision='request_changes',reason='Preserve type requirement explicitly')
 ok(c,M1,'reopen_work',task_id='behavior',reason='Respond to explicit review')
 no(c,M2,'org_review_patch','stale_work_revision',patch_id=patch,decision='accept',reason='Must not reuse old review')
 ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='test_sample.py',text='def test_value():\n    from sample import value\n    assert value == 2\n    assert isinstance(value, int)\n');ok(c,M1,'run_tests')
 patch2=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Repaired candidate')['patch_id'];ok(c,M1,'complete_work',task_id='behavior',patch_id=patch2)
 ok(c,M2,'integrate_patch',patch_id=patch2);ok(c,M2,'run_tests');ok(c,M2,'org_review_patch',patch_id=patch2,decision='accept',reason='Exact new revision tested')
 test=p.world._latest_same_version_test(M2,p.world.org_current_identity(M2))
 evidence=ok(c,M2,'complete_evidence',task_id='regression',requirements=['regression'],test_sequence=test['sequence'],reason='Actual unchanged-code regression checks')
 ok(c,M1,'adopt_evidence',evidence_id=evidence['evidence_id']);ok(c,M1,'run_tests');ok(c,M1,'review_evidence',evidence_id=evidence['evidence_id'],decision='accept',reason='Exact evidence version and actual checks')
 assert ok(c,M1,'delivery_checklist')['package_chain_ready']
 ok(c,M1,'fix_patch',task_ids=['behavior'],message='Final fixed integration')
 delivered=ok(c,M1,'submit_integration',message='Actual repaired contract closure')
 assert delivered['organization_evidence']['independent_review']['kind']=='repairable_contribution_and_evidence_cross_review'
 assert p.world.dynamic()['work']['behavior']['authors']==[M1]
 assert p.world.dynamic()['work']['regression']['authors']==[]
 assert len(p.world.dynamic()['history'])==1 and len(runs)==5

def test_joint_authorship_and_replay_guard(tmp_path):
 p,_,c,_=prepare(tmp_path);split(c);setup(c,'behavior');setup(c,'regression')
 joint=ok(c,M1,'offer_joint_arrangement',task_id='regression',to_member=M2,reviewer=M1,mode='implementation',expected_revision=1,reason='Unstarted ownership exchange')
 ok(c,M2,'accept_joint_arrangement',offer_id=joint['offer_id'])
 no(c,M2,'accept_joint_arrangement','joint_invalid_offer',offer_id=joint['offer_id'])
 ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n')
 no(c,M1,'offer_joint_arrangement','joint_authored_work_unsupported',task_id='behavior',to_member=M2,reviewer=M1,mode='implementation',expected_revision=1,reason='Cannot erase actual authors')
 assert p.world.dynamic()['work']['behavior']['authors']==[M1]
