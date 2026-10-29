"""Prepare the exact API-only startup amendment and post-handoff inventory."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import time

from proworksim import software_benchmark_api_scope_v079 as scope
from proworksim import software_benchmark_api_handoff_v079 as handoff
from proworksim import software_benchmark_api_parent_v076 as parent
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def launcher():
    spec = importlib.util.spec_from_file_location('v079_owned_launcher', scope.ROOT/'tools/launch_api_startup_v079.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def bootstrap():
    parent.require_qualified()
    if scope.AUTH_FILE.exists():
        scope.require_allowed('v079.handoff')
        return {'authorization': reference(scope.AUTH_FILE), 'runtime_operations': 0}
    prior_authority = scope.prior.require_allowed('v076.handoff')
    units = launcher().prepare()
    files = sorted(path for folder in (scope.ROOT/'src/proworksim', scope.ROOT/'tools') for path in folder.glob('*v079*.py'))
    files.append(scope.ROOT/'src/proworksim/software_benchmark_resources_v080.py')
    inherited = scope.load(prior_authority['source_index'])['files']
    source_refs = {ref['path']: ref for ref in inherited}
    source_refs.update({str(path): reference(path) for path in files})
    sources = write_new(scope.SOURCE_FILE, {'version': scope.VERSION,
        'files': [source_refs[key] for key in sorted(source_refs)]})
    authority = write_new(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'prior_authorization': reference(scope.prior.AUTH_FILE), 'source_index': sources,
        'parent_authorization': reference(parent.AUTHORIZATION), 'API_cash_cap_CNY': '1500.00',
        'desired_API_concurrency': 44, 'maximum_API_concurrency': 48, 'maximum_starting_pairs': 8,
        'coordinator_memory_bytes': scope.API_MEMORY_BYTES,
        'Qwen_lifecycle_operations': 0, 'per_container_limits_changed': False,
        'old_API_transition': 'natural_drain_or_independently_proven_dead_owner_recovery',
        'unproven_owner_exit_cancellation_allowed': False, 'parent_created_or_modified': False,
        'temporary_additional_management_memory_bytes': scope.API_MEMORY_BYTES,
        'temporary_additional_management_CPU': 4,
        'unit': units['specification'], 'prepared_unix': time.time(),
        'basis': '用户要求按实际CPU余量尽快提高DeepSeek并发至40以上；原四启动名额已证成为瓶颈'})
    return {'authorization': authority, 'sources': sources, 'unit': units, 'runtime_operations': 0}


def selected_inventory(rows, cursor, previous, *, scheduled, consumed, requested, partial):
    targets = {row['slot_id']: row for row in rows if row['model_key'] == 'DEEPSEEK' and row['input_plus_output_tokens'] == 5_000_000}
    if len(rows) != 6000 or len(targets) != 1000:
        raise ValueError('Keep the original complete 1000-slot API 5M panel')
    if any(cursor.get(key) for key in ('active_generation', 'active_grading', 'pending_controls')):
        raise ValueError('The original API checkpoint is not fully quiet')
    state = {key: {slot: value for slot, value in cursor[key].items() if slot in targets}
             for key in ('generation', 'scores', 'deliveries')}
    excluded = set(previous.get('excluded_old_scheduled_slot_ids', [])) | set(scheduled)
    blocked = excluded | set(consumed) | set(requested) | set(partial)
    allowed = []
    for slot in targets:
        if slot in state['generation']:
            continue
        if slot in blocked:
            state['generation'][slot] = {'status': 'technical_unknown',
                'entered': slot in consumed or slot in requested,
                'actual_model_generation_known': None, 'result': None,
                'error': 'Previously scheduled or consumed identity lacks terminal checkpoint evidence',
                'automatic_replay': False}
        else:
            allowed.append(slot)
    return targets, state, allowed, sorted(excluded & set(targets))


def inventory():
    scope.require_allowed('v079.handoff')
    stopped_ref = reference(scope.HANDOFF_ROOT/'stopped.json')
    stopped = scope.load(stopped_ref)
    if stopped.get('Qwen_lifecycle_operations') != 0 or stopped.get('inflight_tasks_cancelled') is not False:
        raise ValueError('Exact completed API-only handoff required')
    if scope.INVENTORY_FILE.exists() or (scope.BATCH_ROOT/'plan-seal.json').exists():
        raise FileExistsError('Never replace an existing continuation inventory')
    old_spec = reference(scope.OLD_API_ROOT/'coordinator-unit.json')
    if handoff.identity(scope.load(old_spec), handoff.show()) is not None:
        raise ValueError('Old API remains active')
    cursor = scope.load(stopped['cursor'])
    previous = scope.load(reference(scope.prior.API_INVENTORY_FILE))
    rows = scope.load(reference(scope.original.PLAN_FILE))['rows']
    events_ref = reference(scope.OLD_API_ROOT/'events.jsonl')
    scheduled = {event['slot_id'] for line in (scope.OLD_API_ROOT/'events.jsonl').read_bytes().splitlines()
                 if line and (event := json.loads(line)).get('kind') == 'generation_scheduled'}
    ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True) as db:
        if db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]:
            raise ValueError('Old provider still has inflight requests')
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
    targets, state, allowed, excluded = selected_inventory(rows, cursor, previous,
        scheduled=scheduled, consumed=consumed, requested=requested, partial=partial)
    usage = {slot: ref for slot, ref in previous['usage_record_files'].items() if slot in state['generation']}
    for path in (scope.OLD_API_ROOT/'usage-records').glob('*.json'):
        ref = reference(path)
        slot = scope.load(ref).get('slot_id')
        if slot in state['generation']:
            usage[slot] = ref
    # Quiet predecessor v076 flushes its cursor while admission is paused. No
    # already prepared scoring identity is repeated by this handoff.
    pending = list(cursor.get('pending_scores', []))
    pending_ids = set()
    for kind, row, item, prepared in pending:
        if (kind not in {'code', 'delivery'} or targets.get(row['slot_id']) != row
                or type(prepared) is not bool):
            raise ValueError('Recovered pending score is outside the exact original API plan')
        if prepared:
            request = scope.load(item)
            if (scope.original.BATCH_ROOT/'resource-claims'/(request['resource_key']+'.json')).exists():
                raise ValueError('A consumed score identity cannot be repeated')
        else:
            if item != state['generation'][row['slot_id']].get('result'):
                raise ValueError('Recovered scoring candidate identity changed')
        pending_ids.add((kind, row['slot_id']))
    for slot, entry in state['generation'].items():
        if entry.get('status') == 'closed' and slot not in state['scores'] and ('code', slot) not in pending_ids:
            state['scores'][slot] = {'status': 'technical_unknown',
                'error': 'Owner exited without a complete scoring endpoint; original candidate retained',
                'automatic_replay': False}
    current_primary = json.loads(scope.PRIMARY_CURSOR.read_bytes())
    value = {'version': scope.VERSION, 'original_plan': reference(scope.original.PLAN_FILE),
        'handoff': stopped_ref, 'old_events': events_ref, **state,
        'qualifications': current_primary['qualifications'], 'retry_zero_generation': {},
        'allowed_generation_slot_ids': allowed,
        'allowed_generation_slot_indices': [targets[slot]['slot_index'] for slot in allowed],
        'excluded_old_scheduled_slot_ids': excluded, 'usage_record_files': usage,
        'API_ledger': str(ledger), 'planned_API_slots': 1000,
        'unused_score_jobs': pending, 'unused_control_requests': [],
        'delivery_reconciliation': [], 'exceptions': [], 'new_API_cash_budget': False,
        'unknown_reservations_released': False, 'Qwen_lifecycle_operations': 0}
    ref = write_new(scope.INVENTORY_FILE, value)
    plan = write_new(scope.PLAN_FILE, {'version': scope.VERSION,
        'original_plan': reference(scope.original.PLAN_FILE), 'inventory': ref, 'handoff': stopped_ref,
        'API_ledger': str(ledger), 'planned_API_slots': 1000, 'new_preparation_model_calls': 0,
        'maximum_starting_pairs': 8, 'API_parent': reference(parent.CREATED),
        'Qwen_lifecycle_operations': 0})
    seal = write_new(scope.BATCH_ROOT/'plan-seal.json', {'authorization': reference(scope.AUTH_FILE), 'plan': plan})
    return {'inventory': ref, 'plan': plan, 'seal': seal, 'remaining_API_slots': len(allowed),
        'planned_API_slots': 1000, 'new_model_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--bootstrap', action='store_true')
    group.add_argument('--gate', action='store_true')
    group.add_argument('--inventory', action='store_true')
    group.add_argument('--recover-dead-owner', metavar='PROOF_JSON')
    args = parser.parse_args()
    if args.recover_dead_owner:
        handoff.accept_dead_owner(reference(args.recover_dead_owner))
        value = inventory()
    else:
        value = bootstrap() if args.bootstrap else handoff.gate() if args.gate else inventory()
    print(json.dumps(value, ensure_ascii=False))
