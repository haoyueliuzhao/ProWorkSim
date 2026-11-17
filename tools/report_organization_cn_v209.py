"""Read-only v204-v208 final aggregation; no models, scoring or ledger mutation."""
import json,sqlite3,collections,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'artifacts/software-benchmark-v209/final-report-r1';O.mkdir(parents=True,exist_ok=True)
def load(p):return json.loads(Path(p).read_text())
def write(name,v):(O/name).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def reference(p):p=Path(p);return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
ledger=R/'runs/software-benchmark-v204/cn-pilot-r1/ledger.sqlite'
with sqlite3.connect('file:'+str(ledger)+'?mode=ro',uri=True) as c:requests=[dict(zip(('id','slot','status','cost','tokens','body'),r)) for r in c.execute('select id,slot,status,cost,tokens,body from requests')]
assert all(r['status']=='settled' for r in requests)
usage=collections.defaultdict(lambda:collections.Counter())
for r in requests:
 b=json.loads(r['body']);assert b['total_tokens']==r['tokens']
 x=usage[r['slot']];x.update({k:b.get(k,0) or 0 for k in ('input_tokens','output_tokens','total_tokens','cache_hit_tokens','cache_miss_tokens')});x['cost_nanoyuan']+=r['cost'];x['requests']+=1
rows=[]
def episode(path,stage,condition,code,delivery):
 p=Path(path);res=load(p/'result.json');boundary=load(p/'boundary.json');w=load(p/'final-world.json');life=load(p/'policy-lifecycle.json');prog=load(p/'progress.json')
 prefix=Path(res['checkpoint_parent']).parent;pr=load(prefix/'result.json');actual=usage[res['slot']];pref=usage[pr['slot']];logical=actual+pref
 assert logical['total_tokens']==prog['usage']['known_actual_tokens']
 ev=w['software_events'];counts=collections.Counter(e['kind'] for e in ev)
 # Count actual world operations, not requested-but-rejected tool names.
 selected=[e for e in ev if e['kind'] in ('work_message','transfer_offered','transfer_accepted','transfer_declined','task_returned','claim') and e.get('task_id')=='diagnose']
 errors=collections.Counter();error_details=[]
 for o in boundary['outcomes']:
  response=o.get('response',{});error=response.get('error',{})
  if isinstance(error,dict) and error:
   errors[error.get('type','unspecified')]+=1;error_details.append({'worker':o.get('worker_id'),'decision':o.get('decision'),'error':error})
 assert boundary['execution_integrity_failure'] is None
 choice=load(p/'policy-choice.json');text=choice.get('intervention_text');first=min((p/'physical-api').glob('*/request.json'),key=lambda f:f.stat().st_mtime);wire=load(first)['payload']['wire']
 presented=None if not text else any(text in m.get('content','') for m in wire['messages'] if isinstance(m.get('content'),str))
 row={'intervention_in_first_request':presented,'first_request':reference(first),'error_details':error_details,'budget_exhaustion_recorded':any(v=='team_budget_exhausted' for v in boundary['role_stops'].values()),'stage':stage,'condition':condition,'instance_id':res['instance_id'],'slot':res['slot'],'code':bool(code),'delivery':bool(delivery),'logical_usage_including_prefix':dict(logical),'paid_suffix_usage':dict(actual),'prefix_slot':pr['slot'],'elapsed_seconds':res['finished']-res['started'],'closure_reason':boundary['closure_reason'],'role_stops':boundary['role_stops'],'pre_dispatch_boundaries':boundary['pre_dispatch_boundaries'],'cash_censored':boundary['cash_censored'],'lifecycle':life,'world_event_counts':dict(counts),'diagnose_communication_events':selected,'errors':dict(errors),'source':reference(p/'result.json'),'episode_dir':str(p)}
 rows.append(row)
for window,rel in [(1,'software-benchmark-v205/window1-main-r1'),(2,'software-benchmark-v207/window2-main-r1')]:
 for block in load(R/'runs'/rel/'feedback.json')['blocks']:
  for arm,v in block['results'].items():
   episode(Path(v['generation_receipt']['path']).parent,f'development_{window}',arm,v['terminal_code_pass'],v['legal_delivery'] and v['official_code_pass'])
