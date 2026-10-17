"""Read-only final scientific aggregation; no model, world or acceptance replay."""
from pathlib import Path
from collections import Counter
from fractions import Fraction
import hashlib,json,sys
sys.path.insert(0,str(Path.cwd()))
from scripts import software_learning_reporting_v050 as reporting
from scripts.software_organization_reporting_v047 import outcome_values
BASE=Path.cwd(); OUT=BASE/'artifacts/software-learning-v050/final-analysis'
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p);b=p.read_bytes();return {'path':str(p.resolve()),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
old=BASE/'runs/software-learning-v050';r1=BASE/'runs/software-learning-v050-resume-r1';new=BASE/'runs/software-learning-v050-resume-r6-restored'
plan=read(r1/'plan.json');units=reporting.inventory(plan);direction=read(r1/'direction.json');support=read(r1/'support.json');issues=[];rows=[];workers={};rawrows=[]
for unit in units:
 if unit['phase']=='training':root=old if unit['slot_id']=='org50-train-LA-r01' else r1
 elif unit['branch'] in ('S_star','B'):root=r1
 else:
  root=new
  unit['worker']='dev-'+unit['branch']+'-'+str(next(i for i,u in enumerate(plan['inventory']['development_units_shared_by_branches']) if u['unit_id']==unit['unit_id']))
 worker=unit['worker'];folder=root/worker/'actual/episodes'/unit['slot_id'];source=folder/'slot-result.json';raw=read(source)
 assert all(raw[k]==unit[k] for k in ['slot_id','sampling_seed','purpose','first_member'])
 if (str(root),worker) not in workers:
  report=read(root/worker/'actual/report.json');progress=read(root/worker/'actual/progress.json');workers[(str(root),worker)]={'report':report,'progress':progress}
 wk=workers[(str(root),worker)]
 for candidate in wk['report'].get('rows',[])+wk['progress']:
  if candidate['slot_id']==unit['slot_id']:assert all(candidate.get(k)==raw.get(k) for k in ['R_joint','R_token','Q_joint','Q_token','usage','actor_identity','status'])
 metrics=outcome_values(raw);assert raw['status']=='closed' and metrics['R_joint'] is not None
 cost=reporting.previous._cost(raw,status='closed',issues=issues,path=folder)
 measurement=read(folder/'mechanical-measurement.json');feedback=measurement['feedback'];stop=measurement['stop_assessment'];guard=read(folder/'evaluation-guard.json')
 row={**unit,'status':'closed',**metrics,'submitted':raw['submitted'],'complete_delivery':raw['complete_delivery'],
  'administrative_censoring':raw['administrative_censoring'],'cost':cost,'private_checks_passed':raw['private_checks_passed'],'private_checks_total':raw['private_checks_total'],
  'actor_identity':raw['actor_identity'],'episode_start_steps':raw['episode_start_steps'],'learning_binding':raw['learning_binding'],
  'usage_by_member':raw['usage_by_member'],'outcome_scope':raw['outcome_scope'],
  'measurement':{'decision':measurement['decision'],'global_violations':stop.get('global_violations'),'unresolved':stop.get('unresolved'),
   'local_resource_rejections':stop.get('local_resource_rejections'),'feedback_denominators':feedback.get('denominators'),'page_denominators':feedback.get('page_denominators'),
   'context_blocked_feedback_ids':stop.get('context_blocked_feedback_ids')},
  'evaluation_guard':{k:guard.get(k) for k in ['learning_unchanged','rng_restored_exactly','software_binding_unchanged','actor_identity_unchanged']},
  'source_phase':root.name,'episode_folder':str(folder),'references':{'slot-result.json':ref(source),'mechanical-measurement.json':ref(folder/'mechanical-measurement.json'),'evaluation-guard.json':ref(folder/'evaluation-guard.json')},
  'started_at':raw['started_at'],'ended_at':raw['ended_at'],'wall_seconds':raw['wall_seconds'],
  'closure_reason':raw['boundary']['closure_reason'],'role_stops':raw['boundary']['role_stops'],
  'actor_updates':raw['actor_updates'],'critic_updates':raw['critic_updates'],'new_backward_calls':raw['new_backward_calls'],
  'process_violation':raw['process_violation'],'member_requested_births':raw['member_lifecycle'].get('member_requested_births'),
 }
 rows.append(row);rawrows.append(raw)
assert len(rows)==56 and not issues
metrics=reporting.aggregate_rows(units,rows,direction)
def aggregate(panel):
 count=Counter('complete_success' if r['R_joint']==1 else 'submitted_incomplete' if r['submitted'] else 'unsubmitted' for r in panel)
 return {'n':len(panel),'outcomes':dict(count),'R_joint_sum':sum(r['R_joint'] for r in panel),'R_joint_mean':sum(r['R_joint'] for r in panel)/len(panel),'Q_joint_mean':sum(r['Q_joint'] for r in panel)/len(panel),
  'Q_joint_mean_exact_from_checks':str(sum((Fraction(r['private_checks_passed'],r['private_checks_total']) if r['submitted'] and not r['process_violation'] else Fraction(0) for r in panel),Fraction(0))/len(panel)),
  'status_counts':dict(Counter(r['status'] for r in panel)),'administrative_censored':sum(r['administrative_censoring'] for r in panel),
  'generation':{k:reporting.previous._sum_complete(panel,k) for k in panel[0]['cost'] if k!='status'},
  'local_resource_rejections':dict(Counter(v['reason'] for r in panel for v in r['measurement']['local_resource_rejections'].values())),
  'measurement_decisions':dict(Counter(r['measurement']['decision'] for r in panel))}
groups={'training':aggregate(rows[:24]),**{b:aggregate([r for r in rows if r['phase']=='development' and r['branch']==b]) for b in reporting.BRANCHES}}
groups['all']=aggregate(rows)
root_groups={k:{root:aggregate([r for r in rows if (r['phase']=='training' if k=='training' else r['phase']=='development' and r['branch']==k) and r['root']==root]) for root in (['LA','LB'] if k=='training' else ['DA','DB','DC','DD'])} for k in ['training',*reporting.BRANCHES]}
blocks={root+'/'+member:{k:block.get(k) for k in ['M','n_positive','v','n_by_class','b','actual_repeats','base_training_trajectory_count','admitted_decision_count','composition_degrees_of_freedom','eligible_slots','base_actor_mask','actual_advantage_counts']} for root,s in support['roots'].items() for member,block in s['blocks'].items()}
fbkeys=['all_saved_feedback_units','protocol_feedback_saved_exactly','with_later_actual_generation','presented_in_later_actual_generation','presented_in_first_actual_followup','without_later_actual_generation']
feedback_summary={k:sum(r['measurement']['feedback_denominators'][k] for r in rows) for k in fbkeys}
feedback_summary['no_followup_reasons']=dict(sum((Counter(r['measurement']['feedback_denominators']['no_followup_reasons']) for r in rows),Counter()))
feedback_summary['by_tool']={}
for r in rows:
 for t,d in r['measurement']['feedback_denominators']['by_tool'].items():
  dest=feedback_summary['by_tool'].setdefault(t,{'feedback_units':0,'presented_in_actual_generation':0,'no_followup_reasons':{}})
  for k in ['feedback_units','presented_in_actual_generation']:dest[k]+=d[k]
  dest['no_followup_reasons']=dict(Counter(dest['no_followup_reasons'])+Counter(d['no_followup_reasons']))
pagekeys=['reports_saved','reports_storage_verified','reports_with_directory_presented','reports_with_any_page_presented','reports_historically_fully_presented','verified_page_feedback_returns','actual_page_read_requests']
page_summary={k:sum(r['measurement']['page_denominators'][k] for r in rows) for k in pagekeys}
updates={}
for branch,root in [('B',r1),('Q_plus',BASE/'runs/software-learning-v050-resume-r4'),('Q_minus',BASE/'runs/software-learning-v050-resume-r5')]:
 folder=root/('update-'+branch)/'actual';report=read(folder/'report.json');loaded=read(folder/'loaded-state.json');binding=read(folder/'update-v050-learning-binding.json');token=read(folder/'update-token-evidence.json')
 updates[branch]={'reference':ref(folder/'report.json'),'report':report,'loaded_state':loaded,'binding':binding,'token_evidence':{k:token[k] for k in ['admitted_decisions','admitted_input_tokens','admitted_own_output_tokens','global_member_denominator_factor','old_material_reused','normalization']},'training_compute':read(folder/'training-compute.json')}
artifact={'version':'v050-final-scientific-results-v1','read_only':True,'new_model_calls':0,'new_backward_calls':0,'new_world_or_acceptance_executions':0,
 'provenance':'Original first training slot once + 23 r1 collectors + 8 S_star/8 B from r1 + 8 Q_plus/8 Q_minus from r6-restored. Exact original aggregator reused. No old partial Q runs counted as scientific units.',
 'row_normalization':'Same outcome_values and _cost as original _slot; frozen identity and original slot/progress/worker values checked. Large native training-entry files intentionally not parsed here; support comes from saved completed support report.',
 'units':units,'rows':rows,'metrics':metrics,'groups':groups,'root_groups':root_groups,'support_blocks':blocks,'selected_direction':direction['direction']['selected'],'support_gate':read(r1/'support-gate.json'),
 'updates':updates,'feedback':feedback_summary,'pages':page_summary,'generation_workers':[{'run_root':rr,'worker':w,'status':d['report']['status'],'started_at':d['report']['started_at'],'ended_at':d['report']['ended_at'],'report':ref(Path(rr)/w/'actual/report.json')} for (rr,w),d in workers.items()],
 'sources':{f:ref(r1/f) for f in ['plan.json','direction.json','support.json','support-gate.json','pretraining-admission.json']},'evidence_issues':issues,
 'limitations':['One training window; four manually authored development roots and two paired seeds each; no independent confirmation or population inference.','The selected positive direction raises local_lineage_delivery and lowers evidenced_peer_product_delivery only within LA/member_001; this is not a general collaboration intervention.','Formal failure with partial credit is distinct from unknown. All56 joint/token outcomes and generation cost are known here.']}
(OUT/'scientific-results.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'groups':groups,'root_groups':root_groups,'contrasts':metrics['contrasts'],'finite_difference':metrics['finite_difference'],'feedback':{k:v for k,v in feedback_summary.items() if k!='by_tool'},'pages':page_summary},ensure_ascii=False,indent=2))
