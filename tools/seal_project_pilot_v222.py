"""Freeze zero-API admission evidence and exact deployment closure for v222."""
import json,time,shutil
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v222/protocol-r1';A=R/'artifacts/software-benchmark-v222/preparation-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
assert not (P/'deployment-freeze.json').exists(),'Never overwrite a frozen deployment'
plan=read(P/'candidate-tasks.json');assert len(plan['rows'])==4 and len({r['repo'] for r in plan['rows']})==4
controls=[]
for row in plan['rows']:
 for kind in ('gold','empty'):
  p=R/f'runs/software-benchmark-v222/environment-r1/task-{row["index"]:02d}/{kind}/receipt.json';d=read(p)
  assert d['status']=='official_report' and d['resolved']==(kind=='gold') and d['cleanup_errors']==[];controls.append(reference(p))
sdk={}
for cond in ('PREFIX','L','G'):
 p=R/f'runs/software-benchmark-v222/sdk-control-r1/{cond}/summary.json';d=read(p);assert d['passed'] and d['model_provider_calls']==0;sdk[cond]=reference(p)
assert '5 passed' in (A/'cpu-controls.txt').read_text()
shutil.copyfile('/tmp/v222-cpu.txt',A/'initial-cpu-controls.txt')
audit=Path('/home/zhuxinrui/.codex/attachments/54df4ecb-dd54-44cc-83a8-a83e1c52b063/已粘贴的文本.txt');shutil.copyfile(audit,P/'user-audit.txt')
paths=set()
for manifest in (R/'artifacts/software-benchmark-v219/protocol-r1/deployment-freeze.json',R/'artifacts/software-benchmark-v221/research-and-admission-r1/source-freeze.json'):
 paths.update(Path(r['path']) for r in read(manifest)['files'])
for pattern in ('src/proworksim/*v222.py','tools/*v222.py','tests/*v222.py'):
 paths.update(R.glob(pattern))
paths.update((P/'candidate-tasks.json',P/'user-audit.txt',R/'docs/experiments/software-benchmark-v222-project-graph-paired-protocol.md'))
# No old scored outcome enters the model context; these are executable source hashes.
freeze={'version':'v222-four-pairs-LG-deployment-r1','files':[reference(p) for p in sorted(paths)],'at':time.time()};save(P/'deployment-freeze.json',freeze)
save(P/'admission.json',{'passed':True,'scope':'engineering_and_environment_admission_only','Gate_A_real_trajectory_review':'pending','Gate_B_decision_increment':'pending','Gate_C_CN':'not_authorized','cpu_controls':reference(A/'cpu-controls.txt'),'initial_cpu_controls':reference(A/'initial-cpu-controls.txt'),'SDK':sdk,'environment_controls':controls,'provider_calls_at_seal':0,'max_main_branches':8,'frozen_files':len(paths),'no_shared_host_changes':True,'at':time.time()})
print(json.dumps({'sealed_files':len(paths),'paired_tasks':4,'main_branches':8,'engineering_passed':True}))
