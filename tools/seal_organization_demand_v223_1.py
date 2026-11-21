"""Freeze targeted regression after CPU, real SDK and public actor admission."""
import json,time,shutil,sqlite3
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v223-1/protocol-r1';A=R/'artifacts/software-benchmark-v223-1/preparation-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def main():
 assert not (P/'deployment-freeze.json').exists(),'Never overwrite a frozen running source'
 assert '7 passed' in (A/'cpu-controls.txt').read_text()
 proofs={}
 for name,path in [('sdk_prefix',R/'runs/software-benchmark-v223-1/sdk-control-r1/PREFIX/summary.json'),('sdk_continuation',R/'runs/software-benchmark-v223-1/sdk-control-r2/CONTINUATION/summary.json'),('public_actor',R/'runs/software-benchmark-v223-1/public-label-control-r1/summary.json'),('navigation',A/'navigation-replay.json'),('feedback',A/'feedback-replay.json')]:
  d=read(path);assert d['passed'];proofs[name]=reference(path)
  if name.startswith('sdk'):assert d['model_provider_calls']==0
  if name=='public_actor':assert d['model_calls']==0 and d['cleanup']['owned_actor_removed'] and not d['cleanup']['transport_errors']
  if path.parent!=A:shutil.copyfile(path,A/(name+'-summary.json'))
 rows=read(P/'candidate-tasks.json')['rows'];assert len(rows)==4
 for row in rows:
  q=read(R/f'runs/software-benchmark-v223-1/environment-r1/task-{row["index"]:02d}/qualification.json');assert q['qualified']
  for ref in q['proof'].values():checked(ref)
 source=R/'artifacts/software-benchmark-v223/protocol-r1/deployment-freeze.json';paths=set()
 for ref in read(source)['files']:checked(ref);paths.add(Path(ref['path']))
 for pattern in ('src/proworksim/*v223_1.py','tools/*v223_1.py','tests/*v223_1.py'):paths.update(R.glob(pattern))
 paths.update((P/'candidate-tasks.json',R/'docs/experiments/software-benchmark-v223-1-targeted-repair-pilot.md'))
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  assert c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()==('1100000000000',)
  assert not c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone()
  assert not c.execute('SELECT 1 FROM requests WHERE slot LIKE "v223.1:%"').fetchone()
 freeze={'version':'v223.1-targeted-interface-regression-r1','files':[reference(p) for p in sorted(paths)],'at':time.time()};save(P/'deployment-freeze.json',freeze)
 save(P/'admission.json',{'passed':True,'source_files':len(paths),'proofs':proofs,'official_controls':'exact reused v223 immutable task/image/score controls','batch_model_calls_at_seal':0,'original_results_unchanged':True,'independent_new_attempts':True,'runtime_scope':'four original tasks, at most eight W0/W1 continuations; no C/N learning','at':time.time()});print(json.dumps({'passed':True,'files':len(paths),'new_API_calls':0}))
if __name__=='__main__':main()
