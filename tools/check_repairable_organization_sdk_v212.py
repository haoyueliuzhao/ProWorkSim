"""Real SDK + managed world + actual local pytest, zero provider/model calls."""
import argparse,os,json,sys,copy,importlib.util,subprocess,atexit
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',type=Path);p.add_argument('--docker',action='store_true');a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
os.environ.update(OH_PERSISTENCE_DIR=str(a.output/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
from proworksim import software_organization_runtime_v212 as runtime,software_organization_world_v212 as world,software_sdk_resume_v203_3_4 as resume
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.storage import json_bytes,digest
sys.path.insert(0,str(R/'tests'))
import test_role_baseline_world_v141 as fixture
def clean_run(argv,**kwargs):
 kwargs['env']={k:v for k,v in kwargs.get('env',os.environ).items() if k not in ('PYTHONHOME','PYTHONPATH','PYTHONNOUSERSITE','LD_LIBRARY_PATH','LD_PRELOAD')}
 result=subprocess.run(argv,**kwargs)
 if result.stderr:result.stdout+=result.stderr
 return result
prepare=clone_function(fixture.prepare,{**fixture.prepare.__globals__,'sys':SimpleNamespace(executable=str(R/'.venv/bin/python')),'subprocess':SimpleNamespace(run=clean_run)})
actor=None
deadline=DispatchDeadline(soft_seconds=21600,hard_seconds=23400)
if a.docker:
 from proworksim.software_organization_actor_v211 import Actor
 from proworksim.repository_sources_v054 import capture_repository
 from proworksim import software_role_baseline_world_v141 as original_world
 row=json.loads((R/'artifacts/software-benchmark-v211/mechanism-plan-r1/candidate-tasks.json').read_text())['rows'][3]
 old=resume.read(a.checkpoint)[0] if a.checkpoint else None
 actor=Actor(row,a.output/'actor',resume_test_calls=old['public_test_calls'] if old else 0);atexit.register(actor.close);actor.start()
 source=a.output/'fixture/source';source.mkdir(parents=True);(source/'sample.py').write_text('value = 1\n');(source/'test_sample.py').write_text('def test_value():\n    from sample import value\n    assert value == 2\n')
 manifest=capture_repository(source,a.output/'fixture/snapshot',task_id=row['instance_id'],problem_statement='SYNTHETIC dynamic SDK/RPC control; change sample to 2. Not an original issue result.',source_identity={'instance_id':row['instance_id'],'repo':row['repo'],'base_commit':row['base_commit'],'dataset_revision':'78f471bf655a3137b2e8a75af1501690ec009ec3'})
 calls=[]
 def tested(**kwargs):calls.append(kwargs['request']);return actor.test(**kwargs)
 prepared=original_world.prepare_case(manifest,a.output/'fixture/prepared',organization_id='FREE2',public_test_callback=tested,deadline=deadline,public_test_entry=actor.entry)
else:
 prepared,_,_,calls=prepare(a.output/'fixture');prepared.source_provider.runner.hard_at=deadline.hard_at
world.attach(prepared,['behavior','regression'])
if a.checkpoint:resume.restore_world(prepared,a.checkpoint)
M1,M2='member_001','member_002';requests=[]
def save(name,x):(a.output/name).write_bytes(json_bytes(x))
class Script:
 def __init__(self):self.rt=None;self.positions={M1:0,M2:0}
 def post(self,route,payload):
  if route in ('/tokenize','/tokenize-prefix'):return {'prompt_tokens':1024,'request_sha256':digest(json_bytes(payload['wire'])),'method':'synthetic control count only','count_only_not_dispatchable':route.endswith('prefix')}
  assert route=='/chat/completions' and len(requests)<100
  requests.append(copy.deepcopy(payload));m=payload['member_id'];w=prepared.world;d=w.dynamic();facts=w._software()
  if payload['usage_id']=='condenser':msg={'role':'assistant','content':'Synthetic history summary, consult actual dynamic_status.'};finish='stop'
  else:
   tool,args=self.next(m,d,facts)
   msg={'role':'assistant','content':None,'tool_calls':[{'id':f'control-{a.output.name}-{len(requests)}','type':'function','function':{'name':tool,'arguments':json.dumps(args)}}]};finish='tool_calls'
  return {'id':f'v212-control-{a.output.name}-{len(requests)}','model':'deepseek-flash','object':'chat.completion','created':0,'choices':[{'index':0,'finish_reason':finish,'message':msg}],'usage':{'prompt_tokens':256,'completion_tokens':25,'total_tokens':281,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':256}}
 def next(self,m,d,facts):
  if not a.checkpoint:
   if m==M2:return 'dynamic_status',{}
   seq=[('split_work',{'task_id':'work_root','children':[{'task_id':'behavior','description':'Repair public behavior','scope':['behavior']},{'task_id':'regression','description':'Regression validation','scope':['regression']}],'reason':'Public scopes'}),
        ('assign_verification',{'task_id':'behavior','reviewer':M2,'reason':'Independent'}),('add_collaboration',{'task_id':'behavior','peer':M2,'reason':'Exchange'}),
        ('assign_verification',{'task_id':'regression','reviewer':M2,'reason':'Independent'}),('add_collaboration',{'task_id':'regression','peer':M2,'reason':'Exchange'}),
        ('begin_work',{'task_id':'behavior'}),('write_file',{'path':'sample.py','text':'value = 2\n'}),('run_tests',{})]
  elif m==M1:
   seq=[('fix_patch',{'task_ids':['behavior'],'message':'Initial real candidate'}),('complete_work',{'task_id':'behavior','patch_id':'patch-1'}),
        ('offer_joint_arrangement',{'task_id':'regression','to_member':M2,'reviewer':M1,'mode':'evidence','expected_revision':1,'reason':'Adjust untouched remaining work after actual edit/test progress'}),
        ('WAIT_REJECTION',{}),('reopen_work',{'task_id':'behavior','reason':'Respond to actual independent review'}),('begin_work',{'task_id':'behavior'}),
        ('write_file',{'path':'test_sample.py','text':'def test_value():\n    from sample import value\n    assert value == 2\n    assert isinstance(value, int)\n'}),
        ('run_tests',{}),('fix_patch',{'task_ids':['behavior'],'message':'Revised candidate'}),('complete_work',{'task_id':'behavior','patch_id':'patch-2'}),
        ('WAIT_EVIDENCE',{}),('adopt_evidence',{'evidence_id':'evidence-1'}),('run_tests',{}),('review_evidence',{'evidence_id':'evidence-1','decision':'accept','reason':'Actual same-version checks'}),
        ('delivery_checklist',{}),('fix_patch',{'task_ids':['behavior'],'message':'Final integration'}),('submit_integration',{'message':'Actual repaired delivery'})]
  else:
   seq=[('WAIT_JOINT',{}),('accept_joint_arrangement',{'offer_id':'joint-1'}),('integrate_patch',{'patch_id':'patch-1'}),('run_tests',{}),
        ('org_review_patch',{'patch_id':'patch-1','decision':'request_changes','reason':'Add explicit integer regression check'}),('WAIT_REVISION',{}),
        ('integrate_patch',{'patch_id':'patch-2'}),('run_tests',{}),('org_review_patch',{'patch_id':'patch-2','decision':'accept','reason':'Exact new revision tested'}),('COMPLETE_EVIDENCE',{})]
  i=self.positions[m]
  if i>=len(seq):return ('staff_done',{'reason':'Synthetic actions complete'}) if a.checkpoint else ('dynamic_status',{})
  tool,args=seq[i]
  predicates={'WAIT_JOINT':lambda:'joint-1' in d['joint_offers'],
              'WAIT_REJECTION':lambda:any(x['decision']=='request_changes' for x in prepared.world.org_state()['reviews']),
              'WAIT_REVISION':lambda:d['work']['behavior']['completion'] and d['work']['behavior']['completion'].get('work_epoch')==1,
              'WAIT_EVIDENCE':lambda:'evidence-1' in d['evidence']}
  if tool in predicates:
   if not predicates[tool]():return 'dynamic_status',{}
   self.positions[m]+=1;return self.next(m,d,facts)
  if tool=='COMPLETE_EVIDENCE':
   test=prepared.world._latest_same_version_test(m,prepared.world.org_current_identity(m))
   tool,args='complete_evidence',{'task_id':'regression','requirements':['regression'],'test_sequence':test['sequence'],'reason':'Actual check, no new code contribution'}
  self.positions[m]+=1;return tool,args

script=Script();owner=runtime.build_team_owner(script.post,organization_id='FREE2',slot_id='v212-control:'+a.output.name,condition_id='dynamic-sdk-zero-api',folder=a.output/'model-ledger',deadline=deadline,identity={'policy_version':runtime.VERSION,'model':'scripted-no-provider','thinking':False})
rt=None
try:
 rt,_,_=runtime.build_runtime(owner,prepared,a.output/'runtime',deadline=deadline,public_initial_message=runtime.CONTRACT)
 script.rt=rt
 if a.checkpoint:
  save('restore.json',resume.restore_runtime(prepared,rt,a.checkpoint))
  if actor:actor.bind_deadline(rt.deadline)
  def check(outcome):
   error=outcome.get('response',{}).get('error',{})
   if error:raise RuntimeError('Unexpected scripted-control error: '+str(error))
  boundary=runtime.run_fragment(prepared,rt,on_opportunity=check);save('boundary.json',boundary)
  assert boundary['execution_integrity_failure'] is None and len(prepared.world._software()['deliveries'])==1
  events=prepared.world.state['software_events'];assert all(any(e['kind']=='organization_v212:'+kind for e in events) for kind in ('joint_accepted','work_reopened','evidence_completed','evidence_reviewed'))
  summary={'passed':True,'real_SDK':True,'actual_isolated_container_RPC':bool(actor),'fresh_process_resume':True,'actual_cpu_pytest_calls':len(calls),'legal_deliveries':1,'model_provider_calls':0,'scripted_requests':len(requests),'tokens_are_synthetic_control_usage':True,'not_real_repository_results':True,'actual_owner':{k:prepared.world._task(k)['owner'] for k in prepared.world.dynamic()['work']},'final_dynamic_state':prepared.world.dynamic()}
  save('summary.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='final_dynamic_state'}))
 else:
  if actor:actor.bind_deadline(rt.deadline)
  resume.register_persistence_types()
  for _ in range(16):
   rt.sync_members();o=rt.step()
   if o['status'] in ('environment_error','execution_integrity_error'):raise RuntimeError(str(o))
  assert prepared.world.dynamic()['work']['behavior']['authors']==[M1] and len(calls)==1
  save('checkpoint-proof.json',resume.save(prepared,rt,a.output/'checkpoint',control_state={'scripted':True}))
  save('summary.json',{'passed':True,'prefix_saved':True,'scripted_requests':len(requests),'model_provider_calls':0});print('Saved genuine SDK checkpoint after actual code/test progress; 0 API')
finally:
 if rt:runtime.close_runtime(rt)
 if actor:actor.close()
 save('requests.json',requests)
