"""Run reviewed complete blocks; grade asynchronously, update only a whole healthy window.

No task replacement, re-sampling, score-based early stopping or candidate changes.
"""
import argparse,json,os,subprocess,concurrent.futures,time
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
plan=json.loads(a.plan.read_text());out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
ledger=Path(plan['ledger']);results=[];grades=[];grading_jobs=[]
expected_states=2 if plan['window']==1 else 3
if plan['window'] not in (1,2) or len(plan['blocks'])!=expected_states:raise ValueError('User-amended complete state count required')
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD')}
def save(status):atomic_write(out/'progress.json',json_bytes({'status':status,'at':time.time(),'plan':str(a.plan.resolve()),'generation':results,'grading':grades,'model_retries':0}))
def command(script,args,log):
 with log.open('xb') as f:return subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
def score(index,kind,d,episode=None):
 args=['--index',index,'--kind',kind,'--output',d]
 if episode:args+=['--episode',episode]
 code=command('score_organization_candidate_v204.py',args,d.with_suffix('.log'))
 f=d/'receipt.json';return json.loads(f.read_text()) if f.exists() else {'status':'technical_unknown','exit':code}
def grade(block,d):
 target=out/('score-'+block['name']);target.mkdir()
 g=score(block['index'],'gold',target/'gold');e=score(block['index'],'empty',target/'empty')
 q=g.get('status')=='official_report' and g.get('resolved')is True and e.get('status')=='official_report' and e.get('resolved')is False
 record={'state_id':block['state_id'],'qualified':q,'branches':{}}
 if q:
  for branch in block['branches']:
   ep=d/branch['name'];res=ep/'result.json'
   if not res.exists() or json.loads(res.read_text())['status']!='closed':record['branches'][branch['candidate']]={'status':'generation_unknown'};continue
   b=target/branch['name'];b.mkdir();c=score(block['index'],'code',b/'code',ep);v=score(block['index'],'delivery',b/'delivery',ep)
   # A code pass never substitutes for a different final legal submission.
   record['branches'][branch['candidate']]={'status':'scored' if c['status']=='official_report' and v['status'] in ('official_report','no_legal_delivery') else 'scoring_unknown',
    'code':c.get('resolved'),'delivery':v.get('resolved'),'refs':{'generation':reference(res),'code_score':reference(b/'code/receipt.json'),**({'delivery_score':reference(b/'delivery/receipt.json')} if v['status']=='official_report' else {})}}
 atomic_write(target/'summary.json',json_bytes(record));return record
save('starting')
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as scorer:
 for block in plan['blocks']:
  if (ledger.parent/'batch-pause.json').exists():save('systemic_fault_paused');break
  d=Path(plan.get('preexisting_blocks',{}).get(block['name'],str(out/block['name'])));f=out/(block['name']+'-plan.json');f.write_bytes(json_bytes(block))
  if block['name'] in plan.get('preexisting_blocks',{}):
   while True:
    old=d/'progress.json'
    if old.exists():
     previous=json.loads(old.read_text())
     if previous['plan']!=block:raise ValueError('Existing block is not the frozen same state')
     if previous['status']=='generation_block_ended':break
    save('waiting_existing_block');time.sleep(20)
   rc=0
  else:
   rc=command('run_organization_block_v204.py',['--plan',f,'--output',d,'--ledger',ledger],out/(block['name']+'.log'))
  progress=d/'progress.json'
  record={'state_id':block['state_id'],'exit':rc,'progress':json.loads(progress.read_text()) if progress.exists() else None};results.append(record)
  if progress.exists():grading_jobs.append(scorer.submit(grade,block,d))
  save('generating_and_scoring')
  if rc or (ledger.parent/'batch-pause.json').exists():break
 for job in grading_jobs:
  try:grades.append(job.result())
  except Exception as e:grades.append({'status':'grading_exception','error':type(e).__name__+':'+str(e)})
  save('scoring')
complete=len(results)==expected_states and len(grades)==expected_states and all(g.get('qualified') and len(g['branches'])==3 and all(b['status']=='scored' for b in g['branches'].values()) for g in grades)
if not complete:save('window_incomplete_no_update');raise SystemExit(0)
manifest={'stage':'development','window':plan['window'],'ledger':str(ledger),'blocks':[{'state_id':g['state_id'],'branches':{z:b['refs'] for z,b in g['branches'].items()}} for g in grades]}
f=out/'feedback-manifest.json';f.write_bytes(json_bytes(manifest));e=out/'feedback.json'
rc=command('collect_organization_feedback_v204.py',['--manifest',f,'--output',e],out/'feedback.log')
if rc:save('feedback_unknown_no_update');raise SystemExit(0)
policies=R/'runs/software-benchmark-v204/policies';policies.mkdir(exist_ok=True)
args=['--evidence',e,'--output',policies/f"q{plan['window']}.json"]
if plan['window']==2:args+=['--previous',policies/'q1.json']
rc=command('update_organization_policy_v204.py',args,out/'update.log');save('updated' if rc==0 else 'update_rejected')
