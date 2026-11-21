"""Freeze the input policy, scores and matched candidate panels for development window two."""
import argparse
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_mapping_selector_v224 import evaluate, initialize, update
from proworksim.software_organization_api_v204 import Ledger
from replay_oa_window2_v224_4 import ROOT, PLAN, prepare, read, save

PUBLIC = ROOT/'artifacts/software-benchmark-v224-4/window2-r1'
OUT = ROOT/'runs/software-benchmark-v224-4/window2-r1'
ARCHIVE = ROOT/'runs/software-benchmark-v223-1/paired4-r1'
DATABASE = ROOT/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
SCORER = ROOT/'tools/score_organization_demand_v223_1.py'
EPISODE = ROOT/'tools/run_window2_episode_v224_4.py'

def seal():
    prepare()
    plan = read(PLAN)
    q1 = read(checked(plan['policy_input']))['policy']
    assert q1['update'] == 1
    PUBLIC.mkdir(parents=True, exist_ok=False)
    rows = read(ROOT/'artifacts/software-benchmark-v223-1/protocol-r1/candidate-tasks.json')['rows']
    selected = [r for r in rows if r['index'] in (2,3)]
    assert [r['instance_id'] for r in selected] == [r['instance'] for r in plan['rows']]
    save(PUBLIC/'candidate-tasks.json',{'rows':selected})
    save(PUBLIC/'q1.json', q1)
    for row in plan['rows']:
        checked(row['checkpoint'])
        checked(row['graph'])
    paths = [Path(__file__),EPISODE,SCORER,PLAN,PUBLIC/'q1.json',PUBLIC/'candidate-tasks.json']
    save(PUBLIC/'deployment-freeze.json',{'files':[reference(p) for p in paths],
         'shared_runtime':reference(ROOT/'artifacts/software-benchmark-v224-2/protocol-r1/deployment-freeze.json'),
         'decision':'Q1 applied before outcomes; run every retained branch; one update after both tasks',
         'reservation':'atomic per panel in original order, preserve 100 CNY for confirmation',
         'no_replacements':True,'v225_started':False})

def make_panel(row,q1):
    i=row['index']
    key=f'task-{i:02d}'
    state=read(checked(row['input']))['actual_decision_state']
    oa=read(checked(row['receipt']))
    old=ARCHIVE/key
    graph=read(checked(row['graph']))
    assert graph['status']=='graph_context_ready'
    with sqlite3.connect('file:'+str(DATABASE)+'?mode=ro',uri=True) as db:
        n=db.execute("SELECT coalesce(sum(tokens),0) FROM requests WHERE slot=? AND status='settled'",(row['slot'],)).fetchone()[0]
    keep=read(old/'GEN-W1/candidate-bank.json')['candidates']['KEEP'].copy()
    keep.update(reason='Keep the checkpoint arrangement',decision_assessment={'decision':'keep','demand_types':[],'reason':'Retain the checkpoint arrangement.'})
    candidates={'KEEP':keep}
    for j,candidate in enumerate(oa['alternatives'],start=1):
        candidates[f'C{j}']={**candidate,'decision_assessment':oa['assessment']}
    assessment=oa.get('assessment',keep['decision_assessment'])
    bank={'candidates':candidates,'decision_assessment':assessment,'actual_generator_tokens':n,
          'shared_graph_tokens':graph['shared_graph_tokens'],'prefix_tokens':state['prefix_tokens'],
          'remaining_branch_token_limit':5_000_000-state['prefix_tokens']-graph['shared_graph_tokens']-n,
          'oa_result':oa['result']}
    task=next(r for r in read(PUBLIC/'candidate-tasks.json')['rows'] if r['index']==i)
    decision=evaluate(state,bank,q1,task['seed'])
    base=evaluate(state,bank,initialize(),task['seed'])
    dest=PUBLIC/key
    dest.mkdir()
    save(dest/'bank.json',bank)
    save(dest/'decision.json',{'q1':decision,'q0':base})
    return bank,decision

def cmd(script,args,log):
    with log.open('xb') as stream:
        subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/run_offline_scorer_v096.py'),str(script),*map(str,args)],
                       cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)

