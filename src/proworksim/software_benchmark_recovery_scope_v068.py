"""Scoped recovery of original unused resources; no shared-host reconfiguration."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

from . import software_benchmark_dispatch_v066 as primary
from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = primary.ROOT
BATCH_ROOT = ROOT / 'runs/software-benchmark-v068/recovery-r1'
PRIMARY_ROOT = BATCH_ROOT / 'primary-coordinator'
PRIMARY_CURSOR = PRIMARY_ROOT / 'cursor.json'
API_ROOT = BATCH_ROOT / 'api-coordinator'
INVENTORY_FILE = BATCH_ROOT / 'continuation-inventory.json'
AUTHORIZATION_FILE = AUTH_FILE = ROOT / 'config/v068-recovery-authorization.json'
PLAN_FILE = BATCH_ROOT / 'plan.json'
SOURCE_FILE = BATCH_ROOT / 'runtime-sources.json'
PROPOSAL_FILE = ROOT / 'artifacts/software-benchmark-v068/runtime-authorization-r1/proposal.json'
PRIMARY_UNIT = 'proworksim-v066-continuation.service'
API_UNIT = 'proworksim-v068-api-continuation.service'
CLAIM_FILE = API_ROOT / 'coordinator-capacity.json'
LEASE_FILE = primary.BATCH_ROOT / 'resource-claims/active-v068-coordinator.json'
VERSION = 'v068-owned-original-panel-recovery-r1'
GIB = 1024**3


def load(ref):
    return json.loads(checked(ref).read_bytes())


def cpu_affinity():
    cpus = primary.host_cpu_pool()[164:168]
    if len(cpus) != 4:
        raise ValueError('Recovery API coordinator requires four declared CPU lanes')
    return cpus


def require_allowed(operation='v068.run', *, slot_id=None, instance_id=None):
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in {'v068.run', 'v068.api.run', 'v068.api.request'}:
        raise PermissionError('Only the bounded ordinary-user recovery is authorized')
    primary.require_v066_allowed('v066.run', slot_id=slot_id, instance_id=instance_id)
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('primary_authorization') != reference(primary.AUTHORIZATION_FILE)
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('proposal') != reference(PROPOSAL_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)):
        raise PermissionError('Exact recovery authority or source seal changed')
    for source in load(auth['source_index'])['files']:
        checked(source)
    plan = load(auth['plan'])
    if (plan.get('original_plan') != reference(primary.PLAN_FILE)
            or plan.get('inventory') != reference(INVENTORY_FILE)
            or plan.get('API_ledger') != str(primary.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3')
            or plan.get('API_total_cash_cap_CNY') != '1500.00'
            or plan.get('combined_cpu_cap') != 152 or plan.get('combined_memory_cap_GiB') != 832
            or plan.get('existing_resource_identities_only') is not True):
        raise ValueError('Recovery cannot alter original experiment or shared resource scope')
    if slot_id is not None:
        inventory = load(plan['inventory'])
        if slot_id not in inventory['allowed_generation_slot_ids']:
            raise PermissionError('A consumed model episode cannot be replayed')
        if operation.startswith('v068.api'):
            row = next(row for row in primary.load(primary.reference(primary.PLAN_FILE))['rows']
                       if row['slot_id'] == slot_id)
            if row['model_key'] != 'DEEPSEEK':
                raise PermissionError('API coordinator has no Qwen lifecycle authority')
    if operation == 'v068.api.request':
        verify_api_host_limits()
        if not LEASE_FILE.is_file() or not CLAIM_FILE.is_file() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('API work requires its owned shared-pool reservation')
    return auth


def reserve_api_coordinator():
    require_allowed('v068.api.run')
    directory = LEASE_FILE.parent
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CLAIM_FILE.exists():
            ref = reference(CLAIM_FILE)
            if (API_ROOT / 'coordinator-capacity-released.json').exists() or not LEASE_FILE.exists():
                raise ValueError('A released coordinator identity cannot be restarted')
            if LEASE_FILE.read_bytes() != checked(ref).read_bytes():
                raise ValueError('Existing auxiliary reservation belongs to another object')
            return ref
        if LEASE_FILE.exists():
            raise ValueError('An unrecognized auxiliary lease cannot be adopted')
        active = [primary.load(primary.reference(path)) for path in directory.glob('active-*.json')]
        admission = primary._budget(active, 4, 16 * GIB)
        value = {'version': VERSION, 'key': 'v068-api-coordinator',
            'spec': {'role': 'auxiliary_coordinator', 'unit': API_UNIT}, 'lane': None,
            'reserved_cpu': 4, 'reserved_memory_bytes': 16 * GIB, 'reserved_spool_bytes': 0,
            'admission': admission, 'lease': str(LEASE_FILE), 'authorization': reference(AUTH_FILE),
            'plan': reference(PLAN_FILE), 'cpu_affinity': cpu_affinity(),
            'primary_model_units_owned': False}
        CLAIM_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = primary._write_claim(CLAIM_FILE, value)
        with LEASE_FILE.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return reference(CLAIM_FILE)


def release_api_coordinator(ref, *, quiescent=True):
    if quiescent is not True or Path(ref['path']).resolve() != CLAIM_FILE.resolve():
        raise ValueError('Only this completed coordinator reservation may be released')
    value = load(ref)
    if value.get('version') != VERSION or value.get('lease') != str(LEASE_FILE):
        raise ValueError('The coordinator claim is outside this recovery scope')
    with (LEASE_FILE.parent / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = API_ROOT / 'coordinator-capacity-released.json'
        if marker.exists():
            if LEASE_FILE.exists():
                raise ValueError('A released reservation unexpectedly reappeared')
            return reference(marker)
        if not LEASE_FILE.exists() or hashlib.sha256(LEASE_FILE.read_bytes()).hexdigest() != ref['sha256']:
            raise ValueError('Refuse to remove an unrecognized auxiliary reservation')
        saved = write_new(marker, {'version': VERSION, 'claim': ref, 'quiescent': True,
                                   'other_claims_or_model_services_changed': False})
        LEASE_FILE.unlink()
        return saved


def verify_api_host_limits():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('No privileged API coordinator')
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if len(paths) != 1 or PurePosixPath(paths[0]).name != API_UNIT or '..' in PurePosixPath(paths[0]).parts:
        raise PermissionError('API recovery must run in its exact bounded user unit')
    folder = Path('/sys/fs/cgroup') / paths[0].lstrip('/')
    actual = {name: (folder / name).read_text().strip()
              for name in ('memory.max', 'memory.swap.max', 'pids.max')}
    actual['cpu_affinity'] = sorted(os.sched_getaffinity(0))
    if (actual['memory.max'] != str(16 * GIB) or actual['memory.swap.max'] != '0'
            or actual['pids.max'] != '512' or actual['cpu_affinity'] != cpu_affinity()):
        raise ValueError('The API coordinator lacks its exact CPU/RAM/PID limits')
    return actual
