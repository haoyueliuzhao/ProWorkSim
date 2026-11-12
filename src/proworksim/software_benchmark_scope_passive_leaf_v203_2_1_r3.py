"""Fresh physical deployment of the same twelve unused model attempts; same150 ledger."""
from __future__ import annotations

from collections import Counter
import fcntl
import os
from pathlib import Path
import resource
import inspect
import json
import sqlite3
import shutil
from functools import lru_cache
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_scope_v203_2_1_r2 as parent
from . import software_benchmark_scope_passive_requests_v203_2_1_r3 as ca_scope
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_alignment_contract_v203_2_1 import GROUP_IDS, validate_plan_identity

ROOT = original.ROOT
VERSION = 'v203.2.1-original-Requests-first-model-leaf-scope-r3'
TASK = 'psf__requests-2317'
QUALIFIED_R3_FILE = ca_scope.COORDINATOR_ROOT/'qualifications'/(TASK+'.json')
CA_RESULT_FILE = ca_scope.BATCH_ROOT/'result.json'
PARENT_GATE_FILE = parent.API_ROOT/'engineering-gate.json'
PREVIOUS_BATCH_ROOT = ROOT/'runs/software-benchmark-v203-2-1/passive-pilot12-r1'
BATCH_ROOT = ROOT/'runs/software-benchmark-v203-2-1/passive-requests-leaf-r3'
ARTIFACT_ROOT = ROOT/'artifacts/software-benchmark-v203-2-1'
API_ROOT = BATCH_ROOT/'api-coordinator'
COORDINATOR_ROOT = BATCH_ROOT/'grading-coordinator'
GRADING_ROOT = BATCH_ROOT/'grading'
PLAN_FILE = BATCH_ROOT/'execution-plan.json'
INVENTORY_FILE = BATCH_ROOT/'inventory.json'
SOURCE_FILE = BATCH_ROOT/'runtime-sources.json'
CPU_POOL_FILE = BATCH_ROOT/'host-cpu-pool.json'
AUTH_FILE = ARTIFACT_ROOT/'requests-leaf-r3/authorization/authorization.json'
PROPOSAL_FILE = ARTIFACT_ROOT/'requests-leaf-r3/authorization/proposal.json'
USER_GRANT_FILE = ARTIFACT_ROOT/'requests-leaf-r3/authorization/user-authority.json'
NETWORK_RESOLUTION_FILE = BATCH_ROOT/'network-resolution.json'
CA_PROFILE_FILE = ROOT/'runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json'
PREPARATION_QUALIFICATION_FILE = API_ROOT/'preparation-qualification.json'
PANEL_FILE = ARTIFACT_ROOT/'requests-leaf-r3/panel.json'
SOURCE_PANEL_FILE = ROOT/'artifacts/software-benchmark-v203-2/pilot-preparation-r1/plan.json'
SOURCE_PLAN_FILE = ROOT/'runs/software-benchmark-v066/v064-continuation-r3/plan.json'
LEDGER_FILE = PREVIOUS_BATCH_ROOT/'ledgers/pilot.sqlite'
LEDGER_FILES = {group: LEDGER_FILE for group in GROUP_IDS}
STATE_ROOT = BATCH_ROOT
BUDGET_BASELINE_FILE = PREVIOUS_BATCH_ROOT/'cash-before.json'
CASH_MODE = 'one_new_CNY150_passive_pilot_ledger_attributed_by_member'
CASH_CAP_CNY = '150.00'
API_UNIT = 'proworksim-v203-2-1-requests-leaf.service'
CLAIM_FILE = API_ROOT/'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT/'resource-claims/active-requests-leaf-coordinator.json'
GIB = 1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 8*GIB, 7*GIB
MAX_GENERATIONS, MAX_GRADERS, MANAGER_CPUS, NOFILE = 1, 1, 4, 16384
MAX_HTTP_CONCURRENCY = 8
MAX_STARTUPS = 1
CONTAINER_PARENT = None
FIRST_PHYSICAL_INDEX, LAST_PHYSICAL_INDEX, DIAGNOSTIC_INDEX = 2032307, 2032307, None
ResourceBusy = original.ResourceBusy
CONSTRAINTS = {**original.CONSTRAINTS,
    'fresh_generation_slots': 12, 'generation_token_upper_bound': 60_000_000,
    'api_generation_token_upper_bound': 60_000_000, 'api_total_budget_cny': CASH_CAP_CNY,
    'api_budget_shared_across_groups': True,
    'cash_budget_scope': CASH_MODE, 'old_ledgers_untouched': True,
    'maximum_actor_containers': 12, 'maximum_controller_containers': 12,
    'maximum_control_containers': 4, 'maximum_code_score_containers': 12,
    'maximum_delivery_score_containers': 12, 'maximum_score_containers': 24,
    'maximum_containers': 52, 'maximum_named_volumes': 12,
    'zero_model_diagnostic_pairs': 0, 'initial_zero_model_diagnostic_pairs': 0,
    'conditional_zero_model_repair_pairs': 0, 'maximum_model_residents': 0,
    'neutral_model_preparation_calls': 0, 'neutral_model_preparation_total_tokens': 0,
    'api_neutral_preparation_calls': 0, 'api_neutral_preparation_total_tokens': 0,
    'free_api_metadata_requests': 0, 'new_owned_user_units': [API_UNIT],
    'maximum_combined_reserved_cpu': 64, 'maximum_combined_reserved_memory_bytes': 456*GIB,
    'host_grading_process_memory_bytes': 4*GIB, 'host_grading_cpu_shared_with_own_container': True,
    'maximum_concurrent_startups':MAX_STARTUPS,
    'coordinator_memory_bytes': API_MEMORY_BYTES, 'coordinator_cpu_quota_percent': 800,
    'active_actor_limit': MAX_GENERATIONS, 'active_controller_limit': MAX_GENERATIONS,
    'active_grader_limit': MAX_GRADERS, 'maximum_active_generation_episodes': MAX_GENERATIONS,
    'generation_pair_reserved_cpu': 6, 'generation_pair_reserved_memory_bytes': 48*GIB,
    'actor_cpu': 4, 'actor_memory_bytes': 16*GIB, 'controller_cpu': 2, 'controller_memory_bytes': 32*GIB,
    'grader_cpu': 4, 'grader_memory_bytes': 16*GIB,
    'maximum_active_containers': 18, 'memory_minimum_free_bytes': 64*GIB,
    'disk_minimum_free_bytes': 128*GIB, 'maximum_real_tls_sessions': 0,
    'real_tls_all_sessions_payload_bytes': 0,
    'real_tls_all_sessions_connections': 0, 'real_tls_session_connections': 512,
    'real_tls_session_payload_bytes': 64*1024**2,
    'system_parent_slice_created': False, 'aggregate_memory_limit_kind': 'sum_of_bounded_owned_objects',
    'physical_gpus': [], 'new_model_calls_for_preparation': 0,
    'host_namespaces_or_mount_configuration_changed': False, 'automatic_replay': False,
    'minimum_captured_cpu_pool': 64, 'requests_private_capability_tasks': ['psf__requests-2317'],
    'requests_private_grader_cap_add': ['NET_ADMIN','NET_BIND_SERVICE'],
    'requests_extra_hosts': {'httpbin.org':'127.0.0.1','www.google.co.uk':'127.0.0.1'},
    'engineering_gate_slot_indices': [2032200, 2032201], 'engineering_gate_included_in_formal_12': True,
    'cash_limit_mode': 'team_start_admission_only', 'finish_started_teams_above_cash_threshold': True,
    'same_existing_v203_2_1_150_CNY_ledger': True, 'additional_cash_CNY': '0.00',
    'new_logical_model_attempts': 0, 'zero_API_physical_redeployment': True,
}


