"""Three preregistered zero-API resume comparisons; children are fresh processes."""
from __future__ import annotations
import argparse,copy,importlib.util,json,os,subprocess,sys
from pathlib import Path
from proworksim import software_role_baseline_runtime_v203_2_1 as runtime
from proworksim import software_sdk_resume_v203_3_2 as resume
from proworksim.storage import json_bytes,digest
from proworksim.software_public_test_retention_v203_2_3_r5 import retaining_executor

ROOT=Path(__file__).resolve().parents[1]
M1,M2='member_001','member_002'
INITIAL='Determine the remaining diagnosis of the public sample, implement, independently review, and deliver. Synthetic resume control; no external provider.'

def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(json_bytes(value))
def fixture(folder):
    spec=importlib.util.spec_from_file_location('sdk_fixture',ROOT/'tools/check_role_baseline_sdk_v141.py')
    f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
    prepared,deadline,calls=f.fixture(folder,'REVIEW2')
    def test(*,files,entry_metadata,request):
        calls.append(copy.deepcopy(request));target=folder/'public-actor-trees'/str(request['call_index']);target.mkdir(parents=True)
        for name,text in files.items():(target/name).write_text(text)
        argv=[str(ROOT/'.venv/bin/python'),'-m','pytest','-q','test_sample.py']
        execute=retaining_executor(folder/'journals',binding={'source_reference':request['source_reference'],
            'candidate_tree_sha256':request['tree_sha256'],'actor_id':request['actor_id']})
        result=execute({'argv':argv},root=target,environment={'PATH':'/usr/bin:/bin','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'},timeout_seconds=20)
        proof={k:result[k] for k in ('validation_status','counts','test_evidence')}
        return {'passed':result['passed'],'execution':{'executed':True,'input_tree_sha256':request['tree_sha256'],
            'actor_id':request['actor_id'],'organization_id':'REVIEW2','managed_request_sha256':digest(json_bytes(request)),
            'argv':argv,'public_test_selection':request['public_test_selection'],'public_test_selection_revision':'v110-public-test-selection-r1',**proof},
            'groups':{'public_repository_tests':{'executed':True,'passed':result['passed'],
                'status':'passed' if result['passed'] else 'failed','output':result['output'],
                'tests':[{'test_id':'test_sample.py::test_value','passed':result['passed']}],**proof}},'repository_collection_errors':[]}
    prepared.source_provider.runner.callback=test
    return prepared,deadline,calls

