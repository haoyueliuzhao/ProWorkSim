"""Read-only live status, distinguishing generator invalidity from no opportunity."""
import json,time,collections,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R/'runs/software-benchmark-v218/pilot8-r1'
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return None
rows=[]
for task in sorted(ROOT.glob('task-*')):
 pre=read(task/'PREFIX/result.json') or {};gen=read(task/'GENERATOR/result.json') or {};gate=read(task/'opportunity-gate.json');diag=read(task/'GENERATOR/generator-diagnostics.json') or {};bank=read(task/'GENERATOR/candidate-bank.json') or {};boundary=read(task/'PREFIX/boundary.json') or {}
 errors=[e for a in diag.get('failures',[]) for e in a['errors']]
 prep_reason=('prefix_execution_unknown' if pre.get('status')=='technical_unknown' else 'generator_output_invalid' if gate and not gate['qualified'] and errors else 'no_valid_structural_proposal_observed' if gate and not gate['qualified'] else 'qualified' if gate and gate['qualified'] else 'preparing')
 rows.append({'task':task.name,'prefix_status':pre.get('status'),'prefix_integrity_failure':boundary.get('execution_integrity_failure'),'generator_status':gen.get('status'),'candidate_count':len(bank.get('candidates',{})),'preparation_classification':prep_reason,'generator_errors':errors,'panel':read(task/'panel-result.json'),'branches':{p.parent.name:read(p).get('status') for p in task.glob('*/result.json') if p.parent.name in ('KEEP','C1','C2')}})
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
 cash=c.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE 'v218:%' GROUP BY status").fetchall();total=c.execute("SELECT COALESCE(sum(cost),0)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
print(json.dumps({'at':time.time(),'progress':read(ROOT/'progress.json'),'finished':read(ROOT/'finished.json'),'rows':rows,'classification_counts':dict(collections.Counter(x['preparation_classification'] for x in rows)),'v218_requests':cash,'shared_cash':total,'remaining':1100-total},ensure_ascii=False,indent=2))