CONSTRAINTS.update(fresh_generation_slots=1,generation_token_upper_bound=5_000_000,
 api_generation_token_upper_bound=5_000_000,maximum_actor_containers=1,maximum_controller_containers=1,
 maximum_control_containers=0,maximum_code_score_containers=1,maximum_delivery_score_containers=1,
 maximum_score_containers=2,maximum_containers=4,maximum_named_volumes=1,
 maximum_combined_reserved_cpu=6,maximum_combined_reserved_memory_bytes=56*GIB,
 maximum_active_containers=2,coordinator_cpu_quota_percent=400,coordinator_memory_bytes=8*GIB,
 engineering_gate_slot_indices=[2032200,2032201],engineering_gate_included_in_formal_12=True,
 leaf_original_logical_task_only=TASK,leaf_physical_index=2032307,parent_runtime_modified=False,
 parent_worst_case_cpu=64,parent_worst_case_memory_bytes=456*GIB,
 joint_cpu_upper_bound=70,joint_memory_upper_bound_bytes=512*GIB,
 joint_required_free_memory_bytes=576*GIB,joint_required_disk_free_bytes=164*GIB,
 generation_and_scoring_must_not_overlap=True,coordinator_shares_own_actor_CPU_lane=True)


def load(ref):
    return original._cached_json(ref)

