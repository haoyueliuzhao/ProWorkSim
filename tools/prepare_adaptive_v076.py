"""Seal adaptive scope and import exact quiet old identities without replay."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sqlite3
import time

from proworksim import software_benchmark_adaptive_scope_v076 as scope
from proworksim import software_benchmark_api_recovery_scope_v072 as old_api
from proworksim import software_benchmark_dispatch_v066 as original
from proworksim import software_benchmark_handoff_v075 as handoff
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = 'v076-post-handoff-identity-inventory-r1'


def load(ref):
    return json.loads(checked(ref).read_bytes())


def launcher():
    spec = importlib.util.spec_from_file_location('v076_owned_launcher', scope.ROOT / 'tools/launch_adaptive_v076.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_bootstrap():
    """Only write scope evidence; do not pause, signal or start any service."""
    handoff.ordinary_user()
    if scope.AUTH_FILE.exists():
        scope.require_allowed('v076.handoff')
        return {'authorization': reference(scope.AUTH_FILE), 'status': 'already_sealed'}
    units = launcher().prepare()
    paths = sorted({path for root in (scope.ROOT / 'src/proworksim', scope.ROOT / 'tools')
                    for version in ('v075', 'v076') for path in root.glob('*' + version + '*.py')})
    source_ref = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': [reference(path) for path in paths]})
    auth = {'version': scope.VERSION, 'status': 'approved',
        'original_authorization': reference(original.AUTHORIZATION_FILE), 'source_index': source_ref,
        'API_total_cash_cap_CNY': '1500.00', 'desired_API_concurrency': 44, 'maximum_API_concurrency': 48,
        'maximum_global_actor_lanes': 52, 'per_container_limits_unchanged': True,
        'model_visible_configuration_unchanged': True, 'shared_host_configuration_changed': False,
        'units': {role: item['specification'] for role, item in units['units'].items()},
        'handoff': {'old_units': handoff.OLD_UNITS, 'old_roots': {key: str(value) for key, value in handoff.OLD_ROOTS.items()},
            'resident_units_reloaded': False, 'signal_only_after_physical_quiescence': True},
        'basis': '用户授权提高DeepSeek并发至40以上，保持单题配置/1500元总账/共享主机隔离',
        'bootstrap_allows_handoff_only_until_plan_sealed': True, 'prepared_unix': time.time()}
    auth_ref = write_new(scope.AUTH_FILE, auth)
    return {'authorization': auth_ref, 'source_index': source_ref, 'units': units['units'], 'runtime_operations': 0}


def merge_entries(*mappings):
    merged = {}
    for values in mappings:
        for key, value in values.items():
            if key in merged and merged[key] != value:
                raise ValueError('Conflicting retained history for ' + key)
            merged[key] = value
    return merged


def scheduled_ids(folder):
    path = folder / 'events.jsonl'
    if not path.exists():
        return set()
    return {event['slot_id'] for raw in path.read_bytes().splitlines() if raw
            and (event := json.loads(raw)).get('kind') == 'generation_scheduled'}


def completed_request(request_ref):
    request = load(request_ref)
    folder = Path(request['directory'])
    completion = folder / 'completion.json'
    if not completion.exists():
        return None
    if not handoff.request_physically_closed(request_ref):
        raise ValueError('Completed old scoring lacks trustworthy physical cleanup')
    return load(reference(completion))


def collect_usage(inventories, roots, eligible):
    values = {}
    for inventory in inventories:
        for slot, ref in inventory.get('usage_record_files', {}).items():
            if slot in eligible:
                if load(ref).get('slot_id') != slot:
                    raise ValueError('Imported usage record has a different task identity')
                values[slot] = ref
    for folder in roots:
        for path in (folder / 'usage-records').glob('*.json'):
            ref = reference(path)
            value = load(ref)
            if value.get('slot_id') in eligible:
                values[value['slot_id']] = ref
    return values


def prepare_inventory():
    scope.require_allowed('v076.handoff')
    if scope.INVENTORY_FILE.exists() or (scope.BATCH_ROOT / 'plan-seal.json').exists():
        raise FileExistsError('Do not replace a sealed continuation inventory')
    boundary = scope.HANDOFF_ROOT / 'administrative-boundary'
    stopped_ref = reference(scope.HANDOFF_ROOT / 'coordinators-stopped.json')
    stopped = load(stopped_ref)
    if stopped.get('resident_units_stopped') is not False or stopped.get('new_generation') != 0:
        raise ValueError('The exact no-model-reload handoff is required')
    staged = handoff.stage_value()
    for role, item in staged['coordinators'].items():
        if handoff.validate_unit(role, load(item['specification']), handoff.show(role)) is not None:
            raise ValueError('Old coordinator remains active')
    # The API finally block was intentionally skipped to retain all residents;
    # explicitly release only its exact now-quiescent auxiliary lease.
    if old_api.LEASE_FILE.exists():
        old_api.release_api_coordinator(reference(old_api.CLAIM_FILE), quiescent=True)
    release_ref = reference(old_api.API_ROOT / 'coordinator-capacity-released.json')
    cursors = {role: load(reference(boundary / f'{role}-cursor.json')) for role in ('primary', 'api')}
    if any(cursor.get('active_generation') or cursor.get('failure') is not None for cursor in cursors.values()):
        raise ValueError('Only quiet generation boundaries may be imported')
    prior_qwen = load(cursors['primary']['resume_inventory'])
    prior_api = load(reference(old_api.INVENTORY_FILE))
    all_rows = load(reference(original.PLAN_FILE))['rows']
    rows = [row for row in all_rows if row['model_key'] == 'QWEN'
            or (row['model_key'] == 'DEEPSEEK' and row['input_plus_output_tokens'] == 5_000_000)]
    targets = {row['slot_id']: row for row in rows}
    if len(all_rows) != 6000 or len(rows) != 4000 or len(targets) != 4000:
        raise ValueError('Keep the original Qwen 3000 and DeepSeek 5M 1000 target identities')
    api_history = {name: merge_entries(prior_api.get(name, {}), cursors['api'].get(name, {}))
                   for name in ('generation', 'scores', 'deliveries')}
    state = {name: merge_entries(cursors['primary'].get(name, {}), api_history[name])
             for name in ('generation', 'scores', 'deliveries')}
    state = {name: {slot: entry for slot, entry in values.items() if slot in targets} for name, values in state.items()}
    excluded = set(prior_api.get('excluded_old_scheduled_slot_ids', []))
    excluded.update(prior_qwen.get('excluded_old_scheduled_slot_ids', []))
    for folder in handoff.OLD_ROOTS.values():
        excluded.update(scheduled_ids(folder))
    ledger = original.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3'
    with sqlite3.connect(ledger.resolve().as_uri() + '?mode=ro', uri=True) as db:
        if db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]:
            raise ValueError('Old API requests are still inflight')
        used_api = set(row[0] for row in db.execute('SELECT DISTINCT slot_id FROM requests'))
    roots = (original.PREDECESSOR_ROOT, original.BATCH_ROOT)
    audit, allowed = [], []
    for row in rows:
        slot, index = row['slot_id'], row['slot_index']
        claims = [str(path) for root in roots for role in ('actor', 'controller', 'volume')
                  if (path := root / 'resource-claims' / f'{role}-{index}.json').exists()]
        candidates = [str(root / 'episodes' / str(index)) for root in roots if (root / 'episodes' / str(index)).exists()]
        reason = ('retained_generation' if slot in state['generation'] else
            'consumed_physical_identity' if claims else 'ever_scheduled' if slot in excluded else
            'API_request_exists' if slot in used_api else 'partial_episode_exists' if candidates else 'unused_original')
        if reason == 'unused_original':
            allowed.append(slot)
        elif slot not in state['generation']:
            state['generation'][slot] = {'status': 'technical_unknown',
                'entered': bool(claims or slot in used_api), 'result': None,
                'error': 'Consumed or previously scheduled identity lacks a complete terminal generation record',
                'handoff_exclusion_reason': reason, 'automatic_replay': False,
                'actual_model_generation_known': None}
        audit.append({'slot_id': slot, 'slot_index': index, 'reason': reason,
            'claims': claims, 'candidate_directories': candidates})
    qualifications = cursors['primary']['qualifications']
    pending_jobs, controls, reconciliations = {}, {}, {}
    completed_controls = dict(prior_qwen.get('completed_controls', {}))

    def record_completion(ref):
        request, completion = load(ref), completed_request(ref)
        if completion is None:
            raise ValueError('A formerly active grader has no physical completion')
        key, slot = request['resource_key'], request.get('slot_id')
        if key.startswith('delivery-score-'):
            state['deliveries'][slot] = {'status': 'official_attempt_completed', 'request': ref, 'completion': completion}
        elif key.startswith('score-'):
            state['scores'][slot] = {'request': ref, 'completion': completion}
            if targets[slot]['arm'] == 'PROJECT' and slot not in state['deliveries']:
                reconciliations[slot] = {'slot_id': slot, 'generation_result': state['generation'][slot]['result'],
                    'code_request': ref}
        else:
            completed_controls.setdefault(request['instance_id'], {})[request['patch_kind']] = completion

    for cursor in cursors.values():
        for ref in cursor.get('active_grading', []):
            record_completion(ref)
        for ref in cursor.get('pending_controls', []):
            request = load(ref)
            if completed_request(ref) is not None:
                record_completion(ref)
            else:
                controls[request['resource_key']] = ref
        for kind, row, item, prepared in cursor.get('pending_scores', []):
            if row['slot_id'] not in targets or row != targets[row['slot_id']] or kind not in {'code', 'delivery'}:
                raise ValueError('Pending scoring job differs from its exact original row')
            if prepared and completed_request(item) is not None:
                record_completion(item)
            elif prepared and any((root / 'resource-claims' / (load(item)['resource_key'] + '.json')).exists()
                                  for root in roots):
                unknown = {'status': 'technical_unknown', 'request': item,
                    'error': 'Consumed prepared score lacks completion; no replay'}
                state['scores' if kind == 'code' else 'deliveries'][row['slot_id']] = unknown
            else:
                pending_jobs[(kind, row['slot_id'])] = [kind, row, item, prepared]
    # Persist all closed candidates lacking their code score. The request file,
    # when already prepared, remains the same physical scoring identity.
    for slot, entry in state['generation'].items():
        if entry.get('status') != 'closed' or slot in state['scores'] or ('code', slot) in pending_jobs:
            continue
        row, result_ref = targets[slot], entry['result']
        matches = []
        for root in roots:
            path = root / 'grading' / f"score-{row['slot_index']}" / 'request.json'
            if path.exists() and load(reference(path)).get('generation_result') == result_ref:
                matches.append(reference(path))
        if len(matches) > 1:
            raise ValueError('Multiple scoring identities claim the same retained candidate')
        if matches and completed_request(matches[0]) is not None:
            record_completion(matches[0])
        elif matches:
            request = load(matches[0])
            consumed = any((root / 'resource-claims' / (request['resource_key'] + '.json')).exists() for root in roots)
            if consumed:
                state['scores'][slot] = {'status': 'technical_unknown', 'error': 'Consumed score lacks completion; no replay',
                    'request': matches[0]}
            else:
                pending_jobs[('code', slot)] = ['code', row, matches[0], True]
        else:
            pending_jobs[('code', slot)] = ['code', row, result_ref, False]
    # Pending tuples already satisfied by imported completed requests are removed.
    pending_jobs = {key: value for key, value in pending_jobs.items()
        if (key[1] not in state['scores'] if key[0] == 'code' else
            state['deliveries'].get(key[1], {}).get('status') != 'official_attempt_completed')}
    for slot, score in state['scores'].items():
        if (targets[slot]['arm'] == 'PROJECT' and score.get('request') and score.get('completion')
                and state['generation'].get(slot, {}).get('status') == 'closed'
                and state['deliveries'].get(slot, {}).get('status') in {None, 'waiting_for_own_code_score'}):
            reconciliations.setdefault(slot, {'slot_id': slot,
                'generation_result': state['generation'][slot]['result'], 'code_request': score['request']})
    usage = collect_usage((prior_qwen, prior_api), handoff.OLD_ROOTS.values(), set(state['generation']))
    scope.BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    audit_ref = write_new(scope.BATCH_ROOT / 'slot-admission-audit.json', {'version': VERSION, 'rows': audit})
    inventory = {'version': VERSION, 'original_plan': reference(original.PLAN_FILE), 'handoff': stopped_ref,
        'predecessor_auxiliary_release': release_ref, **state, 'qualifications': qualifications,
        'retry_zero_generation': {}, 'usage_record_files': usage, 'API_ledger': str(ledger),
        'allowed_generation_slot_ids': allowed,
        'allowed_generation_slot_indices': [targets[slot]['slot_index'] for slot in allowed],
        'excluded_old_scheduled_slot_ids': sorted(excluded & set(targets)),
        'unused_score_jobs': list(pending_jobs.values()), 'unused_control_requests': list(controls.values()),
        'completed_controls': completed_controls, 'delivery_reconciliation': list(reconciliations.values()),
        'exceptions': [], 'admission_audit': audit_ref, 'planned_Qwen_slots': 3000, 'planned_API_slots': 1000,
        'new_API_cash_budget': False, 'unknown_reservations_released': False,
        'prior_provider_failures': {role: cursor.get('provider_failures', {}) for role, cursor in cursors.items()},
        'old_administrative_control_state_is_not_copied_as_new_provider_failure': True}
    inventory_ref = write_new(scope.INVENTORY_FILE, inventory)
    api_ids = {slot for slot, row in targets.items() if row['model_key'] == 'DEEPSEEK'}
    api_inventory = {**inventory,
        **{name: {slot: item for slot, item in inventory[name].items() if slot in api_ids}
           for name in ('generation', 'scores', 'deliveries', 'usage_record_files')},
        'allowed_generation_slot_ids': [slot for slot in allowed if slot in api_ids],
        'allowed_generation_slot_indices': [targets[slot]['slot_index'] for slot in allowed if slot in api_ids],
        'excluded_old_scheduled_slot_ids': sorted(excluded & api_ids),
        'unused_score_jobs': [job for job in pending_jobs.values() if job[1]['slot_id'] in api_ids],
        'unused_control_requests': [],
        'delivery_reconciliation': [item for slot, item in reconciliations.items() if slot in api_ids]}
    api_ref = write_new(scope.BATCH_ROOT / 'api-inventory.json', api_inventory)
    units = launcher().prepare()
    plan_ref = write_new(scope.PLAN_FILE, {'version': scope.VERSION,
        'original_plan': reference(original.PLAN_FILE), 'inventory': inventory_ref, 'API_inventory': api_ref,
        'handoff': stopped_ref, 'API_ledger': str(ledger), 'planned_Qwen_slots': 3000, 'planned_API_slots': 1000,
        'new_model_calls_for_preparation': 0, 'API_total_cash_cap_CNY': '1500.00',
        'units': {role: item['specification'] for role, item in units['units'].items()},
        'model_visible_configuration_unchanged': True, 'new_model_residencies': 0})
    seal = write_new(scope.BATCH_ROOT / 'plan-seal.json', {'authorization': reference(scope.AUTH_FILE), 'plan': plan_ref})
    return {'inventory': inventory_ref, 'API_inventory': api_ref, 'plan': plan_ref, 'seal': seal,
        'remaining': dict(Counter(targets[slot]['model_key'] for slot in allowed)),
        'retained': dict(Counter(value['status'] for value in state['generation'].values())),
        'pending_score_jobs': len(pending_jobs), 'pending_controls': len(controls),
        'new_model_calls': 0, 'resident_lifecycle_operations': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--bootstrap', action='store_true')
    action.add_argument('--inventory', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare_bootstrap() if args.bootstrap else prepare_inventory(), ensure_ascii=False))
