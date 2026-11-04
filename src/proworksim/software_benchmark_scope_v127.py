"""One preserved Requests-1921 candidate score; no generation or service scope."""
from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_scope_v125 as prior
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace

ROOT = original.ROOT
VERSION = 'v127-preserved-requests1921-score-scope-r1'
TASK = 'psf__requests-1921'
RESOURCE_KEY = 'score-v127-7239'
BATCH_ROOT = ROOT/'runs/software-benchmark-v127/requests1921-rescore-r1'
API_ROOT = BATCH_ROOT/'coordinator'
COORDINATOR_ROOT = BATCH_ROOT/'grading-coordinator'
GRADING_ROOT = BATCH_ROOT/'grading'
PLAN_FILE = BATCH_ROOT/'execution-plan.json'
SOURCE_FILE = BATCH_ROOT/'runtime-sources.json'
INVENTORY_FILE = BATCH_ROOT/'inventory.json'
AUTH_FILE = ROOT/'config/v127-requests1921-rescore-authorization.json'
ORIGINAL_SCORE_REQUEST = prior.GRADING_ROOT/'score-7239/request.json'
ORIGINAL_REQUEST_FILE = ORIGINAL_SCORE_REQUEST
ORIGINAL_PLAN_FILE = prior.PLAN_FILE
PRIOR_OWNER_RELEASE = prior.API_ROOT/'coordinator-capacity-released.json'
PRIOR_OWNER_RELEASE_FILE = PRIOR_OWNER_RELEASE
CPU_POOL_FILE = prior.CPU_POOL_FILE
NETWORK_RESOLUTION_FILE = prior.NETWORK_RESOLUTION_FILE
CA_PROFILE_FILE = prior.CA_PROFILE_FILE
GIB = 1024**3
MAX_GENERATIONS, MAX_GRADERS = 0, 1
HOST_MEMORY_BYTES = 4*GIB
SUPERVISOR_MEMORY_BYTES = 4*GIB
TOTAL_MEMORY_BYTES = 16*GIB+HOST_MEMORY_BYTES+SUPERVISOR_MEMORY_BYTES
ResourceBusy = original.ResourceBusy
OPERATIONS = frozenset({'v127.run', 'v066.run', 'v066.score', 'v066.grader.create',
    'v066.grader.start', 'v066.transport', 'v066.resolve'})
CONSTRAINTS = {**original.CONSTRAINTS,
    'fresh_generation_slots': 0, 'generation_token_upper_bound': 0,
    'api_generation_token_upper_bound': 0, 'api_total_budget_cny': '0',
    'maximum_actor_containers': 0, 'maximum_controller_containers': 0,
    'maximum_control_containers': 0, 'maximum_code_score_containers': 1,
    'maximum_delivery_score_containers': 0, 'maximum_score_containers': 1,
    'maximum_containers': 1, 'maximum_named_volumes': 0, 'maximum_model_residents': 0,
    'neutral_model_preparation_calls': 0, 'neutral_model_preparation_total_tokens': 0,
    'api_neutral_preparation_calls': 0, 'api_neutral_preparation_total_tokens': 0,
    'free_api_metadata_requests': 0, 'new_owned_user_units': [], 'physical_gpus': [],
    'active_actor_limit': 0, 'active_controller_limit': 0, 'active_grader_limit': 1,
    'maximum_active_generation_episodes': 0, 'maximum_active_containers': 1,
    'maximum_combined_reserved_cpu': 4, 'maximum_combined_reserved_memory_bytes': TOTAL_MEMORY_BYTES,
    'grader_cpu': 4, 'grader_memory_bytes': 16*GIB,
    'ordinary_host_process_memory_bytes': HOST_MEMORY_BYTES,
    'maximum_ordinary_host_processes': 2,
    'supervisor_memory_bytes': SUPERVISOR_MEMORY_BYTES,
    'scorer_host_process_memory_bytes': HOST_MEMORY_BYTES,
    'host_and_container_share_same_four_CPUs': True,
    'memory_minimum_free_bytes': 64*GIB, 'disk_minimum_free_bytes': 128*GIB,
    'container_network': 'none', 'container_cap_drop': ['ALL'],
    'container_cap_add': ['NET_ADMIN', 'NET_BIND_SERVICE'],
    'model_api_network': 'disabled', 'named_volumes': 'none',
    'maximum_real_tls_sessions': 1, 'real_tls_max_connections': 512,
    'real_tls_all_sessions_payload_bytes': 64*1024**2,
    'new_model_calls_for_preparation': 0, 'automatic_replay': False,
    'host_namespaces_or_mount_configuration_changed': False,
}


def load(ref):
    return original._cached_json(ref)


