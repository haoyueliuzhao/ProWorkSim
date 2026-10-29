"""Original Qwen inventory under a new, independently bounded owner."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_adaptive_scope_v076 as predecessor
from .software_benchmark_candidates_v054 import checked, reference

ROOT = original.ROOT
BATCH_ROOT = ROOT / 'runs/software-benchmark-v080/qwen-json-recovery-r1'
PRIMARY_ROOT = BATCH_ROOT / 'primary-coordinator'
PRIMARY_CURSOR = PRIMARY_ROOT / 'cursor.json'
API_ROOT = BATCH_ROOT / 'unused-api'
PRIMARY_UNIT = 'proworksim-v080-primary.service'
OLD_ROOT = predecessor.PRIMARY_ROOT
OLD_UNIT = predecessor.PRIMARY_UNIT
INVENTORY_FILE = BATCH_ROOT / 'continuation-inventory.json'
PLAN_FILE = BATCH_ROOT / 'plan.json'
SOURCE_FILE = BATCH_ROOT / 'runtime-sources.json'
AUTH_FILE = ROOT / 'config/v080-qwen-recovery-authorization.json'
VERSION = 'v080-original-Qwen-parse-recovery-scope-r1'
GIB = 1024**3
MEMORY_BYTES = 32*GIB


def load(ref):
    return json.loads(checked(ref).read_bytes())


def require_allowed(operation='v080.run', *, slot_id=None, instance_id=None):
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in {'v080.run', 'v076.run'}:
        raise PermissionError('Only the ordinary-user Qwen continuation is authorized')
    original.require_v066_allowed('v066.run', slot_id=slot_id, instance_id=instance_id)
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('original_authorization') != reference(original.AUTHORIZATION_FILE)
            or auth.get('predecessor_authorization') != reference(predecessor.AUTH_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('model_visible_configuration_unchanged') is not True):
        raise PermissionError('The exact Qwen recovery authority changed')
    for source in load(auth['source_index'])['files']:
        checked(source)
    # Preserve every frozen dependency; the new resource reader is a private
    # adapter, not permission to edit the stopped runtime or its original inputs.
    for source in predecessor.load(reference(predecessor.SOURCE_FILE))['files']:
        checked(source)
    plan = load(auth['plan'])
    if (plan.get('original_plan') != reference(original.PLAN_FILE)
            or plan.get('inventory') != reference(INVENTORY_FILE)
            or plan.get('planned_Qwen_slots') != 3000
            or plan.get('coordinator_memory_bytes') != MEMORY_BYTES
            or plan.get('maximum_generation') != 4 or plan.get('maximum_grading') != 1
            or plan.get('new_model_residencies') != 0):
        raise PermissionError('Qwen identity or bounded deployment differs')
    if slot_id is not None:
        inventory = load(plan['inventory'])
        if slot_id not in inventory['allowed_generation_slot_ids']:
            retained = inventory['generation'].get(slot_id, {})
            if retained.get('status') != 'closed' or not isinstance(retained.get('result'), dict):
                raise PermissionError('Consumed Qwen generation cannot be replayed')
        row = next((r for r in original.load(reference(original.PLAN_FILE))['rows'] if r['slot_id'] == slot_id), None)
        if row is None or row['model_key'] != 'QWEN' or instance_id not in (None, row['instance_id']):
            raise PermissionError('Qwen recovery cannot admit another task or model')
    return auth


def verify_host_limits(role='primary'):
    if role != 'primary':
        raise PermissionError('This recovery has no API owner')
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if len(paths) != 1 or Path(paths[0]).name != PRIMARY_UNIT:
        raise PermissionError('Run only in the exact new bounded Qwen unit')
    folder = Path('/sys/fs/cgroup') / paths[0].lstrip('/')
    values = {name: (folder/name).read_text().strip() for name in ('memory.max', 'memory.swap.max', 'pids.max')}
    affinity = list(map(int, original.cpu_set('coordinator').split(',')))
    if (values != {'memory.max': str(MEMORY_BYTES), 'memory.swap.max': '0', 'pids.max': '512'}
            or sorted(os.sched_getaffinity(0)) != affinity):
        raise PermissionError('Qwen owner limits differ from the new grant')
    return {'cgroup': paths[0], 'limits': values, 'affinity': affinity, 'uid': os.getuid(),
            'maximum_grading_processes': 1, 'host_scorer_children_count_toward_parent_memory': True}
