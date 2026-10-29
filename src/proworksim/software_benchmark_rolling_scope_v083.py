"""API-only startup-capacity continuation within the existing parent boundary."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_api_scope_v079 as prior
from . import software_benchmark_api_parent_v076 as parent
from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = original.ROOT
VERSION = 'v083-owned-rolling-API-async-grading-r1'
BATCH_ROOT = ROOT / 'runs/software-benchmark-v083/rolling-api-async-r1'
API_ROOT = BATCH_ROOT / 'api-coordinator'
PRIMARY_ROOT = ROOT / 'runs/software-benchmark-v080/qwen-json-recovery-r1/primary-coordinator'
PRIMARY_CURSOR = PRIMARY_ROOT / 'cursor.json'
OLD_API_ROOT, OLD_API_UNIT = prior.API_ROOT, prior.API_UNIT
API_UNIT = 'proworksim-v083-api.service'
INVENTORY_FILE = API_INVENTORY_FILE = BATCH_ROOT / 'api-inventory.json'
SOURCE_FILE = BATCH_ROOT / 'runtime-sources.json'
PLAN_FILE = BATCH_ROOT / 'plan.json'
AUTH_FILE = AUTHORIZATION_FILE = ROOT / 'config/v083-rolling-api-authorization.json'
HANDOFF_ROOT = BATCH_ROOT / 'handoff'
CLAIM_FILE = API_ROOT / 'coordinator-capacity.json'
LEASE_FILE = original.BATCH_ROOT / 'resource-claims/active-v083-api-coordinator.json'
GIB = 1024**3
API_MEMORY_BYTES = 64 * GIB


def load(ref):
    return json.loads(checked(ref).read_bytes())


def cpu_affinity():
    values = original.host_cpu_pool()[164:168]
    if len(values) != 4:
        raise ValueError('Four declared management CPU lanes are required')
    return values


def require_allowed(operation='v083.run', *, slot_id=None, instance_id=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only the ordinary project user may operate the API continuation')
    if operation not in {'v083.run', 'v083.handoff', 'v083.api.run', 'v083.api.request',
                         'v079.run', 'v079.handoff', 'v079.api.run', 'v079.api.request',
                         'v076.run', 'v076.api.run', 'v076.api.request', 'v072.api.request'}:
        raise PermissionError('Operation outside the API-only continuation')
    original_auth = original.require_v066_allowed('v066.run', slot_id=slot_id, instance_id=instance_id)
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('prior_authorization') != reference(prior.AUTH_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('parent_authorization') != reference(parent.AUTHORIZATION)
            or auth.get('desired_API_concurrency') != 48 or auth.get('maximum_API_concurrency') != 48
            or auth.get('maximum_starting_pairs') != 8 or auth.get('API_cash_cap_CNY') != '1500.00'
            or auth.get('coordinator_memory_bytes') != API_MEMORY_BYTES
            or auth.get('Qwen_lifecycle_operations') != 0
            or auth.get('per_container_limits_changed') is not False):
        raise PermissionError('The exact API startup amendment differs from its sealed authority')
    for source in load(auth['source_index'])['files']:
        checked(source)
    parent.require_qualified()
    if operation.endswith('handoff'):
        return auth
    seal = load(reference(BATCH_ROOT / 'plan-seal.json'))
    if seal.get('authorization') != reference(AUTH_FILE) or seal.get('plan') != reference(PLAN_FILE):
        raise PermissionError('No exact completed API handoff plan')
    plan = load(seal['plan'])
    if (plan.get('original_plan') != reference(original.PLAN_FILE)
            or plan.get('inventory') != reference(INVENTORY_FILE)
            or plan.get('handoff') != reference(HANDOFF_ROOT / 'inventory-boundary.json')
            or plan.get('API_ledger') != str(original.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3')
            or plan.get('planned_API_slots') != 1000 or plan.get('new_preparation_model_calls') != 0):
        raise PermissionError('The original API experiment or unique ledger changed')
    inventory = load(plan['inventory'])
    allowed = set(inventory['allowed_generation_slot_ids'])
    if allowed & set(inventory['generation']) or allowed & set(inventory['excluded_old_scheduled_slot_ids']):
        raise PermissionError('Consumed identities entered the continuation allowlist')
    if slot_id is not None:
        row = next((row for row in original._cached_json(original_auth['plan'])['rows']
                    if row['slot_id'] == slot_id), None)
        if (row is None or row['model_key'] != 'DEEPSEEK' or row['input_plus_output_tokens'] != 5_000_000
                or instance_id not in (None, row['instance_id'])):
            raise PermissionError('Only original DeepSeek 5M task identities are allowed')
        if slot_id not in allowed:
            entry = inventory['generation'].get(slot_id, {})
            historical = API_ROOT/'historical-results.json'
            if (not operation.endswith('request') and slot_id in inventory['old_owned_slot_ids']
                    and (HANDOFF_ROOT/'stopped.json').exists() and historical.exists()):
                entry = load(reference(historical)).get('generation', {}).get(slot_id, entry)
            if operation.endswith('request') or entry.get('status') != 'closed' or not entry.get('result'):
                raise PermissionError('An already consumed generation cannot be replayed')
    elif instance_id is not None and operation.endswith('request'):
        raise PermissionError('Concrete API requests require a task identity')
    if operation.endswith('request'):
        verify_host_limits('api')
        if not LEASE_FILE.exists() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No active owned API coordinator reservation')
    return auth


def verify_host_limits(role='api'):
    if role != 'api':
        raise PermissionError('This revision has no Qwen coordinator authority')
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if len(paths) != 1 or Path(paths[0]).name != API_UNIT:
        raise PermissionError('Not the exact owned API service')
    folder = Path('/sys/fs/cgroup') / paths[0].lstrip('/')
    values = {name: (folder/name).read_text().strip() for name in ('memory.max', 'memory.swap.max', 'pids.max')}
    if values != {'memory.max': str(API_MEMORY_BYTES), 'memory.swap.max': '0', 'pids.max': '512'} or sorted(os.sched_getaffinity(0)) != cpu_affinity():
        raise PermissionError('API coordinator hard limits differ from its grant')
    return {'cgroup': paths[0], 'limits': values, 'affinity': cpu_affinity(), 'uid': os.getuid()}


def reserve_api_coordinator():
    require_allowed('v083.handoff' if not (BATCH_ROOT/'plan-seal.json').exists() else 'v083.api.run')
    CLAIM_FILE.parent.mkdir(parents=True, exist_ok=True)
    with (LEASE_FILE.parent/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CLAIM_FILE.exists():
            if LEASE_FILE.exists() and LEASE_FILE.read_bytes() == CLAIM_FILE.read_bytes():
                return reference(CLAIM_FILE)
            raise ValueError('The API service identity cannot be restarted')
        if LEASE_FILE.exists():
            raise ValueError('Foreign auxiliary lease')
        physical = original.physical_capacity()
        if not physical['passed'] or physical['memory_available_bytes'] < 320*GIB + API_MEMORY_BYTES:
            raise original.ResourceBusy('Actual host headroom prevents the additional management process')
        value = {'version': VERSION, 'key': 'v083-api-coordinator',
            'spec': {'role': 'auxiliary_coordinator', 'unit': API_UNIT},
            'reserved_cpu': 4, 'reserved_memory_bytes': API_MEMORY_BYTES, 'reserved_spool_bytes': 0,
            'lease': str(LEASE_FILE), 'authorization': reference(AUTH_FILE),
            'cpu_affinity': cpu_affinity(), 'physical_at_admission': physical,
            'temporary_overlap_with_old_API_coordinator': not (HANDOFF_ROOT/'stopped.json').exists(),
            'accounting': 'quota_sum_diagnostic_not_actual_usage', 'Qwen_lifecycle_operations': 0}
        raw = original._write_claim(CLAIM_FILE, value)
        with LEASE_FILE.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return reference(CLAIM_FILE)


def release_api_coordinator(ref):
    value = load(ref)
    if Path(ref['path']).resolve() != CLAIM_FILE or value.get('lease') != str(LEASE_FILE):
        raise PermissionError('Only the exact owned API lease can be released')
    with (LEASE_FILE.parent/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = API_ROOT/'coordinator-capacity-released.json'
        if marker.exists():
            if LEASE_FILE.exists() or load(reference(marker)).get('claim') != ref:
                raise ValueError('Reservation release ownership mismatch')
            return reference(marker)
        if not LEASE_FILE.exists() or LEASE_FILE.read_bytes() != checked(ref).read_bytes():
            raise ValueError('Owned lease no longer matches')
        result = write_new(marker, {'claim': ref, 'quiescent': True, 'other_claims_unchanged': True})
        LEASE_FILE.unlink()
        return result
