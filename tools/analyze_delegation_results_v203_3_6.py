"""Read-only final joins: planned slots, unique physical usage, fixed code and delivery."""
import json,sqlite3,collections,pathlib,csv
ROOT=pathlib.Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/software-benchmark-v203-3-6/final-report-r1';OUT.mkdir(parents=True,exist_ok=True)
def load(p):return json.loads(p.read_text())
plan=load(ROOT/'artifacts/software-benchmark-v203-3-3/state-review-r1/plan.json')
prefixroot=ROOT/'runs/software-benchmark-v203-3-3/prefix80-r3'
with sqlite3.connect('file:'+str(prefixroot/'ledger.sqlite')+'?mode=ro',uri=True) as c:
 raw=c.execute('select slot,status,body,cost from requests').fetchall()
usage=collections.defaultdict(lambda:collections.Counter())
for slot,status,body,cost in raw:
 assert status=='settled',status
 u=json.loads(body);usage[slot].update({k:u[k] for k in ('input_tokens','output_tokens','total_tokens','cache_hit_tokens','cache_miss_tokens')});usage[slot]['cost_nanoyuan']+=cost;usage[slot]['requests']+=1
prefix={};prefix_n={}
for i in range(8):
 d=prefixroot/f'prefix-{i:02d}';r=load(d/'result.json');w=load(d/'final-world.json');prefix_n[i]=len(w['software_events']);del w
 prefix[i]={'instance_id':r['instance_id'],**usage[r['slot']]}
records=[]
for row in plan['rows']:
 versions=[v for v in ('v203-3-3','v203-3-4','v203-3-5') if (ROOT/f'runs/software-benchmark-{v}/continuations-r1'/row['run_name']/'result.json').exists()]
 if not versions:records.append({**row,'instance_id':plan['selected'][row['state_rank']]['instance_id'],'status':'not_started'});continue
 assert len(versions)==1
 v=versions[0];d=ROOT/f'runs/software-benchmark-{v}/continuations-r1'/row['run_name'];r=load(d/'result.json');b=load(d/'boundary.json');w=load(d/'final-world.json');facts=next(p['software'] for p in w['projects'].values() if 'software'in p)
 ev=w['software_events'][prefix_n[row['candidate_index']]:]
 kinds=collections.Counter(x['kind'] for x in ev)
 changes=[x for x in ev if any(t in x['kind'] for t in ('transfer','delegate','claim'))]
 tests=[{k:x.get(k) for k in ('sequence','actor_id','source_reference','passed','executed')} for x in ev if x['kind']=='test']
 # Only post-prefix physical responses, never inherited adapter history.
 calls=[]
 for f in (d/'physical-api').glob('*/response.json'):
  body=load(f);req=load(f.parent/'request.json');calls.append({'member':req['payload']['member_id'],'usage_id':req['payload']['usage_id'],
   'tokens':body['usage']['total_tokens'],'tools':[x['function']['name'] for x in body['choices'][0]['message'].get('tool_calls',[])],
   'content':body['choices'][0]['message'].get('content'),'time':req['time']})
 calls.sort(key=lambda x:x['time'])
 requests_by_tool=collections.Counter(t for c in calls for t in c['tools']);rejected=[]
 ids={load(g)['id'] for g in (d/'physical-api').glob('*/response.json')}
 for f in (d/'runtime').rglob('rejected-history-v117/*.json'):
  x=load(f)
  # Restore copies old receipts; new provider IDs are the reliable filter.
  if x['response_id'] in ids:rejected.append({'member':x['worker_id'],'response_id':x['response_id']})
 scores=load(ROOT/f'runs/software-benchmark-{v}/scoring-r1/progress.json')['episodes'][row['run_name']]
 record={**row,'instance_id':r['instance_id'],'deployment':v,'status':r['status'],'usage':dict(usage[r['slot']]),'prefix_usage':prefix[row['candidate_index']],
  'full_policy_tokens':prefix[row['candidate_index']]['total_tokens']+usage[r['slot']]['total_tokens'],
  'code':scores.get('code',{}).get('resolved'),'delivery':scores.get('delivery',{}).get('resolved'),
  'closure_reason':b['closure_reason'],'terminal_details':b.get('terminal_details'),'team_budget':b.get('team_budget'),
  'wall_seconds':r['finished']-r['started'],'event_counts':dict(kinds),'responsibility_events':changes,'public_tests':tests,
  'diagnostic_task_final':facts['tasks'].get('diagnose'),'transfer_offers':facts.get('transfer_offers'),
  'patches':len(facts['patches']),'deliveries':len(facts['deliveries']),'organization_reviews':facts['organization_state'].get('reviews'),
  'physical_tool_request_counts':dict(requests_by_tool),'rejected_response_count':len(rejected),'multi_tool_response_count':sum(len(x['tools'])>1 for x in calls),
  'last_responses':calls[-5:],'purpose_counts':dict(collections.Counter(c['usage_id'] for c in calls)),
  'candidate_lock':r.get('candidate_lock'),'result_source':str(d/'result.json'),'score_source':str(ROOT/f'runs/software-benchmark-{v}/scoring-r1/progress.json')}
 records.append(record);del w,facts,ev
summary={'planned_continuations':16,'normal':sum(r['status']=='closed' for r in records),'unknown':sum(r['status']=='technical_unknown' for r in records),'not_started':sum(r['status']=='not_started' for r in records),
 'total_usage':dict(sum(usage.values(),collections.Counter())),'prefix_usage':dict(sum((collections.Counter(p) for p in [dict(usage['v203.3.3:prefix80-r3:prefix-'+str(i).zfill(2)]) for i in range(8)]),collections.Counter())),
 'records':records,'all_eight_prefixes':prefix,'fee_is_peak_upper_not_invoice':True,'same_task_repeats_not_independent':True}
(OUT/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
for r in records:
 print(r['sequence'],r['arm'],r['status'],r.get('code'),r.get('delivery'),r.get('full_policy_tokens'),r.get('usage',{}).get('total_tokens'),r.get('event_counts'),r.get('rejected_response_count'),r.get('diagnostic_task_final',{}).get('owner'))
print('TOTAL',summary['total_usage'])
