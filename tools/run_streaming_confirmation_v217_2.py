"""Adopt live v217.1 branches; split generation and grading without model replay."""
import concurrent.futures,json,os,subprocess,threading,time,traceback
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_organization_api_v217 import Ledger,AdmissionStopped
from proworksim.software_organization_capacity_v212 import Capacity,Probe,PROFILE
from proworksim.software_organization_selector_v217 import evaluate
from proworksim.software_queue_resilience_v217_1 import FaultRegistry
from proworksim.software_streaming_lanes_v217_2 import SplitLanes
from proworksim.software_process_handoff_v217_2 import process,same_alive,retire
R=Path(__file__).resolve().parents[1]
OLD=R/'runs/software-benchmark-v217/confirmation-resume-r1'
OUT=R/'runs/software-benchmark-v217/streaming-r1'
P=R/'artifacts/software-benchmark-v217/protocol-r1'
A=R/'artifacts/software-benchmark-v217/streaming-optimization-r1'
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return None

def save(p,v):atomic_write(p,json_bytes(v))
def arg(p,k):return p['argv'][p['argv'].index(k)+1] if k in p['argv'] else None

def main():
 for folder in (P,R/'artifacts/software-benchmark-v217/resilience-r1',A):
  for ref in read(folder/'deployment-freeze.json')['files']:checked(ref)
 assert read(A/'admission.json')['passed']
 handoff=read(A/'handoff.json');owner=handoff['coordinator'];now=process(owner['pid'])
 assert same_alive(owner) and now['state'] in ('T','t') and owner['uid']==os.getuid()
 OUT.mkdir(parents=True,exist_ok=False)
 ledger_path=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite';ledger=Ledger(ledger_path)
 cap=Capacity(Probe(R),{**PROFILE,'generation_limit':18,'starting_generation_limit':6})
 mu=threading.RLock();stop=threading.Event();faults=FaultRegistry();states={};outcomes={}
 env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
 policy=read(OLD/'policy-2.json');assert policy['update']==2
 save(OUT/'frozen-confirmation-policy.json',policy)
 inherited={arg(p,'--output'):p for p in handoff['children']}
 for path,p in inherited.items():
  if same_alive(p):
   kind='grader' if arg(p,'--kind') else 'generation'
   cap.leases['inherited:'+path]={'kind':kind,'count':1,'memory':32*1024**3,'starting':kind=='generation' and (read(Path(path)/'result.json') or {}).get('status')=='preparing'}
 def refresh():
  for path,p in inherited.items():
   key='inherited:'+path
   if not same_alive(p):cap.release(key)
   elif (read(Path(path)/'result.json') or {}).get('status') not in (None,'preparing'):
    with cap.lock:
     if key in cap.leases:cap.ready(key)
 def status(key,value):
  with mu:
   states[key]=value;refresh()
   save(OUT/'progress.json',{'status':'paused_new_admissions' if stop.is_set() else 'running','states':states,'capacity':cap.snapshot(),'cash':ledger.snapshot(),'at':time.time(),'legacy_root':str(OLD),'policy_update':2})
 def fault(i,value):
  with mu:
   if faults.record(i,value)['pause_new_admissions']:stop.set()
   save(OUT/'exception-queue.json',{'items':faults.rows,'shared_fault_pause':stop.is_set(),'model_retries':0})
 def acquire(key,kind):
  while True:
   refresh()
   if kind=='generation' and stop.is_set():raise RuntimeError('Shared fault paused new admissions')
   if cap.acquire(key,kind)[0]:return
   time.sleep(3)
 def run(script,args,log,key=None):
  log.parent.mkdir(parents=True,exist_ok=True)
  with log.open('xb') as f:
   proc=subprocess.Popen([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT)
   while proc.poll() is None:
    if key and (read(Path(args[args.index('--output')+1])/'result.json') or {}).get('status') not in (None,'preparing'):
     cap.ready(key)
    time.sleep(3)
   return proc.returncode
 def wait_old(path):
  p=inherited.get(str(path))
  while p and same_alive(p):refresh();time.sleep(3)
  refresh()
 def generate(job):
  row,z,ep,is_old=job;i=row['index'];key=f'{i}:{z}'
  if is_old:
   status(key,{'stage':'adopting_existing_generation','episode':str(ep)})
   wait_old(ep)
  else:
   lease='generate:'+key;acquire(lease,'generation')
   status(key,{'stage':'generating','episode':str(ep),'performance_revision':'v217.2-r2'})
   try:
    run('run_project_relations_episode_v217_2.py',['--index',i,'--condition',z,'--output',ep,'--checkpoint',OLD/f'task-{i:02d}/PREFIX/checkpoint','--bank',OLD/f'task-{i:02d}/GENERATOR/candidate-bank.json','--ledger',ledger_path],ep.with_suffix('.log'),lease)
   finally:cap.release(lease)
  result=read(ep/'result.json') or {'status':'technical_unknown','reason':'process_exited_without_result'}
  status(key,{'stage':'queued_scoring' if result.get('status')=='closed' else 'generation_unknown','episode':str(ep),'generation_status':result.get('status')})
  return job,result
 def score_one(row,z,ep,kind):
  old=OLD/f'task-{row["index"]:02d}/scores'/z/kind
  if ep.parent.parent==OLD:
   wait_old(old)
   for p in (old,old.with_name(kind+'-retry1')):
    receipt=read(p/'receipt.json')
    if receipt and receipt.get('status') in ('official_report','candidate_execution_failed','no_legal_delivery'):
     receipt['_receipt_reference']=reference(p/'receipt.json');return receipt
  for attempt in range(2):
   dest=OUT/f'task-{row["index"]:02d}/scores'/z/f'{kind}-{attempt}';key='score:'+str(dest)
   acquire(key,'grader')
   try:
    rc=run('score_project_relations_v217_1.py',['--index',row['index'],'--kind',kind,'--output',dest,'--episode',ep],dest.with_suffix('.log'))
    receipt=read(dest/'receipt.json') or {'status':'technical_unknown','exit':rc}
    if (dest/'receipt.json').exists():receipt['_receipt_reference']=reference(dest/'receipt.json')
    if receipt.get('status') in ('official_report','candidate_execution_failed','no_legal_delivery') or receipt.get('official_result'):return receipt
   finally:cap.release(key)
  return receipt
 def grade(value):
  job,result=value;row,z,ep,_=job;i=row['index'];key=f'{i}:{z}'
  if result.get('status')!='closed':fault(i,result);return {'status':'generation_unknown','result':result,'episode_path':str(ep)}
  status(key,{'stage':'scoring','episode':str(ep)})
  scores={kind:score_one(row,z,ep,kind) for kind in ('code','delivery')}
  if scores['code'].get('status') not in ('official_report','candidate_execution_failed') or scores['delivery'].get('status') not in ('official_report','candidate_execution_failed','no_legal_delivery'):
   fault(i,{'scoring':scores});return {'status':'scoring_unknown','scores':scores,'episode_path':str(ep)}
  g=read(ep/'progress.json')
  return {'status':'scored','code_correct':scores['code']['resolved'],'legal_correct':scores['delivery']['resolved'],'formal_submission':g['lifecycle']['terminal']=='DELIVERED','logical_tokens':g['logical_total_tokens'],'episode':reference(ep/'result.json'),'episode_path':str(ep),'scores':{k:scores[k]['_receipt_reference'] for k in scores},'normal_budget_stop':any('budget_exhausted' in x for x in read(ep/'boundary.json')['role_stops'].values())}
 rows=read(P/'candidate-tasks.json')['rows'];panels={};jobs=[]
 # The candidate set and policy were frozen before any confirmation outcomes.
 for row in rows:
  i=row['index'];root=OLD/f'task-{i:02d}';bank=read(root/'GENERATOR/candidate-bank.json')
  if row['phase'] not in ('confirm','confirm_backup') or not bank:continue
  if (read(root/'GENERATOR/result.json') or {}).get('status')!='candidate_bank_ready':continue
  decision=evaluate(read(root/'PREFIX/decision-state.json'),bank,policy,row['seed'])
  assert not decision['feature_degenerate']
  prior=read(root/'decision.json');assert prior is None or prior==decision
  save(OUT/root.name/'decision.json',decision)
  panels[i]={'index':i,'instance_id':row['instance_id'],'repo':row['repo'],'phase':'confirm','scene':row['coverage_type'],'decision':decision,'bank':reference(root/'GENERATOR/candidate-bank.json'),'outcomes':{}}
  order=[decision['selected']]+[z for z in bank['candidates'] if z!=decision['selected']]
  slots={'v217:'+root.name+':'+z:bank['remaining_branch_token_limit'] for z in order}
  with ledger.db() as c:
   grants={s:c.execute('SELECT token_limit,status FROM block_slots WHERE slot=?',(s,)).fetchone() for s in slots}
   consumed={s:c.execute('SELECT status FROM slots WHERE id=?',(s,)).fetchone() for s in slots}
  if any(grants.values()):assert all(g and g[0]==slots[s] for s,g in grants.items()),'Partial or changed panel reservation'
  else:
   assert not any(consumed.values())
   ledger.reserve_block(str(OUT/root.name/'branches'),slots,'confirm')
  for z in order:
   old=root/z;s='v217:'+root.name+':'+z
   is_old=old.exists() or str(old) in inherited
   if not is_old:assert consumed[s] is None and (grants[s] is None or grants[s][1]=='pending'),'Consumed model identity without evidence'
   jobs.append((row,z,old if is_old else OUT/root.name/z,is_old))
 save(OUT/'adopted-plan.json',{'jobs':[{'index':r['index'],'condition':z,'episode':str(ep),'inherited':old} for r,z,ep,old in jobs],'model_replays':0,'policy':reference(OLD/'policy-2.json')})
 lanes=SplitLanes(18,2);futures={lanes.submit(lambda j=j:generate(j),grade):j for j in jobs}
 try:
  for f in concurrent.futures.as_completed(futures):
   row,z,ep,_=futures[f];i=row['index']
   try:result=f.result()
   except Exception as e:
    result={'status':'isolated_exception','error':str(e),'traceback':traceback.format_exc(),'episode_path':str(ep)};fault(i,result)
   panels[i]['outcomes'][z]=result;status(f'{i}:{z}',{'stage':result['status'],'episode':str(ep)})
   panel=panels[i];bank=read(checked(panel['bank']))
   if len(panel['outcomes'])==len(bank['candidates']):
    panel['complete']=all(x['status']=='scored' for x in panel['outcomes'].values());save(OUT/f'task-{i:02d}/panel-result.json',panel)
   save(OUT/'legacy-retirement.json',retire(handoff))
 finally:lanes.close()
 save(OUT/'confirm-results.json',list(panels.values()))
 save(OUT/'legacy-retirement.json',retire(handoff))
 save(OUT/'finished.json',{'status':'completed_with_isolated_unknowns' if faults.rows else 'completed','cash':ledger.snapshot(),'finished':time.time(),'policy_updates':2})
 status('coordinator',{'stage':'finished'})
 run('report_project_selection_v217_2.py',[],OUT/'report.log')
if __name__=='__main__':main()
