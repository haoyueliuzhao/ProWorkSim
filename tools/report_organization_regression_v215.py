"""Read-only final v213 report, v212 comparator and separate v214 engineering evidence."""
from pathlib import Path
import collections,json,sqlite3,statistics,resource
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];root=R/'runs/software-benchmark-v213/regression6-r1';out=R/'artifacts/software-benchmark-v215/final-report-r1';out.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
def load(p):return json.loads(p.read_text())
def save(name,x):(out/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
usage=collections.defaultdict(collections.Counter);models=collections.Counter();fingerprints=collections.Counter()
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
 records=c.execute("SELECT slot,status,cost,tokens,body FROM requests WHERE slot LIKE 'v213:%'").fetchall()
 for slot,status,cost,tokens,body in records:
  assert status=='settled';v=json.loads(body);assert tokens==v['total_tokens']
  usage[slot].update({k:v.get(k,0) or 0 for k in ('input_tokens','output_tokens','total_tokens','cache_hit_tokens','cache_miss_tokens')});usage[slot].update(cost_nanoyuan=cost,requests=1);models[v.get('provider_model')]+=1;fingerprints[v.get('system_fingerprint')]+=1
 # Explicit report scope, not all future users of the still-open shared cash ledger.
 prior=c.execute("SELECT sum(cost) FROM requests WHERE status='settled' AND (slot LIKE 'v211:%' OR slot LIKE 'v212:%')").fetchone()[0]
rows=[]
for task in sorted(root.glob('task-*')):
 for z in ('SINGLE','COMBO'):
  p=task/z;g=load(p/'result.json');b=load(p/'boundary.json');d=load(p/'dynamic-final.json');progress=load(p/'progress.json');u=usage[g['slot']]
  assert g['status']=='closed' and u['total_tokens']==progress['usage']['known_actual_tokens']
  scores={k:load(task/'scores'/z/k/'receipt.json') for k in ('code','delivery')}
  assert scores['code']['status']=='official_report' and scores['delivery']['status'] in ('official_report','no_legal_delivery')
  assert not scores['code']['cleanup_errors'] and not scores['delivery']['cleanup_errors'] and not (p/'cleanup-error.json').exists()
  calls=collections.Counter();errors=[];steps=[]
  for o in b['outcomes']:
   dec=o.get('decision',{});tool=dec.get('action');response=o.get('response',{});calls[tool or 'no_tool']+=1
   if tool in ('open_patch_review','run_patch_review_tests','org_review_patch','complete_work','complete_evidence','adopt_evidence','review_evidence','integrate_patch','submit_integration','offer_joint_arrangement','accept_joint_arrangement'):
    steps.append({'actor':o.get('worker_id'),'tool':tool,'ok':response.get('ok'),'arguments':dec.get('arguments'),'result':response.get('result'),'error':response.get('error')})
   if response.get('error'):errors.append({'actor':o.get('worker_id'),'tool':tool,'error':response['error'],'arguments':dec.get('arguments')})
  w=load(p/'final-world.json');events=w['software_events'];sw=w['projects']['SOFTWARE27']['software'];counts=collections.Counter(e['kind'] for e in events)
  reviews=[e for e in events if e['kind']=='organization_v141:candidate_reviewed'];tests=[e for e in events if e['kind']=='test']
  repeated=collections.Counter((e['actor_id'],e['files_sha256'],e['entry_metadata_sha256'],json.dumps(e.get('public_test_selection'),sort_keys=True)) for e in tests)
  compact_events=[]
  for e in events:
   if e['kind'] in ('organization_v213:work_performed','organization_v213:joint_offered','organization_v213:joint_accepted','organization_v213:evidence_completed','organization_v213:evidence_reviewed','organization_v213:published_review_opened','organization_v213:published_review_tested','organization_v141:candidate_reviewed','submit','integrate','edit'):
    compact_events.append({k:e[k] for k in ('sequence','kind','actor_id','task_id','patch_id','evidence_id','decision','passed','test_sequence','test_evidence','adoption_kind','main_workspace_adopted','source_reference','paths','operation') if k in e})
  conflicts=sum('<<<<<<< working-copy' in line for line in (task/'scores'/z/'code/prediction.patch').read_text().splitlines())
  row={'instance_id':g['instance_id'],'condition':z,'slot':g['slot'],'code_pass':scores['code']['resolved'],'formal_submission_present':bool(sw['deliveries']),'legal_delivery_pass':scores['delivery']['resolved'],'usage':dict(u),'generation_minutes':(g['finished']-g['started'])/60,'preparation_seconds':g['API_admitted_at']-g['started'],'budget_boundary':any('budget_exhausted' in x for x in b['role_stops'].values()),'cash_censored':b['cash_censored'],'role_stops':b['role_stops'],'per_member':progress['usage']['per_member'],'per_usage_id':progress['usage']['per_usage_id'],'tools':dict(calls),'errors':errors,'steps':steps,'packages':d['delivery_gaps']['packages'],'package_chain_ready':d['delivery_gaps']['package_chain_ready'],'world_event_counts':dict(counts),'review_records':reviews,'compact_events':compact_events,'tests_count':len(tests),'repeat_same_actor_content_and_selection':sum(n-1 for n in repeated.values()),'conflict_markers_in_final_prediction':conflicts,'midwork_proposal':load(p/'midwork-proposal.json') if (p/'midwork-proposal.json').exists() else None,'first_submission':None,'refs':{k:reference(p/k) for k in ('result.json','boundary.json','dynamic-final.json','final-world.json','candidate-lock.json')},'score_refs':{k:reference(task/'scores'/z/k/'receipt.json') for k in scores}}
  if (p/'first-submission-usage.json').exists():
   f=load(p/'first-submission-usage.json');fu=f['usage'];first_cost=sum(x.get('normalized_usage',{}).get('peak_cost_nanoyuan',0) for x in fu['calls'])
   assert sum(x.get('normalized_usage',{}).get('total_tokens',0) for x in fu['calls'])==fu['known_actual_tokens']
   row['first_submission']={'tokens':fu['known_actual_tokens'],'cost_CNY_upper':first_cost/1e9,'post_submission_tokens':u['total_tokens']-fu['known_actual_tokens'],'post_submission_cost_CNY_upper':(u['cost_nanoyuan']-first_cost)/1e9,'post_submission_wall_seconds':g['finished']-f['at'],'post_submission_per_member_tokens':{m:v['known_actual_tokens']-fu['per_member'][m]['known_actual_tokens'] for m,v in progress['usage']['per_member'].items()},'formal_delivery_count':len(sw['deliveries']),'first_matches_last_legal_identity':all(f['delivery'].get(k)==sw['deliveries'][-1].get(k) for k in ('files_sha256','entry_metadata_sha256','source_reference')),'ref':reference(p/'first-submission-usage.json')}
  rows.append(row);print('analyzed',task.name,z,flush=True);del w,events,sw
summary=[]
for z in ('SINGLE','COMBO'):
 rr=[r for r in rows if r['condition']==z];tot=collections.Counter()
 for r in rr:tot.update(r['usage'])
 summary.append({'condition':z,'n':len(rr),'code_pass':sum(r['code_pass'] for r in rr),'formal_submission_present':sum(r['formal_submission_present'] for r in rr),'legal_delivery_pass':sum(r['legal_delivery_pass'] for r in rr),'average_tokens':tot['total_tokens']/len(rr),'average_input':tot['input_tokens']/len(rr),'average_output':tot['output_tokens']/len(rr),'totals':dict(tot),'input_fraction':tot['input_tokens']/tot['total_tokens'],'cache_hit_fraction_of_input':tot['cache_hit_tokens']/tot['input_tokens'],'cost_CNY_upper':tot['cost_nanoyuan']/1e9,'budget_boundary_runs':sum(r['budget_boundary'] for r in rr),'average_generation_minutes':statistics.mean(r['generation_minutes'] for r in rr),'review_view_open_attempts':sum(r['tools'].get('open_patch_review',0) for r in rr),'review_view_test_attempts':sum(r['tools'].get('run_patch_review_tests',0) for r in rr),'explicit_accept_records':sum(sum(e['decision']=='accept' for e in r['review_records']) for r in rr)})
total=collections.Counter()
for r in rows:total.update(r['usage'])
final={'version':'v215-report-of-v213-r1','groups':summary,'total_usage':dict(total),'new_stage_CNY_upper':total['cost_nanoyuan']/1e9,'shared_700_CNY_through_v213':(prior+total['cost_nanoyuan'])/1e9,'remaining_CNY_through_v213':700-(prior+total['cost_nanoyuan'])/1e9,'all_requests_settled':True,'technical_unknown':0,'provider_models':dict(models),'provider_fingerprints':dict(fingerprints),'gate':load(root/'stage-b-gate.json'),'v212_comparator':reference('artifacts/software-benchmark-v213/v212-blockers-r1/evidence.json'),'v214_engineering_only':reference('artifacts/software-benchmark-v214/performance-admission-r1/admission.json'),'new_model_calls':0,'new_official_scores':0,'source_results_modified':False}
save('episodes.json',rows);save('summary.json',final);print(json.dumps(summary,ensure_ascii=False),flush=True)
