"""Reproducible read-only v216 preparation and v216.1/.2 continuation report.

No model, scorer, Docker or service actions. Logical counterfactual cost is
separate from each physically billed request. Old generations stay unchanged.
"""
import collections,json,sqlite3,statistics,resource
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];O=R/'artifacts/software-benchmark-v216/final-report-r1';O.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
def read(p):return json.loads(p.read_text())
def save(n,v):(O/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
usage=collections.defaultdict(collections.Counter);models=collections.Counter();fps=collections.Counter()
keys=('input_tokens','output_tokens','total_tokens','cache_hit_tokens','cache_miss_tokens')
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
 for slot,status,cost,tokens,body in c.execute("SELECT slot,status,cost,tokens,body FROM requests WHERE slot LIKE 'v216:%'"):
  assert status=='settled';v=json.loads(body);assert tokens==v['total_tokens']
  usage[slot].update({k:v.get(k,0) or 0 for k in keys});usage[slot].update(cost_nanoyuan=cost,requests=1);models[v['provider_model']]+=1;fps[v.get('system_fingerprint')]+=1
 prior=c.execute("SELECT COALESCE(sum(cost),0) FROM requests WHERE status='settled' AND (slot LIKE 'v211:%' OR slot LIKE 'v212:%' OR slot LIKE 'v213:%')").fetchone()[0]
rows=[]
for revision,dirname in [('v216.1','target-repair6-r1'),('v216.2','targeted-closure4-r1')]:
 root=R/'runs/software-benchmark-v216'/dirname
 for task in sorted(root.glob('*-task-*')):
  for condition in ('KEEP','ADAPT'):
   ep=task/condition;g=read(ep/'result.json');b=read(ep/'boundary.json');d=read(ep/'dynamic-final.json');p=read(ep/'progress.json');cost=read(ep/'cost-endpoints.json');assert g['status']=='closed'
   scores={k:read(task/'scores'/condition/k/'receipt.json') for k in ('code','delivery')}
   assert scores['code']['status']=='official_report' and scores['delivery']['status'] in ('official_report','no_legal_delivery')
   native=collections.Counter()
   for v in p['usage']['calls']:
    u=v['normalized_usage'];native.update({k:u.get(k,0) or 0 for k in keys})
   assert native['total_tokens']==p['usage']['known_actual_tokens']
   gen=collections.Counter(usage[f"v216:r2-task-{g['index']:02d}:GENERATOR"])
   if g['index']==0:gen.update(usage['v216:task-00:GENERATOR'])
   assert gen['total_tokens']==g['generator_tokens']
   logical=collections.Counter({k:native[k]+gen[k] for k in keys});physical=usage[g['slot']]
   assert logical['total_tokens']==p['logical_total_tokens']
   assert physical['total_tokens']+g['prefix_tokens']+g['generator_tokens']==logical['total_tokens']
   calls=collections.Counter();errors=[];actions=[]
   for o in b['outcomes']:
    dec=o.get('decision',{});tool=dec.get('action');resp=o.get('response',{});calls[tool or o.get('status')]+=1
    result=resp.get('result') or {};result_keys=('source_reference','passed','executed','report_id','patch_id','review_id','evidence_id','test_sequence','paths','conflicts','conflict_count','event_sequence','task_id','decision','identity','requirements','source_patch_id','owner','previous_owner','mode','episode_state')
    item={'actor':o.get('worker_id'),'tool':tool,'arguments':dec.get('arguments'),'ok':resp.get('ok'),'result':{k:result[k] for k in result_keys if k in result},'error':resp.get('error'),'full_result_in_boundary_ref':True}
    if resp.get('error'):errors.append(item)
    if tool in ('offer_joint_arrangement','accept_joint_arrangement','complete_work','complete_evidence','org_review_patch','review_evidence','integrate_patch','fix_patch','run_tests','run_patch_review_tests','submit_integration'):actions.append(item)
   final_obs={}
   for capture in (ep/'runtime/public-capture').glob('*.jsonl'):
    for line in capture.open():
     x=json.loads(line)
     if x['kind']=='public_observation':final_obs[capture.stem]=x['payload']
   cleanup=[str(x.relative_to(R)) for x in ep.glob('*cleanup*error*')]
   score_cleanup={k:v.get('cleanup_errors',[]) for k,v in scores.items()}
   failedtests={}
   for f in (task/'scores'/condition/'code').glob('logs/run_evaluation/*/*/*/report.json'):
    official=read(f)[g['instance_id']];failedtests={k:v['failure'] for k,v in official['tests_status'].items() if v['failure']}
   rows.append({'revision':revision,'instance_id':g['instance_id'],'index':g['index'],'condition':condition,'slot':g['slot'],'code_pass':scores['code']['resolved'],'legal_delivery_pass':scores['delivery']['resolved'],'terminal':p['lifecycle']['terminal'],'logical_usage':dict(logical),'physical_usage':dict(physical),'prefix_tokens':g['prefix_tokens'],'generator_tokens':g['generator_tokens'],'generation_minutes':(g['finished']-g['started'])/60,'preparation_seconds':g['API_admitted_at']-g['started'],'timing':p['timing'],'budget_boundary':any('budget_exhausted' in s for s in b['role_stops'].values()),'cash_censored':b['cash_censored'],'role_stops':b['role_stops'],'per_usage_id':p['usage']['per_usage_id'],'tools':dict(calls),'errors':errors,'key_actions':actions,'packages':d['delivery_gaps']['packages'],'package_chain_ready':d['delivery_gaps']['package_chain_ready'],'final_observed_readiness':{m:o.get('delivery_readiness') for m,o in final_obs.items()},'physical_requests_after_delivered':cost['physical_requests_after_delivered'],'first_submission_logical_tokens':cost['first_submission']['logical_tokens'] if cost['first_submission'] else None,'failed_official_tests':failedtests,'cleanup_errors':cleanup,'score_cleanup_errors':score_cleanup,'refs':{k:reference(ep/k) for k in ('result.json','boundary.json','dynamic-final.json','progress.json','cost-endpoints.json','candidate-lock.json')},'score_refs':{k:reference(task/'scores'/condition/k/'receipt.json') for k in scores}})
   print(revision,g['instance_id'],condition,logical['total_tokens'],physical['total_tokens'],flush=True)
groups=[]
for rev in ('v216.1','v216.2'):
 for z in ('KEEP','ADAPT'):
  rr=[x for x in rows if x['revision']==rev and x['condition']==z];log=collections.Counter();phy=collections.Counter()
  for r in rr:log.update(r['logical_usage']);phy.update(r['physical_usage'])
  groups.append({'revision':rev,'condition':z,'n':len(rr),'code_pass':sum(r['code_pass'] for r in rr),'legal_delivery_pass':sum(r['legal_delivery_pass'] for r in rr),'average_logical_tokens':log['total_tokens']/len(rr),'average_logical_input':log['input_tokens']/len(rr),'average_logical_output':log['output_tokens']/len(rr),'average_new_continuation_tokens':phy['total_tokens']/len(rr),'physical_usage':dict(phy),'new_cost_CNY_upper':phy['cost_nanoyuan']/1e9,'budget_boundary_runs':sum(r['budget_boundary'] for r in rr),'average_generation_minutes':statistics.mean(r['generation_minutes'] for r in rr),'logical_input_fraction':log['input_tokens']/log['total_tokens']})
physical_groups=collections.defaultdict(collections.Counter)
for slot,u in usage.items():
 phase='initial_preparation' if slot.startswith('v216:task-') else ('v216.2_continuations' if slot.startswith('v216:r3-') else ('v216.1_preparation' if slot.endswith((':PREFIX',':GENERATOR')) else 'v216.1_continuations'))
 physical_groups[phase].update(u)
total=collections.Counter()
for v in physical_groups.values():total.update(v)
summary={'version':'v216-final-report-r1','groups':groups,'physical_stage_totals':{k:dict(v) for k,v in physical_groups.items()},'total_physical_usage':dict(total),'total_this_round_CNY_upper':total['cost_nanoyuan']/1e9,'shared700_through_v216_CNY_upper':(prior+total['cost_nanoyuan'])/1e9,'shared700_remaining_CNY':700-(prior+total['cost_nanoyuan'])/1e9,'models':dict(models),'fingerprints':dict(fps),'gate':read(R/'runs/software-benchmark-v216/targeted-closure4-r1/stage-b-gate.json'),'initial_gate':read(R/'runs/software-benchmark-v216/target-repair6-r1/stage-b-gate.json'),'score_unknowns':0,'new_model_calls_in_reporting':0,'new_scoring_in_reporting':0,'protocols_not_pooled':True}
save('episodes.json',rows);save('summary.json',summary);print(json.dumps(summary['groups'],ensure_ascii=False,indent=2))
