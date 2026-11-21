"""Four full W0/W1 pairs; no C/N fitting, candidate search, or automatic model replay."""
import concurrent.futures,json,os,subprocess,threading,time,traceback
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked,read_episode_candidates
from proworksim.software_organization_api_v223_1 import Ledger
from proworksim.software_organization_capacity_v212 import Capacity,Probe,PROFILE
from proworksim.software_streaming_lanes_v217_2 import SplitLanes
from proworksim.software_queue_resilience_v217_1 import FaultRegistry
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v223-1/protocol-r1';OUT=R/'runs/software-benchmark-v223-1/paired4-r1';ENV=R/'runs/software-benchmark-v223-1/environment-r1';LEDGER=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return None
def save(p,v):atomic_write(p,json_bytes(v))
def main():
 assert read(P/'admission.json')['passed']
 for ref in read(P/'deployment-freeze.json')['files']:checked(ref)
 OUT.mkdir(parents=True,exist_ok=False);plan=read(P/'candidate-tasks.json');ledger=Ledger(LEDGER);ledger.reserve_panel()
 cap=Capacity(Probe(R),{**PROFILE,'generation_limit':8,'starting_generation_limit':4,'managed_memory_budget_bytes':512*1024**3})
 mu=threading.RLock();stop=threading.Event();faults=FaultRegistry();states={};completed_branches={};in_progress_pairs=set()
 env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
 def status(key,state,**kw):
  with mu:
   states[str(key)]={'status':state,**kw};save(OUT/'progress.json',{'status':'finished' if key=='coordinator' else 'paused_new_admissions' if stop.is_set() else 'running','states':states,'cash':ledger.snapshot(),'capacity':cap.snapshot(),'at':time.time()})
 def fault(i,value):
  with mu:
   if faults.record(i,value)['pause_new_admissions']:stop.set()
   save(OUT/'exception-queue.json',{'items':faults.rows,'shared_fault_pause':stop.is_set(),'automatic_model_retries':0})
 def acquire(key,kind):
  while True:
   if stop.is_set() and kind=='generation':raise RuntimeError('Repeated shared infrastructure fault: new admissions paused')
   if cap.acquire(key,kind)[0]:return
   time.sleep(3)
 def release_unused(slot):
  with ledger.db() as c:
   if not c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():c.execute('UPDATE block_slots SET status="not_started" WHERE slot=? AND status="pending"',(slot,))
 def run(script,args,log,lease=None):
  log.parent.mkdir(parents=True,exist_ok=True)
  with log.open('xb') as f:
   child=subprocess.Popen([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT)
   while child.poll() is None:
    if lease and (read(Path(args[args.index('--output')+1])/'result.json') or {}).get('status') not in (None,'preparing'):cap.ready(lease)
    time.sleep(3)
   return child.returncode
 def prepare(row):
  i=row['index'];root=OUT/f'task-{i:02d}';root.mkdir();key=f'prefix:{i}';slot='v223.1:'+root.name+':PREFIX';proceed=False
  try:
   from proworksim.software_organization_api_v223_1 import AdmissionStopped
   while True:
    if stop.is_set():raise RuntimeError('Shared fault pause before starting new pair')
    try:
     with mu:ledger.reserve_pair(i);in_progress_pairs.add(i)
     break
    except AdmissionStopped:
     with mu:can_release_later=bool(in_progress_pairs)
     if not can_release_later:status(i,'cash_not_admitted');return None
     status(i,'waiting_pair_cash_headroom');time.sleep(3)
   qpath=ENV/f'task-{i:02d}/qualification.json'
   while not qpath.exists():
    paths={k:ENV/f'task-{i:02d}'/k/'receipt.json' for k in ('gold','empty')}
    if all(p.exists() for p in paths.values()):
     qpath=root/'environment-qualification.json';receipts={k:read(p) for k,p in paths.items()};save(qpath,{'qualified':all(v.get('status')=='official_report' and v.get('resolved')==(k=='gold') and v.get('cleanup_errors')==[] for k,v in receipts.items()),'proof':{k:reference(p) for k,p in paths.items()}});break
    if stop.is_set() or (ENV/'finished.json').exists():raise RuntimeError('Environment unavailable; retain original task identity')
    status(i,'waiting_environment');time.sleep(5)
   q=read(qpath)
   if not q['qualified']:status(i,'environment_unqualified',qualification=q);return None
   ledger.reserve_stage(slot);acquire(key,'generation');status(i,'prefix_running',instance_id=row['instance_id'])
   prefix=root/'PREFIX';run('run_organization_demand_episode_v223_1.py',['--index',i,'--condition','PREFIX','--output',prefix,'--ledger',LEDGER],root/'prefix.log',key)
   result=read(prefix/'result.json') or {'status':'technical_unknown','reason':'missing_prefix_result'}
   if result['status']=='no_eligible_decision_state':status(i,'no_eligible_state',result=result);return None
   if result['status']!='decision_checkpoint_ready':fault(i,result);status(i,'prefix_unavailable',result=result);return None
   cap.ready(key);status(i,'shared_graph_review')
   graphslot='v223.1:'+root.name+':GRAPH';ledger.reserve_stage(graphslot)
   try:
    run('review_project_graph_v223_1.py',['--index',i,'--prefix',prefix,'--output',root/'GRAPH','--ledger',LEDGER],root/'graph-review.log')
   finally:release_unused(graphslot)
   reviewed=read(root/'GRAPH/result.json') or {'status':'technical_unknown','reason':'missing_graph_review'}
   if reviewed['status']!='graph_context_ready':fault(i,reviewed);status(i,'graph_review_unknown',result=reviewed);return None
   status(i,'common_checkpoint_ready');proceed=True;return row
  except Exception as e:fault(i,{'type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()});status(i,'prepare_unknown');return None
  finally:
   cap.release(key);release_unused(slot)
   if not proceed:
    ledger.finish_pair(i)
    with mu:in_progress_pairs.discard(i)
 def generate(row,z):
  i=row['index'];root=OUT/f'task-{i:02d}';ep=root/z;gen=root/('GEN-'+z);key=f'{i}:{z}';slots=[]
  try:
   acquire(key,'generation');status(key,'generating_proposal')
   slot='v223.1:'+root.name+':GEN-'+z;ledger.reserve_stage(slot);slots.append(slot)
   run('generate_organization_candidates_v223_1.py',['--index',i,'--condition',z,'--prefix',root/'PREFIX','--output',gen,'--ledger',LEDGER],gen.with_suffix('.log'))
   gr=read(gen/'result.json') or {'status':'technical_unknown','reason':'missing_generator_result'}
   if gr['status']!='candidate_bank_ready':return row,z,ep,gr
   slot='v223.1:'+root.name+':'+z;limit=ledger.reserve_stage(slot);slots.append(slot)
   bank=gen/'candidate-bank.json';assert limit==read(bank)['remaining_branch_token_limit']
   status(key,'continuing',selected=read(bank)['selected'])
   run('run_organization_demand_episode_v223_1.py',['--index',i,'--condition',z,'--output',ep,'--checkpoint',root/'PREFIX/checkpoint','--bank',bank,'--ledger',LEDGER],ep.with_suffix('.log'),key)
   result=read(ep/'result.json') or {'status':'technical_unknown','reason':'missing_generation_result'}
   return row,z,ep,result
  except Exception as e:
   return row,z,ep,{'status':'technical_unknown','type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()}
  finally:
   cap.release(key)
   for s in slots:release_unused(s)
 def score(row,z,ep,kind):
  for attempt in range(2):
   dest=ep.parent/'scores'/z/f'{kind}-{attempt}';key='score:'+str(dest);acquire(key,'grader')
   try:
    rc=run('score_organization_demand_v223_1.py',['--index',row['index'],'--kind',kind,'--episode',ep,'--output',dest],dest.with_suffix('.log'))
    receipt=read(dest/'receipt.json') or {'status':'technical_unknown','exit':rc}
    if (dest/'receipt.json').exists():receipt['_reference']=reference(dest/'receipt.json')
    if receipt['status'] in ('official_report','candidate_execution_failed','no_legal_delivery') or receipt.get('official_result'):return receipt
   finally:cap.release(key)
  return receipt
 def grade_one(value):
  row,z,ep,result=value;i=row['index'];key=f'{i}:{z}'
  if result['status']!='closed':fault(i,result);status(key,'generation_unknown');return {'status':'generation_unknown','result':result}
  status(key,'scoring');code=score(row,z,ep,'code');pair=read_episode_candidates(read(ep/'candidate-lock.json'))
  if code['status'] in ('official_report','candidate_execution_failed') and pair['lock'].get('last_legal_delivery') and read(checked(pair['lock']['terminal_code']))['tree_sha256']==read(checked(pair['lock']['last_legal_delivery']))['tree_sha256']:
   delivery={**code,'kind':'delivery','endpoint_lock':pair['lock']['last_legal_delivery'],'same_tree_score_reference':code['_reference'],'model_calls':0};delivery.pop('_reference',None);path=ep.parent/'scores'/z/'delivery-reused.json';save(path,delivery);delivery['_reference']=reference(path)
  else:delivery=score(row,z,ep,'delivery')
  scores={'code':code,'delivery':delivery};g=read(ep/'cost-endpoints.json')
  known=code['status'] in ('official_report','candidate_execution_failed') and delivery['status'] in ('official_report','candidate_execution_failed','no_legal_delivery')
  if not known:fault(i,{'scoring':scores})
  result={'status':'scored' if known else 'scoring_unknown','code_correct':code.get('resolved'),'legal_correct':delivery.get('resolved'),'logical_tokens':g['logical_total_tokens'],'episode':reference(ep/'result.json'),'scores':{k:v.get('_reference') for k,v in scores.items()}}
  save(ep.parent/(z+'-result.json'),result);status(key,result['status']);return result
 def grade(value):
  try:return grade_one(value)
  finally:
   i=value[0]['index']
   with mu:
    completed_branches[i]=completed_branches.get(i,0)+1
    if completed_branches[i]==2:
     in_progress_pairs.discard(i)
     released=ledger.finish_pair(i);save(OUT/f'task-{i:02d}/pair-settlement.json',{'released':released,'both_branch_callbacks_finished':True,'at':time.time()})
 lanes=SplitLanes(8,2);pool=concurrent.futures.ThreadPoolExecutor(max_workers=4);preps={pool.submit(prepare,r):r for r in plan['rows']};jobs={};results={}
 try:
  for f in concurrent.futures.as_completed(preps):
   row=f.result()
   if row and not stop.is_set():
    for z in ('W0','W1'):jobs[lanes.submit(lambda r=row,c=z:generate(r,c),grade)]=(row,z)
  for f in concurrent.futures.as_completed(jobs):
   row,z=jobs[f];key=str(row['index'])+':'+z
   try:results[key]=f.result()
   except Exception as e:results[key]={'status':'isolated_exception','type':type(e).__name__,'error':str(e)};fault(row['index'],results[key]);status(key,'isolated_exception')
   save(OUT/'all-results.json',results)
 finally:pool.shutdown(wait=True);lanes.close()
 released=ledger.finish();save(OUT/'finished.json',{'status':'completed_with_unknowns' if faults.rows else 'completed_with_unqualified_states' if len(results)<8 else 'completed','results':results,'cash':ledger.snapshot(),'envelope_released':released,'at':time.time(),'C_N_updates':0});status('coordinator','finished')
if __name__=='__main__':main()
