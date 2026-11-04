"""Recovery authority inside the original v131 task, cash and object envelope."""
from __future__ import annotations

import fcntl
from contextlib import closing
import os
from pathlib import Path
import resource
import sqlite3
from types import ModuleType

from . import software_benchmark_scope_v131 as prior
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace

ROOT = prior.ROOT
VERSION = 'v132-original-team-candidate-and-unused-inventory-recovery-r1'
BATCH_ROOT = prior.BATCH_ROOT
STATE_ROOT = ROOT/'runs/software-benchmark-v132/fixed-organization-recovery-r1'
API_ROOT = STATE_ROOT/'api-coordinator'
ARTIFACT_ROOT = ROOT/'artifacts/software-benchmark-v132'
PLAN_FILE = prior.PLAN_FILE
SOURCE_FILE = STATE_ROOT/'runtime-sources.json'
CONTINUATION_FILE = STATE_ROOT/'continuation.json'
DRAIN_FILE = STATE_ROOT/'admission-control.json'
PROPOSAL_FILE = ARTIFACT_ROOT/'recovery-authorization-r1/proposal.json'
AUTH_FILE = ROOT/'config/v132-fixed-organization-recovery-authorization.json'
USER_GRANT_FILE = ROOT/'config/v132-controlled-handoff-user-grant.json'
GRADING_ROOT = ROOT/'runs/software-benchmark-v132/grading-recovery-r1/grading'
COORDINATOR_ROOT = ROOT/'runs/software-benchmark-v132/grading-recovery-r1/coordinator'
CLAIM_FILE = API_ROOT/'coordinator-capacity.json'
LEASE_FILE = BATCH_ROOT/'resource-claims/active-v132-coordinator.json'
CPU_POOL_FILE = prior.CPU_POOL_FILE
LEDGER_FILES = prior.LEDGER_FILES
GROUP_IDS = prior.GROUP_IDS
CONSTRAINTS = prior.CONSTRAINTS
API_UNIT = prior.API_UNIT
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 32*prior.GIB, 30*prior.GIB
MAX_GENERATIONS, MAX_STARTUPS, MAX_GRADERS = 48, 8, 2
MANAGER_CPUS, NOFILE = 8, 16384
CONTAINER_PARENT = prior.CONTAINER_PARENT
PREPARATION_QUALIFICATION_FILE = prior.PREPARATION_QUALIFICATION_FILE
NETWORK_RESOLUTION_FILE = prior.NETWORK_RESOLUTION_FILE
CA_PROFILE_FILE = prior.CA_PROFILE_FILE
ResourceBusy = prior.ResourceBusy
load, retain, validate_plan = prior.load, prior.retain, prior.validate_plan
host_cpu_pool, cpu_set = prior.host_cpu_pool, prior.cpu_set
GIB = prior.GIB


def never_consumed(row):
    """A new first attempt needs both unused physical identity and zero billing."""
    if (BATCH_ROOT/'episodes'/str(row['slot_index'])).exists():
        return False
    for role in ('actor', 'controller', 'volume'):
        if (BATCH_ROOT/'resource-claims'/f"{role}-{row['slot_index']}.json").exists():
            return False
    path = LEDGER_FILES[row['organization_id']]
    with closing(sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)) as db:
        return db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1', (row['slot_id'],)).fetchone() is None


def continuation():
    value = load(reference(CONTINUATION_FILE))
    if value.get('original_plan') != reference(PLAN_FILE):
        raise PermissionError('Recovery must use the unchanged original250 identities')
    original = {row['slot_id']: row for row in validate_plan(load(reference(PLAN_FILE)))['rows']}
    rows = value.get('eligible_first_generation', [])
    if (len({row['slot_id'] for row in rows}) != len(rows)
            or any(original.get(row['slot_id']) != row for row in rows)):
        raise PermissionError('Unused inventory changed task, seed, budget or original identity')
    return value


