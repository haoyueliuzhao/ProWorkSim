"""Deployment recovery of the original120 attempts, not a second pilot.

Authority combines the original specific grant, the user's later standing
experimental-Docker permission and an explicit implementation amendment.
"""
from __future__ import annotations

from collections import Counter
import fcntl
import os
from pathlib import Path
import resource
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_scope_v142 as previous
import copy
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_alignment_contract_v157 import GROUP_IDS, validate_plan_identity

ROOT = original.ROOT
VERSION = 'v157-review2-communication-pilot-scope-r1'
BATCH_ROOT = ROOT/'runs/software-benchmark-v157/communication-pilot24-r1'
STATE_ROOT = BATCH_ROOT
ARTIFACT_ROOT = ROOT/'artifacts/software-benchmark-v157'
API_ROOT = STATE_ROOT/'api-coordinator'
COORDINATOR_ROOT = STATE_ROOT/'grading-coordinator-r3'
GRADING_ROOT = STATE_ROOT/'grading'
PLAN_FILE = STATE_ROOT/'execution-plan-r2.json'
INVENTORY_FILE = STATE_ROOT/'inventory.json'
SOURCE_FILE = STATE_ROOT/'runtime-sources.json'
CPU_POOL_FILE = STATE_ROOT/'host-cpu-pool.json'
AUTH_FILE = ROOT/'config/v157-communication-pilot-authorization.json'
ENV_AUTH_FILE = ROOT/'config/v157-communication-environment-authorization-r3.json'
DIAGNOSTIC_AUTH_FILE = ROOT/'config/v157-communication-diagnostic-authorization.json'
PROPOSAL_FILE = ARTIFACT_ROOT/'runtime-authorization-r1/proposal.json'
USER_GRANT_FILE = ROOT/'config/v157-communication-pilot-user-grant.json'
STANDING_POLICY_FILE = ROOT/'config/v143-standing-docker-user-policy.json'
STANDING_PERMISSION_FILE = STANDING_POLICY_FILE
PANEL_FILE = ROOT/'artifacts/software-benchmark-v156/communication-design-r1/approved-panel.json'
SOURCE_PLAN_FILE = ROOT/'runs/software-benchmark-v066/v064-continuation-r3/plan.json'
LEDGER_FILE = BATCH_ROOT/'ledgers/pilot.sqlite'
LEDGER_FILES = {group:LEDGER_FILE for group in GROUP_IDS}
BUDGET_BASELINE_FILE = BATCH_ROOT/'cash-authority.json'
PREPARATION_QUALIFICATION_FILE = API_ROOT/'preparation-qualification.json'
CASH_MODE = 'independent_CNY500_communication_pilot_shared_by_all_three_conditions'
CASH_CAP_CNY = '500.00'
API_UNIT = 'proworksim-v157-communication-pilot.service'
CLAIM_FILE = API_ROOT/'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT/'resource-claims/active-v157-coordinator.json'
GIB=1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*GIB,30*GIB
MAX_GENERATIONS,MAX_GRADERS,MANAGER_CPUS,NOFILE = 16,2,8,16384
MAX_STARTUPS=4
CONTAINER_PARENT=None
FIRST_PHYSICAL_INDEX,LAST_PHYSICAL_INDEX,DIAGNOSTIC_INDEX=15700,15771,1
ResourceBusy=original.ResourceBusy
CONSTRAINTS={**previous.CONSTRAINTS,
 'fresh_generation_slots':72,'generation_token_upper_bound':360_000_000,
 'api_generation_token_upper_bound':360_000_000,'api_total_budget_cny':CASH_CAP_CNY,
 'api_budget_shared_across_groups':True,'cash_budget_scope':CASH_MODE,'old_ledgers_untouched':True,
 'maximum_actor_containers':75,'maximum_controller_containers':75,
 'maximum_control_containers':48,'maximum_code_score_containers':72,
 'maximum_delivery_score_containers':72,'maximum_score_containers':144,
 'maximum_containers':342,'maximum_named_volumes':75,
 'zero_model_diagnostic_pairs':3,'initial_zero_model_diagnostic_pairs':3,
 'conditional_zero_model_repair_pairs':0,'new_owned_user_units':[API_UNIT],
 'maximum_combined_reserved_cpu':112,'maximum_combined_reserved_memory_bytes':840*GIB,
 'maximum_concurrent_startups':MAX_STARTUPS,'maximum_active_containers':34,
 'coordinator_memory_bytes':API_MEMORY_BYTES,'coordinator_cpu_quota_percent':800,
 'actor_cpu':4,'actor_memory_bytes':16*GIB,'controller_cpu':2,'controller_memory_bytes':32*GIB,
 'grader_cpu':4,'grader_memory_bytes':16*GIB,'host_grading_process_memory_bytes':4*GIB,
 'active_actor_limit':16,'active_controller_limit':16,'active_grader_limit':2,
 'maximum_active_generation_episodes':16,'generation_pair_reserved_cpu':6,
 'generation_pair_reserved_memory_bytes':48*GIB,'memory_minimum_free_bytes':64*GIB,
 'disk_minimum_free_bytes':128*GIB,'maximum_real_tls_sessions':0,
 'real_tls_all_sessions_payload_bytes':0,'real_tls_all_sessions_connections':0,
 'real_tls_session_connections':0,'real_tls_session_payload_bytes':0,
 'system_parent_slice_created':False,'aggregate_memory_limit_kind':'sum_of_bounded_owned_objects',
 'host_namespaces_or_mount_configuration_changed':False,'automatic_replay':False,
 'physical_gpus':[],'new_model_calls_for_preparation':0}

