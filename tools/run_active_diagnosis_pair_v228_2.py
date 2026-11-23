"""Independent corrected-evidence pair. Preserves both earlier Astropy arms and the eight-task panel."""
import argparse
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.software_anomaly_budget_v226 import AnomalyLedger
from proworksim.software_benchmark_candidates_v054 import checked,reference
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import atomic_write,json_bytes,read_json
from run_anomaly_development_v227 import invoke
from run_graph_control_episode_v228_1 import main as episode
from report_graph_control_v228 import arm_receipts

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'artifacts/software-benchmark-v228/diagnosis-supplement-r1'
RUN=ROOT/'runs/software-benchmark-v228/supplement-r1/astropy-evidence-r2'
DB=ROOT/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
ENTRY=Path(__file__).name
ARMS=('W0','W1')


def run_pair():
    for f in read_json(PLAN/'freeze.json')['files']:checked(f)
    row,=read_json(PLAN/'panel.json')['rows']
    prefix=Path(row['archived_prefix'])
    manifest=read_json(checked(row['checkpoint_manifest']))
    if manifest['identity']!=row['checkpoint_id']:raise ValueError('Unknown checkpoint')
    remaining=5_000_000-manifest['prefix_tokens']
    meter=AnomalyLedger(DB,stage='v228',stage_cny=135)
    slots={arm:f'v228:{RUN.name}:{arm}' for arm in ARMS}
    RUN.mkdir(parents=True,exist_ok=False)
    meter.reserve_panel(RUN.name,{s:remaining for s in slots.values()})

    def branch(arm):
        ep=RUN/arm
        result=invoke(ENTRY,['--index',0,'--condition',arm,'--prefix',prefix],ep,'result.json')
        if result['status']=='closed':
            scores={}
            for kind in ('code','delivery'):
                score=invoke(row['scorer_script'],['--index',row['source_index'],'--kind',kind,'--episode',ep],
                             RUN/f'{arm}-{kind}','receipt.json')
                scores[kind]={k:score.get(k) for k in ('status','resolved')}
            result={**result,'official':scores}
        return arm_receipts(RUN,arm,result)

    arms={}
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures={arm:pool.submit(branch,arm) for arm in ARMS}
            for arm,future in futures.items():
                try:arms[arm]=future.result()
                except Exception as error:arms[arm]={'status':'technical_unknown','error':repr(error)}
    finally:
        with meter.db() as db:
            for slot in slots.values():
                db.execute("UPDATE block_slots SET status='not_started' WHERE slot=? AND status='pending' AND NOT EXISTS(SELECT 1 FROM slots WHERE id=?)",(slot,slot))
    paired=all(r.get('checkpoint')==manifest['identity'] and r.get('decision_remaining_tokens')==remaining and
               all(type(r.get('official',{}).get(k,{}).get('resolved')) is bool for k in ('code','delivery')) for r in arms.values())
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as db:
        usage=list(db.execute('SELECT slot,status,count(*),sum(tokens),sum(cost) FROM requests WHERE slot IN (?,?) GROUP BY slot,status ORDER BY slot,status',tuple(slots.values())))
    result={'study':'v228.2 separate exposed mechanism replication','instance_id':row['instance_id'],
            'checkpoint':manifest['identity'],'complete_pair':paired,'arms':arms,'ledger_columns':['slot','status','requests','tokens','nanoyuan'],
            'usage':usage,'original_panel':reference(ROOT/'artifacts/software-benchmark-v228/paired-audit-r1/final-evidence.json'),
            'CN_updates':0,'pool_with_original':False}
    atomic_write(RUN/'summary.json',json_bytes(result))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--run-pair',action='store_true')
    p.add_argument('--index',type=int);p.add_argument('--condition',choices=ARMS)
    p.add_argument('--output',type=Path);p.add_argument('--prefix',type=Path)
    a=p.parse_args()
    if a.run_pair:run_pair()
    else:
        row,=read_json(PLAN/'panel.json')['rows']
        if a.index!=0 or a.condition not in ARMS or a.output!=RUN/a.condition or a.prefix!=Path(row['archived_prefix']):
            p.error('Only the two frozen independent continuations are supported')
        clone_function(episode,{**episode.__globals__,'PLAN':PLAN})(a)
