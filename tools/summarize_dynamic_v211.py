"""Read-only status for the dynamic organization mechanism batch."""
from pathlib import Path
import json,sqlite3,time
R=Path(__file__).resolve().parents[1];root=R/'runs/software-benchmark-v211/mechanism18-r1';p=root/'progress.json';progress=json.loads(p.read_text()) if p.exists() else {}
out={'at':time.time(),'batch':'v211 dynamic mechanism','status':progress.get('status','not_started'),'states':progress.get('states',{}),'episodes':[],'budget_CNY':700,'stage_estimated_start_line_CNY':220,'CN_learning_started':False}
for f in sorted(root.glob('task-*/O*/result.json')):
 d=json.loads(f.read_text());g=f.parent/'progress.json';g=json.loads(g.read_text()) if g.exists() else {}
 out['episodes'].append({'slot':d['slot'],'instance_id':d['instance_id'],'condition':d['condition'],'status':d['status'],'tokens':g.get('usage',{}).get('known_actual_tokens'),'opportunities':g.get('opportunities'),'error':d.get('error')})
l=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
if l.exists():
 with sqlite3.connect('file:'+str(l)+'?mode=ro',uri=True) as c:
  out['ledger']=[{'status':s,'requests':n,'tokens':t,'cost_or_reservation_CNY':v/1e9} for s,n,t,v in c.execute('select status,count(*),coalesce(sum(tokens),0),coalesce(sum(cost),0) from requests group by status')]
print(json.dumps(out,ensure_ascii=False,indent=2))
