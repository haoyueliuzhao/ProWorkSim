"""One approved first-window supplement. Share the existing capped account and never reuse a slot."""
import sqlite3
from pathlib import Path
from run_graph_learning_window_v229 import ROOT,WindowLedger,read_json,save,checked,reference,update_window,Q0
from run_graph_learning_window_v229 import run_case as base_case,invoke as dispatch
from proworksim.software_fixed_organization_clone_v131 import clone_function

PLAN=ROOT/'artifacts/software-benchmark-v229/dev1-extension-r1'
OUT=ROOT/'runs/software-benchmark-v229/dev1-extension-r1'
ORIGINAL=ROOT/'runs/software-benchmark-v229/dev1-r1'


def invoke(script,args,destination,receipt):
    if script=='run_graph_learning_episode_v229.py':
        script='run_graph_learning_episode_v229_1.py'
    return dispatch(script,args,destination,receipt)


run_case=clone_function(base_case,{**base_case.__globals__,'OUT':OUT,'invoke':invoke})


def main():
    proof=read_json(PLAN/'freeze.json')
    for ref in proof['files']:checked(ref)
    authority=read_json(checked(proof['original_authority']))
    meter=WindowLedger(authority)
    plan=read_json(PLAN/'panel.json')
    rows=[plan['rows'][i] for i in plan['supplement_indices']]
    if len(rows)!=4 or len({r['instance_id'] for r in rows})!=4 or any(r['instance_id'] in plan['excluded_original_ids'] for r in rows):
        raise ValueError('Supplement identities overlap frozen design')
    if read_json(ORIGINAL/'window-result.json')['Q1_produced'] or meter.stage!=130_000_000_000:
        raise ValueError('Unexpected first window or cash authority')
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'launch.json').open('x') as f:
        import json
        json.dump({'freeze':reference(PLAN/'freeze.json'),'funding':'existing dev1 only'},f)
    policy=OUT/'Q0.json';save(policy,Q0);records=[];gated=False
    for row in rows:
        if gated:
            record={'instance_id':row['instance_id'],'status':'not_admitted_after_cash_gate'}
        else:
            try:record=run_case(row,policy,meter)
            except Exception as error:record={'instance_id':row['instance_id'],'status':'technical_unknown','error':repr(error)}
            gated=record['status']=='cash_not_admitted'
        save(OUT/f"result-{row['index']}.json",record)
        records.append(record)
    complete=[r for r in records if r['status']=='paired']
    update=update_window(Q0,complete,[r['instance_id'] for r in rows])
    with sqlite3.connect(f'file:{meter.path}?mode=ro',uri=True) as c:
        usage=c.execute("SELECT slot,status,count(*),sum(tokens),sum(cost) FROM requests WHERE slot LIKE 'v229:%' GROUP BY slot,status ORDER BY slot").fetchall()
    save(OUT/'window-result.json',{'cohort':'additional development only','tasks':[{k:v for k,v in r.items() if k in ('instance_id','status','error')} for r in records],
         'update':update,'Q1_produced':update['fitted'],'original_cohort':reference(ORIGINAL/'window-result.json'),
         'ledger_columns':['slot','status','requests','tokens','nanoyuan'],'dev1_usage_including_original':usage})


if __name__=='__main__':main()
