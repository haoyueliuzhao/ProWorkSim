"""Run the four prespecified first-window attempts; isolate faults and retain single-support tasks."""
import argparse
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import BoundedSemaphore
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_graph_budget_v229 import WindowLedger,AdmissionStopped
from proworksim.software_graph_policy_v229 import update_window,Q0
from proworksim.storage import atomic_write,json_bytes,read_json
from run_anomaly_development_v227 import invoke

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'artifacts/software-benchmark-v229/design-r1'
OUT=ROOT/'runs/software-benchmark-v229/dev1-r1'
SCORES=BoundedSemaphore(2)


def save(path,value):
    atomic_write(path,json_bytes(value))


def grade(row,folder,name,result):
    if result['status']!='closed':return result
    scores={}
    for kind in ('code','delivery'):
        dest=folder/(name+'-'+kind)
        with SCORES:
            r=invoke(row['scorer_script'],['--index',row['source_index'],'--kind',kind,'--episode',folder/name],dest,'receipt.json')
        receipt=dest/'receipt.json'
        scores[kind]={'resolved':r.get('resolved'),'status':r['status'],'receipt':reference(receipt) if receipt.exists() else None}
    result={**result,'official':scores,'legal_correct':scores['delivery']['resolved']}
    if name in ('KEEP','CHANGE'):
        result['checkpoint']=read_json(folder/name/'common-state.json')['checkpoint']
        change=read_json(folder/name/'assigned-graph.json')
        result.update(activated_option=change['decision']['option'],changed=change['changed'])
    return result


def run_case(row,policy,meter):
    case=f"task-{row['index']:02d}"
    folder=OUT/case;folder.mkdir()
    key='v229:'+case
    def execute(name):
        args=['--index',row['index'],'--condition',name,'--policy',policy]
        if name!='PREFIX':args+=['--prefix',folder/'PREFIX']
        result=invoke('run_graph_learning_episode_v229.py',args,folder/name,'result.json')
        return grade(row,folder,name,result)
    record={'instance_id':row['instance_id'],'phase':row['phase']}
    try:meter.reserve_case(key)
    except AdmissionStopped as exc:return {**record,'status':'cash_not_admitted','error':str(exc)}
    split=False
    try:
        prefix=execute('PREFIX')
        if prefix['status']!='point_ready':
            return {**record,'status':'no_observation' if prefix['status']=='closed' else 'prefix_unknown','natural_episode':prefix}
        bank=read_json(folder/'PREFIX/candidate-bank.json')
        arms=tuple(bank['decision']['q'])
        meter.split(key,arms,prefix['prefix_tokens']+bank['osa_tokens']);split=True
        with ThreadPoolExecutor(max_workers=2) as pool:
            fs={arm:pool.submit(execute,arm) for arm in arms};results={}
            for arm,future in fs.items():
                try:results[arm]=future.result()
                except Exception as exc:results[arm]={'status':'technical_unknown','error':repr(exc)}
        known=all(s.get('status')=='closed' and all(type(s['official'][k]['resolved']) is bool for k in ('code','delivery')) for s in results.values())
        status=('paired' if len(arms)==2 else 'single_response') if known else 'incomplete'
        return {**record,'status':status,'bank':bank,'arms':results}
    finally:
        if not split:meter.split(key,(),None)
        else:
            with meter.db() as c:
                for name in ('KEEP','CHANGE'):
                    c.execute("UPDATE block_slots SET status='not_started' WHERE slot=? AND status='pending'",(key+':'+name,))


def main():
    for x in read_json(PLAN/'freeze.json')['files']:checked(x)
    authority=read_json(OUT/'authority.json')
    if authority.get('phase')!='dev1' or not authority.get('approved'):raise ValueError('First window authority missing')
    runlock=OUT/'launch.json'
    with runlock.open('x') as f:f.write(json_bytes({'authority':reference(OUT/'authority.json'),'freeze':reference(PLAN/'freeze.json')}).decode())
    if authority['scope']=='independent':
        meter=WindowLedger.create_independent(authority)
    else:meter=WindowLedger(authority)
    rows=[r for r in read_json(PLAN/'panel.json')['rows'] if r['phase']=='dev1']
    assert len(rows)==4
    policy=OUT/'Q0.json';save(policy,Q0)
    def one(row):
        try:record=run_case(row,policy,meter)
        except Exception as exc:record={'status':'technical_unknown','instance_id':row['instance_id'],'error':repr(exc)}
        save(OUT/f"result-{row['index']}.json",record)
        return record
    # With less than two worst-case reservations available run serially to avoid artificial misses.
    lanes=2 if authority['stage_cap_CNY']>=160 else 1
    with ThreadPoolExecutor(max_workers=lanes) as pool:records=list(pool.map(one,rows))
    fitted=update_window(Q0,[r for r in records if r['status']=='paired'],[r['instance_id'] for r in rows])
    save(OUT/'window-result.json',{'tasks':[{k:v for k,v in r.items() if k in ('instance_id','status','error')} for r in records],
        'update':fitted,'Q1_produced':fitted['fitted']})
    with sqlite3.connect(f"file:{meter.path}?mode=ro",uri=True) as db:
        usage=list(db.execute("SELECT slot,status,count(*),sum(tokens),sum(cost) FROM requests WHERE slot GLOB 'v229:*' GROUP BY slot,status"))
    save(OUT/'physical-usage.json',{'columns':['slot','status','requests','tokens','nanoyuan'],'rows':usage})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.parse_args();main()
