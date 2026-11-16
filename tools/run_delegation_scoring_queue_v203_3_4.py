"""Single-lane asynchronous scoring, original candidates only; failures don't block queue."""
import argparse,json,os,subprocess,time
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
ROOT=Path(__file__).resolve().parents[1]
def save(p,v):atomic_write(p,json_bytes(v))
def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);generation=a.generation.resolve()
 plan=json.loads(a.plan.read_text());rows=plan['rows'];done={};qual={}
 env={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD'}}
 def score(index,kind,target,episode=None):
  argv=[str(ROOT/'.venv/bin/python'),str(ROOT/'tools/run_offline_scorer_v096.py'),str(ROOT/'tools/score_delegation_candidate_v203_3_3_r2.py'),
   '--output',str(target),'--index',str(index),'--kind',kind]
  if episode:argv+=['--episode',str(episode)]
  with target.with_suffix('.log').open('xb') as log:
   p=subprocess.run(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
  f=target/'receipt.json'
  if f.exists():return json.loads(f.read_text())
  return {'status':'technical_unknown','resolved':None,'error':'score process exit '+str(p.returncode)}
 def progress(status):save(out/'progress.json',{'status':status,'at':time.time(),'qualifications':qual,'episodes':done,'generation_root':str(generation)})
 prior=json.loads(a.qualification_source.read_text())
 for state in plan['selected']:
  key=str(state['candidate_index']);q=prior['qualifications'][key]
  if q['passed'] is not True:raise ValueError('Cannot reuse an unqualified original scorer')
  qual[key]=q
 progress('unchanged_scoring_qualification_reused')
 while True:
  old=json.loads(a.predecessor_score.read_text())
  if old['status']=='closed_with_unstarted_or_unknown_preserved':break
  progress('waiting_predecessor_score_lane');time.sleep(20)
 while True:
  for row in rows:
   name=row['run_name'];folder=generation/name;result=folder/'result.json'
   if name in done or not result.exists():continue
   try:v=json.loads(result.read_text())
   except json.JSONDecodeError:continue
   if v['status'] in ('preparing','running'):continue
   if v['status']!='closed' or not (folder/'candidate-lock.json').exists():
    done[name]={'status':'generation_unknown_no_normal_score','generation_status':v['status'],'error':v.get('error')};progress('waiting_and_scoring');continue
   i=row['candidate_index']
   if not qual[str(i)]['passed']:
    done[name]={'status':'scoring_environment_unknown','resolved':None,'original_candidate_retained':True};continue
   target=out/name;target.mkdir()
   code=score(i,'code',target/'code',folder)
   from proworksim.software_benchmark_candidates_v054 import checked
   lock_ref=json.loads((folder/'candidate-lock.json').read_text());lock=json.loads(checked(lock_ref).read_bytes())
   if lock['last_legal_delivery'] is None:
    delivery={'status':'no_legal_delivery','resolved':False,'model_calls':0,'scoring_calls':0}
   elif lock['same_tree'] is True and code['status']=='official_report':
    terminal=json.loads(checked(lock['terminal_code']).read_bytes());submitted=json.loads(checked(lock['last_legal_delivery']).read_bytes())
    if terminal['tree_sha256']!=submitted['tree_sha256']:raise ValueError('Invalid same-tree reuse')
    delivery={'status':'same_locked_tree_score_reuse','resolved':code['resolved'],'source':str(target/'code/receipt.json'),'submitted_lock':lock['last_legal_delivery'],'tree_sha256':submitted['tree_sha256'],'scoring_calls':0}
   else:delivery=score(i,'delivery',target/'delivery',folder)
   done[name]={'status':'scored' if code['status']=='official_report' and delivery.get('resolved') is not None else 'scoring_unknown',
    'arm':row['arm'],'repeat':row['repeat'],'state_rank':row['state_rank'],'code':code,'delivery':delivery}
   save(target/'summary.json',done[name]);progress('waiting_and_scoring')
  queue=generation/'queue.json'
  try:q=json.loads(queue.read_text())
  except (FileNotFoundError,json.JSONDecodeError):q={'status':'running'}
  if q['status']!='running' and all(x['run_name'] in done for x in q.get('finished',[])):
   progress('closed_with_unstarted_or_unknown_preserved');break
  progress('waiting_and_scoring');time.sleep(20)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--generation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--qualification-source',type=Path,required=True);p.add_argument('--predecessor-score',type=Path,required=True);main(p.parse_args())
