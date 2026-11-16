"""Bounded prefix queue: errors isolated, one registered prefix per candidate.

No score-aware selection or branch auto-admission; current-evidence eligibility
is reviewed before any continuation is scheduled.
"""
import argparse,concurrent.futures,json,subprocess,time,os
from pathlib import Path
from proworksim.storage import json_bytes
ROOT=Path(__file__).resolve().parents[1]
def main(a):
 a.output.mkdir(parents=True,exist_ok=False)
 def run(i):
  target=a.output/f'prefix-{i:02d}'
  with (a.output/f'prefix-{i:02d}.log').open('xb') as log:
   p=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/run_offline_scorer_v096.py'),str(ROOT/'tools/run_delegation_episode_v203_3_3_r2.py'),
    '--output',str(target),'--ledger',str(a.output/'ledger.sqlite'),'--index',str(i)],stdout=log,stderr=subprocess.STDOUT,timeout=25000,env={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD'}})
  return {'index':i,'exit':p.returncode,'result':str(target/'result.json')}
 results=[]
 # First real prefix validates provider/SDK/ledger before subsequent prefixes.
 first=run(0);results.append(first)
 if first['exit']!=0:
  (a.output/'queue.json').write_bytes(json_bytes({'status':'first_prefix_needs_repair','results':results}));return
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  futures={pool.submit(run,i):i for i in range(1,8)}
  for f in concurrent.futures.as_completed(futures):
   try:results.append(f.result())
   except Exception as e:results.append({'index':futures[f],'queue_error':type(e).__name__+':'+str(e)})
   (a.output/'queue.json').write_bytes(json_bytes({'status':'prefixes_running','results':results,'at':time.time()}))
 (a.output/'queue.json').write_bytes(json_bytes({'status':'prefixes_ended_awaiting_review','results':results,'at':time.time()}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);main(p.parse_args())
