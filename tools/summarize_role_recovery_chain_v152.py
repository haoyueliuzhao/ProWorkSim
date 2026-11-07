"""Read-only current view of model, normal export, official scoring and shared cash.

Original v146 export errors are preserved; validated v149/v151 recovery is
reported separately rather than repeatedly calling those models unfinished.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT/'runs/software-benchmark-v146/api-recovery21-r1'
EXPORT = ROOT/'runs/software-benchmark-v149/closed-export-recovery-r1'
SCORING = ROOT/'runs/software-benchmark-v151/same-tree-score-handoff-r1'


def read(path, default=None):
    return json.loads(path.read_bytes()) if path.is_file() else default


def cash(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5) as db:
        db.execute('PRAGMA query_only=ON')
        rows = list(db.execute('SELECT status,reserved_nanoyuan,settled_nanoyuan,usage_json FROM requests'))
    settled = sum(r[2] for r in rows if r[0] == 'settled')
    inflight = sum(r[1] for r in rows if r[0] == 'reserved')
    unknown = sum(r[1] for r in rows if r[0] not in {'settled','reserved'})
    return {'settled_CNY': settled/1e9, 'inflight_reserved_CNY': inflight/1e9,
            'unknown_reserved_CNY': unknown/1e9, 'committed_upper_CNY': (settled+inflight+unknown)/1e9,
            'physical_request_statuses': dict(Counter(r[0] for r in rows)),
            'known_actual_tokens': sum(json.loads(r[3])['total_tokens'] for r in rows
                                      if r[0] == 'settled' and r[3]),
            'actual_usage_complete_for_all_request_records': all(r[0] == 'settled' for r in rows)}


def summarize():
    plan = read(MODEL/'execution-plan.json')
    model = read(MODEL/'api-coordinator/progress.json', {})
    scoring = read(SCORING/'watch-progress.json', {})
    targets = scoring.get('targets', {})
    result = []
    for first in [r for r in plan['rows'] if r['recovery_round'] == 1]:
        attempts = sorted([r for r in plan['rows'] if r['original_slot_id'] == first['original_slot_id']],
                          key=lambda r:r['recovery_round'])
        measured = []
        for row in attempts:
            index = row['slot_index']
            export = read(EXPORT/str(index)/'recovery-result.json')
            code, delivery = (targets.get(f'{index}:{endpoint}', {}) for endpoint in ('code','delivery'))
            if export is not None and (export.get('status') != 'recovered_closed_export'
                                       or export.get('slot_id') != row['slot_id']):
                raise ValueError('Export identity differs from its planned model attempt')
            code_known = export is not None and type(code.get('resolved')) is bool
            delivery_known = export is not None and type(delivery.get('resolved')) is bool
            measured.append({'slot_index':index, 'recovery_round':row['recovery_round'],
                'normal_work_exported': export is not None,
                'code_status':code.get('state','waiting_normal_export'),
                'code':code.get('resolved') if code_known else None,
                'delivery_status':delivery.get('state','waiting_normal_export'),
                'delivery':delivery.get('resolved') if delivery_known else None,
                'fully_measured':code_known and delivery_known,
                'entered':(MODEL/'episodes'/str(index)/'entered.json').exists()})
        # Never choose a better score. Prefer the first fully measured normal
        # recovery; the second identity exists only for technical interruption.
        selected = next((r for r in measured if r['fully_measured']), None)
        if selected is None:
            selected = next((r for r in measured if r['normal_work_exported']), measured[0])
        result.append({'original_slot_id':first['original_slot_id'], 'instance_id':first['instance_id'],
            'group_id':first['group_id'], 'selected_attempt':selected, 'attempts':measured,
            'independent_second_attempt_selected':selected['recovery_round']==2})
    groups = {}
    for group in ('FREE2','REVIEW2'):
        rows = [r['selected_attempt'] for r in result if r['group_id'] == group]
        groups[group] = {'planned_original_episodes':len(rows),
            'normal_work_exported':sum(r['normal_work_exported'] for r in rows),
            'code_scored':sum(type(r['code']) is bool for r in rows),
            'code_passed':sum(r['code'] is True for r in rows),
            'delivery_measured':sum(type(r['delivery']) is bool for r in rows),
            'delivery_passed':sum(r['delivery'] is True for r in rows),
            'fully_measured':sum(r['fully_measured'] for r in rows)}
    original = cash(ROOT/'runs/software-benchmark-v142/role-pilot40-r1/ledgers/pilot.sqlite')
    recovery = cash(ROOT/'runs/software-benchmark-v145/api-recovery-prepared-r1/ledger.sqlite')
    return {'observed_Asia_Shanghai':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'planned_original_episodes':21, 'conditional_extra_identities_not_new_tasks':21,
        'model_phase':model.get('phase'), 'active':model.get('generation_active'),
        'pending':model.get('generation_pending'), 'raw_model_prepared_statuses':model.get('prepared_statuses'),
        'normal_export_and_official_scoring':groups,
        'old_stopped_code_supplements_not_counted_as_new_normal_runs':True,
        'independent_second_attempts_selected':sum(r['independent_second_attempt_selected'] for r in result),
        'cash':{'cumulative_cap_CNY':450, 'original_pilot':original,'independent_recovery':recovery,
                'remaining_after_all_reservations_CNY':450-original['committed_upper_CNY']-recovery['committed_upper_CNY']},
        'source_progress_paths':[str(MODEL/'api-coordinator/progress.json'),str(SCORING/'watch-progress.json')],
        'rows':result}


if __name__ == '__main__':
    value = summarize()
    print(json.dumps({k:v for k,v in value.items() if k!='rows'}, ensure_ascii=False, indent=2))
