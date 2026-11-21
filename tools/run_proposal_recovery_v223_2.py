"""One recovery chain; same candidates score asynchronously from model execution end."""
import json,os,subprocess,time,traceback
from pathlib import Path
from proworksim.storage import json_bytes,atomic_write
from proworksim.software_benchmark_candidates_v054 import reference,checked,read_episode_candidates
from proworksim.software_organization_api_v223_2 import Ledger,NEW
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v223-2/protocol-r1';OUT=R/'runs/software-benchmark-v223-2/recovery-r1';TASK=OUT/'task-03';OLD=R/'runs/software-benchmark-v223-1/paired4-r1/task-03';L=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
def read(p):return json.loads(p.read_text()) if p.exists() else None
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);atomic_write(p,json_bytes(v))
def main():
 assert read(P/'admission.json')['passed']
 for ref in read(P/'deployment-freeze.json')['files']:checked(ref)
 OUT.mkdir(parents=True,exist_ok=False);TASK.mkdir();ledger=Ledger(L);ledger.reserve_recovery();slots=[]
 env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
 def status(name,**extra):save(OUT/'progress.json',{'status':name,'cash':ledger.snapshot(),'at':time.time(),**extra})
 def run(script,args,log):
  with log.open('xb') as f:return subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools'/script),*map(str,args)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 def score(kind):
  for attempt in range(2):
   dest=TASK/'scores'/f'{kind}-{attempt}';dest.parent.mkdir(exist_ok=True)
   rc=run('score_organization_demand_v223_2.py',['--index',3,'--kind',kind,'--episode',TASK/'W0','--output',dest],dest.with_suffix('.log'))
   result=read(dest/'receipt.json') or {'status':'technical_unknown','exit_code':rc}
   if (dest/'receipt.json').exists():result['_reference']=reference(dest/'receipt.json')
   if result['status'] in ('official_report','candidate_execution_failed','no_legal_delivery') or result.get('official_result'):return result
  return result
 outcome=None
 try:
  status('repairing_original_proposal');s=NEW+'REPAIR-W0';ledger.reserve_stage(s);slots.append(s)
  run('recover_proposal_budget_v223_2.py',[],TASK/'proposal-repair.log');proposal=read(TASK/'REPAIR-W0/result.json')
  if not proposal or proposal['status']!='candidate_bank_ready':raise RuntimeError('Proposal recovery did not close: '+json.dumps(proposal,ensure_ascii=False))
  bank=TASK/'REPAIR-W0/candidate-bank.json';s=NEW+'W0';limit=ledger.reserve_stage(s);slots.append(s);assert limit==read(bank)['remaining_branch_token_limit']
  status('native_continuation',selected=read(bank)['selected'],remaining_native_tokens=limit)
  run('run_organization_demand_episode_v223_2.py',['--index',3,'--condition','W0','--output',TASK/'W0','--checkpoint',OLD/'PREFIX/checkpoint','--bank',bank,'--ledger',L],TASK/'native-W0.log')
  generation=read(TASK/'W0/result.json')
  if not generation or generation['status']!='closed':raise RuntimeError('Original unused continuation did not close: '+json.dumps(generation,ensure_ascii=False))
  status('scoring');code=score('code');pair=read_episode_candidates(read(TASK/'W0/candidate-lock.json'))
  if code['status'] in ('official_report','candidate_execution_failed') and pair['lock'].get('last_legal_delivery') and read(checked(pair['lock']['terminal_code']))['tree_sha256']==read(checked(pair['lock']['last_legal_delivery']))['tree_sha256']:
   delivery={**code,'kind':'delivery','endpoint_lock':pair['lock']['last_legal_delivery'],'same_tree_score_reference':code['_reference'],'model_calls':0};delivery.pop('_reference',None);p=TASK/'scores/delivery-reused.json';save(p,delivery);delivery['_reference']=reference(p)
  else:delivery=score('delivery')
  known=code['status'] in ('official_report','candidate_execution_failed') and delivery['status'] in ('official_report','candidate_execution_failed','no_legal_delivery')
  costs=read(TASK/'W0/cost-endpoints.json');outcome={'status':'scored' if known else 'scoring_unknown','code_correct':code.get('resolved'),'legal_correct':delivery.get('resolved'),'logical_tokens':costs['logical_total_tokens'],'episode':reference(TASK/'W0/result.json'),'scores':{'code':code.get('_reference'),'delivery':delivery.get('_reference')},'original_identity':'v223.1:task-03:W0','recovery_identity':NEW+'W0','proposal_revision':reference(TASK/'REPAIR-W0/result.json'),'old_generation_error_preserved':reference(OLD/'GEN-W0/result.json')}
  save(TASK/'W0-result.json',outcome)
  if known:save(OUT/'canonical-overlay.json',{'replaces_only':'3:W0','result':reference(TASK/'W0-result.json'),'original_batch_finished':reference(OLD.parent/'finished.json'),'old_records_unchanged':True})
 except BaseException as e:
  outcome={'status':'technical_unknown','type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()};save(OUT/'exception.json',outcome)
 finally:
  with ledger.db() as c:
   for slot in slots:
    if not c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():c.execute('UPDATE block_slots SET status="not_started" WHERE slot=? AND status="pending"',(slot,))
  released=ledger.finish();save(OUT/'finished.json',{'outcome':outcome,'hold_released':released,'cash':ledger.snapshot(),'at':time.time(),'old_calls_replayed':0,'C_N_updates':0});status('finished',outcome=outcome)
if __name__=='__main__':main()