def load(ref):
    return original._cached_json(ref)

def retain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if load(reference(path)) != value:
            raise ValueError('Prepared v143 identity changed: '+str(path))
        return reference(path)
    return write_new(path, value)

def host_cpu_pool():
    value = load(reference(CPU_POOL_FILE))
    pool = value['cpu_ids']
    if (value.get('uid') != os.getuid() or len(pool) < 112 or len(pool) != len(set(pool))
            or any(type(cpu) is not int or cpu < 0 for cpu in pool)):
        raise ValueError('The frozen available CPU inventory changed')
    return pool

def cpu_set(role, index=0):
    if type(index) is not int or index < 0:
        raise ValueError('A nonnegative fixed lane is required')
    if role == 'coordinator' and index == 0:
        start, stop = 0, 8
    elif role in {'actor', 'controller'} and index < MAX_GENERATIONS:
        start = 8 + 6*index + (4 if role == 'controller' else 0)
        stop = start + (2 if role == 'controller' else 4)
    elif role == 'grader' and index < MAX_GRADERS:
        start, stop = 104+4*index, 108+4*index
    else:
        raise ValueError('Resource is outside the pilot CPU lanes')
    return ','.join(map(str, host_cpu_pool()[start:stop]))


def verify_host_limits(role='api'):
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if role != 'api' or len(paths) != 1 or Path(paths[0]).name != API_UNIT:
        raise PermissionError('Use the separately bounded v143 ordinary-user service')
    folder = Path('/sys/fs/cgroup')/paths[0].lstrip('/')
    limits = {key: (folder/key).read_text().strip()
              for key in ('memory.max', 'memory.high', 'memory.swap.max', 'pids.max')}
    if (limits != {'memory.max': str(API_MEMORY_BYTES), 'memory.high': str(API_MEMORY_HIGH_BYTES),
                   'memory.swap.max': '0', 'pids.max': '512'}
            or sorted(os.sched_getaffinity(0)) != host_cpu_pool()[:8]
            or resource.getrlimit(resource.RLIMIT_NOFILE)[0] < NOFILE):
        raise PermissionError('API manager resource limits differ from the reviewed scope')
    return {'uid': os.getuid(), 'cgroup': paths[0], 'limits': limits,
            'cpu_affinity': sorted(os.sched_getaffinity(0)), 'nofile': resource.getrlimit(resource.RLIMIT_NOFILE)[0]}

