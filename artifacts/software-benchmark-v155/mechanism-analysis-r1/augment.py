"""Join compact metrics to existing endpoint locks; never reread model traces."""
from pathlib import Path
import json,hashlib
from collections import Counter
ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim');OUT=ROOT/'artifacts/software-benchmark-v155/mechanism-analysis-r1'
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();raw=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
metrics=read(OUT/'per_episode_metrics.json')['rows'];selected={r['selected_slot_index']:r for r in read(ROOT/'artifacts/software-benchmark-v155/final-report-r1/episodes.json')['rows']}
def local(path, selected_row):
 p=Path(path)
 return Path(selected_row['controller_result_path']).parent/p.relative_to('/pws/output') if p.is_relative_to('/pws/output') else p
gaps=[]
for m in metrics:
 if not (m['code_passed'] and not m['delivery_passed']):continue
 s=selected[m['selected_slot_index']]
 if s['normal_export_ref']:
  r=read(s['normal_export_ref']['path']);lockref=r['closure']['controller_candidate_lock']
 else:lockref=ref(Path(s['controller_result_path']).parent/'project-candidates/lock.json')
 l=read(lockref['path'])
 code=read(local(l['terminal_code']['path'],s));delivery=read(local(l['last_legal_delivery']['path'],s)) if l['last_legal_delivery'] else None
 gaps.append({k:m[k] for k in ['selected_slot_id','selected_slot_index','instance_id','group_id','explicit_budget_boundary','terminal_details','tool_counts','review_decisions','last_relevant_operations','rejection_examples','controller_source']}|{
  'episode_lock':lockref,'submitted':l['submitted'],'same_tree':l['same_tree'],'code_source':code['source_reference'],
  'delivery_source':delivery['source_reference'] if delivery else None,
  'gap_kind':'older_different_legal_submission_failed' if l['submitted'] else 'no_legal_submission',
  'code_evidence':s['code_evidence'],'delivery_evidence':s['delivery_evidence']})
positive=next(m for m in metrics if m['selected_slot_index']==10056)
p=Path(selected[10056]['controller_result_path']).parent/'project-candidates/lock.json';pl=read(p);terminal=read(local(pl['terminal_code']['path'],selected[10056]))
assert terminal['source_reference']==positive['peer_code_integrations'][0]['source_reference']
positive_case={'kind':'observed_partner_integration_with_passing_final_code','selected_slot_id':positive['selected_slot_id'],
 'instance_id':positive['instance_id'],'group_id':'FREE2','selected_slot_index':10056,'code_passed':True,'delivery_passed':True,
 'integration':positive['peer_code_integrations'][0],'patch_author':positive['patch_authors']['patch-3'],
 'locked_terminal_source':terminal['source_reference'],'episode_lock':ref(p),'same_tree_as_last_legal_delivery':pl['same_tree'],
 'observer_artifact_measurement':positive['observer']['artifacts'],'controller_source':positive['controller_source'],
 'limit':'This proves explicit member002 patch adoption into the exact final member001 version. An older legal submission also passes; no isolated causal benefit or final legal-delivery-chain use of that partner patch is proven.'}
neg=next(m for m in metrics if m['selected_slot_index']==10017)
negative_case={'kind':'repeated_public_testing_without_official_success','selected_slot_id':neg['selected_slot_id'],
 'instance_id':neg['instance_id'],'group_id':neg['group_id'],'selected_slot_index':10017,'code_passed':False,'delivery_passed':False,
 'explicit_budget_boundary':neg['explicit_budget_boundary'],'tests':neg['tests'],'tools':{k:neg['tool_counts'].get(k) for k in ['send_message','org_status','run_tests','read_test_result','fix_patch','integrate_patch','org_review_patch','submit_integration']},
 'last_relevant_operations':neg['last_relevant_operations'],'controller_source':neg['controller_source'],
 'limit':'Different selections or independently motivated checks are not automatically redundant. Passing some public checks does not establish official correctness; budget prevents a causal claim that review itself caused failure.'}
errors=[{'selected_slot_id':m['selected_slot_id'],'selected_slot_index':m['selected_slot_index'],'group_id':m['group_id'],'instance_id':m['instance_id'],
 'observer_source':m['observer']['source'],'errors':m['observer']['measurement_errors'],'code_passed':m['code_passed'],'delivery_passed':m['delivery_passed']} for m in metrics if m['observer']['measurement_errors']]
errorproof={'version':'v155-observer-execution-semantics-mismatch-r1','episodes':len(errors),'error_records':sum(len(m['errors']) for m in errors),'rows':errors,
 'execution_rule':'World acceptance requires explicit adoption and actual same-version public-test execution; passed=True is not required.',
 'observer_rule':'artifact_review accept demands linked validation.passed=True.',
 'execution_effect':'RuntimeObservationBridge.execute first executes the world action; safely then catches ObservationError, records it and returns original response. No action/model retry is performed.',
 'execution_source':ref(ROOT/'src/proworksim/software_role_baseline_world_v141.py'),
 'observer_source':ref(ROOT/'src/proworksim/software_collaboration_observation_v141.py'),
 'isolation_source':ref(ROOT/'src/proworksim/software_collaboration_runtime_observer_v141.py'),
 'fixed_in_this_report':False,'new_tests_or_model_calls':0}
(OUT/'observer-error-evidence.json').write_text(json.dumps(errorproof,ensure_ascii=False,indent=2))
cases={'version':'v155-source-bound-mechanism-cases-r1','gaps':gaps,'positive_partner_integration':positive_case,
 'repeated_test_failure':negative_case,'placeholder_model_write_proof':ref(OUT/'pytest6197-model-write-provenance.json')}
(OUT/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
s=read(OUT/'summary.json')
for g,d in s['groups'].items():
 a=[m for m in metrics if m['group_id']==g]
 d['gap_types']=dict(Counter(v['gap_kind'] for v in gaps if v['group_id']==g))
 d['observer_unique_read_events_presented_known']=sum(m['observer'].get('information',{}).get('read_events_presented_to_model',0) for m in a)
 d['observed_representations_per_known_read_event']=d['observer_known_read_presentations']/d['observer_unique_read_events_presented_known']
 d['read_response_same_member_overlap_ratio']=d['read_file_responses']['same_member_reread_characters']/d['read_file_responses']['valid_span_characters']
 d['read_response_cross_member_overlap_ratio']=d['read_file_responses']['cross_member_overlap_characters']/d['read_file_responses']['valid_span_characters']
 d['explicit_budget_boundary_rate']=d['explicit_budget_boundary_count']/40
s['case_evidence']=ref(OUT/'cases.json');s['observer_error_evidence']=ref(OUT/'observer-error-evidence.json')
s['placeholder_attribution_proof']=ref(OUT/'pytest6197-model-write-provenance.json')
s['observer_unfinalized_events_bytes_read']=sum(m['observer']['source']['bytes'] for m in metrics if m['observer']['kind']=='unfinalized_events_readonly')
s['observer_actual_full_presentation_counts_unknown_episodes']=sum(m['observer']['coverage'].get('presentations') is not True for m in metrics)
s['recorded_measurement_errors_are_generation_failures']=False
(OUT/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2))
print('gap_types',{g:v['gap_types'] for g,v in s['groups'].items()})
print('observer_errors',errorproof['episodes'],errorproof['error_records'])
print('cases_ready',str(OUT/'cases.json'))
