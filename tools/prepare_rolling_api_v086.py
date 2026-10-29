"""Prepare the exact API-only startup amendment and post-handoff inventory."""
from __future__ import annotations

import argparse
from contextlib import closing
import importlib.util
import json
import sqlite3
import time

from proworksim import software_benchmark_rolling_scope_v086 as scope
from proworksim import software_benchmark_rolling_handoff_v086 as handoff
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def launcher():
    spec = importlib.util.spec_from_file_location('v086_owned_launcher', scope.ROOT/'tools/launch_rolling_api_v086.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def bootstrap():
    parent.require_qualified()
    if scope.AUTH_FILE.exists():
        scope.require_allowed('v086.handoff')
        return {'authorization': reference(scope.AUTH_FILE), 'runtime_operations': 0}
    prior_authority = scope.prior.require_allowed('v085.handoff')
    units = launcher().prepare()
    files = sorted(path for folder in (scope.ROOT/'src/proworksim', scope.ROOT/'tools') for path in folder.glob('*v086*.py'))
    files.extend([scope.ROOT/'src/proworksim/software_benchmark_async_queue_v082.py',
                  scope.ROOT/'src/proworksim/software_benchmark_resources_v080.py'])
    inherited = scope.load(prior_authority['source_index'])['files']
    source_refs = {ref['path']: ref for ref in inherited}
    source_refs.update({str(path): reference(path) for path in files})
    sources = write_new(scope.SOURCE_FILE, {'version': scope.VERSION,
        'files': [source_refs[key] for key in sorted(source_refs)]})
    authority = write_new(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'prior_authorization': reference(scope.prior.AUTH_FILE), 'source_index': sources,
        'parent_authorization': reference(parent.AUTHORIZATION), 'API_cash_cap_CNY': '1500.00',
        'desired_API_concurrency': 48, 'maximum_API_concurrency': 48, 'maximum_starting_pairs': scope.MAX_STARTING_PAIRS,
        'coordinator_memory_bytes': scope.API_MEMORY_BYTES,
        'manager_CPU_count': scope.MANAGER_CPUS, 'nofile_soft_limit': scope.NOFILE,
        'Qwen_lifecycle_operations': 0, 'per_container_limits_changed': False,
        'old_API_transition': 'paused_old_admissions_with_disjoint_successor_inventory',
        'unproven_owner_exit_cancellation_allowed': False, 'parent_created_or_modified': False,
        'temporary_additional_management_memory_bytes': scope.API_MEMORY_BYTES,
        'temporary_additional_management_CPU': scope.MANAGER_CPUS,
        'unit': units['specification'], 'prepared_unix': time.time(),
        'basis': '用户要求按实际CPU余量提高DeepSeek并发；全部评分准备和交付校验异步，原在途自然完成'})
    return {'authorization': authority, 'sources': sources, 'unit': units, 'runtime_operations': 0}


def partition(rows, cursor, previous, scheduled, consumed, requested, partial):
    targets = {row['slot_id']: row for row in rows if row['model_key'] == 'DEEPSEEK'
               and row['input_plus_output_tokens'] == 5_000_000}
    if len(rows) != 6000 or len(targets) != 1000:
        raise ValueError('Preserve the complete original two-group API target panel')
    state = {key: {slot: entry for slot, entry in cursor.get(key, {}).items() if slot in targets}
             for key in ('generation', 'scores', 'deliveries')}
    excluded = set(previous.get('excluded_old_scheduled_slot_ids', [])) | set(scheduled)
    old_owned = set(state['generation']) | set(scheduled)
    blocked = excluded | set(consumed) | set(requested) | set(partial)
    allowed, external = [], []
    for slot in targets:
        if slot in state['generation']:
            continue
        if slot in scheduled:
            state['generation'][slot] = {'status': 'external_running', 'entered': slot in consumed or slot in requested,
                'original_owner': scope.OLD_API_UNIT, 'result': None,
                'measurement_pending': True, 'not_a_model_failure': True, 'automatic_replay': False}
            external.append(slot)
        elif slot in blocked:
            state['generation'][slot] = {'status': 'technical_unknown',
                'entered': slot in consumed or slot in requested, 'result': None,
                'error': 'Previously consumed identity lacks a retained terminal checkpoint',
                'automatic_replay': False}
            old_owned.add(slot)
        else:
            allowed.append(slot)
    if set(allowed) & old_owned:
        raise ValueError('Rolling API inventories overlap')
    return targets, state, allowed, sorted(old_owned), external, sorted(excluded & set(targets))


