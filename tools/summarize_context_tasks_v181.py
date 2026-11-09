"""Read-only status: task denominators, official endpoints and the actual cash ledger."""
import json
import sqlite3
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v181/full-context-pilot-r1'


def read(path):return json.loads(path.read_bytes()) if path.is_file() else {}


def summary():
    plan=read(RUN/'execution-plan.json');progress=read(RUN/'api-coordinator/progress.json')
    layers=[progress]
    for folder in ('software-benchmark-v182/context-continuation-r1','software-benchmark-v184/pylint-completion-r1'):
        value=read(ROOT/'runs'/folder/'api-coordinator/progress.json')
        if value:layers.append(value)
    combined={'records':{},'scores':{},'exceptions':{},'generation_active':0,'grading_active':0}
    for value in layers:
        for key in ('records','scores','exceptions'):combined[key].update(value.get(key,{}))
        for key in ('generation_active','grading_active'):combined[key]+=value.get(key,0)
    combined['stage']='generation_and_async_scoring' if any(v.get('stage')=='generation_and_async_scoring' and v.get('generation_active',0)+v.get('grading_active',0)>0 for v in layers) else layers[-1].get('stage')
    combined['qualified_environments']=max(v.get('qualified_environments',0) for v in layers)
    repaired=read(ROOT/'runs/software-benchmark-v184/pylint-completion-r1/grading-coordinator/qualifications/pylint-dev__pylint-8898.json')
    if repaired.get('passed'):
        combined['qualified_environments']=12
        combined['exceptions'].pop('qualification:pylint-dev__pylint-8898',None)
    combined['generation_inflight_or_waiting']=combined['generation_active']
    combined['generation_active']=len(list((RUN/'resource-claims').glob('active-actor-*.json')))
    progress=combined
    rows={r['slot_id']:r for r in plan['rows']};groups={}
    ledger=ROOT/'runs/software-benchmark-v175/context-replay-r1/api-ledger.sqlite'
    with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        cumulative=db.execute("SELECT SUM(CASE WHEN status='settled' THEN cost ELSE 0 END) paid,SUM(CASE WHEN status!='settled' THEN reserved ELSE 0 END) held FROM requests").fetchone()
        calls=[dict(r) for r in db.execute("SELECT * FROM requests WHERE job_id LIKE 'v181:%'")]
        recovery_exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='zero_call_recoveries_v182'").fetchone()
        recovered=[r[0] for r in db.execute('SELECT job_id FROM zero_call_recoveries_v182')] if recovery_exists else []
    for slot in recovered:
        record=progress['records'].get(slot,{})
        if record.get('error',{}).get('type')=='FileExistsError' and not record.get('result'):progress['records'].pop(slot,None)
        if progress['exceptions'].get(slot,{}).get('type')=='FileExistsError':progress['exceptions'].pop(slot,None)
    for group in ('M0','M1-5','M1-10','M3-R'):
        items=[r for r in rows.values() if r['group_id']==group]
        primary={r['slot_id'] for r in items if r['primary_panel']}
        finished=[v for s,v in progress.get('records',{}).items() if s in primary]
        code=[v for v in progress.get('scores',{}).values() if v['slot_id'] in primary and v['endpoint']=='code']
        delivery=[v for v in progress.get('scores',{}).values() if v['slot_id'] in primary and v['endpoint']=='delivery']
        billed=[c for c in calls if c['job_id'] in primary and c['status']=='settled']
        usage=[json.loads(c['usage']) for c in billed]
        known=sum(u['total_tokens'] for u in usage)
        closed={v['row']['slot_id'] for v in finished if v['status']=='closed'}
        closed_tokens=sum(json.loads(c['usage'])['total_tokens'] for c in billed if c['job_id'] in closed)
        groups[group]={'primary_planned':len(primary),'repeat_planned':len(items)-len(primary),
            'primary_generation_states':dict(Counter(v['status'] for v in finished)),
            'primary_code_scored':sum(type(v.get('resolved')) is bool for v in code),
            'primary_code_pass':sum(v.get('resolved') is True for v in code),
            'primary_delivery_known':sum(type(v.get('resolved')) is bool for v in delivery),
            'primary_delivery_pass':sum(v.get('resolved') is True for v in delivery),
            'primary_actual_tokens_so_far':known,'closed_primary_mean_actual_tokens':closed_tokens/len(closed) if closed and not any(c['job_id'] in closed and c['status']!='settled' for c in calls) else None,
            'primary_paid_upper_CNY':sum(c['cost'] for c in billed)/1e9,
            'score_denominator_is_not_completed_subset':True}
    diagnostics=[read(p) for p in RUN.glob('diagnostic-*/result.json')]
    return {'stage':progress.get('stage','initializing'),'diagnostics_passed':sum(d.get('passed') is True for d in diagnostics),
        'qualified_environments':progress.get('qualified_environments',0),
        'generation_active':progress.get('generation_active',0),'generation_inflight_or_waiting':progress.get('generation_inflight_or_waiting',0),'grading_active':progress.get('grading_active',0),
        'groups':groups,'physical_requests_this_phase':len(calls),
        'physical_statuses_this_phase':dict(Counter(c['status'] for c in calls)),
        'cumulative_paid_upper_CNY':(cumulative['paid'] or 0)/1e9,
        'cumulative_unknown_or_live_upper_CNY':(cumulative['held'] or 0)/1e9,
        'nominal_new_admission_limit_CNY':250,'active_tasks_may_finish_above_limit':True,
        'exceptions':progress.get('exceptions',{}),'coordinator_error':read(RUN/'api-coordinator/coordinator-error.json'),
        'recovered_zero_call_startups':recovered,'readonly':True,'old_reports_rewritten':False}


if __name__=='__main__':print(json.dumps(summary(),ensure_ascii=False,indent=2))
