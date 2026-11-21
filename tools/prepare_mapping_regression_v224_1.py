"""Freeze the original four tasks as independent repair-validation attempts."""
import json,sqlite3
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v224-1/protocol-r1';E=R/'runs/software-benchmark-v224-1/environment-r1'
def main():
 P.mkdir(parents=True,exist_ok=False);old=R/'artifacts/software-benchmark-v224/protocol-r1/candidate-tasks.json';plan=json.loads(old.read_text())
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  paid=c.execute('SELECT sum(cost)/1e9 FROM requests WHERE status="settled"').fetchone()[0]
  assert not c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone()
  assert not c.execute('SELECT 1 FROM requests WHERE slot LIKE "v224_1:%"').fetchone()
 plan.update(version='v224.1-independent-repair-validation-four-r1',original_plan=reference(old),independent_new_attempts=True,original_results_preserved=True,same_tasks_seeds_images=True,selection_method='same four preselected v224 tasks and order; no score-based substitution',remaining_at_start=1100-paid,new_cash_budget=0,stage_admission_available_CNY=1000-paid,second_window_requires_effective_update=True,not_an_independent_confirmation_set=True,paid_attempts_authorization='2026-11-21 user: 按照审计方案继续推进实验',maximum_physical_token_bound=60_000_000)
 (P/'candidate-tasks.json').write_bytes(json_bytes(plan));proofs=[]
 for row in plan['rows']:
  checked(row['configuration']);oldq=R/f'runs/software-benchmark-v224/environment-r1/task-{row["index"]:02d}/qualification.json';q=json.loads(oldq.read_text());assert q['qualified'] and q['instance_id']==row['instance_id']
  for ref in q['proof'].values():checked(ref)
  q.update(reused_exact_task_configuration=row['configuration'],original_qualification=reference(oldq),new_controls_run=0,actor_runtime_unchanged=True,scorer_semantics_unchanged=True)
  target=E/f'task-{row["index"]:02d}/qualification.json';target.parent.mkdir(parents=True,exist_ok=False);target.write_bytes(json_bytes(q));proofs.append(reference(target))
 (P/'environment-reuse.json').write_bytes(json_bytes({'qualified':4,'new_controls':0,'qualification_references':proofs,'why':'same task/base/image/public runner and official score logic; new output namespaces only'}));print(json.dumps({'tasks':len(plan['rows']),'remaining_CNY':1100-paid,'new_budget':0,'new_environment_controls':0}))
if __name__=='__main__':main()
