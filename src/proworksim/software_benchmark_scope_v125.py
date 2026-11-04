"""First calls for two original REF tasks under the existing amended cumulative ledger."""
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
VERSION = 'v125-original-REF-first-generation-scope-r1'
ORIGINAL_BATCH_ROOT = ROOT / 'runs/software-benchmark-v111/aligned-interface-r1'
PRIOR_BATCH_ROOT = ROOT / 'runs/software-benchmark-v123/nine-api-recovery-r1'
BATCH_ROOT = ROOT / 'runs/software-benchmark-v125/ref-first-generation-r1'
API_ROOT = BATCH_ROOT / 'api-coordinator'
COORDINATOR_ROOT = BATCH_ROOT / 'grading-coordinator'
GRADING_ROOT = BATCH_ROOT / 'grading'
PLAN_FILE = BATCH_ROOT / 'execution-plan.json'
INVENTORY_FILE = BATCH_ROOT / 'inventory.json'
SOURCE_FILE = BATCH_ROOT / 'runtime-sources.json'
CPU_POOL_FILE = ROOT / 'runs/software-benchmark-v118/project-repaired-r1/host-cpu-pool.json'
AUTH_FILE = ROOT / 'config/v125-ref-first-generation-authorization.json'
NETWORK_RESOLUTION_FILE = ROOT / 'runs/software-benchmark-v118/project-repaired-r1/network-resolution.json'
CA_PROFILE_FILE = ROOT / 'runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json'
PROJECT_SCHEMA_WIRE_FILE = ROOT / 'artifacts/software-benchmark-v117/rejected-history-sdk-r3/PROJECT/ledger/request-0001.json'
PREPARATION_QUALIFICATION_FILE = API_ROOT / 'preparation-qualification.json'
PANEL_FILE = ROOT / 'artifacts/software-benchmark-v125/first-generation-preparation-r1/panel.json'
LEDGER_FILE = ROOT / 'runs/software-benchmark-v105/nonthinking-interface-r1/api-ledger.sqlite'
BUDGET_BASELINE_FILE = BATCH_ROOT / 'cash-before.json'
CASH_MODE = 'continue_original_v105_ledger_with_v122_available_CNY45_amendment'
API_UNIT = 'proworksim-v118-project.service'
CLAIM_FILE = API_ROOT / 'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT / 'resource-claims/active-v125-coordinator.json'
GIB = 1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*GIB, 24*GIB
MAX_GENERATIONS, MAX_GRADERS, MANAGER_CPUS, NOFILE = 2, 2, 8, 16384
CASH_CAP_CNY = '389.7945248'
CASH_AMENDMENT_FILE = ROOT/'config/v122-cash-amendment.json'
DIAGNOSTIC_INDEX = None
RECOVERY_FILE = BATCH_ROOT / 'first-generation-recovery.json'
USER_GRANT_FILE = ROOT / 'config/v125-ref-unresolved-user-grant.json'
USER_PROPOSAL_FILE = ROOT / 'artifacts/software-benchmark-v125/first-generation-preparation-r1/proposal.json'
PRIOR_COMPLETION_FILE = BATCH_ROOT / 'prior-v123-completion.json'
PARENT_AUTH_FILE = ROOT / 'config/v114-unknown-recovery-authorization.json'
ORIGINAL_PLAN_FILE = ORIGINAL_BATCH_ROOT / 'execution-plan-v113.json'
PRIOR_PLAN_FILE = PRIOR_BATCH_ROOT / 'execution-plan.json'
PRIOR_API_ROOT = PRIOR_BATCH_ROOT / 'api-coordinator'
HELD_INVENTORY_FILE = ROOT / 'artifacts/software-benchmark-v125/first-generation-preparation-r1/inventory.json'
FIRST_PHYSICAL_INDEX, LAST_PHYSICAL_INDEX = 7239, 7267
ResourceBusy = original.ResourceBusy

