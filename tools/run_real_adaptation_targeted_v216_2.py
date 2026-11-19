"""Four targeted independent continuations from frozen real-state checkpoints.

No automatic candidate/model resampling after real generation. Every state is
isolated; scores are asynchronous and cannot be observed by solver/generator.
"""
import concurrent.futures,json,os,subprocess,threading,time
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_organization_api_v216_2 import Ledger,AdmissionStopped
from proworksim.software_organization_capacity_v212 import Capacity,Probe,PROFILE
from proworksim.software_benchmark_candidates_v054 import checked,reference
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v216/targeted-closure-r1';OUT=R/'runs/software-benchmark-v216/targeted-closure4-r1';OUT.mkdir(parents=True,exist_ok=False)
def read(p):return json.loads(p.read_text()) if p.exists() else None
proof=read(R/'runs/software-benchmark-v216/sdk-control-v216-2-r1/summary.json')
if not(proof and proof.get('passed') and proof.get('terminal_delivery_stopped_scheduler') and proof.get('model_provider_calls')==0):raise ValueError('New lifecycle SDK gate required')
plan=read(P/'candidate-tasks.json');assert len(plan['rows'])==2
prior_root=R/'runs/software-benchmark-v216/target-repair6-r1'
assert read(prior_root/'progress.json')['status']=='closed'
for r in read(P/'deployment-freeze.json')['files']:checked(r)
ledger_path=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite';ledger=Ledger(ledger_path)
capacity=Capacity(Probe(R),{**PROFILE,'generation_limit':4,'starting_generation_limit':4});mutex=threading.RLock();scoreslots=threading.Semaphore(2)
states={str(r['index']):{'instance_id':r['instance_id'],'status':'queued'} for r in plan['rows']}
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
def update(i,status,**kw):
 with mutex:
  states[str(i)].update(status=status,**kw);atomic_write(OUT/'progress.json',json_bytes({'status':'running','states':states,'at':time.time(),'capacity':capacity.snapshot(),'ledger':str(ledger_path),'C_N_update':False}))
def run(script,args,log):
 log.parent.mkdir(parents=True,exist_ok=True)
 with log.open('xb') as f:return subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
def acquire(key,kind,n=1):
 while not capacity.acquire(key,kind,n)[0]:time.sleep(5)
def reserve(i,block,slots,phase):
 while True:
  try:ledger.reserve_block(block,slots,phase=phase);return True
  except AdmissionStopped as e:
   with ledger.db() as c:pending=c.execute('SELECT count(*) FROM slots WHERE status="active"').fetchone()[0]+c.execute('SELECT count(*) FROM block_slots WHERE status="pending"').fetchone()[0]
   if not pending:update(i,'not_started_cash',reason=str(e));return False
   update(i,'waiting_complete_block_cash',reason=str(e));time.sleep(10)
def unused_release(slot):
 with ledger.db() as c:
  if not c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():c.execute('UPDATE block_slots SET status="not_started_environment_failure" WHERE slot=? AND status="pending"',(slot,))
def score(i,kind,out,episode):
 with scoreslots:
  key='score:'+str(out);acquire(key,'grader')
  try:
   rc=run('score_real_adaptation_v216.py',['--index',i,'--kind',kind,'--output',out,'--episode',episode],out.with_suffix('.log'));return read(out/'receipt.json') or {'status':'technical_unknown','exit':rc}
  finally:capacity.release(key)
def branch(i,z,out,checkpoint,bank):
 rc=run('run_real_adaptation_episode_v216_2.py',['--index',i,'--condition',z,'--output',out,'--checkpoint',checkpoint,'--bank',bank,'--ledger',ledger_path],out.with_suffix('.log'));unused_release('v216:'+out.parent.name+':'+out.name);return read(out/'result.json') or {'status':'technical_unknown','exit':rc}
def task(row):
 i=row['index'];root=OUT/f'r3-task-{i:02d}';root.mkdir()
 try:
  for k,proof in row['reused_exact_environment_controls'].items():
   v=read(checked(proof));assert v['status']=='official_report' and v['resolved']==(k=='gold')
  prefix=checked(row['reused_checkpoint_manifest']).parent
  bank=checked(row['reused_candidate_bank']);b=read(bank)
  atomic_write(root/'independent-attempt.json',json_bytes({'old_main_results_retained':True,'new_attempt':True,'checkpoint':row['reused_checkpoint_manifest'],'bank':row['reused_candidate_bank'],'no_new_prefix_or_generator_calls':True,'configuration_revision':'v216.2'}))
  slots={'v216:'+root.name+':'+z:b['remaining_branch_token_limit'] for z in ('KEEP','ADAPT')}
  if not reserve(i,str(root),slots,'A'):return
  key='run:'+str(i);acquire(key,'generation',2);update(i,'generating_paired_continuations',bank=reference(bank),remaining_each=b['remaining_branch_token_limit'],prefix_tokens=b['prefix_tokens'],generator_tokens=b['actual_generator_tokens'])
  stop=threading.Event()
  def ready():
   while not stop.wait(5):
    rr=[read(root/z/'result.json') for z in ('KEEP','ADAPT')]
    if all(r and r['status']!='preparing' for r in rr):capacity.ready(key);return
  watch=threading.Thread(target=ready,daemon=True);watch.start()
  try:
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    jobs={z:pool.submit(branch,i,z,root/z,prefix,bank) for z in ('KEEP','ADAPT')};results={z:f.result() for z,f in jobs.items()}
  finally:stop.set();watch.join();capacity.release(key)
  update(i,'scoring',generation={z:r['status'] for z,r in results.items()});scores={}
  for z,r in results.items():
   if r['status']!='closed':scores[z]={'status':'generation_unknown'};continue
   code=score(i,'code',root/f'scores/{z}/code',root/z);delivery=score(i,'delivery',root/f'scores/{z}/delivery',root/z)
   scores[z]={'status':'scored' if code.get('status')=='official_report' and delivery.get('status') in ('official_report','no_legal_delivery') else 'scoring_unknown','code':code.get('resolved'),'delivery':delivery.get('resolved')}
  update(i,'closed' if all(s['status']=='scored' for s in scores.values()) else 'closed_with_unknown',scores=scores)
 except BaseException as e:update(i,'isolated_exception',error={'type':type(e).__name__,'message':str(e)})
 finally:
  for key in ('prefix:'+str(i),'generator:'+str(i),'run:'+str(i)):capacity.release(key)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(task,plan['rows']))
