"""Owned no-network containers and ordinary-user execution for the60-run pilot."""
from collections import Counter
import fcntl
import os
from pathlib import Path
import resource
import shutil
import inspect
from functools import lru_cache
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_candidates_v054 import checked,reference,write_new
from .software_benchmark_alignment_contract_v193 import GROUP_IDS,validate_plan_identity,VERSION as ALIGNMENT_VERSION

ROOT=original.ROOT
VERSION='v193-four-context-S1-private-runtime-r1'
BATCH_ROOT=STATE_ROOT=ROOT/'runs/software-benchmark-v055/secondary-volume-r1/software-benchmark-v193/key-event-pilot-r1'
ARTIFACT_ROOT=ROOT/'artifacts/software-benchmark-v193'
API_ROOT=STATE_ROOT/'api-coordinator';COORDINATOR_ROOT=STATE_ROOT/'grading-coordinator';GRADING_ROOT=STATE_ROOT/'grading'
PLAN_FILE=STATE_ROOT/'execution-plan.json';INVENTORY_FILE=STATE_ROOT/'inventory.json';SOURCE_FILE=STATE_ROOT/'runtime-sources.json'
PANEL_FILE=ROOT/'artifacts/software-benchmark-v191/full-task-design-r1/plan.json'
SOURCE_PLAN_FILE=ROOT/'runs/software-benchmark-v066/v064-continuation-r3/plan.json'
CPU_POOL_FILE=STATE_ROOT/'cpu-pool.json'
AUTH_FILE=ROOT/'config/v193-context-task-runtime-authorization.json'
PROPOSAL_FILE=ARTIFACT_ROOT/'runtime-authorization-r1/proposal.json'
USER_GRANT_FILE=ARTIFACT_ROOT/'runtime-authorization-r1/user-authority.json'
LEDGER_FILE=BATCH_ROOT/'api-ledger.sqlite'
LEDGER_FILES={g:LEDGER_FILE for g in GROUP_IDS}
CASH_CAP_CNY='300.00';CASH_MODE='new_v193_ledger_interleaved_repeats_earmarked'
API_UNIT='proworksim-v193-context-pilot.service'
CLAIM_FILE=API_ROOT/'coordinator-capacity.json';LEASE_FILE=BATCH_ROOT/'resource-claims/active-coordinator.json'
PREPARATION_QUALIFICATION_FILE=API_ROOT/'preparation-qualification.json'
GIB=1024**3
MAX_GENERATIONS,MAX_GRADERS,MAX_STARTUPS,MANAGER_CPUS,NOFILE=4,2,2,8,16384
API_MEMORY_BYTES,API_MEMORY_HIGH_BYTES=32*GIB,30*GIB
CONTAINER_PARENT=None
FIRST_PHYSICAL_INDEX,LAST_PHYSICAL_INDEX=19300,19359
STORAGE_POLICY={'artifact_root':str(BATCH_ROOT),'artifact_minimum_free_bytes':128*GIB,
 'existing_Docker_root':str(ROOT/'runs/software-panel-v053/docker/data'),
 'Docker_minimum_free_bytes':100*GIB,'additional_pair_spool_bytes':4*GIB,
 'new_mounts_or_shared_configuration_changes':False}
ResourceBusy=original.ResourceBusy
CONSTRAINTS={**original.CONSTRAINTS,'fresh_generation_slots':60,'generation_token_upper_bound':300_000_000,
 'api_generation_token_upper_bound':300_000_000,'api_total_budget_cny':CASH_CAP_CNY,'api_budget_shared_across_groups':True,
 'cash_budget_scope':CASH_MODE,'maximum_actor_containers':64,'maximum_controller_containers':64,
 'maximum_control_containers':24,'maximum_code_score_containers':60,'maximum_delivery_score_containers':60,
 'maximum_score_containers':120,'maximum_containers':272,'maximum_named_volumes':64,
 'zero_model_diagnostic_pairs':4,'maximum_model_residents':0,'physical_gpus':[],
 'neutral_model_preparation_calls':0,'api_neutral_preparation_calls':0,'free_api_metadata_requests':0,
 'new_owned_user_units':[API_UNIT],'maximum_combined_reserved_cpu':40,'maximum_combined_reserved_memory_bytes':264*GIB,
 'actor_cpu':4,'actor_memory_bytes':16*GIB,'controller_cpu':2,'controller_memory_bytes':32*GIB,
 'grader_cpu':4,'grader_memory_bytes':16*GIB,'host_grading_process_memory_bytes':4*GIB,
 'host_grading_cpu_shared_with_own_container':True,'active_actor_limit':4,'active_controller_limit':4,'active_grader_limit':2,
 'generation_pair_reserved_cpu':6,'generation_pair_reserved_memory_bytes':48*GIB,
 'maximum_active_generation_episodes':4,'maximum_active_containers':10,'maximum_concurrent_startups':2,
 'coordinator_memory_bytes':32*GIB,'coordinator_cpu_quota_percent':800,
 'memory_minimum_free_bytes':64*GIB,'disk_minimum_free_bytes':128*GIB,
 'requests_private_capability_tasks':['psf__requests-5414'],'requests_private_grader_cap_add':['NET_ADMIN'],'requests_extra_hosts':{},
 'maximum_real_tls_sessions':0,'real_tls_all_sessions_connections':0,'real_tls_all_sessions_payload_bytes':0,
 'host_namespaces_or_mount_configuration_changed':False,'system_parent_slice_created':False,
 'aggregate_memory_limit_kind':'sum_of_owned_bounded_objects','automatic_replay':False,
 'new_model_calls_for_preparation':0,'cash_limit_mode':'new_paired_block_start_only','finish_started_teams_above_cash_threshold':True}