def solve(i,label):
    key=f'task-{i:02d}'
    root=OUT/key
    ep=root/label
    slot=f'v224.4:{key}:{label}'
    try:
        cmd(EPISODE,['--index',i,'--condition',label,'--output',ep,'--bank',PUBLIC/key/'bank.json',
                     '--checkpoint',ARCHIVE/key/'PREFIX/checkpoint','--ledger',DATABASE],root/(label+'.log'))
        result=read(ep/'result.json')
        if result['status']!='closed':
            return {'known':False,'generation':result}
        scores={}
        for endpoint in ('code','delivery'):
            path=root/(label+'-'+endpoint)
            cmd(SCORER,['--index',i,'--kind',endpoint,'--episode',ep,'--output',path],path.with_suffix('.log'))
            scores[endpoint]=read(path/'receipt.json')
        return {'known':all(type(r.get('resolved')) is bool for r in scores.values()),
                'code_correct':scores['code'].get('resolved'),'legal_correct':scores['delivery'].get('resolved'),
                'logical_tokens':read(ep/'cost-endpoints.json')['logical_total_tokens'],
                'scores':{k:reference(root/(label+'-'+k)/'receipt.json') for k in scores}}
    except Exception as exc:
        return {'known':False,'error':repr(exc)}
    finally:
        with sqlite3.connect(DATABASE,timeout=60) as db:
            db.execute("UPDATE block_slots SET status='not_started' WHERE slot=? AND status='pending' AND NOT EXISTS(SELECT 1 FROM slots WHERE id=?)",(slot,slot))

def execute():
    freeze=read(PUBLIC/'deployment-freeze.json')
    for ref in freeze['files']+read(checked(freeze['shared_runtime']))['files']:
        checked(ref)
    q1=read(PUBLIC/'q1.json')
    OUT.mkdir(parents=True,exist_ok=False)
    cmd(ROOT/"tools/replay_oa_window2_v224_4.py",["run"],OUT/"oa.log")
    records=[]
    ledger=object.__new__(Ledger)
    ledger.path=DATABASE
    rows=read(PLAN.with_name('results.json'))['rows']
    # Both banks and Q0/Q1 draws are fixed before any successor is observed.
    panels=[make_panel(row,q1) for row in rows]
    for row,(bank,decision) in zip(rows,panels):
        i=row['index']
        key=f'task-{i:02d}'
        (OUT/key).mkdir(parents=True,exist_ok=False)
        labels=list(bank['candidates'])
        limit=bank['remaining_branch_token_limit']
        with ledger.db() as db:
            assert not db.execute("SELECT 1 FROM slots WHERE status!='closed'").fetchone()
            assert not db.execute("SELECT 1 FROM block_slots WHERE status='pending'").fetchone()
            admitted=db.execute('SELECT sum(cost) FROM requests').fetchone()[0]+len(labels)*limit*8000<=1000*10**9
            if admitted:
                db.executemany("INSERT INTO block_slots VALUES(?, 'v224.4:dev2', ?, 'pending')",
                               [(f'v224.4:{key}:{z}',limit) for z in labels])
        outcomes={}
        if admitted:
            with ThreadPoolExecutor(max_workers=len(labels)) as pool:
                outcomes=dict(zip(labels,pool.map(lambda z:solve(i,z),labels)))
        item={'index':i,'instance':row['instance'],'decision':decision,'outcomes':outcomes,
              'complete':admitted and all(v['known'] for v in outcomes.values()),'cash_admitted':admitted}
        save(PUBLIC/key/'outcomes.json',item)
        records.append(item)
    q2=update(q1,records,'development_window_two')
    with ledger.db() as db:
        costs=db.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot GLOB 'v224.4:*' GROUP BY status").fetchall()
        spent=db.execute("SELECT sum(cost)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
    save(PUBLIC/'result.json',{'records':records,'policy':q2,'weights_changed':q2['theta']!=q1['theta'],
                               'ledger':costs,'remaining_CNY':1100-spent,'confirmation_started':False})

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['seal','run'])
    (seal if parser.parse_args().mode=='seal' else execute)()
