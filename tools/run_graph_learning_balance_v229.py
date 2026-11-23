"""Continue the frozen dev1 supplement with a cash balance amendment on the same ledger."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_graph_learning_episode_v229_1 as previous_episode
import run_graph_learning_window_v229 as window
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_graph_budget_v229 import WindowLedger
from proworksim.software_graph_policy_v229 import Q0,update_window
from proworksim.software_benchmark_candidates_v054 import checked,reference
from proworksim.storage import json_bytes,atomic_write,read_json

ROOT=window.ROOT
PLAN=ROOT/'artifacts/software-benchmark-v229/dev1-balance90-r1'
OUT=ROOT/'runs/software-benchmark-v229/dev1-balance90-r1'
AUTH=PLAN/'authority.json'


class ExactLedger(WindowLedger):
    def __init__(self, authority):
        self.path=Path(authority['ledger'])
        self.cap=self.stage=authority['new_cap_nanoyuan']
        if type(self.cap)!=int or self.cap<=0 or not self.path.is_file():
            raise ValueError('Existing account and exact integer cap required')


def amend(authority):
    meter=ExactLedger(authority)
    with meter.db() as db:
        old=db.execute("SELECT value FROM meta WHERE key='cap'").fetchone()
        spend=db.execute("SELECT coalesce(sum(cost),0) FROM requests WHERE status='settled'").fetchone()[0]
        if (old!=(str(authority['old_cap_nanoyuan']),) or spend!=authority['settled_nanoyuan_at_amendment']
                or meter.cap-spend!=90_000_000_000):
            raise ValueError('Balance or previous cap changed; amendment not applied')
        if (db.execute("SELECT 1 FROM slots WHERE status!='closed'").fetchone()
                or db.execute("SELECT 1 FROM block_slots WHERE status='pending'").fetchone()
                or db.execute("SELECT 1 FROM requests WHERE status='reserved'").fetchone()):
            raise ValueError('Cannot amend a nonquiescent account')
        db.execute("INSERT INTO meta(key,value) VALUES('v229_balance90_r1',?)",(json_bytes(authority).decode(),))
        db.execute("UPDATE meta SET value=? WHERE key='cap'",(str(meter.cap),))
    return meter


def invoke(script,args,destination,receipt):
    if script=='run_graph_learning_episode_v229.py':
        script=Path(__file__).name
    return window.invoke(script,args,destination,receipt)


def run():
    for r in read_json(PLAN/'freeze.json')['files']:checked(r)
    plan=read_json(PLAN/'panel.json')
    rows=[plan['rows'][i] for i in plan['supplement_indices']]
    OUT.mkdir(parents=True,exist_ok=False)
    meter=amend(read_json(AUTH))
    atomic_write(OUT/'launch.json',json_bytes({'authority':reference(AUTH),'freeze':reference(PLAN/'freeze.json')}))
    policy=OUT/'Q0.json';atomic_write(policy,json_bytes(Q0))
    execute=clone_function(window.run_case,{**window.run_case.__globals__,'OUT':OUT,'invoke':invoke})
    records=[];gated=False
    for row in rows:
        if gated:record={'instance_id':row['instance_id'],'status':'not_admitted_after_cash_gate'}
        else:
            try:record=execute(row,policy,meter)
            except Exception as exc:record={'instance_id':row['instance_id'],'status':'technical_unknown','error':repr(exc)}
            gated=record['status']=='cash_not_admitted'
        atomic_write(OUT/f"result-{row['index']}.json",json_bytes(record));records.append(record)
    update=update_window(Q0,[r for r in records if r['status']=='paired'],[r['instance_id'] for r in rows])
    with meter.db() as db:
        usage=db.execute("SELECT slot,status,count(*),sum(tokens),sum(cost) FROM requests GROUP BY slot,status ORDER BY slot").fetchall()
    atomic_write(OUT/'window-result.json',json_bytes({'tasks':[{k:v for k,v in r.items() if k in ('instance_id','status','error')} for r in records],
        'update':update,'Q1_produced':update['fitted'],'ledger_columns':['slot','status','requests','tokens','nanoyuan'],'usage':usage}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--index',type=int);parser.add_argument('--condition',choices=['PREFIX','KEEP','CHANGE'])
    parser.add_argument('--output',type=Path);parser.add_argument('--policy',type=Path);parser.add_argument('--prefix',type=Path)
    args=parser.parse_args()
    if args.run:run()
    else:
        if args.index not in read_json(PLAN/'panel.json')['supplement_indices'] or args.output!=OUT/f'task-{args.index:02d}'/args.condition:
            parser.error('Outside frozen task identity')
        clone_function(previous_episode.main,{**previous_episode.main.__globals__,'PLAN':PLAN,'AUTH':AUTH,'WindowLedger':ExactLedger})(args)
