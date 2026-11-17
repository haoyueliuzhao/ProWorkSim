"""Read-only window2 state and sole 200-CNY ledger, no prior-budget aggregation."""
import json,sqlite3,time
from pathlib import Path
R=Path('runs');base=R/'software-benchmark-v204';root=R/'software-benchmark-v207'
def load(p):return json.loads(p.read_text()) if p.exists() else None
with sqlite3.connect('file:'+str((base/'cn-pilot-r1/ledger.sqlite').resolve())+'?mode=ro',uri=True) as c:
 usage=[{'status':s,'requests':n,'tokens':t,'cost_upper_CNY':v/1e9} for s,n,t,v in c.execute('select status,count(*),sum(tokens),sum(cost) from requests group by status')]
out={'at':time.time(),'budget_start_line_CNY':200,'ledger':usage,'window2_states':2,'window2_candidate_runs':6,'excluded_prefix_index':4,'batch_paused':(base/'cn-pilot-r1/batch-pause.json').exists(),'window':load(root/'window2-main-r1/progress.json'),'episodes':[]}
for p in (root/'window2-main-r1').glob('w2-state-*/*/result.json'):
 r=load(p);g=load(p.parent/'progress.json');out['episodes'].append({'slot':r['slot'],'status':r['status'],'opportunities':g['opportunities'] if g else None,'tokens_with_prefix':g['usage']['known_actual_tokens'] if g else None})
for name in ('q1','q2'):out[name]=load(base/'policies'/(name+'.json'))
print(json.dumps(out,ensure_ascii=False,indent=2))
