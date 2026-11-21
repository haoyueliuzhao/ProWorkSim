"""Four public-description development tasks, frozen before new model outcomes."""
import json,hashlib
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];P=R/'artifacts/software-benchmark-v224/protocol-r1'
SPECS=[('dev1','matplotlib__matplotlib-24026',['stackplot should not change Axes cycler','`CN` alias','`ax.plot()`','`matplotlib.patches.Rectangle()`'],'color_alias_and_shared_cycle'),('dev1','pytest-dev__pytest-7432',['--runxfail','skipif','pytest -rs','item itself'],'skip_xfail_reporting'),('dev2','pydata__xarray-3095',['Dataset.copy(deep=True)','DataArray.copy','copy.copy()','copy.deepcopy()'],'copy_protocol_and_coordinate_dtype'),('dev2','sphinx-doc__sphinx-9229',['ScaffoldOpts','FileContents','FileOp','rendered HTML'],'multiple_type_alias_rendering')]
def main():
 P.mkdir(parents=True,exist_ok=False);pool={};old=set()
 for v in ('v216','v217','v218','v222','v223'):
  p=R/f'artifacts/software-benchmark-{v}/protocol-r1/candidate-tasks.json'
  if p.exists():old.update(r['instance_id'] for r in json.loads(p.read_text())['rows'])
 for p in sorted((R/'runs/software-benchmark-v064/full-verified-r1/configs').glob('*.json')):
  d=json.loads(p.read_text());pool.setdefault(d['instance_id'],(p,d))
 shortlist={repo:sorted([i for i,(_,d) in pool.items() if i not in old and d['public_task']['repo']==repo],key=lambda i:hashlib.sha256(('v224-dev4:'+i).encode()).hexdigest())[:6] for repo in ('matplotlib/matplotlib','pytest-dev/pytest','pydata/xarray','sphinx-doc/sphinx')}
 rows=[]
 for i,(phase,iid,quotes,scene) in enumerate(SPECS):
  assert iid not in old;p,d=pool[iid];v=d['public_task'];assert iid in shortlist[v['repo']];text=v['problem_statement'];anchors=[]
  for n,q in enumerate(quotes):
   start=text.index(q);anchors.append({'id':'scope_'+str(n+1),'exact_public_quote':q,'start_character':start,'end_character':start+len(q),'annotation_not_additional_requirement':True})
  rows.append({'index':i,'phase':phase,'instance_id':iid,'repo':v['repo'],'base_commit':v['base_commit'],'public_problem':text,'public_problem_sha256':hashlib.sha256(text.encode()).hexdigest(),'requirements':anchors,'coverage_type':scene,'configuration':reference(p),'actor_image_id':d['public_test_entry']['source_identity']['actor_image_id'],'scorer_image_id':d['scorer_request_base']['image']['image_id'],'historically_exposed':True,'seed':int(hashlib.sha256(('v224:'+iid).encode()).hexdigest()[:8],16)})
 plan={'version':'v224-two-window-mapping-CN-development-r1','rows':rows,'main_states':4,'maximum_main_branches':12,'prefix_limit':2_000_000,'graph_limit':80_000,'generator_limit':200_000,'task_token_limit':5_000_000,'shared_cash_cap':1100,'stage_cumulative_cash_ceiling':1000,'confirmation_cash_preserved':100,'remaining_at_start':286.79602368,'new_cash_budget':0,'no_backups':True,'historical_scores_used_to_choose_tasks':False,'selection_method':'assistant public-text review within first six SHA256(v224-dev4:instance) per repository; prefer interacting public behaviors; not an unbiased or never-seen benchmark','public_shortlists':shortlist,'conditions':['KEEP','C1','C2'],'model':'deepseek-flash','thinking':False,'input_bound':98304,'output_bound':32768,'no_forced_alternatives':True,'C_N_updates_maximum':2,'v225_automatically_started':False}
 (P/'candidate-tasks.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n');print([(r['index'],r['instance_id']) for r in rows])
if __name__=='__main__':main()
