"""Read-only joint status. Historical prefix tokens never counted again as API spend."""
import json,sqlite3,time
from pathlib import Path
root=Path('runs/software-benchmark-v203-3-3');db=(root/'prefix80-r3/ledger.sqlite').resolve()
c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
requests=c.execute('SELECT slot,status,cost,tokens,body FROM requests').fetchall();c.close()
settled=[r for r in requests if r[1]=='settled'];b=[r for r in settled if ':continuations-'in r[0]]
q=json.loads((root/'continuations-r1/queue.json').read_text());active=[]
for r in q['active']:
 d=root/'continuations-r1'/r['run_name'];f=d/'result.json';row={'name':r['run_name'],'arm':r['arm'],'state_rank':r['state_rank']}
 if f.exists():row.update(json.loads(f.read_text()))
 p=d/'progress.json'
 if p.exists():z=json.loads(p.read_text());row.update(opportunities=z['opportunities'],cumulative_prefix_plus_continuation_tokens=z['usage']['known_actual_tokens'],last_progress=z['at'])
 active.append(row)
s=root/'scoring-r1/progress.json';score=json.loads(s.read_text()) if s.exists() else None
print(json.dumps({'observed':time.time(),'budget_CNY':80,'known_peak_cost_upper_CNY':sum(r[2] for r in settled)/1e9,
 'remaining_nominal_CNY':80-sum(r[2] for r in settled)/1e9,'actual_tokens':sum(r[3] for r in settled),'settled_requests':len(settled),
 'continuation_only_tokens':sum(r[3] for r in b),'continuation_only_settled_requests':len(b),
 'unsettled_requests':sum(r[1]=='reserved' for r in requests),'generation_status':q['status'],'first_pair_gate':q['first_pair_gate'],
 'finished':q['finished'],'active':active,'unstarted':len(q['unstarted']),
 'score_status':score['status'] if score else 'not_started','scored_episodes':len(score['episodes']) if score else 0},ensure_ascii=False,indent=2))
