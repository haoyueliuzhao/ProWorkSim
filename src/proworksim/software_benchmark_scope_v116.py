"""New aligned attempts under the original cumulative CNY350 money cap."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import resource
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace

ROOT = original.ROOT
VERSION = 'v116-installed-CA-path-recovery-scope-r1'
BATCH_ROOT = ROOT / 'runs/software-benchmark-v111/aligned-interface-r1'
API_ROOT = BATCH_ROOT / 'api-coordinator-v116'
COORDINATOR_ROOT = BATCH_ROOT / 'grading-coordinator-v116'
GRADING_ROOT = BATCH_ROOT / 'grading-v116'
PLAN_FILE = BATCH_ROOT / 'execution-plan-v116.json'
INVENTORY_FILE = BATCH_ROOT / 'inventory.json'
SOURCE_FILE = BATCH_ROOT / 'runtime-sources-v116.json'
CPU_POOL_FILE = BATCH_ROOT / 'host-cpu-pool.json'
AUTH_FILE = ROOT / 'config/v116-installed-CA-recovery-authorization.json'
INSTALLED_CA_RECOVERY_FILE = BATCH_ROOT / 'recovery-v116/requests-recovery-v116.json'
REQUESTS_RECOVERY_FILE = INSTALLED_CA_RECOVERY_FILE
PARENT_AUTH_FILE = ROOT / 'config/v115-tls-binding-recovery-authorization.json'
TLS_PRECREATION_RECOVERY_FILE = BATCH_ROOT / 'recovery-v114/precreation-recovery-v115.json'
NETWORK_RESOLUTION_FILE = BATCH_ROOT / 'recovery-v114/network-resolution.json'
CA_PROFILE_FILE = BATCH_ROOT / 'recovery-v116/ca-profile.json'
CONCURRENCY_AUTH_FILE = ROOT / 'config/v112-concurrency-amendment.json'
PREPARATION_RECOVERY_FILE = BATCH_ROOT / 'preparation-recovery-v113.json'
ORIGINAL_AUTH_FILE = ROOT / 'config/v111-aligned-interface-authorization.json'
PANEL_FILE = ROOT / 'artifacts/software-benchmark-v111/preparation-r1/panel.json'
LEDGER_FILE = ROOT / 'runs/software-benchmark-v105/nonthinking-interface-r1/api-ledger.sqlite'
BUDGET_BASELINE_FILE = BATCH_ROOT / 'recovery-v114/cash-before.json'
CASH_MODE = 'continue_original_v105_ledger_cumulative_CNY350'
API_UNIT = 'proworksim-v111-aligned.service'
CLAIM_FILE = API_ROOT / 'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT / 'resource-claims/active-v116-coordinator.json'
GIB = 1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*GIB, 24*GIB
MAX_GENERATIONS, MAX_GRADERS, MANAGER_CPUS, NOFILE = 4, 2, 8, 16384
CASH_CAP_CNY = '350.00'
FIRST_PHYSICAL_INDEX, LAST_PHYSICAL_INDEX = 7200, 7299
ResourceBusy = original.ResourceBusy

CONSTRAINTS = {**original.CONSTRAINTS,
    'fresh_generation_slots': 4, 'generation_token_upper_bound': 20_000_000,
    'api_generation_token_upper_bound': 20_000_000, 'api_total_budget_cny': CASH_CAP_CNY,
    'cash_budget_scope': CASH_MODE,
    'old_settled_and_uncertain_reservations_retained': True,
    'maximum_actor_containers': 4, 'maximum_controller_containers': 4,
    'maximum_control_containers': 4, 'maximum_code_score_containers': 4,
    'maximum_delivery_score_containers': 2, 'maximum_score_containers': 6,
    'maximum_containers': 18, 'maximum_named_volumes': 4,
    'zero_model_diagnostic_pairs': 0, 'initial_zero_model_diagnostic_pairs': 0,
    'conditional_zero_model_repair_pairs': 0, 'maximum_model_residents': 0,
    'neutral_model_preparation_calls': 0, 'neutral_model_preparation_total_tokens': 0,
    'api_neutral_preparation_calls': 0, 'api_neutral_preparation_total_tokens': 0,
    'free_api_metadata_requests': 0, 'new_owned_user_units': [API_UNIT],
    'maximum_combined_reserved_cpu': 40, 'maximum_combined_reserved_memory_bytes': 192*GIB,
    'coordinator_memory_bytes': API_MEMORY_BYTES, 'coordinator_cpu_quota_percent': 800,
    'active_actor_limit': MAX_GENERATIONS, 'active_controller_limit': MAX_GENERATIONS,
    'active_grader_limit': MAX_GRADERS, 'maximum_active_generation_episodes': MAX_GENERATIONS,
    'generation_pair_reserved_cpu': 6, 'generation_pair_reserved_memory_bytes': 32*GIB,
    'actor_cpu': 4, 'actor_memory_bytes': 16*GIB, 'controller_cpu': 2, 'controller_memory_bytes': 16*GIB,
    'grader_cpu': 4, 'grader_memory_bytes': 16*GIB,
    'maximum_active_containers': 10, 'memory_minimum_free_bytes': 64*GIB,
    'disk_minimum_free_bytes': 128*GIB, 'maximum_real_tls_sessions': 10,
    'real_tls_all_sessions_payload_bytes': 10*64*1024**2,
    'system_parent_slice_created': False, 'aggregate_memory_limit_kind': 'sum of bounded owned objects',
    'previous_runtime_must_be_quiescent': True,
    'physical_gpus': [],
    'new_model_calls_for_preparation': 0,
    'host_namespaces_or_mount_configuration_changed': False,
    'automatic_replay': False,
}


def load(ref):
    return original._cached_json(ref)


def retain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if load(reference(path)) != value:
            raise ValueError('Prepared v111 identity changed: '+str(path))
        return reference(path)
    return write_new(path, value)


def host_cpu_pool():
    value = load(reference(CPU_POOL_FILE))
    pool = value['cpu_ids']
    if (value.get('uid') != os.getuid() or len(pool) < 176 or len(pool) != len(set(pool))
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
        start, stop = 32+4*index, 36+4*index
    else:
        raise ValueError('Resource is outside the API-only v111 CPU lanes')
    return ','.join(map(str, host_cpu_pool()[start:stop]))


def validate_plan(plan):
    from .software_benchmark_alignment_contract_v110 import validate_plan_identity
    rows=plan.get('rows',[])
    generation=plan.get('generation_rows',[])
    if (plan.get('version')!=VERSION or plan.get('root')!=str(BATCH_ROOT)
            or plan.get('panel')!=reference(PANEL_FILE) or plan.get('constraints')!=CONSTRAINTS
            or plan.get('host_cpu_pool')!=reference(CPU_POOL_FILE)
            or {row['slot_index'] for row in rows}!={7238,7239,7266,7267}
            or len(rows)!=4 or {row['slot_index'] for row in generation}!={7238,7239,7266,7267}
            or len(generation)!=4 or len(plan.get('environments',{}))!=2
            or plan.get('score_recoveries')!=[]):
        raise PermissionError('Only the fixed eight unresolved endpoints may enter this recovery')
    for row in rows:
        validate_plan_identity(row)
        if row.get('model_key')!='DEEPSEEK' or row.get('thinking') is not False:
            raise PermissionError('No model or thinking-mode change')
    if any(row not in rows for row in generation):
        raise PermissionError('Generation rows must be exact original identities')
    return plan


def require_allowed(operation='v111.run', *, slot_id=None, instance_id=None, grading_only=False):
    allowed = {'v105.run', 'v105.api.run', 'v105.api.request', 'v105.prepare', 'v112.run', 'v112.api.run', 'v112.api.request', 'v112.prepare', 'v113.run', 'v113.api.run', 'v113.api.request', 'v113.prepare', 'v114.run', 'v114.api.run', 'v114.api.request', 'v114.prepare', 'v115.run', 'v115.api.run', 'v115.api.request', 'v115.prepare', 'v116.run', 'v116.api.run', 'v116.api.request', 'v116.prepare', 'v111.run', 'v111.api.run', 'v111.api.request', 'v111.prepare',
               'v076.run', 'v079.run', 'v088.run', 'v089.run', 'v096.run',
               'v072.api.request'} | (set(original.OPERATIONS)-{'v066.model.start'})
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in allowed:
        raise PermissionError('Only the bounded ordinary-user v111 API experiment is admitted')
    if grading_only and operation not in {'v111.run', 'v112.run', 'v113.run', 'v114.run', 'v115.run', 'v116.run', 'v066.run', 'v066.score', 'v066.delivery.score',
            'v066.control', 'v066.grader.create', 'v066.grader.start', 'v066.transport', 'v066.resolve'}:
        raise PermissionError('Grading authority cannot create actors or call the model')
    if not AUTH_FILE.is_file():
        raise PermissionError('Concrete v111 runtime authorization has not been sealed')
    from .software_benchmark_alignment_contract_v110 import VERSION as ALIGNMENT_VERSION
    auth = load(reference(AUTH_FILE))
    if (auth.get('precreation_recovery') != reference(TLS_PRECREATION_RECOVERY_FILE)
            or auth.get('original_authorized_total_containers') != 26
            or auth.get('already_created_containers') != 12
            or auth.get('additional_object_allowance') != 4
            or auth.get('total_authorized_containers') != 30
            or auth.get('total_authorized_TLS_sessions') != 14
            or auth.get('installed_CA_recovery') != reference(INSTALLED_CA_RECOVERY_FILE)):
        raise PermissionError('Only the unused physical allowance may continue after proven zero creation')
    if (auth.get('original_batch_authorization') != reference(PARENT_AUTH_FILE)
            or auth.get('network_resolution') != reference(NETWORK_RESOLUTION_FILE)
            or auth.get('CA_profile') != reference(CA_PROFILE_FILE)):
        raise PermissionError('Recovery requires its own exact environment and operation authority')
    if (auth.get('concurrency_authorization') != reference(CONCURRENCY_AUTH_FILE)
            or auth.get('preparation_recovery') != reference(PREPARATION_RECOVERY_FILE)
            or auth.get('diagnostics_repeated') != 0):
        raise PermissionError('Recovery must keep the consumed diagnostics and exact object allowance')
    if (auth.get('original_authorization') != reference(ORIGINAL_AUTH_FILE)
            or auth.get('explicit_concurrency_instruction') != '提高并发'):
        raise PermissionError('A new concurrency bound needs its explicit user instruction and original object scope')
    if (auth.get('execution_alignment_version') != ALIGNMENT_VERSION
            or auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('API_cash_cap_CNY') != CASH_CAP_CNY
            or auth.get('cash_budget_scope') != CASH_MODE
            or auth.get('ledger_path') != str(LEDGER_FILE)
            or auth.get('cash_before_run') != reference(BUDGET_BASELINE_FILE)
            or auth.get('new_generation_attempts') != 4
            or auth.get('constraints') != CONSTRAINTS
            or auth.get('shared_host_configuration_changes') != 0):
        raise PermissionError('Independent API budget or resource authority differs')
    for item in load(auth['source_index'])['files']:
        checked(item)
    plan = validate_plan(load(auth['plan']))
    if slot_id is not None:
        matches = [row for row in plan['rows'] if row['slot_id'] == slot_id]
        if operation.endswith('request') and slot_id not in {row['slot_id'] for row in plan['generation_rows']}:
            raise PermissionError('An already called model episode cannot be resampled')
        if len(matches) != 1 or instance_id not in (None, matches[0]['instance_id']):
            raise PermissionError('Request is outside the frozen 100 new attempts')
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Task is outside the frozen 50-task panel')
    if operation in {'v066.transport', 'v066.resolve'} and instance_id not in original.TLS_TASKS:
        raise PermissionError('External grading transport is limited to the two declared TLS tasks')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.is_file() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No live exact v111 API-owner reservation')
    return auth


def require_grading_allowed(operation='v111.run', **identity):
    return require_allowed(operation, grading_only=True, **identity)


def verify_host_limits(role='api'):
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if role != 'api' or len(paths) != 1 or Path(paths[0]).name != API_UNIT:
        raise PermissionError('Use the separately bounded v111 ordinary-user service')
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
    # Called under the existing atomic resource allocation lock.
    used_cpu = MANAGER_CPUS + sum(row['reserved_cpu'] for row in active
                                 if row['spec']['role'] != 'auxiliary_coordinator')
    used_memory = API_MEMORY_BYTES + sum(row['reserved_memory_bytes'] for row in active
                                       if row['spec']['role'] != 'auxiliary_coordinator')
    graders = sum(row['spec']['role'] in {'score', 'delivery_score', 'control'} for row in active)
    if cpu == 4 and memory == 16*GIB and spool == 0 and graders >= MAX_GRADERS:
        raise ResourceBusy('Both independently bounded grading lanes are occupied')
    if used_cpu+cpu > 40 or used_memory+memory > 192*GIB:
        raise ResourceBusy('Bounded v111 CPU/RAM capacity is full')
    capacity = dispatch_view().physical_capacity()
    spool_total = spool + sum(row.get('reserved_spool_bytes', 0) for row in active)
    if (capacity['memory_available_bytes'] < CONSTRAINTS['memory_minimum_free_bytes']+memory
            or capacity['disk_free_bytes'] < CONSTRAINTS['disk_minimum_free_bytes']+spool_total):
        raise ResourceBusy('Shared-host memory or disk headroom is insufficient')
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
        value = {'version': VERSION, 'key': 'v116-api-coordinator',
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
