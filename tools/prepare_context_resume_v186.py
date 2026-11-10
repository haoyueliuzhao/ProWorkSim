"""Freeze exactly the unentered original identities and existing start grants."""
import json,sqlite3
from pathlib import Path
from proworksim.software_context_resume_v186 import scope,STATE,REMAINING,HANDOFF,never_entered,VERSION
from proworksim.software_benchmark_candidates_v054 import reference

def main():
 if not scope.load(reference(HANDOFF))['old_manager_stopped']:raise ValueError('Old owner still active')
 plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
 with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row
  all_jobs=[dict(r) for r in db.execute("SELECT * FROM jobs WHERE status='running'")]
  rows=[row for row in plan['rows'] if never_entered(row,db)]
  called={r[0] for r in db.execute("SELECT DISTINCT job_id FROM requests WHERE job_id LIKE 'v181:%'")}
 if len(rows)!=20 or len(all_jobs)!=4 or len(called)!=40:raise ValueError('The audited40 called/20 unentered boundary changed')
 started={job['job_id'] for job in all_jobs}
 if not started<={row['slot_id'] for row in rows}:raise ValueError('A live grant belongs to an entered task')
 ordered=[row for row in rows if row['slot_id'] in started]+[row for row in rows if row['slot_id'] not in started]
 old=scope.load(reference(scope.ROOT/'runs/software-benchmark-v182/context-continuation-r1/api-coordinator/progress.json'))
 progress=scope.retain(STATE/'old-progress.json',old)
 value={'version':VERSION,'plan':reference(scope.PLAN_FILE),'rows':ordered,'existing_running_grants':all_jobs,
  'called_slots_preserved':sorted(called),'old_progress':progress,'handoff':reference(HANDOFF),
  'resume_order':'four previously admitted starts, then original order of remaining unentered blocks',
  'new_model_attempts_beyond_original60':0,'same_cumulative_cash_CNY':250,'old_results_overwritten':False}
 ref=scope.retain(REMAINING,value);print(json.dumps({'remaining':ref,'rows':len(rows),'prior_grants':len(all_jobs)}))
if __name__=='__main__':main()
