"""Seal v223 engineering admission, without claiming a scientific result."""
import json,time,shutil
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v223/protocol-r1';A=R/'artifacts/software-benchmark-v223/preparation-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
assert not (P/'deployment-freeze.json').exists(),'Never overwrite a frozen deployment'
plan=read(P/'candidate-tasks.json');assert plan['main_conditions']==['W0','W1'] and len(plan['rows'])==4
original=read(A/'environment-original-panel.json')
for a,b in zip(original['rows'],plan['rows']):
 assert {k:v for k,v in a.items() if k!='selection'}=={k:v for k,v in b.items() if k!='selection'}
controls=[]
for row in plan['rows']:
 for kind in ('gold','empty'):
  p=R/f'runs/software-benchmark-v223/environment-r1/task-{row["index"]:02d}/{kind}/receipt.json';d=read(p)
  assert d['status']=='official_report' and d['resolved']==(kind=='gold') and d['cleanup_errors']==[];controls.append(reference(p))
sdk=R/'runs/software-benchmark-v223/sdk-control-r1/summary.json';d=read(sdk);assert d['passed'] and d['model_provider_calls']==0 and d['new_demand_observer_executed'];shutil.copyfile(sdk,A/'sdk-summary.json')
assert '8 passed' in (A/'cpu-controls.txt').read_text()
replay=R/'artifacts/software-benchmark-v223/historical-replay-r1/summary.json';assert read(replay)['passed'] and read(replay)['model_calls']==0
shutil.copyfile('/home/zhuxinrui/.codex/attachments/b8129ac1-0852-48bb-8a0c-e5d911e7d5b9/已粘贴的文本.txt',P/'user-audit.txt')
paths={Path(r['path']) for r in read(R/'artifacts/software-benchmark-v222/protocol-r1/deployment-freeze.json')['files']}
# All new entrypoints and changed deployment dependencies are immutable after seal.
for pattern in ('src/proworksim/*v223.py','tools/*v223.py','tests/*v223.py','src/proworksim/*v222_1.py'):
 paths.update(R.glob(pattern))
paths.update((P/'candidate-tasks.json',P/'user-audit.txt',R/'docs/experiments/software-benchmark-v223-organization-demand-protocol.md'))
freeze={'version':'v223-four-pairs-W0-W1-deployment-r1','files':[reference(p) for p in sorted(paths)],'at':time.time()};save(P/'deployment-freeze.json',freeze)
save(P/'admission.json',{'passed':True,'scope':'engineering_and_environment_admission_only','demand_semantic_accuracy':'unknown_no_independent_gold','Graph_Agent_offline_comparison':'not_run_no_archived_agent_output','Gate_next_stage':'pending_live_v223_review','cpu_controls':reference(A/'cpu-controls.txt'),'SDK':reference(sdk),'historical_replay':reference(replay),'environment_controls':controls,'provider_calls_at_seal':0,'max_main_branches':8,'frozen_files':len(paths),'shared_cash_cap':1100,'worst_new_panel_CNY':320,'new_budget':0,'no_shared_host_changes':True,'at':time.time()})
print(json.dumps({'sealed_files':len(paths),'paired_tasks':4,'main_branches':8,'engineering_passed':True}))
