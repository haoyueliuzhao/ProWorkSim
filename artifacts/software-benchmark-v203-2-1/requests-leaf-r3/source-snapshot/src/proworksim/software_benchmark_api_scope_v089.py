"""Explicit fresh recovery attempts for the 44 administrative budget cutoffs.

The original six-thousand-slot authority is checked only for each logical
source. New physical identities belong to this separately sealed authority.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import resource
import time

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_api_scope_v088 as predecessor
from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = original.ROOT
VERSION = 'v089-budget-cutoff-independent-recovery-r1'
BATCH_ROOT = ROOT/'runs/software-benchmark-v089/budget-recovery-r1'
API_ROOT = BATCH_ROOT/'api-coordinator'
PRIMARY_ROOT = predecessor.PRIMARY_ROOT
PRIMARY_CURSOR = PRIMARY_ROOT/'cursor.json'
API_UNIT = 'proworksim-v089-api.service'
OLD_API_ROOT, OLD_API_UNIT = predecessor.API_ROOT, predecessor.API_UNIT
INVENTORY_FILE = BATCH_ROOT/'recovery-inventory.json'
PLAN_FILE = BATCH_ROOT/'execution-plan.json'
SOURCE_FILE = BATCH_ROOT/'runtime-sources.json'
AUTH_FILE = AUTHORIZATION_FILE = ROOT/'config/v089-budget-recovery-authorization.json'
USER_AUTH_FILE = ROOT/'artifacts/software-benchmark-v089/recovery-authorization-r1/authorization.json'
CLAIM_FILE = API_ROOT/'coordinator-capacity.json'
LEASE_FILE = original.BATCH_ROOT/'resource-claims/active-v089-api-coordinator.json'
COORDINATOR_ROOT = BATCH_ROOT/'grading-coordinator'
RECOVERY_SUFFIX = ':recovery-v089-r1'
FIRST_PHYSICAL_INDEX, RECOVERY_COUNT = 6000, 44
API_MEMORY_BYTES, API_MEMORY_HIGH_BYTES = 64*1024**3, 32*1024**3
MAX_STARTING_PAIRS, MANAGER_CPUS, NOFILE = 16, 8, 16384
CASH_CAP_CNY = '1700.00'


def load(ref):
    return json.loads(checked(ref).read_bytes())


def parent_module():
    from . import software_benchmark_api_parent_v089
    return software_benchmark_api_parent_v089


def require_explicit_recovery_authorization():
    if not USER_AUTH_FILE.is_file():
        raise PermissionError('Explicit authorization of 44 independent recovery attempts is required')
    ref = reference(USER_AUTH_FILE)
    value = load(ref)
    expected = {'version': 'v089-explicit-budget-recovery-authorization-r1',
        'status': 'approved', 'explicit_user_reply': '启动44个独立恢复回合',
        'authorized_generation_attempts': 44, 'REF': 21, 'PROJECT': 23,
        'per_attempt_input_plus_output_token_upper_bound': 5_000_000,
        'total_new_input_plus_output_token_upper_bound': 220_000_000,
        'same_ledger_total_CNY': '1700.00', 'same_task_seed_and_model_settings': True,
        'old_results_and_fees_preserved': True, 'new_attempts_are_not_exact_session_resumption': True,
        'other_205_unknowns_after_this_phase': True, 'existing_Qwen_operations_modified': False}
    if any(type(value.get(key)) is not type(item) or value.get(key) != item for key, item in expected.items()):
        raise PermissionError('Cash top-up alone does not authorize independent recovery attempts')
    # The proposal path is historical audit context. Runtime authority binds
    # this immutable approval record, not a report that may later gain results.
    return ref


def cpu_affinity():
    values = original.host_cpu_pool()[168:176]
    if len(values) != MANAGER_CPUS:
        raise ValueError('The original eight available management CPUs are required')
    return values


def validate_mapping(row, source, config, original_config):
    expected = {**source, 'slot_id': source['slot_id']+RECOVERY_SUFFIX,
        'slot_index': row['slot_index'], 'configuration': row['configuration'],
        'original_slot_id': source['slot_id'], 'original_slot_index': source['slot_index'],
        'recovery_attempt': 1}
    if (row != expected or row['slot_index'] not in range(FIRST_PHYSICAL_INDEX, FIRST_PHYSICAL_INDEX+RECOVERY_COUNT)
            or source['model_key'] != 'DEEPSEEK' or source['input_plus_output_tokens'] != 5_000_000
            or config != {**original_config, 'slot_id': row['slot_id'], 'slot_index': row['slot_index']}):
        raise PermissionError('Recovery identity differs from the exact original task/seed/condition mapping')
    return row


def require_allowed(operation='v089.run', *, slot_id=None, instance_id=None,
                    grading_only=False):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Recovery host processes remain ordinary user processes')
    names = {'v089.run', 'v089.prepare', 'v089.api.run', 'v089.api.request',
             'v088.run', 'v086.run', 'v079.run', 'v076.run', 'v072.api.request'} | set(original.OPERATIONS)
    if operation not in names or grading_only and operation.endswith('request'):
        raise PermissionError('Operation outside the new recovery scope')
    explicit_approval = require_explicit_recovery_authorization()
    ancestor = original.require_v066_allowed('v066.run', instance_id=instance_id)
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('explicit_recovery_authorization') != explicit_approval
            or auth.get('prior_authorization') != reference(predecessor.AUTH_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('API_cash_cap_CNY') != CASH_CAP_CNY
            or auth.get('fresh_recovery_attempts') != RECOVERY_COUNT
            or auth.get('generation_token_upper_bound') != 220_000_000
            or auth.get('original_first_attempts_overwritten') is not False
            or auth.get('Qwen_lifecycle_operations') != 0):
        raise PermissionError('The explicit 44-attempt budget-recovery authority changed')
    for ref in load(auth['source_index'])['files']:
        checked(ref)
    plan = load(auth['plan'])
    inventory = load(reference(INVENTORY_FILE))
    if (plan.get('version') != VERSION or plan.get('inventory') != reference(INVENTORY_FILE)
            or plan.get('explicit_recovery_authorization') != explicit_approval
            or inventory.get('explicit_recovery_authorization') != explicit_approval
            or plan.get('original_plan') != ancestor['plan']
            or len(plan.get('rows', [])) != RECOVERY_COUNT
            or sum(r.get('arm') == 'REF' for r in plan['rows']) != 21
            or sum(r.get('arm') == 'PROJECT' for r in plan['rows']) != 23
            or any(r.get('input_plus_output_tokens') != 5_000_000 for r in plan['rows'])
            or {r['slot_index'] for r in plan['rows']} != set(range(FIRST_PHYSICAL_INDEX, FIRST_PHYSICAL_INDEX+RECOVERY_COUNT))
            or inventory.get('API_ledger') != str(original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3')):
        raise PermissionError('The fresh recovery plan is incomplete or uses another ledger')
    if slot_id is not None:
        row = next((r for r in plan['rows'] if r['slot_id'] == slot_id), None)
        if row is None or instance_id not in (None, row['instance_id']):
            raise PermissionError('Only the explicitly selected recovery attempt is allowed')
        source = next((r for r in original._cached_json(ancestor['plan'])['rows']
                       if r['slot_id'] == row['original_slot_id']), None)
        if source is None:
            raise PermissionError('Missing logical source identity')
        validate_mapping(row, source, load(row['configuration']), load(source['configuration']))
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Task is outside the 44-attempt recovery panel')
    if not grading_only:
        parent_module().require_qualified()
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.exists() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No active exact recovery-manager lease')
    return auth


def require_grading_allowed(operation='v076.run', **identity):
    if operation not in {'v076.run', 'v079.run', 'v089.run', 'v066.run', 'v066.score', 'v066.delivery.score',
                         'v066.grader.create', 'v066.grader.start', 'v066.transport', 'v066.resolve'}:
        raise PermissionError('Grading-only authority cannot generate or create actors')
    return require_allowed(operation, grading_only=True, **identity)


def verify_host_limits(role='api'):
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')]
    if role != 'api' or len(paths) != 1 or Path(paths[0]).name != API_UNIT:
        raise PermissionError('Use only the independently bounded new API service')
    folder = Path('/sys/fs/cgroup')/paths[0].lstrip('/')
    limits = {k: (folder/k).read_text().strip() for k in ('memory.max', 'memory.high', 'memory.swap.max', 'pids.max')}
    if (limits != {'memory.max': str(API_MEMORY_BYTES), 'memory.high': str(API_MEMORY_HIGH_BYTES),
                   'memory.swap.max': '0', 'pids.max': '512'}
            or sorted(os.sched_getaffinity(0)) != cpu_affinity()
            or resource.getrlimit(resource.RLIMIT_NOFILE)[0] < NOFILE):
        raise PermissionError('Recovery-manager boundaries differ from the frozen specification')
    return {'cgroup': paths[0], 'limits': limits, 'affinity': cpu_affinity(),
            'nofile_soft_hard': list(resource.getrlimit(resource.RLIMIT_NOFILE)), 'uid': os.getuid()}


def reserve_api_coordinator():
    from .software_benchmark_api_scope_v088 import manager_cpu_admission
    require_allowed()
    CLAIM_FILE.parent.mkdir(parents=True, exist_ok=True)
    observed = None if CLAIM_FILE.exists() else manager_cpu_admission()
    with (LEASE_FILE.parent/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CLAIM_FILE.exists():
            if LEASE_FILE.exists() and LEASE_FILE.read_bytes() == CLAIM_FILE.read_bytes():
                return reference(CLAIM_FILE)
            raise ValueError('A consumed manager identity cannot restart')
        if LEASE_FILE.exists() or observed is None or not 0 <= time.time()-observed['observed_unix'] <= 10:
            raise ValueError('Foreign manager lease or stale CPU observation')
        capacity = original.physical_capacity()
        if not capacity['passed'] or capacity['memory_available_bytes'] < 384*1024**3:
            raise original.ResourceBusy('Actual host headroom prevents recovery-manager admission')
        value = {'version': VERSION, 'key': 'v089-api-coordinator', 'spec': {'role': 'auxiliary_coordinator', 'unit': API_UNIT},
            'reserved_cpu': MANAGER_CPUS, 'reserved_memory_bytes': API_MEMORY_BYTES, 'reserved_spool_bytes': 0,
            'lease': str(LEASE_FILE), 'authorization': reference(AUTH_FILE), 'cpu_affinity': cpu_affinity(),
            'physical_at_admission': capacity, 'actual_CPU_at_admission': observed,
            'Qwen_lifecycle_operations': 0, 'accounting': 'quota_sum_diagnostic_not_actual_usage'}
        raw = original._write_claim(CLAIM_FILE, value)
        with LEASE_FILE.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return reference(CLAIM_FILE)


def release_api_coordinator(ref):
    value = load(ref)
    if Path(ref['path']).resolve() != CLAIM_FILE or value.get('lease') != str(LEASE_FILE):
        raise PermissionError('Not the exact owned recovery-manager reservation')
    with (LEASE_FILE.parent/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = API_ROOT/'coordinator-capacity-released.json'
        if marker.exists():
            if LEASE_FILE.exists() or load(reference(marker)).get('claim') != ref:
                raise ValueError('Reservation release identity differs')
            return reference(marker)
        if not LEASE_FILE.exists() or LEASE_FILE.read_bytes() != checked(ref).read_bytes():
            raise ValueError('Owned lease no longer matches')
        result = write_new(marker, {'claim': ref, 'quiescent': True, 'other_claims_unchanged': True})
        LEASE_FILE.unlink()
        return result
