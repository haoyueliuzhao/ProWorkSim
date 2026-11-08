"""New deployment for never-called original communication tasks on the same500 ledger."""
from __future__ import annotations

from collections import Counter
import fcntl
import os
from pathlib import Path
import resource
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_scope_v142 as previous
from . import software_benchmark_scope_v157 as original_scope
import copy
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_alignment_contract_v157 import GROUP_IDS, validate_plan_identity

ROOT = original.ROOT
VERSION = 'v168-original-second-wave-scope-r1'
BATCH_ROOT = ROOT/'runs/software-benchmark-v168/communication-wave2-r1'
STATE_ROOT = BATCH_ROOT
ARTIFACT_ROOT = ROOT/'artifacts/software-benchmark-v168'
API_ROOT = STATE_ROOT/'api-coordinator'
COORDINATOR_ROOT = STATE_ROOT/'grading-coordinator'
GRADING_ROOT = STATE_ROOT/'grading'
PLAN_FILE = STATE_ROOT/'execution-plan.json'
INVENTORY_FILE = STATE_ROOT/'inventory.json'
SOURCE_FILE = STATE_ROOT/'runtime-sources.json'
COEXISTENCE_FILE = STATE_ROOT/'predecessor-coexistence.json'
CPU_POOL_FILE = original_scope.CPU_POOL_FILE
AUTH_FILE = ROOT/'config/v168-communication-recovery-authorization.json'
PROPOSAL_FILE = ARTIFACT_ROOT/'runtime-authorization-r1/proposal.json'
USER_GRANT_FILE = ROOT/'config/v168-communication-recovery-user-grant.json'
STANDING_POLICY_FILE = ROOT/'config/v143-standing-docker-user-policy.json'
STANDING_PERMISSION_FILE = STANDING_POLICY_FILE
PANEL_FILE = ROOT/'artifacts/software-benchmark-v156/communication-design-r1/approved-panel.json'
SOURCE_PLAN_FILE = ROOT/'runs/software-benchmark-v066/v064-continuation-r3/plan.json'
LEDGER_FILE = original_scope.LEDGER_FILE
LEDGER_FILES = {group:LEDGER_FILE for group in GROUP_IDS}
BUDGET_BASELINE_FILE = original_scope.BUDGET_BASELINE_FILE
PREPARATION_QUALIFICATION_FILE = API_ROOT/'preparation-qualification.json'
CASH_MODE = 'same_v157_CNY500_ledger_never_called_original_slots_only'
CASH_CAP_CNY = '500.00'
API_UNIT = 'proworksim-v168-communication-wave2.service'
CLAIM_FILE = API_ROOT/'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT/'resource-claims/active-v168-coordinator.json'
GIB=1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*GIB,30*GIB
MAX_GENERATIONS,MAX_GRADERS,MANAGER_CPUS,NOFILE = 16,2,8,16384
MAX_STARTUPS=4
CONTAINER_PARENT=None
FIRST_PHYSICAL_INDEX,LAST_PHYSICAL_INDEX,DIAGNOSTIC_INDEX=15736,15771,None
ResourceBusy=original.ResourceBusy
CONSTRAINTS={**previous.CONSTRAINTS,
 'fresh_generation_slots':36,'generation_token_upper_bound':180_000_000,
 'api_generation_token_upper_bound':180_000_000,'api_total_budget_cny':CASH_CAP_CNY,
 'api_budget_shared_across_groups':True,'cash_budget_scope':CASH_MODE,'old_ledgers_untouched':False,'existing_v157_ledger_continued':True,'unrelated_older_ledgers_untouched':True,
 'maximum_actor_containers':36,'maximum_controller_containers':36,
 'maximum_control_containers':0,'maximum_code_score_containers':36,
 'maximum_delivery_score_containers':36,'maximum_score_containers':72,
 'maximum_containers':144,'maximum_named_volumes':36,
 'zero_model_diagnostic_pairs':0,'initial_zero_model_diagnostic_pairs':0,
 'conditional_zero_model_repair_pairs':0,'new_owned_user_units':[API_UNIT],
 'maximum_combined_reserved_cpu':112,'maximum_combined_reserved_memory_bytes':840*GIB,
 'maximum_concurrent_startups':MAX_STARTUPS,'maximum_active_containers':34,
 'coordinator_memory_bytes':API_MEMORY_BYTES,'coordinator_cpu_quota_percent':800,
 'actor_cpu':4,'actor_memory_bytes':16*GIB,'controller_cpu':2,'controller_memory_bytes':32*GIB,
 'grader_cpu':4,'grader_memory_bytes':16*GIB,'host_grading_process_memory_bytes':4*GIB,
 'active_actor_limit':16,'active_controller_limit':16,'active_grader_limit':2,
 'maximum_active_generation_episodes':16,'generation_pair_reserved_cpu':6,
 'generation_pair_reserved_memory_bytes':48*GIB,'memory_minimum_free_bytes':64*GIB,
 'disk_minimum_free_bytes':128*GIB,'maximum_real_tls_sessions':6,
 'real_tls_all_sessions_payload_bytes':384*1024**2,'real_tls_all_sessions_connections':3072,
 'real_tls_session_connections':512,'real_tls_session_payload_bytes':64*1024**2,
 'requests_private_capability_tasks':['psf__requests-1724'],
 'requests_private_grader_cap_add':['NET_BIND_SERVICE'],
 'requests_extra_hosts':{'httpbin.org':'127.0.0.1'},
 'real_tls_connections_per_session':512,'real_tls_payload_bytes_per_session':64*1024**2,
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
        return ','.join(map(str,manager_cpu_ids()))
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
            or sorted(os.sched_getaffinity(0)) != manager_cpu_ids()
            or resource.getrlimit(resource.RLIMIT_NOFILE)[0] < NOFILE):
        raise PermissionError('API manager resource limits differ from the reviewed scope')
    return {'uid': os.getuid(), 'cgroup': paths[0], 'limits': limits,
            'cpu_affinity': sorted(os.sched_getaffinity(0)), 'nofile': resource.getrlimit(resource.RLIMIT_NOFILE)[0]}

