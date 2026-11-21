"""Read-only v223 trajectory audit; no model, container, scoring or source mutation."""
import collections,csv,importlib.util,json,sqlite3
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1];RUN=R/'runs/software-benchmark-v223/paired4-r1';OUT=R/'artifacts/software-benchmark-v223/trajectory-audit-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))
def category(name,purpose):
 if purpose=='condenser':return 'history_summary'
 if name in ('read_file','read_task','search_file','search_repository','locate_work','list_files'):return 'source_navigation'
 if name in ('write_file','replace_file','delete_file','rename_file','apply_patch'):return 'code_edit'
 if name in ('run_tests','run_patch_review_tests'):return 'public_test_request'
 if name in ('read_test_result',):return 'test_feedback_read'
 if name in ('split_work','dynamic_status','org_status','work_readiness','assign_verification','add_collaboration','send_message','org_declare_role','read_work_event','offer_joint_arrangement','accept_joint_arrangement','select_arrangement','change_dependency','handoff_patch','complete_work','org_review_patch','open_patch_review'):return 'organization_and_coordination'
 if name in ('staff_wait','staff_done'):return 'wait_or_finish'
 if name=='annotate_project_graph':return 'graph_review'
 if name=='propose_organization':return 'proposal'
 return 'format_or_other'
