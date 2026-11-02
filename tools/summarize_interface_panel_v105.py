"""Read-only live/final accounting for the v105 paired non-thinking test."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / 'artifacts/software-benchmark-v105/preparation-r1/panel.json'
BATCH = ROOT / 'runs/software-benchmark-v105/nonthinking-interface-r1'
TERMINAL = {'closed', 'technical_unknown', 'cancelled', 'not_started'}
FIELDS = ('input_tokens', 'output_tokens', 'total_tokens', 'cache_hit_tokens',
          'cache_miss_tokens', 'reasoning_tokens')


def ref(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}


def read(path):
    return json.loads(Path(path).read_bytes())


def bound(reference):
    path = Path(reference['path'])
    body = path.read_bytes()
    if len(body) != reference['bytes'] or hashlib.sha256(body).hexdigest() != reference['sha256']:
        raise ValueError('Immutable evidence changed: ' + str(path))
    return json.loads(body)


def tokens(usage):
    if usage is None:
        return None
    prompt, output, total = (usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
    if any(type(x) is not int or x < 0 for x in (prompt, output, total)) or prompt + output != total:
        raise ValueError('Reported input/output usage does not reconcile')
    hit = usage.get('prompt_cache_hit_tokens', (usage.get('prompt_tokens_details') or {}).get('cached_tokens'))
    miss = usage.get('prompt_cache_miss_tokens')
    reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
    for name, value, maximum in [('cache_hit', hit, prompt), ('cache_miss', miss, prompt), ('reasoning', reasoning, output)]:
        if value is not None and (type(value) is not int or not 0 <= value <= maximum):
            raise ValueError('Invalid reported ' + name)
    if hit is not None and miss is not None and hit + miss != prompt:
        raise ValueError('Reported cache partitions do not reconcile')
    return {'input_tokens': prompt, 'output_tokens': output, 'total_tokens': total,
            'cache_hit_tokens': hit, 'cache_miss_tokens': miss, 'reasoning_tokens': reasoning}


def ledger_snapshot(path):
    if not path.exists():
        return [], {'present': False, 'read_only': True, 'query_only': True}
    with sqlite3.connect('file:' + str(path.resolve()) + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute('SELECT request_id,slot_id,condition,usage_id,status,'
            'usage_json,reserved_nanoyuan,settled_nanoyuan FROM requests ORDER BY request_id')]
        for row in rows:
            usage = json.loads(row.pop('usage_json')) if row.get('usage_json') is not None else None
            row.pop('usage_json', None)
            row['usage'] = tokens(usage)
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return rows, {'present': True, 'path': str(path), 'read_only': True, 'query_only': True,
                      'records': len(rows), 'records_sha256': digest}


def official_score(folder, row):
    paths = {name: folder / (name + '.json') for name in ('request', 'receipt', 'completion', 'quiescence')}
    if not paths['receipt'].exists():
        return {'resolved': None, 'state': 'not_scored'}
    receipt = read(paths['receipt'])
    if receipt.get('status') != 'official_report':
        return {'resolved': None, 'state': 'technical_unknown', 'receipt': ref(paths['receipt'])}
    if not all(p.exists() for p in paths.values()):
        return {'resolved': None, 'state': 'awaiting_scoring_closeout', 'receipt': ref(paths['receipt'])}
    request, completed, quiet = (read(paths[k]) for k in ('request', 'completion', 'quiescence'))
    identity = bound(receipt['identity'])
    report = receipt['official_result'][1][row['instance_id']]
    candidate = bound(request['candidate_lock'])
    empty = candidate.get('patch_receipt', {}).get('patch', {}).get('bytes') == 0
    if (any(receipt.get(k) != row[k] for k in ('slot_id', 'instance_id', 'condition_id'))
            or any(request.get(k) != row[k] for k in ('slot_id', 'instance_id', 'condition_id'))
            or identity.get('request') != ref(paths['request'])
            or any(identity.get(k) != request.get(k) for k in ('slot_id', 'configuration', 'candidate_lock', 'plan', 'scorer_manifest'))
            or type(receipt.get('resolved')) is not bool or report.get('resolved') is not receipt['resolved']
            or report.get('infra_failure', False)
            or not (report.get('patch_successfully_applied') is True or empty and receipt['resolved'] is False)
            or receipt.get('candidate_changed') is not False or receipt.get('actor_feedback') is not False):
        raise ValueError('Score is not bound to this exact candidate and planned attempt')
    if (completed.get('returncode') != 0 or quiet.get('quiescent') is not True
            or quiet.get('cleanup_errors') != [] or quiet.get('create_result_unknown') is not False):
        return {'resolved': None, 'state': 'awaiting_scoring_closeout', 'receipt': ref(paths['receipt'])}
    return {'resolved': receipt['resolved'], 'state': 'resolved' if receipt['resolved'] else 'unresolved',
            'receipt': ref(paths['receipt']), 'candidate_lock': request['candidate_lock']}


def generation_record(batch, summary, row):
    record = summary.get('generation', {}).get(row['slot_id'], {})
    result_ref = record.get('result')
    path = batch / 'episodes' / str(row['slot_index']) / 'result.json'
    if result_ref is not None:
        result = bound(result_ref)
    elif path.exists():
        result_ref, result = ref(path), read(path)
    else:
        result = None
    if result is not None:
        if result.get('slot_id') != row['slot_id'] or result.get('instance_id') != row['instance_id']:
            raise ValueError('Generation result belongs to another attempt')
        return result.get('status', record.get('status', 'technical_unknown')), result, result_ref
    if row['slot_id'] in summary.get('unentered_generation', []):
        return 'not_started', None, None
    return record.get('status', 'not_started' if summary.get('finished_unix') else 'pending'), None, None


def diagnostics(result):
    if result is None:
        return {'observation_state': 'no_final_generation_record'}
    boundary = result.get('managed_boundary', {})
    outcomes = boundary.get('outcomes', [])
    errors = [str(o.get('response', {}).get('error', {}).get('message', '')) for o in outcomes]
    calls = result.get('ledger', {}).get('calls', [])
    caps = [r['max_output_tokens'] for r in calls if type(r.get('max_output_tokens')) is int]
    return {'observation_state': 'final_generation_record_only',
        'managed_sync_permission_errors_observed': sum('Operation not permitted' in message for message in errors),
        'managed_cursor_error_messages_observed': sum('cursor' in message.lower() for message in errors),
        'managed_test_calls': sum(o.get('decision', {}).get('action') == 'run_tests' for o in outcomes),
        'managed_tests_executed': sum(o.get('decision', {}).get('action') == 'run_tests'
            and o.get('response', {}).get('result', {}).get('executed') is True for o in outcomes),
        'adaptive_output_requests_observed': sum(0 < cap < 32768 for cap in caps),
        'requests_with_recorded_output_cap': len(caps), 'role_stops': boundary.get('role_stops', {}),
        'closure_reason': result.get('closure_reason'), 'delivery_validation': result.get('delivery_validation'),
        'absence_of_observed_errors_is_not_full_repair_certification': True}


def analyze(panel, calls, snapshot, batch, coordinator):
    by_slot = defaultdict(list)
    planned = {r['slot_id']: r for r in panel['rows']}
    for request in calls:
        if request['slot_id'] in planned:
            if request['condition'] != planned[request['slot_id']]['condition_id']:
                raise ValueError('Ledger condition differs from frozen panel')
            by_slot[request['slot_id']].append(request)
    rows = []
    for row in panel['rows']:
        detail = {k: row[k] for k in ('slot_id', 'slot_index', 'instance_id', 'arm', 'condition_id', 'seed')}
        records = by_slot[row['slot_id']]
        known = [r['usage'] for r in records if r['usage'] is not None]
        issues = []
        try:
            state, result, evidence = generation_record(batch, coordinator, row)
        except (ValueError, KeyError, OSError) as error:
            state, result, evidence = 'technical_unknown', None, None
            issues.append({'stage': 'generation', 'error': str(error)})
        settled = all(r['status'] == 'settled' and r['usage'] is not None for r in records)
        complete = snapshot['present'] and state in TERMINAL and settled
        detail.update(generation_state=state, generation_result=evidence,
            ledger_requests=len(records), settled_requests=sum(r['status'] == 'settled' for r in records),
            request_status_counts=dict(Counter(r['status'] for r in records)),
            usage_complete_and_called=complete and bool(records), usage_final=complete,
            usage_prefix_complete=bool(records) and settled,
            no_API_request_in_snapshot=not records,
            token_known_lower_bounds={k: sum(u[k] for u in known if u[k] is not None) for k in FIELDS},
            optional_field_reported_requests={k: sum(u[k] is not None for u in known)
                                              for k in FIELDS[3:]},
            exact_final_tokens={k: sum(u[k] for u in known) if complete and all(u[k] is not None for u in known) else None
                                for k in FIELDS},
            unexpected_positive_reasoning_requests=sum((u['reasoning_tokens'] or 0) > 0 for u in known),
            settled_upper_cny=sum(r['settled_nanoyuan'] or 0 for r in records if r['status'] == 'settled') / 1e9,
            unresolved_reserved_cny=sum(r['reserved_nanoyuan'] for r in records if r['status'] != 'settled') / 1e9,
            interface_diagnostics=diagnostics(result))
        try:
            detail['code'] = official_score(batch / 'grading' / f'score-{row["slot_index"]}', row)
        except (ValueError, KeyError, OSError) as error:
            detail['code'] = {'resolved': None, 'state': 'technical_unknown'}
            issues.append({'stage': 'code_score', 'error': str(error)})
        detail['delivery'] = None
        if row['arm'] == 'PROJECT':
            proof = (result or {}).get('delivery_validation', {})
            if proof.get('submitted') is False:
                detail['delivery'] = {'resolved': False, 'state': 'no_legal_delivery'}
            elif proof.get('submitted') is True and proof.get('same_tree') is True and type(detail['code']['resolved']) is bool:
                detail['delivery'] = {**detail['code'], 'same_tree_code_result_reused': True}
            else:
                try:
                    detail['delivery'] = official_score(batch / 'grading' / f'delivery-score-{row["slot_index"]}', row)
                except (ValueError, KeyError, OSError) as error:
                    detail['delivery'] = {'resolved': None, 'state': 'technical_unknown'}
                    issues.append({'stage': 'delivery_score', 'error': str(error)})
        detail['measurement_issues'] = issues
        rows.append(detail)
    groups = {}
    for arm in ('REF', 'PROJECT'):
        items = [r for r in rows if r['arm'] == arm]
        known_scores = [r for r in items if type(r['code']['resolved']) is bool]
        complete_called = [r for r in items if r['usage_complete_and_called']]
        exact_full = all(r['usage_final'] for r in items)
        groups[arm] = {'planned': len(items),
            'generation_states': dict(Counter(r['generation_state'] for r in items)),
            'code_passed': sum(r['code']['resolved'] is True for r in items),
            'code_failed': sum(r['code']['resolved'] is False for r in items),
            'code_pending_or_unknown': len(items) - len(known_scores),
            'full_panel_accuracy': sum(r['code']['resolved'] is True for r in items) / len(items) if len(known_scores) == len(items) else None,
            'scored_subset_accuracy_diagnostic': sum(r['code']['resolved'] is True for r in items) / len(known_scores) if known_scores else None,
            'delivery_passed': sum(r['delivery']['resolved'] is True for r in items) if arm == 'PROJECT' else None,
            'complete_called_usage_tasks': len(complete_called),
            'mean_actual_tokens_complete_called_subset': sum(r['exact_final_tokens']['total_tokens'] for r in complete_called) / len(complete_called) if complete_called else None,
            'mean_actual_tokens_all_planned_tasks': sum(r['exact_final_tokens']['total_tokens'] for r in items) / len(items) if exact_full else None,
            'known_token_lower_bounds': {k: sum(r['token_known_lower_bounds'][k] for r in items) for k in FIELDS},
            'exact_group_tokens': {k: sum(r['exact_final_tokens'][k] for r in items)
                                   if exact_full and all(r['exact_final_tokens'][k] is not None for r in items) else None for k in FIELDS},
            'reported_optional_field_requests': {k: sum(r['optional_field_reported_requests'][k] for r in items) for k in FIELDS[3:]},
            'ledger_requests': sum(r['ledger_requests'] for r in items),
            'settled_requests': sum(r['settled_requests'] for r in items),
            'unexpected_positive_reasoning_requests': sum(r['unexpected_positive_reasoning_requests'] for r in items),
            'settled_upper_cny': sum(r['settled_upper_cny'] for r in items),
            'unresolved_reserved_cny': sum(r['unresolved_reserved_cny'] for r in items)}
    paired = []
    for task in panel['task_ids']:
        pair = {r['arm']: r for r in rows if r['instance_id'] == task}
        if all(type(pair[arm]['code']['resolved']) is bool for arm in ('REF', 'PROJECT')):
            paired.append({arm: pair[arm]['code']['resolved'] for arm in ('REF', 'PROJECT')})
    cost_pairs = [{arm: next(r for r in rows if r['instance_id'] == task and r['arm'] == arm) for arm in ('REF', 'PROJECT')}
                  for task in panel['task_ids']]
    cost_pairs = [p for p in cost_pairs if all(p[a]['usage_complete_and_called'] for a in ('REF', 'PROJECT'))]
    other = [r for r in calls if r['slot_id'] not in planned]
    summary = {'version': 'v105-live-and-final-token-interface-summary-r1',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'groups': groups, 'ledger_snapshot': snapshot,
        'paired_code_known': len(paired), 'paired_outcomes': dict(Counter(f"{r['REF']}->{r['PROJECT']}" for r in paired)),
        'paired_complete_usage_tasks': len(cost_pairs),
        'paired_mean_tokens': {arm: sum(p[arm]['exact_final_tokens']['total_tokens'] for p in cost_pairs) / len(cost_pairs) if cost_pairs else None for arm in ('REF', 'PROJECT')},
        'batch_budget_cny': panel['api_total_budget_cny'],
        'all_batch_settled_upper_cny': sum(r['settled_nanoyuan'] or 0 for r in calls if r['status'] == 'settled') / 1e9,
        'all_batch_unresolved_reserved_cny': sum(r['reserved_nanoyuan'] for r in calls if r['status'] != 'settled') / 1e9,
        'auxiliary_requests_outside_task_means': len(other),
        'auxiliary_settled_upper_cny': sum(r['settled_nanoyuan'] or 0 for r in other if r['status'] == 'settled') / 1e9,
        'measurement_issues': sum(bool(r['measurement_issues']) for r in rows),
        'notes': ['Known usage sums are lower bounds until every request is settled.',
                  'Optional cache/reasoning fields remain unknown when omitted; reasoning is already inside completion.',
                  'Live request count includes admitted reservations; settled count is separately reported.',
                  'Final task means require terminal generation and complete usage; zero-call tasks excluded from called-subset mean.',
                  'Budget and preparation requests share this batch cash ledger but are excluded from task means.',
                  'Recorded interface-error absence is not comprehensive proof that every repair is complete.'],
        'model_calls_by_summarizer': 0, 'Docker_operations': 0, 'ledger_rows_changed': False}
    return summary, rows


def run(panel_path=PANEL, batch=BATCH, output=None):
    panel = read(panel_path)
    candidates = [batch / 'api-coordinator' / name for name in ('progress.json', 'run-summary.json')]
    present = [p for p in candidates if p.exists()]
    latest = max(present, key=lambda p: p.stat().st_mtime_ns) if present else None
    coordinator = read(latest) if latest else {}
    calls, snapshot = ledger_snapshot(batch / 'api-ledger.sqlite')
    summary, rows = analyze(panel, calls, snapshot, batch, coordinator)
    summary['panel'] = ref(panel_path)
    summary['coordinator_source'] = ref(latest) if latest else None
    output = output or batch / 'reporting'
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary.json', summary), ('per-task.json', rows)]:
        path = output / name
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(path)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel', type=Path, default=PANEL)
    parser.add_argument('--batch-root', type=Path, default=BATCH)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.panel, args.batch_root, args.output), ensure_ascii=False, indent=2))
