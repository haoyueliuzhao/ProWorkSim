"""Independent one-lane qualification and dual-version scoring of the closed real pair."""
import json,os,subprocess,argparse
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
R=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD')};results={}
def score(name,kind,episode=None):
 args=[str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools/score_organization_candidate_v204.py'),'--output',str(out/name),'--index','0','--kind',kind]
 if episode:args+=['--episode',str(episode)]
 with (out/(name+'.log')).open('xb') as log:ret=subprocess.run(args,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT)
 f=out/name/'receipt.json';value=json.loads(f.read_text()) if f.exists() else {'status':'technical_unknown','exit':ret.returncode}
 results[name]=value;atomic_write(out/'progress.json',json_bytes({'status':'running','results':results}));return value
g=score('gold','gold');e=score('empty','empty');qualified=g.get('status')=='official_report' and g.get('resolved')is True and e.get('status')=='official_report' and e.get('resolved')is False
if qualified:
 for arm in ('keep','assist'):
  ep=R/'runs/software-benchmark-v204/admission-pair-r1'/arm
  for kind in ('code','delivery'):score(arm+'-'+kind,kind,ep)
atomic_write(out/'progress.json',json_bytes({'status':'closed','qualified':qualified,'results':results,'used_for_q_updates':False,'solver_feedback':False,'new_API_calls':0}))
