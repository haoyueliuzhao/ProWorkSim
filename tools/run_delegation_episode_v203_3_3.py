"""Real original-repository REVIEW2 prefix or one frozen-checkpoint continuation."""
from __future__ import annotations
import argparse,json,os,time,traceback
from pathlib import Path
from proworksim.storage import json_bytes
ROOT=Path(__file__).resolve().parents[1]
def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(json_bytes(value))
class SettledPrefix(Exception):pass

def main(a):
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(a.output/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1',
        HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHON_DOTENV_DISABLED='1')
    from proworksim import software_role_baseline_runtime_v203_2_1 as runtime
    from proworksim import software_role_baseline_runtime_v141 as original
    from proworksim import software_role_baseline_world_v141 as world
    from proworksim import software_sdk_resume_v203_3_2 as resume
    from proworksim.software_delegation_actor_v203_3_3 import Actor
    from proworksim.software_delegation_api_v203_3_3 import Ledger,Backend,DirectHTTPS
    from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_benchmark_candidates_v054 import reference
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.software_benchmark_public_context_v062 import prepare_public_context
    from proworksim.software_benchmark_alignment_contract_v203_2_1 import initial_message
    from proworksim.harness_port import HarnessPort
    rows=json.loads((ROOT/'artifacts/software-benchmark-v203-3-3/preparation-r1/candidates.json').read_text())['rows'];row=rows[a.index]
    checkpoint=a.checkpoint.resolve() if a.checkpoint else None
    state=resume.read(checkpoint)[0] if checkpoint else None
    limit=5_000_000-state['prefix_ledger']['known_actual_tokens'] if state else 500_000
    slot='v203.3.3:'+a.output.name
    ledger=Ledger(a.ledger);admitted=False;actor=rt=prepared=None
    result={'version':'v203.3.3-real-state-episode-r1','slot':slot,'index':a.index,'instance_id':row['instance_id'],'arm':a.arm,
        'checkpoint_parent':str(checkpoint) if checkpoint else None,'started':time.time(),'status':'preparing','stage_token_limit':limit,
        'old_ledger_transferred':False,'official_score':None,'scoring_status':'not_started'}
    save(a.output/'result.json',result)
    try:
        actor=Actor(row,a.output/'actor',resume_test_calls=state['public_test_calls'] if state else 0).start()
        deadline=DispatchDeadline(soft_seconds=21600,hard_seconds=23400)
        prepared=world.prepare_case(a.output/'actor/source-manifest.json',a.output/'prepared',organization_id='REVIEW2',
            public_test_callback=actor.test,deadline=deadline,public_test_entry=actor.entry)
        if checkpoint:resume.restore_world(prepared,checkpoint)
        else:
            port=HarnessPort(world.SoftwareCollaborationPort(prepared.world.session('member_001',world.PROJECT),'member_001'),
                'member_001',project_id=world.PROJECT,public_sink=lambda *_:None,world_sink=lambda *_:None,harness_sink=lambda *_:None)
            port.tools();receipts=[]
            for i,(tool,args) in enumerate([('create_task',{'task_id':'diagnose','description':'Diagnose the cause of the public issue and establish a public reproduction before implementing; report remaining uncertainty.'}),
                ('claim_task',{'task_id':'diagnose','reason':'Initial developer diagnostic responsibility in common preparation'})]):
                value=port.call(tool,request_key=slot+':preparation:'+str(i),association={},**args)
                receipts.append(value)
                if not value['ok']:raise ValueError('Common preparation action rejected')
            save(a.output/'common-preparation.json',{'receipts':receipts,'model_calls':0,'hidden_information':False,'identical_before_assignment':True})
        tok=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';ref=reference(tok)
        counter=OfficialDeepSeekCounter(tok,manifest_sha256=ref['sha256'])
        content,metadata=load_official_content_counter(tok,manifest_sha256=ref['sha256'])
        schemas={m:original.member_wire_tools('REVIEW2',m) for m in ('member_001','member_002')}
        names={t['function']['name'] for arr in schemas.values() for t in arr}
        backend=Backend(a.output/'physical-api',ledger,slot,counter,DirectHTTPS(load_api_key(ROOT/'.env'),timeout_seconds=1800),names)
        owner=runtime.build_team_owner(backend.post,organization_id='REVIEW2',slot_id=slot,condition_id=a.arm,
            folder=a.output/'model-ledger',deadline=deadline,identity={'policy_version':'v203.3.3-real-flash-NT','model':'deepseek-flash','thinking':False},
            observation_token_counter=content,observation_tokenizer_id=metadata['tokenizer_id'],require_content_counter=True)
        c=actor.config
        context=prepare_public_context(c['public_task'],registry_reference=c['public_test_registry'],
            baseline_mapping_reference=c['public_test_entry']['baseline_mapping'],public_environment=actor.public)
        save(a.output/'public-context.json',context)
        initial=initial_message(c['public_task']['problem_statement'],public_context=context['visible_text'])
        rt,_,_=runtime.build_runtime(owner,prepared,a.output/'runtime',deadline=deadline,public_initial_message=initial)
        if checkpoint:save(a.output/'restore.json',resume.restore_runtime(prepared,rt,checkpoint))
        else:resume.register_persistence_types()
        ledger.admit(slot,limit);admitted=True
        result.update(status='running',API_admitted_at=time.time());save(a.output/'result.json',result)
        if a.arm=='REASSIGN':
            rt.policies['member_001'].conversation.send_message('Preassigned experimental condition: attempt to delegate the existing unfinished diagnose task to member_002 using offer_transfer and the original acceptance workflow. No new task facts or diagnosis answers are supplied. Keep member_001 implementation and delivery, member_002 final review.')
        def opportunity(outcome):
            save(a.output/'progress.json',{'at':time.time(),'opportunities':rt.opportunities,'actions':rt.actions,
                'usage':owner.adapter.ledger.snapshot(),'last_outcome':outcome})
            if not checkpoint:
                if outcome['status'] in original.TECHNICAL_FAILURES: return
                # No extra request after the first eight settled opportunities;
                # semantic admission is reviewed on immutable current evidence.
                if rt.opportunities>=8 or owner.adapter.ledger.actual>=300_000:raise SettledPrefix()
        try:
            boundary=runtime.run_fragment(prepared,rt,on_opportunity=opportunity)
            save(a.output/'boundary.json',boundary)
            result['status']='closed' if boundary['execution_integrity_failure'] is None else 'technical_unknown'
        except SettledPrefix:
            proof=resume.save(prepared,rt,a.output/'checkpoint',control_state={'real_prefix':True,'index':a.index})
            save(a.output/'checkpoint-proof.json',proof);result.update(status='awaiting_state_review',checkpoint=reference(a.output/'checkpoint/manifest.json'))
        save(a.output/'final-world.json',prepared.world.store.load())
        runtime.close_runtime(rt);rt=None
        if checkpoint:
            save(a.output/'candidate-lock.json',runtime.lock_fixed_candidates(prepared,a.output/'closure',sdk_closed=True))
    except BaseException as error:
        result.update(status='technical_unknown',error_type=type(error).__name__,error=str(error))
        (a.output/'traceback.txt').write_text(traceback.format_exc())
    finally:
        if rt:
            try:runtime.close_runtime(rt)
            except Exception as error:result['SDK_close_error']=str(error)
        if prepared:
            try:save(a.output/'final-world.json',prepared.world.store.load())
            except Exception as error:result['save_error']=str(error)
        if actor:
            try:actor.close()
            except Exception as error:result['cleanup_error']=str(error)
        if admitted:ledger.close(slot)
        result.update(finished=time.time(),ledger=reference(a.ledger));save(a.output/'result.json',result)
        save(a.output/'cash-snapshot.json',ledger.snapshot())
    print(json.dumps({k:result.get(k) for k in ('slot','status','error_type','error')}))
    return 0 if result['status'] in ('closed','awaiting_state_review') else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--index',type=int,required=True);p.add_argument('--checkpoint',type=Path);p.add_argument('--arm',choices=['PREFIX','KEEP','REASSIGN'],default='PREFIX')
    a=p.parse_args()
    if bool(a.checkpoint)!=(a.arm!='PREFIX'):p.error('Continuation requires a checkpoint; prefix has none')
    raise SystemExit(main(a))
