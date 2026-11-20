"""Read-only full-request usage accounting and exact-version trace diagnostics."""
import json,collections,statistics,sqlite3,hashlib
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import checked,reference
R=Path(__file__).resolve().parents[1];ROOT=R/'runs/software-benchmark-v219/recovery6-r1';OUT=R/'artifacts/software-benchmark-v220/trace-audit-r1'
def read(p):return json.loads(p.read_text())
def save(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def key(v):return json.dumps(v,sort_keys=True,ensure_ascii=False)
GROUPS={
 'locating_reading':{'read_file','search_file','search_repository','diff_workspace','read_work_event','search_work_history','read_work_history','list_repository','list_directory','inspect_workspace','list_files'},
 'tests_and_feedback':{'run_tests','run_patch_review_tests','read_test_result'},
 'editing':{'replace_file','write_file','create_file','delete_file','rename_file','apply_patch','edit_file'},
 'peer_communication':{'send_message','handoff_patch'},
 'organization_and_delivery':{'dynamic_status','select_arrangement','offer_joint_arrangement','accept_joint_arrangement','decline_joint_arrangement','change_dependency','add_collaboration','assign_verification','work_readiness','begin_work','fix_patch','complete_work','open_patch_review','org_review_patch','integrate_patch','complete_evidence','adopt_evidence','review_evidence','delivery_checklist','delivery_readiness','submit_integration','org_status','reopen_work','split_work'},
 'private_notes':{'work_note','work_todo','search_private_history','read_private_history'},
 'wait_done':{'staff_wait','staff_done'}}
def purpose(name,usage):
 if usage=='condenser':return 'history_summary'
 for g,names in GROUPS.items():
  if name in names:return g
 return 'other_or_invalid_output'
def main():
 OUT.mkdir(parents=True,exist_ok=True);panels=[read(p) for p in sorted(ROOT.glob('task-*/panel-result.json'))];episodes=[];calls=[];aggregate=collections.defaultdict(collections.Counter)
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as db:
  for panel in panels:
   for z,outcome in panel['outcomes'].items():
    ep=ROOT/f'task-{panel["index"]:02d}'/z;b=read(ep/'boundary.json');g=read(ep/'progress.json');bank=read(checked(panel['bank']));by_id={o.get('decision',{}).get('model_tool_call_id'):o for o in b['outcomes'] if o.get('decision',{}).get('model_tool_call_id')};groups=collections.defaultdict(collections.Counter);epcalls=[]
    for f in (ep/'physical-api').glob('*/usage.json'):
     u=read(f);req=read(f.with_name('request.json'));res=read(f.with_name('response.json'));payload=req['payload'];msg=res['choices'][0]['message'];tc=msg.get('tool_calls') or [];name=tc[0]['function']['name'] if len(tc)==1 else 'no_or_multiple_tools';cid=tc[0].get('id') if len(tc)==1 else None;o=by_id.get(cid);args={}
     if len(tc)==1:
      try:args=json.loads(tc[0]['function']['arguments'])
      except (ValueError,TypeError):pass
     cat=purpose(name,payload['usage_id']);counts={'requests':1,'input_tokens':u['input_tokens'],'output_tokens':u['output_tokens'],'tokens':u['total_tokens'],'cache_hit_tokens':u.get('cache_hit_tokens',0),'cost_nanoyuan':u['peak_cost_nanoyuan']}
     assert u['input_tokens']+u['output_tokens']==u['total_tokens'];groups[cat].update(counts);aggregate[cat].update(counts)
     epcalls.append({'task':panel['index'],'condition':z,'time':req['time'],'physical_id':req['physical_id'],'provider_id':u['provider_response_id'],'member':payload['member_id'],'usage_id':payload['usage_id'],'tool':name,'purpose':cat,**counts,'matched_executed_outcome':o is not None,'tool_ok':o.get('response',{}).get('ok') if o else None,'read_cursor':bool(args.get('cursor')) if isinstance(args,dict) else False,'usage_ref':reference(f),'request_ref':reference(f.with_name('request.json'))})
    epcalls.sort(key=lambda x:x['time']);calls+=epcalls;totals=collections.Counter()
    for row in epcalls:totals.update({k:row[k] for k in ('requests','input_tokens','output_tokens','tokens','cache_hit_tokens','cost_nanoyuan')})
    slot='v219:'+ep.parent.name+':'+z;dbtot=db.execute('SELECT count(*),sum(tokens),sum(cost) FROM requests WHERE slot=? AND status="settled"',(slot,)).fetchone();assert tuple(totals[k] for k in ('requests','tokens','cost_nanoyuan'))==dbtot
    assert bank['prefix_tokens']+bank['actual_generator_tokens']+totals['tokens']==outcome['logical_tokens']
    tests=[];reads=[];errors=[];waits=[];seen_tests=set();seen_reads=set();testdup=readdup=0;actions=collections.Counter()
    for index,o in enumerate(b['outcomes']):
     d=o.get('decision',{});tool=d.get('action');args=d.get('arguments',{});response=o.get('response',{});rr=response.get('result',{}) or {};actor=o['worker_id'];actions[tool or o['status']]+=1
     if response.get('ok') is False:errors.append({'index':index,'actor':actor,'tool':tool,'error':response.get('error'),'arguments':args})
     if o['status'] in ('worker_waiting','model_format_feedback','unattributed_tool_rejection'):waits.append({'index':index,'actor':actor,'status':o['status'],'reason':o.get('reason')})
     if tool in ('run_tests','run_patch_review_tests'):
      identity=(actor,tool,key(args),rr.get('files_sha256'));duplicate=bool(rr.get('executed') and rr.get('files_sha256') and identity in seen_tests)
      if rr.get('executed') and rr.get('files_sha256'):seen_tests.add(identity)
      testdup+=duplicate;tests.append({'index':index,'actor':actor,'tool':tool,'arguments':args,'executed':rr.get('executed'),'passed':rr.get('passed'),'files_sha256':rr.get('files_sha256'),'counts':rr.get('counts'),'same_member_same_version_same_selection_repeat':duplicate,'report_id':rr.get('report_id')})
     if tool=='read_file' and response.get('ok'):
      ident=(actor,rr.get('path'),rr.get('text_sha256'),rr.get('start_character'),rr.get('end_character'));duplicate=rr.get('text_sha256') is not None and ident in seen_reads;seen_reads.add(ident);readdup+=duplicate
      reads.append({'index':index,'actor':actor,'path':rr.get('path'),'start':rr.get('start_character'),'end':rr.get('end_character'),'cursor':bool(args.get('cursor')),'identical_content_range_repeat':duplicate})
    score=read(checked(outcome['scores']['code']));report=score['official_result'][1][panel['instance_id']];ts=report.get('tests_status',{});res=read(ep/'result.json');dynamic=read(ep/'dynamic-final.json')
    members={m:{'requests':sum(c['member']==m for c in epcalls),'tokens':sum(c['tokens'] for c in epcalls if c['member']==m),'mean_agent_input':statistics.mean(v) if (v:=[c['input_tokens'] for c in epcalls if c['member']==m and c['usage_id']=='agent']) else None} for m in ('member_001','member_002')}
    episode={'index':panel['index'],'instance_id':panel['instance_id'],'phase':panel['phase'],'condition':z,'code':outcome['code_correct'],'legal':outcome['legal_correct'],'submitted':outcome['formal_submission'],'logical_tokens':outcome['logical_tokens'],'prefix_tokens':bank['prefix_tokens'],'generator_tokens':bank['actual_generator_tokens'],'physical_continuation':dict(totals),'groups':{k:dict(v) for k,v in groups.items()},'member_usage':members,'budget_stop':outcome['normal_budget_stop'],'termination':b['termination_class'],'stage_notices':b['stage_wait_corrections'],'actions':dict(actions),'errors':errors,'tests':tests,'file_reads':reads,'exact_test_repeats':testdup,'identical_read_repeats':readdup,'wait_and_format_events':waits,'official_failed_F2P':ts.get('FAIL_TO_PASS',{}).get('failure',[]),'official_failed_P2P':ts.get('PASS_TO_PASS',{}).get('failure',[]),'wall_seconds':res['finished']-res['started'],'timing':g.get('timing'),'choice':dynamic['lifecycle'].get('choice'),'boundary_ref':reference(ep/'boundary.json'),'official_ref':outcome['scores']['code']}
    episodes.append(episode)
  current=db.execute("SELECT count(*),sum(tokens),sum(cost) FROM requests WHERE slot LIKE 'v219:%' AND status='settled'").fetchone()
  total=db.execute("SELECT sum(cost)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
 summary={'episodes':len(episodes),'distinct_states':len(panels),'code_pass':sum(e['code'] for e in episodes),'legal_pass':sum(e['legal'] for e in episodes),'budget_stops':sum(e['budget_stop'] for e in episodes),'all_continuation_requests_reconciled':True,'attribution_basis':'Entire input+output request grouped by returned action/usage; NOT exclusive semantic communication/source cost or causal savings','groups':{k:dict(v) for k,v in aggregate.items()},'continuation_requests':len(calls),'continuation_tokens':sum(c['tokens'] for c in calls),'continuation_input':sum(c['input_tokens'] for c in calls),'continuation_output':sum(c['output_tokens'] for c in calls),'continuation_cost_CNY_upper':sum(c['cost_nanoyuan'] for c in calls)/1e9,'v219_physical_total':dict(zip(('requests','tokens','cost_nanoyuan'),current)),'shared_cash':total,'remaining_CNY':1100-total,'score_infrastructure_unknown':0,'same_member_version_selector_test_repeats':sum(e['exact_test_repeats'] for e in episodes),'identical_file_range_repeats':sum(e['identical_read_repeats'] for e in episodes),'stage_notices':sum(len(e['stage_notices']) for e in episodes),'branch_mean_logical_tokens':statistics.mean(e['logical_tokens'] for e in episodes)}
 save('requests.json',calls);save('episodes.json',episodes);save('summary.json',summary)
 print(json.dumps(summary,ensure_ascii=False))
 for e in episodes:print(e['index'],e['condition'],'logical',e['logical_tokens'],'groups',{k:v['tokens'] for k,v in e['groups'].items()},'tests',[(t['executed'],t['passed'],t['counts']) for t in e['tests']],'readrepeat',e['identical_read_repeats'])
if __name__=='__main__':main()
