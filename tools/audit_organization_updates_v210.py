"""Independently reconstruct old updates from bound real outcomes; zero API."""
import json,hashlib,math
from pathlib import Path
from proworksim.software_organization_design_v210 import ARMS,reconstruct_update,coupling,distances
R=Path(__file__).resolve().parents[1];O=R/'artifacts/software-benchmark-v210/offline-audit-r1';O.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(Path(p).read_text())
def checked(ref):
 p=Path(ref['path']);raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Source changed: '+str(p))
 return json.loads(raw)
q={z:1/3 for z in ARMS};ref=dict(q);used=set();results=[]
plan_paths=[R/'artifacts/software-benchmark-v205/window1-r1/plan.json',R/'artifacts/software-benchmark-v207/window2-r1/plan.json']
for window,folder in [(1,'software-benchmark-v205/window1-main-r1'),(2,'software-benchmark-v207/window2-main-r1')]:
 f=R/'runs'/folder/'feedback.json';e=read(f);plan=read(plan_paths[window-1]);assert e['window']==window
 assert {b['state_id'] for b in e['blocks']}=={b['state_id'] for b in plan['blocks']}
 rows=[]
 for b in e['blocks']:
  assert b['stage']=='development' and b['state_id'] not in used;used.add(b['state_id']);v={};repo=None
  for arm,x in b['results'].items():
   g=checked(x['generation_receipt']);score=checked(x['official_score_receipt']);u=checked(x['usage_receipt'])
   assert g['status']=='closed' and g['arm']==arm and g['instance_id']==b['state_id'].split(':')[0] and score['status']=='official_report'
   assert u['execution_integrity_failure'] is None and score['resolved']==x['official_code_pass']
   assert u['team_budget']['model']['charged_tokens']==x['full_team_tokens']
   # Independently bind whether a legal candidate existed and its exact scored tree.
   lock_ref=read(Path(x['generation_receipt']['path']).parent/'candidate-lock.json')
   # Stored lock wrapper is a reference to the immutable candidate metadata.
   lock=checked(lock_ref) if 'path' in lock_ref else lock_ref
   delivery=lock.get('last_legal_delivery');assert bool(delivery)==x['legal_delivery']
   endpoint=checked(delivery if delivery else lock['terminal_code'])
   assert endpoint['tree_sha256']==score['candidate_tree_sha256']
   v[arm]={'y':bool(delivery and score['resolved']),'tokens':x['full_team_tokens']}
   repo=g['instance_id'].rsplit('-',1)[0]
  rows.append({'state_id':b['state_id'],'stage':'development','repo':repo,'results':v})
 a=reconstruct_update(q,ref,rows);old=read(R/f'runs/software-benchmark-v204/policies/q{window}.json')
 comparisons={k:a[k]==old[k] for k in ('contribution','novelty','q_after')};assert all(comparisons.values())
 assert sum(a['q_after'].values())==1 and min(a['q_after'].values())>=.05
 results.append({'window':window,'exact_float_matches':comparisons,'rows':rows,'recalculated':a,'original':str(R/f'runs/software-benchmark-v204/policies/q{window}.json')});q=a['q_after']
c=coupling(ref,q);c['same_three_probability']=(1-c['common_inverse_cdf_disagreement'])**3
out={'independent_implementation':True,'old_update_module_imported':False,'raw_scores_usage_and_registered_states_verified':True,'confirmation_or_old_contaminated_results_used':False,'windows':results,'coupling_correction':c,'historical_q_unchanged':True,'model_calls':0}
(O/'update-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'exact':[r['exact_float_matches'] for r in results],'coupling':c},indent=2))
