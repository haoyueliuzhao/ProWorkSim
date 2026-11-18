"""Three frozen complete paired blocks; zero-API prep, controlled scores, independent failures.

Only starts after real SDK/container control passes. No C/N update in this stage.
"""
import concurrent.futures,json,os,subprocess,threading,time
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_organization_api_v212 import Ledger,AdmissionStopped
from proworksim.software_organization_capacity_v212 import Capacity,Probe,PROFILE
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v212/stage-a-plan-r1';OUT=R/'runs/software-benchmark-v212/stage-a6-r1';OUT.mkdir(parents=True,exist_ok=False)
proof=json.loads((R/'runs/software-benchmark-v212/sdk-control-r1/restored/summary.json').read_text())
if not (proof.get('passed') and proof.get('actual_isolated_container_RPC') and proof.get('model_provider_calls')==0):raise ValueError('Actual dynamic SDK/container gate required')
plan=json.loads((P/'candidate-tasks.json').read_text());assert len(plan['rows'])==3
from proworksim.software_benchmark_candidates_v054 import checked
for ref in json.loads((P/'deployment-freeze.json').read_text())['files']:checked(ref)
ledger_path=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite';ledger=Ledger(ledger_path)
capacity=Capacity(Probe(R),{**PROFILE,'generation_limit':6,'starting_generation_limit':4})
mutex=threading.RLock();score_semaphore=threading.Semaphore(2);states={str(r['index']):{'instance_id':r['instance_id'],'status':'queued'} for r in plan['rows']}
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
def update(i,status,**values):
 with mutex:
  states[str(i)].update(status=status,**values)
  atomic_write(OUT/'progress.json',json_bytes({'status':'running','states':states,'capacity':capacity.snapshot(),'at':time.time(),'ledger':str(ledger_path),'shared_total_cash_cap':700,'stage_a_estimated_start_line':60,'C_N_update':False}))
def run(script,args,log):
 log.parent.mkdir(parents=True,exist_ok=True)
 with log.open('xb') as f:return subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
def read(p):return json.loads(p.read_text()) if p.exists() else None
def acquire(key,kind,count=1):
 while not capacity.acquire(key,kind,count)[0]:time.sleep(5)
def score(i,kind,out,episode=None):
 with score_semaphore:
  key='score:'+str(out);acquire(key,'grader')
  try:
   args=['--index',i,'--kind',kind,'--output',out]
   if episode:args+=['--episode',episode]
   rc=run('score_repairable_candidate_v212.py',args,out.with_suffix('.log'))
   return read(out/'receipt.json') or {'status':'technical_unknown','exit':rc}
  finally:capacity.release(key)
def branch(i,condition,out,checkpoint):
 rc=run('run_repairable_episode_v212.py',['--index',i,'--condition',condition,'--output',out,'--checkpoint',checkpoint,'--ledger',ledger_path],out.with_suffix('.log'))
 result=read(out/'result.json') or {'status':'technical_unknown','exit':rc}
 # Release only reservations for a proven never-admitted child after process exit.
 slot='v212:'+out.parent.name+':'+out.name
 with ledger.db() as c:
  if not c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():c.execute('UPDATE block_slots SET status="not_started_environment_failure" WHERE slot=? AND status="pending"',(slot,))
 return result