CONSTRAINTS = {**original.CONSTRAINTS,
    'fresh_generation_slots': 2, 'generation_token_upper_bound': 10_000_000,
    'api_generation_token_upper_bound': 10_000_000, 'api_total_budget_cny': CASH_CAP_CNY,
    'cash_budget_scope': CASH_MODE,
    'old_settled_and_uncertain_reservations_retained': True,
    'maximum_actor_containers': 2, 'maximum_controller_containers': 2,
    'maximum_control_containers': 0, 'maximum_code_score_containers': 2,
    'maximum_delivery_score_containers': 0, 'maximum_score_containers': 2,
    'maximum_containers': 6, 'maximum_named_volumes': 2,
    'zero_model_diagnostic_pairs': 0, 'initial_zero_model_diagnostic_pairs': 0,
    'conditional_zero_model_repair_pairs': 0, 'maximum_model_residents': 0,
    'neutral_model_preparation_calls': 0, 'neutral_model_preparation_total_tokens': 0,
    'api_neutral_preparation_calls': 0, 'api_neutral_preparation_total_tokens': 0,
    'free_api_metadata_requests': 0, 'new_owned_user_units': [API_UNIT],
    'maximum_combined_reserved_cpu': 28, 'maximum_combined_reserved_memory_bytes': 128*GIB,
    'coordinator_memory_bytes': API_MEMORY_BYTES, 'coordinator_cpu_quota_percent': 800,
    'active_actor_limit': MAX_GENERATIONS, 'active_controller_limit': MAX_GENERATIONS,
    'active_grader_limit': MAX_GRADERS, 'maximum_active_generation_episodes': MAX_GENERATIONS,
    'generation_pair_reserved_cpu': 6, 'generation_pair_reserved_memory_bytes': 32*GIB,
    'actor_cpu': 4, 'actor_memory_bytes': 16*GIB, 'controller_cpu': 2, 'controller_memory_bytes': 16*GIB,
    'grader_cpu': 4, 'grader_memory_bytes': 16*GIB,
    'maximum_active_containers': 6, 'memory_minimum_free_bytes': 64*GIB,
    'disk_minimum_free_bytes': 128*GIB, 'maximum_real_tls_sessions': 2,
    'real_tls_all_sessions_payload_bytes': 2*64*1024**2,
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
            raise ValueError('Prepared v125 identity changed: '+str(path))
        return reference(path)
    return write_new(path, value)


def host_cpu_pool():
    value = load(reference(CPU_POOL_FILE))
    pool = value['cpu_ids']
    if (value.get('uid') != os.getuid() or len(pool) < 28 or len(pool) != len(set(pool))
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
        start, stop = 20+4*index, 24+4*index
    else:
        raise ValueError('Resource is outside the API-only v118 CPU lanes')
    return ','.join(map(str, host_cpu_pool()[start:stop]))


def validate_plan(plan):
    rows = plan.get('rows', [])
    if (plan.get('version') != VERSION or plan.get('root') != str(BATCH_ROOT)
            or plan.get('panel') != reference(PANEL_FILE)
            or plan.get('constraints') != CONSTRAINTS
            or plan.get('host_cpu_pool') != reference(CPU_POOL_FILE)
            or len(rows) != 2 or len({r['slot_id'] for r in rows}) != 2
            or {r['slot_index'] for r in rows} != {7239, 7267}
            or any(r.get('model_key') != 'DEEPSEEK' or r.get('thinking') is not False
                   or r.get('input_plus_output_tokens') != 5_000_000 for r in rows)
            or any(r.get('arm') != 'REF' for r in rows)
            or len(plan.get('environments', {})) != 2):
        raise PermissionError('The two uncalled original REF task scope changed')
    expected_counts = {'actor': 2, 'controller': 2, 'volume': 2, 'score': 2}
    if plan.get('resource_role_counts') != expected_counts:
        raise PermissionError('The bounded new container/volume inventory changed')
    if plan.get('diagnostics') != []:
        raise PermissionError('The passed zero-model diagnostic must not be repeated')
    originals = {row['slot_id']: row for row in load(reference(ORIGINAL_PLAN_FILE))['rows']}
    if plan.get('generation_rows') != rows or any(row != originals.get(row['slot_id']) for row in rows):
        raise PermissionError('Only unchanged original never-called REF identities may continue')
    from .software_benchmark_alignment_contract_v110 import validate_plan_identity
    for row in rows:
        validate_plan_identity(row)
    return plan


def require_allowed(operation='v118.run', *, slot_id=None, instance_id=None, grading_only=False):
    allowed = {'v125.run', 'v125.api.run', 'v125.api.request', 'v125.prepare', 'v123.run', 'v123.api.run', 'v123.api.request', 'v123.prepare', 'v121.run', 'v121.api.run', 'v121.api.request', 'v121.prepare', 'v120.run', 'v120.api.run', 'v120.api.request', 'v120.prepare', 'v119.run', 'v119.api.run', 'v119.api.request', 'v119.prepare', 'v105.run', 'v105.api.run', 'v105.api.request', 'v105.prepare', 'v118.run', 'v118.api.run', 'v118.api.request', 'v118.prepare', 'v118.run', 'v118.api.run', 'v118.api.request', 'v118.prepare',
               'v076.run', 'v079.run', 'v088.run', 'v089.run', 'v096.run',
               'v072.api.request'} | (set(original.OPERATIONS)-{'v066.model.start'})
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in allowed:
        raise PermissionError('Only the bounded ordinary-user v125 API experiment is admitted')
    if grading_only and operation not in {'v125.run', 'v123.run', 'v121.run', 'v120.run', 'v119.run', 'v118.run', 'v118.run', 'v066.run', 'v066.score', 'v066.delivery.score',
            'v066.control', 'v066.grader.create', 'v066.grader.start', 'v066.transport', 'v066.resolve'}:
        raise PermissionError('Grading authority cannot create actors or call the model')
    if not AUTH_FILE.is_file():
        raise PermissionError('Concrete v125 runtime authorization has not been sealed')
    from .software_benchmark_alignment_contract_v110 import VERSION as ALIGNMENT_VERSION
    auth = load(reference(AUTH_FILE))
    grant = load(reference(USER_GRANT_FILE))
    if (grant.get('status') != 'approved'
            or grant.get('explicit_user_instruction') != '对ref的未定做分析处理'
            or grant.get('proposal') != reference(USER_PROPOSAL_FILE)
            or auth.get('user_grant') != reference(USER_GRANT_FILE)
            or auth.get('first_generation_recovery') != reference(RECOVERY_FILE)
            or auth.get('prior_completion') != reference(PRIOR_COMPLETION_FILE)
            or auth.get('maximum_containers') != 6
            or auth.get('maximum_named_volumes') != 2
            or auth.get('cash_amendment') != reference(CASH_AMENDMENT_FILE)):
        raise PermissionError('Only the explicitly authorized independent recovery after prior-stage completion is admitted')
    if (auth.get('execution_alignment_version') != ALIGNMENT_VERSION
            or auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('API_cash_cap_CNY') != CASH_CAP_CNY
            or auth.get('cash_budget_scope') != CASH_MODE
            or auth.get('ledger_path') != str(LEDGER_FILE)
            or auth.get('cash_before_run') != reference(BUDGET_BASELINE_FILE)
            or auth.get('new_generation_attempts') != 2
            or auth.get('constraints') != CONSTRAINTS
            or auth.get('shared_host_configuration_changes') != 0):
        raise PermissionError('Independent API budget or resource authority differs')
    for item in load(auth['source_index'])['files']:
        checked(item)
    plan = validate_plan(load(auth['plan']))
    if slot_id is not None:
        matches = [row for row in plan['rows'] if row['slot_id'] == slot_id]
        if len(matches) != 1 or instance_id not in (None, matches[0]['instance_id']):
            raise PermissionError('Request is outside the frozen two uncalled REF attempts')
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Task is outside the frozen two-task panel')
    if operation in {'v066.transport', 'v066.resolve'} and instance_id not in original.TLS_TASKS:
        raise PermissionError('External grading transport is limited to the two declared TLS tasks')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.is_file() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No live exact v125 API-owner reservation')
    return auth


def require_grading_allowed(operation='v118.run', **identity):
    return require_allowed(operation, grading_only=True, **identity)


def verify_host_limits(role='api'):
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if role != 'api' or len(paths) != 1 or Path(paths[0]).name != API_UNIT:
        raise PermissionError('Use the separately bounded v125 ordinary-user service')
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
    if used_cpu+cpu > 28 or used_memory+memory > 128*GIB:
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
        value = {'version': VERSION, 'key': 'v125-api-coordinator',
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