class Script:
    def __init__(self,folder,prepared):
        self.folder=folder;self.prepared=prepared;self.phase='prefix';self.arm='KEEP';self.counts={M1:0,M2:0}
        self.positions={M1:0,M2:0};self.requests=[];self.summaries=0;self.rt=None
    def post(self,route,payload):
        if route in {'/tokenize','/tokenize-prefix'}:
            return {'prompt_tokens':256,'request_sha256':digest(json_bytes(payload['wire'])),
                'method':'deterministic control only','count_only_not_dispatchable':route.endswith('prefix')}
        assert route=='/chat/completions'
        self.requests.append(copy.deepcopy(payload));assert len(self.requests)<90
        member=payload['member_id'];self.counts[member]+=1
        if payload['usage_id']=='condenser':
            self.summaries+=1
            self.rt.policies[member].agent.condenser.max_size=80
            message={'role':'assistant','content':'We have read the public sample. Diagnosis remains incomplete. No fixed repair or review exists. Continue from actual task and version evidence.'};finish='stop'
        else:
            if self.phase=='prefix':
                first=[('create_task',{'task_id':'diagnose','description':'Find the cause and reproduce before implementing; no diagnosis conclusion yet'}),
                    ('claim_task',{'task_id':'diagnose','reason':'Initial developer responsibility'}),('run_tests',{})]
                i=self.positions[member];name,args=first[i] if member==M1 and i<len(first) else ('read_file',{'path':'sample.py'})
                self.positions[member]+=1
            else:name,args=self.suffix(member)
            message={'role':'assistant','content':None,'tool_calls':[{'id':f'control-{member}-{self.counts[member]}','type':'function',
                'function':{'name':name,'arguments':json.dumps(args)}}]};finish='tool_calls'
        return {'id':f'control-{self.rt.owner.window_id}-response-{len(self.requests)}','model':'deepseek-flash','object':'chat.completion','created':0,
            'choices':[{'index':0,'finish_reason':finish,'message':message}],
            'usage':{'prompt_tokens':256,'completion_tokens':25,'total_tokens':281,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':256}}
    def suffix(self,member):
        facts=self.prepared.world._software()
        dev=[('run_tests',{}),('write_file',{'path':'sample.py','text':'value = 2\n'}),('run_tests',{}),
            ('fix_patch',{'task_ids':[],'message':'Original author final candidate'}),('WAIT_REVIEW',{}),
            ('submit_integration',{'message':'Same-version reviewed delivery'}),('staff_done',{'reason':'Delivered'}),('staff_done',{'reason':'Self-review complete'})]
        reviewer=[('WAIT_PATCH',{}),('integrate_patch',{'patch_id':'patch-1'}),('run_tests',{}),
            ('org_review_patch',{'patch_id':'patch-1','decision':'accept','reason':'Actual adopted version tested; I did not implement'}),
            ('staff_done',{'reason':'Reviewed'}),('staff_done',{'reason':'Self-review complete'})]
        if self.arm=='REASSIGN':
            dev=[('offer_transfer',{'task_id':'diagnose','to_member':M2,'reason':'Preassigned diagnostic delegation probe'}),
                ('WAIT_DIAG',{}),*dev[1:]]
            reviewer=[('WAIT_OFFER',{}),('accept_transfer',{'offer_id':'transfer-1'}),('run_tests',{}),
                ('send_message',{'recipient':M1,'task_id':'diagnose','body':'Public reproduction remains failing; implement and publish for my independent test.'}),*reviewer]
        actions=dev if member==M1 else reviewer
        while True:
            i=self.positions[member];name,args=actions[i] if i<len(actions) else ('staff_done',{'reason':'No further work'})
            if not name.startswith('WAIT_'):break
            reviews=self.prepared.world.org_state()['reviews']
            offers=facts.get('transfer_offers',{})
            if name=='WAIT_OFFER':
                # Original observation exposes real offers; use the actual ID.
                available=bool(offers)
                if available:
                    item=next(iter(offers.values())) if isinstance(offers,dict) else offers[0]
                    actions[i+1][1]['offer_id']=item['offer_id']
            else:
                available={'WAIT_PATCH':bool(facts['patches']),'WAIT_REVIEW':any(r.get('decision')=='accept' for r in reviews),
                    'WAIT_DIAG':any(r.get('kind')=='work_message' and r.get('actor_id')==M2 for r in self.prepared.world.state['software_events'])}.get(name,False)
            if not available:return 'staff_wait',{'reason':'Wait for actual peer evidence'}
            self.positions[member]+=1
        if i<len(actions):self.positions[member]+=1
        return name,args
    def snapshot(self):return {'counts':self.counts,'positions':self.positions,'summaries':self.summaries}

def build(folder,branch,checkpoint=None):
    prepared,deadline,calls=fixture(folder/'case')
    if checkpoint:resume.restore_world(prepared,checkpoint)
    script=Script(folder,prepared)
    namespace='v203.3.2:'+branch+':'+digest(str(folder.resolve()).encode())[:12]
    owner=runtime.build_team_owner(script.post,organization_id='REVIEW2',slot_id=namespace,
        condition_id='resume-control',folder=folder/'model-ledger',deadline=deadline,
        identity={'policy_version':'deterministic-resume-control'},observation_token_counter=lambda s:len(s.split()),
        observation_tokenizer_id='control-word-counter-not-provider')
    rt,_,_=runtime.build_runtime(owner,prepared,folder/'runtime',deadline=deadline,public_initial_message=INITIAL)
    script.rt=rt
    if checkpoint:
        state,_=resume.read(checkpoint);proof=resume.restore_runtime(prepared,rt,checkpoint)
        script.counts=state['control_state']['counts'];script.summaries=state['control_state']['summaries']
        save(folder/'restore.json',proof)
    return prepared,rt,script,calls

def suffix(folder,prepared,rt,script,*,arm,checkpoint):
    script.phase='suffix';script.arm=arm;script.positions={M1:0,M2:0}
    prefix=rt.owner.adapter.ledger.actual;prefix_attempts=rt.owner.adapter.ledger.attempts;start=len(script.requests)
    if arm=='REASSIGN':
        rt.policies[M1].conversation.send_message('Preassigned experimental condition: attempt to delegate the existing unfinished diagnose task to member_002 using offer_transfer and the original acceptance workflow. No new task facts or diagnosis answers are supplied. Keep member_001 implementation and delivery, member_002 final review.')
    try:
        boundary=runtime.run_fragment(prepared,rt)
        save(folder/'boundary.json',boundary)
        assert boundary['execution_integrity_failure'] is None,boundary['execution_integrity_failure']
        assert len(prepared.world._software()['deliveries'])==1,'No legal delivery'
    finally:runtime.close_runtime(rt)
    lock=runtime.lock_fixed_candidates(prepared,folder/'closure',sdk_closed=True)
    requests=script.requests[start:]
    save(folder/'continuation-requests.json',requests)
    save(folder/'final-world.json',prepared.world.store.load())
    summary={'passed':True,'arm':arm,'new_process_pid':os.getpid(),'prefix_tokens_not_recharged':prefix,
        'continuation_tokens_synthetic':rt.owner.adapter.ledger.actual-prefix,
        'new_adapter_requests':rt.owner.adapter.ledger.attempts-prefix_attempts,'prefix_attempts':prefix_attempts,
        'first_generation':next(r for r in requests if r['usage_id']=='agent'),
        'physical_request_ids':[r['request_id'] for r in requests],
        'checkpoint':str(checkpoint),'legal_deliveries':1,'lock':lock,'API_calls':0,
        'final_diagnostic_owner':prepared.world._software()['tasks']['diagnose']['owner']}
    save(folder/'result.json',summary);return summary

def main(output,checkpoint=None,branch='CONT',arm='KEEP'):
    output.mkdir(parents=True,exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(output/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1')
    prepared,rt,script,calls=build(output,branch,checkpoint)
    if not checkpoint:
        for worker in rt.policies.values():worker.agent.condenser.max_size=12
        for _ in range(20):
            rt.sync_members();outcome=rt.step()
            assert outcome['status'] not in {'environment_error','model_service_error','execution_integrity_error'},outcome
            if rt.opportunities>=12 and script.summaries:break
        assert script.summaries and prepared.source_provider.runner.calls>0
        checkpoint=output/'checkpoint'
        proof=resume.save(prepared,rt,checkpoint,control_state=script.snapshot())
        save(output/'prefix-requests.json',script.requests)
        state,_=resume.read(checkpoint);resume.reset_clock(rt,prepared,state['clock'])
    suffix(output,prepared,rt,script,arm=arm,checkpoint=checkpoint)
    print(json.dumps({'passed':True,'branch':branch,'arm':arm,'API_calls':0}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',type=Path)
    p.add_argument('--branch',default='CONT');p.add_argument('--arm',choices=['KEEP','REASSIGN'],default='KEEP')
    a=p.parse_args();main(a.output.resolve(),a.checkpoint.resolve() if a.checkpoint else None,a.branch,a.arm)
