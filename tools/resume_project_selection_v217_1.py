"""Two real feedback windows and frozen all-candidate confirmation.

Candidate and task selection precede outcomes. Failure is data; infrastructure
failure pauses new admissions. No retries of consumed model identities.
"""
import concurrent.futures,json,os,subprocess,threading,time,traceback
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_organization_api_v217 import Ledger,AdmissionStopped
from proworksim.software_organization_capacity_v212 import Capacity,Probe,PROFILE
from proworksim.software_organization_selector_v217 import initialize,evaluate,update
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v217/protocol-r1';OUT=R/'runs/software-benchmark-v217/confirmation-resume-r1';HISTORY=R/'runs/software-benchmark-v217/selection28-r1';RECOVERY=R/'artifacts/software-benchmark-v217/resilience-r1'
def read(p):return json.loads(p.read_text()) if p.exists() else None
def save(p,v):atomic_write(p,json_bytes(v))
OUT.mkdir(parents=True,exist_ok=False)
for ref in read(P/'deployment-freeze.json')['files']:checked(ref)
for ref in read(RECOVERY/'deployment-freeze.json')['files']:checked(ref)
assert read(HISTORY/'finished.json')['status']=='paused_infrastructure'
assert read(P/'admission.json')['passed']
plan=read(P/'candidate-tasks.json');rows=plan['rows'];ledger_path=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite';ledger=Ledger(ledger_path)
capacity=Capacity(Probe(R),{**PROFILE,'generation_limit':18,'starting_generation_limit':6});lock=threading.RLock();score_sem=threading.Semaphore(2);STOP=threading.Event();states=read(HISTORY/'progress.json')['states'];phase='confirm';policy=read(RECOVERY/'policy-2.json')
assert policy['update']==2
for n in (0,1):save(OUT/f'policy-{n}.json',read(HISTORY/f'policy-{n}.json'))
save(OUT/'policy-2.json',policy)
canonical_dev2=read(RECOVERY/'dev2-results-canonical.json');r4=next(r for r in canonical_dev2 if r['index']==4);states['4'].update(status='closed',outcomes=r4['outcomes'],classification_recovered=True)
from proworksim.software_queue_resilience_v217_1 import FaultRegistry
fault_registry=FaultRegistry()
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
def status(index,state,**kw):
 with lock:
  states.setdefault(str(index),{}).update(status=state,**kw)
  save(OUT/'progress.json',{'status':'paused_infrastructure' if STOP.is_set() else 'running','phase':phase,'states':states,'policy_update':policy['update'],'capacity':capacity.snapshot(),'cash':ledger.snapshot(),'at':time.time()})
def fault(index,reason):
 with lock:
  entry=fault_registry.record(index,reason)
  if entry['pause_new_admissions']:STOP.set()
  save(OUT/'exception-queue.json',{'items':fault_registry.rows,'shared_fault_pause':STOP.is_set(),'model_retries':0})
  status(index,'isolated_unknown',reason=reason)
def run(script,args,log):
 log.parent.mkdir(parents=True,exist_ok=True)
 with log.open('xb') as f:return subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT).returncode

def release_unused(slot):
 with ledger.db() as c:
  if not c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():c.execute('UPDATE block_slots SET status="not_started" WHERE slot=? AND status="pending"',(slot,))
def reserve(index,block,slots):
 while not STOP.is_set():
  try:ledger.reserve_block(str(block),slots,phase);return True
  except AdmissionStopped as e:
   with ledger.db() as c:active=c.execute("SELECT count(*) FROM slots WHERE status='active' AND id LIKE 'v217:%'").fetchone()[0]+c.execute("SELECT count(*) FROM block_slots WHERE status='pending' AND slot LIKE 'v217:%'").fetchone()[0]
   if not active:status(index,'not_started_cash',reason=str(e));return False
   status(index,'waiting_complete_block_cash',reason=str(e));time.sleep(5)
 return False

def acquire(key,kind,count=1):
 while True:
  if STOP.is_set():return False
  allowed,reason=capacity.acquire(key,kind,count)
  if allowed:return True
  time.sleep(5)

def qualify(row):
 path=R/f'runs/software-benchmark-v217/environment-r2/task-{row["index"]:02d}/qualification.json'
 while not path.exists() and not STOP.is_set():time.sleep(5)
 v=read(path) or {}
 if not v.get('qualified'):status(row['index'],'environment_unqualified',qualification=v);return False
 for kind,ref in v['proof'].items():
  s=read(checked(ref));assert s['status']=='official_report' and s['resolved']==(kind=='gold')
 return True

