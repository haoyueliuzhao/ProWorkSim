"""Only new-task image checks and isolated official gold/empty controls, no API."""
import json,subprocess,concurrent.futures,os,time
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
R=Path(__file__).resolve().parents[1];OUT=R/'runs/software-benchmark-v224/environment-r1';OUT.mkdir(parents=True,exist_ok=False)
rows=json.loads((R/'artifacts/software-benchmark-v224/protocol-r1/candidate-tasks.json').read_text())['rows']
env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
import docker
cfg=json.loads(checked(rows[0]['configuration']).read_text());client=docker.DockerClient(base_url='unix://'+cfg['scorer_request_base']['docker_socket'],timeout=120)
def save(p,v):atomic_write(p,json_bytes(v))
valid=[]
for row in rows:
 folder=OUT/f'task-{row["index"]:02d}';folder.mkdir()
 try:
  for iid in (row['actor_image_id'],row['scorer_image_id']):assert client.images.get(iid).id==iid
  valid.append(row);save(folder/'images.json',{'present':True,'actor':row['actor_image_id'],'scorer':row['scorer_image_id']})
 except Exception as e:save(folder/'qualification.json',{'qualified':False,'reason':'image_unavailable','error':str(e)})
client.close()
def score(item):
 row,kind=item;folder=OUT/f'task-{row["index"]:02d}'/kind
 with folder.with_suffix('.log').open('xb') as log:
  rc=subprocess.run([str(R/'.venv/bin/python'),str(R/'tools/run_offline_scorer_v096.py'),str(R/'tools/score_mapping_v224.py'),'--index',str(row['index']),'--kind',kind,'--output',str(folder)],cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
 return row['index'],kind,rc
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for i,k,rc in pool.map(score,[(r,k) for r in valid for k in ('gold','empty')]):save(OUT/f'task-{i:02d}'/(k+'-exit.json'),{'exit':rc})
for r in valid:
 p=OUT/f'task-{r["index"]:02d}';proof={};qualified=True
 for k in ('gold','empty'):
  f=p/k/'receipt.json';v=json.loads(f.read_text()) if f.exists() else {};qualified&=v.get('status')=='official_report' and v.get('resolved')==(k=='gold')
  if f.exists():proof[k]=reference(f)
 save(p/'qualification.json',{'qualified':qualified,'proof':proof,'instance_id':r['instance_id']})
save(OUT/'finished.json',{'finished':time.time(),'qualified':sum(json.loads(p.read_text())['qualified'] for p in OUT.glob('task-*/qualification.json')),'model_calls':0})
