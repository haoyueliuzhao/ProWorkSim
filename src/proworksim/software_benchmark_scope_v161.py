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
from .software_benchmark_alignment_contract_v161 import GROUP_IDS, validate_plan_identity

ROOT = original.ROOT
VERSION = 'v161-independent-technical-recovery-scope-r1'
BATCH_ROOT = ROOT/'runs/software-benchmark-v161/independent-technical-recovery-r1'
STATE_ROOT = BATCH_ROOT
ARTIFACT_ROOT = ROOT/'artifacts/software-benchmark-v161'
API_ROOT = STATE_ROOT/'api-coordinator'
COORDINATOR_ROOT = STATE_ROOT/'grading-coordinator'
GRADING_ROOT = STATE_ROOT/'grading'
PLAN_FILE = STATE_ROOT/'execution-plan.json'
INVENTORY_FILE = STATE_ROOT/'inventory.json'
SOURCE_FILE = STATE_ROOT/'runtime-sources-r2.json'
RECOVERY_AUTHORITY_FILE=ROOT/'config/v161-independent-technical-recovery-authority.json'
RECOVERY_PROPOSAL_FILE=ARTIFACT_ROOT/'final-independent-recovery-plan-r1/proposal.json'
PREDECESSOR_ROOT=ROOT/'runs/software-benchmark-v159/communication-pilot-recovery-r1'
PREDECESSOR_UNIT='proworksim-v159-communication-recovery.service'
CPU_POOL_FILE = original_scope.CPU_POOL_FILE
AUTH_FILE = ROOT/'config/v161-communication-technical-recovery-authorization.json'
PROPOSAL_FILE = ARTIFACT_ROOT/'runtime-authorization-r2/proposal.json'
USER_GRANT_FILE = ROOT/'config/v161-communication-technical-recovery-user-grant.json'
STANDING_POLICY_FILE = ROOT/'config/v143-standing-docker-user-policy.json'
STANDING_PERMISSION_FILE = STANDING_POLICY_FILE
PANEL_FILE = ROOT/'artifacts/software-benchmark-v156/communication-design-r1/approved-panel.json'
SOURCE_PLAN_FILE = ROOT/'runs/software-benchmark-v066/v064-continuation-r3/plan.json'
LEDGER_FILE = original_scope.LEDGER_FILE
LEDGER_FILES = {group:LEDGER_FILE for group in GROUP_IDS}
BUDGET_BASELINE_FILE = original_scope.BUDGET_BASELINE_FILE
PREPARATION_QUALIFICATION_FILE = API_ROOT/'preparation-qualification-r2.json'
CASH_MODE = 'same_v157_CNY500_ledger_explicit_independent_technical_attempts_only'
CASH_CAP_CNY = '500.00'
API_UNIT = 'proworksim-v161-communication-technical-recovery.service'
CLAIM_FILE = API_ROOT/'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT/'resource-claims/active-v161-coordinator.json'
GIB=1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*GIB,30*GIB
MAX_GENERATIONS,MAX_GRADERS,MANAGER_CPUS,NOFILE = 16,2,8,16384
MAX_STARTUPS=4
CONTAINER_PARENT=None
FIRST_PHYSICAL_INDEX,LAST_PHYSICAL_INDEX,DIAGNOSTIC_INDEX=16100,16113,None
ResourceBusy=original.ResourceBusy
CONSTRAINTS={**previous.CONSTRAINTS,
 'fresh_generation_slots':14,'generation_token_upper_bound':70_000_000,
 'api_generation_token_upper_bound':70_000_000,'api_total_budget_cny':CASH_CAP_CNY,
 'api_budget_shared_across_groups':True,'cash_budget_scope':CASH_MODE,'old_ledgers_untouched':False,'existing_v157_ledger_continued':True,'unrelated_older_ledgers_untouched':True,
 'maximum_actor_containers':14,'maximum_controller_containers':14,
 'maximum_control_containers':0,'maximum_code_score_containers':14,
 'maximum_delivery_score_containers':14,'maximum_score_containers':28,
 'maximum_containers':56,'maximum_named_volumes':14,
 'zero_model_diagnostic_pairs':0,'initial_zero_model_diagnostic_pairs':0,
 'conditional_zero_model_repair_pairs':0,'new_owned_user_units':[API_UNIT,'proworksim-v161-technical-recovery-waiter.service'],
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
 'real_tls_session_connections':512,'real_tls_session_payload_bytes':64*1024**2,
 'requests_private_capability_tasks':[],
 'requests_private_grader_cap_add':[],
 'requests_extra_hosts':{},
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
    if not predecessor_quiescence_status()['passed']:
        raise ResourceBusy('Independent recovery must wait for predecessor cleanup')
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
        value = {'version': VERSION, 'key': 'v161-api-coordinator',
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
    from .software_benchmark_alignment_contract_v161 import RECOVERY_IDENTITIES
    proof=load(reference(RECOVERY_PROPOSAL_FILE))
    old=original_scope.validate_plan(load(reference(original_scope.PLAN_FILE)))
    original_rows={r['slot_id']:r for r in old['rows']}
    attempts=proof['attempts']
    if (plan.get('version')!=VERSION or plan.get('original_plan')!=reference(original_scope.PLAN_FILE)
        or plan.get('panel')!=reference(PANEL_FILE) or plan.get('constraints')!=CONSTRAINTS
        or plan.get('recovery_proposal')!=reference(RECOVERY_PROPOSAL_FILE)
        or plan.get('original_ledger')!=str(LEDGER_FILE) or len(plan.get('rows',[]))!=14
        or plan.get('diagnostics')!=[] or plan.get('training') is not False):
        raise PermissionError('Independent recovery lost exact14 identities, original condition or500-CNY ledger')
    expected_resources={}
    for item,row,mapping in zip(attempts,plan['rows'],RECOVERY_IDENTITIES,strict=True):
        expected=copy.deepcopy(original_rows[item['original_slot_id']])
        expected.update(slot_id=item['recovery_slot_id'],slot_index=item['slot_index'],configuration=item['configuration'])
        if row!=expected or any(item[k]!=v for k,v in mapping.items()):
            raise PermissionError('Recovery may only rename exact failed technical attempts and physical identities')
        before=load(item['original_configuration']);after=load(item['configuration'])
        before={**before,'slot_id':item['recovery_slot_id'],'slot_index':item['slot_index']}
        if before!=after:raise PermissionError('Fresh initial model configuration differs beyond independent identity')
        validate_plan_identity(row)
        if row['wave']!=1 or row['instance_id']=='psf__requests-1724':
            raise PermissionError('This recovery is one wave and needs no scoring network')
        for role in ('actor','controller','volume','score','delivery-score'):
            spec=copy.deepcopy(old['resources'][f"{role}-{item['original_slot_index']}"])
            spec['slot_id']=row['slot_id'];expected_resources[f"{role}-{row['slot_index']}"]=spec
    if plan.get('resources')!=expected_resources:
        raise PermissionError('Only declared14 fresh pairs,14volumes and28score endpoints may exist')
    if set(plan['environments'])!={r['instance_id'] for r in plan['rows']}:
        raise PermissionError('No foreign environment is needed for these five tasks')
    return plan

def never_consumed(row):
    validate_plan_identity(row)
    return not any((BATCH_ROOT/'resource-claims'/f"{role}-{row['slot_index']}.json").exists()
                   for role in ('actor','controller','volume'))

def require_allowed(operation='v161.run', *, slot_id=None, instance_id=None, grading_only=False):
    operations={'v161.run','v161.api.run','v161.api.request','v161.prepare','v161.register_attempts','v161.wait','v105.run'} | (set(original.OPERATIONS)-{'v066.model.start','v066.resolve','v066.control'})
    if os.getuid()==0 or os.geteuid()==0 or operation not in operations:
        raise PermissionError('Only the separately sealed ordinary-user recovery may execute')
    if grading_only and operation not in {'v161.run','v105.run','v066.run','v066.score','v066.delivery.score','v066.grader.create','v066.grader.start','v066.transport'}:
        raise PermissionError('Recovery grading cannot generate or create controls')
    if operation=='v066.transport':
        raise PermissionError('Independent recovery has no scoring egress authority')
    auth=load(reference(AUTH_FILE))
    if (auth.get('version')!=VERSION or auth.get('status')!='approved'
        or auth.get('plan')!=reference(PLAN_FILE) or auth.get('source_index')!=reference(SOURCE_FILE)
        or auth.get('proposal')!=reference(PROPOSAL_FILE) or auth.get('user_grant')!=reference(USER_GRANT_FILE)
        or auth.get('API_cash_cap_CNY')!='500.00' or auth.get('constraints')!=CONSTRAINTS
        or auth.get('shared_host_configuration_changes')!=0
        or auth.get('original_ledger')!=str(LEDGER_FILE) or auth.get('new_cash_budget_CNY')!='0.00'
        or auth.get('recovery_authority')!=reference(RECOVERY_AUTHORITY_FILE)):
        raise PermissionError('The existing500 cap, unused rows or isolated recovery scope changed')
    gate=load(auth['gate'])
    if gate.get('passed') is not True:raise PermissionError('Recovery engineering gate has not passed')
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

def require_grading_allowed(operation='v161.run',**identity):
    return require_allowed(operation,grading_only=True,**identity)


def predecessor_quiescence_status():
    """Read exact owned cleanup receipts and leases; never changes predecessor state."""
    import json,subprocess
    from .software_benchmark_ref_resident_v066 import user_manager_environment
    folder=PREDECESSOR_ROOT/'resource-claims'
    leases=sorted(str(p) for p in folder.glob('active-*.json'))
    pending=[];verified=[]
    plan_path=PREDECESSOR_ROOT/'execution-plan.json'
    if not plan_path.is_file():
        return {'passed':False,'v159_all_owned_objects_removed':False,'lease_empty':not leases,
                'reason':'predecessor_plan_missing','active_leases':leases}
    plan=load(reference(plan_path))
    for key in plan['resources']:
        claim=folder/(key+'.json')
        if not claim.exists():continue
        release=folder/(key+'.released.json')
        if not release.exists():pending.append(key);continue
        value=load(reference(release))
        if value.get('claim')!=reference(claim) or value.get('quiescent') is not True:
            raise PermissionError('Predecessor release lost exact ownership identity')
        verified.append(reference(release))
    for row in plan['rows']:
        if not (folder/f"actor-{row['slot_index']}.json").exists():continue
        quiet=PREDECESSOR_ROOT/'episodes'/str(row['slot_index'])/'quiescence.json'
        if not quiet.exists():pending.append('pair_quiet:'+row['slot_id']);continue
        value=load(reference(quiet))
        if (value.get('quiescent') is not True or value.get('cleanup_errors')!=[]
            or value.get('create_result_unknown') is not False or value.get('all_owned_objects_removed') is not True):
            pending.append('pair_not_removed:'+row['slot_id'])
    final=PREDECESSOR_ROOT/'api-coordinator/coordinator-finalization.json'
    finalized=False
    if final.exists():
        value=load(reference(final));release=value.get('coordinator_release')
        finalized=value.get('cleanup_errors')==[] and isinstance(release,dict) and load(release).get('released') is True
    observed=subprocess.run(['systemctl','--user','show',PREDECESSOR_UNIT,'--no-pager',
        '--property=ActiveState,SubState,MainPID'],env=user_manager_environment(),capture_output=True,text=True,timeout=20)
    state=dict(line.split('=',1) for line in observed.stdout.splitlines() if '=' in line)
    inactive=observed.returncode==0 and state.get('ActiveState') in {'inactive','failed'} and state.get('MainPID')=='0'
    passed=not leases and not pending and finalized and inactive
    return {'version':'v161-predecessor-cleanup-r1','passed':passed,
        'v159_all_owned_objects_removed':not pending and finalized,'lease_empty':not leases,
        'active_leases':leases,'pending_cleanup':pending,'coordinator_finalized':finalized,
        'predecessor_service_inactive':inactive,'service_state':state,'released_resource_count':len(verified),
        'predecessor_plan':reference(plan_path),'predecessor_files_processes_or_objects_changed':False}

def reconcile_generation_limit():
    value=predecessor_quiescence_status()
    if not value['passed']:raise ResourceBusy('Predecessor cleanup is not complete')
    return value

def manager_cpu_ids():
    return host_cpu_pool()[:8]
