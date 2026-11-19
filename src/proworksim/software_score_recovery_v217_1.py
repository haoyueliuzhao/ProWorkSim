"""Strict evidence classification of candidate merge-conflict syntax failures.

The raw official report is retained. A missing report, timeout, failed patch
application or unbound error remains unknown and cannot be converted to failure.
"""
import json,re
from pathlib import Path
from .software_benchmark_candidates_v054 import checked,reference
VERSION='v217.1-candidate-failure-not-infrastructure-r1'
def conflict_evidence(report,run_log,test_output,files):
 if report.get('resolved') is not False or report.get('infra_failure') is not False:return None
 if not re.search(r'^>>>>> Test Exit Code: 1\s*$',test_output,re.M):return None
 if not all(x in test_output for x in ('>>>>> Start Test Output','>>>>> End Test Output','>>>>> Test Exit Code: 1','SyntaxError:')):return None
 matches=re.findall(r'File "/testbed/([^"\n]+)", line (\d+)',test_output)
 for path,line in reversed(matches):
  if path not in files or f'Applied patch {path} cleanly.' not in run_log:continue
  source=files[path];n=int(line);lines=source.splitlines()
  if not (0<n<=len(lines) and lines[n-1].lstrip().startswith('<<<<<<< ') and '>>>>>>> ' in source):continue
  try:compile(source,path,'exec')
  except SyntaxError as e:
   if e.lineno==n:return {'path':path,'line':n,'locked_source_line':lines[n-1],'patch_applied_log_evidence':True,'test_exit_code':1,'candidate_compile_error':str(e),'classification':'unresolved_candidate_merge_conflict'}
 return None

def recover(receipt,score_dir):
 if receipt.get('status')!='technical_unknown' or not receipt.get('official_result'):return None
 iid=receipt['instance_id'];report=receipt['official_result'][1].get(iid,{})
 if not receipt.get('endpoint_lock') or not receipt.get('patch'):return None
 lock=json.loads(checked(receipt['endpoint_lock']).read_text())
 if lock['tree_sha256']!=receipt['candidate_tree_sha256']:raise ValueError('Candidate identity mismatch')
 checked(receipt['patch']);bundle=json.loads(checked(lock['candidate']).read_text())
 paths=list(Path(score_dir).glob('logs/run_evaluation/*/*/'+iid+'/test_output.txt'))
 if len(paths)!=1:return None
 output=paths[0];log=output.with_name('run_instance.log');official=output.with_name('report.json')
 if not log.exists() or json.loads(official.read_text()).get(iid)!=report:return None
 proof=conflict_evidence(report,log.read_text(),output.read_text(),bundle['files'])
 if not proof:return None
 return {**receipt,'status':'candidate_execution_failed','resolved':False,'classification_revision':VERSION,'raw_status':'technical_unknown','raw_official_result_retained':True,'failure_evidence':proof,'evidence_refs':{'locked_candidate':lock['candidate'],'test_output':reference(output),'run_log':reference(log),'official_report':reference(official)},'model_calls':0,'new_scoring_calls':0}
