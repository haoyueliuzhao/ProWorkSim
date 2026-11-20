"""Eight public-only pilot tasks, fixed before any new API outcomes."""
import json,hashlib
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/software-benchmark-v222/protocol-r1'
SPECS=[
 ('paired','django__django-13516','interface_output_validation',['self.stdout/stderr','during migrate command']),
 ('paired','sympy__sympy-13615','mixed_symbolic_numeric_relations',['mixture of Symbols and numbers','Complement(a,b)']),
 ('paired','astropy__astropy-14369','parser_table_unit_integration',['composite units','same as in the input MRT file']),
 ('paired','scikit-learn__scikit-learn-25102','transformer_dtype_dependencies',['categorical dtype','sequentially use ColumnTransformer'])]
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
 rows.append({'index':i,'phase':phase,'instance_id':iid,'repo':v['repo'],'base_commit':v['base_commit'],'public_problem':problem,'public_problem_sha256':hashlib.sha256(problem.encode()).hexdigest(),'requirements':anchors,'coverage_type':scene,'configuration':reference(p),'actor_image_id':c['public_test_entry']['source_identity']['actor_image_id'],'scorer_image_id':c['scorer_request_base']['image']['image_id'],'historically_exposed':True,'selection':{'method':'Public review of first three SHA256(v222-four-pairs:instance) per repository; exclude v217/v218 panels; no scores or solution patches used','seed':'v222-four-pairs','public_scenario_is_hypothesis':True},'seed':int(hashlib.sha256(('v222:'+iid).encode()).hexdigest()[:8],16)})
plan={'version':'v222-four-pair-LG-r1','main_states':4,'max_main_continuations':8,'prefix_limit':2_000_000,'prefix_checkpoint_opportunities':24,'prefix_checkpoint_actual_tokens':1_200_000,'generator_limit':200_000,'task_token_limit':5_000_000,'rows':rows,'no_backups':True,'skip_without_structural_alternative':False,'selection_rule':'first compiler-valid structural candidate in model order; otherwise KEEP; no outcome search','shared_cash_cap':1100,'remaining_at_start':410.29992528,'worst_batch_CNY':320,'new_budget':0,'full_study_never_unseen':False,'model':'deepseek-flash','thinking':False,'input_bound':98304,'output_bound':32768,'main_conditions':['L','G'],'C_N_updates':0,'BV_runs':0}

OUT.mkdir(parents=True,exist_ok=True);(OUT/'candidate-tasks.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
print([(r['index'],r['instance_id']) for r in rows])