def _budget(active, cpu, memory, spool=0):
    workers = [r for r in active if r['spec']['role'] != 'auxiliary_coordinator']
    used_cpu = MANAGER_CPUS + sum(r['reserved_cpu'] for r in workers)
    # Two fixed host scorer subprocesses share grader cores, but not its memory cap.
    used_memory = API_MEMORY_BYTES + 8*GIB + sum(r['reserved_memory_bytes'] for r in workers)
    graders = sum(r['spec']['role'] in {'score', 'delivery_score', 'control'} for r in workers)
    if cpu == 4 and memory == 16*GIB and spool == 0 and graders >= MAX_GRADERS:
        raise ResourceBusy('Both bounded grading lanes are occupied')
    if (used_cpu+cpu > CONSTRAINTS['maximum_combined_reserved_cpu']
            or used_memory+memory > CONSTRAINTS['maximum_combined_reserved_memory_bytes']):
        raise ResourceBusy('Pilot aggregate CPU/RAM reservations are full')
    capacity = dispatch_view().physical_capacity()
    spool_total = spool+sum(r.get('reserved_spool_bytes', 0) for r in active)
    if (os.getloadavg()[0] > len(host_cpu_pool())-16
            or capacity['memory_available_bytes'] < CONSTRAINTS['memory_minimum_free_bytes']+memory
            or capacity['disk_free_bytes'] < CONSTRAINTS['disk_minimum_free_bytes']+spool_total):
        raise ResourceBusy('Actual shared-host CPU, memory or disk headroom prevents admission')
    return {'reserved_cpu_after': used_cpu+cpu, 'reserved_memory_bytes_after': used_memory+memory,
            'reserved_payload_spool_bytes_after': spool_total, 'physical_at_admission': capacity,
            'spool_is_filesystem_quota': False}


def dispatch_view(guard=None):
    guard = guard or require_allowed
    namespace = clone_namespace(original, VERSION=VERSION, BATCH_ROOT=BATCH_ROOT,
        PLAN_FILE=PLAN_FILE, RESUME_FILE=INVENTORY_FILE, SOURCE_INDEX_FILE=SOURCE_FILE,
        CPU_POOL_FILE=CPU_POOL_FILE, GRADING_ROOT=GRADING_ROOT,
        COORDINATOR_RUN_ROOT=COORDINATOR_ROOT, AUTHORIZATION_FILE=(DIAGNOSTIC_AUTH_FILE if guard is require_diagnostic_allowed else AUTH_FILE if AUTH_FILE.is_file() else ENV_AUTH_FILE),
        CONSTRAINTS=CONSTRAINTS, __file__=__file__)
    def allowed(operation='v066.run', **identity):
        value = guard(operation, **identity)
        return {**value, 'plan': reference(PLAN_FILE), 'sources': value['source_index'],
                'constraints': CONSTRAINTS}
    namespace.update(require_v066_allowed=allowed, host_cpu_pool=host_cpu_pool,
                     cpu_set=cpu_set, _budget=_budget)
    original_claim = namespace['claim_resource']
    def claim_resource(key, *, lane=None):
        if guard is require_diagnostic_allowed or not AUTH_FILE.is_file():
            restricted = guard('v066.run')
            if key not in restricted['resource_keys']:
                raise PermissionError('Environment-only authority cannot create model/actor/candidate objects')
        if key not in load(reference(PLAN_FILE))['resources']:
            raise PermissionError('Resource is outside the fresh pilot')
        return original_claim(key, lane=lane)
    namespace['claim_resource'] = claim_resource
    module = ModuleType(__name__+'.private_dispatch')
    module.__dict__.update(namespace)
    return module