facts=[]
for row in plan['rows']:
 i=row['index'];root=OUT/f'r3-task-{i:02d}';ep=root/'ADAPT';r=read(ep/'result.json') or {};d=read(ep/'dynamic-final.json') or {};cost=read(ep/'cost-endpoints.json') or {};state=read(root/'PREFIX/decision-state.json') or {};f={'index':i,'instance_id':row['instance_id'],'closed':r.get('status')=='closed','formal_delivery':False,'actual_post_progress_adaptation':False,'partner_code_integrated':False,'no_post_delivery_requests':False,'final_evidence_current':False}
 if f['closed']:
  world=read(ep/'final-world.json');sw=world['projects']['SOFTWARE27']['software'];protocol=sw['protocol_v216'];choice=protocol['choice'];events=world['software_events'];f['formal_delivery']=protocol['terminal']=='DELIVERED' and bool(sw['deliveries']);f['choice']=choice
  accepted=[e for e in events if e['kind']=='organization_v213:joint_accepted' and choice and choice['decision']=='attempt' and e['sequence']>choice['event_sequence']]
  followed=[]
  for e in accepted:
   later=[x for x in events if x['sequence']>e['sequence'] and ((x['kind']=='organization_v213:work_performed' and x['actor_id']==e['actor_id'] and x.get('task_id')==e['task_id']) or (x['kind']=='organization_v213:evidence_completed' and x.get('checker')==e['actor_id'] and x.get('task_id')==e['task_id']))]
   if later:followed.append({'offer_id':e['offer_id'],'task_id':e['task_id'],'accept_sequence':e['sequence'],'followthrough_sequences':[x['sequence'] for x in later]})
  f['actual_post_progress_adaptation']=bool(followed);f['adaptation_chains']=followed;packages=d.get('delivery_gaps',{}).get('packages',[])
  f['partner_code_integrated']=any(t['completion'] and t['completion'].get('kind')=='code' and t['completion']['author']=='member_002' and 'integrate_partner_patch' not in t['missing'] and 'member_002' in d['work'][t['task_id']]['authors'] for t in packages)
  f['final_evidence_current']=all(not t['missing'] for t in packages);f['no_post_delivery_requests']=f['formal_delivery'] and cost.get('physical_requests_after_delivered')==0
 facts.append(f)
keep_integrity=[]
for row in plan['rows']:
 ep=OUT/f"r3-task-{row['index']:02d}"/'KEEP';d=read(ep/'dynamic-final.json') or {}
 bank=read(checked(row['reused_candidate_bank']));original=bank['selected']['KEEP']['target']['work']
 observed=d.get('work',{})
 valid=bool(observed) and set(observed)==set(original) and all(all(observed[k].get(field)==v.get(field) for field in ('owner','scope','children','depends_on','mode')) for k,v in original.items())
 keep_integrity.append({'index':row['index'],'scope_owner_dependency_mode_preserved':valid})
passed=all(x['scope_owner_dependency_mode_preserved'] for x in keep_integrity) and sum(f['actual_post_progress_adaptation'] for f in facts)>=2 and sum(f['formal_delivery'] and f['final_evidence_current'] and f['no_post_delivery_requests'] for f in facts)>=2 and any(f['formal_delivery'] and f['partner_code_integrated'] for f in facts)
atomic_write(OUT/'stage-b-gate.json',json_bytes({'passed':passed,'facts':facts,'KEEP_integrity':keep_integrity,'B_model_calls_started':False,'new_phase_requires_frozen_new_state_panel':True,'automatic_repeat':False,'next_action':'mechanism gate passed; separately freeze new development panel before B' if passed else 'repair only observed blockers; do not repeat the whole regression automatically'}))
atomic_write(OUT/'progress.json',json_bytes({'status':'closed' if all(x['status']=='closed' for x in states.values()) else 'closed_with_unknown_or_unadmitted','states':states,'at':time.time(),'capacity':capacity.snapshot(),'ledger':ledger.snapshot(),'stage_B_gate_passed':passed,'C_N_update':False}))
