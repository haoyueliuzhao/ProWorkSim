"""Recover retained results and freeze the six never-entered original repeats."""
import json,sqlite3,subprocess,time
from proworksim.software_context_resume_v189 import scope,STATE,REMAINING,HANDOFF,OLD_PROGRESS,VERSION,active_claims,never_entered
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment


def main():
 if HANDOFF.exists() or REMAINING.exists():raise ValueError('Existing recovery preparation must be preserved')
 result=subprocess.run(['systemctl','--user','show','proworksim-v188-context-budget.service','--no-pager',
  '--property=ActiveState,SubState,MainPID'],env=user_manager_environment(),capture_output=True,text=True,timeout=15)
 state=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
 if result.returncode or state.get('MainPID')!='0' or state.get('ActiveState') not in ('inactive','failed'):
  raise ValueError('Previous owner is not stopped')
 if active_claims(scope.dispatch_view()):raise ValueError('Previous owned resources remain active')
 plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
 oldpath=scope.ROOT/'runs/software-benchmark-v188/budget-continuation-r1/api-coordinator/progress.json'
 oldref=reference(oldpath);old=json.loads(oldpath.read_bytes())
 original_progress=scope.retain(STATE/'raw-predecessor-progress.json',old)
 recovery=[];quiet_refs=[]
 with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row
  if db.execute("SELECT count(*) FROM requests WHERE status!='settled'").fetchone()[0]:raise ValueError('Unsettled HTTP requires separate review')
  pending=[r for r in plan['rows'] if never_entered(r,db)]
  if len(pending)!=6 or [r['slot_index'] for r in pending]!=list(range(18154,18160)):raise ValueError('Original remaining identities changed')
  running=[dict(r) for r in db.execute("SELECT * FROM jobs WHERE status='running'")]
  for row in plan['rows']:
   if row in pending:continue
   path=scope.BATCH_ROOT/'episodes'/str(row['slot_index'])/'result.json'
   ref=reference(path);episode=scope.load(ref)
   if episode.get('slot_id')!=row['slot_id'] or episode.get('configuration')!=row['configuration']:
    raise ValueError('Original episode identity mismatch')
   quiet=scope.load(episode['quiescence'])
   if quiet.get('all_owned_objects_removed') is not True or quiet.get('cleanup_errors'):raise ValueError('Cleanup incomplete')
   quiet_refs.append(episode['quiescence'])
   if row['slot_index'] in (18152,18153):
    if episode['status']!='closed' or not episode.get('candidate_lock'):raise ValueError('No trusted closed candidate')
    old['records'][row['slot_id']]={'row':row,'result':ref,'status':'closed'}
    score=scope.GRADING_ROOT/f"score-{row['slot_index']}"/'request.json'
    item={'slot_id':row['slot_id'],'original_result':ref}
    if row['slot_index']==18152:
     completion=scope.load(reference(score.parent/'completion.json'))
     receipt=scope.load(reference(score.parent/'receipt.json'))
     if completion.get('returncode')!=0 or receipt.get('status')!='official_report':raise ValueError('Completed official score missing')
     item['completed_score']=reference(score)
    elif score.exists():raise ValueError('Second original scoring identity unexpectedly entered')
    recovery.append(item)
  if len(running)!=1 or running[0]['job_id']!=recovery[1]['slot_id']:raise ValueError('Unexpected live accounting state')
 if len(old['records'])!=54:raise ValueError('Closed-result count differs from original54 calls')
 old.update(stage='recovered_predecessor_closed',generation_active=0,grading_active=0,
  generation_inflight_or_waiting=0,generation_finished=54,source_progress=original_progress,
  restored_result_slots=[x['slot_id'] for x in recovery],new_model_calls=0)
 recovered=scope.retain(OLD_PROGRESS,old)
 handoff=scope.retain(HANDOFF,{'version':VERSION,'observed_unix':time.time(),'old_manager_stopped':True,
  'old_manager_state':state,'old_resources_removed':True,'unsettled_HTTP':0,
  'original_progress':original_progress,'recovered_progress':recovered,
  'source_error':reference(oldpath.parent/'coordinator-error.json'),
  'completed_slots':list(old['records']),'original_cleanup_records':quiet_refs,
  'old_running_job_to_close_from_retained_result':running[0],
  'generation_replayed':False,'shared_host_changes':0})
 remaining=scope.retain(REMAINING,{'version':VERSION,'plan':reference(scope.PLAN_FILE),'rows':pending,
  'closed_result_recovery':recovery,'handoff':handoff,'new_attempts_outside_original60':0,
  'cash_cap_CNY':300,'budget_additions_CNY':0,'old_results_overwritten':False})
 print(json.dumps({'remaining':remaining,'unentered':6,'retained_results':2,'completed_score_to_collect':1}))


if __name__=='__main__':main()
