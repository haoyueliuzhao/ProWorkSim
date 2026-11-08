"""Only two new1724 environment controls and one separately bounded probe.

No v157 source, claim, authority, API allowance or service is modified. The new
lane uses the next four frozen host CPUs; no host settings are changed. Import
and validation are read-only; explicit callers create their own project files.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace

ROOT=original.ROOT
VERSION='v158-requests1724-two-controls-scope-r1'
TASK='psf__requests-1724'
TASKS=TLS_TASKS=frozenset({TASK})
BATCH_ROOT=ROOT/'runs/software-benchmark-v158/requests1724-environment-r1'
STATE_ROOT=BATCH_ROOT
ARTIFACT_ROOT=ROOT/'artifacts/software-benchmark-v158'
COORDINATOR_ROOT=BATCH_ROOT/'coordinator'
GRADING_ROOT=BATCH_ROOT/'grading'
PLAN_FILE=BATCH_ROOT/'plan.json'
INVENTORY_FILE=BATCH_ROOT/'inventory.json'
SOURCE_FILE=BATCH_ROOT/'runtime-sources.json'
RESOLUTION_FILE=BATCH_ROOT/'network-resolution.json'
NETWORK_RESOLUTION_FILE=RESOLUTION_FILE
SOURCE_CPU_POOL_FILE=ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/host-cpu-pool.json'
CPU_POOL_FILE=SOURCE_CPU_POOL_FILE
AUTH_FILE=ROOT/'config/v158-requests1724-control-authorization.json'
ENV_AUTH_FILE=AUTH_FILE
PROBE_AUTH_FILE=ROOT/'config/v158-requests1724-probe-authorization.json'
STANDING_POLICY_FILE=ROOT/'config/v143-standing-docker-user-policy.json'
STANDING_PERMISSION_FILE=STANDING_POLICY_FILE
CONTROL_KEYS=('control-'+TASK+'-gold','control-'+TASK+'-empty')
MAX_GRADERS=1
GIB=1024**3
ResourceBusy=original.ResourceBusy
validate_ipv4_targets=original.validate_ipv4_targets
validate_connect_target=original.validate_connect_target
check_ipv4=validate_ipv4_targets
CONSTRAINTS={
    'fresh_generation_slots':0,'generation_token_upper_bound':0,'api_generation_token_upper_bound':0,
    'api_total_budget_cny':'0','model_calls':0,'maximum_actor_containers':0,'maximum_controller_containers':0,
    'maximum_control_containers':2,'maximum_code_score_containers':0,'maximum_delivery_score_containers':0,
    'maximum_score_containers':0,'maximum_containers':2,'maximum_named_volumes':0,
    'maximum_active_containers':1,'active_actor_limit':0,'active_controller_limit':0,'active_grader_limit':1,
    'maximum_combined_reserved_cpu':4,'maximum_combined_reserved_memory_bytes':20*GIB,
    'grader_cpu':4,'grader_memory_bytes':16*GIB,'host_grading_process_memory_bytes':4*GIB,
    'pids_limit':512,'memory_minimum_free_bytes':64*GIB,'disk_minimum_free_bytes':128*GIB,
    'generation_pair_reserved_cpu':0,'generation_pair_reserved_memory_bytes':0,'generation_pair_payload_spool_bytes':0,
    'container_network':'none','container_cap_add':['NET_BIND_SERVICE'],'container_cap_drop':['ALL'],
    'no_new_privileges':True,'privileged':False,'host_bind_mounts':False,'published_ports':False,
    'host_devices_or_gpu_in_containers':False,'physical_gpus':[],'new_owned_user_units':[],
    'maximum_real_tls_sessions':2,'real_tls_session_connections':512,
    'real_tls_session_payload_bytes':64*1024**2,'real_tls_all_sessions_connections':1024,
    'real_tls_all_sessions_payload_bytes':128*1024**2,
    'endpoint_probe_maximum_connections':4,'endpoint_probe_maximum_application_bytes':64*1024,
    'shared_host_configuration_changes':0,'automatic_replay':False,
}
OPERATIONS=frozenset({'v158.run','v158.prepare','v105.run','v066.run','v066.control',
    'v066.grader.create','v066.grader.start','v066.transport'})


def load(ref):
    return original._cached_json(ref)


def retain(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if load(reference(path))!=value:
            raise ValueError('Never replace frozen1724 scope/evidence')
        return reference(path)
    return write_new(path,value)


def host_cpu_pool():
    value=load(reference(SOURCE_CPU_POOL_FILE));cpus=value.get('cpu_ids')
    if (value.get('uid')!=os.getuid() or not isinstance(cpus,list) or len(cpus)<116
            or cpus!=sorted(set(cpus)) or any(type(cpu) is not int or cpu<0 for cpu in cpus)):
        raise ValueError('The existing frozen shared-server CPU inventory differs')
    return cpus


def cpu_set(role,index=0):
    if role!='grader' or type(index) is not int or index!=0:
        raise ValueError('Only the one new1724 grading lane is admitted')
    return ','.join(map(str,host_cpu_pool()[112:116]))


def validate_plan(plan):
    resources=plan.get('resources',{})
    if (plan.get('version')!=VERSION or plan.get('constraints')!=CONSTRAINTS
            or set(plan.get('environments',{}))!={TASK} or set(resources)!=set(CONTROL_KEYS)
            or plan.get('model_calls',0)!=0 or plan.get('rows',[]) or plan.get('generation_rows',[])):
        raise ValueError('Only the exact two new1724 environment controls are planned')
    image=plan['environments'][TASK].get('image_id')
    for key in CONTROL_KEYS:
        row=resources[key]
        if (row.get('role')!='control' or row.get('instance_id')!=TASK
                or row.get('patch_kind')!=key.rsplit('-',1)[1] or row.get('image_id')!=image):
            raise ValueError('A control changed task, patch type, or pinned image')
    if plan.get('host_cpu_pool')!=reference(SOURCE_CPU_POOL_FILE):
        raise ValueError('The new lane must use the exact existing frozen CPU pool')
    return plan


def _sources(auth):
    refs=load(auth['source_index']).get('files')
    if not isinstance(refs,list) or not refs:
        raise PermissionError('The actual independent1724 source closure must be sealed')
    names={str(Path(row['path']).resolve()) for row in refs}
    if str(Path(__file__).resolve()) not in names or len(names)!=len(refs):
        raise PermissionError('The1724 guard source is missing or duplicated')
    for ref in refs:
        if not Path(ref['path']).resolve().is_relative_to(ROOT.resolve()):
            raise PermissionError('A scoring source is outside this project')
        checked(ref)


def require_grading_allowed(operation='v158.run',*,slot_id=None,instance_id=None):
    if (os.getuid()==0 or os.geteuid()==0 or operation not in OPERATIONS or slot_id is not None
            or instance_id not in (None,TASK)):
        raise PermissionError('No model, candidate, foreign task, root operation or unrelated service')
    auth=load(reference(AUTH_FILE))
    if (auth.get('version')!='v158-requests1724-control-authority-r1' or auth.get('status')!='approved'
            or auth.get('plan')!=reference(PLAN_FILE) or auth.get('scope')!=reference(__file__)
            or auth.get('standing_policy')!=reference(STANDING_POLICY_FILE)
            or auth.get('resource_keys')!=list(CONTROL_KEYS) or auth.get('constraints')!=CONSTRAINTS
            or auth.get('maximum_containers')!=2 or auth.get('maximum_concurrent_graders')!=1
            or auth.get('model_calls')!=0 or auth.get('shared_host_configuration_changes')!=0
            or auth.get('maximum_real_tls_sessions')!=2
            or auth.get('maximum_tcp_connections_total')!=1024
            or auth.get('maximum_transfer_bytes_total')!=128*1024**2):
        raise PermissionError('The separately approved exact1724 control scope changed')
    validate_plan(load(auth['plan']));_sources(auth)
    return auth


require_allowed=require_grading_allowed
require_v066_allowed=require_grading_allowed


def require_probe_allowed(operation='v158.probe'):
    if os.getuid()==0 or os.geteuid()==0 or operation!='v158.probe':
        raise PermissionError('Only the separate ordinary-user bounded probe is admitted')
    auth=load(reference(PROBE_AUTH_FILE))
    if (auth.get('version')!='v158-requests1724-probe-authority-r1' or auth.get('status')!='approved'
            or auth.get('scope')!=reference(__file__)
            or auth.get('standing_policy')!=reference(STANDING_POLICY_FILE)
            or auth.get('instance_id')!=TASK or auth.get('hostname')!='httpbin.org'
            or auth.get('ports')!=[80,443] or auth.get('maximum_connections')!=4
            or auth.get('maximum_application_bytes')!=64*1024 or auth.get('model_calls')!=0
            or auth.get('Docker_operations')!=0 or auth.get('shared_host_configuration_changes')!=0):
        raise PermissionError('The standalone1724 endpoint-probe authority changed')
    _sources(auth)
    return auth


def _budget(active,cpu,memory,spool=0):
    if active or cpu!=4 or memory!=16*GIB or spool!=0:
        raise ResourceBusy('Only one bounded1724 control may occupy its new lane')
    physical=dispatch_view().physical_capacity()
    if (not physical['passed'] or physical['memory_available_bytes']<64*GIB+20*GIB
            or os.getloadavg()[0]>len(host_cpu_pool())-16):
        raise ResourceBusy('Preserve actual shared-server CPU, memory and disk headroom')
    return {'reserved_cpu_after':4,'reserved_memory_bytes_after':20*GIB,
            'reserved_payload_spool_bytes_after':0,'physical_at_admission':physical,
            'host_scoring_process_shares_grader_CPU_set':True}


def dispatch_view(guard=None):
    guard=guard or require_grading_allowed
    ns=clone_namespace(original,VERSION=VERSION,BATCH_ROOT=BATCH_ROOT,PLAN_FILE=PLAN_FILE,
        RESUME_FILE=INVENTORY_FILE,SOURCE_INDEX_FILE=SOURCE_FILE,CPU_POOL_FILE=CPU_POOL_FILE,
        GRADING_ROOT=GRADING_ROOT,COORDINATOR_RUN_ROOT=COORDINATOR_ROOT,AUTHORIZATION_FILE=AUTH_FILE,
        CONSTRAINTS=CONSTRAINTS,TLS_TASKS=TLS_TASKS,__file__=__file__)
    def allowed(operation='v066.run',**identity):
        auth=guard(operation,**identity)
        return {**auth,'sources':auth['source_index'],'constraints':CONSTRAINTS}
    ns.update(require_v066_allowed=allowed,host_cpu_pool=host_cpu_pool,cpu_set=cpu_set,_budget=_budget)
    original_claim=ns['claim_resource']
    def claim_resource(key,*,lane=None):
        if key not in CONTROL_KEYS or lane not in (None,0):
            raise PermissionError('Only the two new1724 controls on lane0 may be claimed')
        guard('v066.run')
        return original_claim(key,lane=0)
    ns['claim_resource']=claim_resource
    result=ModuleType(__name__+'.private_dispatch');result.__dict__.update(ns)
    return result
