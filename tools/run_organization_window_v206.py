"""Run reviewed complete blocks; grade asynchronously, update only a whole healthy window.

No task replacement, re-sampling, score-based early stopping or candidate changes.
"""
import argparse,json,os,subprocess,concurrent.futures,time,threading
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_organization_capacity_v206 import Capacity,Probe,PROFILE
from proworksim.software_organization_api_v204 import Ledger,AdmissionStopped
from proworksim import software_sdk_resume_v203_3_4 as resume
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--generation-limit',type=int,default=48);a=p.parse_args()
if not 1<=a.generation_limit<=48:p.error('Generation bound must be 1..48')
plan=json.loads(a.plan.read_text());out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
ledger=Path(plan['ledger']);results=[];grades=[];grading_jobs=[];capacity=Capacity(Probe(R),{**PROFILE,'generation_limit':a.generation_limit})
if plan.get('preexisting_blocks'):raise ValueError('Future batches only; do not take over active old blocks')
confirmation=plan.get('stage')=='confirmation'
expected_states=4 if confirmation else (2 if plan['window']==1 else 3)
if plan['window'] not in ((3,) if confirmation else (1,2)) or len(plan['blocks'])!=expected_states:raise ValueError('Frozen complete state count required')
if plan['window']==2 and not (R/'runs/software-benchmark-v204/policies/q1.json').exists():raise ValueError('First true update required before window two')
if confirmation and not (R/'runs/software-benchmark-v204/policies/q2.json').exists():raise ValueError('Frozen second true update required before confirmation')
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD')}
def save(status):atomic_write(out/'progress.json',json_bytes({'status':status,'at':time.time(),'plan':str(a.plan.resolve()),'generation':results,'grading':grades,'model_retries':0,'capacity':capacity.snapshot()}))
def command(script,args,log):
 with log.open('xb') as f:return subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
def _score(index,kind,d,episode=None):
 args=['--index',index,'--kind',kind,'--output',d]
 if episode:args+=['--episode',episode]
 code=command('score_organization_candidate_v204.py',args,d.with_suffix('.log'))
 f=d/'receipt.json';return json.loads(f.read_text()) if f.exists() else {'status':'technical_unknown','exit':code}
def score(index,kind,d,episode=None):
 key='score:'+str(d)
 while not capacity.acquire(key,'grader')[0]:time.sleep(5)
 try:return _score(index,kind,d,episode)
 finally:capacity.release(key)
def grade(block,d):
 target=out/('score-'+block['name']);target.mkdir()
 g=score(block['index'],'gold',target/'gold');e=score(block['index'],'empty',target/'empty')
 q=g.get('status')=='official_report' and g.get('resolved')is True and e.get('status')=='official_report' and e.get('resolved')is False
 record={'state_id':block['state_id'],'qualified':q,'branches':{}}
 if q:
  for branch in block['branches']:
   ep=d/branch['name'];res=ep/'result.json'
   if not res.exists() or json.loads(res.read_text())['status']!='closed':record['branches'][branch.get('candidate',branch['name'])]={'status':'generation_unknown'};continue
   b=target/branch['name'];b.mkdir();c=score(block['index'],'code',b/'code',ep);v=score(block['index'],'delivery',b/'delivery',ep)
   # A code pass never substitutes for a different final legal submission.
   record['branches'][branch.get('candidate',branch['name'])]={'status':'scored' if c['status']=='official_report' and v['status'] in ('official_report','no_legal_delivery') else 'scoring_unknown',
    'code':c.get('resolved'),'delivery':v.get('resolved'),'refs':{'generation':reference(res),'code_score':reference(b/'code/receipt.json'),**({'delivery_score':reference(b/'delivery/receipt.json')} if v['status']=='official_report' else {})}}
 atomic_write(target/'summary.json',json_bytes(record));return record
def generate(block,d):
 key=block['state_id'];stop=threading.Event()
 def watch_startup():
  while not stop.wait(5):
   statuses=[]
   for b in block['branches']:
    try:statuses.append(json.loads((d/b['name']/'result.json').read_text())['status'])
    except (FileNotFoundError,json.JSONDecodeError):statuses.append('preparing')
   if all(s!='preparing' for s in statuses):capacity.ready(key);return
 watcher=threading.Thread(target=watch_startup,daemon=True);watcher.start()
 try:
  f=out/(block['name']+'-plan.json');f.write_bytes(json_bytes(block))
  rc=command('run_organization_block_v206.py',['--plan',f,'--output',d,'--ledger',ledger,'--pre-reserved'],out/(block['name']+'.log'))
  progress=d/'progress.json'
  return {'state_id':key,'exit':rc,'progress':json.loads(progress.read_text()) if progress.exists() else None}
 finally:stop.set();watcher.join();capacity.release(key)
