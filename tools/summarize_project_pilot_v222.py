"""Read-only current v222 status; model requests are not completed tasks."""
import json,sqlite3,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];OUT=R/'runs/software-benchmark-v222/paired4-r1'
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return None
p=read(OUT/'progress.json');rows=[]
for task in sorted(OUT.glob('task-*')):
 row={'task':task.name,'prefix':(read(task/'PREFIX/result.json') or {}).get('status')}
 for z in ('L','G'):
  row[z]={'generator':(read(task/('GEN-'+z)/'result.json') or {}).get('status'),'generation':(read(task/z/'result.json') or {}).get('status'),'result':read(task/(z+'-result.json'))}
 rows.append(row)
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
 usage=[dict(zip(('status','requests','tokens','cost_CNY_upper'),r)) for r in c.execute('SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE "v222:%" GROUP BY status')]
 paid=c.execute('SELECT COALESCE(sum(cost),0)/1e9 FROM requests WHERE status="settled"').fetchone()[0]
print(json.dumps({'at':time.time(),'progress':p,'rows':rows,'actual_API':usage,'cumulative_CNY_upper':paid,'remaining_CNY':1100-paid,'planned_pairs':4,'planned_branches':8,'finished':read(OUT/'finished.json')},ensure_ascii=False,indent=2))