def retain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if load(reference(path)) != value:
            raise ValueError('Prepared v203.2.1 identity changed: '+str(path))
        return reference(path)
    return write_new(path, value)

def host_cpu_pool():
    value = load(reference(CPU_POOL_FILE))
    pool = value['cpu_ids']
    if (value.get('uid') != os.getuid() or len(pool) < 70 or len(pool) != len(set(pool))
            or any(type(cpu) is not int or cpu < 0 for cpu in pool)):
        raise ValueError('The frozen available CPU inventory changed')
    return pool

def cpu_set(role,index=0):
    if index!=0 or role not in {'coordinator','actor','controller','grader'}:
        raise ValueError('Only one own leaf lane is permitted')
    pool=host_cpu_pool()
    selected=pool[68:70] if role=='controller' else pool[64:68]
    return ','.join(map(str,selected))


def physical_capacity():
    available=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
    free=shutil.disk_usage(ROOT).free;pool=host_cpu_pool()
    return {'memory_available_bytes':available,'disk_free_bytes':free,'CPU_pool_count':len(pool),
        'joint_cpu_upper_bound':70,'joint_memory_upper_bound_bytes':512*GIB,
        'required_free_memory_bytes':576*GIB,'required_disk_free_bytes':164*GIB,
        'passed':available>=576*GIB and free>=164*GIB and len(pool)>=70,
        'parent_runtime_state_modified':False}


def verify_host_limits(role='api'):
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if role != 'api' or len(paths) != 1 or Path(paths[0]).name != API_UNIT:
        raise PermissionError('Use the separately bounded v203.2.1 ordinary-user service')
    folder = Path('/sys/fs/cgroup')/paths[0].lstrip('/')
    limits = {key: (folder/key).read_text().strip()
              for key in ('memory.max', 'memory.high', 'memory.swap.max', 'pids.max')}
    if (limits != {'memory.max': str(API_MEMORY_BYTES), 'memory.high': str(API_MEMORY_HIGH_BYTES),
                   'memory.swap.max': '0', 'pids.max': '512'}
            or sorted(os.sched_getaffinity(0)) != host_cpu_pool()[64:68]
            or resource.getrlimit(resource.RLIMIT_NOFILE)[0] < NOFILE):
        raise PermissionError('API manager resource limits differ from the reviewed scope')
    return {'uid': os.getuid(), 'cgroup': paths[0], 'limits': limits,
            'cpu_affinity': sorted(os.sched_getaffinity(0)), 'nofile': resource.getrlimit(resource.RLIMIT_NOFILE)[0]}

def _budget(active,cpu,memory,spool=0):
    workers=[r for r in active if r['spec']['role']!='auxiliary_coordinator']
    if workers:raise ResourceBusy('The one leaf pair or scorer must clean before another enters')
    if (cpu,memory,spool) not in {(6,48*GIB,4*GIB),(4,16*GIB,0)}:
        raise PermissionError('Unexpected leaf resource envelope')
    capacity=physical_capacity()
    if not capacity['passed']:raise ResourceBusy('Parent plus leaf conservative headroom unavailable')
    return {'reserved_cpu_after':max(4,cpu),'reserved_memory_bytes_after':8*GIB+memory+(4*GIB if cpu==4 else 0),
        'reserved_payload_spool_bytes_after':spool,'physical_at_admission':capacity,
        'coordinator_CPU_shares_own_lane':True,'generation_scoring_overlap':False}


