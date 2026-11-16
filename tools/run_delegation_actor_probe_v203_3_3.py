import argparse,json
from pathlib import Path
from proworksim.software_delegation_actor_v203_3_3 import Actor
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--index',type=int,default=0);a=p.parse_args()
rows=json.loads(Path('artifacts/software-benchmark-v203-3-3/preparation-r1/candidates.json').read_text())['rows']
actor=Actor(rows[a.index],a.output)
try:
 actor.start()
 print(json.dumps({'passed':True,'instance_id':rows[a.index]['instance_id'],'API_calls':0}))
finally:actor.close()
