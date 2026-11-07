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
from .software_benchmark_alignment_contract_v141 import GROUP_IDS, validate_plan_identity

ROOT = original.ROOT
VERSION = 'v143-three-role-baselines-scope-r1'
BATCH_ROOT = previous.BATCH_ROOT
STATE_ROOT = BATCH_ROOT/'deployment-v143'
ARTIFACT_ROOT = ROOT/'artifacts/software-benchmark-v143'
API_ROOT = STATE_ROOT/'api-coordinator'
COORDINATOR_ROOT = STATE_ROOT/'grading-coordinator'
GRADING_ROOT = STATE_ROOT/'grading'
PLAN_FILE = STATE_ROOT/'execution-plan.json'
INVENTORY_FILE = STATE_ROOT/'inventory.json'
SOURCE_FILE = STATE_ROOT/'runtime-sources.json'
CPU_POOL_FILE = previous.CPU_POOL_FILE
AUTH_FILE = ROOT/'config/v143-role-pilot-authorization.json'
PROPOSAL_FILE = ARTIFACT_ROOT/'runtime-authorization-r1/proposal.json'
USER_GRANT_FILE = ROOT/'config/v143-role-pilot-user-grant.json'
NETWORK_RESOLUTION_FILE = previous.NETWORK_RESOLUTION_FILE
NETWORK_SCOPE_MAPPING_FILE = STATE_ROOT/'network-scope-equivalence.json'
STANDING_POLICY_FILE = ROOT/'config/v143-standing-docker-user-policy.json'
STANDING_PERMISSION_FILE = STANDING_POLICY_FILE
PRIOR_COMPLETION_FILE = STATE_ROOT/'predecessor-completion.json'
CA_PROFILE_FILE = ROOT/'runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json'
PREPARATION_QUALIFICATION_FILE = API_ROOT/'preparation-qualification.json'
PANEL_FILE = previous.PANEL_FILE
SOURCE_PANEL_FILE = ROOT/'artifacts/software-benchmark-v118/preparation-r1/panel.json'
SOURCE_PLAN_FILE = ROOT/'runs/software-benchmark-v118/project-repaired-r1/execution-plan-v119.json'
LEDGER_FILE = BATCH_ROOT/'ledgers/pilot.sqlite'
LEDGER_FILES = {group: LEDGER_FILE for group in GROUP_IDS}
BUDGET_BASELINE_FILE = previous.BUDGET_BASELINE_FILE
CASH_MODE = 'one_new_CNY400_pilot_ledger_attributed_by_group_member'
CASH_CAP_CNY = '400.00'
API_UNIT = previous.API_UNIT
CLAIM_FILE = API_ROOT/'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT/'resource-claims/active-v143-coordinator.json'
GIB = 1024**3
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*GIB, 30*GIB
MAX_GENERATIONS, MAX_GRADERS, MANAGER_CPUS, NOFILE = 16, 2, 8, 16384
MAX_STARTUPS = 4
CONTAINER_PARENT = None
FIRST_PHYSICAL_INDEX, LAST_PHYSICAL_INDEX, DIAGNOSTIC_INDEX = 10000, 10119, 5
ResourceBusy = original.ResourceBusy
CONSTRAINTS = {**original.CONSTRAINTS,
    'fresh_generation_slots': 120, 'generation_token_upper_bound': 600_000_000,
    'api_generation_token_upper_bound': 600_000_000, 'api_total_budget_cny': CASH_CAP_CNY,
    'api_budget_shared_across_groups': True,
    'cash_budget_scope': CASH_MODE, 'old_ledgers_untouched': True,
    'maximum_actor_containers': 125, 'maximum_controller_containers': 125,
    'maximum_control_containers': 80, 'maximum_code_score_containers': 120,
    'maximum_delivery_score_containers': 120, 'maximum_score_containers': 240,
    'maximum_containers': 570, 'maximum_named_volumes': 125,
    'zero_model_diagnostic_pairs': 5, 'initial_zero_model_diagnostic_pairs': 4,
    'conditional_zero_model_repair_pairs': 1, 'maximum_model_residents': 0,
    'neutral_model_preparation_calls': 0, 'neutral_model_preparation_total_tokens': 0,
    'api_neutral_preparation_calls': 0, 'api_neutral_preparation_total_tokens': 0,
    'free_api_metadata_requests': 0, 'new_owned_user_units': [API_UNIT],
    'maximum_combined_reserved_cpu': 112, 'maximum_combined_reserved_memory_bytes': 840*GIB,
    'host_grading_process_memory_bytes': 4*GIB, 'host_grading_cpu_shared_with_own_container': True,
    'maximum_concurrent_startups':MAX_STARTUPS,
    'coordinator_memory_bytes': API_MEMORY_BYTES, 'coordinator_cpu_quota_percent': 800,
    'active_actor_limit': MAX_GENERATIONS, 'active_controller_limit': MAX_GENERATIONS,
    'active_grader_limit': MAX_GRADERS, 'maximum_active_generation_episodes': MAX_GENERATIONS,
    'generation_pair_reserved_cpu': 6, 'generation_pair_reserved_memory_bytes': 48*GIB,
    'actor_cpu': 4, 'actor_memory_bytes': 16*GIB, 'controller_cpu': 2, 'controller_memory_bytes': 32*GIB,
    'grader_cpu': 4, 'grader_memory_bytes': 16*GIB,
    'maximum_active_containers': 34, 'memory_minimum_free_bytes': 64*GIB,
    'disk_minimum_free_bytes': 128*GIB, 'maximum_real_tls_sessions': 16,
    'real_tls_all_sessions_payload_bytes': 1024*1024**2,
    'real_tls_all_sessions_connections': 8192, 'real_tls_session_connections': 512,
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
        if key in {f'diagnostic-1-{role}' for role in ('actor','controller','volume')}:
            raise PermissionError('The consumed v142 diagnostic identity remains permanently closed')
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
        value = {'version': VERSION, 'key': 'v143-api-coordinator',
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

def recovery_plan():
    """Return an exact metadata revision; create/launch nothing."""
    old_ref = reference(previous.PLAN_FILE)
    old = previous.validate_plan(load(old_ref))
    value = copy.deepcopy(old)
    resources = value['resources']
    for role in ('actor','controller','volume'):
        resources[f'diagnostic-5-{role}'] = {**resources[f'diagnostic-1-{role}'],
            'diagnostic_index': 5, 'replaces_zero_model_resource': f'diagnostic-1-{role}'}
    diagnostics = copy.deepcopy(old['diagnostics'])
    diagnostics[0].update(index=5, replaces_diagnostic_index=1)
    value.update(version=VERSION, previous_plan=old_ref, deployment_root=str(STATE_ROOT),
        constraints=CONSTRAINTS, diagnostics=diagnostics,
        resource_role_counts=dict(Counter(row['role'] for row in resources.values())),
        retained_consumed_diagnostic_indices=[1], additional_model_attempts=0,
        original120_identity_seed_configuration_and_cash_cap_unchanged=True,
        deployment_amendment='Replace zero-model failed diagnostic1 withnew diagnostic5; retain2/3/4')
    return value


def validate_plan(plan):
    if plan != recovery_plan():
        raise PermissionError('Recovery must preserve the exact original120 attempts and add only diagnostic5')
    expected = {'actor':125, 'controller':125, 'volume':125, 'score':120, 'delivery_score':120, 'control':80}
    if plan['resource_role_counts'] != expected:
        raise PermissionError('The cumulative owned-resource ceiling changed')
    for row in plan['rows']:
        validate_plan_identity(row)
    return plan


def prior_zero_model_cleanup():
    result_ref = reference(BATCH_ROOT/'diagnostic-1/result.json')
    result = load(result_ref)
    quiet = load(result['quiescence'])
    final_ref = reference(previous.API_ROOT/'coordinator-finalization.json')
    final = load(final_ref)
    released = load(final['coordinator_release'])
    if (result.get('model_calls') != 0 or result.get('model_dispatch_started') is not False
            or result.get('measurement_kind') != 'zero_model_diagnostic'
            or quiet.get('quiescent') is not True or quiet.get('all_owned_objects_removed') is not True
            or quiet.get('cleanup_errors') != [] or quiet.get('create_result_unknown') is not False
            or final.get('cleanup_errors') != [] or released.get('released') is not True):
        raise PermissionError('Original zero-model attempt or owned-resource cleanup is unproven')
    return {'failed_diagnostic': result_ref, 'diagnostic_quiescence': result['quiescence'],
            'coordinator_finalization': final_ref, 'coordinator_release': final['coordinator_release'],
            'original_model_calls': 0, 'additional_model_attempts': 0}


def validate_authority_basis(auth):
    """Do not relabel a standing instruction as approval of a new proposal."""
    grant = load(auth['user_grant'])
    original_ref = reference(previous.USER_GRANT_FILE)
    original = load(original_ref)
    permission_ref = reference(STANDING_PERMISSION_FILE)
    permission = load(permission_ref)
    if (Path(auth['user_grant']['path']).resolve() != USER_GRANT_FILE.resolve()
            or grant.get('status') != 'authorized_by_existing_instructions'
            or grant.get('explicit_new_proposal_user_approval') is not False
            or grant.get('original_user_grant') != original_ref
            or grant.get('standing_docker_permission') != permission_ref
            or grant.get('deployment_amendment') != reference(PROPOSAL_FILE)
            or grant.get('additional_model_attempts') != 0
            or original.get('status') != 'approved' or original.get('proposal') != reference(previous.PROPOSAL_FILE)
            or permission.get('record_kind') != 'standing_user_instruction'
            or permission.get('experimental_docker_without_disruption') is not True
            or permission.get('shared_server_or_other_users_may_be_affected') is not False
            or permission.get('other_root_operations_authorized') is not False):
        raise PermissionError('Recovery authority must cite the original grant and actual standing instruction')
    if auth.get('previous_zero_model_cleanup') != prior_zero_model_cleanup():
        raise PermissionError('Recovery lacks original stopped-owner and zero-model cleanup evidence')
    return grant


def original_probe_mapping():
    """Describe the already completed probe, without claiming a new test."""
    from .software_benchmark_environment_v141 import validate_resolution
    old_scope = reference(previous.__file__)
    resolution_ref = reference(previous.NETWORK_RESOLUTION_FILE)
    resolved = validate_resolution(resolution_ref, scope_ref=old_scope,
        expected_source='v142_current_DNS_and_bounded_endpoint_probe')
    diagnostic_ref = reference(previous.ARTIFACT_ROOT/'httpbin-direct-diagnostic-r1.json')
    diagnostic = load(diagnostic_ref)
    if (resolved.get('diagnostic') != diagnostic_ref or diagnostic.get('passed') is not True
            or diagnostic.get('scope') != old_scope or diagnostic.get('proxy_used') is not False
            or diagnostic.get('maximum_connections') != 4 or len(diagnostic.get('probes', [])) > 4
            or diagnostic.get('maximum_application_bytes') != 65536
            or diagnostic.get('source') != reference(ROOT/'tools/check_httpbin_direct_v142.py')):
        raise PermissionError('Only this completed bounded direct probe can support the recovery endpoint')
    plan = validate_plan(load(reference(PLAN_FILE)))
    old_plan = load(reference(previous.PLAN_FILE))
    if plan['environments'] != old_plan['environments'] or CA_PROFILE_FILE != previous.CA_PROFILE_FILE:
        raise PermissionError('Probe reuse cannot change task images or the approved scoring CA profile')
    return {'version':'v143-explicit-original-probe-scope-equivalence-r1',
        'original_scope':old_scope, 'current_scope':reference(__file__),
        'original_probe':diagnostic_ref, 'original_resolution':resolution_ref,
        'original_plan':reference(previous.PLAN_FILE), 'current_plan':reference(PLAN_FILE),
        'same_CA_profile':reference(CA_PROFILE_FILE), 'selected_ip':resolved['selected_ip'],
        'hostname':resolved['hostname'], 'ports':resolved['ports'],
        'probe_reexecuted':False, 'probe_scope_relabelled':False, 'new_network_connections':0,
        'same_task_images_CA_and_numeric_endpoint':True, 'container_gold_empty_qualification_complete':False}


def validate_original_probe_reuse():
    expected = original_probe_mapping()
    mapping_ref = reference(NETWORK_SCOPE_MAPPING_FILE)
    if load(mapping_ref) != expected:
        raise PermissionError('The explicit original-scope to recovery-scope endpoint proof changed')
    return {'version':expected['version'], 'passed':True,
        'references':[expected['original_probe'],expected['original_resolution'],mapping_ref],
        'selected_ip':expected['selected_ip'], 'new_network_connections':0,
        'probe_reexecuted':False, 'actual_container_qualification_pending':True}


def prepare_scope_metadata():
    """Freeze only new local recovery descriptors; no runtime operation."""
    plan = retain(PLAN_FILE, recovery_plan())
    prior = retain(PRIOR_COMPLETION_FILE, {'version':VERSION,
        **prior_zero_model_cleanup(), 'all_owned_resources_quiet':True,
        'fresh_service_inactive_check_required_at_launch':True})
    mapping = retain(NETWORK_SCOPE_MAPPING_FILE, original_probe_mapping())
    return {'plan':plan, 'predecessor':prior, 'probe_scope_mapping':mapping,
            'new_model_calls':0, 'new_Docker_operations':0, 'new_network_connections':0}


def never_consumed(row):
    validate_plan_identity(row)
    return not any((BATCH_ROOT/'resource-claims'/f"{role}-{row['slot_index']}.json").exists()
                   for role in ('actor', 'controller', 'volume'))


def require_allowed(operation='v143.run', *, slot_id=None, instance_id=None, grading_only=False):
    allowed = {'v143.run','v143.api.run','v143.api.request','v143.prepare'} | (set(original.OPERATIONS)-{'v066.model.start'})
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in allowed:
        raise PermissionError('Only the new ordinary-user role-pilot scope is admitted')
    if grading_only and operation not in {'v143.run','v066.run','v066.score','v066.delivery.score','v066.control',
            'v066.grader.create','v066.grader.start','v066.transport','v066.resolve'}:
        raise PermissionError('Grading cannot start generation or call the model')
    if not AUTH_FILE.is_file():
        raise PermissionError('Concrete v143 Docker and runtime authorization is not sealed')
    from .software_benchmark_alignment_contract_v141 import VERSION as ALIGNMENT_VERSION
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
    validate_authority_basis(auth)
    for item in load(auth['source_index'])['files']:
        checked(item)
    plan = validate_plan(load(auth['plan']))
    if slot_id is not None:
        matched = [r for r in plan['rows'] if r['slot_id'] == slot_id]
        if len(matched) != 1 or instance_id not in (None,matched[0]['instance_id']):
            raise PermissionError('Request is outside the frozen120 team attempts')
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Task is outside the selected40 panel')
    if operation in {'v066.transport','v066.resolve'} and instance_id not in original.TLS_TASKS:
        raise PermissionError('Scoring egress is limited to the two declared TLS tasks')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.is_file() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('There is no live exact v143 API owner')
    return auth


def require_grading_allowed(operation='v143.run', **identity):
    return require_allowed(operation, grading_only=True, **identity)