def main():
 OUT.mkdir(parents=True,exist_ok=True);sources={};stages=[];request_rows=[];episodes=[]
 def evidence(p):
  p=p.resolve();sources[str(p)]=reference(p);return sources[str(p)]
 for root in sorted(RUN.glob('task-*')):
  i=int(root.name.split('-')[1])
  for stage in sorted(root.iterdir()):
   if not stage.is_dir() or not (stage/'physical-api').exists():continue
   rows=[]
   for p in (stage/'physical-api').glob('*/request.json'):
    q=read(p);b=read(p.parent/'response.json');u=b['usage'];calls=b['choices'][0]['message'].get('tool_calls') or [];tool=calls[0]['function']['name'] if len(calls)==1 else 'format_or_multiple_tools'
    row={'task':i,'stage':stage.name,'physical_id':q['physical_id'],'time':q['time'],'member':q['payload']['member_id'],'purpose':q['payload']['usage_id'],'tool':tool,'category':category(tool,q['payload']['usage_id']),'input_tokens':u['prompt_tokens'],'output_tokens':u['completion_tokens'],'total_tokens':u['total_tokens'],'cached_input_tokens':u.get('prompt_cache_hit_tokens',0),'input_is_authoritative_provider_usage':True,'source':evidence(p),'response':evidence(p.parent/'response.json')}
    assert row['input_tokens']+row['output_tokens']==row['total_tokens'];rows.append(row)
   rows.sort(key=lambda x:x['time']);cumulative=0
   for n,row in enumerate(rows,1):cumulative+=row['total_tokens'];row['stage_request_number']=n;row['stage_cumulative_tokens']=cumulative
   request_rows+=rows
   by=collections.defaultdict(lambda:{'requests':0,'input_tokens':0,'output_tokens':0,'total_tokens':0})
   for row in rows:
    for k in ('input_tokens','output_tokens','total_tokens'):by[row['category']][k]+=row[k]
    by[row['category']]['requests']+=1
   stat={'task':i,'stage':stage.name,'requests':len(rows),'input_tokens':sum(x['input_tokens'] for x in rows),'output_tokens':sum(x['output_tokens'] for x in rows),'total_tokens':cumulative,'categories':dict(by),'mean_prompt_tokens':sum(x['input_tokens'] for x in rows)/max(1,len(rows)),'max_prompt_tokens':max((x['input_tokens'] for x in rows),default=0)};stages.append(stat)
   if stage.name not in ('PREFIX','W0','W1'):continue
   bpath=stage/'boundary.json';b=read(bpath) if bpath.exists() else None;ep={'task':i,'stage':stage.name,'result':read(stage/'result.json'),'result_reference':evidence(stage/'result.json'),'boundary_reference':evidence(bpath) if b else None,'termination_class':b.get('termination_class') if b else 'qualified_checkpoint','opportunities':b.get('opportunities') if b else read(stage/'progress.json')['opportunities']}
   if b:
    actions=[];public=[];errors=[];searches=[]
    for n,o in enumerate(b['outcomes'],1):
     dec=o.get('decision',{});tool=dec.get('action');res=o.get('response',{});v=res.get('result') or {};err=res.get('error');args=dec.get('arguments',{})
     compact={'opportunity_in_fragment':n,'member':o['worker_id'],'action':tool,'status':o['status'],'ok':res.get('ok'),'arguments':args,'error':err}
     actions.append(compact)
     if err:errors.append(compact)
     if tool=='search_repository':searches.append({'opportunity':n,'args':args,'matches':len(v.get('matches',[])),'complete':v.get('complete'),'returned_cursor':bool(v.get('next_cursor')),'supplied_cursor':bool(args.get('cursor'))})
     if tool in ('run_tests','run_patch_review_tests'):
      public.append({'opportunity':n,'member':o['worker_id'],'tool':tool,'ok':res.get('ok'),'source_reference':v.get('source_reference'),'executed':v.get('executed'),'passed':v.get('passed'),'counts':v.get('counts'),'pages':v.get('total_pages'),'first_page_chars':len(v.get('page',{}).get('text','')),'evidence_chars':len(json.dumps(v.get('test_evidence',{}),ensure_ascii=False)),'feedback_chars':len(json.dumps(v,ensure_ascii=False)),'error':err})
    ep.update(action_counts=dict(collections.Counter(x['action'] or x['status'] for x in actions)),errors=errors,public_tests=public,repository_searches=searches)
    save(OUT/f'task-{i:02d}-{stage.name}-actions.json',actions)
   dpath=stage/'decision-state.json'
   if dpath.exists():d=read(dpath);ep.update(prefix_flags=d['reason_flags'],prefix_tokens=d['prefix_tokens']);evidence(dpath)
   tpath=stage/'demand-timeline-final.json'
   if tpath.exists():
    t=read(tpath);records=t['records'];start=len(read(root/'PREFIX/demand-timeline-final.json')['records']) if stage.name!='PREFIX' else 0;own=records[start:]
    ep['graph_observation']={'record_count_in_fragment':len(own),'events_with_relation_delta':sum(any(x['delta'][k] for k in ('added','changed','removed')) for x in own),'changed_relation_counts':sum(len(x['delta']['changed']) for x in own),'fresh_demands':sum(len(x['new_demand_ids']) for x in own),'reconsideration_events':[{'index':x['index'],'new_demand_ids':x['new_demand_ids'],'types':[y['type'] for y in x['assessment']['demands']]} for x in own if x['reconsideration_event']]};evidence(tpath)
   episodes.append(ep)
 finished=read(RUN/'finished.json');evidence(RUN/'finished.json');pair_rows=[];generators=[]
 for i in (2,3):
  root=RUN/f'task-{i:02d}';gr=read(root/'GRAPH/result.json');evidence(root/'GRAPH/result.json')
  for z in ('W0','W1'):
   bank=read(root/('GEN-'+z)/'candidate-bank.json');score=read(root/(z+'-result.json'));evidence(root/('GEN-'+z)/'candidate-bank.json');evidence(root/(z+'-result.json'))
   row={'task':i,'condition':z,'prefix_tokens':bank['prefix_tokens'],'shared_graph_tokens':bank['shared_graph_tokens'],'generator_tokens':bank['actual_generator_tokens'],'logical_total_tokens':score['logical_tokens'],'physical_continuation_tokens':next(x['total_tokens'] for x in stages if x['task']==i and x['stage']==z),'selected':bank['selected'],'code_correct':score['code_correct'],'legal_correct':score['legal_correct']}
   for metric in ('input_tokens','output_tokens'):
    row['logical_'+metric]=sum(next(v[metric] for v in stages if v['task']==i and v['stage']==part) for part in ('PREFIX','GRAPH','GEN-'+z,z))
   assert row['logical_input_tokens']+row['logical_output_tokens']==row['logical_total_tokens']
   assert row['logical_total_tokens']==sum(row[k] for k in ('prefix_tokens','shared_graph_tokens','generator_tokens','physical_continuation_tokens'));pair_rows.append(row)
   diag=read(root/('GEN-'+z)/'generator-diagnostics.json');evidence(root/('GEN-'+z)/'generator-diagnostics.json');assessments=[read(p) for p in sorted((root/('GEN-'+z)).glob('assessment-*.json'))]
   generators.append({'task':i,'condition':z,'diagnostics':{k:diag[k] for k in ('format_and_compile_failures','generated_candidate_count','unparseable_response_count')},'final_assessment':assessments[-1],'selected_reason':bank['candidates'][bank['selected']]['reason'],'bank_contains_full_assessment':'assessment' in bank,'shared_graph_reference':bank['shared_graph_state']})
   for ref in score['scores'].values():evidence(Path(ref['path']))
 totals={k:sum(x[k] for x in request_rows) for k in ('input_tokens','output_tokens','total_tokens','cached_input_tokens')}
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  db=c.execute('SELECT status,count(*),sum(tokens),sum(cost) FROM requests WHERE slot LIKE "v223:%" GROUP BY status').fetchall()
 assert len(db)==1 and db[0][0]=='settled' and db[0][1]==len(request_rows) and db[0][2]==totals['total_tokens']
 logical=sum(x['logical_total_tokens'] for x in pair_rows);shared=sum(x['prefix_tokens']+x['shared_graph_tokens'] for x in pair_rows if x['condition']=='W0');unqualified=sum(x['total_tokens'] for x in stages if x['task'] in (0,1))
 assert logical-shared+unqualified==totals['total_tokens']
 # Reproduce path compilation only; no execution, Docker or paid call.
 spec=importlib.util.spec_from_file_location('v223_audit_public','tools/public_test_library_v175.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 folder=RUN/'task-00/PREFIX';tree=read(folder/'actor/initial-tree.json');entry=read(folder/'actor/create-intent.json')['configuration']['public_test_entry'];validation=[]
 for target in ('tests.utils_tests.test_timezone','utils_tests.test_timezone','db_functions.test_datetime','db_functions.datetime.test_extract_trunc'):
  try:module.selected_entry(entry,{'kind':'django','targets':[target]},files=tree['files'],entry_metadata=tree['entry_metadata']);result={'accepted_by_static_validator':True}
  except module.PublicTestSelectionError as e:result={'accepted_by_static_validator':False,'error':str(e)}
  validation.append({'target':target,**result})
 evidence(folder/'actor/initial-tree.json');evidence(R/'tools/public_test_library_v175.py')
 source=read(RUN/'task-01/PREFIX/actor/initial-tree.json')['files']['sympy/sets/contains.py'];assert 'def as_set(self):\n        raise NotImplementedError()' in source
 base=read(RUN/'task-03/GRAPH/base-state.json');units=[r for r in base['project_relations']['relations'] if r['id'].startswith(('e1d584','fb8ac4'))];graphout=read(RUN/'task-03/GRAPH/response.json');claims=json.loads(graphout['choices'][0]['message']['tool_calls'][0]['function']['arguments'])['hypotheses'];assert 'lines 4315-7236' in claims[0]['claim']
 evidence(RUN/'task-03/GRAPH/base-state.json');evidence(RUN/'task-03/GRAPH/response.json')
 # Identify an actually redundant second call, without counterfactual rerunning.
 from proworksim.software_organization_planning_v223 import parse
 d=RUN/'task-02/GEN-W0';bank=read(d/'candidate-bank.json');raw=read(d/'generated-0.json');args,_=parse(raw['choices'][0]['message']['tool_calls'][0]['function']['arguments'],read(d/'condition-state.json'))
 assert bank['candidates'][bank['selected']]['model_target']==args['candidates'][0]
 redundant=sorted([x for x in request_rows if x['task']==2 and x['stage']=='GEN-W0'],key=lambda x:x['time'])[1]
 aggregate={z:{'mean_logical_tokens':sum(x['logical_total_tokens'] for x in pair_rows if x['condition']==z)/2,'generator_tokens':sum(x['generator_tokens'] for x in pair_rows if x['condition']==z),'continuation_tokens':sum(x['physical_continuation_tokens'] for x in pair_rows if x['condition']==z)} for z in ('W0','W1')}
 delta=2*(aggregate['W0']['mean_logical_tokens']-aggregate['W1']['mean_logical_tokens']);gdelta=aggregate['W0']['generator_tokens']-aggregate['W1']['generator_tokens']
 facts={'scope':'v223 completed four planned tasks; two admitted paired tasks','provider_totals':totals,'physical_requests':len(request_rows),'physical_cost_CNY_upper':db[0][3]/1e9,'remaining_shared_CNY':finished['cash']['remaining_CNY'],'logical_sum':logical,'shared_once_deduction':shared,'unqualified_prefix_tokens':unqualified,'pair_rows':pair_rows,'group_totals':aggregate,'between_group_total_delta':delta,'proposal_stage_delta':gdelta,'proposal_fraction_of_total_delta':gdelta/delta,'stages':stages,'episodes':episodes,'generators':generators,'unchanged_first_valid_candidate_repair':{'task':2,'condition':'W0','second_call_total_tokens':redundant['total_tokens'],'second_call_input_tokens':redundant['input_tokens'],'selected_first_candidate_unchanged':True},'django_static_validation':validation,'django_file_presence':{p:p in tree['files'] for p in ('tests/utils_tests/test_timezone.py','tests/db_functions/test_datetime.py','tests/db_functions/datetime/test_extract_trunc.py')},'graph_unit_ambiguity':{'relations':units,'claim':claims[0],'all_claims_remain_E3':True},'no_model_calls':True,'no_score_changes':True,'new_runtime_changes':False,'category_limit':'Whole request grouped by returned action; NOT causal tool cost or communication-only token attribution'}
 save(OUT/'facts.json',facts);save(OUT/'sources.json',list(sources.values()))
 with (OUT/'requests.csv').open('w') as f:
  keys=['task','stage','physical_id','member','purpose','tool','category','input_tokens','output_tokens','total_tokens','cached_input_tokens','stage_request_number','stage_cumulative_tokens'];writer=csv.DictWriter(f,keys,extrasaction='ignore');writer.writeheader();writer.writerows(request_rows)
 save(OUT/'verification.json',{'passed':True,'provider_ledger_reconciled':True,'logical_physical_reconciled':True,'sources':len(sources),'requests':len(request_rows),'API_calls_by_this_analysis':0,'tests_executed_by_this_analysis':0,'static_validator_calls':4})
 print(json.dumps({k:facts[k] for k in ('provider_totals','physical_cost_CNY_upper','logical_sum','shared_once_deduction','unqualified_prefix_tokens','group_totals','proposal_fraction_of_total_delta','django_static_validation')},ensure_ascii=False))
if __name__=='__main__':main()
