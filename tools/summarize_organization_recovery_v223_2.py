"""Read-only canonical overlay; keep original unknown and new recovery visible."""
import json,sqlite3
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import checked
R=Path(__file__).resolve().parents[1];OLD=R/'runs/software-benchmark-v223-1/paired4-r1';NEW=R/'runs/software-benchmark-v223-2/recovery-r1'
def read(p):return json.loads(p.read_text()) if p.exists() else None
def main():
 results=dict(read(OLD/'finished.json')['results']);overlay=read(NEW/'canonical-overlay.json')
 if overlay:
  assert overlay['replaces_only']=='3:W0';results['3:W0']=read(checked(overlay['result']))
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  rows=list(c.execute('SELECT slot,status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE "v223.2:%" GROUP BY slot,status'));spent=c.execute('SELECT sum(cost)/1e9 FROM requests WHERE status="settled"').fetchone()[0]
 print(json.dumps({'original_qualified_task_count':2,'results':results,'recovery':read(NEW/'finished.json') or read(NEW/'progress.json'),'new_physical_requests':rows,'shared_spent_CNY':spent,'shared_remaining_CNY':1100-spent,'old_error_remains_in_original_files':True},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
