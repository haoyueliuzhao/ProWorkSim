"""Compact, read-only physical vs logical progress for the real-state pilot."""
import json,sqlite3,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];root=R/'runs/software-benchmark-v216/targeted-closure4-r1'
def read(p):return json.loads(p.read_text()) if p.exists() else {}
progress=read(root/'progress.json');episodes=[]
for t in sorted(root.glob('r3-task-*')):
 for z in ('KEEP','ADAPT'):
  p=t/z;reused=read(t/'reused-prefix.json') if z=='PREFIX' else {}
  if reused:p=Path(reused['source']['path']).parent.parent
  r=read(p/'result.json');g=read(p/'progress.json');u=g.get('usage',{});row={'task':t.name,'stage':z,'status':'reused_frozen_checkpoint' if reused else r.get('status','not_started'),'actual_native_tokens':u.get('known_actual_tokens',r.get('actual_tokens')),'logical_tokens':g.get('logical_total_tokens'),'timing':g.get('timing'),'started':r.get('started'),'finished':r.get('finished'),'error':r.get('error'),'terminal':g.get('lifecycle',{}).get('terminal'),'choice':g.get('lifecycle',{}).get('choice')}
  if z in ('KEEP','ADAPT'):row['scores']={k:{x:v.get(x) for x in ('status','resolved','error')} for k in ('code','delivery') for v in [read(t/'scores'/z/k/'receipt.json')]}
  episodes.append(row)
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
 requests=[dict(zip(('status','requests','tokens','cost_CNY_upper'),r)) for r in c.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE 'v216:r3-%' GROUP BY status")]
 spent=c.execute("SELECT COALESCE(sum(cost),0)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
print(json.dumps({'at':time.time(),'coordinator_status':progress.get('status'),'states':progress.get('states'),'episodes':episodes,'physical_requests':requests,'shared700_settled_CNY_upper':spent,'remaining_before_unsettled_reservations_CNY':700-spent,'gate':read(root/'stage-b-gate.json'),'C_N_real_updates':0,'B_C_started':False},ensure_ascii=False,indent=2))