def prepare(row):
 i=row['index'];root=OUT/f'task-{i:02d}';prefix=root/'PREFIX';gen=root/'GENERATOR';key='prepare:'+str(i)
 try:
  root.mkdir()
  if not qualify(row):return None
  slot='v217:'+root.name+':PREFIX'
  if not reserve(i,prefix,{slot:plan['prefix_limit']}):return None
  if not acquire(key,'generation'):release_unused(slot);return None
  status(i,'running_common_prefix',instance_id=row['instance_id'],repo=row['repo'],phase=phase)
  try:rc=run('run_project_relations_episode_v217.py',['--index',i,'--condition','PREFIX','--output',prefix,'--ledger',ledger_path],root/'prefix.log')
  finally:capacity.release(key);release_unused(slot)
  result=read(prefix/'result.json') or {'status':'technical_unknown','exit':rc}
  if result['status']=='technical_unknown':fault(i,result);return None
  if result['status']!='decision_checkpoint_ready':status(i,'prefix_unqualified',result=result);return None
  slot='v217:'+root.name+':GENERATOR'
  if not reserve(i,gen,{slot:plan['generator_limit']}):return None
  status(i,'generating_candidates')
  rc=run('generate_project_candidates_v217.py',['--index',i,'--prefix',prefix,'--output',gen,'--ledger',ledger_path],root/'generator.log');release_unused(slot)
  result=read(gen/'result.json') or {'status':'technical_unknown','exit':rc}
  if result['status']!='candidate_bank_ready':fault(i,result);return None
  status(i,'panel_ready',candidate_count=result['candidate_count']);return row
 except Exception as e:fault(i,{'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()});return None
 finally:capacity.release(key)

def score(row,z,kind,ep):
 with score_sem:
  for attempt in range(2):
   out=ep.parent/'scores'/z/(kind if attempt==0 else kind+'-retry1');key='score:'+str(out)
   while not capacity.acquire(key,'grader')[0]:time.sleep(5)
   try:
    rc=run('score_project_relations_v217_1.py',['--index',row['index'],'--kind',kind,'--output',out,'--episode',ep],out.with_suffix('.log'))
    receipt=read(out/'receipt.json') or {'status':'technical_unknown','exit':rc,'error_type':'MissingScorerReceipt'}
    if (out/'receipt.json').exists():receipt['_receipt_reference']=reference(out/'receipt.json')
    if receipt['status'] in ('official_report','candidate_execution_failed','no_legal_delivery'):return receipt
    # A returned official negative is not repeatedly scored merely to get a pass.
    if receipt.get('official_result'):return receipt
   finally:capacity.release(key)
  return receipt

def branch(row,z,bank):
 i=row['index'];root=OUT/f'task-{i:02d}';ep=root/z
 rc=run('run_project_relations_episode_v217.py',['--index',i,'--condition',z,'--output',ep,'--checkpoint',root/'PREFIX/checkpoint','--bank',bank,'--ledger',ledger_path],ep.with_suffix('.log'));release_unused('v217:'+root.name+':'+z)
 result=read(ep/'result.json') or {'status':'technical_unknown','exit':rc}
 if result['status']!='closed':fault(i,result);return {'status':'generation_unknown','result':result}
 scores={kind:score(row,z,kind,ep) for kind in ('code','delivery')};g=read(ep/'progress.json')
 if scores['code'].get('status') not in ('official_report','candidate_execution_failed') or scores['delivery'].get('status') not in ('official_report','candidate_execution_failed','no_legal_delivery'):
  fault(i,{'scoring':scores});return {'status':'scoring_unknown','scores':scores}
 return {'status':'scored','code_correct':scores['code']['resolved'],'legal_correct':scores['delivery']['resolved'],'formal_submission':g['lifecycle']['terminal']=='DELIVERED','logical_tokens':g['logical_total_tokens'],'episode':reference(ep/'result.json'),'scores':{k:scores[k]['_receipt_reference'] for k in scores},'normal_budget_stop':any('budget_exhausted' in x for x in read(ep/'boundary.json')['role_stops'].values())}

def execute(row):
 i=row['index'];root=OUT/f'task-{i:02d}';bank_path=root/'GENERATOR/candidate-bank.json';bank=read(bank_path);state=read(root/'PREFIX/decision-state.json');decision=evaluate(state,bank,policy,row['seed']);save(root/'decision.json',decision)
 if decision['feature_degenerate']:
  fault(i,{'reason':'all_project_candidate_features_identical','before_successor_calls':True});return None
 slots={'v217:'+root.name+':'+z:bank['remaining_branch_token_limit'] for z in bank['candidates']}
 if not reserve(i,root/'branches',slots):return None
 key='branches:'+str(i)
 if not acquire(key,'generation',len(slots)):
  for slot in slots:release_unused(slot)
  return None
 status(i,'running_all_candidates',selected=decision['selected'],policy_update=policy['update'],probabilities=decision['probabilities'],candidate_count=len(slots))
 stop=threading.Event()
 def ready():
  while not stop.wait(5):
   results=[read(root/z/'result.json') for z in bank['candidates']]
   if all(r and r['status']!='preparing' for r in results):capacity.ready(key);return
 watch=threading.Thread(target=ready,daemon=True);watch.start()
 try:
  # Selected arm is submitted first and is a real run, never merely an offline weight.
  order=[decision['selected']]+[z for z in bank['candidates'] if z!=decision['selected']]
  with concurrent.futures.ThreadPoolExecutor(max_workers=len(order)) as pool:
   futures={pool.submit(branch,row,z,bank_path):z for z in order};outcomes={}
   for f in concurrent.futures.as_completed(futures):
    z=futures[f]
    try:outcomes[z]=f.result()
    except Exception as error:
     fault(i,{'type':type(error).__name__,'message':str(error),'stage':z});outcomes[z]={'status':'isolated_exception','error':str(error)}
    status(i,'running_or_scoring',outcomes=outcomes)
  record={'index':i,'instance_id':row['instance_id'],'repo':row['repo'],'phase':phase,'scene':row['coverage_type'],'decision':decision,'outcomes':outcomes,'bank':reference(bank_path),'complete':all(x['status']=='scored' for x in outcomes.values())}
  save(root/'panel-result.json',record);status(i,'closed' if record['complete'] else 'closed_with_unknown',outcomes=outcomes);return record
 except Exception as e:fault(i,{'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()});return None
 finally:stop.set();watch.join();capacity.release(key)

def isolated_execute(row):
 try:return execute(row)
 except Exception as e:
  fault(row['index'],{'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()});return None

backups={'development':[r for r in rows if r['phase']=='dev_backup'],'confirm':[r for r in rows if r['phase']=='confirm_backup']}
try:
 for phase in ('confirm',):
  if STOP.is_set():break
  if phase=='confirm':save(OUT/'frozen-confirmation-policy.json',policy)
  primary=[r for r in rows if r['phase']==phase];ready=[]
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
   for r in pool.map(prepare,primary):
    if r:ready.append(r)
  # Only replace qualification failures before ANY outcomes in this window.
  failures=[r for r in primary if states.get(str(r['index']),{}).get('status') in ('environment_unqualified','prefix_unqualified')]
  queue=backups['confirm' if phase=='confirm' else 'development']
  for bad in failures:
   if STOP.is_set() or not queue:break
   backup=queue.pop(0);save(OUT/f'replacement-{bad["index"]}.json',{'original':bad['index'],'replacement':backup['index'],'reason':states[str(bad['index'])]['status'],'before_window_successor_outcomes':True})
   r=prepare(backup)
   if r:ready.append(r)
  if STOP.is_set():break
  records=[]
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
   for result in pool.map(isolated_execute,ready):
    if result:records.append(result)
  save(OUT/(phase+'-results.json'),records)
  if STOP.is_set():break
  if phase!='confirm':
   complete=[r for r in records if r['complete']]
   policy=update(policy,complete,phase);save(OUT/f'policy-{policy["update"]}.json',policy)
  else:save(OUT/'frozen-confirmation-policy.json',policy)
 save(OUT/'finished.json',{'status':'paused_infrastructure' if STOP.is_set() else 'completed_with_isolated_unknowns' if fault_registry.rows else 'completed','policy_updates':policy['update'],'cash':ledger.snapshot(),'finished':time.time(),'stage':phase})
except BaseException as e:
 STOP.set()
 fault('coordinator',{'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
 save(OUT/'finished.json',{'status':'paused_infrastructure','policy_updates':policy['update'],'cash':ledger.snapshot(),'finished':time.time(),'stage':phase})
finally:
 save(OUT/'progress.json',{'status':'paused_infrastructure' if STOP.is_set() else 'closed','phase':phase,'states':states,'policy_update':policy['update'],'cash':ledger.snapshot(),'at':time.time(),'capacity':capacity.snapshot()})
if not STOP.is_set():
 with (OUT/'report.log').open('xb') as log:subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/report_project_selection_v217_1.py')],cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT)
