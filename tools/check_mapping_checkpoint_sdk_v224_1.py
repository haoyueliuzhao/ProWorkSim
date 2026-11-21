"""Real SDK checkpoint/early-stop wiring; scripted responses, zero provider calls."""
import argparse,os,json,sys,copy,subprocess
from pathlib import Path
from types import SimpleNamespace as NS
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--scenario',choices=['single','split','peer'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
os.environ.update(OH_PERSISTENCE_DIR=str(out/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
from proworksim import software_organization_runtime_v223_1 as runtime,software_organization_world_v223_1 as world,software_sdk_resume_v203_3_4 as resume
from proworksim.software_mapping_checkpoint_v224_1 import capture,SamplingUnavailable,INITIAL_WORK_INSTRUCTION
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import digest,json_bytes
sys.path.insert(0,str(R/'tests'));import test_role_baseline_world_v141 as fixture

def clean_run(argv,**kwargs):
 kwargs['env']={k:v for k,v in kwargs.get('env',os.environ).items() if k not in ('PYTHONHOME','PYTHONPATH','PYTHONNOUSERSITE','LD_LIBRARY_PATH','LD_PRELOAD')}
 result=subprocess.run(argv,**kwargs)
 if result.stderr:result.stdout+=result.stderr
 return result
prepare=clone_function(fixture.prepare,{**fixture.prepare.__globals__,'sys':NS(executable=str(R/'.venv/bin/python')),'subprocess':NS(run=clean_run)})
prepared,_,_,calls=prepare(out/'fixture');deadline=DispatchDeadline(soft_seconds=180,hard_seconds=240);prepared.source_provider.runner.hard_at=deadline.hard_at
world.attach(prepared,['behavior','regression'],condition='G');M1,M2='member_001','member_002';requests=[];positions={M1:0,M2:0};observations=[]
children=[{'task_id':'behavior','description':'Public repair','scope':['behavior']},{'task_id':'regression','description':'Public regression','scope':['regression']}]
if a.scenario=='single':seq1=[('assign_verification',{'task_id':'work_root','reviewer':M2,'reason':'Independent'}),('add_collaboration',{'task_id':'work_root','peer':M2,'reason':'Review'}),('begin_work',{'task_id':'work_root'}),('write_file',{'path':'sample.py','text':'value = 2\n'})];seq2=[]
elif a.scenario=='split':seq1=[('split_work',{'task_id':'work_root','children':children,'reason':'Two genuine scopes'}),('assign_verification',{'task_id':'behavior','reviewer':M2,'reason':'Independent'}),('add_collaboration',{'task_id':'behavior','peer':M2,'reason':'Review'}),('begin_work',{'task_id':'behavior'}),('write_file',{'path':'sample.py','text':'value = 2\n'}),('run_tests',{})];seq2=[]
else:
 seq1=[('split_work',{'task_id':'work_root','children':children,'reason':'Two genuine scopes'}),('assign_work',{'task_id':'behavior','to_member':M2,'reason':'Peer implements'}),('WAIT_PATCH',{}),('open_patch_review',{'patch_id':'patch-1'}),('run_patch_review_tests',{'patch_id':'patch-1'})]
 seq2=[('WAIT_OFFER',{}),('ACCEPT',{}),('assign_verification',{'task_id':'behavior','reviewer':M1,'reason':'Independent'}),('add_collaboration',{'task_id':'behavior','peer':M1,'reason':'Review'}),('begin_work',{'task_id':'behavior'}),('write_file',{'path':'sample.py','text':'value = 2\n'}),('run_tests',{}),('fix_patch',{'task_ids':['behavior'],'message':'Publish exact candidate for real review'})]
def action(m):
 seq=seq1 if m==M1 else seq2;i=positions[m]
 if i>=len(seq):return 'dynamic_status',{}
 tool,args=seq[i];facts=prepared.world._software()
 if tool=='WAIT_PATCH':
  if 'patch-1' not in facts['patches']:return 'dynamic_status',{}
  positions[m]+=1;return action(m)
 if tool in ('WAIT_OFFER','ACCEPT'):
  offers=prepared.world.org_state().get('transfer_offers',{})
  # Actual public offer record is used; no guessed transfer identifier.
  offers=facts.get('transfer_offers',offers)
  if not offers:
   events=[e for e in prepared.world.state['software_events'] if e.get('recipient')==M2 and e.get('offer_id')]
   if not events:return 'dynamic_status',{}
   offer=events[-1]['offer_id']
  else:offer=next(iter(offers))
  if tool=='WAIT_OFFER':positions[m]+=1;return action(m)
  tool,args='accept_transfer',{'offer_id':offer}
 positions[m]+=1;return tool,args

def post(route,payload):
 if route in ('/tokenize','/tokenize-prefix'):return {'prompt_tokens':1024,'request_sha256':digest(json_bytes(payload['wire'])),'method':'synthetic control count only','count_only_not_dispatchable':route.endswith('prefix')}
 assert route=='/chat/completions' and len(requests)<80
 requests.append(copy.deepcopy(payload));tool,args=action(payload['member_id']);msg={'role':'assistant','content':None,'tool_calls':[{'id':'cpu-'+str(len(requests)),'type':'function','function':{'name':tool,'arguments':json.dumps(args)}}]}
 return {'id':'sdk-'+a.scenario+'-'+str(len(requests)),'model':'deepseek-flash','object':'chat.completion','created':0,'choices':[{'index':0,'finish_reason':'tool_calls','message':msg}],'usage':{'prompt_tokens':256,'completion_tokens':25,'total_tokens':281,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':256}}
owner=runtime.build_team_owner(post,organization_id='FREE2',slot_id='v2241-sdk:'+a.scenario,condition_id='scripted-only',folder=out/'model-ledger',deadline=deadline,identity={'policy_version':runtime.VERSION,'model':'scripted-no-provider','thinking':False});rt=None
class Ready(Exception):pass
try:
 rt,_,_=runtime.build_runtime(owner,prepared,out/'runtime',deadline=deadline,public_initial_message=runtime.CONTRACT+'\n'+INITIAL_WORK_INSTRUCTION);resume.register_persistence_types()
 def step(o):
  if o.get('response',{}).get('ok') is False:raise ValueError(str(o['response']))
  state=capture(prepared,rt);gate=state['mapping_decision_gate'];observations.append(gate)
  if gate['sampling_exhausted']:raise SamplingUnavailable()
  if gate['eligible']:raise Ready()
 try:runtime.run_fragment(prepared,rt,on_opportunity=step);raise AssertionError('Missing early boundary')
 except SamplingUnavailable:assert a.scenario=='single';status='sampling_space_exhausted'
 except Ready:assert a.scenario!='single';status='decision_checkpoint_ready'
 proof=resume.save(prepared,rt,out/'checkpoint',control_state={'qualified':status=='decision_checkpoint_ready','mapping_gate':observations[-1],'scripted':True})
 (out/'checkpoint-proof.json').write_bytes(json_bytes(proof));saved=resume.read(out/'checkpoint')[0];assert saved['control_state']['mapping_gate']==observations[-1]
 summary={'passed':True,'scenario':a.scenario,'status':status,'real_SDK':True,'actual_cpu_tests':len(calls),'scripted_requests':len(requests),'model_provider_calls':0,'containers':0,'boundary_preserved_checkpoint':True,'gate':observations[-1]}
 if a.scenario=='peer':assert any(w['mode']=='published_patch_review' and w['author']==M2 for w in observations[-1]['witnesses'])
 (out/'summary.json').write_bytes(json_bytes(summary));print(json.dumps(summary))
finally:
 if rt:runtime.close_runtime(rt)
 (out/'requests.json').write_bytes(json_bytes(requests));(out/'gates.json').write_bytes(json_bytes(observations))