def dispatch_view(guard=None):
    guard = guard or require_allowed
    namespace = clone_namespace(original, VERSION=VERSION, BATCH_ROOT=BATCH_ROOT,
        PLAN_FILE=PLAN_FILE, RESUME_FILE=INVENTORY_FILE, SOURCE_INDEX_FILE=SOURCE_FILE,
        CPU_POOL_FILE=CPU_POOL_FILE, GRADING_ROOT=GRADING_ROOT,
        COORDINATOR_RUN_ROOT=COORDINATOR_ROOT, AUTHORIZATION_FILE=AUTH_FILE,
        CONSTRAINTS=CONSTRAINTS, __file__=__file__)
    def allowed(operation='v066.run', **identity):
        value = guard(operation, **identity)
        return {**value, 'plan': reference(PLAN_FILE), 'sources': reference(SOURCE_FILE),
                'constraints': CONSTRAINTS}
    namespace.update(require_v066_allowed=allowed, host_cpu_pool=host_cpu_pool,
                     cpu_set=cpu_set, _budget=_budget, physical_capacity=physical_capacity)
    # Allocate from this batch's atomic lanes; no old-owner lane inventory.
    source = inspect.getsource(original.claim_resource)
    for role in ('score', 'delivery_score', 'control'):
        source = source.replace('"'+role+'": ("grader", 4, 4, 16 * GIB)',
                                '"'+role+'": ("grader", 1, 4, 16 * GIB)')
    # Keep the actual provider's accepted prefix; batch path+resource key
    # in the native SHA-derived name makes every r2 object independently owned.
    exec(compile(source, __file__+':owned-lanes', 'exec'), namespace)
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
        value = {'version': VERSION, 'key': 'v203.2.1-api-coordinator',
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
    rows=plan.get('rows',[])
    parent_plan=parent.load(reference(parent.PLAN_FILE))
    original_row=next(r for r in parent_plan['rows'] if r['instance_id']==TASK)
    expected={'actor':1,'controller':1,'volume':1,'score':1,'delivery_score':1}
    if (plan.get('version')!=VERSION or plan.get('root')!=str(BATCH_ROOT) or len(rows)!=1
        or rows[0].get('slot_index')!=2032307 or plan.get('constraints')!=CONSTRAINTS
        or plan.get('parent_plan')!=reference(parent.PLAN_FILE) or set(plan.get('environments',{}))!={TASK}
        or plan.get('resource_role_counts')!=expected
        or dict(Counter(v['role'] for v in plan.get('resources',{}).values()))!=expected
        or plan.get('CA_qualification')!=reference(QUALIFIED_R3_FILE)):
        raise PermissionError('Only the original Requests first-model leaf and its exact bounds are allowed')
    row=rows[0];validate_plan_identity(row)
    if {k:v for k,v in row.items() if k not in {'configuration','slot_index'}}!={k:v for k,v in original_row.items() if k not in {'configuration','slot_index'}}:
        raise PermissionError('The original task, seed, logical identity or model policy changed')
    return plan


def never_consumed(row):
    validate_plan_identity(row)
    return not any((BATCH_ROOT/'resource-claims'/f"{role}-{row['slot_index']}.json").exists()
                   for role in ('actor', 'controller', 'volume'))


def require_allowed(operation='v203.2.1.run', *, slot_id=None, instance_id=None, grading_only=False):
    allowed = {'v203.2.1.run','v203.2.1.api.run','v203.2.1.api.request','v203.2.1.prepare'} | (set(original.OPERATIONS)-{'v066.model.start'})
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in allowed:
        raise PermissionError('Only the new ordinary-user role-pilot scope is admitted')
    if grading_only and operation not in {'v203.2.1.run','v066.run','v066.score','v066.delivery.score','v066.control',
            'v066.grader.create','v066.grader.start','v066.transport','v066.resolve'}:
        raise PermissionError('Grading cannot start generation or call the model')
    if not AUTH_FILE.is_file():
        raise PermissionError('Concrete v203.2.1 Docker and runtime authorization is not sealed')
    from .software_benchmark_alignment_contract_v203_2_1 import VERSION as ALIGNMENT_VERSION
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('execution_alignment_version') != ALIGNMENT_VERSION
            or auth.get('plan') != reference(PLAN_FILE) or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('proposal') != reference(PROPOSAL_FILE)
            or auth.get('API_cash_cap_CNY') != CASH_CAP_CNY
            or auth.get('cash_budget_scope') != CASH_MODE
            or auth.get('ledger_paths') != {g:str(p) for g,p in LEDGER_FILES.items()}
            or auth.get('constraints') != CONSTRAINTS or auth.get('shared_host_configuration_changes') != 0):
        raise PermissionError('The exact shared cash budget, fresh plan or owned-object authority differs')
    grant = load(auth['user_grant'])
    if grant.get('status') != 'approved' or grant.get('proposal') != reference(PROPOSAL_FILE):
        raise PermissionError('The concrete new runtime scope needs its explicit user grant')
    _verify_source_once(auth['source_index']['path'], auth['source_index']['sha256'], auth['source_index']['bytes'])
    plan = validate_plan(load(auth['plan']))
    if slot_id is not None:
        matched = [r for r in plan['rows'] if r['slot_id'] == slot_id]
        if len(matched) != 1 or instance_id not in (None,matched[0]['instance_id']):
            raise PermissionError('Request is outside the frozen twelve team attempts')
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Task is outside the selected twelve-task panel')
    if operation in {'v066.transport','v066.resolve'}:
        raise PermissionError('This selected pilot admits no external scoring egress')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.is_file() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('There is no live exact v203.2.1 API owner')
    if operation=='v066.run' or operation.startswith(('v066.actor','v066.controller','v066.volume')) or operation.endswith('request'):
        if not gate_status()['passed']:raise PermissionError('Parent engineering and verified CA gates must both pass')
    return auth


