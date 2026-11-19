import itertools,copy,json
from test_role_baseline_world_v141 import prepare as substrate,M1,M2
from test_organization_world_v211 import ok,no,split
from test_organization_world_v212 import setup
from proworksim import software_organization_world_v216_2 as world
from proworksim.harness_port import HarnessPort

def prepare(path):
    p,_,_,runs=substrate(path);world.attach(p,['behavior','regression'])
    ports={m:HarnessPort(world.Port(p.world.session(m,world.PROJECT),m),m,project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in (M1,M2)}
    for port in ports.values():port.tools()
    n=itertools.count()
    def c(m,t,**a):return ports[m].call(t,request_key=f'v216-2-{next(n)}',association={},**a)
    return p,ports,c,runs

def test_keep_guard_blocks_real_reassignment_but_allows_setup_and_delivery(tmp_path):
    p,ports,c,runs=prepare(tmp_path);split(c)
    world.register_proposal(p.world,{'candidate_id':'keep','keep':True,'actions':[]},{'cpu':True})
    ok(c,M1,'select_arrangement',candidate_id='keep',decision='keep',reason='Preserve checkpoint structure')
    no(c,M1,'assign_work','kept_arrangement_frozen',task_id='regression',to_member=M2,reason='Must be blocked')
    no(c,M1,'change_dependency','kept_arrangement_frozen',task_id='regression',depends_on='behavior',operation='add',reason='Must be blocked')
    no(c,M1,'offer_joint_arrangement','kept_arrangement_frozen',task_id='regression',to_member=M2,reviewer=M1,mode='implementation',expected_revision=1,reason='Must be blocked')
    setup(c,'behavior');setup(c,'regression')
    ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'run_tests')
    patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Candidate')['patch_id'];ok(c,M1,'complete_work',task_id='behavior',patch_id=patch)
    ready=ok(c,M1,'delivery_readiness');assert any(a.get('patch_id')==patch and a['actor']==M2 for a in ready['next_actions'])
    ok(c,M2,'open_patch_review',patch_id=patch);ok(c,M2,'run_patch_review_tests',patch_id=patch);ok(c,M2,'org_review_patch',patch_id=patch,decision='accept',reason='Actual checks')
    t=p.world._latest_same_version_test(M1,p.world.org_current_identity(M1));e=ok(c,M1,'complete_evidence',task_id='regression',requirements=['regression'],test_sequence=t['sequence'],reason='No additional code necessary')['evidence_id']
    ok(c,M2,'adopt_evidence',evidence_id=e);ok(c,M2,'run_tests',evidence_id=e);ok(c,M2,'review_evidence',evidence_id=e,decision='accept',reason='Actual evidence checks')
    assert ok(c,M1,'delivery_readiness')['ready_to_submit']
    ok(c,M1,'submit_integration',message='Explicit exact version');assert p.world.protocol()['terminal']=='DELIVERED'
    assert all(p.world._task(t)['owner']==M1 for t in ('behavior','regression'))

def test_dependency_guidance_and_default_dedup_preserve_explicit_full_records(tmp_path):
    p,ports,c,_=prepare(tmp_path);split(c);setup(c,'behavior');setup(c,'regression')
    ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n');ok(c,M1,'run_tests')
    patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Actual candidate')['patch_id'];ok(c,M1,'complete_work',task_id='behavior',patch_id=patch)
    proposal={'candidate_id':'adapt','keep':False,'actions':[],'target':{'long_record':'x'*10000},'operations':[],'reason':'Synthetic'}
    world.register_proposal(p.world,proposal,{'cpu':True});ok(c,M1,'select_arrangement',candidate_id='adapt',decision='attempt',reason='Actual decision')
    off=ok(c,M1,'offer_joint_arrangement',task_id='regression',to_member=M2,reviewer=M1,mode='implementation',expected_revision=1,reason='Actual assignment');ok(c,M2,'accept_joint_arrangement',offer_id=off['offer_id'])
    ok(c,M2,'change_dependency',task_id='regression',depends_on='behavior',operation='add',reason='Requires actual upstream version')
    r=ok(c,M2,'work_readiness',task_id='regression');g=next(g for g in r['gaps'] if g['kind']=='upstream_patch_not_adopted');assert g['next_explicit_action']['arguments']['patch_id']==patch
    no(c,M2,'begin_work','work_setup_incomplete',task_id='regression')
    assert p.world.dynamic()['work']['regression']['authors']==[]
    full=ok(c,M2,'dynamic_status');assert full['lifecycle']['proposal']['target']==proposal['target']
    # Exercise actual observation path, with world and explicit records unchanged.
    before=copy.deepcopy(p.world.protocol());obs=ports[M2].observe()
    assert p.world.protocol()==before
    assert 'proposal' not in obs['dynamic_organization']['lifecycle']
    assert 'delivery_readiness' not in obs['delivery_status']
    assert obs['organization_decision']['candidate_id']=='adapt'
    assert 'x'*10000 not in json.dumps(obs)

def test_repair_budget_keeps_old_cost_and_reserves_four_branches(tmp_path):
    from proworksim.software_organization_api_v216_2 import Ledger,CAPS
    l=Ledger(tmp_path/'cash.sqlite')
    for i in (2,4):l.reserve_block(str(i),{f'v216:r3-task-{i:02d}:{z}':3_900_000 for z in ('KEEP','ADAPT')})
    assert l.snapshot()['cap_CNY']==700 and sum(CAPS.values())==451_000_000_000
    assert l.snapshot()['new_phase_estimates']['A_and_prepare']['estimated_exposure_CNY']==42
