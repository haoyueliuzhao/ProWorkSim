"""Four predeclared controlled states, real managed ownership and execution branches.

No model/API, no benchmark result, no natural mismatch prevalence estimate.
"""
from __future__ import annotations
import argparse,copy,hashlib,importlib.util,inspect,json,os,subprocess,sys
from pathlib import Path
from proworksim import software_role_baseline_world_v141 as world
from proworksim.harness_port import HarnessPort
from proworksim.storage import json_bytes,digest
from proworksim.software_branch_checkpoint_v203_3_1 import capture,restore,require_live_resume
from proworksim.software_organization_decision_v203_3_1 import validate_work_package
from proworksim.software_public_test_retention_v203_2_3_r5 import retaining_executor

ROOT=Path(__file__).resolve().parents[1]
STATES=[('dependency','django__django-11095','django/contrib/admin/options.py'),
        ('load','sympy__sympy-24661','sympy/parsing/sympy_parser.py'),
        ('clear_recovery','sphinx-doc__sphinx-10673','sphinx/environment/collectors/toctree.py'),
        ('stable','django__django-15572','django/template/autoreload.py')]

def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def reference(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def fixture_module():
    p=ROOT/'tests/test_role_baseline_world_v141.py'
    s=importlib.util.spec_from_file_location('controls_v141',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def sources():
    found={}
    for p in (ROOT/'runs/software-benchmark-v203-2-1').glob('*/episodes/*/controller-output/source-snapshot/source-manifest.json'):
        data=json.loads(p.read_text());task=data['tasks'][0]['task_id']
        if task in {r[1] for r in STATES}:
            desired=next(r[2] for r in STATES if r[1]==task)
            found[task]={'manifest':reference(p),'source_identity':data['tasks'][0]['source_identity'],
                'public_issue':data['tasks'][0]['problem_statement'],
                'archived_initial_tree_reference':data['tasks'][0]['initial_tree'],
                'path_hint':desired,'original_repository_bytes_loaded':False,
                'use':'public issue inspired controlled analogue; not original repository execution; no scores or reference patches read'}
    if len(found)!=4:raise ValueError('All four static sources required')
    return found

def main(out,resume_controls=None):
    out.mkdir(parents=True,exist_ok=False);module=fixture_module();provenance=sources()
    plan={'version':'v203.3.1-four-controlled-states-r1','states':[
        {'id':name,'source_task':task,'source':provenance[task],
         'kind':'controlled_analogue_not_original_SWE_bench_issue',
         'branches':['KEEP','REASSIGN_DIAGNOSIS'],'seed':2033100+i,
         'predicted_winner':None} for i,(name,task,_) in enumerate(STATES)],
        'frozen_before_branch_execution':True,'API_calls_allowed':0,
        'paid_pilot_proposal':'4 states x 2 branches x 2 repetitions = 16; not authorized or launched'}
    save(out/'plan.json',plan);results=[]
    for name,task,_ in STATES:
        if resume_controls and all((resume_controls/name/b/'result.json').is_file() for b in ('KEEP','REASSIGN_DIAGNOSIS')):
            prior=[json.loads((resume_controls/name/b/'result.json').read_text()) for b in ('KEEP','REASSIGN_DIAGNOSIS')]
            assert prior[0]['checkpoint_identity']==prior[1]['checkpoint_identity']
            assert [r['actual_first_test_actor'] for r in prior]==['member_001','member_002']
            results.append({'state':name,'source':provenance[task],'branches':prior,
                'intervention_changes_execution':True,'organization_effect_estimated':False,
                'completed_control_reused_without_reexecution':str(resume_controls/name)})
            continue
        folder=out/name
        initial={'dependency':'from helper import OFFSET\nvalue = OFFSET + 1\n',
                 'load':'value = 1\n','clear_recovery':'value = (\n','stable':'value = 1\n'}[name]
        setup="    (source/'sample.py').write_text("+repr(initial)+")\n"
        if name=='dependency':setup+="    (source/'helper.py').write_text('OFFSET = 0\\n')\n"
        if name=='load':setup+="    (source/'other_work.py').write_text('INTERFACE = \\\"preserve\\\"\\n')\n"
        source=inspect.getsource(module.prepare)
        old='    (source / "sample.py").write_text("value = 1\\n")\n'
        assert source.count(old)==1
        namespace=dict(module.__dict__);exec(compile(source.replace(old,setup),__file__+':controlled-baseline','exec'),namespace)
        prepared,ports,rawcall,_=namespace['prepare'](folder/'prefix','REVIEW2')
        histories={m:[] for m in ports}
        def call(member,tool,**args):
            r=rawcall(member,tool,**args);assert r['ok'],r
            histories[member].append({'tool':tool,'arguments':args,'response':r});return r['result']
        call('member_001','create_task',task_id='diagnose',description='Public diagnostic package: '+name)
        call('member_001','claim_task',task_id='diagnose',reason='Initial explicit diagnostic responsibility')
        if name=='load':
            call('member_001','create_task',task_id='interface_check',description='Inspect existing interface in addition to implementation')
            call('member_001','claim_task',task_id='interface_check',reason='Distinct remaining developer work')
        if name=='stable':
            call('member_001','write_file',path='sample.py',text='value = 2\n')
            published=call('member_001','fix_patch',task_ids=[],message='Stable control: existing author candidate awaiting verification')
            call('member_002','integrate_patch',patch_id=published['patch_id'])
        for member in ports:call(member,'read_file',path='sample.py')
        # Prefixes differ in disclosed public work circumstances, not outcomes.
        notes={'dependency':'Inspect sample.py and its public test together before implementation.',
               'load':'Developer also owns final implementation; diagnostic work can be delegated.',
               'clear_recovery':'The reproduction path is already explicit; no known ownership conflict.',
               'stable':'Current roles and handoff are clear; no established need to reorganize.'}
        call('member_001','send_message',recipient='member_002',task_id='diagnose',body=notes[name])
        baseline=prepared.world.org_current_identity('member_001')
        package={'kind':'public_diagnosis','task_id':'diagnose','old_owner':'member_001','new_owner':'member_002',
            'source_reference':baseline['source_reference'],'files_sha256':baseline['files_sha256'],
            'implementation_author':'member_001','delivery_member':'member_001','final_reviewer':'member_002',
            'next_work':[{'tool':'read_file','arguments':{'path':'sample.py'}},{'tool':'run_tests','arguments':{}}],
            'other_member_work':'Wait for the diagnosis, then implement; final independent review remains member_002',
            'test_evidence':[],'pending':'Initial reproduction not yet run; no claim of a positive organization effect'}
        validate_work_package(package);save(folder/'package.json',package)
        checkpoint=folder/'checkpoint'
        frozen=capture(prepared,checkpoint,histories=histories,budget={'remaining_tokens':5_000_000,'actual_provider_tokens':0},
            schedule={'phase':'diagnosis','next_owner_from_task':'diagnose','implementation_waits_for_diagnosis':True})
        branch_results=[]
        for branch in ('KEEP','REASSIGN_DIAGNOSIS'):
            target=folder/branch;fork,state,identity=restore(prepared,checkpoint,target)
            receipts=[];tests=[];sequence=0
            forkports={m:HarnessPort(world.SoftwareCollaborationPort(fork.world.session(m,world.PROJECT),m),m,
                project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None) for m in ports}
            for port in forkports.values():port.tools()
            def apply(member,tool,**args):
                nonlocal sequence
                sequence+=1;r=forkports[member].call(tool,request_key=f'{name}:{branch}:{sequence}',association={},**args)
                receipts.append({'actor':member,'tool':tool,'arguments':args,'response':r})
                assert r['ok'],r
                state['histories'][member].append(receipts[-1]);return r['result']
            def public_test(*,files,entry_metadata,request):
                directory=target/'test-runs'/str(len(tests)+1);directory.mkdir(parents=True)
                for path,text in files.items():
                    dest=directory/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
                argv=[sys.executable,'-m','pytest','-q','test_sample.py']
                execute=retaining_executor(target/'framework-journals',binding={
                    'source_reference':request['source_reference'],'candidate_tree_sha256':request['tree_sha256'],
                    'actor_id':request['actor_id'],'call_index':request['call_index']})
                measured=execute({'argv':argv},root=directory,
                    environment={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'},timeout_seconds=20)
                passed=measured['passed'];counts=measured['counts']
                tests.append({'request':request,'returncode':measured['returncode'],'stdout':measured['output'],
                    'counts':counts,'validation_status':measured['validation_status'],
                    'test_evidence':measured['test_evidence'],'directory':str(directory)})
                return {'passed':passed,'execution':{'executed':True,'input_tree_sha256':request['tree_sha256'],
                    'actor_id':request['actor_id'],'organization_id':'REVIEW2','managed_request_sha256':digest(json_bytes(request)),
                    'argv':argv,'public_test_selection':request['public_test_selection'],'public_test_selection_revision':'v110-public-test-selection-r1',
                    'validation_status':measured['validation_status'],'counts':counts,'test_evidence':measured['test_evidence']},
                    'groups':{'public_repository_tests':{'passed':passed,'executed':True,'status':'passed' if passed else 'failed',
                        'output':measured['output'],'tests':[{'test_id':'test_sample.py::test_value','passed':passed}]}},'repository_collection_errors':[]}
            fork.source_provider.runner.callback=public_test
            if branch=='REASSIGN_DIAGNOSIS':
                offer=apply('member_001','offer_transfer',task_id='diagnose',to_member='member_002',reason='Frozen one-time diagnostic reassignment')
                apply('member_002','accept_transfer',offer_id=offer['offer_id'])
                sent=apply('member_001','send_message',recipient='member_002',task_id='diagnose',body=json.dumps(package))
                read=apply('member_002','read_work_event',sequence=sent['message_sequence'])
                assert json.loads(read['body'])==package
            actual_owner=fork.world._software()['tasks']['diagnose']['owner']
            for step in package['next_work']:apply(actual_owner,step['tool'],**step['arguments'])
            if actual_owner=='member_002':apply(actual_owner,'send_message',recipient='member_001',task_id='diagnose',body=f"Actual diagnostic return code: {tests[0]['returncode']}. Continue the frozen implementation/verification plan; no hidden evaluation used.")
            # Both branches keep the same post-diagnosis implementation and review protocol.
            if name=='load':apply('member_001','read_file',path='other_work.py')
            if fork.world._bundle('member_001')[2]['files']['sample.py']!='value = 2\n':
                apply('member_001','write_file',path='sample.py',text='value = 2\n')
            apply('member_001','run_tests')
            if name=='stable':
                patch={'patch_id':published['patch_id']}
            else:
                patch=apply('member_001','fix_patch',task_ids=[],message='Author implementation after diagnostic work')
                apply('member_002','integrate_patch',patch_id=patch['patch_id'])
            apply('member_002','run_tests')
            apply('member_002','org_review_patch',patch_id=patch['patch_id'],decision='accept',reason='Actual same-version check; reviewer did not modify implementation')
            delivered=apply('member_001','submit_integration',message='Frozen REVIEW2 delivery')
            assert not any(r['actor']=='member_002' and r['tool'] in {'write_file','replace_file','fix_patch'} for r in receipts)
            result={'branch':branch,'checkpoint_identity':identity,'diagnostic_executor':actual_owner,
                'actual_first_test_actor':tests[0]['request']['actor_id'],'action_count':len(receipts),
                'public_tests':len(tests),'legal_control_delivery':True,'delivery':delivered,
                'implementation_author':'member_001','final_reviewer':'member_002',
                'paid_model_tokens':None,'scripted_API_calls':0,'official_benchmark_resolved':None,
                'semantic_state_same_before_intervention':identity==frozen['identity']}
            save(target/'receipts.json',receipts);save(target/'tests.json',tests);save(target/'result.json',result)
            branch_results.append(result)
        assert [r['actual_first_test_actor'] for r in branch_results]==['member_001','member_002']
        results.append({'state':name,'source':provenance[task],'branches':branch_results,
            'intervention_changes_execution':True,'organization_effect_estimated':False})
    historical={'status':'not_admitted_for_paired_API_resume','reason':'Existing observation packets and final archives are not verified decision-time two-member SDK checkpoints. No history is reconstructed from future outputs.',
        'new_capture_support':'managed-world controlled checkpoints implemented; live SDK continuation still requires separate restore evidence'}
    try:require_live_resume({'kind':'controlled_managed_world'})
    except ValueError:historical['incomplete_history_rejected']=True
    summary={'version':'v203.3.1-action-and-checkpoint-controls-r1','passed':True,'states':results,
        'controlled_states':4,'structural_source_repositories':3,'branches':8,'API_calls':0,
        'actual_SWE_bench_runs':0,'synthetic_results_are_not_effect_sizes':True,'historical_resume':historical}
    save(out/'summary.json',summary);print(json.dumps({'passed':True,'states':4,'branches':8,'API_calls':0}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--resume-controls',type=Path)
    a=p.parse_args();main(a.output.resolve(),a.resume_controls.resolve() if a.resume_controls else None)