confirm=R/'runs/software-benchmark-v208/confirmation-main-r1'
assert load(confirm/'progress.json')['status']=='confirmation_closed'
for p in sorted(confirm.glob('score-*/summary.json')):
 s=load(p);assert s['qualified']
 for arm,v in s['branches'].items():
  assert v['status']=='scored';episode(Path(v['refs']['generation']['path']).parent,'confirmation',arm,v['code'],v['delivery'])
# Read admission official endpoints rather than hard-code reported outcomes.
for arm in ('keep','assist'):
 scores=R/'runs/software-benchmark-v205/admission-score-r1'
 code=load(scores/(arm+'-code')/'receipt.json');delivery=load(scores/(arm+'-delivery')/'receipt.json')
 assert code['status']==delivery['status']=='official_report'
 episode(R/'runs/software-benchmark-v204/admission-pair-r1'/arm,'admission',arm.upper(),code['resolved'],delivery['resolved'])
assert len(rows)==20
aggregates=[]
for stage in ('development','confirmation','admission'):
 arms=('KEEP','ASSIST','TRANSFER') if stage=='development' else (('q0','q2') if stage=='confirmation' else ('KEEP','ASSIST'))
 for arm in arms:
  rr=[x for x in rows if (x['stage'].startswith('development') if stage=='development' else x['stage']==stage) and x['condition']==arm]
  aggregates.append({'stage':stage,'condition':arm,'n':len(rr),'code_pass':sum(x['code'] for x in rr),'delivery_pass':sum(x['delivery'] for x in rr),'average_tokens':sum(x['logical_usage_including_prefix']['total_tokens'] for x in rr)/len(rr),'average_input':sum(x['logical_usage_including_prefix']['input_tokens'] for x in rr)/len(rr),'average_output':sum(x['logical_usage_including_prefix']['output_tokens'] for x in rr)/len(rr),'paid_suffix_CNY_upper':sum(x['paid_suffix_usage']['cost_nanoyuan'] for x in rr)/1e9,'budget_exhausted_runs':sum(x['budget_exhaustion_recorded'] for x in rr),'policy_started':sum(x['lifecycle']['started'] for x in rr),'policy_finished':sum(x['lifecycle']['finished'] for x in rr)})
by_stage={}
for stage in ('admission','development_1','development_2','confirmation'):
 rr=[x for x in rows if x['stage']==stage];u=collections.Counter()
 for x in rr:u.update(x['paid_suffix_usage'])
 by_stage[stage]=dict(u)
prefix_slots={s:u for s,u in usage.items() if 'prefix-' in s}
assert len(prefix_slots)==11
u=collections.Counter()
for v in prefix_slots.values():u.update(v)
by_stage['all_prefixes']=dict(u)
total=collections.Counter()
for v in usage.values():total.update(v)
assert total['total_tokens']==sum(x['total_tokens'] for x in by_stage.values())
summary={'version':'v209-final-r1','scope':'v204-v208 organization CN pilot','model':'deepseek-flash','thinking':False,'physical_usage':dict(total),'physical_usage_by_stage':by_stage,'prefix_count':len(prefix_slots),'continuations':len(rows),'nominal_cash_line_CNY':200,'cost_CNY_upper':total['cost_nanoyuan']/1e9,'cash_remaining_CNY':200-total['cost_nanoyuan']/1e9,'aggregates':aggregates,'q0':load(R/'artifacts/software-benchmark-v204/protocol-r1/q0.json'),'q1':load(R/'runs/software-benchmark-v204/policies/q1.json'),'q2':load(R/'runs/software-benchmark-v204/policies/q2.json'),'all_requests_settled':True,'same_action_confirmation_pairs':3,'technical_unknown':0,'new_api_or_scoring':0}
write('episodes.json',rows);write('summary.json',summary)
print(json.dumps({'aggregates':aggregates,'physical':dict(total),'by_stage':by_stage,'lifecycle':[(x['stage'],x['instance_id'],x['condition'],x['lifecycle']['started'],x['lifecycle']['finished'],x['closure_reason'],x['errors']) for x in rows]},ensure_ascii=False,indent=2))
