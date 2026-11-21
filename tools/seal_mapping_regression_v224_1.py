"""Admit independent repair validation; no paid work before this source freeze."""
import json,time,sqlite3,py_compile
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_mapping_selector_v224 import SPEC
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v224-1/protocol-r1';A=R/'artifacts/software-benchmark-v224-1/preparation-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_bytes(json_bytes(v))
def main():
 assert not (P/'deployment-freeze.json').exists();A.mkdir(exist_ok=False)
 review=R/'artifacts/software-benchmark-v224-1/review-r1/implementation-review.json'
 for ref in read(review)['files']:checked(ref)
 cpu=R/'artifacts/software-benchmark-v224-1/review-r1/cpu-controls.txt';assert '8 passed' in cpu.read_text();proofs={'CPU':reference(cpu),'unchanged_repaired_source':reference(review)}
 for s in ('single','split','peer'):
  path=R/f'runs/software-benchmark-v224-1/sdk-control-r2/{s}/summary.json';d=read(path);assert d['passed'] and d['model_provider_calls']==0 and d['containers']==0 and d['boundary_preserved_checkpoint'];proofs[s]=reference(path);save(A/(s+'-SDK.json'),d)
  assert d['status']==('sampling_space_exhausted' if s=='single' else 'decision_checkpoint_ready')
 old_sdk=R/'runs/software-benchmark-v223-1/sdk-control-r2/CONTINUATION/summary.json';assert read(old_sdk)['passed'];proofs['unchanged_continuation']=reference(old_sdk)
 plan=read(P/'candidate-tasks.json');old=read(checked(plan['original_plan']));assert plan['rows']==old['rows']
 env=read(P/'environment-reuse.json');assert env['qualified']==4 and env['new_controls']==0
 for ref in env['qualification_references']:
  q=read(checked(ref));assert q['qualified']
  for kind,proof in q['proof'].items():
   receipt=read(checked(proof));assert receipt['resolved']==(kind=='gold') and not receipt['cleanup_errors']
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  assert c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()==('1100000000000',)
  assert not c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone()
  assert not c.execute('SELECT 1 FROM requests WHERE slot LIKE "v224_1:%"').fetchone()
 save(P/'selector-spec.json',SPEC);paths=set()
 for ref in read(R/'artifacts/software-benchmark-v224/protocol-r1/deployment-freeze.json')['files']:checked(ref);paths.add(Path(ref['path']))
 for pattern in ('src/proworksim/*v224_1.py','tools/*v224_1.py','tests/*v224_1.py'):
  for p in R.glob(pattern):py_compile.compile(str(p),doraise=True);paths.add(p)
 paths.update((P/'candidate-tasks.json',P/'selector-spec.json',P/'environment-reuse.json',R/'docs/experiments/software-benchmark-v224-1-repair-validation-protocol.md',R/'docs/experiments/software-benchmark-v224-1-sampling-review-and-repair.md'))
 save(P/'deployment-freeze.json',{'version':'v224.1-independent-repair-validation','files':[reference(p) for p in sorted(paths)],'at':time.time()})
 save(P/'admission.json',{'passed':True,'proofs':proofs,'environment':reference(P/'environment-reuse.json'),'paid_calls_at_seal':0,'independent_attempts':True,'maximum_prefixes':4,'maximum_continuations':12,'new_budget':0,'cumulative_limit_CNY':1100,'new_admission_ceiling_CNY':1000,'second_window_requires_effective_update':True,'v225_started':False,'at':time.time()})
 print(json.dumps({'passed':True,'source_files':len(paths),'model_calls':0,'same_tasks':4}))
if __name__=='__main__':main()
