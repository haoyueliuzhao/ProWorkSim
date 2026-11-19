"""Fresh eight-state pilot; streaming preparation, generation and isolated grading."""
import concurrent.futures,json,os,subprocess,threading,time,traceback
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked,read_episode_candidates
from proworksim.software_organization_api_v218 import Ledger,AdmissionStopped
from proworksim.software_organization_capacity_v212 import Capacity,Probe,PROFILE
from proworksim.software_organization_selector_v217 import evaluate,update
from proworksim.software_organization_opportunity_v218 import admit_bank
from proworksim.software_streaming_lanes_v217_2 import SplitLanes
from proworksim.software_queue_resilience_v217_1 import FaultRegistry
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v218/protocol-r1';OUT=R/'runs/software-benchmark-v218/pilot8-r1';ENV=R/'runs/software-benchmark-v218/environment-r1';LEDGER=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return None

def save(p,v):atomic_write(p,json_bytes(v))
def main():
 assert read(P/'admission.json')['passed']
 for ref in read(P/'deployment-freeze.json')['files']:checked(ref)
 OUT.mkdir(parents=True,exist_ok=False);plan=read(P/'candidate-tasks.json');rows=plan['rows'];ledger=Ledger(LEDGER)
 cap=Capacity(Probe(R),{**PROFILE,'generation_limit':12,'starting_generation_limit':4,'managed_memory_budget_bytes':512*1024**3})
 mu=threading.RLock();cashlock=threading.Lock();stop=threading.Event();faults=FaultRegistry();states={};phase='preparation';policy=read(checked(plan['initial_policy']));records=[]
 save(OUT/'starting-policy.json',policy)
 env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
 def status(key,state,**kwargs):
  with mu:
   states[str(key)]={'status':state,**kwargs}
   save(OUT/'progress.json',{'status':'finished' if key=='coordinator' and state=='finished' else 'paused_new_admissions' if stop.is_set() else 'running','phase':phase,'states':states,'policy_update':policy['update'],'cash':ledger.snapshot(),'capacity':cap.snapshot(),'at':time.time()})
 def fault(i,value):
  with mu:
   if faults.record(i,value)['pause_new_admissions']:stop.set()
   save(OUT/'exception-queue.json',{'items':faults.rows,'shared_fault_pause':stop.is_set(),'automatic_model_retries':0})
 def release_unused(slots):
  with ledger.db() as c:
   for s in slots:
    if not c.execute('SELECT 1 FROM slots WHERE id=?',(s,)).fetchone():c.execute("UPDATE block_slots SET status='not_started' WHERE slot=? AND status='pending'",(s,))
 def reserve(i,key,slots):
  while not stop.is_set():
   try:
    with cashlock:ledger.reserve_block(str(key),slots)
    return True
   except AdmissionStopped as e:
    with ledger.db() as c:n=c.execute("SELECT count(*) FROM slots WHERE status='active' AND id LIKE 'v218:%'").fetchone()[0]+c.execute("SELECT count(*) FROM block_slots WHERE status='pending' AND slot LIKE 'v218:%'").fetchone()[0]
    if not n:status(i,'not_started_cash',reason=str(e));return False
    status(i,'waiting_cash',reason=str(e));time.sleep(3)
  return False
 def acquire(key,kind):
  while True:
   if stop.is_set() and kind=='generation':raise RuntimeError('Shared infrastructure pause before new admission')
   if cap.acquire(key,kind)[0]:return
   time.sleep(3)
 def run(script,args,log,lease=None):
  log.parent.mkdir(parents=True,exist_ok=True)
  with log.open('xb') as f:
   p=subprocess.Popen([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT)
   while p.poll() is None:
    if lease and (read(Path(args[args.index('--output')+1])/'result.json') or {}).get('status') not in (None,'preparing'):cap.ready(lease)
    time.sleep(3)
   return p.returncode
 def prepare(row):
  i=row['index'];root=OUT/f'task-{i:02d}';root.mkdir();lease='prepare:'+str(i);slots=[]
  try:
   qpath=ENV/f'task-{i:02d}/qualification.json'
   while not qpath.exists():
    receipts={k:ENV/f'task-{i:02d}'/k/'receipt.json' for k in ('gold','empty')}
    if all(p.exists() for p in receipts.values()):
     proofs={k:read(p) for k,p in receipts.items()}
     qpath=root/'environment-qualification.json'
     save(qpath,{'qualified':all(proofs[k] and proofs[k].get('status')=='official_report' and proofs[k].get('resolved')==(k=='gold') and proofs[k].get('cleanup_errors')==[] for k in proofs),'proof':{k:reference(p) for k,p in receipts.items()},'streaming_completed_controls':True})
     break
    if stop.is_set():return None
    if (ENV/'finished.json').exists():raise RuntimeError('Environment control ended without qualification')
    status(i,'waiting_environment');time.sleep(5)
   qualification=read(qpath)
   if not qualification['qualified']:status(i,'environment_unqualified');return None
   for kind,ref in qualification['proof'].items():
    receipt=read(checked(ref));assert receipt['status']=='official_report' and receipt['resolved']==(kind=='gold')
   prefix=root/'PREFIX';slot='v218:'+root.name+':PREFIX';slots.append(slot)
   if not reserve(i,prefix,{slot:plan['prefix_limit']}):return None
   acquire(lease,'generation');status(i,'running_prefix',instance_id=row['instance_id'])
   run('run_project_relations_episode_v218.py',['--index',i,'--condition','PREFIX','--output',prefix,'--ledger',LEDGER],root/'prefix.log',lease)
   result=read(prefix/'result.json') or {'status':'technical_unknown','reason':'missing_prefix_result'}
   if result['status']!='decision_checkpoint_ready':
    if result['status']=='technical_unknown':fault(i,result)
    status(i,'prefix_unqualified',result=result);return None
   gen=root/'GENERATOR';slot='v218:'+root.name+':GENERATOR';slots.append(slot)
   if not reserve(i,gen,{slot:plan['generator_limit']}):return None
   status(i,'generating_candidates');run('generate_project_candidates_v218.py',['--index',i,'--prefix',prefix,'--output',gen,'--ledger',LEDGER],root/'generator.log')
   result=read(gen/'result.json') or {'status':'technical_unknown','reason':'missing_bank'}
   if result['status']!='candidate_bank_ready':fault(i,result);status(i,'candidate_unknown');return None
   bank=read(gen/'candidate-bank.json');gate=admit_bank(bank,read(prefix/'decision-state.json'));save(root/'opportunity-gate.json',gate)
   if not gate['qualified']:status(i,'opportunity_unqualified',gate=gate);return None
   status(i,'panel_ready',candidate_count=len(bank['candidates']));return row
  except Exception as e:fault(i,{'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()});status(i,'prepare_unknown');return None
  finally:cap.release(lease);release_unused(slots)
 def generate(job):
  row,z,bank=job;i=row['index'];ep=OUT/f'task-{i:02d}'/z;key=f'{i}:{z}';slot='v218:'+ep.parent.name+':'+z
  try:
   acquire(key,'generation');status(key,'generating')
   run('run_project_relations_episode_v218.py',['--index',i,'--condition',z,'--output',ep,'--checkpoint',ep.parent/'PREFIX/checkpoint','--bank',bank,'--ledger',LEDGER],ep.with_suffix('.log'),key)
   result=read(ep/'result.json') or {'status':'technical_unknown','reason':'no_generation_result'}
   status(key,'queued_scoring' if result['status']=='closed' else 'generation_unknown');return job,ep,result
  finally:cap.release(key);release_unused([slot])
 def score(row,z,ep,kind):
  for attempt in range(2):
   dest=ep.parent/'scores'/z/f'{kind}-{attempt}';key='score:'+str(dest);acquire(key,'grader')
   try:
    rc=run('score_project_relations_v218.py',['--index',row['index'],'--kind',kind,'--episode',ep,'--output',dest],dest.with_suffix('.log'))
    receipt=read(dest/'receipt.json') or {'status':'technical_unknown','exit':rc}
    if (dest/'receipt.json').exists():receipt['_reference']=reference(dest/'receipt.json')
    if receipt['status'] in ('official_report','candidate_execution_failed','no_legal_delivery') or receipt.get('official_result'):return receipt
   finally:cap.release(key)
  return receipt
 def grade(value):
  job,ep,result=value;row,z,bank=job;i=row['index'];key=f'{i}:{z}'
  if result['status']!='closed':fault(i,result);return {'status':'generation_unknown','result':result}
  status(key,'scoring');code=score(row,z,ep,'code');pair=read_episode_candidates(read(ep/'candidate-lock.json'))
  if code['status'] in ('official_report','candidate_execution_failed') and pair['lock'].get('last_legal_delivery') and read(checked(pair['lock']['terminal_code']))['tree_sha256']==read(checked(pair['lock']['last_legal_delivery']))['tree_sha256']:
   delivery={**code,'kind':'delivery','endpoint_lock':pair['lock']['last_legal_delivery'],'same_tree_score_reference':code['_reference'],'model_calls':0};delivery.pop('_reference',None);path=ep.parent/'scores'/z/'delivery-reused.json';save(path,delivery);delivery['_reference']=reference(path)
  else:delivery=score(row,z,ep,'delivery')
  scores={'code':code,'delivery':delivery}
  if code['status'] not in ('official_report','candidate_execution_failed') or delivery['status'] not in ('official_report','candidate_execution_failed','no_legal_delivery'):fault(i,{'scoring':scores});return {'status':'scoring_unknown','scores':scores}
  g=read(ep/'progress.json');b=read(ep/'boundary.json')
  return {'status':'scored','code_correct':code['resolved'],'legal_correct':delivery['resolved'],'logical_tokens':g['logical_total_tokens'],'formal_submission':g['lifecycle']['terminal']=='DELIVERED','episode':reference(ep/'result.json'),'scores':{k:v['_reference'] for k,v in scores.items()},'normal_budget_stop':any('budget_exhausted' in v for v in b['role_stops'].values()),'termination_class':b['termination_class'],'stage_wait_corrections':b['stage_wait_corrections']}
 lanes=SplitLanes(12,2);prep_pool=concurrent.futures.ThreadPoolExecutor(max_workers=8);preps={r['index']:prep_pool.submit(prepare,r) for r in rows}
 try:
  for phase in ('dev1','dev2','confirm'):
   if stop.is_set():break
   frozen=json.loads(json.dumps(policy));save(OUT/(phase+'-policy.json'),frozen);panel_jobs={};panels={}
   futures=[preps[r['index']] for r in rows if r['phase']==phase]
   for f in concurrent.futures.as_completed(futures):
    row=f.result()
    if not row or stop.is_set():continue
    i=row['index'];root=OUT/f'task-{i:02d}';bank_path=root/'GENERATOR/candidate-bank.json';bank=read(bank_path);decision=evaluate(read(root/'PREFIX/decision-state.json'),bank,frozen,row['seed']);save(root/'decision.json',decision)
    if decision['feature_degenerate']:status(i,'feature_unqualified');continue
    slots={'v218:'+root.name+':'+z:bank['remaining_branch_token_limit'] for z in bank['candidates']}
    if not reserve(i,root/'branches',slots):continue
    panels[i]={'index':i,'phase':phase,'instance_id':row['instance_id'],'repo':row['repo'],'scene':row['coverage_type'],'decision':decision,'bank':reference(bank_path),'outcomes':{}}
    order=[decision['selected']]+[z for z in bank['candidates'] if z!=decision['selected']]
    for z in order:
     job=(row,z,bank_path);panel_jobs[lanes.submit(lambda j=job:generate(j),grade)]=job
   for f in concurrent.futures.as_completed(panel_jobs):
    row,z,bank=panel_jobs[f];i=row['index']
    try:result=f.result()
    except Exception as e:result={'status':'isolated_exception','type':type(e).__name__,'error':str(e)};fault(i,result)
    panels[i]['outcomes'][z]=result;status(f'{i}:{z}',result['status'])
    if len(panels[i]['outcomes'])==len(read(bank)['candidates']):
     panels[i]['complete']=all(v['status']=='scored' for v in panels[i]['outcomes'].values());save(OUT/f'task-{i:02d}/panel-result.json',panels[i]);status(i,'closed' if panels[i]['complete'] else 'closed_with_unknown')
   current=list(panels.values());records+=current;save(OUT/(phase+'-results.json'),current)
   if phase!='confirm':
    complete=[p for p in current if p['complete']]
    if complete:policy=update(policy,complete,'v218-'+phase);save(OUT/f'policy-{policy["update"]}.json',policy)
    else:save(OUT/(phase+'-no-update.json'),{'reason':'No complete eligible panels; no synthetic update'})
  save(OUT/'all-results.json',records)
 finally:prep_pool.shutdown(wait=True);lanes.close()
 save(OUT/'finished.json',{'status':'paused_shared_infrastructure' if stop.is_set() else 'completed_with_isolated_unknowns' if faults.rows else 'completed','cash':ledger.snapshot(),'policy_update':policy['update'],'finished':time.time()})
 status('coordinator','finished')
 run('report_organization_pilot_v218.py',[],OUT/'report.log')
if __name__=='__main__':main()
