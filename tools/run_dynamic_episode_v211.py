"""One actual dynamic-work episode or zero-model initial SDK checkpoint."""
import argparse,json,os,time,traceback
from pathlib import Path
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1]
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(x))
def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 os.environ.update(OH_PERSISTENCE_DIR=str(out/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHON_DOTENV_DISABLED='1')
 from proworksim import software_organization_runtime_v211 as runtime,software_organization_world_v211 as dynamic,software_role_baseline_world_v141 as world,software_sdk_resume_v203_3_4 as resume
 from proworksim.software_organization_actor_v211 import Actor
 from proworksim.software_organization_runtime_v204 import after_opportunity,public_context
 from proworksim.software_organization_api_v211 import Ledger,Backend,DirectHTTPS
 from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
 from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
 from proworksim.software_collaboration_observation_v141 import load_official_content_counter
 from proworksim.software_benchmark_candidates_v054 import reference,checked
 from proworksim.software_organization_runtime_v047 import DispatchDeadline
 panel=R/'artifacts/software-benchmark-v211/mechanism-plan-r1';row=json.loads((panel/'candidate-tasks.json').read_text())['rows'][a.index]
 state=resume.read(a.checkpoint)[0] if a.checkpoint else None
 slot='v211:'+out.parent.name+':'+out.name;limit=5_000_000-(state['prefix_ledger']['known_actual_tokens'] if state else 0)
 result={'version':'v211-dynamic-episode-r1','slot':slot,'index':a.index,'instance_id':row['instance_id'],'condition':a.condition,'status':'preparing','started':time.time(),'checkpoint_parent':str(a.checkpoint.resolve()) if a.checkpoint else None,'stage_token_limit':limit,'official_score':None}
 save(out/'result.json',result);actor=rt=None;admitted=False;ledger=Ledger(a.ledger)
 try:
  actor=Actor(row,out/'actor',resume_test_calls=state['public_test_calls'] if state else 0);actor.start()
  deadline=DispatchDeadline(soft_seconds=21600,hard_seconds=23400)
  prepared=world.prepare_case(out/'actor/source-manifest.json',out/'prepared',organization_id='FREE2',public_test_callback=actor.test,deadline=deadline,public_test_entry=actor.entry)
  dynamic.attach(prepared,[r['id'] for r in row['requirements']])
  if state:resume.restore_world(prepared,a.checkpoint)
  tok=R/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';counter=OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256']);content,meta=load_official_content_counter(tok,manifest_sha256=reference(tok)['sha256'])
  names={t['function']['name'] for m in ('member_001','member_002') for t in runtime.member_wire_tools('FREE2',m)}
  if a.condition=='PREPARE':
   def post(route,payload):raise RuntimeError('Initial checkpoint must not issue model/count requests')
  else:
   backend=Backend(out/'physical-api',ledger,slot,counter,DirectHTTPS(load_api_key(R/'.env'),timeout_seconds=1800),names);post=backend.post
  owner=runtime.build_team_owner(post,organization_id='FREE2',slot_id=slot,condition_id='v211-'+a.condition,folder=out/'model-ledger',deadline=deadline,identity={'policy_version':runtime.VERSION,'model':'deepseek-flash','thinking':False},observation_token_counter=content,observation_tokenizer_id=meta['tokenizer_id'],require_content_counter=True)
  c=actor.config;context=public_context(c,actor.public)
  initial=runtime.CONTRACT+'\n\n'+c['public_task']['problem_statement']+'\n\n'+context
  rt,_,_=runtime.build_runtime(owner,prepared,out/'runtime',deadline=deadline,public_initial_message=initial)
  if state:save(out/'restore.json',resume.restore_runtime(prepared,rt,a.checkpoint))
  actor.bind_deadline(rt.deadline)
  if a.condition=='PREPARE':
   assert owner.adapter.ledger.attempts==0
   save(out/'checkpoint-proof.json',resume.save(prepared,rt,out/'checkpoint',control_state={'task_index':a.index,'dynamic_version':dynamic.VERSION,'model_calls':0}))
   result.update(status='initial_checkpoint_ready',checkpoint=reference(out/'checkpoint/manifest.json'),model_calls=0)
  else:
   for frozen in json.loads((panel/'deployment-freeze.json').read_text())['files']:checked(frozen)
   ledger.admit(slot,limit);admitted=True
   bank_path=panel/f'candidates-{a.index}.json';bank=json.loads(bank_path.read_text());candidate=bank['selected'][a.condition]
   intervention=('Execute this frozen initial organization plan using only your own actual tools and role identity. It is a proposal, not a completed graph. Read real dynamic_status and transfer receipts. For arguments_from_real_receipt, copy the actual preceding offer_id; never send the reference object as a tool argument. Preserve every refusal, unavailable step and partial execution; never claim an unexecuted plan succeeded. Keep ownership consent and original task acceptance. After initialization, perform the actual work and exact contribution-level review/delivery under the common contract.\n'+json.dumps(candidate,ensure_ascii=False))
   for w in rt.policies.values():w.conversation.send_message(intervention)
   save(out/'organization-plan.json',{'source':reference(bank_path),'condition':a.condition,'candidate':candidate,'instruction':intervention,'before_first_model_call':True})
   result.update(status='running',API_admitted_at=time.time());save(out/'result.json',result)
   def step(o):
    after_opportunity(actor,out/'transport-fault.json')
    save(out/'progress.json',{'at':time.time(),'opportunities':rt.opportunities,'actions':rt.actions,'usage':owner.adapter.ledger.snapshot(),'last_outcome':o})
   boundary=runtime.run_fragment(prepared,rt,on_opportunity=step);save(out/'boundary.json',boundary)
   result['status']='closed' if boundary['execution_integrity_failure'] is None else 'technical_unknown'
  save(out/'final-world.json',prepared.world.store.load());save(out/'dynamic-final.json',prepared.world._action_dynamic_status('member_001',world.PROJECT))
  runtime.close_runtime(rt);rt=None
  if a.condition!='PREPARE' and result['status']=='closed':save(out/'candidate-lock.json',runtime.lock_fixed_candidates(prepared,out/'closure',sdk_closed=True))
 except BaseException as error:
  result.update(status='technical_unknown',error={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()});save(out/'exception.json',result['error'])
 finally:
  if rt:
   try:runtime.close_runtime(rt)
   except Exception as error:save(out/'runtime-close-error.json',{'type':type(error).__name__,'message':str(error)})
  if admitted:ledger.close(slot)
  if actor:
   try:actor.close()
   except Exception as error:save(out/'cleanup-error.json',{'type':type(error).__name__,'message':str(error)})
  result['finished']=time.time();save(out/'result.json',result);save(out/'cash-snapshot.json',ledger.snapshot())
 print(json.dumps({'slot':slot,'status':result['status'],'error':result.get('error')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--index',type=int,required=True);p.add_argument('--condition',choices=['PREPARE','O0','O1','O2'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',type=Path);p.add_argument('--ledger',type=Path,required=True);a=p.parse_args()
 if (a.condition!='PREPARE')!=(a.checkpoint is not None):p.error('Every paid branch needs the frozen common checkpoint')
 main(a)
