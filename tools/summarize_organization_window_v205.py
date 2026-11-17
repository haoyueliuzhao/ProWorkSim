"""Read-only current CN window, authoritative shared ledger and exact score endpoints."""
import json,sqlite3,time
from pathlib import Path
R=Path('runs');base=R/'software-benchmark-v204';run=R/'software-benchmark-v205'
def read(p):return json.loads(p.read_text()) if p.exists() else None
with sqlite3.connect('file:'+str((base/'cn-pilot-r1/ledger.sqlite').resolve())+'?mode=ro',uri=True) as c:
 usage=[{'status':s,'requests':n,'tokens':t,'cost_upper_CNY':v/1e9} for s,n,t,v in c.execute('select status,count(*),sum(tokens),sum(cost) from requests group by status')]
result={'at':time.time(),'budget_CNY':200,'ledger':usage,'batch_paused':(base/'cn-pilot-r1/batch-pause.json').exists(),'window1_states':2,'window1_candidate_runs':6,'retired_prefix_index':3}
s=read(run/'admission-score-r1/progress.json')
result['admission_scores']={k:{z:v.get(z) for z in ('status','resolved')} for k,v in s['results'].items()} if s else None
result['prefixes']=[read(p) for p in (run/'window1-prefixes-r1').glob('*/result.json')]
result['window']=read(run/'window1-main-r1/progress.json')
result['current_episodes']=[]
for parent in (run/'w1-state-01',run/'window1-main-r1/w1-state-02'):
 for f in parent.glob('*/result.json'):
  v=read(f);p=read(f.parent/'progress.json');result['current_episodes'].append({'slot':v['slot'],'status':v['status'],'opportunities':p['opportunities'] if p else None,'tokens_with_prefix':p['usage']['known_actual_tokens'] if p else None})
result['q1']=read(base/'policies/q1.json');result['q2']=read(base/'policies/q2.json')
print(json.dumps(result,ensure_ascii=False,indent=2))