def verify_host_limits(role='api'):
    groups = [line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')]
    if role != 'api' or len(groups) != 1 or Path(groups[0]).name != API_UNIT:
        raise PermissionError('Only the original ordinary-user unit in its new lifecycle may coordinate recovery')
    folder = Path('/sys/fs/cgroup')/groups[0].lstrip('/')
    limits = {key: (folder/key).read_text().strip()
              for key in ('memory.max', 'memory.high', 'memory.swap.max', 'pids.max')}
    expected = {'memory.max': str(API_MEMORY_BYTES), 'memory.high': str(API_MEMORY_HIGH_BYTES),
                'memory.swap.max': '0', 'pids.max': '512'}
    if (limits != expected or sorted(os.sched_getaffinity(0)) != host_cpu_pool()[:8]
            or resource.getrlimit(resource.RLIMIT_NOFILE)[0] < NOFILE):
        raise PermissionError('Recovery manager exceeds or differs from its reviewed bounded profile')
    return {'uid': os.getuid(), 'cgroup': groups[0], 'limits': limits,
            'cpu_affinity': sorted(os.sched_getaffinity(0)), 'nofile': resource.getrlimit(resource.RLIMIT_NOFILE)[0]}


def require_allowed(operation='v132.run', *, slot_id=None, instance_id=None, grading_only=False):
    # Reuse the concrete original Docker, data, networking and parent grant.
    # Do not call the old API-request guard: it deliberately pins the old24G high.
    original_auth = prior.require_grading_allowed('v131.run')
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('No root coordination or host configuration mutation')
    allowed = {'v132.run', 'v132.prepare', 'v132.api.run', 'v132.api.request',
               'v131.run', 'v131.api.run', 'v131.api.request'} | (set(prior.original.OPERATIONS)-{'v066.model.start'})
    if operation not in allowed:
        raise PermissionError('Operation outside original bounded recovery authority')
    auth = load(reference(AUTH_FILE))
    grant = load(reference(USER_GRANT_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or grant.get('user_reply') != '授权受控停止并交接修复' or grant.get('status') != 'approved'
            or auth.get('original_authorization') != reference(prior.AUTH_FILE)
            or auth.get('user_grant') != reference(USER_GRANT_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('proposal') != reference(PROPOSAL_FILE)
            or auth.get('continuation') != reference(CONTINUATION_FILE)
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('constraints') != CONSTRAINTS
            or auth.get('new_model_retries') != 0):
        raise PermissionError('Recovery scope, original cash, tasks or explicit handoff consent changed')
    for item in load(auth['source_index'])['files']:
        checked(item)
    plan = validate_plan(load(auth['plan']))
    if slot_id is not None:
        matches = [row for row in plan['rows'] if row['slot_id'] == slot_id]
        if len(matches) != 1 or instance_id not in (None, matches[0]['instance_id']):
            raise PermissionError('Foreign task identity')
        generation = operation.endswith('request') or operation in {
            'v066.actor.create', 'v066.controller.create', 'v066.volume.create'}
        if generation and slot_id not in {row['slot_id'] for row in continuation()['eligible_first_generation']}:
            raise PermissionError('Already-entered tasks cannot be silently resampled')
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Foreign environment identity')
    if grading_only and (operation.endswith('request') or '.actor.' in operation or '.controller.' in operation):
        raise PermissionError('Scoring cannot generate new model work')
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.exists() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No exact live recovery coordinator owner')
    return {**auth, 'execution_alignment_version': original_auth['execution_alignment_version']}


def require_grading_allowed(operation='v132.run', **identity):
    return require_allowed(operation, grading_only=True, **identity)


def dispatch_view(guard=None):
    guard = guard or require_allowed
    namespace = clone_namespace(prior.original, VERSION=VERSION, BATCH_ROOT=BATCH_ROOT,
        PLAN_FILE=PLAN_FILE, RESUME_FILE=CONTINUATION_FILE, SOURCE_INDEX_FILE=SOURCE_FILE,
        CPU_POOL_FILE=CPU_POOL_FILE, GRADING_ROOT=GRADING_ROOT,
        COORDINATOR_RUN_ROOT=COORDINATOR_ROOT, AUTHORIZATION_FILE=AUTH_FILE,
        CONSTRAINTS=CONSTRAINTS, __file__=__file__)

    def allowed(operation='v066.run', **identity):
        value = guard(operation, **identity)
        return {**value, 'plan': reference(PLAN_FILE), 'sources': reference(SOURCE_FILE), 'constraints': CONSTRAINTS}

    namespace.update(require_v066_allowed=allowed, host_cpu_pool=host_cpu_pool,
                     cpu_set=cpu_set, _budget=prior._budget)
    module = ModuleType(__name__+'.dispatch')
    module.__dict__.update(namespace)
    return module


def reserve_api_coordinator():
    require_allowed()
    if prior.LEASE_FILE.exists() or not (prior.API_ROOT/'coordinator-capacity-released.json').exists():
        raise PermissionError('The original coordinator has not released ownership')
    # The sealed stop proof records inactive service and original process absence.
    stopped = load(continuation()['original_owner_stopped'])
    if stopped.get('original_owner_absent') is not True or stopped.get('original_unit_inactive') is not True:
        raise PermissionError('Original lifecycle quiescence was not established')
    CLAIM_FILE.parent.mkdir(parents=True, exist_ok=True)
    with (LEASE_FILE.parent/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CLAIM_FILE.exists():
            if LEASE_FILE.exists() and LEASE_FILE.read_bytes() == checked(reference(CLAIM_FILE)).read_bytes():
                return reference(CLAIM_FILE)
            raise PermissionError('A consumed recovery owner identity cannot restart')
        if LEASE_FILE.exists() or prior.LEASE_FILE.exists():
            raise PermissionError('Another coordinator owner exists')
        value = {'version': VERSION, 'key': 'v132-api-coordinator',
            'spec': {'role': 'auxiliary_coordinator', 'unit': API_UNIT},
            'reserved_cpu': MANAGER_CPUS, 'reserved_memory_bytes': API_MEMORY_BYTES,
            'reserved_spool_bytes': 0, 'lease': str(LEASE_FILE), 'authorization': reference(AUTH_FILE)}
        raw = prior.original._write_claim(CLAIM_FILE, value)
        with LEASE_FILE.open('xb') as stream:
            stream.write(raw)
    return reference(CLAIM_FILE)


def release_api_coordinator(claim_ref):
    value = load(claim_ref)
    if Path(claim_ref['path']).resolve() != CLAIM_FILE or value.get('lease') != str(LEASE_FILE):
        raise PermissionError('Foreign recovery owner')
    with (LEASE_FILE.parent/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if LEASE_FILE.exists():
            if LEASE_FILE.read_bytes() != checked(claim_ref).read_bytes():
                raise PermissionError('Owner identity changed')
            LEASE_FILE.unlink()
    return write_new(API_ROOT/'coordinator-capacity-released.json', {'claim': claim_ref, 'released': True})