def load(ref):return original._cached_json(ref)


def retain(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if load(reference(path))!=value:raise ValueError('An immutable prepared object changed: '+str(path))
        return reference(path)
    return write_new(path,value)


def host_cpu_pool():
    value=load(reference(CPU_POOL_FILE));pool=value['cpu_ids']
    if value['uid']!=os.getuid() or len(pool)<40 or len(pool)!=len(set(pool)):raise ValueError('CPU inventory changed')
    return pool


def cpu_set(role,index=0):
    if role=='coordinator' and index==0:start,end=0,8
    elif role in ('actor','controller') and 0<=index<4:
        start=8+6*index+(4 if role=='controller' else 0);end=start+(2 if role=='controller' else 4)
    elif role=='grader' and 0<=index<2:start,end=32+4*index,36+4*index
    else:raise ValueError('Unknown owned CPU lane')
    return ','.join(map(str,host_cpu_pool()[start:end]))


def verify_host_limits(role='api'):
    paths=[l.split(':',2)[2] for l in Path('/proc/self/cgroup').read_text().splitlines() if l.startswith('0::')]
    if role!='api' or len(paths)!=1 or Path(paths[0]).name!=API_UNIT:raise PermissionError('Use the bounded ordinary-user coordinator')
    p=Path('/sys/fs/cgroup')/paths[0].lstrip('/')
    expected={'memory.max':str(API_MEMORY_BYTES),'memory.high':str(API_MEMORY_HIGH_BYTES),'memory.swap.max':'0','pids.max':'512'}
    if {k:(p/k).read_text().strip() for k in expected}!=expected:raise PermissionError('Own coordinator limits changed')
    if sorted(os.sched_getaffinity(0))!=host_cpu_pool()[:8]:raise PermissionError('Own coordinator CPU lane changed')
    return {'uid':os.getuid(),'cgroup':paths[0],'limits':expected}


def _budget(active,cpu,memory,spool=0):
    workers=[r for r in active if r['spec']['role']!='auxiliary_coordinator']
    used_cpu=8+sum(r['reserved_cpu'] for r in workers);used_memory=40*GIB+sum(r['reserved_memory_bytes'] for r in workers)
    if used_cpu+cpu>40 or used_memory+memory>264*GIB:raise ResourceBusy('Owned aggregate capacity full')
    physical=dispatch_view().physical_capacity();spools=spool+sum(r.get('reserved_spool_bytes',0) for r in workers)
    if (not physical['passed'] or os.getloadavg()[0]>len(host_cpu_pool())-16
        or physical['memory_available_bytes']<64*GIB+memory or physical['disk_free_bytes']<128*GIB+spools):
        raise ResourceBusy('Wait for actual shared-host headroom')
    if physical['docker_disk_free_bytes']<STORAGE_POLICY['Docker_minimum_free_bytes']+spools:
        raise ResourceBusy('Wait for the existing Docker filesystem headroom')
    return {'reserved_cpu_after':used_cpu+cpu,'reserved_memory_bytes_after':used_memory+memory,
        'reserved_payload_spool_bytes_after':spools,'physical_at_admission':physical,'spool_is_filesystem_quota':False}


def physical_capacity():
    available=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
    free=shutil.disk_usage(BATCH_ROOT).free
    docker_free=shutil.disk_usage(STORAGE_POLICY['existing_Docker_root']).free
    return {'memory_available_bytes':available,'disk_free_bytes':free,'docker_disk_free_bytes':docker_free,
        'passed':available>=CONSTRAINTS['memory_minimum_free_bytes'] and free>=128*GIB and docker_free>=100*GIB}


def validate_plan(plan):
    panel=load(reference(PANEL_FILE))
    if plan.get('panel')!=reference(PANEL_FILE) or len(plan['rows'])!=60 or plan.get('constraints')!=CONSTRAINTS:
        raise ValueError('Frozen four-policy panel or resource bounds changed')
    for actual,selected in zip(plan['rows'],panel['rows']):
        validate_plan_identity(actual)
        if any(actual[k]!=selected[k] for k in ('instance_id','repeat_index','primary_panel','framework_seed')) or actual['group_id']!=selected['condition']:
            raise ValueError('A task, repeat or condition was substituted')
    expected={'actor':64,'controller':64,'volume':64,'score':60,'delivery_score':60,'control':24}
    if dict(Counter(r['role'] for r in plan['resources'].values()))!=expected:raise ValueError('Owned object bounds changed')
    return plan


def require_allowed(operation='v193.run',*,slot_id=None,instance_id=None,grading_only=False):
    from .software_public_test_view_v193 import VERSION as TEST_VIEW
    if os.getuid()==0 or os.geteuid()==0:raise PermissionError('Host execution must be ordinary user')
    if operation not in ({'v193.run','v193.api.request','v193.prepare'}|set(original.OPERATIONS)-{'v066.model.start'}):
        raise PermissionError('Operation is outside this CPU/API experiment')
    auth=load(reference(AUTH_FILE))
    if (auth.get('status')!='approved' or auth.get('plan')!=reference(PLAN_FILE)
        or auth.get('source_index')!=reference(SOURCE_FILE) or auth.get('constraints')!=CONSTRAINTS
        or auth.get('execution_alignment_version')!=ALIGNMENT_VERSION or auth.get('cash_cap_CNY')!='300.00'
        or auth.get('common_public_test_view_revision')!=TEST_VIEW or auth.get('storage_policy')!=STORAGE_POLICY):
        raise PermissionError('Current explicit task/standing Docker authority is not bound')
    _verify_source_once(auth['source_index']['path'],auth['source_index']['sha256'],auth['source_index']['bytes'])
    plan=validate_plan(load(auth['plan']))
    if slot_id is not None and not any(r['slot_id']==slot_id and instance_id in (None,r['instance_id']) for r in plan['rows']):
        raise PermissionError('Foreign episode')
    if instance_id is not None and instance_id not in plan['environments']:raise PermissionError('Foreign task')
    if operation in {'v066.transport','v066.resolve'}:raise PermissionError('No scoring egress in this selected panel')
    if operation=='v193.api.request':verify_host_limits()
    return auth


@lru_cache(maxsize=2)
def _verify_source_once(path,sha256,size):
    for ref in load({'path':path,'sha256':sha256,'bytes':size})['files']:checked(ref)
    return True


def dispatch_view(guard=None):
    guard=guard or require_allowed
    ns=clone_namespace(original,VERSION=VERSION,BATCH_ROOT=BATCH_ROOT,PLAN_FILE=PLAN_FILE,
        RESUME_FILE=INVENTORY_FILE,SOURCE_INDEX_FILE=SOURCE_FILE,CPU_POOL_FILE=CPU_POOL_FILE,
        GRADING_ROOT=GRADING_ROOT,COORDINATOR_RUN_ROOT=COORDINATOR_ROOT,AUTHORIZATION_FILE=AUTH_FILE,
        CONSTRAINTS=CONSTRAINTS,__file__=__file__)
    def allowed(operation='v066.run',**identity):
        value=guard(operation,**identity)
        return {**value,'plan':reference(PLAN_FILE),'sources':value['source_index'],'constraints':CONSTRAINTS}
    ns.update(require_v066_allowed=allowed,host_cpu_pool=host_cpu_pool,cpu_set=cpu_set,_budget=_budget,
        physical_capacity=physical_capacity,STORAGE_POLICY=STORAGE_POLICY)
    source=inspect.getsource(original.claim_resource)
    for role in ('score','delivery_score','control'):
        source=source.replace('"'+role+'": ("grader", 4, 4, 16 * GIB)',
            '"'+role+'": ("grader", 2, 4, 16 * GIB)')
    exec(compile(source,__file__+':two-score-lanes','exec'),ns)
    module=ModuleType(__name__+'.private_dispatch');module.__dict__.update(ns);return module


def never_consumed(row):
    return not any((BATCH_ROOT/'resource-claims'/f'{role}-{row["slot_index"]}.json').exists() for role in ('actor','controller','volume'))


require_grading_allowed=require_allowed
