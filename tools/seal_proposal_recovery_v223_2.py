"""Freeze one non-resampled correction and unused continuation, no paid calls."""
import json,time,sqlite3
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v223-2/protocol-r1';A=R/'artifacts/software-benchmark-v223-2/preparation-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_bytes(json_bytes(v))
def main():
 assert not (P/'deployment-freeze.json').exists();assert '5 passed' in (A/'cpu-controls.txt').read_text()
 plan=read(P/'recovery-plan.json');quote=read(checked(plan['quote']));assert quote['max_tokens']==6216 and quote['dispatch']
 for ref in plan['old_sources'].values():checked(ref)
 for key in ('repair_wire','repair_wire_before_allocation'):checked(plan[key])
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  assert not c.execute('SELECT 1 FROM slots WHERE id="v223.1:task-03:W0"').fetchone()
  assert not c.execute('SELECT 1 FROM requests WHERE slot LIKE "v223.2:%"').fetchone()
 paths=set()
 for ref in read(R/'artifacts/software-benchmark-v223-1/protocol-r1/deployment-freeze.json')['files']:checked(ref);paths.add(Path(ref['path']))
 for pattern in ('src/proworksim/*v223_2.py','tools/*v223_2.py','tests/*v223_2.py'):paths.update(R.glob(pattern))
 paths.update((P/'candidate-tasks.json',P/'recovery-plan.json',P/'allocation.json',R/'docs/experiments/software-benchmark-v223-2-proposal-budget-recovery.md'))
 save(P/'deployment-freeze.json',{'version':'v223.2-budget-recovery-r1','files':[reference(p) for p in sorted(paths)],'at':time.time()})
 save(P/'admission.json',{'passed':True,'CPU':reference(A/'cpu-controls.txt'),'old_runtime_unchanged':True,'old_calls_replayed':0,'new_paid_calls_at_seal':0,'maximum_new_logical_proposal_calls':1,'maximum_new_native_continuations':1,'new_cash_budget':0,'maximum_additional_tokens':plan['maximum_additional_input_output_tokens'],'source_files':len(paths),'at':time.time()})
 print(json.dumps({'passed':True,'source_files':len(paths),'output_cap':6216,'additional_tokens':plan['maximum_additional_input_output_tokens']}))
if __name__=='__main__':main()
