"""Independent, no-network scoring of the one original17002 locked candidate."""
from __future__ import annotations
import os
from pathlib import Path
from types import ModuleType
from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_candidates_v054 import checked,reference,write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace

ROOT=original.ROOT
VERSION='v173-original17002-candidate-only-rescore-scope-r1'
BATCH_ROOT=ROOT/'runs/software-benchmark-v173/original-17002-rescore-r1'
ARTIFACT_ROOT=ROOT/'artifacts/software-benchmark-v173/original-17002-rescore-r1'
COORDINATOR_ROOT=BATCH_ROOT/'coordinator'
GRADING_ROOT=BATCH_ROOT/'grading'
PLAN_FILE=BATCH_ROOT/'plan.json'
INVENTORY_FILE=BATCH_ROOT/'inventory.json'
SOURCE_FILE=BATCH_ROOT/'runtime-sources.json'
SOURCE_CPU_POOL_FILE=ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/host-cpu-pool.json'
CPU_POOL_FILE=SOURCE_CPU_POOL_FILE
AUTH_FILE=ROOT/'config/v173-original-17002-rescore-authorization.json'
RELEASE_FILE=BATCH_ROOT/'execution-release.json'
STANDING_POLICY_FILE=ROOT/'config/v143-standing-docker-user-policy.json'
PROPOSAL_FILE=ARTIFACT_ROOT/'proposal.json'
TASK='pydata__xarray-3151'
SLOT='v157:pydata__xarray-3151:REVIEW2_C0:2026110801560009:completion-recovery-v170'
CODE_KEY='score-original-17002-code-v173'
DELIVERY_KEY='delivery-score-original-17002-v173'
MAX_GRADERS=1
GIB=1024**3
ResourceBusy=original.ResourceBusy
CONSTRAINTS={'maximum_containers':2,'maximum_score_containers':2,'maximum_control_containers':0,
 'maximum_actor_containers':0,'maximum_controller_containers':0,'maximum_named_volumes':0,
 'fresh_generation_slots':0,'generation_token_upper_bound':0,'api_total_budget_cny':'0','new_model_calls':0,
 'active_grader_limit':1,'maximum_combined_reserved_cpu':4,'maximum_combined_reserved_memory_bytes':20*GIB,
 'grader_cpu':4,'grader_memory_bytes':16*GIB,'host_grading_process_memory_bytes':4*GIB,
 'memory_minimum_free_bytes':64*GIB,'disk_minimum_free_bytes':128*GIB,
 'active_actor_limit':0,'generation_pair_reserved_cpu':0,'generation_pair_reserved_memory_bytes':0,
 'generation_pair_payload_spool_bytes':0,'maximum_real_tls_sessions':0,
 'container_network':'none','container_cap_add':[],'container_cap_drop':['ALL'],
 'no_new_privileges':True,'privileged':False,'host_bind_mounts':False,'physical_gpus':[],
 'new_owned_user_units':[],'same_tree_delivery_reuses_only_own_code_score':True,
 'shared_host_configuration_changes':0,'automatic_model_replay':False}
OPERATIONS=frozenset({'v173.run','v173.prepare','v105.run','v066.run','v066.score','v066.delivery.score',
                     'v066.grader.create','v066.grader.start'})


def load(ref):return original._cached_json(ref)


