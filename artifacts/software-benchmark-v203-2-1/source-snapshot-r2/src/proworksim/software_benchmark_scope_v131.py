"""Exact new five-group scope; only owned objects after a concrete runtime grant."""
from __future__ import annotations

from collections import Counter
import fcntl
import os
from pathlib import Path
import resource
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_alignment_contract_v131 import GROUP_IDS, validate_plan_identity

ROOT = original.ROOT
VERSION = 'v131-five-fixed-organizations-scope-r1'
BATCH_ROOT = ROOT/'runs/software-benchmark-v131/fixed-organization-50-r1'
ARTIFACT_ROOT = ROOT/'artifacts/software-benchmark-v131'
API_ROOT = BATCH_ROOT/'api-coordinator'
COORDINATOR_ROOT = BATCH_ROOT/'grading-coordinator'
GRADING_ROOT = BATCH_ROOT/'grading'
PLAN_FILE = BATCH_ROOT/'execution-plan.json'
INVENTORY_FILE = BATCH_ROOT/'inventory.json'
SOURCE_FILE = BATCH_ROOT/'runtime-sources.json'
CPU_POOL_FILE = BATCH_ROOT/'host-cpu-pool.json'
AUTH_FILE = ROOT/'config/v131-fixed-organization-authorization.json'
PROPOSAL_FILE = ARTIFACT_ROOT/'runtime-authorization-r1/proposal.json'
USER_GRANT_FILE = ROOT/'config/v131-fixed-organization-user-grant.json'
NETWORK_RESOLUTION_FILE = BATCH_ROOT/'network-resolution.json'
CA_PROFILE_FILE = ROOT/'runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json'
PREPARATION_QUALIFICATION_FILE = API_ROOT/'preparation-qualification.json'
PANEL_FILE = ARTIFACT_ROOT/'preparation-r1/panel.json'
SOURCE_PANEL_FILE = ROOT/'artifacts/software-benchmark-v118/preparation-r1/panel.json'
SOURCE_PLAN_FILE = ROOT/'runs/software-benchmark-v118/project-repaired-r1/execution-plan-v119.json'
LEDGER_FILES = {group: BATCH_ROOT/'ledgers'/(group+'.sqlite') for group in GROUP_IDS}
BUDGET_BASELINE_FILE = BATCH_ROOT/'cash-before.json'
CASH_MODE = 'five_independent_new_CNY100_ledgers_no_transfer'
CASH_CAP_CNY, GROUP_CASH_CAP_CNY = '500.00', '100.00'
API_UNIT = 'proworksim-v131-fixed-organizations.service'
CLAIM_FILE = API_ROOT/'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT/'resource-claims/active-v131-coordinator.json'
GIB = 1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*GIB, 24*GIB
MAX_GENERATIONS, MAX_GRADERS, MANAGER_CPUS, NOFILE = 48, 2, 8, 16384
MAX_STARTUPS = 8
CONTAINER_PARENT = "proworksimv131api.slice"
FIRST_PHYSICAL_INDEX, LAST_PHYSICAL_INDEX, DIAGNOSTIC_INDEX = 9000, 9249, 1
ResourceBusy = original.ResourceBusy
CONSTRAINTS = {**original.CONSTRAINTS,
    'fresh_generation_slots': 250, 'generation_token_upper_bound': 1_250_000_000,
    'api_generation_token_upper_bound': 1_250_000_000, 'api_total_budget_cny': CASH_CAP_CNY,
    'api_budget_by_group_CNY': {g: GROUP_CASH_CAP_CNY for g in GROUP_IDS},
    'cash_budget_scope': CASH_MODE, 'old_ledgers_untouched': True,
    'maximum_actor_containers': 251, 'maximum_controller_containers': 251,
    'maximum_control_containers': 4, 'maximum_code_score_containers': 250,
    'maximum_delivery_score_containers': 250, 'maximum_score_containers': 500,
    'maximum_containers': 1006, 'maximum_named_volumes': 251,
    'zero_model_diagnostic_pairs': 1, 'initial_zero_model_diagnostic_pairs': 1,
    'conditional_zero_model_repair_pairs': 0, 'maximum_model_residents': 0,
    'neutral_model_preparation_calls': 0, 'neutral_model_preparation_total_tokens': 0,
    'api_neutral_preparation_calls': 0, 'api_neutral_preparation_total_tokens': 0,
    'free_api_metadata_requests': 0, 'new_owned_user_units': [API_UNIT],
    'maximum_combined_reserved_cpu': 152, 'maximum_combined_reserved_memory_bytes': 864*GIB,
    'aggregate_parent_cpu_cores':144,'aggregate_parent_memory_bytes':832*GIB,
    'aggregate_parent_memory_high_bytes':768*GIB,'aggregate_parent':CONTAINER_PARENT,
    'maximum_concurrent_startups':MAX_STARTUPS,
    'coordinator_memory_bytes': API_MEMORY_BYTES, 'coordinator_cpu_quota_percent': 800,
    'active_actor_limit': MAX_GENERATIONS, 'active_controller_limit': MAX_GENERATIONS,
    'active_grader_limit': MAX_GRADERS, 'maximum_active_generation_episodes': MAX_GENERATIONS,
    'generation_pair_reserved_cpu': 6, 'generation_pair_reserved_memory_bytes': 32*GIB,
    'actor_cpu': 4, 'actor_memory_bytes': 16*GIB, 'controller_cpu': 2, 'controller_memory_bytes': 16*GIB,
    'grader_cpu': 4, 'grader_memory_bytes': 16*GIB,
    'maximum_active_containers': 98, 'memory_minimum_free_bytes': 64*GIB,
    'disk_minimum_free_bytes': 128*GIB, 'maximum_real_tls_sessions': 24,
    'real_tls_all_sessions_payload_bytes': 1536*1024**2,
    'system_parent_slice_created': True, 'aggregate_memory_limit_kind': 'new_owned_parent_hard_cap_plus_bounded_manager',
    'physical_gpus': [], 'new_model_calls_for_preparation': 0,
    'host_namespaces_or_mount_configuration_changed': False, 'automatic_replay': False,
}


