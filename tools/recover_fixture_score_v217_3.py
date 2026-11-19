"""Three serial isolated scores; no model generation or shared-host changes."""
import json,os,subprocess,time
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,checked,read_episode_candidates
from proworksim.storage import atomic_write,json_bytes
R=Path(__file__).resolve().parents[1];OUT=R/'runs/software-benchmark-v217/fixture-recovery-r1';EP=R/'runs/software-benchmark-v217/confirmation-resume-r1/task-13/KEEP'
def read(p):return json.loads(p.read_text())
def save(p,v):atomic_write(p,json_bytes(v))
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 pair=read_episode_candidates(read(EP/'candidate-lock.json'));code=read(checked(pair['lock']['terminal_code']));delivery=read(checked(pair['lock']['last_legal_delivery']))
 assert code['tree_sha256']==delivery['tree_sha256']
 env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
 receipts={}
 for kind in ('gold','empty','code'):
  with (OUT/(kind+'.log')).open('xb') as log:
   p=subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools/score_project_relations_v217_3.py'),'--index','13','--kind',kind,'--episode',str(EP),'--output',str(OUT/kind)],cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT)
  receipt=read(OUT/kind/'receipt.json');receipts[kind]=reference(OUT/kind/'receipt.json')
  assert p.returncode==0 and receipt['status']=='official_report' and not receipt['cleanup_errors'],receipt
  if kind!='code':assert receipt['resolved']==(kind=='gold'),receipt
  save(OUT/'progress.json',{'last_closed':kind,'receipts':receipts,'at':time.time()})
 result=read(OUT/'code/receipt.json');reuse={**result,'kind':'delivery','endpoint_lock':pair['lock']['last_legal_delivery'],'reused_score':reference(OUT/'code/receipt.json'),'same_tree_proof':{'code':pair['lock']['terminal_code'],'delivery':pair['lock']['last_legal_delivery'],'tree_sha256':code['tree_sha256']},'new_scoring_calls':0}
 save(OUT/'delivery-reused.json',reuse)
 save(OUT/'canonical-overlay.json',{'index':13,'condition':'KEEP','code':reference(OUT/'code/receipt.json'),'delivery':reference(OUT/'delivery-reused.json'),'original_code':reference(R/'runs/software-benchmark-v217/streaming-r2/task-13/scores/KEEP/code-0/receipt.json'),'original_delivery':reference(R/'runs/software-benchmark-v217/streaming-r2/task-13/scores/KEEP/delivery-0/receipt.json'),'qualified':True,'controls':receipts,'model_calls':0,'scoring_containers':3,'finished':time.time()})
 print(json.dumps({'resolved':result['resolved'],'code_and_delivery_same_tree':True,'model_calls':0,'containers':3}))
if __name__=='__main__':main()