def retain(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():
  if load(reference(path))!=value:raise ValueError('Never replace frozen17002 score metadata')
  return reference(path)
 return write_new(path,value)


def host_cpu_pool():
 value=load(reference(SOURCE_CPU_POOL_FILE));cpus=value.get('cpu_ids')
 if value.get('uid')!=os.getuid() or not isinstance(cpus,list) or len(cpus)<120 or cpus!=sorted(set(cpus)):
  raise ValueError('Original available CPU inventory changed')
 return cpus


def cpu_set(role,index=0):
 if role!='grader' or type(index) is not int or index!=0:raise ValueError('One independent17002 grader lane only')
 return ','.join(map(str,host_cpu_pool()[116:120]))


def validate_plan(plan):
 if (plan.get('version')!=VERSION or plan.get('constraints')!=CONSTRAINTS
     or set(plan.get('resources',{}))!={CODE_KEY,DELIVERY_KEY}
     or set(plan.get('environments',{}))!={TASK} or len(plan.get('rows',[]))!=1):
  raise ValueError('Only the exact original17002 dual endpoints are planned')
 row=plan['rows'][0]
 if row.get('slot_id')!=SLOT or row.get('slot_index')!=17002 or row.get('instance_id')!=TASK:
  raise ValueError('Original task/slot/seed identity changed')
 for key,role,endpoint in [(CODE_KEY,'score','code'),(DELIVERY_KEY,'delivery_score','delivery')]:
  item=plan['resources'][key]
  if item.get('role')!=role or item.get('slot_id')!=SLOT or item.get('instance_id')!=TASK or item.get('endpoint')!=endpoint:
   raise ValueError('Unplanned scoring resource')
 if plan.get('host_cpu_pool')!=reference(SOURCE_CPU_POOL_FILE) or plan.get('new_model_calls')!=0:
  raise ValueError('Scoring cannot change the CPU inventory or call a model')
 return plan


def main_grader_claims():
 roots=[ROOT/'runs/software-benchmark-v170/completion-recovery13-r1']
 return [reference(path) for root in roots for path in sorted((root/'resource-claims').glob('active-grader-*.json'))]


def require_grading_allowed(operation='v173.run',*,slot_id=None,instance_id=None):
 if os.getuid()==0 or os.geteuid()==0 or operation not in OPERATIONS or slot_id not in (None,SLOT) or instance_id not in (None,TASK):
  raise PermissionError('Only ordinary-user original17002 scoring, no model/network/root operations')
 auth=load(reference(AUTH_FILE))
 if (auth.get('version')!='v173-original17002-rescore-authority-r1' or auth.get('status')!='approved'
     or auth.get('scope')!=reference(__file__) or auth.get('plan')!=reference(PLAN_FILE)
     or auth.get('source_index')!=reference(SOURCE_FILE) or auth.get('standing_policy')!=reference(STANDING_POLICY_FILE)
     or auth.get('resource_keys')!=[CODE_KEY,DELIVERY_KEY] or auth.get('constraints')!=CONSTRAINTS
     or auth.get('maximum_score_containers')!=2 or auth.get('new_model_calls')!=0
     or auth.get('shared_host_configuration_changes')!=0 or auth.get('network_connections')!=0):
  raise PermissionError('The new candidate-scoring authority changed')
 validate_plan(load(auth['plan']))
 for ref in load(auth['source_index'])['files']:checked(ref)
 if operation in {'v066.grader.create','v066.grader.start'}:
  release=load(reference(RELEASE_FILE))
  if (release.get('approved') is not True or release.get('plan')!=auth['plan']
      or release.get('authority')!=reference(AUTH_FILE) or release.get('task')!=TASK
      or release.get('coordination_basis')!='root_confirmed_main_grader_slot_available'):
   raise PermissionError('Actual scoring awaits the explicit parent/root coordination release')
  if main_grader_claims():raise ResourceBusy('Coordinate with the original main grading queue before creating this grader')
 return auth


require_allowed=require_grading_allowed


def _budget(active,cpu,memory,spool=0):
 if active or cpu!=4 or memory!=16*GIB or spool:raise ResourceBusy('Only one independent17002 grader may enter')
 if main_grader_claims():raise ResourceBusy('Original grading lane is busy; keep the supplemental score queued')
 physical=dispatch_view().physical_capacity()
 if not physical['passed'] or physical['memory_available_bytes']<84*GIB or os.getloadavg()[0]>len(host_cpu_pool())-16:
  raise ResourceBusy('Retain actual shared-server CPU/memory/disk headroom')
 return {'reserved_cpu_after':4,'reserved_memory_bytes_after':20*GIB,'reserved_payload_spool_bytes_after':0,
         'physical_at_admission':physical,'main_grader_leases_observed_empty':True}


def dispatch_view(guard=None):
 guard=guard or require_grading_allowed
 ns=clone_namespace(original,VERSION=VERSION,BATCH_ROOT=BATCH_ROOT,PLAN_FILE=PLAN_FILE,
  RESUME_FILE=INVENTORY_FILE,SOURCE_INDEX_FILE=SOURCE_FILE,CPU_POOL_FILE=CPU_POOL_FILE,
  GRADING_ROOT=GRADING_ROOT,COORDINATOR_RUN_ROOT=COORDINATOR_ROOT,AUTHORIZATION_FILE=AUTH_FILE,
  CONSTRAINTS=CONSTRAINTS,__file__=__file__)
 def allowed(operation='v066.run',**identity):
  auth=guard(operation,**identity)
  return {**auth,'sources':auth['source_index'],'constraints':CONSTRAINTS}
 ns.update(require_v066_allowed=allowed,host_cpu_pool=host_cpu_pool,cpu_set=cpu_set,_budget=_budget)
 original_claim=ns['claim_resource']
 def claim(key,*,lane=None):
  if key not in (CODE_KEY,DELIVERY_KEY) or lane not in (None,0):raise PermissionError('No foreign scorer resource')
  if key==DELIVERY_KEY and load(reference(PLAN_FILE)).get('same_tree_delivery') is True:
   raise PermissionError('The audited same-tree delivery must reuse its own code score without another container')
  return original_claim(key,lane=0)
 ns['claim_resource']=claim
 value=ModuleType(__name__+'.private_dispatch');value.__dict__.update(ns)
 return value
