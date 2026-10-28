"""A bounded API-only coordinator sharing the live v066 resource allocator.

It does not own or stop Qwen services. Its extra coordinator reservation is
visible to the original allocator under the same lock and total CPU/RAM cap.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

from . import software_benchmark_dispatch_v066 as primary
from .software_benchmark_candidates_v054 import reference, checked, write_new

ROOT = primary.ROOT
BATCH_ROOT = RUN_ROOT = ROOT / 'runs/software-benchmark-v067/api-continuation-r1'
SPEC_FILE = RUN_ROOT / 'coordinator-unit.json'
PLAN_FILE = RUN_ROOT / 'plan.json'
SOURCE_FILE = RUN_ROOT / 'runtime-sources.json'
AUTH_FILE = ROOT / 'config/v067-api-continuation-authorization.json'
PROPOSAL_FILE = ROOT / 'artifacts/software-benchmark-v067/runtime-authorization-r1/proposal.json'
UNIT = 'proworksim-v067-api-continuation.service'
VERSION = 'v067-owned-api-only-continuation-r1'
CLAIM_FILE = RUN_ROOT / 'coordinator-capacity.json'
LEASE_FILE = primary.BATCH_ROOT / 'resource-claims/active-v067-coordinator.json'
GIB = 1024**3


def load(ref):
    return json.loads(checked(ref).read_bytes())


def cpu_affinity():
    cpus = primary.host_cpu_pool()[164:168]
    if len(cpus) != 4:
        raise ValueError('The additional coordinator requires four unused declared CPU lanes')
    return cpus


def primary_cursor():
    path = primary.COORDINATOR_RUN_ROOT / 'cursor.json'
    value = json.loads(path.read_bytes())
    failure = value.get('provider_failures', {}).get('DEEPSEEK', {})
    if failure.get('reason') != 'api_initialization_unavailable':
        raise ValueError('The original API scheduler must remain independently paused')
    if value.get('failure') is not None or value.get('phase') == 'stopping':
        raise RuntimeError('The primary queue reports a shared safety stop')
    rows = {row['slot_id']: row for row in primary.load(primary.reference(primary.PLAN_FILE))['rows']}
    if any(rows[slot]['model_key'] == 'DEEPSEEK' for slot in value.get('active_generation', [])):
        raise ValueError('The primary scheduler still owns active API work')
    return value


def require_allowed(operation='v067.run', *, slot_id=None, instance_id=None):
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in {'v067.run', 'v067.api.request'}:
        raise PermissionError('Only the ordinary-user API continuation is authorized')
    primary.require_v066_allowed('v066.run')
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('primary_authorization') != reference(primary.AUTHORIZATION_FILE)
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('proposal') != reference(PROPOSAL_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)):
        raise PermissionError('The exact API-only supplement has not been approved and sealed')
    sources = load(auth['source_index'])
    for ref in sources['files']:
        checked(ref)
    plan = load(auth['plan'])
    if (plan['primary_plan'] != reference(primary.PLAN_FILE)
            or plan['API_ledger'] != str(primary.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3')
            or plan['API_total_cash_cap_CNY'] != '1500.00'
            or plan['new_model_residents'] != 0 or plan['new_environment_controls'] != 0):
        raise ValueError('The API supplement cannot change the shared task/resource/cash scope')
    if slot_id is not None:
        row = next((row for row in plan['allowed_rows'] if row['slot_id'] == slot_id), None)
        if row is None or row['model_key'] != 'DEEPSEEK' or instance_id not in (None, row['instance_id']):
            raise PermissionError('Only an original unconsumed API slot may be dispatched')
    primary_cursor()
    if operation == 'v067.api.request':
        verify_host_limits()
        if not LEASE_FILE.is_file() or not CLAIM_FILE.is_file():
            raise PermissionError('Actual API work requires the shared coordinator reservation')
        if LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise ValueError('The API coordinator reservation changed')
    return auth


def reserve_coordinator():
    require_allowed()
    directory = LEASE_FILE.parent
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CLAIM_FILE.exists():
            ref = reference(CLAIM_FILE)
            if (RUN_ROOT / 'coordinator-capacity-released.json').exists() or not LEASE_FILE.exists():
                raise ValueError('A released API coordinator identity cannot be restarted')
            if LEASE_FILE.read_bytes() != checked(ref).read_bytes():
                raise ValueError('The existing shared reservation belongs to another object')
            return ref
        if LEASE_FILE.exists():
            raise ValueError('An existing shared lease without this owned claim cannot be adopted')
        active = [primary.load(primary.reference(path)) for path in directory.glob('active-*.json')]
        admitted = primary._budget(active, 4, 16 * GIB)
        value = {'version': VERSION, 'key': 'v067-api-coordinator',
            'spec': {'role': 'auxiliary_coordinator', 'unit': UNIT}, 'lane': None,
            'reserved_cpu': 4, 'reserved_memory_bytes': 16 * GIB, 'reserved_spool_bytes': 0,
            'admission': admitted, 'lease': str(LEASE_FILE), 'authorization': reference(AUTH_FILE),
            'plan': reference(PLAN_FILE), 'cpu_affinity': cpu_affinity(),
            'primary_model_units_owned': False}
        CLAIM_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = primary._write_claim(CLAIM_FILE, value)
        with LEASE_FILE.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return reference(CLAIM_FILE)


def release_coordinator(ref, *, quiescent=True):
    if quiescent is not True or Path(ref['path']).resolve() != CLAIM_FILE.resolve():
        raise ValueError('Only this completed coordinator may release its reservation')
    raw = checked(ref).read_bytes()
    value = json.loads(raw)
    if value.get('version') != VERSION or value.get('lease') != str(LEASE_FILE):
        raise ValueError('The coordinator claim is not owned by this scope')
    with (LEASE_FILE.parent / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = RUN_ROOT / 'coordinator-capacity-released.json'
        if marker.exists():
            if LEASE_FILE.exists():
                raise ValueError('Released reservation unexpectedly reappeared')
            return reference(marker)
        if not LEASE_FILE.exists() or hashlib.sha256(LEASE_FILE.read_bytes()).hexdigest() != ref['sha256']:
            raise ValueError('Refuse to unlink an unrecognized shared-pool reservation')
        saved = write_new(marker, {'version': VERSION, 'claim': ref, 'quiescent': True,
                                   'other_claims_or_model_services_changed': False})
        LEASE_FILE.unlink()
        return saved


def verify_host_limits():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('No privileged API coordinator')
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    paths = [line.split(':', 2)[2] for line in rows if line.startswith('0::')]
    if len(paths) != 1 or PurePosixPath(paths[0]).name != UNIT or '..' in PurePosixPath(paths[0]).parts:
        raise PermissionError('Run API continuation only in its own resource-bounded user unit')
    folder = Path('/sys/fs/cgroup') / paths[0].lstrip('/')
    actual = {name: (folder / name).read_text().strip()
              for name in ('memory.max', 'memory.swap.max', 'pids.max')}
    actual['cpu_affinity'] = sorted(os.sched_getaffinity(0))
    if (actual['memory.max'] != str(16 * GIB) or actual['memory.swap.max'] != '0'
            or actual['pids.max'] != '512' or actual['cpu_affinity'] != cpu_affinity()):
        raise ValueError('The auxiliary API coordinator lacks its exact CPU/RAM/PID limits')
    return actual
