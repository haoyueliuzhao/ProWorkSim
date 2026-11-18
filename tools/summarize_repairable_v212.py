"""Read-only current stage-A progress; distinguish paid requests from completed runs."""
import json,sqlite3,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];out=R/'runs/software-benchmark-v212/stage-a6-r1'
def read(p):return json.loads(p.read_text()) if p.exists() else None
progress=read(out/'progress.json');episodes=[]
for task in sorted(out.glob('task-*')):
 for name in ('SINGLE','COMBO'):
  ep=task/name;v=read(ep/'result.json') or {'status':'not_started'};p=read(ep/'progress.json')
  episodes.append({'task':task.name,'condition':name,'status':v['status'],'error':v.get('error'),'progress':p,'first_submission':read(ep/'first-submission-usage.json'),'code':read(task/'scores'/name/'code/receipt.json'),'delivery':read(task/'scores'/name/'delivery/receipt.json')})
ledger=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
with sqlite3.connect('file:'+str(ledger)+'?mode=ro',uri=True) as c:
 rows=[dict(zip(('status','requests','tokens','cost_CNY_upper'),r)) for r in c.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE 'v212:%' GROUP BY status")]
 paid=c.execute("SELECT COALESCE(sum(cost),0)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
print(json.dumps({'at':time.time(),'coordinator':progress,'episodes':episodes,'stage_A_requests':rows,'shared_700_settled_CNY_upper':paid,'remaining_before_pending_reservations_CNY':700-paid,'stage_B_gate':read(out/'stage-b-gate.json'),'B_C_started':False},ensure_ascii=False,indent=2))