# Precompute immutable state identities once, then serialize complete cash grants
# in the coordinator before concurrent launch. Pressure is re-read at admission.
pending=list(plan['blocks']);limits={}
for b in pending:
 proof=json.loads((Path(b['checkpoint'])/'manifest.json').read_text())
 if proof['identity']!=b['checkpoint_identity']:raise ValueError('Changed reviewed prefix')
 # Each actual child still verifies the complete frozen checkpoint before API.
 # The coordinator only needs the prior token total for an atomic cash grant.
 limits[b['state_id']]=5000000-proof['prefix_tokens']
save('starting');active={};cash_stopped=False
with concurrent.futures.ThreadPoolExecutor(max_workers=48) as workers, concurrent.futures.ThreadPoolExecutor(max_workers=2) as scorer:
 while pending or active:
  for future in [f for f in active if f.done()]:
   b,d=active.pop(future)
   try:record=future.result()
   except Exception as error:record={'state_id':b['state_id'],'exit':1,'error':str(error),'progress':None}
   results.append(record)
   if record['progress'] is not None:grading_jobs.append(scorer.submit(grade,b,d))
  paused=(ledger.parent/'batch-pause.json').exists()
  if pending and not paused:
   b=pending[0];key=b['state_id'];ok,reason=capacity.acquire(key,'generation',len(b['branches']))
   if ok:
    d=out/b['name'];slots={'v204:'+d.name+':'+x['name']:limits[key] for x in b['branches']}
    try:Ledger(ledger).reserve_block(str(d),slots)
    except AdmissionStopped:
     capacity.release(key)
     if not active:cash_stopped=True;break
    except Exception:
     capacity.release(key);raise
    else:
     pending.pop(0);active[workers.submit(generate,b,d)]=(b,d);save('generating_and_scoring');continue
  if paused and not active:break
  save('generating_and_scoring');time.sleep(5)
 for job in grading_jobs:
  try:grades.append(job.result())
  except Exception as error:grades.append({'status':'grading_exception','error':str(error)})
  save('scoring')
if pending:
 save('cash_block_admission_stopped' if cash_stopped else 'systemic_fault_paused');raise SystemExit(0)
# Update only after all original complete blocks; execution order cannot pick winners.
order={b['state_id']:i for i,b in enumerate(plan['blocks'])}
results.sort(key=lambda r:order[r['state_id']]);grades.sort(key=lambda r:order.get(r.get('state_id'),999))
complete=len(results)==expected_states and len(grades)==expected_states and all(g.get('qualified') and len(g['branches'])==(2 if confirmation else 3) and all(b['status']=='scored' for b in g['branches'].values()) for g in grades)
if not complete:save('window_incomplete_no_update');raise SystemExit(0)
if confirmation:
 atomic_write(out/'confirmation-results.json',json_bytes({'fixed_configs':True,'results':grades,'actual_fees_in_ledger':str(ledger),'no_further_update':True}));save('confirmation_closed');raise SystemExit(0)
manifest={'stage':'development','window':plan['window'],'ledger':str(ledger),'blocks':[{'state_id':g['state_id'],'branches':{z:b['refs'] for z,b in g['branches'].items()}} for g in grades]}
f=out/'feedback-manifest.json';f.write_bytes(json_bytes(manifest));e=out/'feedback.json'
rc=command('collect_organization_feedback_v204.py',['--manifest',f,'--output',e],out/'feedback.log')
if rc:save('feedback_unknown_no_update');raise SystemExit(0)
policies=R/'runs/software-benchmark-v204/policies';policies.mkdir(exist_ok=True)
args=['--evidence',e,'--output',policies/f"q{plan['window']}.json"]
if plan['window']==2:args+=['--previous',policies/'q1.json']
rc=command('update_organization_policy_v204.py',args,out/'update.log');save('updated' if rc==0 else 'update_rejected')
