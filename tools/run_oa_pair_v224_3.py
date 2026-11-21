"""Run and score every alternative from the only qualifying OA replay state."""
import argparse
import json
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_organization_api_v204 import Ledger
from proworksim.software_mapping_selector_v224 import evaluate, initialize, update

R = Path(__file__).resolve().parents[1]
P = R/'artifacts/software-benchmark-v224-3/pair-r1'
OUT = R/'runs/software-benchmark-v224-3/pair-r1/task-01'
OLD = R/'runs/software-benchmark-v222/paired4-r1/task-01'
L = R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'

def read(path):
    return json.loads(path.read_text())

def save(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def prepare():
    replay = read(P.parent/'oa-replay-r1/results.json')
    eligible = [row for row in replay['rows'] if row['alternative_count']]
    assert [row['slot'] for row in eligible] == ['v224.3:oa:mid-1']
    row = eligible[0]
    result = read(checked(row['receipt']))
    oldbank = read(OLD/'GEN-G/candidate-bank.json')
    state = read(checked(row['input']))['actual_decision_state']
    with sqlite3.connect('file:'+str(L)+'?mode=ro',uri=True) as db:
        n, = db.execute("SELECT sum(tokens) FROM requests WHERE slot=? AND status='settled'",(row['slot'],)).fetchone()
    keep = oldbank['candidates']['KEEP'].copy()
    keep.update(reason='Keep current scope, owners and dependencies',decision_assessment={'decision':'keep','demand_types':[],'reason':'Keep current arrangement'})
    c1, = result['alternatives']
    c1['decision_assessment'] = result['assessment']
    bank = {'candidates':{'KEEP':keep,'C1':c1},'actual_generator_tokens':n,'shared_graph_tokens':0,
            'prefix_tokens':state['prefix_tokens'],'remaining_branch_token_limit':5_000_000-state['prefix_tokens']-n,
            'decision_assessment':result['assessment']}
    planrow = next(x for x in read(R/'artifacts/software-benchmark-v222/protocol-r1/candidate-tasks.json')['rows'] if x['index']==1)
    assert planrow['instance_id']==row['instance'] and bank['prefix_tokens']==oldbank['prefix_tokens']
    checked(read(OLD/'PREFIX/result.json')['checkpoint'])
    P.mkdir(parents=True,exist_ok=False)
    save(P/'candidate-tasks.json',{'rows':[planrow]})
    save(P/'bank.json',bank)
    decision=evaluate(state,bank,initialize(),planrow['seed'])
    save(P/'decision.json',decision)
    paths=[P/'candidate-tasks.json',P/'bank.json',P/'decision.json',Path(__file__),R/'tools/run_oa_pair_episode_v224_3.py',R/'tools/score_project_relations_v222.py',OLD/'PREFIX/checkpoint/manifest.json']
    save(P/'deployment-freeze.json',{'files':[reference(path) for path in paths],
            'shared_runtime_freeze':reference(R/'artifacts/software-benchmark-v224-2/protocol-r1/deployment-freeze.json'),
            'both_arms_required':True,'single_development_state':True})

def execute():
    freeze=read(P/'deployment-freeze.json')
    for ref in freeze['files'] + read(checked(freeze['shared_runtime_freeze']))['files']:
        checked(ref)
    bank=read(P/'bank.json')
    limit=bank['remaining_branch_token_limit']
    OUT.mkdir(parents=True,exist_ok=False)
    ledger=object.__new__(Ledger)
    ledger.path=L
    with ledger.db() as db:
        assert db.execute("SELECT value FROM meta WHERE key='cap'").fetchone()==('1100000000000',)
        assert not db.execute("SELECT 1 FROM slots WHERE status!='closed'").fetchone()
        assert not db.execute("SELECT 1 FROM block_slots WHERE status='pending'").fetchone()
        assert db.execute('SELECT sum(cost) FROM requests').fetchone()[0]+limit*2*8000 <= 1000*10**9
        db.executemany("INSERT INTO block_slots VALUES(?,'v224.3:pair',?,'pending')",
                       [('v224.3:task-01:'+z,limit) for z in bank['candidates']])
    def command(script,args,log):
        with log.open('xb') as stream:
            subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,stdout=stream,stderr=subprocess.STDOUT,check=True)
    def branch(z):
        ep=OUT/z
        try:
            command('run_oa_pair_episode_v224_3.py',['--index',1,'--condition',z,'--output',ep,'--bank',P/'bank.json','--checkpoint',OLD/'PREFIX/checkpoint','--ledger',L], OUT/(z+'.log'))
            episode=read(ep/'result.json')
            if episode['status']!='closed':
                return {'known':False,'episode':episode}
            receipts={}
            for kind in ('code','delivery'):
                dest=OUT/(z+'-'+kind)
                command('score_project_relations_v222.py',['--index',1,'--kind',kind,'--episode',ep,'--output',dest],OUT/(z+'-'+kind+'.log'))
                receipts[kind]=read(dest/'receipt.json')
            return {'known':all(type(x.get('resolved')) is bool for x in receipts.values()),
                    'code_correct':receipts['code'].get('resolved'),'legal_correct':receipts['delivery'].get('resolved'),
                    'logical_tokens':read(ep/'cost-endpoints.json')['logical_total_tokens'],
                    'scores':{k:reference(OUT/(z+'-'+k)/'receipt.json') for k in receipts}}
        except Exception as err:
            return {'known':False,'error':str(err)}
        finally:
            with ledger.db() as db:
                db.execute("UPDATE block_slots SET status='not_started' WHERE slot=? AND status='pending' AND NOT EXISTS(SELECT 1 FROM slots WHERE id=?)",('v224.3:task-01:'+z,)*2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=dict(zip(bank['candidates'],pool.map(branch,bank['candidates'])))
    decision=read(P/'decision.json')
    fitted=update(initialize(),[{'index':1,'complete':all(v['known'] for v in outcomes.values()),'outcomes':outcomes,'decision':decision}],'development_replay')
    save(P/'result.json',{'outcomes':outcomes,'policy':fitted,'v225_started':False})

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['prepare','run'])
    (prepare if parser.parse_args().mode=='prepare' else execute)()