def require_grading_allowed(operation='v203.2.1.run', **identity):
    return require_allowed(operation, grading_only=True, **identity)


@lru_cache(maxsize=2)
def _verify_source_once(path, sha256, size):
    for item in load({'path':path,'sha256':sha256,'bytes':size})['files']:
        checked(item)
    return True


def qualified_r3_ref():return reference(QUALIFIED_R3_FILE)


def gate_status():
    value={'passed':False,'parent_engineering_passed':False,'CA_qualified':False,
           'parent_gate':None,'CA_qualification':None,'reason':'parent_engineering_pending'}
    if not PARENT_GATE_FILE.is_file():return value
    parent_ref=reference(PARENT_GATE_FILE);gate=load(parent_ref);value['parent_gate']=parent_ref
    if gate.get('passed') is not True:
        value['reason']='parent_engineering_failed';return value
    if (gate.get('predeclared_indices')!=[2032200,2032201] or gate.get('scores_used_for_gate') is not False
        or gate.get('shared_host_usage_complete') is not True):
        value['reason']='parent_engineering_witness_invalid';return value
    value['parent_engineering_passed']=True
    result=load(reference(CA_RESULT_FILE));qualification=qualified_r3_ref()
    if (result.get('qualification_passed') is not True or result.get('cleanup_proven') is not True
        or result.get('active_owned_claims')!=[] or result.get('qualification')!=qualification
        or result.get('returncodes')!=[0,0]):
        value['reason']='CA_qualification_incomplete';return value
    value.update(passed=True,CA_qualified=True,CA_qualification=qualification,reason='both_required_gates_passed')
    return value


def validate_first_model_admission(*,require_empty_admission=True):
    plan=validate_plan(load(reference(PLAN_FILE)));row=plan['rows'][0]
    if not gate_status()['passed']:raise PermissionError('Leaf cannot bypass the parent or CA gate')
    if not never_consumed(row):raise PermissionError('Leaf physical generation identity already consumed')
    for claim_path in (parent.BATCH_ROOT/'resource-claims').glob('active-*.json'):
        item=parent.load(reference(claim_path))
        if item.get('spec',{}).get('slot_id')==row['slot_id']:
            raise PermissionError('The original task has an active parent resource')
    with sqlite3.connect(LEDGER_FILE.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        own=db.execute('SELECT COUNT(*) FROM requests WHERE slot_id=?',(row['slot_id'],)).fetchone()[0]
        admission=db.execute('SELECT state FROM team_admissions WHERE slot_id=?',(row['slot_id'],)).fetchone()
        total=db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
    if own or (require_empty_admission and admission is not None):
        raise PermissionError('Only the never-called, unadmitted original task may enter this leaf')
    return {'slot_id':row['slot_id'],'own_provider_requests':own,'existing_other_requests':total,
            'own_admission_state':admission[0] if admission else None,'ledger_not_modified':True}
