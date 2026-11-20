"""Four public-only pilot tasks, fixed before any new API outcomes."""
import json,hashlib
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/software-benchmark-v223/protocol-r1'
SPECS=[
 ('paired','django__django-14792','timezone_query_interface',['TimezoneMixin','resulting query']),
 ('paired','sympy__sympy-23950','boolean_set_interface',['Contains.as_set','Piecewise']),
 ('paired','astropy__astropy-14182','table_output_headers',['header_rows','ascii.rst']),
 ('paired','scikit-learn__scikit-learn-13496','inherited_estimator_interface',['warm_start','n_estimators'])]
pool={}
for p in sorted((R/'runs/software-benchmark-v064/full-verified-r1/configs').glob('*.json')):
 c=json.loads(p.read_text());pool.setdefault(c['instance_id'],(p,c))
rows=[]
old=set()
for version in ('v217','v218','v222'):
 old.update(r['instance_id'] for r in json.loads((R/f'artifacts/software-benchmark-{version}/protocol-r1/candidate-tasks.json').read_text())['rows'])
for i,(phase,iid,scene,quotes) in enumerate(SPECS):
 assert iid not in old
 p,c=pool[iid];v=c['public_task'];problem=v['problem_statement'];anchors=[]
 for k,q in enumerate(quotes):
  start=problem.index(q);anchors.append({'id':'scope_'+str(k+1),'exact_public_quote':q,'start_character':start,'end_character':start+len(q)})
 rows.append({'index':i,'phase':phase,'instance_id':iid,'repo':v['repo'],'base_commit':v['base_commit'],'public_problem':problem,'public_problem_sha256':hashlib.sha256(problem.encode()).hexdigest(),'requirements':anchors,'coverage_type':scene,'configuration':reference(p),'actor_image_id':c['public_test_entry']['source_identity']['actor_image_id'],'scorer_image_id':c['scorer_request_base']['image']['image_id'],'historically_exposed':True,'selection':{'method':'Public review of first three SHA256(v223-four:instance) per repository; exclude v217/v218/v222 panels; no scores or solution patches used','seed':'v223-four','public_scenario_is_hypothesis':True},'seed':int(hashlib.sha256(('v223:'+iid).encode()).hexdigest()[:8],16)})
plan={'version':'v223-four-pair-W0-W1-r1','main_states':4,'max_main_continuations':8,'prefix_limit':2_000_000,'demand_gate':'actual_code_then_public_test_and_supported_reconsideration','generator_limit':200_000,'graph_limit':80_000,'task_token_limit':5_000_000,'rows':rows,'no_backups':True,'skip_without_structural_alternative':False,'selection_rule':'first compiler-valid structural candidate in model order; otherwise KEEP; no outcome search','shared_cash_cap':1100,'remaining_at_start':349.84986584,'worst_batch_CNY':320,'new_budget':0,'full_study_never_unseen':False,'model':'deepseek-flash','thinking':False,'input_bound':98304,'output_bound':32768,'main_conditions':['W0','W1'],'C_N_updates':0,'BV_runs':0}

OUT.mkdir(parents=True,exist_ok=True);(OUT/'candidate-tasks.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
print([(r['index'],r['instance_id']) for r in rows])
