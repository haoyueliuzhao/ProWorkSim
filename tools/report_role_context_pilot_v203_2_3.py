"""Read-only report totals, including prior failed attempts, from provider usage."""
from collections import defaultdict
from pathlib import Path
import hashlib,json,sqlite3
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runs/software-benchmark-v203-2-3/role-context-recovery12-r3'
OUT=ROOT/'artifacts/software-benchmark-v203-2-3/final-report-r1'

def load(p):return json.loads(p.read_bytes())
def ref(p):
    b=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
def zero():return {'calls':0,'input':0,'output':0,'tokens':0,'cash_nanoyuan':0}
def add(v,r):
    u=json.loads(r['usage_json']);v['calls']+=1;v['input']+=u['prompt_tokens'];v['output']+=u['completion_tokens'];v['tokens']+=u['prompt_tokens']+u['completion_tokens'];v['cash_nanoyuan']+=r['settled_nanoyuan']
def main():
    plan=load(BASE/'execution-plan.json');byid={r['slot_id']:r for r in plan['rows']}
    final_path=ROOT/'artifacts/software-benchmark-v203-2-3/terminal-repair-r5/final-summary.json';final=load(final_path)
    results={r['slot_id']:r['resolved'] for r in final['rows']}
    groups=defaultdict(zero);members=defaultdict(zero);purposes=defaultdict(zero);tasks=defaultdict(zero)
    db=sqlite3.connect((BASE/'ledgers/recovery.sqlite').resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    rows=[dict(r) for r in db.execute('SELECT request_id,slot_id,member_id,usage_id,status,usage_json,settled_nanoyuan FROM requests ORDER BY request_id')];db.close()
    for r in rows:
        assert r['status']=='settled';add(groups[byid[r['slot_id']]['group_id']],r);add(tasks[r['slot_id']],r);add(members[r['member_id']],r);add(purposes[r['usage_id']],r)
    detail=[]
    for r in plan['rows']:
        k=r['slot_id'];v=tasks.get(k);gate=False
        if v:
            controller=BASE/'episodes'/str(r['slot_index'])/'controller-output/controller-result.json'
            b=load(controller)['managed_boundary'];gate=any(x.get('status')=='team_budget_exhausted' for x in b['terminal_details'].values())
        detail.append({'task':r['instance_id'],'condition':r['group_id'],'slot_id':k,'called':bool(v),'usage':v,'code_resolved':results.get(k),'budget_gate':gate,'normal_generation_valid':False})
    common=set.intersection(*[{r['task'] for r in detail if r['called'] and r['condition']==g} for g in ('K0','K1','K2')])
    for g,v in groups.items():
        selected=[r for r in detail if r['condition']==g and r['called']];matched=[r for r in selected if r['task'] in common]
        v.update(planned=4,called=len(selected),code_passed=sum(r['code_resolved'] is True for r in selected),mean_tokens_called=v['tokens']/len(selected),mean_API_requests_called=v['calls']/len(selected),cash_CNY=v['cash_nanoyuan']/1e9,common_tasks=len(matched),common_passed=sum(r['code_resolved'] is True for r in matched),common_mean_tokens=sum(r['usage']['tokens'] for r in matched)/len(matched),common_mean_API_requests=sum(r['usage']['calls'] for r in matched)/len(matched))
    prior=load(ROOT/'artifacts/software-benchmark-v203-2-3/cash-handoff-r3/handoff.json')
    total={key:sum(v[key] for v in groups.values()) for key in zero()}
    assert total['tokens']==54670031 and total['calls']==1069 and len(results)==11
    d={'version':'v203.2.3-final-report-r1','report_date':'2026-11-15','groups':dict(groups),'tasks':detail,'by_member':dict(members),'by_purpose':dict(purposes),'current_attempt_totals':total,'prior_interrupted_attempts':{'rounds':9,'calls':prior['parent_calls_preserved'],'tokens':prior['parent_tokens_preserved'],'cash_CNY':prior['parent_settled_nanoyuan']/1e9},'all_attempts':{'rounds_called':20,'calls':total['calls']+prior['parent_calls_preserved'],'tokens':total['tokens']+prior['parent_tokens_preserved'],'cash_upper_CNY':(total['cash_nanoyuan']+prior['parent_settled_nanoyuan'])/1e9},'supplemental_results':{'scored':11,'passed':8,'failed':3,'scoring_unknown':0,'unstarted':1,'budget_gate_rounds':sum(r['budget_gate'] for r in detail)},'budget_CNY':130,'remaining_CNY':final['remaining_API_budget_CNY'],'new_API_calls_for_report':0,'context_effect_identified':False,'common_tasks':sorted(common),'sources':{'plan':ref(BASE/'execution-plan.json'),'supplemental_scores':ref(final_path),'handoff':ref(ROOT/'artifacts/software-benchmark-v203-2-3/cash-handoff-r3/handoff.json'),'selected_provider_rows_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),'provider_sqlite':str(BASE/'ledgers/recovery.sqlite')}}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'summary.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:d[k] for k in ['groups','by_purpose','all_attempts','supplemental_results']},ensure_ascii=False))
if __name__=='__main__':main()
