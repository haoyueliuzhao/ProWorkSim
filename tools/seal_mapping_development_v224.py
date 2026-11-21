"""Seal four new development tasks after minimal CPU and environment admission."""
import json,time,sqlite3,py_compile
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_mapping_selector_v224 import SPEC
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v224/protocol-r1';A=R/'artifacts/software-benchmark-v224/preparation-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_bytes(json_bytes(v))
def main():
 assert not (P/'deployment-freeze.json').exists(),'Never overwrite a deployment freeze'
 assert '7 passed' in (A/'cpu-controls.txt').read_text()
 replay=read(A/'gate-replay.json');assert replay['passed'] and replay['API_calls']==0
 for row in replay['rows']:
  checked(row['source']);checked(row['decision']);assert row['actual']['eligible']==row['expected_eligible']
 proofs={'CPU':reference(A/'cpu-controls.txt'),'gate_replay':reference(A/'gate-replay.json')}
 for label,path in [('SDK_prefix',R/'runs/software-benchmark-v223-1/sdk-control-r1/PREFIX/summary.json'),('SDK_continuation',R/'runs/software-benchmark-v223-1/sdk-control-r2/CONTINUATION/summary.json')]:
  d=read(path);assert d['passed'] and d['model_provider_calls']==0;proofs[label]=reference(path)
 env=[]
 for row in read(P/'candidate-tasks.json')['rows']:
  checked(row['configuration']);qpath=R/f'runs/software-benchmark-v224/environment-r1/task-{row["index"]:02d}/qualification.json';q=read(qpath);assert q['qualified'];receipts={}
  for kind,ref in q['proof'].items():
   receipt=read(checked(ref));assert receipt['resolved']==(kind=='gold') and not receipt.get('cleanup_errors');receipts[kind]=ref
  env.append({'index':row['index'],'qualification':reference(qpath),'receipts':receipts})
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  assert c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()==('1100000000000',)
  assert not c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone()
  assert not c.execute('SELECT 1 FROM requests WHERE slot LIKE "v224:%"').fetchone()
 save(P/'selector-spec.json',SPEC);save(A/'environment-controls.json',env)
 paths=set()
 for ref in read(R/'artifacts/software-benchmark-v223-2/protocol-r1/deployment-freeze.json')['files']:checked(ref);paths.add(Path(ref['path']))
 for pattern in ('src/proworksim/*v224.py','tools/*v224.py','tests/*v224.py'):
  for path in R.glob(pattern):py_compile.compile(str(path),doraise=True);paths.add(path)
 paths.update((P/'candidate-tasks.json',P/'selector-spec.json',R/'docs/experiments/software-benchmark-v224-mapping-development-protocol.md'))
 save(P/'deployment-freeze.json',{'version':'v224-two-window-mapping-CN-r1','files':[reference(p) for p in sorted(paths)],'at':time.time()})
 save(P/'admission.json',{'passed':True,'proofs':proofs,'environment':reference(A/'environment-controls.json'),'unchanged_runtime_and_SDK_reused':True,'new_model_calls_at_seal':0,'planned_states':4,'maximum_main_continuations':12,'maximum_updates':2,'new_cash_budget':0,'confirmation_reserved_CNY':100,'source_files':len(paths),'v225_started':False,'at':time.time()})
 print(json.dumps({'passed':True,'source_files':len(paths),'environment_qualified':len(env),'new_API_calls':0}))
if __name__=='__main__':main()
