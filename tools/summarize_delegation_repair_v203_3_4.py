"""Read-only joined ledger and old/new continuation services, no duplicate slots."""
import json,sqlite3,time
from pathlib import Path
root=Path('runs');db=(root/'software-benchmark-v203-3-3/prefix80-r3/ledger.sqlite').resolve()
with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
 req=c.execute('SELECT slot,status,cost,tokens FROM requests').fetchall()
 queues=[]
 for version in ('v203-3-3','v203-3-4'):
  d=root/f'software-benchmark-{version}/continuations-r1';f=d/'queue.json'
  if not f.exists():continue
  q=json.loads(f.read_text());active=[]
  for r in q['active']:
   folder=d/r['run_name'];v=json.loads((folder/'result.json').read_text()) if (folder/'result.json').exists() else {'status':'starting'}
   p=folder/'progress.json';progress=json.loads(p.read_text()) if p.exists() else {}
   active.append({'run':r['run_name'],'arm':r['arm'],'status':v['status'],'opportunities':progress.get('opportunities'),
    'cumulative_prefix_plus_branch_tokens':progress.get('usage',{}).get('known_actual_tokens'),'last_progress':progress.get('at')})
  sf=d.parent/'scoring-r1/progress.json';score=json.loads(sf.read_text()) if sf.exists() else {}
  queues.append({'version':version,'status':q['status'],'gate':q['first_pair_gate'],'active':active,'finished':q['finished'],
   'unstarted':len(q['unstarted']) if version=='v203-3-4' else '14 identities handed to v203.3.4; do not add again',
   'score_status':score.get('status'),'endpoint_rows':len(score.get('episodes',{}))})
 settled=[r for r in req if r[1]=='settled'];slots=c.execute('SELECT id,status,hold FROM slots').fetchall()
 outstanding=[r for r in req if r[1]=='reserved'];state={x[0]:x[1] for x in slots}
 known=sum(r[2] for r in settled)/1e9
 print(json.dumps({'at':time.time(),'nominal_budget_CNY':80,'known_peak_cost_upper_CNY':known,'nominal_remaining_CNY':80-known,
  'actual_tokens':sum(r[3] for r in settled),'settled_requests':len(settled),
  'inflight_requests':sum(state[r[0]]=='active' for r in outstanding),'uncertain_requests':sum(state[r[0]]!='active' for r in outstanding),
  'planned_original_continuations':16,'additional_model_attempts':0,'queues':queues},ensure_ascii=False,indent=2))
