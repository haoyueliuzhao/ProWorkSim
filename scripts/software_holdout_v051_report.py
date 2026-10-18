"""Summarize the fixed HOLD inventory from terminal records, without executing it."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

CONDITIONS = ('S_star', 'B', 'Q_plus', 'Q_minus')
METRICS = ('F', 'Q_joint', 'R_token', 'Q_token')


def read(path):
    return json.loads(Path(path).read_text())


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def checked(ref):
    path = Path(ref['path'])
    if reference(path)['sha256'] != ref['sha256']:
        raise ValueError('Changed original evidence: ' + str(path))
    return path


def bounded(values):
    if not values:
        raise ValueError('Use the original nonempty denominator')
    known = [value for value in values if value is not None]
    if any(type(value) not in (int, float) or not 0 <= value <= 1 for value in known):
        raise ValueError('Outcome outside the declared unit interval')
    total, n, missing = sum(known), len(values), len(values) - len(known)
    return {'denominator': n, 'known': len(known), 'unknown': missing,
            'mean': total / n if missing == 0 else None,
            'bounds': [total / n, (total + missing) / n]}


def paired(rows, left, right, metric, tasks):
    index = {(row['task_id'], row['condition']): row[metric] for row in rows}
    if len(index) != len(tasks) * 4:
        raise ValueError('Preserve every task and all four states')
    pairs, low, high = [], 0, 0
    for task in tasks:
        a, b = index[task, left], index[task, right]
        difference = None if a is None or b is None else a - b
        low += (0 if a is None else a) - (1 if b is None else b)
        high += (1 if a is None else a) - (0 if b is None else b)
        pairs.append({'task_id': task, 'difference': difference})
    known = [pair['difference'] for pair in pairs if pair['difference'] is not None]
    return {'left': left, 'right': right, 'denominator': len(tasks), 'known_pairs': len(known),
            'mean': sum(known) / len(tasks) if len(known) == len(tasks) else None,
            'bounds': [low / len(tasks), high / len(tasks)], 'pairs': pairs}


def worker_gpu_index(attempt):
    index = attempt.get('gpu', {}).get('index')
    return index if index is not None else attempt.get('binding', {}).get('gpu_index')


def summarize(root):
    root = Path(root).resolve()
    plan, supervisor = read(root / 'plan.json'), read(root / 'supervisor.json')
    if supervisor['status'] not in ('complete', 'paused'):
        raise ValueError('Only terminal inventories can receive a final report')
    if checked(supervisor['plan']) != root / 'plan.json':
        raise ValueError('Supervisor belongs to a different plan')
    source_rows = plan['rows']
    tasks = list(dict.fromkeys(row['task_id'] for row in source_rows))
    if len(source_rows) != 32 or len(tasks) != 8:
        raise ValueError('Original logical panel must contain eight tasks and32 rows')
    rows, worker_intervals, used_attempts = [], [], set()
    for original in source_rows:
        slot = original['slot_id']
        state = supervisor['states'][slot]
        row = {key: original[key] for key in ('slot_id', 'task_id', 'condition', 'seed', 'first_member')}
        row.update(host_state=state['status'], started=False, submitted=None,
                   **{metric: None for metric in METRICS})
        for attempt in state['attempts']:
            identity = str(Path(attempt['output']).resolve())
            if identity in used_attempts or 'seconds' not in attempt:
                raise ValueError('Duplicated or unterminated worker interval')
            used_attempts.add(identity)
            worker_intervals.append({**{key: attempt.get(key) for key in (
                'output', 'pid', 'started_at', 'ended_at', 'seconds', 'exit_code', 'reason')},
                'gpu_index': worker_gpu_index(attempt)})
        folder = root / 'slots' / slot
        started, closed = folder / 'started.json', folder / 'closed.json'
        row['started'] = started.exists()
        if state['status'] == 'source_or_input_blocked':
            if row['started'] or state['attempts'] or closed.exists():
                raise ValueError('Blocked inventory acquired execution evidence')
            row['status'] = 'source_or_input_blocked'
            row['qualification'] = plan['blocked_cases'][original['task_id']]
        elif not row['started']:
            row['status'] = 'not_started'
        else:
            row['started_record'] = reference(started)
            row['status'] = 'technical_unknown'
            attempt = Path(read(started)['attempt'])
            report_path = attempt / 'report.json'
            if report_path.exists():
                report = read(report_path)
                row['worker_report'] = reference(report_path)
                if report.get('row') != original or checked(report['source_plan']) != root / 'plan.json':
                    raise ValueError('Report inventory or plan binding mismatch')
                result = report.get('result', {})
                row['raw_outcomes'] = {key: result.get(key) for key in (*METRICS, 'R_joint', 'submitted')}
                row['accounting'] = report.get('accounting')
                row['verdict'] = report.get('verdict')
                row['measurement_decision'] = report.get('measurement', {}).get('decision')
                row['usage'] = result.get('usage')
                row['boundary'] = result.get('boundary')
                row['host_final_test_executions'] = result.get('host_final_test_executions')
                if state['status'] == 'complete':
                    if (not closed.exists() or checked(read(closed)['report']) != report_path
                            or report.get('status') != 'closed' or row['verdict'].get('decision') != 'continue'
                            or row['measurement_decision'] != 'continue'):
                        raise ValueError('Host completion lacks its original closed receipt')
                    row.update(status='closed', submitted=result.get('submitted'),
                               **{metric: result.get(metric) for metric in METRICS})
            elif state['status'] == 'complete':
                raise ValueError('Completed slot lacks a report')
            if (attempt / 'interruption.json').exists():
                row['interruption'] = reference(attempt / 'interruption.json')
        rows.append(row)
    metrics = {}
    for metric in METRICS:
        metrics[metric] = {condition: bounded([row[metric] for row in rows if row['condition'] == condition])
                           for condition in CONDITIONS}
        metrics[metric]['paired'] = {f'{left}_minus_{right}': paired(rows, left, right, metric, tasks)
                                    for left, right in (('B', 'S_star'), ('Q_plus', 'B'), ('Q_minus', 'B'), ('Q_plus', 'Q_minus'))}
    seconds = sum(attempt['seconds'] for attempt in worker_intervals)
    return {'version': 'software-holdout-v051-final-v1',
            'created_at_beijing': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            'root': str(root), 'plan': reference(root / 'plan.json'),
            'supervisor': reference(root / 'supervisor.json'), 'host_status': supervisor['status'],
            'report_source': reference(__file__), 'admission': plan['model_admission'],
            'source_commit': plan['source_commit'], 'logical_slots': 32, 'logical_tasks': 8,
            'qualified_case_ids': plan['qualified_case_ids'], 'rows': rows, 'metrics': metrics,
            'status_counts': dict(Counter(row['status'] for row in rows)),
            'closed_successes': sum(row['status'] == 'closed' and row['F'] == 1 for row in rows),
            'closed_submitted_not_full': sum(row['status'] == 'closed' and row['F'] == 0 and row['submitted'] is True for row in rows),
            'closed_no_submit': sum(row['status'] == 'closed' and row['submitted'] is False for row in rows),
            'billing': supervisor['ledger'],
            'worker_cost': {'unique_intervals': len(worker_intervals), 'seconds': seconds,
                            'hours': seconds / 3600, 'intervals': worker_intervals},
            'original_records_modified': False, 'new_model_calls': 0, 'new_scoring_calls': 0,
            'new_tokenizer_calls': 0, 'new_parameter_updates': 0, 'new_backward_calls': 0,
            'scope': 'Original eight-task panel. Missing or blocked outcomes remain null. Old checkpoints under new execution conditions; do not merge with v050. Costs are HOLD only, without nested durations or previous stages.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Keep each final read-only receipt immutable')
    result = summarize(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': reference(args.output), 'status_counts': result['status_counts'],
                      'worker_hours': result['worker_cost']['hours']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
