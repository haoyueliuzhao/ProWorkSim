"""Prepare/seal/run exactly two independent zero-model Requests CA controls.

Execution uses exactly two bounded host processes by forking once and calling
scoring directly. There is no extra service or supervising scoring process.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import time
from proworksim import software_benchmark_scope_passive_requests_v203_2_1_r3 as scope
from proworksim.software_benchmark_candidates_v054 import checked,reference


def module(path,name):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def prepare():
 parent=scope.parent;old=parent.load(reference(parent.PLAN_FILE));env=old['environments'][scope.TASK]
 resources={}
 for kind in ('gold','empty'):
  key='control-ca-r3-'+scope.TASK+'-'+kind
  resources[key]={'role':'control','instance_id':scope.TASK,'patch_kind':kind,
   'image_id':env['image_id'],'endpoint':'environment_control','independent_CA_revision':'r3'}
 plan={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'rows':[],'resources':resources,
  'environments':{scope.TASK:env},'constraints':scope.CONSTRAINTS,'parent_plan':reference(parent.PLAN_FILE),
  'host_cpu_pool':reference(scope.CPU_POOL_FILE),'model_calls':0,'volumes':0,'controls':2,
  'source_configuration_reused_without_model_change':True,'parent_runtime_state_changed':False,
  'user_authority':'Current task authorizes independent gold/empty CA environment validation only; no model attempt or cash is added.'}
 scope.validate_plan(plan)
 return {'plan':scope.retain(scope.PLAN_FILE,plan),'CPU_lanes':[scope.cpu_set('grader',i) for i in (0,1)],
  'CPU_offsets':[64,71],'model_calls':0,'Docker_operations':0,'needs_cold_grading_metadata_before_seal':True}


def refs(value):
 found=[]
 if isinstance(value,dict):
  if set(('path','sha256','bytes'))<=set(value) and isinstance(value['path'],str) and type(value['bytes']) is int:
   found.append({k:value[k] for k in ('path','sha256','bytes')})
  else:
   for child in value.values():found.extend(refs(child))
 elif isinstance(value,list):
  for child in value:found.extend(refs(child))
 return found


def seal():
 if scope.SOURCE_FILE.exists() or scope.AUTH_FILE.exists():raise ValueError('Independent control scope is already sealed')
 if list((scope.BATCH_ROOT/'resource-claims').glob('*.json')):raise ValueError('Control identities already consumed')
 plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
 from proworksim import software_benchmark_grading_passive_v203_2_1_r3 as grading
 control_plan=scope.load(reference(scope.COORDINATOR_ROOT/'control-plan.json'))
 if len(control_plan.get('controls',[]))!=2:raise ValueError('Exactly two prepared control requests required')
 old=module(scope.ROOT/'tools/seal_role_pilot_v142.py','ca_r3_source_reader')
 roots=[Path(__file__).resolve(),Path(scope.__file__),Path(grading.__file__),
  scope.ROOT/'src/proworksim/software_benchmark_environment_passive_v203_2_1_r3.py',
  scope.ROOT/'tools/run_offline_scorer_v096.py']
 sources=old.source_closure(scope.ROOT,roots=roots)
 files=sources+[reference(scope.PLAN_FILE),reference(scope.CPU_POOL_FILE),reference(scope.parent.SOURCE_FILE),
  reference(scope.COORDINATOR_ROOT/'scorer-manifest.json'),reference(scope.COORDINATOR_ROOT/'control-plan.json')]
 config=scope.load(plan['environments'][scope.TASK]['configuration'])
 files += [plan['environments'][scope.TASK]['configuration'],config['scorer_request_base']['dataset'],
           config['scorer_request_base']['baseline_mapping'],*control_plan['controls']]
 for path in (scope.GRADING_ROOT/'environments').rglob('*.json'):
  ref=reference(path);files.append(ref)
  for dependency in refs(scope.load(ref)):checked(dependency);files.append(dependency)
 from proworksim import software_benchmark_environment_passive_v203_2_1_r3 as env
 for dependency in refs(env.manifest()):checked(dependency);files.append(dependency)
 files=list({ref['path']:ref for ref in files}.values())
 source_ref=scope.retain(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,
  'parent_source':reference(scope.parent.SOURCE_FILE),'runtime_results_excluded':True,'no_model_authority':True})
 auth=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'approved',
  'plan':reference(scope.PLAN_FILE),'source_index':source_ref,'constraints':scope.CONSTRAINTS,
  'model_calls':0,'parent_runtime_mutations':0,'new_containers':2,'new_volumes':0,'new_services':0,
  'authority':'用户本轮请求、持续实验Docker授权及明确评分侧CA许可；执行范围仅Requests2317两个独立gold/empty控制，CPU offsets64..71，保留在途r2范围不变。'})
 return {'authorization':auth,'sources':source_ref,'model_calls':0,'Docker_operations':0,
  'combined_cpu_upper_bound':72,'combined_memory_upper_bound_GiB':496}


def one(request_ref,claim_ref):
 from proworksim import software_benchmark_grading_passive_v203_2_1_r3 as grading
 from proworksim.software_benchmark_rescore_v095 import host_limits
 request=scope.load(request_ref);folder=Path(request['directory']);claim=scope.load(claim_ref)
 result={'version':scope.VERSION,'request':request_ref,'resource_key':request['resource_key'],
  'capacity_claim':claim_ref,'pid':os.getpid(),'status':'process_exited','returncode':0}
 native_entered=False
 try:
  host_limits(scope.cpu_set('grader',claim['lane']))
  scope.retain(folder/'capacity-claim.json',{'prepared_request':request_ref,'claim':claim_ref})
  scope.retain(folder/'started.json',{'version':scope.VERSION,'request':request_ref,
   'resource_key':request['resource_key'],'started_unix':time.time(),'capacity_claim':claim_ref,
   'pid':os.getpid(),'host_process_memory_limit_bytes':4*scope.GIB,'direct_scoring_no_extra_supervisor':True})
  native_entered=True
  outcome=grading.score_request(request)
  result['official_status']=outcome.get('status');result['resolved']=outcome.get('resolved')
 except BaseException as error:
  result.update(returncode=1,status='technical_unknown',error={'type':type(error).__name__,'message':str(error)})
  if not native_entered:
   # This branch precedes every scorer/Docker invocation; only our local claim
   # exists and can be released with an explicit unentered proof.
   scope.retain(folder/'quiescence.json',{'version':scope.VERSION,'resource_key':request['resource_key'],
    'quiescent':True,'cleanup_errors':[],'create_result_unknown':False,'owned_container_ids':[],
    'deadline_reached':False,'proof':'No scoring function or Docker operation entered','model_calls':0})
   scope.dispatch_view().release_resource(claim_ref,quiescent=True)
 finally:
  result['finished_unix']=time.time();scope.retain(folder/'completion.json',result)
 return result['returncode']


def execute():
 if os.environ.get('PROWORKSIM_SCORER_HOST_THREAD_PROFILE')!='v096-single-thread-host-scorer-library-profile-r1':
  raise PermissionError('Use tools/run_offline_scorer_v096.py for the two bounded cold scoring processes')
 scope.require_allowed();before=scope.verify_sources();capacity=scope.physical_capacity()
 if not capacity['passed']:raise scope.ResourceBusy('Joint parent-plus-controls CPU/memory/disk headroom is unavailable')
 if (scope.BATCH_ROOT/'execution-started.json').exists():raise ValueError('Never replay the independent control identities')
 prepared=scope.load(reference(scope.COORDINATOR_ROOT/'control-plan.json'));requests=prepared['controls']
 if len(requests)!=2:raise ValueError('Exactly two controls required')
 policy=scope.dispatch_view();claims=[]
 try:
  for lane,request_ref in enumerate(requests):
   request=scope.load(request_ref);claims.append(policy.claim_resource(request['resource_key'],lane=lane))
 except BaseException:
  # No score function or Docker call has entered yet.
  for claim in claims:policy.release_resource(claim,quiescent=True)
  raise
 scope.retain(scope.BATCH_ROOT/'source-check-before.json',before)
 scope.retain(scope.BATCH_ROOT/'execution-started.json',{'version':scope.VERSION,'unix':time.time(),
  'pid':os.getpid(),'requests':requests,'claims':claims,'capacity':capacity,'model_calls':0,
  'host_processes':2,'extra_supervisor_process':False,'parent_runtime_state_modified':False})
 # Each resulting process calls the native scorer directly and sets its own
 #4CPU/4GiB host bound. Only the original process performs final qualification.
 child=os.fork()
 if child==0:
  try:code=one(requests[1],claims[1])
  except BaseException:code=1
  os._exit(code)
 try:first=one(requests[0],claims[0])
 finally:_,wait_status=os.waitpid(child,0)
 second=os.waitstatus_to_exitcode(wait_status)
 from proworksim import software_benchmark_grading_passive_v203_2_1_r3 as grading
 scoring=grading.scorer(policy);host=grading.host(policy,scoring)
 clean=all(host.trustworthy_cleanup(ref) for ref in requests)
 after=scope.verify_sources();scope.retain(scope.BATCH_ROOT/'source-check-after.json',after)
 result={'version':scope.VERSION,'returncodes':[first,second],'cleanup_proven':clean,
  'model_calls':0,'parent_runtime_mutations':0,'qualification':None,'qualification_passed':False}
 if clean and first==0 and second==0:
  try:
   result['qualification']=host.qualify(scope.TASK);result['qualification_passed']=True
  except Exception as error:result['qualification_error']={'type':type(error).__name__,'message':str(error)}
 result['active_owned_claims']=[str(p) for p in (scope.BATCH_ROOT/'resource-claims').glob('active-*.json')]
 result['source_identity_before_and_after_validated']=True
 scope.retain(scope.BATCH_ROOT/'result.json',result)
 return result


def main():
 p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
 g.add_argument('--prepare',action='store_true');g.add_argument('--seal',action='store_true');g.add_argument('--execute',action='store_true')
 a=p.parse_args();print(json.dumps(prepare() if a.prepare else seal() if a.seal else execute(),ensure_ascii=False))


if __name__=='__main__':main()
