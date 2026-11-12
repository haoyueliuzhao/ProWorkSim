"""Two ordinary-user Requests controls sharing the active r2 grader allocator."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from types import ModuleType

from . import software_benchmark_scope_v203_2_1_r2 as parent
from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace

ROOT = parent.ROOT
VERSION = 'v203.2.1-independent-requests2317-CA-controls-r3'
TASK = 'psf__requests-2317'
BATCH_ROOT = ROOT / 'runs/software-benchmark-v203-2-1/requests2317-ca-controls-r3'
GRADING_ROOT = BATCH_ROOT / 'grading'
COORDINATOR_ROOT = BATCH_ROOT / 'coordinator'
PLAN_FILE = BATCH_ROOT / 'plan.json'
SOURCE_FILE = BATCH_ROOT / 'sources.json'
AUTH_FILE = BATCH_ROOT / 'authorization.json'
CPU_POOL_FILE = parent.CPU_POOL_FILE
SHARED_CLAIM_ROOT = parent.BATCH_ROOT / 'resource-claims'
ARTIFACT_ROOT = ROOT / 'artifacts/software-benchmark-v203-2-1/requests2317-ca-r3'
GIB = 1024 ** 3
ResourceBusy = original.ResourceBusy
CONSTRAINTS = {**parent.CONSTRAINTS,
    'maximum_containers': 2, 'maximum_control_containers': 2, 'maximum_named_volumes': 0,
    'fresh_generation_slots': 0, 'generation_token_upper_bound': 0, 'api_generation_token_upper_bound': 0,
    'maximum_active_generation_episodes': 0, 'maximum_active_containers': 1, 'maximum_model_residents': 0,
    'new_owned_user_units': [], 'maximum_code_score_containers': 0, 'maximum_delivery_score_containers': 0,
    'maximum_score_containers': 0, 'maximum_actor_containers': 0, 'maximum_controller_containers': 0,
    'model_API_calls': 0, 'maximum_concurrent_new_controls': 1,
    'shared_parent_allocation_lock': str(SHARED_CLAIM_ROOT / 'allocation.lock'),
    'shared_parent_grader_lanes': 2, 'parent_budget_limits_unchanged': True,
    'reserved_memory_per_control_including_runner': 17 * GIB,
    'host_runner_and_scorer_share_own_grader_CPU_lane': True,
    'new_service_or_parent_slice': False, 'external_network': False,
    'private_CA_addition': 'existing private httpbin CA appended to original source/installed Requests roots'}


def load(ref):
    return json.loads(checked(ref).read_bytes())


def retain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if load(reference(path)) != value:
            raise ValueError('Immutable r3 preparation changed')
        return reference(path)
    return write_new(path, value)


def cpu_set(role, index=0):
    if role != 'grader' or index not in (0, 1):
        raise ValueError('r3 may use only the two shared r2 grader lanes')
    return parent.cpu_set('grader', index)


def validate_plan(plan):
    keys = {'control-' + TASK + '-' + kind for kind in ('gold', 'empty')}
    if (plan.get('version') != VERSION or plan.get('root') != str(BATCH_ROOT)
            or set(plan.get('resources', {})) != keys or set(plan.get('environments', {})) != {TASK}
            or plan.get('rows') != [] or plan.get('constraints') != CONSTRAINTS
            or plan.get('parent_plan') != reference(parent.PLAN_FILE)):
        raise ValueError('Only two exact independent Requests2317 control identities are permitted')
    for key, item in plan['resources'].items():
        if item.get('role') != 'control' or item.get('instance_id') != TASK or key != 'control-' + TASK + '-' + item.get('patch_kind', ''):
            raise ValueError('A control resource changed task or patch identity')
    return plan


def require_allowed(operation='v203.2.1.ca-controls', *, slot_id=None, instance_id=None):
    allowed = {'v203.2.1.ca-controls', 'v066.run', 'v066.control', 'v066.grader.create', 'v066.grader.start'}
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in allowed or slot_id is not None or instance_id not in (None, TASK):
        raise PermissionError('r3 is ordinary-user scoring-only; no model, actor or network operation')
    auth = load(reference(AUTH_FILE))
    if (auth.get('status') != 'approved' or auth.get('version') != VERSION
            or auth.get('plan') != reference(PLAN_FILE) or auth.get('sources') != reference(SOURCE_FILE)
            or auth.get('constraints') != CONSTRAINTS):
        raise PermissionError('Independent r3 control scope is not sealed')
    for entry in load(auth['sources'])['files']:
        checked(entry)
    validate_plan(load(auth['plan']))
    parent.require_allowed('v066.run', instance_id=TASK)
    return auth


require_grading_allowed = require_allowed


def claim_resource(key, *, lane=None):
    auth = require_allowed()
    plan = validate_plan(load(auth['plan']))
    if key not in plan['resources']:
        raise ValueError('Foreign r3 resource')
    own = BATCH_ROOT / 'resource-claims'
    own.mkdir(parents=True, exist_ok=True)
    SHARED_CLAIM_ROOT.mkdir(parents=True, exist_ok=True)
    with (SHARED_CLAIM_ROOT / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        claim = own / (key + '.json')
        if claim.exists():
            raise ValueError('Consumed r3 control identity cannot replay')
        active = [load(reference(path)) for path in SHARED_CLAIM_ROOT.glob('active-*.json')]
        if any(item.get('version') == VERSION for item in active):
            raise ResourceBusy('r3 controls are serialized')
        lanes = (0, 1) if lane is None else (lane,)
        if any(number not in (0, 1) for number in lanes):
            raise ValueError('Foreign shared grading lane')
        selected = next((number for number in lanes if not (SHARED_CLAIM_ROOT / f'active-grader-{number}.json').exists()), None)
        if selected is None:
            raise ResourceBusy('The active r2/r3 shared grader lanes are occupied')
        # Under the parent's exact allocation lock, include all of its active
        # actor pairs/scorers and reserve one extra GiB for the small r3 runner.
        admission = parent._budget(active, 4, 17 * GIB, 0)
        lease = SHARED_CLAIM_ROOT / f'active-grader-{selected}.json'
        value = {'version': VERSION, 'key': key, 'spec': plan['resources'][key],
                 'authorization': reference(AUTH_FILE), 'plan': auth['plan'], 'lease': str(lease),
                 'lane': selected, 'reserved_cpu': 4, 'reserved_memory_bytes': 17 * GIB,
                 'reserved_spool_bytes': 0, 'parent_actor_key': None, 'admission': admission,
                 'docker_name': 'pws-v066-' + hashlib.sha256((str(BATCH_ROOT) + ':' + key).encode()).hexdigest()[:24]}
        raw = original._write_claim(claim, value)
        with lease.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return reference(claim)


def release_resource(claim_ref, *, quiescent):
    if quiescent is not True:
        return False
    value = load(claim_ref)
    own = (BATCH_ROOT / 'resource-claims').resolve()
    if (Path(claim_ref['path']).resolve() != own / (value['key'] + '.json') or value['version'] != VERSION
            or value['key'] not in validate_plan(load(reference(PLAN_FILE)))['resources']):
        raise ValueError('Foreign r3 claim')
    lease = Path(value['lease'])
    if lease != SHARED_CLAIM_ROOT / f"active-grader-{value['lane']}.json":
        raise ValueError('Foreign shared capacity lease')
    with (SHARED_CLAIM_ROOT / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if lease.exists():
            if lease.read_bytes() != checked(claim_ref).read_bytes():
                raise ValueError('Another job owns this shared capacity lane')
            lease.unlink()
        retain(own / (value['key'] + '.released.json'), {'version': VERSION, 'claim': claim_ref, 'quiescent': True})
    return True


def dispatch_view(guard=None):
    authorize = guard or require_allowed
    namespace = clone_namespace(original, VERSION=VERSION, BATCH_ROOT=BATCH_ROOT,
        PLAN_FILE=PLAN_FILE, SOURCE_INDEX_FILE=SOURCE_FILE, AUTHORIZATION_FILE=AUTH_FILE,
        GRADING_ROOT=GRADING_ROOT, COORDINATOR_RUN_ROOT=COORDINATOR_ROOT,
        CONSTRAINTS=CONSTRAINTS, CPU_POOL_FILE=CPU_POOL_FILE, __file__=__file__)
    def allowed(operation='v066.run', **identity):
        value = authorize(operation, **identity)
        return {**value, 'plan': reference(PLAN_FILE), 'sources': reference(SOURCE_FILE), 'constraints': CONSTRAINTS}
    namespace.update(require_v066_allowed=allowed, claim_resource=claim_resource, release_resource=release_resource,
                     cpu_set=cpu_set, host_cpu_pool=parent.host_cpu_pool)
    module = ModuleType(__name__ + '.private_dispatch')
    module.__dict__.update(namespace)
    return module
