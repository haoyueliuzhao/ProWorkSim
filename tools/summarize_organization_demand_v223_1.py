"""Read-only status, paired endpoints and de-duplicated physical API accounting."""
import json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'runs/software-benchmark-v223-1/paired4-r1'
def read(p):return json.loads(p.read_text()) if p.exists() else None
def main():
 rows=[]
 for i in range(4):
  root=O/f'task-{i:02d}';prefix=read(root/'PREFIX/result.json');graph=read(root/'GRAPH/result.json')
  for z in ('W0','W1'):
   ep=read(root/z/'result.json');score=read(root/(z+'-result.json'));bank=read(root/('GEN-'+z)/'candidate-bank.json');progress=read(root/z/'progress.json')
   rows.append({'task':i,'condition':z,'prefix':prefix and prefix['status'],'graph':graph and graph['status'],'generation':ep and ep['status'],'selected':bank and bank['selected'],'score':score,'progress':{k:progress[k] for k in ('opportunities','logical_total_tokens','at')} if progress else None})
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  requests=[dict(zip(('status','requests','tokens','cost_CNY_upper'),r)) for r in c.execute('SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE "v223.1:%" GROUP BY status')]
  spent=c.execute('SELECT COALESCE(sum(cost),0)/1e9 FROM requests WHERE status="settled"').fetchone()[0]
 print(json.dumps({'rows':rows,'physical_API':requests,'shared_settled_CNY':spent,'shared_remaining_CNY':1100-spent,'finished':read(O/'finished.json'),'logical_and_physical_costs_not_interchangeable':True},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
