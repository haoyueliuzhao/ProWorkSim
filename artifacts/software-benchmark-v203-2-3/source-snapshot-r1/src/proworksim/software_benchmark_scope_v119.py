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
VERSION = 'v119-project-startup-recovery-scope-r1'
BATCH_ROOT = ROOT / 'runs/software-benchmark-v118/project-repaired-r1'
API_ROOT = BATCH_ROOT / 'api-coordinator-v119'
COORDINATOR_ROOT = BATCH_ROOT / 'grading-coordinator-v119'
GRADING_ROOT = BATCH_ROOT / 'grading-v119'
PLAN_FILE = BATCH_ROOT / 'execution-plan-v119.json'
INVENTORY_FILE = BATCH_ROOT / 'inventory.json'
SOURCE_FILE = BATCH_ROOT / 'runtime-sources-v119.json'
CPU_POOL_FILE = BATCH_ROOT / 'host-cpu-pool.json'
AUTH_FILE = ROOT / 'config/v119-project-startup-recovery.json'
NETWORK_RESOLUTION_FILE = BATCH_ROOT / 'network-resolution.json'
CA_PROFILE_FILE = ROOT / 'runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json'
PROJECT_SCHEMA_WIRE_FILE = ROOT / 'artifacts/software-benchmark-v117/rejected-history-sdk-r3/PROJECT/ledger/request-0001.json'
PREPARATION_QUALIFICATION_FILE = API_ROOT / 'preparation-qualification.json'
PANEL_FILE = ROOT / 'artifacts/software-benchmark-v118/preparation-r1/panel.json'
LEDGER_FILE = ROOT / 'runs/software-benchmark-v105/nonthinking-interface-r1/api-ledger.sqlite'
BUDGET_BASELINE_FILE = BATCH_ROOT / 'cash-before.json'
CASH_MODE = 'continue_original_v105_ledger_cumulative_CNY350'
API_UNIT = 'proworksim-v118-project.service'
CLAIM_FILE = API_ROOT / 'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT / 'resource-claims/active-v119-coordinator.json'
GIB = 1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*GIB, 24*GIB
MAX_GENERATIONS, MAX_GRADERS, MANAGER_CPUS, NOFILE = 16, 2, 8, 16384
CASH_CAP_CNY = '350.00'
DIAGNOSTIC_INDEX = 2
RECOVERY_FILE = BATCH_ROOT / 'startup-recovery-v119.json'
PARENT_AUTH_FILE = ROOT / 'config/v118-project-rerun-authorization.json'
FIRST_PHYSICAL_INDEX, LAST_PHYSICAL_INDEX = 8000, 8049
ResourceBusy = original.ResourceBusy

