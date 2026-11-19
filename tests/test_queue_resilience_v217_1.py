from proworksim.software_score_recovery_v217_1 import conflict_evidence,recover
from proworksim.software_queue_resilience_v217_1 import FaultRegistry
from pathlib import Path
import json

def test_candidate_failure_requires_applied_patch_and_exact_syntax_source():
 source='x = 1\n<<<<<<< working-copy\nx = 2\n=======\nx = 3\n>>>>>>> incoming-patch\n'
 report={'resolved':False,'infra_failure':False,'patch_successfully_applied':False}
 log='Applied patch sample.py cleanly.'
 output='>>>>> Start Test Output\nFile "/testbed/sample.py", line 2\nSyntaxError: invalid syntax\n>>>>> End Test Output\n>>>>> Test Exit Code: 1'
 assert conflict_evidence(report,log,output,{'sample.py':source})['line']==2
 assert conflict_evidence(report,'patch failed',output,{'sample.py':source}) is None
 assert conflict_evidence({**report,'infra_failure':True},log,output,{'sample.py':source}) is None
 assert conflict_evidence(report,log,output,{'sample.py':'x=2\n'}) is None
 assert conflict_evidence(report,log,output.replace('Test Exit Code: 1','Test Exit Code: 124'),{'sample.py':source}) is None

def test_isolation_and_repeated_common_fault_count_distinct_tasks():
 q=FaultRegistry()
 for i in range(6):assert not q.record(i,{'scoring':{'status':'technical_unknown'}})['pause_new_admissions']
 for _ in range(5):assert not q.record(10,{'type':'FatalTransport','message':'transport broken'})['pause_new_admissions']
 assert not q.record(11,{'type':'FatalTransport','message':'transport broken'})['pause_new_admissions']
 assert q.record(12,{'type':'FatalTransport','message':'transport broken'})['pause_new_admissions']
 assert not q.record(13,{'type':'ValueError','message':'candidate parse failed'})['pause_new_admissions']

def test_real_locked_sympy_candidate_is_false_without_new_scoring():
 root=Path(__file__).resolve().parents[1];score=root/'runs/software-benchmark-v217/selection28-r1/task-04/scores/KEEP/code'
 raw=json.loads((score/'receipt.json').read_text());result=recover(raw,score)
 assert raw['status']=='technical_unknown' and result['status']=='candidate_execution_failed'
 assert result['resolved'] is False and result['failure_evidence']['path']=='sympy/simplify/simplify.py'
 assert result['official_result']==raw['official_result'] and result['candidate_tree_sha256']==raw['candidate_tree_sha256']

def test_window_keeps_other_tasks_after_one_worker_raises():
 import ast,concurrent.futures
 path=Path(__file__).resolve().parents[1]/'tools/resume_project_selection_v217_1.py'
 tree=ast.parse(path.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='isolated_execute')
 faults=[]
 def execute(row):
  if row['index']==2:raise RuntimeError('One isolated preflight failure')
  return {'index':row['index'],'complete':True}
 import traceback
 ns={'execute':execute,'fault':lambda i,r:faults.append((i,r)),'traceback':traceback}
 exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(ns['isolated_execute'],[{'index':i} for i in (1,2,3)]))
 assert [r['index'] for r in results if r]==[1,3] and faults[0][0]==2
