"""Compact read-only status, no request-body or full model ledger expansion."""
from pathlib import Path
import json,sqlite3,time
R=Path(__file__).resolve().parents[1];root=R/'runs/software-benchmark-v213/regression6-r1'
def load(p):return json.loads(p.read_text()) if p.exists() else {}
progress=load(root/'progress.json');episodes=[]
for task in sorted(root.glob('task-*')):
 for z in ('SINGLE','COMBO'):
  p=task/z;r=load(p/'result.json');g=load(p/'progress.json');u=g.get('usage',{})
  scores={k:{x:v.get(x) for x in ('status','resolved','error')} for k in ('code','delivery') for v in [load(task/'scores'/z/k/'receipt.json')]}
  episodes.append({'task':task.name,'condition':z,'status':r.get('status','not_started'),'started':r.get('started'),'finished':r.get('finished'),'last_progress_at':g.get('at'),'actual_tokens':u.get('known_actual_tokens'),'attempts':u.get('attempts'),'opportunities':g.get('opportunities'),'first_submission':(p/'first-submission-usage.json').exists(),'error':r.get('error'),'scores':scores})
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
 requests=[dict(zip(('status','count','tokens','CNY_upper'),r)) for r in c.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE 'v213:%' GROUP BY status")]
 paid=c.execute("SELECT sum(cost)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
print(json.dumps({'at':time.time(),'coordinator_status':progress.get('status'),'states':progress.get('states'),'episodes':episodes,'requests':requests,'shared_700_paid_CNY_upper':paid,'remaining_before_reservations_CNY':700-paid,'stage_B_gate':load(root/'stage-b-gate.json'),'B_C_started':False},ensure_ascii=False,indent=2))
