"""Two isolated Requests CA controls; no active r2 files or resources are changed."""
from __future__ import annotations
from functools import lru_cache
import inspect
import json
import os
from pathlib import Path
import shutil
from types import ModuleType
from . import software_benchmark_scope_v203_2_1_r2 as parent
from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace

ROOT=parent.ROOT
VERSION='v203.2.1-independent-requests-private-CA-control-scope-r3'
TASK='psf__requests-2317'
BATCH_ROOT=ROOT/'runs/software-benchmark-v203-2-1/requests-ca-r3'
GRADING_ROOT=BATCH_ROOT/'grading'
COORDINATOR_ROOT=BATCH_ROOT/'coordinator'
PLAN_FILE=BATCH_ROOT/'plan.json'
SOURCE_FILE=BATCH_ROOT/'runtime-sources.json'
AUTH_FILE=BATCH_ROOT/'authorization.json'
CPU_POOL_FILE=parent.CPU_POOL_FILE
ARTIFACT_ROOT=ROOT/'artifacts/software-benchmark-v203-2-1/requests-ca-r3'
MAX_GRADERS=2
GIB=1024**3
ResourceBusy=original.ResourceBusy
PARENT_MAX_CPU=64
PARENT_MAX_MEMORY=456*GIB
OWN_MAX_CPU=8
OWN_MAX_MEMORY=40*GIB
COMBINED_CPU=72
COMBINED_MEMORY=496*GIB
COMBINED_DISK_FLOOR=(128+32+8)*GIB
CONSTRAINTS={**parent.CONSTRAINTS,
 'fresh_generation_slots':0,'generation_token_upper_bound':0,'api_generation_token_upper_bound':0,
 'api_total_budget_cny':'0.00','model_API_calls':0,'maximum_model_residents':0,
 'maximum_actor_containers':0,'maximum_controller_containers':0,'maximum_named_volumes':0,
 'maximum_code_score_containers':0,'maximum_delivery_score_containers':0,'maximum_score_containers':0,
 'maximum_control_containers':2,'maximum_containers':2,'maximum_active_generation_episodes':0,
 'active_actor_limit':0,'active_controller_limit':0,'active_grader_limit':2,'maximum_active_containers':2,
 'new_owned_user_units':[],'maximum_combined_reserved_cpu':OWN_MAX_CPU,
 'maximum_combined_reserved_memory_bytes':OWN_MAX_MEMORY,'host_grading_process_memory_bytes':4*GIB,
 'host_grading_cpu_shared_with_own_container':True,'scoring_only':True,'maximum_concurrent_new_controls':2,
 'joint_parent_cpu_upper_bound':COMBINED_CPU,'joint_parent_memory_upper_bound_bytes':COMBINED_MEMORY,
 'joint_headroom_memory_floor_bytes':(64+496)*GIB,'joint_disk_floor_bytes':COMBINED_DISK_FLOOR,
 'CPU_pool_offsets':[64,71],'parent_CPU_pool_offsets':[0,63],
 'parent_source_and_runtime_state_modified':False,'new_service_or_parent_slice':False,
 'automatic_replay':False,'model_calls_during_preparation':0,
 'requests_private_capability_tasks':[TASK],
 'requests_private_grader_cap_add':['NET_ADMIN','NET_BIND_SERVICE'],
 'requests_extra_hosts':{'httpbin.org':'127.0.0.1','www.google.co.uk':'127.0.0.1'}}


def load(ref):return json.loads(checked(ref).read_bytes())


def retain(path,value):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():
  if load(reference(p))!=value:raise ValueError('Immutable independent control preparation changed')
  return reference(p)
 return write_new(p,value)


def host_cpu_pool():
 pool=parent.host_cpu_pool()
 if len(pool)<COMBINED_CPU:raise ResourceBusy('The frozen CPU pool lacks72 disjoint reserved cores')
 return pool


def cpu_set(role,index=0):
 if role!='grader' or type(index) is not int or index not in (0,1):
  raise ValueError('Only the two independent scoring lanes are admitted')
 pool=host_cpu_pool();return ','.join(map(str,pool[64+4*index:68+4*index]))


def physical_capacity():
 available=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
 free=shutil.disk_usage(ROOT).free;pool=host_cpu_pool()
 return {'memory_available_bytes':available,'disk_free_bytes':free,'CPU_pool_count':len(pool),
  'parent_worst_case_cpu':PARENT_MAX_CPU,'parent_worst_case_memory_bytes':PARENT_MAX_MEMORY,
  'own_worst_case_cpu':OWN_MAX_CPU,'own_worst_case_memory_bytes':OWN_MAX_MEMORY,
  'joint_cpu_upper_bound':COMBINED_CPU,'joint_memory_upper_bound_bytes':COMBINED_MEMORY,
  'required_memory_available_bytes':(64+496)*GIB,'required_disk_free_bytes':COMBINED_DISK_FLOOR,
  'parent_mutated':False,'passed':available>=(64+496)*GIB and free>=COMBINED_DISK_FLOOR and len(pool)>=72}


