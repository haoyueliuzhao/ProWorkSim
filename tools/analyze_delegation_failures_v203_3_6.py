import json,collections,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1];O=ROOT/'artifacts/software-benchmark-v203-3-6/final-report-r1';a=json.loads((O/'analysis.json').read_text());rows=[]
for r in a['records']:
 if r['status']=='not_started':continue
 d=pathlib.Path(r['result_source']).parent;counts=collections.Counter();messages=collections.Counter();declines=[];first=None
 for line in (d/'runtime/experience.jsonl').open():
  if '"kind": "tool_call"' not in line and '"kind":"tool_call"' not in line:continue
  v=json.loads(line)
  if v.get('kind')!='tool_call':continue
  p=v['payload'];tool=p.get('action');response=p.get('response',{})
  if tool in ('run_tests','integrate_patch','org_review_patch','submit_integration','offer_transfer','accept_transfer','decline_transfer'):
   counts[tool+('_ok' if response.get('ok') else '_error')]+=1
   if not response.get('ok'):messages[tool+':'+str(response.get('error',{}).get('message'))]+=1
   if tool=='run_tests' and not first:first={'event_sequence':v['sequence'],'response':response,'source':str(d/'runtime/experience.jsonl')}
   if tool=='decline_transfer':declines.append(p['arguments'])
 req=list((d/'public-test-rpc').glob('*/request.json'));rpc_deadline=json.loads((d/'actor/create-intent.json').read_text())['configuration']['lifecycle_deadline']
 request_deadline=json.loads(req[0].read_text()).get('hard_deadline_monotonic') if req else None
 rows.append({'sequence':r['sequence'],'counts':dict(counts),'errors':dict(messages),'first_test_feedback':first,'decline_arguments':declines,
  'actor_rpc_deadline':rpc_deadline,'test_request_deadline':request_deadline,'deadline_equal':rpc_deadline==request_deadline if req else None,
  'actual_actor_public_test_RPC_responses':sum(json.loads(f.read_text()).get('tool')=='managed_public_test' for f in (d/'actor/rpc').glob('*response.json'))})
(O/'failure-audit.json').write_text(json.dumps({'rows':rows,'classification':'9 closed runs have solver environment contamination; official fixed-code scores remain diagnostic'},ensure_ascii=False,indent=2)+'\n')
for r in rows:print(r['sequence'],r['counts'],r['errors'],r['decline_arguments'],r['deadline_equal'])
for arm in ('KEEP','REASSIGN'):
 rs=[r for r in a['records'] if r['status']=='closed' and r['arm']==arm];u=sum((collections.Counter(r['usage']) for r in rs),collections.Counter());print('GROUP',arm,'n',len(rs),'pass',sum(r['code'] for r in rs),'usage',dict(u),'mean_full',sum(r['full_policy_tokens'] for r in rs)/len(rs))
print('PREFIX',a['prefix_usage'])
print('NORMAL purposes',sum((collections.Counter(r['purpose_counts']) for r in a['records'] if r['status']=='closed'),collections.Counter()))
# Request-level descriptive costs; not an exclusive causal attribution.
purpose=collections.Counter();testing=collections.Counter();per_run={}
for r in a['records']:
 if r['status']!='closed':continue
 d=pathlib.Path(r['result_source']).parent;own=collections.Counter()
 for f in (d/'physical-api').glob('*/response.json'):
  body=json.loads(f.read_text());q=json.loads((f.parent/'request.json').read_text())['payload'];u=body['usage'];key=q['usage_id']
  purpose[key+'_requests']+=1;purpose[key+'_tokens']+=u['total_tokens']
  if any(z['function']['name']=='run_tests' for z in body['choices'][0]['message'].get('tool_calls',[])):
   testing['requests']+=1;testing['input_tokens']+=u['prompt_tokens'];testing['output_tokens']+=u['completion_tokens'];testing['total_tokens']+=u['total_tokens'];own['requests']+=1;own['tokens']+=u['total_tokens']
 per_run[r['sequence']]=dict(own)
(O/'request-cost-diagnostic.json').write_text(json.dumps({'purpose':dict(purpose),'requests_containing_run_tests':dict(testing),'per_run':per_run,'not_exclusive_or_causal_token_attribution':True},indent=2)+'\n')
