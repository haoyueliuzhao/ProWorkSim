"""Two independent development windows; complete-panel updates and isolated faults."""
import concurrent.futures,json,os,subprocess,threading,time,traceback
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked,read_episode_candidates
from proworksim.software_mapping_api_v224 import Ledger,AdmissionStopped
from proworksim.software_mapping_selector_v224 import initialize,evaluate,update
from proworksim.software_organization_capacity_v212 import Capacity,Probe,PROFILE
from proworksim.software_streaming_lanes_v217_2 import SplitLanes
from proworksim.software_queue_resilience_v217_1 import FaultRegistry
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v224/protocol-r1';OUT=R/'runs/software-benchmark-v224/development4-r1';ENV=R/'runs/software-benchmark-v224/environment-r1';L=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return None
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);atomic_write(p,json_bytes(v))
def main():
 assert read(P/'admission.json')['passed']
 for ref in read(P/'deployment-freeze.json')['files']:checked(ref)
 OUT.mkdir(parents=True,exist_ok=False);plan=read(P/'candidate-tasks.json');ledger=Ledger(L);ledger.reserve_batch();policy=initialize();save(OUT/'policy-0.json',policy)
 cap=Capacity(Probe(R),{**PROFILE,'generation_limit':8,'starting_generation_limit':4,'managed_memory_budget_bytes':512*1024**3});mu=threading.RLock();stop=threading.Event();faults=FaultRegistry();states={};pending_panels={};running_work=set();phase='dev1'
 env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
 def status(key,state,**kw):
  with mu:states[str(key)]={'status':state,**kw};save(OUT/'progress.json',{'status':'paused_new_admissions' if stop.is_set() else 'running','phase':phase,'policy_updates':policy['update'],'states':states,'cash':ledger.snapshot(),'capacity':cap.snapshot(),'at':time.time()})
 def fault(i,value):
  with mu:
   if faults.record(i,value)['pause_new_admissions']:stop.set()
   save(OUT/'exception-queue.json',{'items':faults.rows,'shared_fault_pause':stop.is_set(),'model_replays':0})
 def release_unused(slot):
  with ledger.db() as c:
   if not c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():c.execute('UPDATE block_slots SET status="not_started" WHERE slot=? AND status="pending"',(slot,))
 def acquire(key,kind):
  while True:
   if stop.is_set() and kind=='generation':raise RuntimeError('Shared fault pause')
   if cap.acquire(key,kind)[0]:return
   time.sleep(3)
 def run(script,args,log,lease=None):
  log.parent.mkdir(parents=True,exist_ok=True)
  with log.open('xb') as f:
   child=subprocess.Popen([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT)
   while child.poll() is None:
    if lease and (read(Path(args[args.index('--output')+1])/'result.json') or {}).get('status') not in (None,'preparing'):cap.ready(lease)
    time.sleep(3)
   return child.returncode
 def prepare(row):
  i=row['index'];root=OUT/f'task-{i:02d}';root.mkdir();key=f'prep:{i}';slots=[]
  try:
   q=read(ENV/f'task-{i:02d}/qualification.json')
   if not q or not q['qualified']:status(i,'environment_unqualified',qualification=q);return None
   for ref in q['proof'].values():checked(ref)
   while True:
    if stop.is_set():return None
    try:
     with mu:ledger.reserve_prep(i);running_work.add(key)
     break
    except AdmissionStopped:
     with mu:can_wait=bool(running_work)
     if not can_wait:status(i,'preparation_cash_not_admitted');return None
     status(i,'preparation_waiting_cash');time.sleep(3)
   acquire(key,'generation');status(i,'prefix_running',instance_id=row['instance_id'])
   slot=f'v224:task-{i:02d}:PREFIX';ledger.reserve_stage(slot);slots.append(slot);prefix=root/'PREFIX'
   run('run_mapping_episode_v224.py',['--index',i,'--condition','PREFIX','--output',prefix,'--ledger',L],root/'prefix.log',key)
   result=read(prefix/'result.json') or {'status':'technical_unknown','reason':'missing_prefix_result'}
   if result['status']=='no_eligible_decision_state':status(i,'no_real_decision_window',result=result);return None
   if result['status']!='decision_checkpoint_ready':fault(i,result);status(i,'prefix_unknown');return None
   cap.ready(key);status(i,'graph_review');slot=f'v224:task-{i:02d}:GRAPH';ledger.reserve_stage(slot);slots.append(slot)
   run('review_mapping_graph_v224.py',['--index',i,'--prefix',prefix,'--output',root/'GRAPH','--ledger',L],root/'graph.log')
   graph=read(root/'GRAPH/result.json') or {'status':'technical_unknown'}
   if graph['status']!='graph_context_ready':fault(i,graph);status(i,'graph_unknown');return None
   status(i,'OA_candidate_generation');slot=f'v224:task-{i:02d}:GENERATOR';ledger.reserve_stage(slot);slots.append(slot)
   run('generate_mapping_candidates_v224.py',['--index',i,'--condition','OA','--prefix',prefix,'--output',root/'GENERATOR','--ledger',L],root/'generator.log')
   gen=read(root/'GENERATOR/result.json') or {'status':'technical_unknown'}
   if gen['status']!='candidate_bank_ready':fault(i,gen);status(i,'generator_unknown');return None
   status(i,'panel_ready',candidate_count=gen['candidate_count']);return row
  except Exception as e:fault(i,{'type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()});status(i,'preparation_unknown');return None
  finally:
   cap.release(key)
   for s in slots:release_unused(s)
   ledger.finish_block(f'prep-{i}')
   with mu:running_work.discard(key)
 def generate(row,z,bank):
  i=row['index'];ep=OUT/f'task-{i:02d}'/z;key=f'gen:{i}:{z}';slot=f'v224:task-{i:02d}:'+z
  try:
   acquire(key,'generation');status(f'{i}:{z}','generating')
   run('run_mapping_episode_v224.py',['--index',i,'--condition',z,'--output',ep,'--checkpoint',ep.parent/'PREFIX/checkpoint','--bank',bank,'--ledger',L],ep.with_suffix('.log'),key)
   return row,z,ep,read(ep/'result.json') or {'status':'technical_unknown','reason':'missing_native_result'}
  except Exception as e:return row,z,ep,{'status':'technical_unknown','error':str(e),'traceback':traceback.format_exc()}
  finally:cap.release(key);release_unused(slot)
 def score(row,z,ep,kind):
  for attempt in range(2):
   dest=ep.parent/'scores'/z/f'{kind}-{attempt}';key='score:'+str(dest);acquire(key,'grader')
   try:
    rc=run('score_mapping_v224.py',['--index',row['index'],'--kind',kind,'--episode',ep,'--output',dest],dest.with_suffix('.log'))
    receipt=read(dest/'receipt.json') or {'status':'technical_unknown','exit':rc}
    if (dest/'receipt.json').exists():receipt['_reference']=reference(dest/'receipt.json')
    if receipt['status'] in ('official_report','candidate_execution_failed','no_legal_delivery') or receipt.get('official_result'):return receipt
   finally:cap.release(key)
  return receipt
 def grade_one(value):
  row,z,ep,result=value;i=row['index']
  if result['status']!='closed':fault(i,result);return {'status':'generation_unknown','result':result}
  status(f'{i}:{z}','scoring');code=score(row,z,ep,'code');pair=read_episode_candidates(read(ep/'candidate-lock.json'))
  if code['status'] in ('official_report','candidate_execution_failed') and pair['lock'].get('last_legal_delivery') and read(checked(pair['lock']['terminal_code']))['tree_sha256']==read(checked(pair['lock']['last_legal_delivery']))['tree_sha256']:
   delivery={**code,'kind':'delivery','endpoint_lock':pair['lock']['last_legal_delivery'],'same_tree_score_reference':code['_reference'],'model_calls':0};delivery.pop('_reference',None);p=ep.parent/'scores'/z/'delivery-reused.json';save(p,delivery);delivery['_reference']=reference(p)
  else:delivery=score(row,z,ep,'delivery')
  known=code['status'] in ('official_report','candidate_execution_failed') and delivery['status'] in ('official_report','candidate_execution_failed','no_legal_delivery') and type(code.get('resolved')) is bool and type(delivery.get('resolved')) is bool
  if not known:fault(i,{'scoring':{'code':code,'delivery':delivery}})
  boundary=read(ep/'boundary.json');receipts=boundary['outcomes'];actions={}
  for o in receipts:
   name=o.get('decision',{}).get('action')
   if o.get('response',{}).get('ok') and name in ('split_work','assign_work','offer_joint_arrangement','accept_joint_arrangement','accept_transfer','change_dependency','assign_verification','integrate_patch'):actions[name]=actions.get(name,0)+1
  choice=(read(ep/'progress.json').get('lifecycle') or {}).get('choice');
  v={'actual_organization_action_counts':actions,'actual_choice':choice,'status':'scored' if known else 'scoring_unknown','code_correct':code.get('resolved'),'legal_correct':delivery.get('resolved'),'logical_tokens':read(ep/'cost-endpoints.json')['logical_total_tokens'],'episode':reference(ep/'result.json'),'scores':{'code':code.get('_reference'),'delivery':delivery.get('_reference')}};save(ep.parent/(z+'-result.json'),v);status(f'{i}:{z}',v['status']);return v
 def grade(value):
  try:return grade_one(value)
  finally:
   i=value[0]['index']
   with mu:
    pending_panels[i]-=1
    if pending_panels[i]==0:ledger.finish_block(f'panel-{i}');running_work.discard('panel:'+str(i))
 def dispatch(row,lanes,current_policy):
  i=row['index'];root=OUT/f'task-{i:02d}';bankpath=root/'GENERATOR/candidate-bank.json';bank=read(bankpath);state=read(root/'GENERATOR/condition-state.json');dec=evaluate(state,bank,current_policy,row['seed']);save(root/'decision.json',dec)
  while True:
   if stop.is_set():return None
   try:
    with mu:ledger.reserve_panel(i,list(bank['candidates']),bank['remaining_branch_token_limit']);pending_panels[i]=len(bank['candidates']);running_work.add('panel:'+str(i))
    break
   except AdmissionStopped:
    with mu:can_wait=bool(running_work)
    if not can_wait:status(i,'whole_panel_cash_not_admitted');return None
    status(i,'panel_waiting_cash');time.sleep(3)
  status(i,'candidate_panel_started',selected=dec['selected'],probabilities=dec['probabilities'],policy_update=dec['policy_update'],candidate_count=len(bank['candidates']))
  order=[dec['selected']]+[z for z in bank['candidates'] if z!=dec['selected']]
  return {'row':row,'decision':dec,'bank':reference(bankpath),'jobs':{z:lanes.submit(lambda z=z:generate(row,z,bankpath),grade) for z in order}}
 all_records=[]
 try:
  for phase in ('dev1','dev2'):
   if stop.is_set():break
   save(OUT/(phase+'-policy-before.json'),policy);current_policy=policy;rows=[r for r in plan['rows'] if r['phase']==phase];lanes=SplitLanes(8,2);panels=[]
   try:
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     futures=[pool.submit(prepare,r) for r in rows]
     for f in concurrent.futures.as_completed(futures):
      row=f.result()
      if row:
       panel=dispatch(row,lanes,current_policy)
       if panel:panels.append(panel)
    records=[]
    for panel in panels:
     outcomes={}
     for z,f in panel['jobs'].items():
      try:outcomes[z]=f.result()
      except Exception as e:outcomes[z]={'status':'technical_unknown','error':str(e)};fault(panel['row']['index'],outcomes[z])
     row=panel['row'];record={'index':row['index'],'instance_id':row['instance_id'],'repo':row['repo'],'phase':phase,'decision':panel['decision'],'outcomes':outcomes,'bank':panel['bank'],'complete':all(v['status']=='scored' for v in outcomes.values()),'planned_window_states':2};save(OUT/f'task-{row["index"]:02d}/panel-result.json',record);records.append(record);status(row['index'],'panel_closed',complete=record['complete'])
    save(OUT/(phase+'-results.json'),records);policy=update(current_policy,records,phase);save(OUT/(phase+'-policy-after.json'),policy);save(OUT/'policy-latest.json',policy);all_records+=records
   finally:lanes.close()
  save(OUT/'frozen-development-policy.json',policy)
 except BaseException as e:fault('coordinator',{'type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()})
 released=ledger.finish();save(OUT/'finished.json',{'status':'closed_with_unknowns' if faults.rows else 'completed','policy_updates':policy['update'],'planned_states':4,'completed_panels':len(all_records),'informative_complete_panels':sum(r['complete'] and len(r['outcomes'])>1 and not r['decision']['feature_degenerate'] for r in all_records),'records':all_records,'policy':policy,'cash':ledger.snapshot(),'holds_released':released,'v225_started':False,'at':time.time()})
if __name__=='__main__':main()