def retain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if load(reference(path)) != value:
            raise ValueError('Prepared v127 identity changed: '+str(path))
        return reference(path)
    return write_new(path, value)


def host_cpu_pool():
    value = load(reference(CPU_POOL_FILE))
    pool = value['cpu_ids']
    if (value.get('uid') != os.getuid() or len(pool) < 32
            or len(set(pool)) != len(pool) or any(type(cpu) is not int or cpu < 0 for cpu in pool)):
        raise ValueError('Use the frozen original CPU inventory')
    return pool


def cpu_set(role, index=0):
    if role not in {'grader', 'coordinator'} or index != 0:
        raise ValueError('Only one shared four-CPU host/grader lane is admitted')
    return ','.join(map(str, host_cpu_pool()[28:32]))


def prior_owner_released():
    ref = reference(PRIOR_OWNER_RELEASE)
    proof = load(ref)
    if (proof.get('released') is not True
            or proof.get('claim') != reference(prior.API_ROOT/'coordinator-capacity.json')
            or list((prior.BATCH_ROOT/'resource-claims').glob('active-*.json'))):
        raise PermissionError('The original v125 owner has not released its resources')
    return ref


def validate_plan(plan):
    request_ref = reference(ORIGINAL_SCORE_REQUEST)
    request = load(request_ref)
    originals = load(reference(ORIGINAL_PLAN_FILE))['rows']
    rows = [row for row in originals if row['slot_index'] == 7239]
    spec = plan.get('resources', {}).get(RESOURCE_KEY, {})
    if (len(rows) != 1 or plan.get('version') != VERSION or plan.get('root') != str(BATCH_ROOT)
            or plan.get('rows') != rows or plan.get('generation_rows') != []
            or set(plan.get('environments', {})) != {TASK}
            or set(plan.get('resources', {})) != {RESOURCE_KEY}
            or spec.get('role') != 'score' or spec.get('slot_id') != rows[0]['slot_id']
            or spec.get('instance_id') != TASK or spec.get('endpoint') != 'code'
            or plan.get('resource_role_counts') != {'score': 1}
            or plan.get('constraints') != CONSTRAINTS
            or plan.get('original_score_request') != request_ref
            or plan.get('preserved_candidate_lock') != request['candidate_lock']
            or plan.get('preserved_generation_result') != request['generation_result']
            or plan.get('prior_v125_owner_release') != reference(PRIOR_OWNER_RELEASE)
            or plan.get('score_request_path') != str(GRADING_ROOT/RESOURCE_KEY/'request.json')):
        raise PermissionError('Only the unchanged original Requests-1921 candidate may be rescored')
    return plan


def require_allowed(operation='v127.run', *, slot_id=None, instance_id=None, grading_only=False):
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in OPERATIONS:
        raise PermissionError('Only the single ordinary-user managed scoring operation is admitted')
    auth = load(reference(AUTH_FILE))
    plan = validate_plan(load(reference(PLAN_FILE)))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('constraints') != CONSTRAINTS or auth.get('maximum_containers') != 1
            or auth.get('maximum_named_volumes') != 0 or auth.get('model_calls') != 0
            or auth.get('shared_host_configuration_changes') != 0
            or any(auth.get(key) != plan[key] for key in (
                'original_score_request', 'preserved_candidate_lock', 'prior_v125_owner_release'))):
        raise PermissionError('The single-score authorization differs from its sealed proposal')
    prior_owner_released()
    row = plan['rows'][0]
    if slot_id not in (None, row['slot_id']) or instance_id not in (None, TASK):
        raise PermissionError('A request is outside the single retained candidate')
    for item in load(auth['source_index'])['files']:
        checked(item)
    return auth


def require_grading_allowed(operation='v127.run', **identity):
    return require_allowed(operation, grading_only=True, **identity)


def _budget(active, cpu, memory, spool=0):
    if active or cpu != 4 or memory != 16*GIB or spool != 0:
        raise ResourceBusy('Only one exact grader reservation is allowed')
    capacity = dispatch_view().physical_capacity()
    if (capacity['memory_available_bytes'] < CONSTRAINTS['memory_minimum_free_bytes']+TOTAL_MEMORY_BYTES
            or capacity['disk_free_bytes'] < CONSTRAINTS['disk_minimum_free_bytes']):
        raise ResourceBusy('Shared-host headroom is insufficient for this one score')
    return {'reserved_cpu_after': 4, 'reserved_memory_bytes_after': TOTAL_MEMORY_BYTES,
            'reserved_payload_spool_bytes_after': 0, 'physical_at_admission': capacity,
            'spool_is_filesystem_quota': False}


def dispatch_view(guard=None):
    guard = guard or require_grading_allowed
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
