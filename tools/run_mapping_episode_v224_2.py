"""One paid common prefix or fresh KEEP/ADAPT continuation; no host organization actions."""
import argparse,json,os,time,traceback
from pathlib import Path
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v224-2/protocol-r1'
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(x))
class PrefixReady(Exception):pass
from proworksim.software_natural_checkpoint_v224_2 import INITIAL_WORK_INSTRUCTION

def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 os.environ.update(OH_PERSISTENCE_DIR=str(out/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHON_DOTENV_DISABLED='1')
 from proworksim import software_natural_organization_runtime_v224_2 as runtime,software_natural_organization_world_v224_2 as dynamic,software_role_baseline_world_v141 as world,software_sdk_resume_v203_3_4 as resume
 from proworksim.software_organization_actor_v223_1 import Actor
 from proworksim.software_organization_runtime_v204 import after_opportunity,public_context
 from proworksim.software_mapping_api_v224_2 import Ledger,Backend,DirectHTTPS
 from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
 from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
 from proworksim.software_collaboration_observation_v141 import load_official_content_counter
 from proworksim.software_benchmark_candidates_v054 import reference,checked
 from proworksim.software_organization_runtime_v047 import DispatchDeadline
 from proworksim.software_natural_checkpoint_v224_2 import capture
 from proworksim.software_runtime_performance_v222_1 import metrics,VERSION as PERFORMANCE_VERSION
 plan=json.loads((P/'candidate-tasks.json').read_text());row=next(r for r in plan['rows'] if r['index']==a.index)
 for ref in json.loads((P/'deployment-freeze.json').read_text())['files']:checked(ref)
 state=resume.read(a.checkpoint)[0] if a.checkpoint else None
 bank=json.loads(a.bank.read_text()) if a.bank else None;generator_tokens=(bank['actual_generator_tokens']+bank['shared_graph_tokens']) if bank else 0;prefix_tokens=state['prefix_ledger']['known_actual_tokens'] if state else 0
 limit=5_000_000-prefix_tokens-generator_tokens if state else plan['prefix_limit'];slot='v224_2:'+out.parent.name+':'+out.name
 result={'version':'v224.2-natural-work-episode-r1','slot':slot,'index':a.index,'instance_id':row['instance_id'],'condition':a.condition,'status':'preparing','started':time.time(),'checkpoint_parent':str(a.checkpoint.resolve()) if a.checkpoint else None,'prefix_tokens':prefix_tokens,'generator_tokens':generator_tokens,'stage_token_limit':limit,'official_score':None}
 save(out/'result.json',result);actor=rt=prepared=None;admitted=False;ledger=Ledger(a.ledger)
 try:
  actor=Actor(row,out/'actor',resume_test_calls=state['public_test_calls'] if state else 0);actor.start();deadline=DispatchDeadline(soft_seconds=21600,hard_seconds=23400)
  timing={'api_transport_seconds':0.,'public_test_callback_seconds':0.,'public_test_command_seconds':0.,'model_loop_seconds':0.}
  def public_test(**kw):
   started=time.monotonic()
   try:
    result=actor.test(**kw);timing['public_test_command_seconds']+=result.get('execution',{}).get('wall_seconds',0.);return result
   finally:timing['public_test_callback_seconds']+=time.monotonic()-started
  prepared=world.prepare_case(out/'actor/source-manifest.json',out/'prepared',organization_id='FREE2',public_test_callback=public_test,deadline=deadline,public_test_entry=actor.entry)
  dynamic.attach(prepared,[r['id'] for r in row['requirements']],condition='G')
  if state:resume.restore_world(prepared,a.checkpoint)
  tok=R/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';counter=OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256']);content,meta=load_official_content_counter(tok,manifest_sha256=reference(tok)['sha256'])
  names={t['function']['name'] for m in ('member_001','member_002') for t in runtime.member_wire_tools('FREE2',m)}
  class TimedDirect(DirectHTTPS):
   def request(self,*args,**kwargs):
    started=time.monotonic()
    try:return super().request(*args,**kwargs)
    finally:timing['api_transport_seconds']+=time.monotonic()-started
  backend=Backend(out/'physical-api',ledger,slot,counter,TimedDirect(load_api_key(R/'.env'),timeout_seconds=1800),names)
  def post(route,payload):
   if route=='/chat/completions' and prepared.world.protocol()['terminal']:raise RuntimeError('No API call after terminal business state')
   return backend.post(route,payload)
  owner=runtime.build_team_owner(post,organization_id='FREE2',slot_id=slot,condition_id='v224.2-'+a.condition,folder=out/'model-ledger',deadline=deadline,identity={'policy_version':runtime.VERSION,'model':'deepseek-flash','thinking':False,'performance_revision':PERFORMANCE_VERSION},observation_token_counter=content,observation_tokenizer_id=meta['tokenizer_id'],require_content_counter=True)
  initial=runtime.CONTRACT+'\n\n'+actor.config['public_task']['problem_statement']+'\n\n'+public_context(actor.config,actor.public)
  rt,_,_=runtime.build_runtime(owner,prepared,out/'runtime',deadline=deadline,public_initial_message=initial)
  if state:
   save(out/'restore.json',resume.restore_runtime(prepared,rt,a.checkpoint));runtime.set_native_limit(rt,5_000_000-generator_tokens)
   candidate=bank['candidates'][a.condition];dynamic.register_proposal(prepared.world,candidate,{'bank':reference(a.bank),'checkpoint':reference(a.checkpoint/'manifest.json')})
   text=runtime.CONTRACT+'\nAn authorized work observation is available; no prior test or reserved idle work is required. Shared prefix and generator cost are retained. '+str(generator_tokens)+' Graph review plus proposal tokens are deducted from the common 5M logical task allowance. member_001 must explicitly select_arrangement(attempt/keep/defer); this does not execute a change. Each owner and recipient must act with actual tool receipts and can refuse. KEEP means retain current arrangement; do not introduce external changes. After decision, continue work, repair conflicts and refresh evidence as necessary. When delivery_readiness is ready, explicitly submit. Assigned candidate:\n'+json.dumps(candidate,ensure_ascii=False)
   text+='\nShared OA assessment (hypotheses, not an action command): '+json.dumps(bank['decision_assessment'],ensure_ascii=False)+'\nAssigned branch decision and exact handoff: '+json.dumps(candidate['decision_assessment'],ensure_ascii=False)+'\nEarlier informal intentions cannot override the selected KEEP/DEFER restriction. Read current owners before acting.'
   for w in rt.policies.values():w.conversation.send_message(text)
   runtime.enter_continuation(rt)
   save(out/'assigned-proposal.json',{'bank':reference(a.bank),'candidate':candidate,'instruction':text,'host_changed_owner':False})
  else:
   resume.register_persistence_types();runtime.set_native_limit(rt,plan['prefix_limit'])
   text=INITIAL_WORK_INSTRUCTION+' Public issue annotations, not extra requirements: '+json.dumps(row['requirements'],ensure_ascii=False)
   for w in rt.policies.values():w.conversation.send_message(text)
  from proworksim.software_project_relations_v223_1 import Projection,synchronize
  from proworksim.software_organization_demand_v223 import Timeline
  timeline=Timeline()
  if state:timeline.restore(state['control_state']['demand_timeline'])
  projection=Projection('member_001')
  if state:projection.restore(state['control_state']['project_projection'])
  initial_projection=synchronize(projection,prepared.world,row['requirements']);save(out/'project-relations-initial.json',initial_projection)
  actor.bind_deadline(rt.deadline);ledger.admit(slot,limit);admitted=True;result.update(status='running',API_admitted_at=time.time());save(out/'result.json',result)
  first_submission=None;loop_started=time.monotonic()
  def step(o):
   nonlocal first_submission
   after_opportunity(actor,out/'transport-fault.json');u=owner.adapter.ledger.snapshot()
   projection.record_outcome(o,prepared.world.state['software_events'])
   pg=synchronize(projection,prepared.world,row['requirements']);save(out/'project-relations.json',pg)
   with (out/'project-relation-maintenance.jsonl').open('a') as log:log.write(json.dumps({'opportunity':rt.opportunities,'graph_id':pg['graph_id'],'relations':len(pg['relations']),'visible_events':pg['processed_visible_events'],'last_tool':o.get('decision',{}).get('action'),'last_ok':o.get('response',{}).get('ok'),'worker':o.get('worker_id'),'condition':a.condition,'project_graph_after':pg['graph_id'],'organization_graph_sha256':__import__('hashlib').sha256(json_bytes(prepared.world.dynamic())).hexdigest()})+'\n')
   timing['model_loop_seconds']=time.monotonic()-loop_started;timing['local_residual_seconds']=max(0.,timing['model_loop_seconds']-timing['api_transport_seconds']-timing['public_test_callback_seconds'])
   save(out/'progress.json',{'at':time.time(),'opportunities':rt.opportunities,'actions':rt.actions,'usage':u,'logical_total_tokens':u['known_actual_tokens']+generator_tokens,'generator_tokens':generator_tokens,'lifecycle':prepared.world.protocol(),'cache':metrics(prepared.world),'timing':dict(timing),'last_outcome':o})
   if prepared.world.protocol()['terminal']=='DELIVERED' and first_submission is None:
    first_submission={'at':time.time(),'usage':u,'physical_requests':backend.requests,'logical_tokens':u['known_actual_tokens']+generator_tokens};save(out/'first-submission-usage.json',first_submission)
   decision=capture(prepared,rt);decision['project_relations']=pg
   # A fresh continuation has its own lifecycle; a passive observer never changes it.
   terminal=bool(prepared.world.protocol()['terminal'])
   timeline.record_outcome(o,decision)
   decision['visible_blockages']=[x for x in timeline.blockages if x['work_signature']==__import__('proworksim.software_project_relations_v217',fromlist=['identity']).identity(decision['graph']['work'])]
   assessment=timeline.update(decision,pg,terminal=terminal)
   with (out/'organization-demand-timeline.jsonl').open('a') as f:f.write(json.dumps(assessment)+'\n')
   if not state:
    gate=decision['mapping_decision_gate']
    save(out/'sampling-gate-latest.json',gate)
    decision['organization_demand']=assessment['assessment']
    decision['proposal_tool_schemas'].update({t['name']:t['parameters'] for t in prepared.world._tool_definitions('SOFTWARE27') if t['name']=='integrate_patch'})
    if decision['eligible']:
     decision['checkpoint_trigger']='actual_authorized_repository_activity_without_mutability_or_test_prerequisite'
     decision['does_not_prove_organization_action_enabled']=True
     artifact,version,bundle=prepared.world._bundle('member_001')
     save(out/'generator-authorized-source.json',{'actor':'member_001','files':bundle['files'],'entry_metadata':bundle.get('entry_metadata'),'source_reference':{'object_id':artifact['artifact_id'],'version_id':version},'private_peer_material':False})
     decision['authorized_generator_source']=reference(out/'generator-authorized-source.json');save(out/'decision-state.json',decision)
     raise PrefixReady()
  try:
   boundary=runtime.run_fragment(prepared,rt,on_opportunity=step);save(out/'boundary.json',boundary)
   result['status']=('closed' if state or prepared.world.protocol()['terminal'] else 'baseline_checkpoint_ready') if boundary['execution_integrity_failure'] is None else 'technical_unknown'
  except PrefixReady:
   save(out/'checkpoint-proof.json',resume.save(prepared,rt,out/'checkpoint',control_state={'real_prefix':True,'index':a.index,'model_generated_initial_structure':True,'project_projection':projection.export(),'demand_timeline':timeline.export()}))
   from proworksim.software_organization_planning_v223 import historical_worker_context
   records=[]
   for request in (out/'physical-api').glob('*/request.json'):
    doc=json.loads(request.read_text())
    if doc['payload']['member_id']=='member_001' and doc['payload']['usage_id']=='agent':records.append((doc['time'],request,doc))
   if not records:raise ValueError('No authentic worker input for W0; never fabricate history')
   _,request,doc=max(records,key=lambda x:x[0]);history=historical_worker_context(doc);history['source']=reference(request);save(out/'worker-seen-context.json',history)
   result.update(status='decision_checkpoint_ready',checkpoint=reference(out/'checkpoint/manifest.json'))
  if not state and result['status'] in ('baseline_checkpoint_ready','closed'):
   decision=capture(prepared,rt);decision['project_relations']=synchronize(projection,prepared.world,row['requirements']);save(out/'decision-state.json',decision)
   if result['status']=='baseline_checkpoint_ready':
    save(out/'checkpoint-proof.json',resume.save(prepared,rt,out/'checkpoint',control_state={'real_prefix':True,'qualified':False,'index':a.index,'project_projection':projection.export(),'demand_timeline':timeline.export(),'keep_only_continuation':True}))
  save(out/'demand-timeline-final.json',timeline.export())
  save(out/'final-world.json',prepared.world.store.load());save(out/'dynamic-final.json',prepared.world._action_dynamic_status('member_001',world.PROJECT));save(out/'performance.json',{'cache':metrics(prepared.world),'timing':timing})
  save(out/'cost-endpoints.json',{'first_submission':first_submission,'final_native_usage':owner.adapter.ledger.snapshot(),'generator_tokens':generator_tokens,'logical_total_tokens':owner.adapter.ledger.actual+generator_tokens,'physical_requests_after_delivered':backend.requests-first_submission['physical_requests'] if first_submission else None})
  runtime.close_runtime(rt);rt=None
  if result['status']=='closed':save(out/'candidate-lock.json',runtime.lock_fixed_candidates(prepared,out/'closure',sdk_closed=True))
 except BaseException as error:
  result.update(status='technical_unknown',error={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()});save(out/'exception.json',result['error'])
 finally:
  if rt:
   try:runtime.close_runtime(rt)
   except Exception as e:save(out/'runtime-close-error.json',{'error':str(e)})
  if admitted:
   try:ledger.close(slot)
   except Exception as e:save(out/'ledger-close-error.json',{'error':str(e)})
  if actor:
   try:actor.close()
   except Exception as e:save(out/'cleanup-error.json',{'error':str(e)})
  result['finished']=time.time();save(out/'result.json',result);save(out/'cash-snapshot.json',ledger.snapshot())
 print(json.dumps({'slot':slot,'status':result['status'],'error':result.get('error')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--index',type=int,required=True);p.add_argument('--condition',choices=['PREFIX','KEEP','C1','C2'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',type=Path);p.add_argument('--bank',type=Path);p.add_argument('--ledger',type=Path,required=True);a=p.parse_args()
 if a.condition!='PREFIX' and (not a.checkpoint or not a.bank):p.error('Continuation needs frozen checkpoint and candidate bank')
 main(a)
