"""Current CN pilot state, no old money and no synthetic scores in learned q."""
import json,sqlite3,time
from pathlib import Path
root=Path('runs/software-benchmark-v204');db=(root/'cn-pilot-r1/ledger.sqlite').resolve()
result={'at':time.time(),'independent_budget_CNY':200,'real_updates_completed':0,'training':False,'old_v20333_six_retired':True}
if db.exists():
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
  result['request_statuses']=[{'status':s,'count':n,'cost_upper_CNY':cost/1e9,'tokens':t} for s,n,cost,t in c.execute('select status,count(*),sum(cost),sum(tokens) from requests group by status')]
for name,path in [('prefix',root/'admission-r1/prefix-00/result.json'),('pair',root/'admission-pair-r1/progress.json'),('real_pair_gate',root/'admission-feedback-gate.json')]:
 if path.exists():result[name]=json.loads(path.read_text())
result['pair_children']=[json.loads(p.read_text()) for p in (root/'admission-pair-r1').glob('*/result.json')]
for name in ('q1','q2'):
 f=root/'policies'/(name+'.json')
 if f.exists():result[name]=json.loads(f.read_text());result['real_updates_completed']+=1
print(json.dumps(result,ensure_ascii=False,indent=2))
