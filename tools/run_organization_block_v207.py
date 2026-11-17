"""One complete fresh-state comparison block. Does not select/retry by model score."""
import argparse,json,os,subprocess,concurrent.futures
from pathlib import Path
from proworksim.software_organization_api_v207 import Ledger
from proworksim import software_sdk_resume_v203_3_4 as resume
from proworksim.storage import json_bytes
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--pre-reserved',action='store_true');a=p.parse_args()
plan=json.loads(a.plan.read_text());out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
if (a.ledger.parent/'batch-pause.json').exists():raise RuntimeError('Systemic fault gate: do not admit another block')
state,identity=resume.read(Path(plan['checkpoint']));limit=5000000-state['prefix_ledger']['known_actual_tokens']
if identity['identity']!=plan['checkpoint_identity']:raise ValueError('Reviewed state changed')
review=plan['eligibility']
if review.get('checkpoint_identity')!=identity['identity'] or review.get('diagnosis')!='unfinished' or review.get('final_review_active') is not False or review.get('environment_healthy') is not True:raise ValueError('Audited eligible state required')
expected={'admission':2,'development':3,'confirmation':2}
if len(plan['branches'])!=expected[plan['stage']]:raise ValueError('Incomplete comparison block')
if plan['stage']=='development' and {x['candidate'] for x in plan['branches']}!={'KEEP','ASSIST','TRANSFER'}:raise ValueError('Complete candidate panel required')
slots={'v204:'+out.name+':'+b['name']:limit for b in plan['branches']};ledger=Ledger(a.ledger)
if a.pre_reserved:
 with ledger.db() as c:
  if any(c.execute('SELECT token_limit,status,block_id FROM block_slots WHERE slot=?',(slot,)).fetchone()!=(limit,'pending',str(out)) for slot in slots):raise ValueError('Exact complete block reservation required')
else:ledger.reserve_block(str(out),slots)
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD')}
def run(b):
 if (a.ledger.parent/'batch-pause.json').exists():return {'branch':b,'status':'not_started_systemic_pause'}
 command=[str(ROOT/'.venv/bin/python'),str(ROOT/'tools/run_offline_scorer_v096.py'),str(ROOT/'tools/run_organization_episode_v207.py'),'--output',str(out/b['name']),'--ledger',str(a.ledger),'--index',str(plan['index']),'--checkpoint',plan['checkpoint'],'--arm',b.get('candidate','KEEP')]
 if plan['stage']=='confirmation':command+=['--policy-config',b['policy_config'],'--draw',str(plan['draw'])]
 with (out/(b['name']+'.log')).open('xb') as log:r=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
 f=out/b['name']/'result.json';return {'branch':b,'exit':r.returncode,'result':json.loads(f.read_text()) if f.exists() else None}
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=len(plan['branches'])) as pool:
 for f in concurrent.futures.as_completed([pool.submit(run,b) for b in plan['branches']]):
  results.append(f.result());(out/'progress.json').write_bytes(json_bytes({'plan':plan,'results':results,'status':'running'}))
(out/'progress.json').write_bytes(json_bytes({'plan':plan,'results':results,'status':'generation_block_ended','partial_effect_update_allowed':False}))
