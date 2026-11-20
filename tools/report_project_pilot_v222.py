"""Read-only paired outcomes, actual usage and provenance review; no self-made gold."""
import collections,json,sqlite3,time
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1];B=R/'runs/software-benchmark-v222/paired4-r1';P=R/'artifacts/software-benchmark-v222/protocol-r1';O=R/'artifacts/software-benchmark-v222/results-r1'
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return None

def provenance_review(context,source,events,decision):
 rows=[];byseq={e['sequence']:e for e in events}
 for r in context['project_relations']['relations']:
  verdict='unknown';scope='relation_truth';reason='Requires semantic or independent relevance review'
  if r['kind']=='ledger_work_state':
   w=decision['graph']['work'].get(r['source']);verdict='correct' if w and r['target']==w['owner'] else 'incorrect';scope='recorded_owner_only';reason='Compared to original authoritative work ledger, not graph output'
  elif r['evidence_level']=='E1' and r.get('source_event') in byseq:
   e=byseq[r['source_event']];scope='event_reference_and_version_only'
   version=e.get('source_reference') or e.get('identity',{}).get('source_reference')
   verdict='correct' if not r.get('version') or r['version']==version else 'unknown';reason='Exact source event exists; semantic relation necessity remains unverified'
   if r['kind']=='work_observed_region':verdict='correct' if e['kind']=='read' and e.get('path')==r['target'] and r['version']==version else 'incorrect'
   if r['kind']=='test_version':verdict='correct' if e['kind']=='test' and r['target']==e['actor_id'] and all(r['details'].get(k)==e.get(k) for k in ('executed','passed')) and r['version']==version else 'incorrect'
  elif r['evidence_level']=='E2':
   d=r['details'];text=source['files'].get(r['source']);scope='static_syntax_only'
   if text is not None and r['version']==source['source_reference']:
    import ast
    try:
     tree=ast.parse(text)
     if d['kind']=='static_import':ok=any(isinstance(n,(ast.Import,ast.ImportFrom)) and n.lineno==d['line'] for n in ast.walk(tree)) and r['target'] in source['files']
     else:ok=all(any(n.lineno==line and ((isinstance(n,ast.Name) and n.id==name) or (isinstance(n,ast.Attribute) and n.attr==name)) for n in ast.walk(tree) if hasattr(n,'lineno')) for name,line in d.get('matches',[]))
     verdict='correct' if ok else 'incorrect';reason='Independent AST reparse of bound raw public source; no runtime dependency claim'
    except (SyntaxError,ValueError,RecursionError):reason='Raw syntax cannot be reparsed'
  rows.append({'id':r['id'],'level':r['evidence_level'],'scope':scope,'verdict':verdict,'reason':reason,'necessary_dependency':'unknown'})
 counts=collections.Counter(x['verdict'] for x in rows)
 return {'relations':rows,'provenance_scope_counts':dict(counts),'provenance_precision':counts['correct']/(counts['correct']+counts['incorrect']) if counts['correct']+counts['incorrect'] else None,'semantic_P_edge':None,'necessary_R_edge':None,'why_not_semantic_metrics':'Provenance and syntax checks are not independent necessary-dependency gold','reviewer':'deterministic source checks; AI semantic review pending, no human blind review'}

def main():
 O.mkdir(parents=True,exist_ok=True);plan=read(P/'candidate-tasks.json');results=[]
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  requests=c.execute('SELECT slot,status,tokens,cost,body FROM requests WHERE slot LIKE "v222:%"').fetchall()
 def usage(slot):
  rr=[r for r in requests if r[0]==slot];u={'requests':len(rr),'settled':0,'input_tokens':0,'output_tokens':0,'total_tokens':0,'CNY_peak_upper':0.,'unsettled_requests':0}
  for _,status,tokens,cost,body in rr:
   if status!='settled':u['unsettled_requests']+=status!='http_error';continue
   d=json.loads(body);u['settled']+=1;u['total_tokens']+=tokens;u['CNY_peak_upper']+=cost/1e9
   u['input_tokens']+=d.get('prompt_tokens',d.get('input_tokens',0));u['output_tokens']+=d.get('completion_tokens',d.get('output_tokens',0))
  assert u['input_tokens']+u['output_tokens']==u['total_tokens']
  return u
 for row in plan['rows']:
  task=B/f'task-{row["index"]:02d}';base='v222:'+task.name+':'
  prefix=usage(base+'PREFIX');decision=read(task/'PREFIX/decision-state.json');source=read(task/'PREFIX/generator-authorized-source.json');prefixworld=read(task/'PREFIX/final-world.json')
  pair={'instance_id':row['instance_id'],'repo':row['repo'],'prefix':prefix,'conditions':{}}
  for z in ('L','G'):
   ep=task/z;gen=task/('GEN-'+z);bank=read(gen/'candidate-bank.json');diag=read(gen/'generator-diagnostics.json');context=read(gen/'condition-state.json');world=read(ep/'final-world.json');g=usage(base+'GEN-'+z);s=usage(base+z)
   x={'generator':g,'continuation':s,'logical_total_tokens':prefix['total_tokens']+g['total_tokens']+s['total_tokens'],'logical_CNY_peak_upper':prefix['CNY_peak_upper']+g['CNY_peak_upper']+s['CNY_peak_upper'],'generation':read(ep/'result.json'),'outcome':read(task/(z+'-result.json')),'selected':bank.get('selected') if bank else None,'candidate_diagnostics':diag,'information_audit':read(gen/'information-audit.json'),'component_estimates':read(gen/'input-component-estimates.json')}
   if context and source and prefixworld:
    x['relation_review']=provenance_review(context,source,prefixworld['software_events'],decision)
   if world:
    events=world['software_events'];start=max((e['sequence'] for e in (prefixworld or {}).get('software_events',[])),default=0);new=[e for e in events if e['sequence']>start];x['continuation_event_counts']=dict(collections.Counter(e['kind'] for e in new));x['navigation_cost_events']=[e for e in new if e['kind']=='navigation_v222:located']
   pair['conditions'][z]=x
  pair['complete_pair']=all(x.get('outcome',{} ) and x['outcome']['status']=='scored' for x in pair['conditions'].values());results.append(pair)
 totals={'actual_physical_tokens':sum(r[2] for r in requests if r[1]=='settled'),'actual_physical_cost_peak_upper':sum(r[3] for r in requests if r[1]=='settled')/1e9,'settled_requests':sum(r[1]=='settled' for r in requests),'unknown_or_inflight_requests':sum(r[1] not in ('settled','http_error') for r in requests)}
 summary={'version':'v222-paired-evidence-report-r1','at':time.time(),'complete_pairs':sum(r['complete_pair'] for r in results),'planned_pairs':4,'planned_branches':8,'totals':totals,'rows':results,'C_N_updates':0,'shared_prefix_paid_once':True,'logical_prefix_counted_in_each_arm':True,'P_edge_semantics_pending':True,'R_edge_reference_pending':True}
 (O/'summary.json').write_bytes(json_bytes(summary));print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False))
if __name__=='__main__':main()