def task(row):
 i=row['index'];root=OUT/f'task-{i:02d}';root.mkdir();prep=root/'initial';key='prep:'+str(i)
 try:
  acquire(key,'generation');update(i,'preparing_initial_checkpoint')
  try:rc=run('run_repairable_episode_v212.py',['--index',i,'--condition','PREPARE','--output',prep,'--ledger',ledger_path],root/'prepare.log')
  finally:capacity.release(key)
  prepared=read(prep/'result.json')
  if not prepared or prepared['status']!='initial_checkpoint_ready':update(i,'initial_environment_unknown',detail=prepared,exit=rc);return
  # Exact image/scorer qualifications from the closed v211 batch are hash-bound.
  for kind,proof in row['reused_exact_environment_controls'].items():
   v=read(checked(proof));assert v['status']=='official_report' and v['resolved']==(kind=='gold')
  checkpoint=prep/'checkpoint';limit=5_000_000-read(checkpoint/'manifest.json')['prefix_tokens'];key='run:'+str(i)
  slots={'v212:'+root.name+':'+z:limit for z in ('SINGLE','COMBO')}
  while True:
   acquire(key,'generation',2)
   try:ledger.reserve_block(str(root),slots);break
   except AdmissionStopped as error:
    capacity.release(key)
    with ledger.db() as c:
     active=c.execute('SELECT count(*) FROM slots WHERE status="active"').fetchone()[0];pending=c.execute('SELECT count(*) FROM block_slots WHERE status="pending"').fetchone()[0]
    if not(active or pending):update(i,'not_started_cash',reason=str(error));return
    update(i,'waiting_whole_block_cash',reason=str(error));time.sleep(10)
  update(i,'generating',checkpoint=prepared['checkpoint'])
  # The actor startup status releases the startup quota, not the generation lease.
  stop=threading.Event()
  def watch_ready():
   while not stop.wait(5):
    rr=[read(root/z/'result.json') for z in ('SINGLE','COMBO')]
    if all(x and x['status']!='preparing' for x in rr):capacity.ready(key);return
  watcher=threading.Thread(target=watch_ready,daemon=True);watcher.start()
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   jobs={z:pool.submit(branch,i,z,root/z,checkpoint) for z in ('SINGLE','COMBO')};results={z:f.result() for z,f in jobs.items()}
  stop.set();watcher.join();capacity.release(key)
  update(i,'scoring',generation={z:r['status'] for z,r in results.items()})
  scores={}
  for z,r in results.items():
   if r['status']!='closed':scores[z]={'status':'generation_unknown'};continue
   code=score(i,'code',root/f'scores/{z}/code',root/z);delivery=score(i,'delivery',root/f'scores/{z}/delivery',root/z)
   scores[z]={'status':'scored' if code.get('status')=='official_report' and delivery.get('status') in ('official_report','no_legal_delivery') else 'scoring_unknown','code':code.get('resolved'),'delivery':delivery.get('resolved')}
  update(i,'closed' if len(scores)==2 and all(x['status']=='scored' for x in scores.values()) else 'closed_with_unknown',scores=scores)
 except BaseException as error:
  update(i,'isolated_exception',error={'type':type(error).__name__,'message':str(error)})
 finally:
  capacity.release('prep:'+str(i));capacity.release('run:'+str(i))
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 list(pool.map(task,plan['rows']))
atomic_write(OUT/'progress.json',json_bytes({'status':'closed' if all(x['status']=='closed' for x in states.values()) else 'closed_with_unknown_or_not_started','states':states,'capacity':capacity.snapshot(),'at':time.time(),'ledger':ledger.snapshot(),'C_N_update':False,'mechanism_effectiveness_not_inferred_from_code_scores':True}))

# A gate uses real protocol facts, independent of official correctness.
rows=[]
for row in plan['rows']:
 i=row['index'];ep=OUT/f'task-{i:02d}'/'COMBO';final=read(ep/'final-world.json');g=read(ep/'result.json') or {};facts={'index':i,'instance_id':row['instance_id'],'closed':g.get('status')=='closed','formal_delivery':False,'partner_code_adopted':False,'midwork_joint':False}
 if final:
  sw=final['projects']['SOFTWARE27']['software'];events=final['software_events'];facts['formal_delivery']=bool(sw['deliveries'])
  # Inspect exact terminal contract checklist for contributor identity and integrated patches.
  dy=read(ep/'dynamic-final.json') or {};tasks=dy.get('delivery_gaps',{}).get('packages',[])
  facts['partner_code_adopted']=facts['formal_delivery'] and any(t['completion'] and t['completion'].get('kind')=='code' and t['completion']['author']=='member_002' and 'integrate_partner_patch' not in t['missing'] for t in tasks)
  actual=[e for e in events if e['kind']=='organization_v212:joint_accepted'];proposal=read(ep/'midwork-proposal.json')
  facts['midwork_joint']=bool(proposal and proposal['eligible'] and any(e['sequence']>proposal['trigger_event_sequence'] and e.get('task_id')==proposal['request']['task_id'] for e in actual))
 rows.append(facts)
passed=sum(r['closed'] and r['formal_delivery'] for r in rows)>=2 and any(r['closed'] and r['formal_delivery'] and r['partner_code_adopted'] for r in rows) and any(r['closed'] and r['formal_delivery'] and r['midwork_joint'] for r in rows)
atomic_write(OUT/'stage-b-gate.json',json_bytes({'passed':passed,'facts':rows,'automatic_rerun':False,'B_model_calls_started':False,'next_action':'freeze state-conditioned candidate banks before B' if passed else 'analyze exact missing path; do not launch B/C or repeat 18'}))
