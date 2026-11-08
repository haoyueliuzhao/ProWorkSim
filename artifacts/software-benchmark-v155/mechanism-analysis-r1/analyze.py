"""Read selected controller receipts once; no archives, API, Docker or ledger scan."""
from __future__ import annotations
from collections import Counter,defaultdict
from pathlib import Path
import hashlib,json,statistics
from proworksim.software_benchmark_alignment_contract_v141 import condition
from proworksim.software_collaboration_observation_v141 import load_official_content_counter,_overlap,_json

ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT=ROOT/'artifacts/software-benchmark-v155/mechanism-analysis-r1'
EPISODES=ROOT/'artifacts/software-benchmark-v155/final-report-r1/episodes.json'
GROUPS=('S1','FREE2','REVIEW2')
TARGETS=('send_message','handoff_patch','integrate_patch','org_review_patch','fix_patch','submit_integration','run_tests','read_test_result','read_file','search_repository','write_file','replace_file','create_file','delete_file','rename_file','work_history_search','work_history_read','org_declare_role','create_task','claim_task','return_task','read_task','read_work_event','org_status','offer_transfer','accept_transfer','decline_transfer')

def ref(p,raw=None):
 p=Path(p).resolve();raw=p.read_bytes() if raw is None else raw
 return {'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}

def read(p):return json.loads(Path(p).read_text())
def union_size(intervals):
 total=0;last=None
 for a,b in sorted(intervals):
  if last is None: last=(a,b)
  elif a<=last[1]:last=(last[0],max(last[1],b))
  else:total+=last[1]-last[0];last=(a,b)
 return total+(last[1]-last[0] if last else 0)


def observer(folder):
 summary=folder/'summary.json'
 if summary.exists():
  x=read(summary)
  return {'kind':'finalized_summary','source':ref(summary),'messages':x['messages'],'information':x['information'],
    'artifacts':x['artifacts'],'coverage':x['coverage'],'measurement_errors':x.get('runtime_measurement_errors',[])}
 log=folder/'events.jsonl'
 if not log.exists():return {'kind':'missing','source':None,'coverage':{},'measurement_errors':[]}
 raw=log.read_bytes();lines=raw.splitlines();header=json.loads(lines[0]);meta=header['meta'];rows={};last=None
 for seq,line in enumerate(lines[1:],1):
  x=json.loads(line);body={k:v for k,v in x.items() if k!='sha256'}
  if x['sequence']!=seq or x['previous_sha256']!=last or hashlib.sha256(_json(body).encode()).hexdigest()!=x['sha256']:
   raise ValueError('Observer event chain changed')
  if x['event_id'] in rows:raise ValueError('Duplicate event identity')
  rows[x['event_id']]=x;last=x['sha256']
 messages=[x for x in rows.values() if x['kind']=='message_sent'];reads=[x for x in rows.values() if x['kind']=='information_read']
 presented=Counter()
 for x in rows.values():
  if x['kind']=='information_presented':
   for event in x['data']['information_events']:
    presented[(x['actor'],event)]+=1
 seen=defaultdict(list);team=defaultdict(list);same=cross=chars=0
 for x in reads:
  d=x['data'];key=(d['path'],d['full_text_sha256']);s,e=d['start'],d['end'];a=_overlap(s,e,seen[(x['actor'],key)]);b=_overlap(s,e,team[key]);same+=a;cross+=b-a;chars+=e-s;seen[(x['actor'],key)].append((s,e));team[key].append((s,e))
 errors=read(folder/'measurement-errors.json') if (folder/'measurement-errors.json').exists() else []
 return {'kind':'unfinalized_events_readonly','source':ref(log,raw),'event_count':len(rows),'team_id':meta['team_id'],
  'messages':{'sent':len(messages),'obtained_receipts':sum(x['kind']=='message_received' for x in rows.values()),
    'observed_model_presentations':sum(n for (_,eid),n in presented.items() if rows[eid]['kind']=='message_received'),
    'actual_model_presentations':None,'direct_content_tokens_known':sum(x['data']['content']['tokens'] or 0 for x in messages),
    'direct_content_tokens':None,'net_communication_token_cost':None},
  'information':{'returned_read_characters':chars,'same_member_reread_characters':same,
    'cross_member_first_acquisition_overlap_characters':cross,
    'returned_content_tokens_known':sum(x['data']['content']['tokens'] or 0 for x in reads),
    'read_events_presented_to_model':len({eid for (_,eid) in presented if rows[eid]['kind']=='information_read'}),
    'observed_model_presentations':sum(n for (_,eid),n in presented.items() if rows[eid]['kind']=='information_read'),
    'actual_model_presentations':None,'presentation_coverage_complete':False},
  'artifacts':{'published':sum(x['kind']=='artifact_published' for x in rows.values()),'entered_legal_delivery_chain':None},
  'coverage':{},'measurement_errors':errors,'finalize_not_replayed':True}


def analyze(row,count):
 p=Path(row['controller_result_path']);raw=p.read_bytes();x=json.loads(raw);b=x['managed_boundary'];l=x['ledger']
 assert x['slot_id']==row['selected_slot_id'] and x['organization_id']==row['group_id']
 assert b['status']=='bounded_work_closed' and b['execution_integrity_failure'] is None
 roles=b.get('role_stops',{});limits=Counter();stopreasons=[]
 for m,d in b.get('terminal_details',{}).items():
  for limit in d.get('limits',[]):limits[limit]+=1
  stopreasons.append({'member':m,**{k:d.get(k) for k in ['status','reason','cause','limits']}})
 budget=any(v in {'model_budget_exhausted','team_budget_exhausted'} for v in roles.values()) or b['closure_reason'].startswith('shared_team_pool_exhausted')
 if b.get('cash_censored'):terminal='cash_boundary'
 elif b.get('administrative_censoring'):terminal='administrative_deadline'
 elif budget:terminal='explicit_model_budget_boundary'
 elif b['closure_reason']=='organization_contract_blocked':terminal='organization_contract_blocked'
 else:terminal='members_stopped_or_waiting_without_explicit_budget_boundary'
 tools=defaultdict(Counter);statuses=Counter();decisions=Counter();rejections=[];allrej=Counter();test_groups=Counter();test_examples=[];tests_executed=tests_passed=0
 messages={'sent':0,'characters':0,'utf8_bytes':0,'plain_content_tokens':0,'unmeasured_payloads':0}
 read_spans=defaultdict(list);read_chars=0;read_missing=0;read_events=0
 patches={};integrations=[];review_choices=Counter();writings=[];event_counts=Counter();memberactions=Counter();last_relevant=[]
 for n,o in enumerate(b['outcomes']):
  status=o.get('status');statuses[status]+=1;d=o.get('decision') or {};decisions[d.get('kind','missing')]+=1
  action=d.get('action');a=d.get('arguments') or {};actor=o.get('worker_id');response=o.get('response') or {};ok=response.get('ok');r=response.get('result') or {}
  if not isinstance(r,dict):r={}
  if action:
   tools[action]['invocations']+=1;tools[action]['successful' if ok is True else 'explicitly_rejected' if ok is False else 'outcome_unknown']+=1
   memberactions[actor]+=1
   if ok is False:
    err=response.get('error') or {};code=err.get('code',err.get('type','unknown')) if isinstance(err,dict) else 'unstructured';allrej[f'{action}:{code}']+=1
    rejections.append({'outcome_index':n,'actor':actor,'tool':action,'error':err,'model_call_id':d.get('model_call_id')})
   if action in {'fix_patch','submit_integration','org_review_patch','integrate_patch','run_tests'}:
    last_relevant.append({'outcome_index':n,'actor':actor,'tool':action,'ok':ok,'status':r.get('status'),'patch_id':r.get('patch_id',a.get('patch_id')),'source_reference':r.get('source_reference'),'passed':r.get('passed'),'error':response.get('error')})
  if ok is True and action=='send_message':
   body=a.get('body');messages['sent']+=1
   if isinstance(body,str):
    messages['characters']+=len(body);messages['utf8_bytes']+=len(body.encode());messages['plain_content_tokens']+=count(body)
   else:messages['unmeasured_payloads']+=1
  if ok is True and action=='read_file':
   read_events+=1
   if {'path','text_sha256','start_character','end_character','text'}<=set(r) and len(r['text'])==r['end_character']-r['start_character']:
    read_spans[(actor,r['path'],r['text_sha256'])].append((r['start_character'],r['end_character']));read_chars+=len(r['text'])
   else:read_missing+=1
  if ok is True and action=='fix_patch' and r.get('patch_id'):patches[r['patch_id']]={'actor':actor,'source_reference':r.get('source_reference'),'outcome_index':n}
  if ok is True and action=='integrate_patch':integrations.append({'outcome_index':n,'actor':actor,'patch_id':a.get('patch_id'),'status':r.get('status'),'conflicts':r.get('conflicts'),'source_reference':r.get('source_reference'),'result':{k:v for k,v in r.items() if k in {'status','source_reference','included_patch_ids','conflicts','changed_paths','patch_id'}}})
  if action=='org_review_patch':review_choices[f"{a.get('decision')}:{'accepted' if ok is True else 'rejected' if ok is False else 'unknown'}"]+=1
  if ok is True and action=='run_tests':
   if r.get('executed') is True:tests_executed+=1
   if r.get('passed') is True:tests_passed+=1
   key=(actor,json.dumps(r.get('source_reference'),sort_keys=True),json.dumps(a.get('selection'),sort_keys=True))
   test_groups[key]+=1
   test_examples.append({'outcome_index':n,'actor':actor,'source_reference':r.get('source_reference'),'selection':a.get('selection'),'executed':r.get('executed'),'passed':r.get('passed'),'validation_status':r.get('validation_status'),'counts':r.get('counts')})
  if row['selected_slot_index']==10219 and action in {'write_file','replace_file','create_file'} and a.get('path')=='src/_pytest/python.py':
   text=a.get('text');writings.append({'outcome_index':n,'actor':actor,'tool':action,'arguments':a,'ok':ok,'action_performed':o.get('action_performed'),'model_call_id':d.get('model_call_id'),'model_tool_call_id':d.get('model_tool_call_id'),'response':response})
 memberunique=sum(union_size(v) for v in read_spans.values());teamspans=defaultdict(list)
 for (actor,path,sha),spans in read_spans.items():teamspans[(path,sha)].extend(spans)
 cross=memberunique-sum(union_size(v) for v in teamspans.values())
 for item in integrations:item['published_author']=patches.get(item['patch_id'],{}).get('actor')
 peer=[z for z in integrations if z['actor']=='member_001' and z['published_author']=='member_002' and z['status']!='conflicted' and not z['conflicts']]
 model=b['team_budget'].get('model',{})
 obs=observer(p.parent/'model-ledger/collaboration-observation')
 data={k:row[k] for k in ['instance_id','repo','group_id','selected_slot_id','selected_slot_index','code_passed','delivery_passed','selection_source']}
 data.update(controller_source=ref(p,raw),closure_reason=b['closure_reason'],terminal_category=terminal,explicit_budget_boundary=budget,
  role_stops=roles,terminal_details=stopreasons,budget_limits=dict(limits),remaining_model_budget={k:model.get(k) for k in ['available_tokens','remaining_decisions','remaining_attempts','charged_tokens']},
  status_counts=dict(statuses),decision_kind_counts=dict(decisions),tool_counts={k:dict(v) for k,v in tools.items()},
  explicit_rejection_count=sum(v['explicitly_rejected'] for v in tools.values()),rejection_categories=dict(allrej),rejection_examples=rejections[-8:],
  message_payload=messages,read_file_responses={'valid_span_characters':read_chars,'events':read_events,'unmeasured_events':read_missing,
    'same_member_reread_characters':read_chars-memberunique,'cross_member_overlap_characters':cross,'is_actual_prompt_cost':False},
  review_decisions=dict(review_choices),peer_code_integrations=peer,all_integrations=integrations,patch_authors=patches,
  tests={'executed':tests_executed,'passed':tests_passed,'same_actor_version_selection_extra_runs':sum(max(0,v-1) for v in test_groups.values()),'examples':test_examples[-6:]},
  actual_actions_by_member=dict(memberactions),last_relevant_operations=last_relevant[-12:],
  finish_review_counts={m:v.get('finish_reviews') for m,v in x.get('finish_review',{}).items()},
  observer=obs,selected_usage={k:row.get(k) for k in ['input_tokens','output_tokens','total_tokens','physical_requests','condenser_tokens']},
  placeholder_write_actions=writings)
 return data


def main():
 selection=read(EPISODES);rows=selection['rows'];assert len(rows)==120
 tok=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
 if (OUT/'per_episode_metrics.json').exists():
  metrics=read(OUT/'per_episode_metrics.json')['rows']
  tokenizer=read(OUT/'summary.json')['message_content_tokenizer']
  assert {m['selected_slot_id'] for m in metrics}=={r['selected_slot_id'] for r in rows}
  for m in metrics:
   m['explicit_budget_boundary']=any(v in {'model_budget_exhausted','team_budget_exhausted'} for v in m['role_stops'].values()) or m['closure_reason'].startswith('shared_team_pool_exhausted')
   if m['explicit_budget_boundary']:m['terminal_category']='explicit_model_budget_boundary'
 else:
  count,tokenizer=load_official_content_counter(tok,manifest_sha256=ref(tok)['sha256'])
  metrics=[analyze(r,count) for r in rows]
 (OUT/'per_episode_metrics.json').write_text(json.dumps({'version':'v155-mechanism-selected120-r1','selection':ref(EPISODES),'rows':metrics},ensure_ascii=False,indent=2))
 groups={}
 for group in GROUPS:
  a=[m for m in metrics if m['group_id']==group];tools=defaultdict(Counter);rej=Counter();terms=Counter(m['terminal_category'] for m in a)
  for m in a:
   for k,v in m['tool_counts'].items():tools[k].update(v)
   rej.update(m['rejection_categories'])
  known_msg_present=sum(m['observer'].get('messages',{}).get('observed_model_presentations',0) for m in a)
  known_read_present=sum(m['observer'].get('information',{}).get('observed_model_presentations',0) for m in a)
  groups[group]={'episodes':len(a),'terminal_categories':dict(terms),'explicit_budget_boundary_count':sum(m['explicit_budget_boundary'] for m in a),
   'budget_boundary_and_code_pass':sum(m['explicit_budget_boundary'] and m['code_passed'] for m in a),
   'budget_boundary_and_code_fail':sum(m['explicit_budget_boundary'] and not m['code_passed'] for m in a),
   'code_pass_delivery_fail':sum(m['code_passed'] and not m['delivery_passed'] for m in a),
   'code_fail_delivery_pass':sum(not m['code_passed'] and m['delivery_passed'] for m in a),
   'code_pass_delivery_fail_with_budget_boundary':sum(m['code_passed'] and not m['delivery_passed'] and m['explicit_budget_boundary'] for m in a),
   'tool_counts':{k:dict(v) for k,v in tools.items()},'explicit_tool_rejections':sum(m['explicit_rejection_count'] for m in a),
   'format_feedback_events':sum(m['status_counts'].get('model_format_feedback',0) for m in a),
   'rejection_categories':dict(rej),'direct_message_payload':{key:sum(m['message_payload'][key] for m in a) for key in ['sent','characters','utf8_bytes','plain_content_tokens','unmeasured_payloads']},
   'read_file_responses':{key:sum(m['read_file_responses'][key] for m in a) for key in ['events','valid_span_characters','unmeasured_events','same_member_reread_characters','cross_member_overlap_characters']},
   'peer_integrations_by_001':sum(len(m['peer_code_integrations']) for m in a),
   'episodes_with_peer_integrations_by_001':sum(bool(m['peer_code_integrations']) for m in a),
   'same_actor_version_selection_extra_test_runs':sum(m['tests']['same_actor_version_selection_extra_runs'] for m in a),
   'observer_finalized_summaries':sum(m['observer']['kind']=='finalized_summary' for m in a),
   'observer_measurement_error_episodes':sum(bool(m['observer']['measurement_errors']) for m in a),
   'observer_presentation_complete_episodes':sum(m['observer']['coverage'].get('presentations') is True for m in a),
   'observer_known_message_presentations':known_msg_present,'observer_known_read_presentations':known_read_present,
   'net_communication_token_cost':None,'causal_member_count_effect':None}
 schemas=read(ROOT/'runs/software-benchmark-v142/role-pilot40-r1/deployment-v143/api-coordinator/api-runtime/member-tool-schemas-r2.json')['schemas']
 configs={g:{'members':condition(g)['fixed_members'],'inference':condition(g)['inference'],'shared_token_budget':5_000_000,
  'strategy':condition(g)['execution_strategy'],'tool_names':{m:[t['function']['name'] for t in v] for m,v in schemas[g].items()},
  'tool_counts':{m:len(v) for m,v in schemas[g].items()}} for g in GROUPS}
 summary={'version':'v155-mechanism-selected120-r1','selection':ref(EPISODES),'source_script':ref(__file__),
  'controller_files_read':120,'controller_bytes_read':sum(m['controller_source']['bytes'] for m in metrics),
  'archive_decompressions':0,'provider_ledger_reads':0,'API_calls':0,'groups':groups,'frozen_configurations':configs,'message_content_tokenizer':tokenizer,
  'method_notes':['Controller outcomes counted once per managed act; response.ok false are explicit rejections, format feedback before dispatch separate.',
   'Budget boundary uses role_stops/model_budget_exhausted or team_budget_exhausted or shared_team_pool closure, not misleading top-level all_members_stopped label.',
   'Successful send_message body plain-text tokens measured using original frozen content tokenizer; not chat-template or repeated input billing.',
   'Read overlaps count returned character spans of same path/full-text hash, not wasted work or actual prompt-token repetition.',
   '99 existing observer summaries plus21 small unfinalized append-only event sidecars; no final coverage fabricated for recovered exports.',
   'Observed model presentations are lower-bound appearances when summary transformation has missing provenance. Net communication cost is not identifiable.',
   'Peer integration means a successful conflict-free member001 integrate of a patch published by member002; final delivered-chain proof requires the existing closure evidence.',
   'Recovery changed transport reliability and calendar period, not role/inference settings; compare selected results separately from original attempts.'],
  'evidence':[ref(ROOT/'src/proworksim/software_role_baseline_runtime_v141.py'),ref(ROOT/'src/proworksim/software_role_baseline_contract_v141.py'),ref(ROOT/'src/proworksim/software_benchmark_alignment_contract_v141.py'),ref(ROOT/'src/proworksim/software_collaboration_runtime_observer_v141.py')],
  'per_episode_metrics':ref(OUT/'per_episode_metrics.json')}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print(json.dumps({g:{k:v for k,v in x.items() if k not in {'tool_counts','rejection_categories'}} for g,x in groups.items()},ensure_ascii=False,indent=2))
 print('PLACEHOLDER',json.dumps(next(m for m in metrics if m['selected_slot_index']==10219)['placeholder_write_actions'],ensure_ascii=False)[:4500])

if __name__=='__main__':main()
