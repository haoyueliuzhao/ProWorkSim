"""Offline final results/mechanism audit. No models, scoring, service or source edits."""
import json,sqlite3,collections,hashlib,statistics,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R/'runs/software-benchmark-v211/mechanism18-r1';OUT=R/'artifacts/software-benchmark-v211/final-report-r1';OUT.mkdir(parents=True,exist_ok=True)
def load(p):return json.loads(Path(p).read_text())
def ref(p):p=Path(p);return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
progress=load(ROOT/'progress.json');reconciliation=load(ROOT/'completion-reconciliation-r1.json')
assert hashlib.sha256((ROOT/'progress.json').read_bytes()).hexdigest()==reconciliation['raw_progress_sha256']
assert all(s['status']=='closed' for s in progress['states'].values())
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
 records=c.execute('select id,slot,status,cost,tokens,body from requests').fetchall()
usage=collections.defaultdict(collections.Counter)
for rid,slot,status,cost,tokens,body in records:
 assert status=='settled';v=json.loads(body);assert tokens==v['total_tokens']
 usage[slot].update({k:v.get(k,0) or 0 for k in ('input_tokens','output_tokens','total_tokens','cache_hit_tokens','cache_miss_tokens')});usage[slot]['cost_nanoyuan']+=cost;usage[slot]['requests']+=1
rows=[]
for i in range(6):
 root=ROOT/f'task-{i:02d}'
 assert load(root/'scores/gold/receipt.json')['resolved']is True and load(root/'scores/empty/receipt.json')['resolved']is False
 for z in ('O0','O1','O2'):
  p=root/z;g=load(p/'result.json');b=load(p/'boundary.json');dy=load(p/'dynamic-final.json');w=load(p/'final-world.json');plan=load(p/'organization-plan.json');model=load(p/'model-ledger/ledger.json')
  assert g['status']=='closed' and b['execution_integrity_failure'] is None
  assert load(p/'actor/cleanup.json')['owned_actor_removed'] is True
  u=usage[g['slot']];assert u['total_tokens']==model['known_actual_tokens']
  scores={kind:load(root/'scores'/z/kind/'receipt.json') for kind in ('code','delivery')}
  assert scores['code']['status']=='official_report' and scores['delivery']['status'] in ('official_report','no_legal_delivery')
  # Verify selected candidate labels against exact immutable candidate tree identity.
  lock=load(load(p/'candidate-lock.json')['path'])
  for kind,key in (('code','terminal_code'),('delivery','last_legal_delivery')):
   if lock[key]:assert load(lock[key]['path'])['tree_sha256']==scores[kind]['candidate_tree_sha256']
   else:assert kind=='delivery' and scores[kind]['status']=='no_legal_delivery'
  leaf={k:v for k,v in dy['work'].items() if not v['children']};all_scopes=[s for x in leaf.values() for s in x['scope']];root_scopes=dy['work']['work_root']['scope']
  formal_scope=set(all_scopes)==set(root_scopes) and len(all_scopes)==len(set(all_scopes));owners=all(v['owner'] in ('member_001','member_002') for v in dy['work'].values())
  expected=plan['candidate']['target']['tasks'];target_signature=sorted((tuple(sorted(t['scope'])),t['owner'],t['reviewer']) for t in expected);actual_signature=sorted((tuple(sorted(v['scope'])),v['owner'],v['reviewer'] or '') for v in leaf.values())
  outcomes=[];errors=collections.Counter();calls=collections.Counter();error_ids=set();by_action=collections.Counter()
  for n,o in enumerate(b['outcomes']):
   dec=o.get('decision',{});tool=dec.get('action');response=o.get('response',{});error=response.get('error')
   if tool:calls[tool]+=1
   if error:
    code=error.get('rejection',{}).get('code') or error.get('code') or error.get('type') or 'unspecified';errors[code]+=1;by_action[tool]+=1
    if dec.get('model_tool_call_id'):error_ids.add(dec['model_tool_call_id'])
    outcomes.append({'position':n,'worker':o.get('worker_id'),'tool':tool,'arguments':dec.get('arguments'),'error':error,'tool_call_id':dec.get('model_tool_call_id')})
  events=w['software_events'];counts=collections.Counter(e['kind'] for e in events)
  # Stage L2 here means recorded code work, not validated semantic contribution.
  work_events=[e for e in events if e['kind']=='organization_v211:work_performed']
  changed_roles=sorted({e['actor_id'] for e in work_events});real_edits=collections.Counter((e['actor_id'],e['task_id']) for e in work_events)
  all_reviews=[e for e in events if e['kind']=='organization_v141:candidate_reviewed']
  task_records=[]
  for tid,v in leaf.items():
   comp=v['completion'];review=None
   if comp:
    same=[e for e in all_reviews if e.get('identity')==comp['identity'] and e.get('actor_id')==v['reviewer']]
    review=same[-1] if same else None
   task_records.append({'task_id':tid,'scope':v['scope'],'owner':v['owner'],'authors':v['authors'],'reviewer':v['reviewer'],'completion':comp,'accepted_completion':bool(review and review['decision']=='accept'),'completion_review':review,'work_events':real_edits[(v['owner'],tid)]})
  associated=collections.Counter();physical_count=0
  for f in (p/'physical-api').glob('*/response.json'):
   response=load(f);uu=load(f.parent/'usage.json');physical_count+=1
   ids={t['id'] for c in response['choices'] for t in c.get('message',{}).get('tool_calls',[]) or []}
   if ids&error_ids:associated.update({k:uu[k] for k in ('input_tokens','output_tokens','total_tokens')});associated['requests']+=1
  assert physical_count==u['requests']
  row={'index':i,'instance_id':g['instance_id'],'condition':z,'slot':g['slot'],'code':scores['code']['resolved'],'delivery':scores['delivery']['resolved'],'delivery_status':scores['delivery']['status'],'usage':dict(u),'generation_wall_seconds':g['finished']-g['started'],'opportunities':b['opportunities'],'budget_exhausted':any(x=='team_budget_exhausted' for x in b['role_stops'].values()),'role_stops':b['role_stops'],'cash_censored':b['cash_censored'],'formal_scope_conserved':formal_scope,'all_work_owned':owners,'target_scope_owner_reviewer_exact':target_signature==actual_signature,'leaf_count':len(leaf),'completed_leaves':sum(v['completion'] is not None for v in leaf.values()),'accepted_completed_leaves':sum(x['accepted_completion'] for x in task_records),'leaf_records':task_records,'actual_code_work_members':changed_roles,'world_event_counts':dict(counts),'tool_calls':dict(calls),'error_counts':dict(errors),'error_by_action':dict(by_action),'errors':outcomes,'whole_requests_associated_with_rejected_tool_not_exclusive_causal_cost':dict(associated),'summary_usage':model.get('per_usage_id',{}),'score_refs':{k:ref(root/'scores'/z/k/'receipt.json') for k in ('code','delivery')},'source':ref(p/'result.json'),'world_path':str(p/'final-world.json')}
  rows.append(row)
  print(i,z,'done',flush=True)
