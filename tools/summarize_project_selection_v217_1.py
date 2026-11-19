"""Read-only compact progress, no ledger mutation or model calls."""
import json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1];root=R/'runs/software-benchmark-v217/confirmation-resume-r1'
def read(p):return json.loads(p.read_text()) if p.exists() else {}
p=read(root/'progress.json');eps=[]
for f in sorted([*root.glob('task-*/*/result.json'),*(R/'runs/software-benchmark-v217/selection28-r1').glob('task-*/*/result.json')]):
 d=read(f);g=read(f.parent/'progress.json');eps.append({'task':f.parent.parent.name,'stage':f.parent.name,'status':d.get('status'),'logical_tokens':g.get('logical_total_tokens'),'error':d.get('error')})
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
 usage=[dict(zip(('status','count','tokens','CNY_upper'),r)) for r in c.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE 'v217:%' GROUP BY status")]
print(json.dumps({'progress':p,'episodes':eps,'physical':usage,'finished':read(root/'finished.json')},ensure_ascii=False,indent=2))
