"""Report actual API tokens from one read-only ledger snapshot, including failed runs."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT/'runs/software-benchmark-v064/full-verified-r1/api-budget/ledger.sqlite3'
OUTPUT = ROOT/'artifacts/software-benchmark-v102/deepseek-token-accounting-r1'
COHORTS = {
    'original_panel': ROOT/'artifacts/software-benchmark-v102/deepseek-final-accounting-r1/original-panel-1000.json',
    'independent_recovery': ROOT/'artifacts/software-benchmark-v102/deepseek-final-accounting-r1/independent-recovery-44.json',
}
RECOVERY_USAGE = ROOT/'runs/software-benchmark-v094/physical-startup-recovery-r1/api-coordinator/actual-usage-summary.json'


def digest(body):
    return hashlib.sha256(body).hexdigest()


def reference(path):
    body = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': digest(body), 'bytes': len(body)}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def run():
    sources = {name: reference(path) for name, path in COHORTS.items()}
    rows = {name: json.loads(path.read_bytes()) for name, path in COHORTS.items()}
    expected = {r['slot_id']: (name, r) for name, values in rows.items() for r in values}
    if len(expected) != 1044:
        raise ValueError('Original and independent physical/model identities must remain separate')
    requests = defaultdict(list)
    with sqlite3.connect('file:'+str(LEDGER)+'?mode=ro', uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        if connection.execute('PRAGMA query_only').fetchone()[0] != 1:
            raise ValueError('Ledger must be strictly read-only')
        all_statuses = dict(connection.execute('SELECT status,COUNT(*) FROM requests GROUP BY status'))
        records = []
        for values in connection.execute('SELECT request_id,slot_id,condition,status,usage_json FROM requests ORDER BY request_id'):
            request_id, slot, condition, status, usage = values
            if slot not in expected:
                continue
            if condition != expected[slot][1]['condition_id'] or status not in {'settled', 'uncertain'}:
                raise ValueError('Unexpected condition or active request at the frozen reporting boundary')
            record = {'request_id': request_id, 'slot_id': slot, 'condition': condition,
                'status': status, 'usage': json.loads(usage) if usage is not None else None}
            if record['usage'] is not None:
                value = record['usage']
                fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
                if (any(type(value.get(k)) is not int or value[k] < 0 for k in fields)
                        or value['total_tokens'] != value['prompt_tokens']+value['completion_tokens']):
                    raise ValueError('Provider I/O usage does not reconcile')
            if status == 'settled' and record['usage'] is None:
                raise ValueError('Settled request lacks provider token accounting')
            requests[slot].append(record)
            records.append(record)
        snapshot = {'ledger_path': str(LEDGER), 'read_only': True, 'query_only': True,
            'snapshot_utc': datetime.now(timezone.utc).isoformat(), 'ledger_request_status_counts': all_statuses,
            'selected_request_count': len(records), 'selected_records_sha256': digest(canonical(records)),
            'query': 'SELECT request_id,slot_id,condition,status,usage_json FROM requests ORDER BY request_id',
            'selection': 'exact frozen 1000 original slot IDs and 44 distinct recovery slot IDs',
            'excluded': ['7.5M and 10M groups', 'neutral preparation requests', 'all unrelated slot identities'],
            'ledger_rows_changed': False}
    summary_groups, detailed = {}, {}
    for cohort, items in rows.items():
        detailed[cohort] = []
        for row in items:
            calls = requests[row['slot_id']]
            known = [x['usage'] for x in calls if x['usage'] is not None]
            complete = bool(calls) and all(x['status'] == 'settled' and x['usage'] is not None for x in calls)
            detail = {key: row[key] for key in ('slot_id', 'slot_index', 'instance_id', 'arm', 'condition_id')}
            detail.update(original_generation_status=row['original_generation_status'],
                code_status=row['code']['status'], issued_requests=len(calls),
                request_status_counts=dict(Counter(x['status'] for x in calls)),
                provider_usage_complete_and_called=complete,
                usage_undetermined=bool(calls) and not complete,
                no_API_requests_in_ledger=not calls,
                known_input_tokens_lower_bound=sum(x['prompt_tokens'] for x in known),
                known_output_tokens_lower_bound=sum(x['completion_tokens'] for x in known),
                known_total_tokens_lower_bound=sum(x['total_tokens'] for x in known),
                request_records_sha256=digest(canonical(calls)))
            detailed[cohort].append(detail)
        summary_groups[cohort] = {}
        for arm in ('REF', 'PROJECT'):
            selected = [r for r in detailed[cohort] if r['arm'] == arm]
            complete = [r for r in selected if r['provider_usage_complete_and_called']]
            incomplete = [r for r in selected if r['usage_undetermined']]
            complete_tokens = sum(r['known_total_tokens_lower_bound'] for r in complete)
            total = sum(r['known_total_tokens_lower_bound'] for r in selected)
            summary_groups[cohort][arm] = {'planned_tasks': len(selected),
                'tasks_with_issued_API_requests': sum(r['issued_requests'] > 0 for r in selected),
                'complete_usage_called_tasks': len(complete), 'undetermined_usage_called_tasks': len(incomplete),
                'no_API_request_tasks': sum(r['no_API_requests_in_ledger'] for r in selected),
                'no_API_request_by_original_generation_state': dict(Counter(r['original_generation_status']
                    for r in selected if r['no_API_requests_in_ledger'])),
                'complete_usage_by_original_generation_state': dict(Counter(r['original_generation_status'] for r in complete)),
                'known_input_tokens_lower_bound': sum(r['known_input_tokens_lower_bound'] for r in selected),
                'known_output_tokens_lower_bound': sum(r['known_output_tokens_lower_bound'] for r in selected),
                'known_total_tokens_lower_bound': total, 'complete_called_subset_total_tokens': complete_tokens,
                'mean_actual_tokens_complete_called_subset': complete_tokens/len(complete) if complete else None,
                'mean_actual_tokens_full_planned_group': None if incomplete else total/len(selected),
                'full_group_exact_mean_available': not incomplete,
                'zero_request_tasks_excluded_from_called_subset_mean': True,
                'known_partial_usage_included_in_lower_bounds': True}
    original_recovery_usage_ref = reference(RECOVERY_USAGE)
    prior = json.loads(RECOVERY_USAGE.read_bytes())
    for arm, group in summary_groups['independent_recovery'].items():
        frozen = prior['groups']['DEEPSEEK_'+arm+'_B5000K']
        if (group['known_total_tokens_lower_bound'] != frozen['known_actual_tokens_lower_bound']
                or group['complete_usage_called_tasks'] != frozen['usage_final_attempts']
                or group['undetermined_usage_called_tasks'] != 0):
            raise ValueError('Independent recovery ledger total differs from its existing finalized usage summary')
    summary = {'version': 'v102-actual-token-accounting-separate-cohorts-r1', 'sources': sources,
        'ledger_snapshot': snapshot, 'groups': summary_groups,
        'existing_independent_usage_summary': original_recovery_usage_ref,
        'tokens_definition': 'provider prompt_tokens + completion_tokens; cached input included; reasoning included within completion, not added twice',
        'mean_denominator': 'all called tasks with complete provider usage, regardless of code result or controller technical failure',
        'incomplete_full_500_means_not_reported': True,
        'model_calls': 0, 'Docker_operations': 0, 'tests_performed': False,
        'statistics_source': reference(__file__)}
    OUTPUT.mkdir(parents=True, exist_ok=False)
    for name, value in [('summary.json', summary), ('per-slot-usage.json', detailed)]:
        with (OUTPUT/name).open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps({'summary': reference(OUTPUT/'summary.json'), 'groups': summary_groups}, ensure_ascii=False))


if __name__ == '__main__':
    run()
