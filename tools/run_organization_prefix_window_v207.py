"""Prepare exactly the frozen three development prefixes; no automatic replacements."""
import argparse,json,os,subprocess,concurrent.futures
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--window',type=int,choices=[1,2],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=R/'runs/software-benchmark-v204';ledger=root/'cn-pilot-r1/ledger.sqlite'
if json.loads((root/'admission-feedback-gate.json').read_text())['passed']is not True:raise ValueError('Real feedback gate not passed')
if a.window==2 and not (root/'policies/q1.json').exists():raise ValueError('First true update required')
a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD')};indices=[1,2,3] if a.window==1 else [4,5,6]
def run(i):
 if (ledger.parent/'batch-pause.json').exists():return {'index':i,'status':'not_started_systemic_pause'}
 d=a.output/f'prefix-{i:02d}';command=[str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools/run_organization_episode_v204_r2.py'),'--output',str(d),'--ledger',str(ledger),'--index',str(i),'--arm','PREFIX']
 with (a.output/f'prefix-{i:02d}.log').open('xb') as log:proc=subprocess.run(command,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT)
 f=d/'result.json';return {'index':i,'exit':proc.returncode,'result':json.loads(f.read_text()) if f.exists() else None}
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for f in concurrent.futures.as_completed([pool.submit(run,i) for i in indices]):
  results.append(f.result());atomic_write(a.output/'progress.json',json_bytes({'status':'running','window':a.window,'results':results}))
atomic_write(a.output/'progress.json',json_bytes({'status':'awaiting_state_review','window':a.window,'results':results,'model_retries':0}))
