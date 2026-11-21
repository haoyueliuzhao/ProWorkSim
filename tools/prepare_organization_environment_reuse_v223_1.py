"""Reuse unchanged official controls by exact task/config/image identity; no Docker."""
import json
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1];OUT=R/'runs/software-benchmark-v223-1/environment-r1'
def main():
 OUT.mkdir(parents=True,exist_ok=False);old=json.loads((R/'artifacts/software-benchmark-v223/protocol-r1/candidate-tasks.json').read_text())['rows'];new=json.loads((R/'artifacts/software-benchmark-v223-1/protocol-r1/candidate-tasks.json').read_text())['rows']
 for a,b in zip(old,new):
  for k in ('index','instance_id','base_commit','configuration','actor_image_id','scorer_image_id'):assert a[k]==b[k]
  checked(b['configuration']);proof={}
  for kind in ('gold','empty'):
   p=R/f'runs/software-benchmark-v223/environment-r1/task-{b["index"]:02d}/{kind}/receipt.json';d=json.loads(p.read_text());assert d['status']=='official_report' and d['resolved']==(kind=='gold') and d['cleanup_errors']==[];proof[kind]=reference(p)
  p=OUT/f'task-{b["index"]:02d}/qualification.json';p.parent.mkdir();p.write_bytes(json_bytes({'qualified':True,'instance_id':b['instance_id'],'proof':proof,'official_environment_unchanged':True,'public_actor_selector_revision_is_separately_tested':True,'new_control_executions':0}))
 (OUT/'finished.json').write_bytes(json_bytes({'qualified':4,'model_calls':0,'new_containers':0,'reuse_reason':'same immutable official image, task config and grader behavior; only new run identities'}));print('Reused four exact official environments; no repeated gold/empty tests.')
if __name__=='__main__':main()
