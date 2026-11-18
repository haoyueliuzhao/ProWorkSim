"""Six public-issue mechanism candidates, frozen without gold/score lookup."""
import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'artifacts/software-benchmark-v211/mechanism-plan-r1';O.mkdir(parents=True,exist_ok=True)
def load(p):return json.loads(Path(p).read_text())
def ref(p):p=Path(p);return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
# Public demand anchors; these are not a prescribed patch or hidden-test file list.
selection=[
 ('sympy__sympy-19346','parallel_public_behaviors',[('dict','`dict`'),('set','`set`'),('existing_containers','`list` and `tuple`')]),
 ('sympy__sympy-13031','parallel_counterparts',[('hstack','hstack'),('vstack','vstack')]),
 ('matplotlib__matplotlib-25775','cross_package_dependency',[('text_api','getters/setters on Text objects'),('annotations','Annotations'),('drawing','drawing stage')]),
 ('scikit-learn__scikit-learn-14629','cross_interface_dependency',[('class_metadata','estimators_[i].classes_'),('prediction','Array with prediction probabilities.')]),
 ('astropy__astropy-14995','verification_and_responsibility',[('one_mask','When one of the operand does not have mask'),('both_masks','mask * mask'),('neither_mask','no mask * no mask')]),
 ('scikit-learn__scikit-learn-14983','stable_organization_negative',[('kfold','RepeatedKFold'),('stratified','RepeatedStratifiedKFold')]),
]
public=R/'artifacts/software-benchmark-v054/source/public-tasks.json';tasks={r['instance_id']:r for r in load(public)};want={s[0] for s in selection};configs={}
for row in load(R/'runs/software-benchmark-v064/full-verified-r1/config-index.json')['rows']:
 if row['slot_index']%12:continue
 c=load(row['configuration']['path'])
 if c['instance_id'] in want:configs[c['instance_id']]=(row,c)
assert set(configs)==want
rows=[]
for i,(name,kind,anchors) in enumerate(selection):
 row,c=configs[name];t=tasks[name];mapping=load(c['scorer_request_base']['baseline_mapping']['path']);req=[]
 for key,text in anchors:
  start=t['problem_statement'].index(text);req.append({'id':key,'exact_public_quote':text,'start_character':start,'end_character':start+len(text)})
 rows.append({'index':i,'instance_id':name,'repo':t['repo'],'base_commit':t['base_commit'],'public_problem':t['problem_statement'],'public_problem_sha256':hashlib.sha256(t['problem_statement'].encode()).hexdigest(),'coverage_type':kind,'requirements':req,'configuration':row['configuration'],'actor_image_id':mapping['actor_image_id'],'scorer_image_id':c['scorer_request_base']['image']['image_id'],'candidate_role':'public-structure mechanism screening, not new repository-level benchmark','semantic_review':{'reviewer':'Codex public issue review','multiple_public_behaviors':True,'at_least_two_organizational_arrangements_proposed':True,'actual_L2_differences_not_assumed':True,'caveat':'Work-package semantics and exact source access need live environment checks; title-only vstack coverage is weaker evidence than explicit hstack reproduction.' if name.endswith('13031') else 'Alternative decomposition is a mechanism hypothesis, not a gold-derived necessity.'},'environment_status':'frozen historical mapping exists; fresh SDK/container gate pending','hidden_solution_read_for_selection':False})
assert len({r['repo'] for r in rows})>=3
plan={'version':'v211-six-real-task-candidates-r1','source':ref(public),'rows':rows,'tasks':6,'repositories':len({r['repo'] for r in rows}),'runs_target':18,'conditions':['O0_original','O1_generated','O2_generated'],'shared_team_token_limit':5000000,'model':'deepseek-flash','thinking':False,'generator_status':'not_yet_frozen_for_paid_dispatch','API_started':False,'cash_total_CNY':700,'mechanism_stage_planning_CNY':220,'later_stage_planning_CNY':480,'old_balance_transferred':False,'same_task_original_acceptance':True,'historical_exposure':True,'mechanism_results_not_selector_training':True,'supersedes_54_state_design':True}
(O/'candidate-tasks.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n');print([(r['instance_id'],r['coverage_type']) for r in rows])
