"""Read-only status; charges from actual provider settlements, never holds."""
import argparse,json,sqlite3,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('runs/software-benchmark-v203-3-3/prefix80-r3'));a=p.parse_args()
r=a.root.resolve();db=r/'ledger.sqlite';out={'root':str(r),'observed':time.time(),'cash_cap_CNY':80,'real_model_requests':0,'actual_tokens':0,'peak_cost_upper_CNY':0,'cash_unknown_requests':0,'episodes':[]}
if db.exists():
 c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
 out['real_model_requests']=c.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
 out['cash_unknown_requests']=c.execute('SELECT COUNT(*) FROM requests WHERE status="reserved"').fetchone()[0]
 out['actual_tokens'],cost=c.execute('SELECT COALESCE(SUM(tokens),0),COALESCE(SUM(cost),0) FROM requests WHERE status="settled"').fetchone();out['peak_cost_upper_CNY']=cost/1e9;c.close()
for d in sorted(r.glob('prefix-*')):
 if not d.is_dir():continue
 f=d/'result.json'
 if not f.exists():continue
 v=json.loads(f.read_text());row={k:v.get(k) for k in ('slot','instance_id','status','error_type','error')}
 if (d/'progress.json').exists():
  z=json.loads((d/'progress.json').read_text());row.update(opportunities=z['opportunities'],last_progress_at=z['at'])
 out['episodes'].append(row)
print(json.dumps(out,ensure_ascii=False,indent=2))
