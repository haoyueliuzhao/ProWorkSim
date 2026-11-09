"""Read-only canonical72 score/cash status; interrupted attempts retain their costs."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_bytes())


def summary():
    original = ROOT/'runs/software-benchmark-v157/communication-pilot24-r1'
    panel = load(original/'execution-plan-r2.json')['rows']
    expected = {(r['instance_id'], r['group_id']): r for r in panel}
    selected = {}
    def add(row, resolved, receipt, kind='official_report'):
        key = (row['instance_id'], row['group_id'])
        if key not in expected or key in selected or type(resolved) is not bool:
            raise ValueError('Never choose between multiple scored candidates or replace a task')
        selected[key] = {'instance_id': key[0], 'group_id': key[1], 'slot_id': row['slot_id'],
            'original_slot_id': expected[key]['slot_id'], 'R_code': resolved,
            'score_evidence': receipt, 'score_kind': kind}
    for version, folder in [(159, 'communication-pilot-recovery-r1'),
        (161, 'independent-technical-recovery-r1'), (169, 'communication-wave2-r2'),
        (170, 'completion-recovery13-r1')]:
        batch = ROOT/f'runs/software-benchmark-v{version}'/folder
        rows = load(batch/'execution-plan.json')['rows']
        for row in rows:
            path = batch/'grading'/('score-'+str(row['slot_index']))/'receipt.json'
            if not path.exists():
                continue
            value = load(path)
            if value.get('status') != 'official_report':
                continue
            if value['slot_id'] != row['slot_id'] or value['instance_id'] != row['instance_id']:
                raise ValueError('Scoring receipt crossed its task identity')
            add(row, value['resolved'], reference(path))
    classifications = ROOT/'artifacts/software-benchmark-v171/confirmed-candidate-failures-r1/canonical-overlay.json'
    for item in load(classifications)['rows']:
        row = next(r for r in panel if r['slot_id'] == item['original_slot_id'])
        add({**row, 'slot_id': item['attempt_slot_id']}, item['R_code'], reference(classifications),
            'confirmed_candidate_execution_failure')
    for version, folder in [(163, 'original-15703-rescore-r1'), (173, 'original-17002-rescore-r1')]:
        path = ROOT/f'runs/software-benchmark-v{version}'/folder/'coordinator/result.json'
        value = load(path)
        receipt = json.loads(checked(value['code_receipt']).read_bytes())
        if receipt['status'] != 'official_report' or receipt['resolved'] != value['R_code']:
            raise ValueError('Recovered official score has no matching report')
        row = next(r for r in panel if receipt['slot_id'].split(':completion-recovery-v170')[0] == r['slot_id'])
        add({**row, 'slot_id': receipt['slot_id']}, value['R_code'], reference(path),
            'original_candidate_recovered_official_report')
    if len(expected) != 72 or set(selected) != set(expected):
        raise ValueError('A planned task/condition is not resolved')
    ledger = original/'ledgers/pilot.sqlite'
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        requests = [dict(r) for r in db.execute('SELECT slot_id,status,usage_json,settled_nanoyuan FROM requests')]
    if any(r['status'] != 'settled' or r['usage_json'] is None for r in requests):
        raise ValueError('Pending/unknown requests must remain visible')
    by_slot = {}
    for request in requests:
        usage = json.loads(request['usage_json'])
        row = by_slot.setdefault(request['slot_id'], {'actual_tokens': 0, 'cash_nanoyuan': 0})
        row['actual_tokens'] += usage['total_tokens']
        row['cash_nanoyuan'] += request['settled_nanoyuan']
    for row in selected.values():
        row.update(by_slot[row['slot_id']])
    groups = {}
    for group in ('C0', 'C1', 'C2'):
        rows = [r for r in selected.values() if r['group_id'] == group]
        groups[group] = {'planned': len(rows), 'known': len(rows), 'correct': sum(r['R_code'] for r in rows),
            'mean_actual_tokens': sum(r['actual_tokens'] for r in rows)/len(rows)}
    return {'version': 'v172-canonical-completion-status-r1',
        'observed_utc': datetime.now(timezone.utc).isoformat(), 'planned_episodes': 72,
        'known_code_results': len(selected), 'correct_code': sum(r['R_code'] for r in selected.values()),
        'score_unknown': 0, 'groups': groups,
        'score_kinds': dict(Counter(r['score_kind'] for r in selected.values())),
        'canonical_results': sorted(selected.values(), key=lambda r: (r['instance_id'], r['group_id'])),
        'all_physical_requests': len(requests), 'all_called_attempts': len(by_slot),
        'all_attempts_actual_tokens': sum(r['actual_tokens'] for r in by_slot.values()),
        'all_attempts_cost_upper_nanoyuan': sum(r['cash_nanoyuan'] for r in by_slot.values()),
        'new_team_start_threshold_CNY': '550', 'started_teams_completed_above_threshold': True,
        'provider_invoice_claimed': False, 'ledger': str(ledger),
        'superseded_attempt_costs_retained': True, 'measurement_coverage_upgraded': False,
        'complete_communication_measurement_claimed': False,
        'note': 'Canonical outcomes follow the authorized technical recovery mapping, not best-of selection. '
            'Full communication-source/fidelity analysis is separate; original partial observations stay partial.'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    value = summary()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_new(args.output, value)
    print(json.dumps({k: v for k, v in value.items() if k != 'canonical_results'}, ensure_ascii=False))
