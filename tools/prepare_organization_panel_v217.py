"""Public-only fixed panel, no scores/patches read and no external calls."""
import json,hashlib
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/software-benchmark-v217/protocol-r1'
# Public review after a deterministic hash shortlist; no historical outcomes used.
SPECS=[
('dev1','django__django-11740','shared_interface',['Change uuid field to FK','create dependency for App2']),
('dev1','sympy__sympy-11618','keep_plausible',['distance calculation wrong','sqrt(5)']),
('dev1','pytest-dev__pytest-10051','verification',['caplog.get_records','nor does it get new records']),
('dev2','django__django-12663','shared_interface',['SimpleLazyObject','nested subquery']),
('dev2','sympy__sympy-16450','independent_scope',['finiteness assumption','integer, rational, prime, even, odd']),
('dev2','pytest-dev__pytest-10081','independent_scope',['class level','function level']),
('confirm','astropy__astropy-13579','shared_interface',['world_to_pixel','SlicedLowLevelWCS']),
('confirm','astropy__astropy-14598','verification',["double single-quote",'FITS Card']),
('confirm','matplotlib__matplotlib-26113','independent_scope',['mincnt','C parameter']),
('confirm','matplotlib__matplotlib-24570','keep_plausible',['HPacker','top']),
('confirm','scikit-learn__scikit-learn-9288','verification',['n_jobs=1','n_jobs > 1']),
('confirm','scikit-learn__scikit-learn-11578','shared_interface',['LogisticRegressionCV','predict_proba']),
('confirm','sphinx-doc__sphinx-10449','independent_scope',['autoclass','return type']),
('confirm','sphinx-doc__sphinx-8595','keep_plausible',['__all__','No entries should be shown']),
('dev_backup','django__django-12965','shared_interface',['delete()','subquery']),
('dev_backup','pytest-dev__pytest-10356','independent_scope',['MRO','markers']),
('confirm_backup','astropy__astropy-7606','keep_plausible',['UnrecognizedUnit','Should be False']),
('confirm_backup','sphinx-doc__sphinx-8621','independent_scope',['standalone keystrokes','compound keystrokes']),
('dev1','django__django-15916','shared_interface',['ModelForm','formfield_callback']),
('dev2','django__django-13417','shared_interface',['QuerySet.ordered','GROUP BY']),
('dev1','sympy__sympy-19637','keep_plausible',['kernS','UnboundLocalError']),
('dev2','sympy__sympy-19954','verification',['sylow_subgroup','IndexError']),
('dev1','pytest-dev__pytest-5787','independent_scope',['chained exceptions','test_chained_exception_with_from']),
('dev2','pytest-dev__pytest-5840','independent_scope',['conftest','lower case']),
('confirm','astropy__astropy-13236','shared_interface',['structured column','NdarrayMixin']),
('confirm','astropy__astropy-14309','verification',['identify_format','IndexError']),
('confirm','matplotlib__matplotlib-23299','keep_plausible',['get_backend()','rc_context']),
('confirm','matplotlib__matplotlib-25960','independent_scope',['wspace','hspace']),
('confirm','scikit-learn__scikit-learn-25931','keep_plausible',['IsolationForest','feature names']),
('confirm','scikit-learn__scikit-learn-25747','verification',['FeatureUnion','pandas']),
('confirm','sphinx-doc__sphinx-9602','shared_interface',['Literal','py:class']),
('confirm','sphinx-doc__sphinx-9591','independent_scope',['Cross-references','type annotations']),
]
pool={}
for p in sorted((R/'runs/software-benchmark-v064/full-verified-r1/configs').glob('*.json')):
 c=json.loads(p.read_text());pool.setdefault(c['instance_id'],(p,c))
rows=[]
for i,(phase,iid,scene,quotes) in enumerate(SPECS):
 p,c=pool[iid];public=c['public_task'];problem=public['problem_statement'];anchors=[]
 for k,q in enumerate(quotes):
  start=problem.index(q);anchors.append({'id':'scope_'+str(k+1),'exact_public_quote':q,'start_character':start,'end_character':start+len(q)})
 rows.append({'index':i,'phase':phase,'instance_id':iid,'repo':public['repo'],'base_commit':public['base_commit'],'public_problem':problem,'public_problem_sha256':hashlib.sha256(problem.encode()).hexdigest(),'requirements':anchors,'coverage_type':scene,'configuration':reference(p),'actor_image_id':c['public_test_entry']['source_identity']['actor_image_id'],'scorer_image_id':c['scorer_request_base']['image']['image_id'],'historically_exposed':True,'selection':{'seed':'v217-panel-20261119','method':'public issue review of deterministic hash shortlists; exclude three old regression tasks and earlier same-week CN confirmation django14155','no_solution_or_scores_read':True,'scenario_is_hypothesis_not_gain_label':True},'seed':int(hashlib.sha256(('v217:'+iid).encode()).hexdigest()[:8],16)})
assert len({r['instance_id'] for r in rows})==32
assert not {r['repo'] for r in rows if r['phase'].startswith('dev')}&{r['repo'] for r in rows if r['phase'].startswith('confirm')}
plan={'version':'v217-public-panel-r1','main_states':28,'max_reserves':4,'max_main_continuations':84,'prefix_limit':2_000_000,'generator_limit':200_000,'task_token_limit':5_000_000,'rows':rows,'backups':'fixed phase queue; only environment/prefix qualification, never successor score; no substitution to repair one-candidate panel','budget_CNY_remaining_at_start':786.29290232,'full_study_never_unseen':False}
OUT.mkdir(parents=True,exist_ok=True);(OUT/'candidate-tasks.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
print([(r['index'],r['phase'],r['instance_id'],r['coverage_type']) for r in rows])