def validate_plan(plan):
 keys={'control-ca-r3-'+TASK+'-'+kind for kind in ('gold','empty')}
 if (plan.get('version')!=VERSION or plan.get('root')!=str(BATCH_ROOT)
  or set(plan.get('resources',{}))!=keys or set(plan.get('environments',{}))!={TASK}
  or plan.get('rows')!=[] or plan.get('constraints')!=CONSTRAINTS
  or plan.get('parent_plan')!=reference(parent.PLAN_FILE)):
  raise ValueError('Only the exact independent Requests gold/empty scope is allowed')
 for key,row in plan['resources'].items():
  if row.get('role')!='control' or row.get('instance_id')!=TASK or key!='control-ca-r3-'+TASK+'-'+row.get('patch_kind',''):
   raise ValueError('A control resource changed its exact identity')
 return plan


def verify_sources():
 source_ref=reference(SOURCE_FILE)
 for ref in load(source_ref)['files']:checked(ref)
 # This is read-only validation of the still-frozen parent source closure.
 parent_source=reference(parent.SOURCE_FILE)
 for ref in parent.load(parent_source)['files']:checked(ref)
 return {'sources':source_ref,'parent_sources':parent_source,'all_references_checked':True,
         'parent_files_modified':False,'model_calls':0}


@lru_cache(maxsize=2)
def _verify_once(path,sha,size):
 return verify_sources()


def require_allowed(operation='v066.run',*,slot_id=None,instance_id=None):
 if (os.getuid()==0 or os.geteuid()==0 or operation not in {'v066.run','v066.control','v066.grader.create','v066.grader.start'}
  or slot_id is not None or instance_id not in (None,TASK)):
  raise PermissionError('Independent CA scope is ordinary-user two-control scoring only')
 auth=load(reference(AUTH_FILE))
 if (auth.get('version')!=VERSION or auth.get('status')!='approved' or auth.get('plan')!=reference(PLAN_FILE)
  or auth.get('source_index')!=reference(SOURCE_FILE) or auth.get('constraints')!=CONSTRAINTS
  or auth.get('model_calls')!=0 or auth.get('parent_runtime_mutations')!=0):
  raise PermissionError('Exact independent CA control scope is not sealed')
 ref=auth['source_index'];_verify_once(ref['path'],ref['sha256'],ref['bytes'])
 validate_plan(load(auth['plan']))
 return auth


require_grading_allowed=require_allowed


def _budget(active,cpu,memory,spool=0):
 if cpu!=4 or memory!=16*GIB or spool!=0:raise PermissionError('Only a4CPU16GiB control container may claim capacity')
 if any(row['spec']['role']!='control' for row in active):raise PermissionError('Foreign object in independent control scope')
 used_cpu=sum(row['reserved_cpu'] for row in active)
 # Each active scorer's host process is bounded to4GiB on the same four cores.
 used_memory=sum(row['reserved_memory_bytes']+4*GIB for row in active)
 if len(active)>=2 or used_cpu+cpu>OWN_MAX_CPU or used_memory+memory+4*GIB>OWN_MAX_MEMORY:
  raise ResourceBusy('Both independent control envelopes are occupied')
 observed=physical_capacity()
 if not observed['passed']:raise ResourceBusy('Conservative parent-plus-control headroom is unavailable')
 return {'reserved_cpu_after':used_cpu+cpu,'reserved_memory_bytes_after':used_memory+memory+4*GIB,
         'physical_at_admission':observed,'parent_scope_untouched':True}


def dispatch_view(guard=None):
 authorize=guard or require_allowed
 ns=clone_namespace(original,VERSION=VERSION,BATCH_ROOT=BATCH_ROOT,PLAN_FILE=PLAN_FILE,
  SOURCE_INDEX_FILE=SOURCE_FILE,AUTHORIZATION_FILE=AUTH_FILE,GRADING_ROOT=GRADING_ROOT,
  COORDINATOR_RUN_ROOT=COORDINATOR_ROOT,CONSTRAINTS=CONSTRAINTS,CPU_POOL_FILE=CPU_POOL_FILE,__file__=__file__)
 def allowed(operation='v066.run',**identity):
  value=authorize(operation,**identity)
  return {**value,'plan':reference(PLAN_FILE),'sources':reference(SOURCE_FILE),'constraints':CONSTRAINTS}
 ns.update(require_v066_allowed=allowed,cpu_set=cpu_set,host_cpu_pool=host_cpu_pool,
           physical_capacity=physical_capacity,_budget=_budget)
 source=inspect.getsource(original.claim_resource)
 for role in ('score','delivery_score','control'):
  source=source.replace('"'+role+'": ("grader", 4, 4, 16 * GIB)','"'+role+'": ("grader", 2, 4, 16 * GIB)')
 exec(compile(source,__file__+':independent-two-lanes','exec'),ns)
 value=ModuleType(__name__+'.private_dispatch');value.__dict__.update(ns);return value
