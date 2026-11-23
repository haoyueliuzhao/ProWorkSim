"""Reserve complete pairs, release unused exposure, score closed candidates, retain misses."""
import argparse
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from proworksim.software_anomaly_budget_v226 import AnomalyLedger,AdmissionStopped
from proworksim.software_benchmark_candidates_v054 import checked
from run_anomaly_development_v227 import invoke,read,save

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'artifacts/software-benchmark-v228/control-r1'
OUT=ROOT/'runs/software-benchmark-v228/control-r1'
DB=ROOT/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
LIMIT=5_000_000


def run(row,meter):
    idx=row['index'];case=f'task-{idx:02d}';root=OUT/case;root.mkdir()
    slot=f'v228:{case}:'
    source=row.get('archived_prefix')
    prefix=Path(source) if source else root/'PREFIX'
    def episode(arm):
        args=['--index',idx,'--condition',arm]
        if arm!='PREFIX':args+=['--prefix',prefix]
        return invoke('run_graph_control_episode_v228.py',args,root/arm,'result.json')
    def grade(arm,result):
        if result['status']!='closed':return result
        receipt={}
        for kind in ('code','delivery'):
            record=invoke(row['scorer_script'],['--index',row['source_index'],'--kind',kind,'--episode',root/arm],
                          root/(arm+'-'+kind),'receipt.json')
            receipt[kind]={'status':record['status'],'resolved':record.get('resolved')}
        return {**result,'official':receipt}
    def release_pending(names):
        with meter.db() as db:
            for n in names:
                db.execute("UPDATE block_slots SET status='not_started' WHERE slot=? AND status='pending' AND NOT EXISTS (SELECT 1 FROM slots WHERE id=?)",(slot+n,slot+n))
    def reserve(limits):
        meter.reserve_panel('control:'+case,{slot+k:v for k,v in limits.items()})
    if source:
        proof=read(checked(row['checkpoint_manifest']))
        assert proof['identity']==row['checkpoint_id']
        prefix_tokens=proof['prefix_tokens']
    else:
        reserve({'PREFIX':LIMIT,'PAIR_HOLD':LIMIT})
        try:
            pre=episode('PREFIX')
        finally:
            release_pending(['PREFIX','PAIR_HOLD'])
        if pre['status']!='point_ready':
            return {'case':case,'status':'no_eligible_observation' if pre['status']=='closed' else 'prefix_unknown',
                    'result':grade('PREFIX',pre)}
        prefix_tokens=pre['prefix_tokens']
    reserve({arm:LIMIT-prefix_tokens for arm in ('W0','W1')})
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending={arm:pool.submit(lambda key:grade(key,episode(key)),arm) for arm in ('W0','W1')}
            arms={arm:f.result() for arm,f in pending.items()}
    finally:
        release_pending(['W0','W1'])
    complete=all(r['status']=='closed' and all(type(x['resolved']) is bool for x in r['official'].values()) for r in arms.values())
    return {'case':case,'status':'scored_pair' if complete else 'incomplete_pair','arms':arms}


def main(indices):
    for item in read(PLAN/'freeze.json')['files']:checked(item)
    OUT.mkdir(parents=True,exist_ok=True)
    meter=AnomalyLedger(DB,stage='v228',stage_cny=135)
    rows=read(PLAN/'panel.json')['rows']
    for i in indices:
        try:record=run(rows[i],meter)
        except AdmissionStopped as exc:
            record={'status':'complete_pair_cash_not_admitted','error':str(exc),'index':i}
        except Exception as exc:
            record={'status':'technical_unknown','error':repr(exc),'index':i}
        save(OUT/f'result-{i}.json',record)
        if record['status']=='complete_pair_cash_not_admitted':break
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as db:
        usage=list(db.execute("SELECT slot,status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot GLOB 'v228:*' GROUP BY slot,status"))
    save(OUT/f'ended-{indices[0]}.json',{'requested':indices,'usage':usage})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('indices',nargs='+',type=int)
    main(parser.parse_args().indices)
