"""Evidence-state distinctions: execution/version facts do not prove semantics."""
import copy

def bind_check(*,actor,requirement_id,requirements,test_event,check_path,source_files,public_input,expected_result):
 if requirement_id not in requirements:raise ValueError('Unknown frozen public requirement')
 if test_event.get('kind')!='test' or test_event.get('actor_id')!=actor:raise ValueError('Bind an actual own public test event')
 if test_event.get('executed') is not True:raise ValueError('No executed public test')
 if check_path not in source_files:raise ValueError('Check path absent from authorized tested tree')
 if not public_input.strip() or not expected_result.strip():raise ValueError('Explicit public input and expectation required')
 execution=test_event.get('public_execution',{}).get('execution',{});counts=execution.get('counts',test_event.get('counts',{}))
 selection=test_event.get('public_test_selection')
 return {'actor':actor,'requirement_id':requirement_id,'test_sequence':test_event['sequence'],'source_reference':copy.deepcopy(test_event.get('source_reference')),'files_sha256':test_event.get('files_sha256'),'entry_metadata_sha256':test_event.get('entry_metadata_sha256'),'executed':True,'passed':test_event.get('passed'),'test_counts':counts,'selection':copy.deepcopy(selection),'check_path':check_path,'public_input':public_input,'expected_result':expected_result,'semantic_coverage':'unverified_member_claim','check_path_in_tested_tree':True,'specific_check_execution':'not_inferred_from_file_presence_or_passing_summary','official_score_used':False}

def summarize(requirements,bindings,current_identity):
 rows=[]
 for req in requirements:
  items=[]
  for b in bindings:
   if b['requirement_id']!=req:continue
   exact=all(b.get(k)==current_identity.get(k) for k in ('source_reference','files_sha256','entry_metadata_sha256'))
   items.append({**copy.deepcopy(b),'current_version':exact,'status':'historical_version' if not exact else 'execution_failed' if b['passed'] is not True else 'executed_passed_coverage_unverified'})
  rows.append({'requirement_id':req,'checks':items,'state':'no_bound_public_check' if not items else 'coverage_still_requires_semantic_review'})
 return {'requirements':rows,'all_requirements_semantically_verified':False,'passed_test_does_not_prove_requirement':True,'delivery_authority_unchanged':True}
