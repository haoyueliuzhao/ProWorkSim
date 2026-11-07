"""Bounded independent recovery after the completed pilot; no old attempt reuse."""
from __future__ import annotations

from collections import Counter
import fcntl
import os
from pathlib import Path
import resource
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_scope_v142 as previous
from . import software_benchmark_scope_v143 as original_pilot
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_alignment_contract_v146 import GROUP_IDS, validate_plan_identity

ROOT = original.ROOT
VERSION = 'v146-independent-role-API-recovery-scope-r1'
BATCH_ROOT = ROOT/'runs/software-benchmark-v146/api-recovery21-r1'
STATE_ROOT = BATCH_ROOT
ARTIFACT_ROOT = ROOT/'artifacts/software-benchmark-v146'
API_ROOT = STATE_ROOT/'api-coordinator'
COORDINATOR_ROOT = STATE_ROOT/'grading-coordinator'
GRADING_ROOT = STATE_ROOT/'grading'
PLAN_FILE = STATE_ROOT/'execution-plan.json'
INVENTORY_FILE = STATE_ROOT/'inventory.json'
SOURCE_FILE = STATE_ROOT/'runtime-sources.json'
CPU_POOL_FILE = previous.CPU_POOL_FILE
AUTH_FILE = ROOT/'config/v146-role-recovery-authorization.json'
PROPOSAL_FILE = ARTIFACT_ROOT/'runtime-authorization-r1/proposal.json'
USER_GRANT_FILE = ROOT/'config/v146-role-recovery-user-grant.json'
NETWORK_RESOLUTION_FILE = previous.NETWORK_RESOLUTION_FILE
NETWORK_SCOPE_MAPPING_FILE = STATE_ROOT/'network-scope-equivalence.json'
STANDING_POLICY_FILE = ROOT/'config/v143-standing-docker-user-policy.json'
STANDING_PERMISSION_FILE = STANDING_POLICY_FILE
PRIOR_COMPLETION_FILE = STATE_ROOT/'predecessor-completion.json'
CA_PROFILE_FILE = ROOT/'runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json'
PREPARATION_QUALIFICATION_FILE = API_ROOT/'preparation-qualification.json'
PANEL_FILE = ARTIFACT_ROOT/'independent-recovery-r1/panel.json'
SOURCE_PANEL_FILE = ROOT/'artifacts/software-benchmark-v118/preparation-r1/panel.json'
SOURCE_PLAN_FILE = ROOT/'runs/software-benchmark-v118/project-repaired-r1/execution-plan-v119.json'
LEDGER_FILE = ROOT/'runs/software-benchmark-v145/api-recovery-prepared-r1/ledger.sqlite'
LEDGER_FILES = {group: LEDGER_FILE for group in GROUP_IDS}
BUDGET_BASELINE_FILE = ROOT/'artifacts/software-benchmark-v145/api-deployment-preparation-r3/cash-authority.json'
CASH_MODE = 'remaining_original400_subledger_after_retaining_original_settled_and_uncertain'
CASH_CAP_CNY = '99.1863482'
ORIGINAL_TOTAL_CAP_CNY = '450.00'
API_UNIT = previous.API_UNIT
CLAIM_FILE = API_ROOT/'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT/'resource-claims/active-v146-coordinator.json'
GIB = 1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*GIB, 30*GIB
MAX_GENERATIONS, MAX_GRADERS, MANAGER_CPUS, NOFILE = 8, 2, 8, 16384
MAX_STARTUPS = 4
CONTAINER_PARENT = None
FIRST_PHYSICAL_INDEX, LAST_PHYSICAL_INDEX, DIAGNOSTIC_INDEX = 10200, 10241, None
ResourceBusy = original.ResourceBusy
CONSTRAINTS = {**original.CONSTRAINTS,
    'fresh_generation_slots': 42, 'generation_token_upper_bound': 210_000_000,
    'api_generation_token_upper_bound': 210_000_000, 'api_total_budget_cny': CASH_CAP_CNY,
    'original_pilot_and_recovery_cumulative_budget_cny': ORIGINAL_TOTAL_CAP_CNY,
    'api_budget_shared_across_groups': True,
    'cash_budget_scope': CASH_MODE, 'old_ledgers_untouched': True,
    'maximum_actor_containers': 42, 'maximum_controller_containers': 42,
    'maximum_control_containers': 0, 'maximum_code_score_containers': 84,
    'maximum_delivery_score_containers': 84, 'maximum_score_containers': 168,
    'maximum_containers': 252, 'maximum_named_volumes': 42,
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
    'disk_minimum_free_bytes': 128*GIB, 'maximum_real_tls_sessions': 32,
    'real_tls_all_sessions_payload_bytes': 2048*1024**2,
    'real_tls_all_sessions_connections': 16384, 'real_tls_session_connections': 512,
    'real_tls_session_payload_bytes': 64*1024**2,
    'system_parent_slice_created': False, 'aggregate_memory_limit_kind': 'sum_of_bounded_owned_objects',
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
            raise ValueError('Prepared v143 identity changed: '+str(path))
        return reference(path)
    return write_new(path, value)

def host_cpu_pool():
    value = load(reference(CPU_POOL_FILE))
    pool = value['cpu_ids']
    if (value.get('uid') != os.getuid() or len(pool) < 64 or len(pool) != len(set(pool))
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
        start, stop = 56+4*index, 60+4*index
    else:
        raise ValueError('Resource is outside the pilot CPU lanes')
    return ','.join(map(str, host_cpu_pool()[start:stop]))


def verify_host_limits(role='api'):
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if role != 'api' or len(paths) != 1 or Path(paths[0]).name != API_UNIT:
        raise PermissionError('Use the separately bounded v146 ordinary-user service')
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
        COORDINATOR_RUN_ROOT=COORDINATOR_ROOT, AUTHORIZATION_FILE=AUTH_FILE,
        CONSTRAINTS=CONSTRAINTS, __file__=__file__)
    def allowed(operation='v066.run', **identity):
        value = guard(operation, **identity)
        return {**value, 'plan': reference(PLAN_FILE), 'sources': reference(SOURCE_FILE),
                'constraints': CONSTRAINTS}
    namespace.update(require_v066_allowed=allowed, host_cpu_pool=host_cpu_pool,
                     cpu_set=cpu_set, _budget=_budget)
    original_claim = namespace['claim_resource']
    def claim_resource(key, *, lane=None):
        resource = load(reference(PLAN_FILE))['resources'].get(key)
        if resource is None:
            raise PermissionError('Foreign recovery resource identity')
        if resource.get('recovery_round') == 2 and resource['role'] in {'actor','controller','volume'}:
            validate_second_attempt_admission(resource['slot_id'])
        if resource.get('score_retry'):
            validate_score_retry_admission(key)
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
        value = {'version': VERSION, 'key': 'v146-api-coordinator',
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

def never_consumed(row):
    validate_plan_identity(row)
    return not any((BATCH_ROOT/'resource-claims'/f"{role}-{row['slot_index']}.json").exists()
                   for role in ('actor', 'controller', 'volume'))


def validate_original_probe_reuse():
    """Retain the original numeric endpoint/CA proof; perform no new probe."""
    return original_pilot.validate_original_probe_reuse()


def validate_plan(plan):
    panel = load(reference(PANEL_FILE))
    rows = plan.get('rows', [])
    expected = {'actor':42, 'controller':42, 'volume':42, 'score':84, 'delivery_score':84}
    if (plan.get('version') != VERSION or plan.get('root') != str(BATCH_ROOT)
            or plan.get('panel') != reference(PANEL_FILE) or rows != panel['rows']
            or plan.get('constraints') != CONSTRAINTS
            or plan.get('host_cpu_pool') != reference(CPU_POOL_FILE)
            or len(rows) != 42 or len({r['slot_id'] for r in rows}) != 42
            or {r['slot_index'] for r in rows} != set(range(10200,10242))
            or plan.get('diagnostics') != []
            or plan.get('resource_role_counts') != expected
            or dict(Counter(r['role'] for r in plan.get('resources', {}).values())) != expected
            or set(plan.get('environments', {})) != set(panel['task_ids'])):
        raise PermissionError('The explicitly bounded independent recovery plan changed')
    old_rows = {r['slot_id']:r for r in load(reference(original_pilot.PLAN_FILE))['rows']}
    for row in rows:
        validate_plan_identity(row)
        old = old_rows.get(row['original_slot_id'])
        if (old is None or row.get('recovery_of_slot_id') != old['slot_id']
                or row.get('original_slot_index') != old['slot_index']
                or any(row.get(k) != old[k] for k in ('instance_id','condition_id','group_id','seed',
                    'fixed_members','organization_id','model_key','thinking','input_plus_output_tokens'))
                or row['recovery_round'] not in (1,2)
                or row['slot_index'] != 10200+row['recovery_task_index']+21*(row['recovery_round']-1)):
            raise PermissionError('A recovery task, seed, group or budget differs from the original')
        prior = load(row['original_generation_result'])
        if prior.get('slot_id') != old['slot_id'] or prior.get('status') != 'technical_unknown':
            raise PermissionError('Only the 21 original interrupted attempts may be independently recovered')
    return plan


def validate_second_attempt_admission(slot_id):
    rows = load(reference(PLAN_FILE))['rows']
    row = next((r for r in rows if r['slot_id'] == slot_id), None)
    if row is None or row['recovery_round'] != 2:
        raise PermissionError('Only the enumerated second recovery attempt may use this gate')
    admission = load(reference(API_ROOT/'recovery-admissions'/f"{row['slot_index']}.json"))
    previous_row = next(r for r in rows if r['slot_id'] == row['retry_of_slot_id'])
    result_ref = reference(BATCH_ROOT/'episodes'/str(previous_row['slot_index'])/'result.json')
    result = load(result_ref)
    quiet = load(result['quiescence'])
    if (admission.get('slot_id') != slot_id or admission.get('prior_slot_id') != previous_row['slot_id']
            or admission.get('prior_result') != result_ref or admission.get('technical_transient') is not True
            or admission.get('first_round_drained') is not True
            or admission.get('reason') != 'transient_transport_failure_after_first_round'
            or result.get('status') != 'technical_unknown'
            or result.get('ledger', {}).get('halted') != 'APIUncertainFailure'
            or result.get('batch_stop_required') is True
            or quiet.get('quiescent') is not True or quiet.get('all_owned_objects_removed') is not True
            or quiet.get('cleanup_errors') != []):
        raise PermissionError('A normal failure, uncertain writer or unapproved replay cannot enter attempt2')
    return admission


def validate_score_retry_admission(key):
    resource = load(reference(PLAN_FILE))['resources'][key]
    record = load(reference(API_ROOT/'score-retry-admissions'/(key+'.json')))
    if (resource.get('score_retry') is not True or record.get('resource_key') != key
            or record.get('slot_id') != resource['slot_id']
            or record.get('technical_scoring_failure') is not True
            or record.get('same_candidate') is not True
            or not isinstance(record.get('prior_request'), dict)
            or not isinstance(record.get('prior_completion'), dict)):
        raise PermissionError('Only a recorded technical scoring failure permits the same-candidate retry')
    prior_request, completion = load(record['prior_request']), load(record['prior_completion'])
    if (prior_request.get('slot_id') != resource['slot_id']
            or completion.get('status') == 'official_report'
            or completion.get('resolved') is not None):
        raise PermissionError('A normal official test failure must not be rescored')
    return record


def require_allowed(operation='v146.run', *, slot_id=None, instance_id=None, grading_only=False):
    allowed = {'v146.run','v146.api.run','v146.api.request','v146.prepare',
               'v143.run','v142.run'} | (set(original.OPERATIONS)-{'v066.model.start'})
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in allowed:
        raise PermissionError('Only this ordinary-user bounded recovery scope is admitted')
    if grading_only and operation not in {'v146.run','v143.run','v142.run','v066.run','v066.score',
            'v066.delivery.score','v066.control','v066.grader.create','v066.grader.start',
            'v066.transport','v066.resolve'}:
        raise PermissionError('Grading cannot create a generation or API call')
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'authorized_by_user_instruction'
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('user_grant') != reference(USER_GRANT_FILE)
            or auth.get('cash_authority') != reference(BUDGET_BASELINE_FILE)
            or auth.get('ledger_paths') != {g:str(p) for g,p in LEDGER_FILES.items()}
            or auth.get('API_cash_cap_CNY') != CASH_CAP_CNY
            or auth.get('constraints') != CONSTRAINTS
            or auth.get('shared_host_configuration_changes') != 0):
        raise PermissionError('Independent recovery cash or resource identity changed')
    for item in load(auth['source_index'])['files']:
        checked(item)
    plan = validate_plan(load(auth['plan']))
    if slot_id is not None:
        matches = [r for r in plan['rows'] if r['slot_id'] == slot_id]
        if len(matches) != 1 or instance_id not in (None,matches[0]['instance_id']):
            raise PermissionError('Request is outside the independent recovery panel')
        if matches[0]['recovery_round'] == 2 and operation.endswith('request'):
            validate_second_attempt_admission(slot_id)
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Foreign recovery task')
    if operation in {'v066.transport','v066.resolve'} and instance_id not in original.TLS_TASKS:
        raise PermissionError('Scoring egress is restricted to the two declared TLS tasks')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.is_file() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No live exact recovery API-owner reservation')
    # Runtime adapters consume a normalized executable authority view.  The
    # sealed record retains the actual standing/explicit user instruction basis.
    from .software_benchmark_alignment_contract_v146 import VERSION as ALIGNMENT_VERSION
    return {**auth, 'status':'approved', 'sealed_authority_status':auth['status'],
        'execution_alignment_version':ALIGNMENT_VERSION,
        'approval_represents_existing_user_authority':True}


def require_grading_allowed(operation='v146.run', **identity):
    return require_allowed(operation, grading_only=True, **identity)