groups=[]
for z in ('O0','O1','O2'):
 rr=[r for r in rows if r['condition']==z];agg=collections.Counter();errs=collections.Counter();calls=collections.Counter();events=collections.Counter();assoc=collections.Counter()
 for r in rr:agg.update(r['usage']);errs.update(r['error_counts']);calls.update(r['tool_calls']);events.update(r['world_event_counts']);assoc.update(r['whole_requests_associated_with_rejected_tool_not_exclusive_causal_cost'])
 groups.append({'condition':z,'n':6,'code_pass':sum(r['code'] for r in rr),'delivery_pass':sum(r['delivery'] for r in rr),'legal_submission_present':sum(r['delivery_status']=='official_report' for r in rr),'average_tokens':agg['total_tokens']/6,'average_input':agg['input_tokens']/6,'average_output':agg['output_tokens']/6,'requests':agg['requests'],'cost_CNY_upper':agg['cost_nanoyuan']/1e9,'budget_exhausted_runs':sum(r['budget_exhausted'] for r in rr),'both_members_code_work_runs':sum(len(r['actual_code_work_members'])==2 for r in rr),'scope_owner_reviewer_target_match':sum(r['target_scope_owner_reviewer_exact'] for r in rr),'leaf_counts':sum(r['leaf_count'] for r in rr),'completed_leaves':sum(r['completed_leaves'] for r in rr),'accepted_completed_leaves':sum(r['accepted_completed_leaves'] for r in rr),'mean_generation_minutes':statistics.mean(r['generation_wall_seconds'] for r in rr)/60,'errors':dict(errs),'tool_calls':dict(calls),'world_events':dict(events),'associated_rejection_requests_not_causal_cost':dict(assoc)})
total=collections.Counter()
for v in usage.values():total.update(v)
summary={'version':'v211-final-report-r1','groups':groups,'total_usage':dict(total),'cost_CNY_upper':total['cost_nanoyuan']/1e9,'remaining_total_CNY':700-total['cost_nanoyuan']/1e9,'same_original_tasks':6,'repos':4,'runs':18,'API_requests':len(records),'all_settled':True,'score_unknown':0,'formal_scope_conserved_runs':sum(r['formal_scope_conserved'] for r in rows),'owner_complete_runs':sum(r['all_work_owned'] for r in rows),'new_API_calls':0,'new_scores':0,'CN_update_performed':False,'coordinator_reconciliation':ref(ROOT/'completion-reconciliation-r1.json')}
save('episodes.json',rows);save('summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
