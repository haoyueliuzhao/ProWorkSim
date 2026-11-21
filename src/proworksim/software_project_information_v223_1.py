"""L/G information boundary and typed sources; never authoritative organization state."""
import copy,hashlib,json,time,sys
from .software_project_relations_v223_1 import Projection,synchronize,identity
from .software_project_navigation_v223_1 import RepositoryIndex
VERSION='v223.1-typed-source-units-and-exact-navigation-r1'
def estimated_object_bytes(value,seen=None):
 seen=set() if seen is None else seen
 if id(value) in seen:return 0
 seen.add(id(value));n=sys.getsizeof(value)
 if isinstance(value,dict):n+=sum(estimated_object_bytes(k,seen)+estimated_object_bytes(v,seen) for k,v in value.items())
 elif isinstance(value,(list,tuple,set)):n+=sum(estimated_object_bytes(v,seen) for v in value)
 return n
def ledger_relations(state,actor='member_001'):
 rows=[]
 for tid,w in state['graph']['work'].items():
  rows.append({'id':identity(['ledger',tid,w]),'kind':'ledger_work_state','source':tid,'target':w['owner'],'source_event':None,'fact_status':'observed','evidence_level':'E1','version':None,'visible_to':actor,'details':{'owner':w['owner'],'reviewer':w['reviewer'],'scope':w['scope'],'authors':w['authors'],'mode':w.get('mode','implementation'),'completion':w.get('completion'),'depends_on':w.get('depends_on',[])}})
 return rows

def type_relations(graph):
 doc=copy.deepcopy(graph)
 for r in doc['relations']:
  if r.get('visible_to')!=doc['actor']:raise ValueError('Foreign private relation')
  r['evidence_level']='E3' if r.get('fact_status')=='member_claim' or r['kind'] in ('work_requires_claim','requirement_work','member_statement') else 'E1'
  r['semantic_dependency_proven']=False
 return doc

def prepare_context(state,condition,*,files,source_reference,entry_metadata,public_query,actor='member_001'):
 if condition not in ('L','G'):raise ValueError('Frozen L/G condition required')
 public=copy.deepcopy(state);public.pop('project_relations',None)
 # Ordinary work/receipt state is common; no privately observed partner material.
 graph={'actor':actor,'relations':ledger_relations(state,actor),'graph_id':None}
 started=time.perf_counter();index=RepositoryIndex(actor);stats=index.update(files,source_reference,entry_metadata=entry_metadata);cold_seconds=time.perf_counter()-started
 base_graph=type_relations(state['project_relations'])
 nav=index.query(public_query,project=base_graph,limit=8,max_chars=8000,use_graph=condition=='G')
 if condition=='G':
  graph['relations']+=base_graph['relations']
  for hit in nav['hits']:
   # Bind static file/symbol evidence to public scopes through an explicitly
   # uncertain hypothesis; static syntax itself is E2, scope assignment is E3.
   for reason in hit['reason']:
    if reason['kind'] not in ('static_import','name_reference_candidate'):continue
    target=reason.get('target') or 'unresolved-symbol-names:'+','.join(str(x[0]) for x in reason.get('matches',[]))
    r={'kind':'static_navigation_relation','source':reason.get('source',hit['path']),'target':target,'source_event':None,'version':source_reference,'fact_status':'static_candidate','evidence_level':'E2','visible_to':actor,'details':reason,'semantic_dependency_proven':False};r['id']=identity(r);graph['relations'].append(r)
  # Associate potentially relevant regions with work via observed source only;
  # no fabricated engineering dependency or automatic ownership change.
 graph['graph_id']=identity(graph)
 public['project_relations']=graph
 public['navigation']=nav
 return public,{'index_stats':stats,'cold_seconds':cold_seconds,'estimated_index_object_bytes':estimated_object_bytes(vars(index)),'memory_measurement':'Python recursive object estimate, not process RSS','navigation':nav,'relations_by_level':{k:sum(r['evidence_level']==k for r in graph['relations']) for k in ('E1','E2','E3')},'context_sha256':identity(public),'condition':condition,'hidden_source_used':False}
