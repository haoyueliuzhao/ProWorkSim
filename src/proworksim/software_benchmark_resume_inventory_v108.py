"""Resume only the original unconsumed pool; preserve every entered attempt."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import software_benchmark_scope_v105 as original
from .software_benchmark_candidates_v054 import reference

VERSION = 'v108-original-57-unconsumed-inventory-r1'
OLD_ROOT = original.BATCH_ROOT/'api-coordinator-v107'
INVENTORY = original.BATCH_ROOT/'resume-v108.json'


def prepare():
    plan = original.load(reference(original.PLAN_FILE))
    history_ref = reference(OLD_ROOT/'run-summary.json')
    history = original.load(history_ref)
    entered = set(history['generation'])
    remaining = [row for row in plan['rows'] if row['slot_id'] not in entered]
    value = {'version': VERSION, 'plan': reference(original.PLAN_FILE),
        'history': history_ref, 'usage_index': reference(OLD_ROOT/'actual-usage-records.json'),
        'initial_health': reference(OLD_ROOT/'initial-pair-api-health.json'),
        'API_qualification': reference(original.BATCH_ROOT/'api-qualification/result.json'),
        'remaining_rows': remaining, 'remaining_count': len(remaining),
        'remaining_by_arm': dict(Counter(row['arm'] for row in remaining)),
        'preserved_entered_count': len(entered), 'preserved_entered_ids': sorted(entered),
        'prior_failure': history['failure'], 'retry_zero_generation': {},
        'additional_model_attempts': 0, 'old_grading_jobs_replayed': 0,
        'original_cash_ledger': str(original.LEDGER_FILE), 'old_results_overwritten': False}
    validate(value, plan, check_unconsumed=True)
    return original.retain(INVENTORY, value)


def validate(value, plan, *, check_unconsumed=False):
    if (value.get('version') != VERSION or value.get('plan') != reference(original.PLAN_FILE)
            or value.get('history') != reference(OLD_ROOT/'run-summary.json')
            or value.get('usage_index') != reference(OLD_ROOT/'actual-usage-records.json')
            or value.get('initial_health') != reference(OLD_ROOT/'initial-pair-api-health.json')
            or value.get('remaining_count') != 57 or value.get('preserved_entered_count') != 43
            or value.get('remaining_by_arm') != {'REF': 29, 'PROJECT': 28}
            or value.get('additional_model_attempts') != 0 or value.get('old_grading_jobs_replayed') != 0
            or value.get('retry_zero_generation') != {} or value.get('old_results_overwritten') is not False):
        raise ValueError('Resume inventory must preserve exactly 43 original attempts and 57 unused rows')
    history = original.load(value['history'])
    entered = set(history['generation'])
    remaining = [row for row in plan['rows'] if row['slot_id'] not in entered]
    if (len(entered) != 43 or value.get('preserved_entered_ids') != sorted(entered)
            or value.get('remaining_rows') != remaining
            or set(history['unentered_generation']) != {row['slot_id'] for row in remaining}
            or history.get('pending_grading_jobs') or history.get('provider_failures')
            or any(item.get('entered') is not True or item.get('status') not in {'closed', 'technical_unknown'}
                   for item in history['generation'].values())):
        raise ValueError('The preserved original stop cannot be replayed or silently reclassified')
    usage = original.load(value['usage_index'])
    if set(usage['record_files']) != entered:
        raise ValueError('All original authoritative usage receipts must remain included')
    health = original.load(value['initial_health'])
    if (health.get('passed') is not True or health.get('slot_ids') != [r['slot_id'] for r in plan['rows'][:2]]
            or health.get('next_generation_limit') != 8 or health.get('score_used_for_admission') is not False):
        raise ValueError('Only the already successful fixed first-pair API gate may be reused')
    for row in plan['rows'][:2]:
        record = original.load(usage['record_files'][row['slot_id']])
        if (record.get('slot_id') != row['slot_id'] or record.get('group_id') != row['group_id']
                or not record.get('calls')):
            raise ValueError('Both original first-pair conditions need their actual settled API usage')
    if check_unconsumed:
        for row in remaining:
            folder = original.BATCH_ROOT/'episodes'/str(row['slot_index'])
            if folder.exists() or any((original.BATCH_ROOT/'resource-claims'/f'{role}-{row["slot_index"]}.json').exists()
                                      for role in ('actor', 'controller', 'volume')):
                raise ValueError('A remaining original environment identity has already been consumed')
        for slot, entry in history['generation'].items():
            row = next(row for row in plan['rows'] if row['slot_id'] == slot)
            expected = original.BATCH_ROOT/'episodes'/str(row['slot_index'])/'result.json'
            if Path(entry['result']['path']).resolve() != expected or entry['result'] != reference(expected):
                raise ValueError('Entered task identity or immutable original result changed')
    return history


def initial_state(history, inventory_ref):
    return {key: history[key] for key in ('generation', 'scores', 'deliveries', 'exceptions', 'provider_failures')} | {
        'inventory': inventory_ref, 'pending_score_jobs': [], 'pending_grading_jobs': [],
        'retry_zero_generation': {}}
