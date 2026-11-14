"""Read-only current records for the four-task K0/K1/K2 pilot."""
from collections import Counter
import json
from pathlib import Path
import sqlite3
import time

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runs/software-benchmark-v203-2-3'
BATCH=BASE/'role-context-pilot12-r1'

def read(path):
    return json.loads(path.read_text()) if path.is_file() else None

def snapshot():
    active=read(BASE/'current-deployment.json') or {}
    batch=Path(active.get('batch_root',str(BATCH)))
    ledger=Path(active.get('ledger_path',str(BATCH/'ledgers/pilot.sqlite')))
    if not batch.resolve().is_relative_to(BASE.resolve()) or not ledger.resolve().is_relative_to(BASE.resolve()):
        raise ValueError('Deployment pointer escaped this experiment')
    plan=read(batch/'execution-plan.json') or {'rows':[]}
    group_by_slot={r['slot_id']:r['group_id'] for r in plan['rows']}
    groups={g:{'planned':4,'called_slots':set(),'requests':0,'input_tokens':0,'output_tokens':0,
               'known_total_tokens':0,'requests_without_usage':0} for g in ('K0','K1','K2')}
    path=ledger;states=Counter();cost=reservation=0
    if path.exists():
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            for row in db.execute('SELECT slot_id,status,usage_json,settled_nanoyuan,reserved_nanoyuan FROM requests'):
                g=groups[group_by_slot[row['slot_id']]];g['called_slots'].add(row['slot_id']);g['requests']+=1
                states[row['status']]+=1
                if row['usage_json']:
                    u=json.loads(row['usage_json']);g['input_tokens']+=u['prompt_tokens'];g['output_tokens']+=u['completion_tokens']
                    g['known_total_tokens']+=u['prompt_tokens']+u['completion_tokens']
                else:g['requests_without_usage']+=1
                if row['settled_nanoyuan'] is not None:cost+=row['settled_nanoyuan']
                elif row['status']!='settled':reservation+=row['reserved_nanoyuan']
    for g in groups.values():g['called_slots']=sorted(g['called_slots'])
    handoff=read(ROOT/'artifacts/software-benchmark-v203-2-3/cash-handoff-r3/handoff.json') or {}
    recovered = handoff.get('child_ledger') == str(ledger)
    prior_cost=handoff.get('parent_settled_nanoyuan',0) if recovered else 0
    prior_reservation=handoff.get('parent_uncertain_reserved_nanoyuan',0) if recovered else 0
    api=batch/'api-coordinator'
    return {'observed_unix':time.time(),'tasks':4,'planned_rounds':12,'cash_cap_CNY':130,
            'active_deployment':active or None,'batch_root':str(batch),'ledger_path':str(ledger),
            'conditions':groups,'physical_states':dict(states),'settled_cost_upper_CNY':cost/1e9,
            'current_ledger_cap_CNY':handoff['child_cap_nanoyuan']/1e9 if recovered else 130,
            'prior_attempt_cost_upper_CNY':prior_cost/1e9,
            'cumulative_cost_upper_CNY':(prior_cost+cost)/1e9,
            'prior_attempt_requests':handoff.get('parent_calls_preserved',0) if recovered else 0,
            'prior_attempt_tokens':handoff.get('parent_tokens_preserved',0) if recovered else 0,
            'cumulative_known_tokens':sum(g['known_total_tokens'] for g in groups.values())+(handoff.get('parent_tokens_preserved',0) if recovered else 0),
            'cumulative_uncertain_reservation_CNY':(reservation+prior_reservation)/1e9,
            'unresolved_request_reservation_CNY':reservation/1e9,
            'cash_not_including_team_admission_holds':True,
            'progress':read(api/'progress.json'),'engineering_gate':read(api/'engineering-gate.json'),
            'task_outcomes':read(api/'task-outcomes.json'),'finalization':read(api/'coordinator-finalization.json'),
            'launch':read(api/'launch-result.json'),'snapshot_is_not_live_process_proof':True}

if __name__=='__main__':print(json.dumps(snapshot(),ensure_ascii=False,indent=2))
