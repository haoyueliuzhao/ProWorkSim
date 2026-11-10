"""Read current v192 progress and physical usage; never mutate or resume work."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import sqlite3
import time

from proworksim import software_benchmark_scope_v192 as scope


def read(path, default=None):
    return json.loads(path.read_bytes()) if path.exists() else default


def owner_alive(start):
    if not start or not isinstance(start.get('pid'), int):
        return False
    proc = Path('/proc') / str(start['pid'])
    try:
        args = (proc / 'cmdline').read_bytes().split(b'\0')
        revision = scope.API_UNIT.removeprefix('proworksim-').split('-')[0]
        entrypoint = scope.ROOT / 'tools' / ('run_context_tasks_' + revision + '.py')
        return proc.stat().st_uid == os.getuid() and str(entrypoint).encode() in args
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        # A sandbox may expose a different PID namespace. Absence here is not
        # proof that the ordinary-user service has stopped on the host.
        return None


def summary():
    now = time.time()
    plan = read(scope.PLAN_FILE)
    progress = read(scope.API_ROOT / 'progress.json', {})
    final = read(scope.API_ROOT / 'final.json')
    start = read(scope.API_ROOT / 'execution-started.json')
    error = read(scope.API_ROOT / 'coordinator-error.json')
    jobs, calls, policy = {}, [], {}
    if scope.LEDGER_FILE.exists():
        with sqlite3.connect(scope.LEDGER_FILE.as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            jobs = {r['job_id']: dict(r) for r in db.execute('SELECT * FROM jobs')}
            calls = [dict(r) for r in db.execute('SELECT * FROM requests')]
            policy = json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
    by_slot = {}
    for call in calls:
        by_slot.setdefault(call['job_id'], []).append(call)
    scores = progress.get('scores', {})
    by_endpoint = {(r['slot_id'], r['endpoint']): r for r in scores.values()}
    groups = {g: {'primary': Counter(), 'repeat': Counter()} for g in scope.GROUP_IDS}
    all_rows = []
    for row in plan['rows']:
        sid = row['slot_id']
        records = by_slot.get(sid, [])
        settled = [r for r in records if r['status'] == 'settled']
        usages = [json.loads(r['usage']) for r in settled]
        job = jobs.get(sid)
        item = {
            'slot_index': row['slot_index'], 'instance_id': row['instance_id'],
            'group': row['group_id'], 'primary': row['primary_panel'],
            'generation_state': job['status'] if job else 'not_admitted',
            'called_model': bool(records), 'physical_requests': len(records),
            'settled_requests': len(settled), 'uncertain_or_inflight_requests': len(records) - len(settled),
            'actual_input_tokens': sum(u['input_tokens'] for u in usages),
            'actual_output_tokens': sum(u['output_tokens'] for u in usages),
            'actual_total_tokens': sum(u['total_tokens'] for u in usages),
            'settled_cost_upper_CNY': sum(r['cost'] for r in settled) / 1e9,
        }
        for endpoint in ('code', 'delivery'):
            score = by_endpoint.get((sid, endpoint), {})
            item[endpoint + '_resolved'] = score.get('resolved')
            item[endpoint + '_status'] = score.get('status', 'not_scored')
        all_rows.append(item)
        counts = groups[row['group_id']]['primary' if row['primary_panel'] else 'repeat']
        counts['planned'] += 1
        counts['called'] += item['called_model']
        counts['not_admitted'] += job is None
        counts['generation_closed'] += bool(job and job['status'] == 'closed')
        counts['generation_unknown'] += bool(job and job['status'] == 'technical_unknown')
        counts['actual_tokens_so_far'] += item['actual_total_tokens']
        counts['settled_cost_upper_CNY'] += item['settled_cost_upper_CNY']
        for endpoint in ('code', 'delivery'):
            result = item[endpoint + '_resolved']
            counts[endpoint + '_known'] += isinstance(result, bool)
            counts[endpoint + '_passed'] += result is True
    settled = [r for r in calls if r['status'] == 'settled']
    committed = sum(r['cost'] if r['status'] == 'settled' else r['reserved'] for r in calls)
    holds = sum(max(0, 5_000_000_000 - sum(r['cost'] if r['status'] == 'settled' else r['reserved']
                       for r in by_slot.get(sid, []))) for sid, job in jobs.items() if job['status'] == 'running')
    earmarks = 10 * sum(not r['primary_panel'] and r['slot_id'] not in jobs for r in plan['rows'])
    newest = max([r['finished'] or r['started'] for r in calls], default=None)
    return {
        'version': 'v192-readonly-progress-r1', 'observed_unix': now,
        'run_root': str(scope.BATCH_ROOT), 'unit': scope.API_UNIT,
        'coordinator_alive': owner_alive(start), 'coordinator_error': error,
        'stage': progress.get('stage', 'zero_model_diagnostics' if start else 'prepared'),
        'progress_age_seconds': now - progress['updated_unix'] if progress.get('updated_unix') else None,
        'last_API_activity_age_seconds': now - newest if newest else None,
        'final_record_exists': final is not None,
        'diagnostics_complete': progress.get('diagnostics_complete', 4 if (scope.API_ROOT / 'diagnostics.json').exists() else 0),
        'qualified_environments': progress.get('qualified_environments', 0),
        'reported_generation_active': progress.get('generation_active'),
        'reported_grading_active': progress.get('grading_active'),
        'resource_gate': progress.get('capacity_gate'),
        'cash': {
            'cap_CNY': policy.get('cap_nanoyuan', 300_000_000_000) / 1e9,
            'settled_upper_CNY': sum(r['cost'] for r in settled) / 1e9,
            'uncertain_or_inflight_upper_CNY': sum(r['reserved'] for r in calls if r['status'] != 'settled') / 1e9,
            'unused_active_job_holds_CNY': holds / 1e9,
            'committed_upper_CNY': (committed + holds) / 1e9,
            'unentered_repeat_earmark_CNY': earmarks,
            'physical_statuses': dict(Counter(r['status'] for r in calls)),
            'cash_checks_only_new_block_admission': True,
            'cost_is_peak_tariff_upper_not_invoice': True,
        },
        'groups': groups, 'rows': all_rows,
        'exceptions': progress.get('exceptions', {}),
        'read_only': True,
        'token_averages_require_closed_matched_task_sets_not_inflight_rows': True,
    }


if __name__ == '__main__':
    print(json.dumps(summary(), ensure_ascii=False, indent=2))