def reserve_api_coordinator():
    require_allowed()
    CLAIM_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with (LEASE_FILE.parent/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CLAIM_FILE.exists():
            if LEASE_FILE.exists() and LEASE_FILE.read_bytes() == CLAIM_FILE.read_bytes():
                return reference(CLAIM_FILE)
            raise ValueError('An already consumed manager identity cannot restart')
        capacity = dispatch_view().physical_capacity()
        if not capacity['passed'] or capacity['memory_available_bytes'] < 96*GIB:
            raise ResourceBusy('Actual headroom prevents manager admission')
        value = {'version': VERSION, 'key': 'v157-api-coordinator',
            'spec': {'role': 'auxiliary_coordinator', 'unit': API_UNIT},
            'reserved_cpu': MANAGER_CPUS, 'reserved_memory_bytes': API_MEMORY_BYTES,
            'reserved_spool_bytes': 0, 'lease': str(LEASE_FILE),
            'authorization': reference(AUTH_FILE), 'physical_at_admission': capacity}
        raw = original._write_claim(CLAIM_FILE, value)
        with LEASE_FILE.open('xb') as stream:
            stream.write(raw)
        return reference(CLAIM_FILE)

def release_api_coordinator(ref):
    value = load(ref)
    if Path(ref['path']).resolve() != CLAIM_FILE or value.get('lease') != str(LEASE_FILE):
        raise PermissionError('Foreign coordinator reservation')
    with (LEASE_FILE.parent/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if LEASE_FILE.exists():
            if LEASE_FILE.read_bytes() != checked(ref).read_bytes():
                raise PermissionError('Coordinator lease ownership changed')
            LEASE_FILE.unlink()
        return retain(API_ROOT/'coordinator-capacity-released.json', {'claim': ref, 'released': True})

def validate_plan(plan):
    panel=load(reference(PANEL_FILE))
    if plan.get('version')!=VERSION or plan.get('panel')!=reference(PANEL_FILE) or plan.get('constraints')!=CONSTRAINTS:
        raise PermissionError('Plan scope, frozen panel or resource limits changed')
    rows=plan.get('rows',[])
    if len(rows)!=72 or len({r['slot_id'] for r in rows})!=72:
        raise PermissionError('Exactly 72 prespecified independent attempts are required')
    for actual, selected in zip(rows,panel['rows']):
        validate_plan_identity(actual)
        for key in ('instance_id','seed','wave','task_index','logical_index','condition_order_index'):
            if actual[key]!=selected[key]: raise PermissionError('Prespecified task/order/seed changed')
        if actual['group_id']!=selected['condition'] or actual['slot_index']!=15700+selected['logical_index']:
            raise PermissionError('Communication condition/order/physical identity changed')
    counts=dict(Counter(v['role'] for v in plan['resources'].values()))
    if counts!={'actor':75,'controller':75,'volume':75,'score':72,'delivery_score':72,'control':48}:
        raise PermissionError('Exact owned-resource ceiling changed')
    return plan

def never_consumed(row):
    validate_plan_identity(row)
    return not any((BATCH_ROOT/'resource-claims'/f"{role}-{row['slot_index']}.json").exists()
                   for role in ('actor','controller','volume'))

def require_allowed(operation='v157.run', *, slot_id=None, instance_id=None, grading_only=False):
    allowed={'v157.run','v157.api.run','v157.api.request','v157.prepare','v105.run'} | (set(original.OPERATIONS)-{'v066.model.start','v066.transport','v066.resolve'})
    if os.getuid()==0 or os.geteuid()==0 or operation not in allowed:
        raise PermissionError('Only ordinary-user isolated communication pilot operations are allowed')
    if grading_only and operation not in {'v157.run','v105.run','v066.run','v066.score','v066.delivery.score','v066.control','v066.grader.create','v066.grader.start'}:
        raise PermissionError('Grading cannot start generation, call API or open network')
    if not AUTH_FILE.is_file(): raise PermissionError('Pilot source and gate authority not sealed')
    auth=load(reference(AUTH_FILE))
    if (auth.get('version')!=VERSION or auth.get('status')!='approved'
        or auth.get('plan')!=reference(PLAN_FILE) or auth.get('source_index')!=reference(SOURCE_FILE)
        or auth.get('proposal')!=reference(PROPOSAL_FILE) or auth.get('user_grant')!=reference(USER_GRANT_FILE)
        or auth.get('API_cash_cap_CNY')!=CASH_CAP_CNY or auth.get('constraints')!=CONSTRAINTS
        or auth.get('shared_host_configuration_changes')!=0):
        raise PermissionError('Frozen pilot authority changed')
    grant=load(auth['user_grant'])
    if grant.get('approved') is not True or grant.get('API_cash_cap_CNY')!=CASH_CAP_CNY:
        raise PermissionError('The actual user continuation and500-yuan authority must be recorded')
    gate=load(auth['gate'])
    if gate.get('passed') is not True or gate.get('source_token_mode')!='estimated_provider_total_authoritative':
        raise PermissionError('Source-estimate pilot gate has not passed')
    for item in load(auth['source_index'])['files']: checked(item)
    plan=validate_plan(load(auth['plan']))
    if slot_id is not None:
        matched=[r for r in plan['rows'] if r['slot_id']==slot_id]
        if len(matched)!=1 or instance_id not in (None,matched[0]['instance_id']):
            raise PermissionError('Identity is outside the frozen72 attempts')
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Task is outside frozen24 panel')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.is_file() or LEASE_FILE.read_bytes()!=checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No live exact API owner')
    return auth

def require_environment_allowed(operation='v157.run', *, slot_id=None, instance_id=None):
    if (os.getuid()==0 or os.geteuid()==0 or slot_id is not None
        or operation not in {'v157.run','v105.run','v066.run','v066.control','v066.grader.create','v066.grader.start'}):
        raise PermissionError('Environment-only authority admits no model, actor, candidate or network')
    auth=load(reference(ENV_AUTH_FILE))
    if (auth.get('version')!='v157-zero-model-environment-authority-r1' or auth.get('status')!='approved'
        or auth.get('plan')!=reference(PLAN_FILE) or auth.get('maximum_containers')!=4
        or auth.get('maximum_concurrent_graders')!=2 or auth.get('model_calls')!=0
        or auth.get('shared_host_configuration_changes')!=0 or auth.get('network_mode')!='none'
        or auth.get('standing_policy')!=reference(STANDING_POLICY_FILE)):
        raise PermissionError('The exact four-control standing-policy scope changed')
    if instance_id is not None and instance_id not in auth['instance_ids']:
        raise PermissionError('Environment control task outside the two missing qualifications')
    for ref in load(auth['source_index'])['files']: checked(ref)
    return auth

def require_grading_allowed(operation='v157.run', **identity):
    if not AUTH_FILE.is_file():
        return require_environment_allowed(operation,**identity)
    return require_allowed(operation,grading_only=True,**identity)


def require_diagnostic_allowed(operation='v066.run', *, slot_id=None, instance_id=None):
    from .software_benchmark_alignment_contract_v157 import VERSION as ALIGNMENT_VERSION
    if (os.getuid()==0 or os.geteuid()==0 or operation not in {'v066.run','v066.actor.create',
            'v066.actor.start','v066.controller.create','v066.controller.start','v066.volume.create'}):
        raise PermissionError('Zero-model diagnostics cannot request API, grading, network or GPU')
    auth=load(reference(DIAGNOSTIC_AUTH_FILE))
    plan=validate_plan(load(reference(PLAN_FILE)))
    keys=[f'diagnostic-{i}-{role}' for i in (1,2,3) for role in ('actor','controller','volume')]
    if (auth.get('version')!='v157-zero-model-diagnostic-authority-r1' or auth.get('status')!='approved'
        or auth.get('plan')!=reference(PLAN_FILE) or auth.get('resource_keys')!=keys
        or auth.get('maximum_containers')!=6 or auth.get('maximum_named_volumes')!=3
        or auth.get('maximum_concurrent_pairs')!=1 or auth.get('model_calls')!=0
        or auth.get('shared_host_configuration_changes')!=0
        or auth.get('standing_policy')!=reference(STANDING_POLICY_FILE)):
        raise PermissionError('The three exact zero-model diagnostics are not independently sealed')
    diagnostics=plan['diagnostics']
    if slot_id is not None and slot_id not in {r['slot_id'] for r in diagnostics}:
        raise PermissionError('Only the three declared diagnostic task/condition identities')
    if instance_id is not None and instance_id not in {r['instance_id'] for r in diagnostics}:
        raise PermissionError('Diagnostic task identity changed')
    for ref in load(auth['source_index'])['files']: checked(ref)
    return {**auth,'execution_alignment_version':ALIGNMENT_VERSION,'constraints':CONSTRAINTS}
