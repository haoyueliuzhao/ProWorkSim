"""Execute the frozen, paired development windows and stop at the first failed gate."""
import json
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import BoundedSemaphore

from proworksim.software_anomaly_budget_v226 import AnomalyLedger, AdmissionStopped
from proworksim.software_anomaly_selector_v226 import development_update
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'artifacts/software-benchmark-v227/window-r1'
OUT = ROOT / 'runs/software-benchmark-v227/development-r1'
DB = ROOT / 'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
scoring = BoundedSemaphore(2)


def read(path):
    return json.loads(path.read_bytes())


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json_bytes(data))


def invoke(script, args, destination, receipt):
    with destination.with_suffix('.log').open('xb') as log:
        result = subprocess.run([ROOT/'.venv/bin/python', ROOT/'tools/run_offline_scorer_v096.py',
                                 ROOT/'tools'/script, *map(str, args), '--output', destination],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    record = destination / receipt
    if record.exists():
        return read(record)
    return {'status': 'technical_unknown', 'returncode': result.returncode,
            'log': str(destination.with_suffix('.log'))}


def episode(row, name, policy):
    folder = OUT / f"task-{row['index']:02d}"
    folder.mkdir(exist_ok=True)
    return invoke('osa_episode_v227.py', ['--index', row['index'], '--condition', name,
                  '--policy', policy], folder / name, 'result.json')


def grade(row, name, result):
    if result['status'] != 'closed':
        return {'status': result['status'], 'error': result.get('error', result.get('log'))}
    folder = OUT / f"task-{row['index']:02d}"
    outcomes = {}
    for kind in ('code', 'delivery'):
        with scoring:
            receipt = invoke(row['scorer_script'], ['--index', row['source_index'], '--kind', kind,
                             '--episode', folder/name], folder/(name+'-'+kind), 'receipt.json')
        outcomes[kind] = receipt.get('resolved')
    return {'status': 'scored' if all(type(x) is bool for x in outcomes.values()) else 'scoring_unknown',
            'code_correct': outcomes['code'], 'legal_correct': outcomes['delivery'],
            'logical_tokens': result['logical_tokens'], 'anomaly_endpoint': result.get('anomaly_endpoint'),
            'worker_choice': result.get('worker_choice'), 'termination': result['termination']}


def run_window(rows, number, policy, ledger):
    theta = read(policy)
    limits = {f"v227:task-{row['index']:02d}:PREFIX": 5_000_000 for row in rows}
    ledger.reserve_panel(f'v227:w{number}:prefixes', limits)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(episode, row, 'PREFIX', policy) for row in rows]
        prefixes = [future.result() for future in futures]
    panels = []
    for row, prefix in zip(rows, prefixes, strict=True):
        task = f"task-{row['index']:02d}"
        panel = {'instance_id':row['instance_id'], 'split':'development', 'target_scene':row['target_scene'],
                 'policy_before':theta, 'complete':False, 'prefix_status':prefix['status']}
        if prefix['status'] == 'point_ready':
            bank = read(OUT/task/'PREFIX/bank.json')
            panel['decision'] = bank['decision']
            names = list(bank['candidates'])
            try:
                ledger.reserve_panel('v227:'+task+':branches', {f'v227:{task}:{n}':bank['limit'] for n in names})
            except AdmissionStopped as exc:
                panel['admission_error'] = str(exc)
            else:
                def branch(name):
                    return grade(row, name, episode(row, name, policy))
                with ThreadPoolExecutor(max_workers=2) as pool:
                    panel['outcomes'] = dict(zip(names, pool.map(branch, names), strict=True))
                sources = {source for c in bank['candidates'].values() for source in c['sources']}
                panel['complete'] = sources >= {'osa','worker'} and all(
                    r['status']=='scored' for r in panel['outcomes'].values())
        else:
            panel['baseline'] = grade(row, 'PREFIX', prefix)
        save(OUT/task/'panel.json', panel)
        panels.append(panel)
    update = development_update(theta, panels, window=number)
    save(OUT/f'window-{number}.json', {'panels':panels,'update':update})
    if number==2 and update['updated']:
        save(OUT/'c-only.json', development_update(theta,panels,window=2,novelty=False))
    return update


def main():
    for item in read(PLAN/'freeze.json')['files']:
        checked(item)
    rows = read(PLAN/'candidate-tasks.json')['rows']
    OUT.mkdir(parents=True,exist_ok=False)
    ledger = AnomalyLedger(DB,stage='v227',stage_cny=100)
    policy = OUT/'policy-0.json'
    save(policy,[0.0]*5)
    for number in (1,2):
        try:
            update = run_window(rows[(number-1)*2:number*2], number, policy, ledger)
        except Exception as error:
            save(OUT/'end.json',{'status':'window_error','window':number,'error':repr(error)})
            raise
        if not update['updated']:
            save(OUT/'end.json',{'status':'gate_closed','window':number,'reason':update['reason']})
            break
        policy = OUT/f'policy-{number}.json'
        save(policy,update['theta'])
    else:
        save(OUT/'end.json',{'status':'development_complete','confirmation_requires_frozen_policies':True})
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as db:
        costs=db.execute("SELECT slot,status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot GLOB 'v227*' GROUP BY slot,status").fetchall()
    save(OUT/'usage.json',{'columns':['slot','status','requests','tokens','yuan'],'rows':costs})


if __name__=='__main__':
    main()
