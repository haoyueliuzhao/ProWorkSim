"""Read-only live status for the original120 role-pilot attempts and common400 cap."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT/'runs/software-benchmark-v142/role-pilot40-r1'
STATE = BATCH/'deployment-v143'


def read(path):
    return json.loads(path.read_text())


def summarize():
    plan = read(STATE/'execution-plan.json')
    value = {'observed_Asia_Shanghai':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'deployment':'v143','runtime_root':str(STATE/'api-coordinator'),
        'planned_episodes':len(plan['rows']), 'planned_by_group':dict(Counter(r['organization_id'] for r in plan['rows'])),
        'budget_cap_CNY':400, 'additional_model_attempts':0, 'diagnostics':[]}
    for spec in plan['diagnostics']:
        folder = BATCH/f"diagnostic-{spec['index']}"
        row = {k:spec[k] for k in ('index','organization_id','instance_id')}
        if (folder/'result.json').exists():
            result=read(folder/'result.json')
            row.update(status=result.get('status'),passed=result.get('passed'),model_calls=result.get('model_calls'),
                       error=result.get('error'))
            if result.get('controller_result'):
                child=read(Path(result['controller_result']['path']))
                row['controller_peak']=child.get('process_resource_peak')
            if result.get('quiescence'):
                quiet=read(Path(result['quiescence']['path']))
                row['cleanup_complete']=quiet.get('quiescent') is True and quiet.get('all_owned_objects_removed') is True
        else:
            row.update(status='running_or_waiting' if folder.exists() else 'not_started',
                       actor_ready=(folder/'actor-ready.json').exists(),controller_ready=(folder/'controller-ready.json').exists())
        value['diagnostics'].append(row)
    qualification_file=STATE/'api-coordinator/qualification-status.json'
    if qualification_file.exists():
        states=read(qualification_file)['qualifications']
        qualified=0
        for state in states.values():
            if state.get('status')=='qualified' and isinstance(state.get('qualification'),dict):
                state=read(Path(state['qualification']['path']))
            if set(state)=={'path','sha256','bytes'}:
                state=read(Path(state['path']))
            qualified += state.get('passed') is True
        value['environment_qualified_tasks']=qualified
        value['environment_qualification_status_path']=str(qualification_file)
    receipts=[]
    for file in sorted((STATE/'grading').glob('control-v142-*/receipt.json')):
        record=read(file)
        receipts.append({'key':file.parent.name,'status':record.get('status'),'resolved':record.get('resolved')})
    value['environment_control_receipts']=receipts
    for name in ('progress.json','run-summary.json','task-outcomes.json','coordinator-finalization.json'):
        path=STATE/'api-coordinator'/name
        if path.exists():
            value[name]=read(path)
    ledger=BATCH/'ledgers/pilot.sqlite'
    if ledger.exists():
        with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True,timeout=5) as db:
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            rows=[dict(row) for row in db.execute('SELECT condition,status,reserved_nanoyuan,settled_nanoyuan,usage_json FROM requests')]
        costs={'settled':0,'reserved':0,'uncertain':0}
        groups={g:{'request_records':0,'settled_requests':0,'known_actual_tokens':0} for g in value['planned_by_group']}
        mapping={row['condition_id']:row['organization_id'] for row in plan['rows']}
        for row in rows:
            state=row['status']
            costs[state]=costs.get(state,0)+(row['settled_nanoyuan'] if state=='settled' else row['reserved_nanoyuan'])
            item=groups[mapping[row['condition']]]
            item['request_records']+=1
            if state=='settled' and row['usage_json']:
                item['settled_requests']+=1
                item['known_actual_tokens']+=json.loads(row['usage_json'])['total_tokens']
        value['cash']={key+'_CNY':val/1_000_000_000 for key,val in costs.items()}
        value['cash']['remaining_after_reservations_CNY']=400-sum(costs.values())/1_000_000_000
        value['usage_by_group']=groups
        value['actual_usage_complete']=all(row['status']=='settled' and row['usage_json'] for row in rows)
    else:
        value['cash']={'ledger_created':False,'settled_CNY':0,'remaining_CNY':400}
        value['actual_model_generation_entered']=False
    return value


if __name__=='__main__':
    print(json.dumps(summarize(),ensure_ascii=False,indent=2))