CONSTRAINTS = {**original.CONSTRAINTS,
    'fresh_generation_slots': 50, 'generation_token_upper_bound': 250_000_000,
    'api_generation_token_upper_bound': 250_000_000, 'api_total_budget_cny': CASH_CAP_CNY,
    'cash_budget_scope': CASH_MODE,
    'old_settled_and_uncertain_reservations_retained': True,
    'maximum_actor_containers': 51, 'maximum_controller_containers': 51,
    'maximum_control_containers': 100, 'maximum_code_score_containers': 50,
    'maximum_delivery_score_containers': 50, 'maximum_score_containers': 100,
    'maximum_containers': 302, 'maximum_named_volumes': 51,
    'zero_model_diagnostic_pairs': 1, 'initial_zero_model_diagnostic_pairs': 1,
    'conditional_zero_model_repair_pairs': 0, 'maximum_model_residents': 0,
    'neutral_model_preparation_calls': 0, 'neutral_model_preparation_total_tokens': 0,
    'api_neutral_preparation_calls': 1, 'api_neutral_preparation_total_tokens': 4096,
    'free_api_metadata_requests': 0, 'new_owned_user_units': [API_UNIT],
    'maximum_combined_reserved_cpu': 112, 'maximum_combined_reserved_memory_bytes': 576*GIB,
    'coordinator_memory_bytes': API_MEMORY_BYTES, 'coordinator_cpu_quota_percent': 800,
    'active_actor_limit': MAX_GENERATIONS, 'active_controller_limit': MAX_GENERATIONS,
    'active_grader_limit': MAX_GRADERS, 'maximum_active_generation_episodes': MAX_GENERATIONS,
    'generation_pair_reserved_cpu': 6, 'generation_pair_reserved_memory_bytes': 32*GIB,
    'actor_cpu': 4, 'actor_memory_bytes': 16*GIB, 'controller_cpu': 2, 'controller_memory_bytes': 16*GIB,
    'grader_cpu': 4, 'grader_memory_bytes': 16*GIB,
    'maximum_active_containers': 34, 'memory_minimum_free_bytes': 64*GIB,
    'disk_minimum_free_bytes': 128*GIB, 'maximum_real_tls_sessions': 8,
    'real_tls_all_sessions_payload_bytes': 8*64*1024**2,
    'system_parent_slice_created': False, 'aggregate_memory_limit_kind': 'sum of bounded owned objects',
    'previous_runtime_must_be_quiescent': True,
    'physical_gpus': [],
    'new_model_calls_for_preparation': 1,
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
            raise ValueError('Prepared v118 identity changed: '+str(path))
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
        raise ValueError('Resource is outside the API-only v118 CPU lanes')
    return ','.join(map(str, host_cpu_pool()[start:stop]))


def validate_plan(plan):
    rows = plan.get('rows', [])
    if (plan.get('version') != VERSION or plan.get('root') != str(BATCH_ROOT)
            or plan.get('panel') != reference(PANEL_FILE)
            or plan.get('constraints') != CONSTRAINTS
            or plan.get('host_cpu_pool') != reference(CPU_POOL_FILE)
            or len(rows) != 50 or len({r['slot_id'] for r in rows}) != 50
            or {r['slot_index'] for r in rows} != set(range(8000, 8050))
            or any(r.get('model_key') != 'DEEPSEEK' or r.get('thinking') is not False
                   or r.get('input_plus_output_tokens') != 5_000_000 for r in rows)
            or any(r.get('arm') != 'PROJECT' for r in rows)
            or len(plan.get('environments', {})) != 50):
        raise PermissionError('The independent PROJECT-only 50-task scope changed')
    expected_counts = {'actor': 51, 'controller': 51, 'volume': 51, 'score': 50, 'delivery_score': 50, 'control': 100}
    if plan.get('resource_role_counts') != expected_counts:
        raise PermissionError('The bounded new container/volume inventory changed')
    diagnostics = plan.get('diagnostics', [])
    if (len(diagnostics) != 1 or diagnostics[0].get('index') != DIAGNOSTIC_INDEX
            or diagnostics[0].get('arm') != 'PROJECT'
            or diagnostics[0].get('instance_id') != 'psf__requests-2931'
            or diagnostics[0].get('model_calls') != 0):
        raise PermissionError('Only the prespecified PROJECT public-fixture diagnostic is admitted')
    from .software_benchmark_alignment_contract_v117 import validate_plan_identity
    for row in rows:
        validate_plan_identity(row)
    return plan


def require_allowed(operation='v118.run', *, slot_id=None, instance_id=None, grading_only=False):
    allowed = {'v119.run', 'v119.api.run', 'v119.api.request', 'v119.prepare', 'v105.run', 'v105.api.run', 'v105.api.request', 'v105.prepare', 'v118.run', 'v118.api.run', 'v118.api.request', 'v118.prepare', 'v118.run', 'v118.api.run', 'v118.api.request', 'v118.prepare',
               'v076.run', 'v079.run', 'v088.run', 'v089.run', 'v096.run',
               'v072.api.request'} | (set(original.OPERATIONS)-{'v066.model.start'})
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in allowed:
        raise PermissionError('Only the bounded ordinary-user v118 API experiment is admitted')
    if grading_only and operation not in {'v119.run', 'v118.run', 'v118.run', 'v066.run', 'v066.score', 'v066.delivery.score',
            'v066.control', 'v066.grader.create', 'v066.grader.start', 'v066.transport', 'v066.resolve'}:
        raise PermissionError('Grading authority cannot create actors or call the model')
    if not AUTH_FILE.is_file():
        raise PermissionError('Concrete v118 runtime authorization has not been sealed')
    from .software_benchmark_alignment_contract_v117 import VERSION as ALIGNMENT_VERSION
    auth = load(reference(AUTH_FILE))
    if (auth.get('parent_authorization') != reference(PARENT_AUTH_FILE)
            or auth.get('startup_recovery') != reference(RECOVERY_FILE)
            or auth.get('prior_created_containers') != 2
            or auth.get('prior_created_volumes') != 1
            or auth.get('cumulative_maximum_containers') != 304
            or auth.get('cumulative_maximum_named_volumes') != 52):
        raise PermissionError('Only the uncalled original PROJECT panel may recover with its new diagnostic identity')
    if (auth.get('execution_alignment_version') != ALIGNMENT_VERSION
            or auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('API_cash_cap_CNY') != CASH_CAP_CNY
            or auth.get('cash_budget_scope') != CASH_MODE
            or auth.get('ledger_path') != str(LEDGER_FILE)
            or auth.get('cash_before_run') != reference(BUDGET_BASELINE_FILE)
            or auth.get('new_generation_attempts') != 50
            or auth.get('constraints') != CONSTRAINTS
            or auth.get('shared_host_configuration_changes') != 0):
        raise PermissionError('Independent API budget or resource authority differs')
    for item in load(auth['source_index'])['files']:
        checked(item)
    plan = validate_plan(load(auth['plan']))
    if slot_id is not None:
        matches = [row for row in plan['rows'] if row['slot_id'] == slot_id]
        if len(matches) != 1 or instance_id not in (None, matches[0]['instance_id']):
            raise PermissionError('Request is outside the frozen 50 new PROJECT attempts')
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Task is outside the frozen 50-task panel')
    if operation in {'v066.transport', 'v066.resolve'} and instance_id not in original.TLS_TASKS:
        raise PermissionError('External grading transport is limited to the two declared TLS tasks')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.is_file() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No live exact v118 API-owner reservation')
    return auth


def require_grading_allowed(operation='v118.run', **identity):
    return require_allowed(operation, grading_only=True, **identity)


def verify_host_limits(role='api'):
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if role != 'api' or len(paths) != 1 or Path(paths[0]).name != API_UNIT:
        raise PermissionError('Use the separately bounded v118 ordinary-user service')
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
    if used_cpu+cpu > 112 or used_memory+memory > 576*GIB:
        raise ResourceBusy('Bounded v118 CPU/RAM capacity is full')
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
        value = {'version': VERSION, 'key': 'v118-api-coordinator',
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
