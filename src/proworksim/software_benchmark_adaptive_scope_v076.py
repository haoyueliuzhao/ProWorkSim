"""Scoped adaptive admission; frozen experiment and unique cash ledger stay fixed."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = original.ROOT
BATCH_ROOT = ROOT / 'runs/software-benchmark-v076/adaptive-concurrency-r1'
PRIMARY_ROOT = BATCH_ROOT / 'primary-coordinator'
API_ROOT = BATCH_ROOT / 'api-coordinator'
PRIMARY_CURSOR = PRIMARY_ROOT / 'cursor.json'
HANDOFF_ROOT = BATCH_ROOT / 'handoff'
INVENTORY_FILE = BATCH_ROOT / 'continuation-inventory.json'
API_INVENTORY_FILE = BATCH_ROOT / 'api-inventory.json'
PLAN_FILE = BATCH_ROOT / 'plan.json'
SOURCE_FILE = BATCH_ROOT / 'runtime-sources.json'
AUTH_FILE = AUTHORIZATION_FILE = ROOT / 'config/v076-adaptive-concurrency-authorization.json'
PRIMARY_UNIT = 'proworksim-v076-primary.service'
API_UNIT = 'proworksim-v076-api.service'
CLAIM_FILE = API_ROOT / 'coordinator-capacity.json'
LEASE_FILE = original.BATCH_ROOT / 'resource-claims/active-v076-coordinator.json'
VERSION = 'v076-owned-adaptive-concurrency-r1'
GIB = 1024**3


def load(ref):
    return json.loads(checked(ref).read_bytes())


def cpu_affinity():
    return original.host_cpu_pool()[168:172]


def require_allowed(operation='v076.run', *, slot_id=None, instance_id=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only the project ordinary user may operate this continuation')
    if operation not in {'v076.run', 'v076.api.run', 'v076.api.request', 'v076.handoff',
                         'v075.run', 'v075.handoff', 'v072.api.request', 'v072.api.run'}:
        raise PermissionError('Operation outside adaptive continuation')
    original_authority = original.require_v066_allowed('v066.run', slot_id=slot_id, instance_id=instance_id)
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('original_authorization') != reference(original.AUTHORIZATION_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('API_total_cash_cap_CNY') != '1500.00'
            or auth.get('desired_API_concurrency') != 44
            or auth.get('maximum_API_concurrency') != 48
            or auth.get('maximum_global_actor_lanes') != 52
            or auth.get('per_container_limits_unchanged') is not True
            or auth.get('model_visible_configuration_unchanged') is not True
            or auth.get('shared_host_configuration_changed') is not False):
        raise PermissionError('Adaptive grant differs from its sealed reviewed scope')
    for ref in load(auth['source_index'])['files']:
        checked(ref)
    if operation.endswith('handoff'):
        return auth
    seal = load(reference(BATCH_ROOT / 'plan-seal.json'))
    if seal.get('authorization') != reference(AUTH_FILE) or seal.get('plan') != reference(PLAN_FILE):
        raise PermissionError('No exact post-handoff execution plan')
    plan = load(seal['plan'])
    if (plan.get('original_plan') != reference(original.PLAN_FILE)
            or plan.get('inventory') != reference(INVENTORY_FILE)
            or plan.get('API_inventory') != reference(API_INVENTORY_FILE)
            or plan.get('API_ledger') != str(original.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3')
            or plan.get('planned_Qwen_slots') != 3000 or plan.get('planned_API_slots') != 1000
            or plan.get('handoff') != reference(HANDOFF_ROOT / 'coordinators-stopped.json')
            or plan.get('new_model_calls_for_preparation') != 0):
        raise PermissionError('Experiment identity or handoff boundary changed')
    inventory = load(plan['inventory'])
    if slot_id is not None and slot_id not in inventory['allowed_generation_slot_ids']:
        # Scoring may address a retained closed candidate without reopening it.
        retained = inventory['generation'].get(slot_id, {})
        if (operation.endswith('request') or retained.get('status') != 'closed'
                or not isinstance(retained.get('result'), dict)):
            raise PermissionError('Consumed generation cannot be replayed')
    if '.api.' in operation:
        api_inventory = load(plan['API_inventory'])
        api_allowed = set(api_inventory['allowed_generation_slot_ids'])
        if (not api_allowed <= set(inventory['allowed_generation_slot_ids'])
                or api_allowed & set(api_inventory['generation'])
                or api_allowed & set(api_inventory['excluded_old_scheduled_slot_ids'])
                or api_inventory.get('API_ledger') != plan['API_ledger']):
            raise PermissionError('API identity inventory is not the exact unused original subset')
        if slot_id is None:
            # Provider initialization has no task identity. Every concrete
            # transport request must subsequently supply its sealed slot.
            if instance_id is not None:
                raise PermissionError('A concrete API task requires its slot identity')
        else:
            original_plan = original._cached_json(original_authority['plan'])
            row = next((value for value in original_plan['rows'] if value['slot_id'] == slot_id), None)
            if (slot_id not in api_allowed or row is None or row.get('model_key') != 'DEEPSEEK'
                    or row.get('input_plus_output_tokens') != 5_000_000
                    or instance_id not in (None, row.get('instance_id'))):
                raise PermissionError('API transport is restricted to its unused DeepSeek 5M identity')
    if operation.endswith('request'):
        verify_host_limits('api')
        if not LEASE_FILE.exists() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('API owner reservation is not active')
    return auth


def verify_host_limits(role):
    if role not in {'primary', 'api'}:
        raise ValueError('Unknown coordinator role')
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    expected = PRIMARY_UNIT if role == 'primary' else API_UNIT
    if len(paths) != 1 or Path(paths[0]).name != expected:
        raise PermissionError('Not the exact bounded adaptive coordinator')
    folder = Path('/sys/fs/cgroup') / paths[0].lstrip('/')
    values = {name: (folder / name).read_text().strip()
              for name in ('memory.max', 'memory.swap.max', 'pids.max')}
    affinity = list(map(int, original.cpu_set('coordinator').split(','))) if role == 'primary' else cpu_affinity()
    if (values != {'memory.max': str(16*GIB), 'memory.swap.max': '0', 'pids.max': '512'}
            or sorted(os.sched_getaffinity(0)) != affinity):
        raise PermissionError('Adaptive coordinator limits or affinity changed')
    return {'cgroup': paths[0], 'limits': values, 'affinity': affinity, 'uid': os.getuid()}


def reserve_api_coordinator():
    require_allowed('v076.api.run')
    CLAIM_FILE.parent.mkdir(parents=True, exist_ok=True)
    with (LEASE_FILE.parent / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CLAIM_FILE.exists():
            if LEASE_FILE.exists() and LEASE_FILE.read_bytes() == CLAIM_FILE.read_bytes():
                return reference(CLAIM_FILE)
            raise ValueError('Consumed coordinator identity cannot be restarted')
        if LEASE_FILE.exists():
            raise ValueError('Foreign auxiliary reservation')
        physical = original.physical_capacity()
        if physical['memory_available_bytes'] < 320*GIB or not physical['passed']:
            raise original.ResourceBusy('Physical headroom prevents coordinator startup')
        value = {'version': VERSION, 'key': 'v076-api-coordinator',
            'spec': {'role': 'auxiliary_coordinator', 'unit': API_UNIT},
            'reserved_cpu': 4, 'reserved_memory_bytes': 16*GIB, 'reserved_spool_bytes': 0,
            'lease': str(LEASE_FILE), 'authorization': reference(AUTH_FILE), 'plan': reference(PLAN_FILE),
            'cpu_affinity': cpu_affinity(), 'accounting': 'per_object_quota_not_actual_usage'}
        raw = original._write_claim(CLAIM_FILE, value)
        with LEASE_FILE.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return reference(CLAIM_FILE)


def release_api_coordinator(ref):
    value = load(ref)
    if Path(ref['path']).resolve() != CLAIM_FILE or value.get('lease') != str(LEASE_FILE):
        raise PermissionError('Only the owned auxiliary reservation may be released')
    with (LEASE_FILE.parent / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if LEASE_FILE.read_bytes() != checked(ref).read_bytes():
            raise ValueError('Auxiliary reservation ownership changed')
        result = write_new(API_ROOT / 'coordinator-capacity-released.json',
                           {'claim': ref, 'quiescent': True, 'other_claims_unchanged': True})
        LEASE_FILE.unlink()
        return result
