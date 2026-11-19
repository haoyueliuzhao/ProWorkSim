"""Eight public-only pilot tasks, fixed before any new API outcomes."""
import json,hashlib
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/software-benchmark-v218/protocol-r1'
SPECS=[
 ('dev1','django__django-15375','query_aggregation',['annotate()','default']),
 ('dev1','sympy__sympy-16792','codegen_interface',['array arguments','incorrect signature']),
 ('dev2','django__django-11490','query_projection',['values()/values_list()','evaluated multiple times']),
 ('dev2','sympy__sympy-13757','dispatch_consistency',['Poly(x)*x','x*Poly(x)']),
 ('confirm','astropy__astropy-13033','required_column_validation',['additional required columns','required columns are missing']),
 ('confirm','astropy__astropy-14539','array_comparison',['variable-length arrays','Comparing a file to itself']),
 ('confirm','scikit-learn__scikit-learn-26323','transformer_composition',['sub-transformers','remainder']),
 ('confirm','scikit-learn__scikit-learn-14629','prediction_interface',['cross_val_predict','MultiOutputClassifier'])]
pool={}
for p in sorted((R/'runs/software-benchmark-v064/full-verified-r1/configs').glob('*.json')):
 c=json.loads(p.read_text());pool.setdefault(c['instance_id'],(p,c))
rows=[]
old={r['instance_id'] for r in json.loads((R/'artifacts/software-benchmark-v217/protocol-r1/candidate-tasks.json').read_text())['rows']}
for i,(phase,iid,scene,quotes) in enumerate(SPECS):
 assert iid not in old
 p,c=pool[iid];v=c['public_task'];problem=v['problem_statement'];anchors=[]
 for k,q in enumerate(quotes):
  start=problem.index(q);anchors.append({'id':'scope_'+str(k+1),'exact_public_quote':q,'start_character':start,'end_character':start+len(q)})
 rows.append({'index':i,'phase':phase,'instance_id':iid,'repo':v['repo'],'base_commit':v['base_commit'],'public_problem':problem,'public_problem_sha256':hashlib.sha256(problem.encode()).hexdigest(),'requirements':anchors,'coverage_type':scene,'configuration':reference(p),'actor_image_id':c['public_test_entry']['source_identity']['actor_image_id'],'scorer_image_id':c['scorer_request_base']['image']['image_id'],'historically_exposed':True,'selection':{'method':'Public issue review of v218 hash shortlists; excludes v217 panel; no historical scores or solution patches used','seed':'v218-public-panel','public_scenario_is_hypothesis':True},'seed':int(hashlib.sha256(('v218:'+iid).encode()).hexdigest()[:8],16)})
plan={'version':'v218-stage-opportunity-pilot','main_states':8,'max_main_continuations':24,'prefix_limit':2_000_000,'generator_limit':200_000,'task_token_limit':5_000_000,'rows':rows,'no_backups':True,'skip_without_structural_alternative':True,'phase_sizes':{'dev1':2,'dev2':2,'confirm':4},'initial_policy':reference(R/'artifacts/software-benchmark-v217/resilience-r1/policy-2.json'),'shared_cash_cap':1100,'remaining_at_start':492.99954208,'planning_admission_CNY':300,'new_budget':0,'full_study_never_unseen':False}
OUT.mkdir(parents=True,exist_ok=True);(OUT/'candidate-tasks.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
print([(r['index'],r['phase'],r['instance_id']) for r in rows])