def inventory():
    scope.require_allowed('v086.handoff')
    boundary_ref = handoff.capture_boundary()
    if boundary_ref.get('status'):
        return boundary_ref
    if scope.INVENTORY_FILE.exists():
        raise FileExistsError('A rolling continuation inventory is immutable')
    boundary = scope.load(boundary_ref)
    cursor = scope.load(boundary['cursor'])
    previous = scope.load(reference(scope.prior.INVENTORY_FILE))
    rows = scope.load(reference(scope.original.PLAN_FILE))['rows']
    ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
    with closing(sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        requested = {row[0] for row in db.execute('SELECT DISTINCT slot_id FROM requests')}
    consumed, partial = set(), set()
    for row in rows:
        if row['model_key'] != 'DEEPSEEK' or row['input_plus_output_tokens'] != 5_000_000:
            continue
        if any((root/'resource-claims'/f"{role}-{row['slot_index']}.json").exists()
               for root in (scope.original.PREDECESSOR_ROOT, scope.original.BATCH_ROOT)
               for role in ('actor', 'controller', 'volume')):
            consumed.add(row['slot_id'])
        if any((root/'episodes'/str(row['slot_index'])).exists()
               for root in (scope.original.PREDECESSOR_ROOT, scope.original.BATCH_ROOT)):
            partial.add(row['slot_id'])
    targets, state, allowed, old_owned, external, excluded = partition(rows, cursor, previous,
        boundary['old_scheduled_slot_ids'], consumed, requested, partial)
    if not allowed:
        raise ValueError('No unused original API task remains for a successor')
    usage = {slot: ref for slot, ref in previous['usage_record_files'].items() if slot in state['generation']}
    for path in (scope.OLD_API_ROOT/'usage-records').glob('*.json'):
        # These reports can still change as the old owner drains. Freeze the
        # captured bytes in the new inventory rather than retaining stale hashes.
        raw = path.read_bytes()
        value = json.loads(raw)
        if value.get('slot_id') in state['generation']:
            frozen = scope.BATCH_ROOT/'usage-at-handoff'/path.name
            frozen.parent.mkdir(exist_ok=True)
            usage[value['slot_id']] = write_new(frozen, raw)
    primary = json.loads(scope.PRIMARY_CURSOR.read_bytes())
    value = {'version': scope.VERSION, 'original_plan': reference(scope.original.PLAN_FILE),
        'handoff': boundary_ref, **state, 'qualifications': primary['qualifications'],
        'retry_zero_generation': {}, 'usage_record_files': usage, 'API_ledger': str(ledger),
        'allowed_generation_slot_ids': allowed,
        'allowed_generation_slot_indices': [targets[slot]['slot_index'] for slot in allowed],
        'excluded_old_scheduled_slot_ids': excluded, 'old_owned_slot_ids': old_owned,
        'external_running_slot_ids_at_handoff': external,
        'planned_API_slots': 1000, 'unused_score_jobs': [], 'unused_control_requests': [],
        'pending_grading_jobs': [], 'delivery_reconciliation': [], 'exceptions': [],
        'new_API_cash_budget': False, 'unknown_reservations_released': False,
        'old_inflight_tasks_cancelled': False, 'Qwen_lifecycle_operations': 0}
    ref = write_new(scope.INVENTORY_FILE, value)
    plan = write_new(scope.PLAN_FILE, {'version': scope.VERSION,
        'original_plan': reference(scope.original.PLAN_FILE), 'inventory': ref, 'handoff': boundary_ref,
        'API_ledger': str(ledger), 'planned_API_slots': 1000, 'new_preparation_model_calls': 0,
        'maximum_starting_pairs': scope.MAX_STARTING_PAIRS, 'API_parent': reference(parent.CREATED),
        'global_API_actor_limit': 48, 'old_and_new_task_sets_disjoint': True,
        'Qwen_lifecycle_operations': 0})
    seal = write_new(scope.BATCH_ROOT/'plan-seal.json', {'authorization': reference(scope.AUTH_FILE), 'plan': plan})
    return {'inventory': ref, 'plan': plan, 'seal': seal, 'new_unused_tasks': len(allowed),
        'externally_owned_inflight_at_boundary': len(external), 'new_model_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--bootstrap', action='store_true')
    group.add_argument('--gate', action='store_true')
    group.add_argument('--inventory', action='store_true')
    group.add_argument('--rollback-before-launch', action='store_true')
    args = parser.parse_args()
    print(json.dumps(bootstrap() if args.bootstrap else handoff.gate() if args.gate
        else handoff.rollback_before_launch() if args.rollback_before_launch else inventory(), ensure_ascii=False))


