"""Public historical regression evidence, no model or repository test execution."""
import json,hashlib,copy,time
from pathlib import Path
from proworksim.software_project_navigation_v223_1 import RepositoryIndex
from proworksim.software_public_feedback_v223_1 import compact
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/software-benchmark-v223-1/preparation-r1'
def save(name,v):(OUT/name).write_bytes(json_bytes(v))
def main():
 OUT.mkdir(parents=True,exist_ok=True);treepath=R/'runs/software-benchmark-v223/paired4-r1/task-01/PREFIX/actor/initial-tree.json';tree=json.loads(treepath.read_text());index=RepositoryIndex('member_001');start=time.monotonic();index.update(tree['files'],{'version_id':'original-v223-public-baseline'},tree['entry_metadata']);navigation=[]
 for query in ('Contains as_set class Contains','Contains class definition as_set as_relational'):
  result=index.query(query,use_graph=True);assert result['hits'][0]['path']=='sympy/sets/contains.py';navigation.append({'query':query,'hits':[(h['path'],h['symbol']) for h in result['hits']]})
 save('navigation-replay.json',{'passed':True,'source':reference(treepath),'queries':navigation,'seconds':time.monotonic()-start,'model_calls':0,'scores_or_reference_fix_used':False});del tree,index
 worldpath=R/'runs/software-benchmark-v223/paired4-r1/task-02/W0/final-world.json';doc=json.loads(worldpath.read_text());reports=doc['projects']['SOFTWARE27']['software']['test_reports'];bound=json.loads((worldpath.parent/'boundary.json').read_text());comparisons=[]
 for outcome in bound['outcomes']:
  if outcome.get('decision',{}).get('action')!='run_tests' or not outcome.get('response',{}).get('ok'):continue
  page=outcome['response']['result'];report=reports[page['report_id']];before=hashlib.sha256(json_bytes(report)).hexdigest();after=compact(report,page,outcome['worker_id']);assert hashlib.sha256(json_bytes(report)).hexdigest()==before
  assert after['counts']==page['counts'] and after['passed']==page['passed'] and after['source_reference']==page['source_reference'];assert after['diagnostic_summary']['failed_tests'] and after['diagnostic_summary']['excerpts']
  comparisons.append({'report_id':page['report_id'],'old_feedback_chars':len(json.dumps(page,ensure_ascii=False)),'new_feedback_chars':len(json.dumps(after,ensure_ascii=False)),'failed_ids':[x['nodeid'] for x in after['diagnostic_summary']['failed_tests']],'same_counts_status_source_and_body':True})
 assert len(comparisons)==5
 save('feedback-replay.json',{'passed':True,'source':reference(worldpath),'reports':comparisons,'raw_body_mutations':0,'test_executions':0,'API_calls':0,'characters_not_provider_token_savings':True})
 print(json.dumps({'navigation_passed':True,'five_failed_reports_passed':True,'old_chars':sum(x['old_feedback_chars'] for x in comparisons),'new_chars':sum(x['new_feedback_chars'] for x in comparisons)}))
if __name__=='__main__':main()
