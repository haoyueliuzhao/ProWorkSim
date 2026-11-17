"""Prepare the original held-out prefixes only after actual q2; no outcome updates."""
import json,os,time,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];base=R/'runs/software-benchmark-v204';current=R/'runs/software-benchmark-v207/window2-main-r1';target=R/'runs/software-benchmark-v207/confirmation-prefixes-r1';status=R/'runs/software-benchmark-v207/confirmation-continuation.json'
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_benchmark_candidates_v054 import reference
while True:
 q=base/'policies/q2.json'
 if q.exists():
  try:policy=json.loads(q.read_text())
  except json.JSONDecodeError:time.sleep(20);continue
  if policy.get('round')!=2:raise ValueError('Wrong policy round')
  break
 progress=current/'progress.json'
 if progress.exists():
  try:p=json.loads(progress.read_text())
  except json.JSONDecodeError:p={}
  if p.get('status') in ('cash_block_admission_stopped','systemic_fault_paused','window_incomplete_no_update','feedback_unknown_no_update','update_rejected'):
   atomic_write(status,json_bytes({'status':'blocked_by_window2','reason':p['status'],'no_new_model_calls':True}));raise SystemExit(0)
 atomic_write(status,json_bytes({'status':'waiting_for_actual_q2','at':time.time()}));time.sleep(20)
if (base/'cn-pilot-r1/batch-pause.json').exists():raise RuntimeError('Systemic fault pause')
atomic_write(status,json_bytes({'status':'preparing_original_confirmation_prefixes','frozen_q2':reference(q),'indices':[7,8,9,10]}))
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD')}
with (target.parent/'confirmation-prefixes-r1.log').open('xb') as log:
 p=subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools/run_organization_prefix_stage_v207.py'),'--window','3','--output',str(target)],cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT)
atomic_write(status,json_bytes({'status':'confirmation_states_await_review' if p.returncode==0 else 'confirmation_preparation_error','exit':p.returncode,'prefix_root':str(target),'frozen_q2':reference(q),'no_confirmation_outcome_used_for_update':True}))
