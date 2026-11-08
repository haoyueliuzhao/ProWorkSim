"""Read the complete shared account while admitting only never-called originals."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sqlite3

from .software_benchmark_api_recovery_v159 import validate_recovery_plan
from .software_benchmark_candidates_v054 import reference


def audit(ledger_path, original_plan):
    from . import software_benchmark_host_api_v157 as original
    from . import software_benchmark_scope_v161 as recovery
    from .software_benchmark_host_api_v161 import checked_authority
    apis = {g: original.api_for(g) for g in original.GROUP_IDS}
    recovery_plan = recovery.validate_plan(recovery.load(reference(recovery.PLAN_FILE)))
    checked_authority(recovery_plan, reference(recovery.RECOVERY_AUTHORITY_FILE), apis)
    original_rows = {r['slot_id']: r for r in original_plan['rows']}
    independent = {r['slot_id']: r for r in recovery_plan['rows']}
    if len(original_rows) != 72 or len(independent) != 14 or set(original_rows) & set(independent):
        raise ValueError('The same account must preserve72 originals plus14 approved independent attempts')
    allowed = {**original_rows, **independent}
    path = Path(ledger_path).resolve()
    if path != Path(apis['C0'].POLICY['child_ledger_path']).resolve():
        raise ValueError('Second wave cannot create or switch cash accounts')
    with original.ledger_read('C0') as db:
        rows = [dict(r) for r in db.execute('SELECT * FROM requests ORDER BY reserved_utc,request_id')]
        halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
    counts = Counter()
    totals = Counter()
    for row in rows:
        scheduled = allowed.get(row['slot_id'])
        if (scheduled is None or row['condition'] != scheduled['condition_id']
                or row['member_id'] not in scheduled['fixed_members']
                or row['usage_id'] not in {'agent', 'condenser', 'compressor'}
                or row['status'] not in {'settled', 'reserved', 'unknown', 'http_error_uncertain'}):
            raise ValueError('Physical account contains an unapproved identity or accounting state')
        if row['slot_id'] in original_rows:
            counts[row['slot_id']] += 1
        totals['physical_requests'] += 1
        totals['inflight_requests'] += row['status'] == 'reserved'
        if row['status'] == 'settled':
            usage = json.loads(row['usage_json'])
            if usage['total_tokens'] != usage['prompt_tokens'] + usage['completion_tokens']:
                raise ValueError('Provider actual token totals disagree')
            totals['known_actual_total_tokens'] += usage['total_tokens']
            totals['settled_peak_upper_nanoyuan'] += row['settled_nanoyuan']
        else:
            totals['held_or_unknown_nanoyuan'] += row['reserved_nanoyuan']
    used = set(counts)
    totals['remaining_peak_upper_nanoyuan'] = 500_000_000_000 - (
        totals['settled_peak_upper_nanoyuan'] + totals['held_or_unknown_nanoyuan'])
    return {'version': 'v168-whole-account-original-slot-admission-r1',
        'ledger_path': str(path), 'global_halt': halt[0] if halt else None,
        'used_original_slots': sorted(used), 'admitted_original_slots': sorted(set(original_rows)-used),
        'totals': dict(totals), 'requests': [{k: r[k] for k in ('request_id', 'slot_id', 'status')} for r in rows],
        'approved_independent_attempts_in_account': len(independent),
        'independent_attempt_costs_included': True, 'additional_cash_allowance_CNY': '0.00',
        'cash_cap_CNY': '500.00', 'model_calls_during_audit': 0}