def _budget(active, cpu, memory, spool=0):
    workers = [r for r in active if r['spec']['role'] != 'auxiliary_coordinator']
    coexistence=coexistence_status()
    if (cpu==CONSTRAINTS['generation_pair_reserved_cpu'] and memory==CONSTRAINTS['generation_pair_reserved_memory_bytes']
        and sum(r['spec']['role']=='actor' for r in workers)>=coexistence['maximum_new_generation']):
        raise ResourceBusy('The draining predecessor limits new generation to eleven')
    used_cpu = MANAGER_CPUS + coexistence["reserved_old_cpu"] + sum(r['reserved_cpu'] for r in workers)
    # Two fixed host scorer subprocesses share grader cores, but not its memory cap.
    used_memory = API_MEMORY_BYTES + 8*GIB + coexistence["reserved_old_memory_bytes"] + sum(r['reserved_memory_bytes'] for r in workers)
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
        COORDINATOR_RUN_ROOT=COORDINATOR_ROOT, AUTHORIZATION_FILE=AUTH_FILE,
        CONSTRAINTS=CONSTRAINTS, __file__=__file__)
    def allowed(operation='v066.run', **identity):
        value = guard(operation, **identity)
        return {**value, 'plan': reference(PLAN_FILE), 'sources': value['source_index'],
                'constraints': CONSTRAINTS}
    namespace.update(require_v066_allowed=allowed, host_cpu_pool=host_cpu_pool,
                     cpu_set=cpu_set, _budget=_budget)
    original_claim = namespace['claim_resource']
    def claim_resource(key, *, lane=None):
        resources=load(reference(PLAN_FILE))['resources']
        if key not in resources:
            raise PermissionError('Resource is outside the fresh pilot')
        if resources[key]['role']=='actor':
            coexistence=coexistence_status()
            blocked=set(coexistence['reserved_old_lanes'])
            if lane is not None and lane in blocked:
                raise ResourceBusy('A draining predecessor owns this original CPU lane')
            if lane is None:
                lane=next((i for i in range(MAX_GENERATIONS) if i not in blocked
                    and not (BATCH_ROOT/'resource-claims'/f'active-actor-{i}.json').exists()),None)
                if lane is None:raise ResourceBusy('Every non-overlapping actor lane is occupied')
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
        value = {'version': VERSION, 'key': 'v168-api-coordinator',
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
    old=original_scope.validate_plan(load(reference(original_scope.PLAN_FILE)))
    original={r['slot_id']:r for r in old['rows']}
    if (plan.get('version')!=VERSION or plan.get('original_plan')!=reference(original_scope.PLAN_FILE)
        or plan.get('panel')!=reference(PANEL_FILE) or plan.get('constraints')!=CONSTRAINTS
        or plan.get('original_ledger')!=str(LEDGER_FILE)):
        raise PermissionError('Never-called recovery lost original frozen panel or same500-yuan ledger')
    allowed=plan.get('admitted_original_slots',[]);used=plan.get('used_original_slots',[])
    expected=[r for r in old['rows'] if r['wave']==2]
    if len(expected)!=36 or plan.get('rows')!=expected:
        raise PermissionError('Only the unchanged original36 second-wave rows are admitted')
    if (not allowed or len(set(allowed))!=len(allowed) or set(allowed)&set(used)
        or set(allowed)|set(used)!=set(original) or [r['slot_id'] for r in plan['rows']]!=allowed):
        raise PermissionError('Original72 identities must split into used preserved and never-called admitted')
    for row in plan['rows']:
        if row!=original[row['slot_id']]:raise PermissionError('Recovery changed original task/config/seed/condition')
        validate_plan_identity(row)
    n=len(allowed)
    if dict(Counter(v['role'] for v in plan['resources'].values()))!={'actor':n,'controller':n,'volume':n,'score':n,'delivery_score':n}:
        raise PermissionError('Only declared unused generation and its two scoring endpoints are in this scope')
    return plan

def never_consumed(row):
    validate_plan_identity(row)
    return not any((BATCH_ROOT/'resource-claims'/f"{role}-{row['slot_index']}.json").exists()
                   for role in ('actor','controller','volume'))

def require_allowed(operation='v168.run', *, slot_id=None, instance_id=None, grading_only=False):
    operations={'v168.run','v168.api.run','v168.api.request','v168.prepare','v105.run'} | (set(original.OPERATIONS)-{'v066.model.start','v066.resolve','v066.control'})
    if os.getuid()==0 or os.geteuid()==0 or operation not in operations:
        raise PermissionError('Only the separately sealed ordinary-user recovery may execute')
    if grading_only and operation not in {'v168.run','v105.run','v066.run','v066.score','v066.delivery.score','v066.grader.create','v066.grader.start','v066.transport'}:
        raise PermissionError('Recovery grading cannot generate or create controls')
    if operation=='v066.transport' and instance_id!='psf__requests-1724':
        raise PermissionError('Only separately qualified1724 scoring may use the frozen bounded HTTP relay')
    auth=load(reference(AUTH_FILE))
    if (auth.get('version')!=VERSION or auth.get('status')!='approved'
        or auth.get('plan')!=reference(PLAN_FILE) or auth.get('source_index')!=reference(SOURCE_FILE)
        or auth.get('proposal')!=reference(PROPOSAL_FILE) or auth.get('user_grant')!=reference(USER_GRANT_FILE)
        or auth.get('API_cash_cap_CNY')!='500.00' or auth.get('constraints')!=CONSTRAINTS
        or auth.get('shared_host_configuration_changes')!=0
        or auth.get('original_ledger')!=str(LEDGER_FILE) or auth.get('new_cash_budget_CNY')!='0.00'):
        raise PermissionError('The existing500 cap, unused rows or isolated recovery scope changed')
    gate=load(auth['gate'])
    if gate.get('passed') is not True or gate.get('advance_to_wave_2') is not True:
        raise PermissionError('Actual first-wave measurement gate has not passed')
    for ref in load(auth['source_index'])['files']:checked(ref)
    plan=validate_plan(load(reference(PLAN_FILE)))
    if slot_id is not None:
        rows=[r for r in plan['rows'] if r['slot_id']==slot_id]
        if len(rows)!=1 or instance_id not in (None,rows[0]['instance_id']):
            raise PermissionError('Used or foreign original identity cannot be resampled')
    elif instance_id is not None and instance_id not in {r['instance_id'] for r in plan['rows']}:
        raise PermissionError('Foreign recovery task')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.is_file() or LEASE_FILE.read_bytes()!=checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No live exact recovery API owner')
    return {**auth,'execution_alignment_version':'v157-review2-communication-pilot-alignment-r1'}

def require_grading_allowed(operation='v168.run',**identity):
    return require_allowed(operation,grading_only=True,**identity)



def coexistence_status():
    from types import FunctionType
    from . import software_benchmark_scope_v161 as previous_scope
    function=previous_scope.predecessor_quiescence_status
    namespace={**function.__globals__,
        'PREDECESSOR_ROOT':previous_scope.BATCH_ROOT,'PREDECESSOR_UNIT':previous_scope.API_UNIT}
    check=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    value=check()
    if not value['passed']:
        raise ResourceBusy('Wait for exact predecessor generation, grading and cleanup completion')
    return {**value,'maximum_new_generation':16,'reserved_old_cpu':0,
        'reserved_old_memory_bytes':0,'active_old_slots':[], 'old_fully_quiescent':True,
        'recovery_predecessor_root':str(previous_scope.BATCH_ROOT)}


def reconcile_generation_limit():
    return coexistence_status()


def manager_cpu_ids():
    return host_cpu_pool()[:8]