def load(ref):
    return original._cached_json(ref)

def retain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if load(reference(path)) != value:
            raise ValueError('Prepared v131 identity changed: '+str(path))
        return reference(path)
    return write_new(path, value)

def host_cpu_pool():
    value = load(reference(CPU_POOL_FILE))
    pool = value['cpu_ids']
    if (value.get('uid') != os.getuid() or len(pool) < 160 or len(pool) != len(set(pool))
            or any(type(cpu) is not int or cpu < 0 for cpu in pool)):
        raise ValueError('The frozen available CPU inventory changed')
    return pool

def cpu_set(role, index=0):
    if type(index) is not int or index < 0:
        raise ValueError('A nonnegative fixed lane is required')
    if role == 'coordinator' and index == 0:
        start, stop = 0, 8
    elif role in {'actor', 'controller'} and index < MAX_GENERATIONS:
        start, stop = 8, 152  # Shared worker CPU set; the parent enforces total144 cores.
    elif role == 'grader' and index < MAX_GRADERS:
        start, stop = 152+4*index, 156+4*index
    else:
        raise ValueError('Resource is outside the API-only v131 CPU lanes')
    return ','.join(map(str, host_cpu_pool()[start:stop]))

def verify_host_limits(role='api'):
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if role != 'api' or len(paths) != 1 or Path(paths[0]).name != API_UNIT:
        raise PermissionError('Use the separately bounded v131 ordinary-user service')
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
    # Individual hard caps may overlap. The separately authorized kernel parent
    # is the aggregate safety boundary; actual pressure controls new admission.
    from .software_benchmark_api_parent_v131 import pressure_probe
    parent = pressure_probe()
    graders = sum(row['spec']['role'] in {'score','delivery_score','control'} for row in active)
    if cpu == 4 and memory == 16*GIB and spool == 0 and graders >= MAX_GRADERS:
        raise ResourceBusy('Both asynchronously bounded grading lanes are occupied')
    physical = dispatch_view().physical_capacity()
    if os.getloadavg()[0] > len(host_cpu_pool())-16:
        raise ResourceBusy('Keep overall shared-host CPU headroom before new admission')
    spool_total = spool+sum(row.get('reserved_spool_bytes',0) for row in active)
    if (parent['current_bytes']+memory > parent['high_bytes']
            or physical['memory_available_bytes'] < CONSTRAINTS['memory_minimum_free_bytes']+memory
            or physical['disk_free_bytes'] < CONSTRAINTS['disk_minimum_free_bytes']+spool_total):
        raise ResourceBusy('Actual parent or shared-host pressure prevents new admission')
    return {'individual_cpu_caps_sum_after': cpu+sum(r['reserved_cpu'] for r in active),
        'individual_memory_caps_sum_after': memory+sum(r['reserved_memory_bytes'] for r in active),
        'aggregate_CPU_hard_cap_cores':144,'aggregate_memory_hard_cap_bytes':832*GIB,
        'aggregate_parent_pressure':parent,'individual_caps_are_not_additive_reservations':True,
        'reserved_payload_spool_bytes_after':spool_total,'physical_at_admission':physical,
        'spool_is_filesystem_quota':False}


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
                     cpu_set=cpu_set, _budget=_budget)
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
        value = {'version': VERSION, 'key': 'v131-api-coordinator',
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
    rows = plan.get('rows', [])
    source = load(reference(SOURCE_PANEL_FILE))
    if (plan.get('version') != VERSION or plan.get('root') != str(BATCH_ROOT)
            or plan.get('panel') != reference(PANEL_FILE) or plan.get('constraints') != CONSTRAINTS
            or plan.get('host_cpu_pool') != reference(CPU_POOL_FILE)
            or len(rows) != 250 or len({r['slot_id'] for r in rows}) != 250
            or {r['slot_index'] for r in rows} != set(range(9000,9250))
            or set(plan.get('environments', {})) != set(source['task_ids'])):
        raise PermissionError('The exact original50 by five-group inventory changed')
    expected = {'actor':251,'controller':251,'volume':251,'score':250,'delivery_score':250,'control':4}
    if plan.get('resource_role_counts') != expected or dict(Counter(v['role'] for v in plan['resources'].values())) != expected:
        raise PermissionError('The new bounded object identity inventory changed')
    for group in GROUP_IDS:
        chosen = [r for r in rows if r.get('organization_id') == group]
        if len(chosen) != 50 or {r['instance_id'] for r in chosen} != set(source['task_ids']):
            raise PermissionError('Every organization must retain the same complete 50 tasks')
    for row in rows:
        validate_plan_identity(row)
        if (row.get('model_key') != 'DEEPSEEK' or row.get('thinking') is not False
                or row.get('input_plus_output_tokens') != 5_000_000):
            raise PermissionError('Only one shared5M nonthinking team allowance is admitted')
    diagnostics = plan.get('diagnostics', [])
    if (len(diagnostics) != 1 or diagnostics[0].get('index') != 1
            or diagnostics[0].get('organization_id') != 'CHIEF'
            or diagnostics[0].get('instance_id') != 'psf__requests-2931'
            or diagnostics[0].get('model_calls') != 0):
        raise PermissionError('Only one common four-member zero-model diagnostic pair is allowed')
    return plan


def require_allowed(operation='v131.run', *, slot_id=None, instance_id=None, grading_only=False):
    allowed = {'v131.run','v131.api.run','v131.api.request','v131.prepare'} | (set(original.OPERATIONS)-{'v066.model.start'})
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in allowed:
        raise PermissionError('Only the new ordinary-user fixed-organization scope is admitted')
    if grading_only and operation not in {'v131.run','v066.run','v066.score','v066.delivery.score','v066.control',
            'v066.grader.create','v066.grader.start','v066.transport','v066.resolve'}:
        raise PermissionError('Grading cannot start generation or call the model')
    if not AUTH_FILE.is_file():
        raise PermissionError('Concrete v131 Docker and runtime authorization is not sealed')
    from .software_benchmark_alignment_contract_v131 import VERSION as ALIGNMENT_VERSION
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('execution_alignment_version') != ALIGNMENT_VERSION
            or auth.get('plan') != reference(PLAN_FILE) or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('proposal') != reference(PROPOSAL_FILE)
            or auth.get('API_cash_cap_by_group_CNY') != {g:GROUP_CASH_CAP_CNY for g in GROUP_IDS}
            or auth.get('ledger_paths') != {g:str(p) for g,p in LEDGER_FILES.items()}
            or auth.get('constraints') != CONSTRAINTS or auth.get('shared_host_configuration_changes') != 0):
        raise PermissionError('The exact five budgets, fresh plan or owned-object authority differs')
    grant = load(auth['user_grant'])
    if grant.get('status') != 'approved' or grant.get('proposal') != reference(PROPOSAL_FILE):
        raise PermissionError('The concrete new runtime scope needs its explicit user grant')
    for item in load(auth['source_index'])['files']:
        checked(item)
    plan = validate_plan(load(auth['plan']))
    if slot_id is not None:
        matched = [r for r in plan['rows'] if r['slot_id'] == slot_id]
        if len(matched) != 1 or instance_id not in (None,matched[0]['instance_id']):
            raise PermissionError('Request is outside the frozen250 team attempts')
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Task is outside the original50 panel')
    if operation in {'v066.transport','v066.resolve'} and instance_id not in original.TLS_TASKS:
        raise PermissionError('Scoring egress is limited to the two declared TLS tasks')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.is_file() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('There is no live exact v131 API owner')
    return auth


def require_grading_allowed(operation='v131.run', **identity):
    return require_allowed(operation, grading_only=True, **identity)
