"""Seal paid natural-work validation, reusing exact-source CPU/SDK evidence."""
import json,time,sqlite3,py_compile
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_mapping_selector_v224 import SPEC
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v224-2/protocol-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_bytes(json_bytes(v))
def main():
 assert not (P/'deployment-freeze.json').exists()
 review=R/'artifacts/software-benchmark-v224-2/preparation-r1/implementation-review.json';audit=read(review);assert audit['passed']
 for ref in audit['files']:checked(ref)
 cpu=checked(audit['CPU']);assert '9 passed' in cpu.read_text()
 for ref in audit['SDK'].values():
  d=read(checked(ref));assert d['passed'] and d['model_provider_calls']==0
 cont=read(checked(audit['SDK']['CONTINUATION']));assert cont['legal_deliveries']==1 and cont['actual_cpu_pytest_calls']==4
 plan=read(P/'candidate-tasks.json');assert plan['rows']==read(checked(plan['original_plan']))['rows'];assert plan['continue_planned_tasks_without_update']
 env=read(P/'environment-reuse.json');assert env['qualified']==4 and env['new_controls']==0
 for ref in env['qualification_references']:
  q=read(checked(ref));assert q['qualified']
  for kind,proof in q['proof'].items():
   receipt=read(checked(proof));assert receipt['resolved']==(kind=='gold') and not receipt['cleanup_errors']
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  assert c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()==('1100000000000',)
  assert not c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone()
  assert not c.execute('SELECT 1 FROM block_slots WHERE status="pending"').fetchone()
  assert not c.execute('SELECT 1 FROM requests WHERE slot LIKE "v224_2:%"').fetchone()
 save(P/'selector-spec.json',SPEC);paths=set()
 for ref in read(R/'artifacts/software-benchmark-v224-1/protocol-r1/deployment-freeze.json')['files']:checked(ref);paths.add(Path(ref['path']))
 for pattern in ('src/proworksim/*v224_2.py','tools/*v224_2.py','tests/*v224_2.py'):
  for p in R.glob(pattern):py_compile.compile(str(p),doraise=True);paths.add(p)
 paths.update((P/'candidate-tasks.json',P/'selector-spec.json',P/'environment-reuse.json',R/'docs/experiments/software-benchmark-v224-2-natural-validation-protocol.md',R/'docs/experiments/software-benchmark-v224-2-natural-coordination-revision.md'))
 save(P/'deployment-freeze.json',{'version':'v224.2-natural-coordination-validation','files':[reference(p) for p in sorted(paths)],'at':time.time()})
 save(P/'admission.json',{'passed':True,'proofs':reference(review),'environment':reference(P/'environment-reuse.json'),'paid_calls_at_seal':0,'independent_attempts':True,'maximum_prefixes':4,'maximum_continuations':12,'new_budget':0,'cumulative_limit_CNY':1100,'new_admission_ceiling_CNY':1000,'continue_planned_tasks_without_update':True,'v225_started':False,'at':time.time()})
 print(json.dumps({'passed':True,'source_files':len(paths),'paid_calls':0,'tasks':4}))
if __name__=='__main__':main()
