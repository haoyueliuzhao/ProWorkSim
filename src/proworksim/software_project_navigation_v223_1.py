"""Versioned, actor-local repository navigation; lexical discovery never graph-gated.

Consumes authorized in-memory file snapshots only. AST is parsed, never imported
or executed. Reference edges are static candidates, not runtime call evidence.
"""
from __future__ import annotations
import ast,collections,hashlib,json,math,re,warnings
from pathlib import PurePosixPath
VERSION='v223.1-exact-definitions-plus-project-navigation-r1'
STOP={'the','and','for','with','that','this','from','into','when','then','return','none','true','false','self','def','class','import','test','tests'}
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def terms(s):
 s=re.sub(r'([a-z0-9])([A-Z])',r'\1 \2',s)
 return [t.lower() for t in re.findall(r'[A-Za-z][A-Za-z0-9]*',s) if len(t)>1 and t.lower() not in STOP]
def safe_path(path):
 p=PurePosixPath(path)
 return bool(path and len(path)<=1024 and not p.is_absolute() and '..' not in p.parts and '\\' not in path and '\x00' not in path and str(p)==path)
class Symbols(ast.NodeVisitor):
 def __init__(self):self.stack=[];self.rows=[];self.imports=[];self.references=[]
 def definition(self,node):
  name='.'.join([*self.stack,node.name]);self.rows.append({'symbol':name,'line':node.lineno,'end_line':getattr(node,'end_lineno',node.lineno),'kind':'class' if isinstance(node,ast.ClassDef) else 'function'})
  self.stack.append(node.name);self.generic_visit(node);self.stack.pop()
 visit_ClassDef=definition;visit_FunctionDef=definition;visit_AsyncFunctionDef=definition
 def visit_Import(self,node):
  self.imports += [{'module':n.name,'level':0,'line':node.lineno} for n in node.names]
 def visit_ImportFrom(self,node):
  self.imports.append({'module':node.module or '', 'level':node.level,'line':node.lineno})
 def visit_Name(self,node):
  if isinstance(node.ctx,ast.Load):self.references.append((node.id,node.lineno))
 def visit_Attribute(self,node):
  self.references.append((node.attr,node.lineno));self.generic_visit(node)
class RepositoryIndex:
 def __init__(self,actor,*,file_char_limit=500_000,total_char_limit=64_000_000,max_files=10000):
  self.actor=actor;self.rows={};self.file_char_limit=file_char_limit;self.total_char_limit=total_char_limit;self.max_files=max_files;self.reference=None;self.stats={};self.edges=[]
 def update(self,files,reference,entry_metadata=None):
  parsed=0;reused=0;skipped=[];new={};size=0
  for path,text in sorted(files.items()):
   meta=(entry_metadata or {}).get(path,{})
   if meta.get('encoding','utf-8')!='utf-8' or meta.get('kind','file')!='file':skipped.append({'path':path,'reason':'non_text_or_non_regular_entry'});continue
   if not safe_path(path) or not isinstance(text,str):skipped.append({'path':path,'reason':'not_safe_text_path'});continue
   if len(new)>=self.max_files or size+min(len(text),self.file_char_limit)>self.total_char_limit:skipped.append({'path':path,'reason':'index_resource_bound'});continue
   digest=sha(text);size+=min(len(text),self.file_char_limit)
   if path in self.rows and self.rows[path]['sha256']==digest:new[path]=self.rows[path];reused+=1;continue
   sample=text[:self.file_char_limit];lines=sample.splitlines();visitor=Symbols();status='not_python';parsed+=1
   if path.endswith('.py'):
    if len(text)>self.file_char_limit:status='file_too_large_for_complete_ast'
    else:
     try:
      with warnings.catch_warnings():
       warnings.simplefilter('ignore',SyntaxWarning);visitor.visit(ast.parse(text,filename=path))
      status='parsed'
     except (SyntaxError,RecursionError,ValueError):status='syntax_unresolved'
   new[path]={'path':path,'sha256':digest,'terms':collections.Counter(terms(sample)),'identifiers':collections.Counter(x.lower() for x in re.findall(r'[A-Za-z_][A-Za-z0-9_]*',sample)),'path_terms':set(terms(path)),'symbols':visitor.rows,'imports':visitor.imports,'references':visitor.references,'parse_status':status,'truncated':len(sample)<len(text),'lines':lines,'is_test':any(p in ('test','tests') for p in PurePosixPath(path).parts) or PurePosixPath(path).name.startswith('test_')}
  removed=sorted(set(self.rows)-set(new));self.rows=new;self.reference=dict(reference);self.edges=[];module_paths={}
  for path in new:
   if path.endswith('.py'):
    module=path[:-3].replace('/','.');module_paths[module]=path
    if module.endswith('.__init__'):module_paths[module[:-9]]=path
  for path,row in new.items():
   package=path.split('/')[:-1]
   for imp in row['imports']:
    base=package[:max(0,len(package)-imp['level']+1)] if imp['level'] else []
    module='.'.join([*base,imp['module']]).strip('.');target=module_paths.get(module)
    if target and target!=path:self.edges.append({'kind':'static_import','source':path,'target':target,'line':imp['line'],'confidence':'syntax_binding_not_runtime_call'})
  self.stats={'parsed_files':parsed,'reused_files':reused,'removed_files':removed,'indexed_files':len(new),'skipped_files':skipped,'index_chars':size,'complete_repository_index':not skipped and not any(x['truncated'] for x in new.values())}
  return self.stats
 def query(self,query,*,project=None,task_id=None,limit=8,max_chars=8000,use_graph=True):
  if not isinstance(query,str) or not query.strip() or len(query)>4000:raise ValueError('Bounded nonempty query required')
  if type(limit)is not int or not 1<=limit<=12 or type(max_chars)is not int or not 1500<=max_chars<=12000:raise ValueError('Bounded result size required')
  if project and project.get('actor')!=self.actor:raise ValueError('Foreign actor graph')
  identifiers={x for x in re.findall(r'[A-Za-z_][A-Za-z0-9_]*',query) if x.lower() not in STOP};q=set(terms(query));exact={x.lower() for x in re.findall(r'[A-Za-z_][A-Za-z0-9_]*',query) if ('_' in x or re.search(r'[a-z][A-Z]',x))};N=len(self.rows)
  df=collections.Counter(t for r in self.rows.values() for t in q if t in r['terms'] or t in r['path_terms'])
  exact_df=collections.Counter(t for r in self.rows.values() for t in exact if t in r['identifiers'])
  average=sum(sum(r['terms'].values()) for r in self.rows.values())/max(1,N);scores={};reasons=collections.defaultdict(list)
  for path,r in self.rows.items():
   length=sum(r['terms'].values());norm=1.2*(.25+.75*length/max(1,average))
   score=sum(math.log(1+(N-df[t]+.5)/(df[t]+.5))*r['terms'][t]*2.2/(r['terms'][t]+norm) for t in q if t in r['terms'])
   score+=sum(3*math.log(1+(N-df[t]+.5)/(df[t]+.5)) for t in q&r['path_terms'])
   score+=sum(6*math.log(1+(N-exact_df[t]+.5)/(exact_df[t]+.5))*min(2,r['identifiers'][t]) for t in exact if t in r['identifiers'])
   score+=max((4*len(q&set(terms(x['symbol'])))+12*len(exact&{z.lower() for z in x['symbol'].split('.')}) for x in r['symbols']),default=0)
   if score:scores[path]=score;reasons[path].append({'kind':'global_lexical_match','not_proven_relevance':True})
  definition_rank={p:max((2 if x['kind']=='class' else 1 for x in r['symbols'] if x['symbol'].split('.')[-1] in identifiers),default=0) for p,r in self.rows.items()}
  for p,rank in definition_rank.items():
   if rank:
    scores.setdefault(p,0.);reasons[p].insert(0,{'kind':'exact_public_symbol_definition','symbol_names':[x['symbol'] for x in self.rows[p]['symbols'] if x['symbol'].split('.')[-1] in identifiers][:4],'not_proven_root_cause':True})
  lexical=sorted(scores,key=lambda p:(-definition_rank[p],-scores[p],p));retained=lexical[:min(3,limit)];extra=set();graph_scores=collections.Counter()
  if use_graph:
   for e in self.edges:
    if e['source'] in lexical[:4] or e['target'] in lexical[:4]:
     target=e['target'] if e['source'] in lexical[:4] else e['source'];extra.add(target);graph_scores[target]=max(graph_scores[target],.1*max(scores.values(),default=1));reasons[target].append(e)
   # Conservative symbol-name reference candidates, never claimed resolved calls.
   named={x['symbol'].split('.')[-1] for p in lexical[:2] for x in self.rows[p]['symbols'] if q&set(terms(x['symbol']))}
   for path,row in self.rows.items():
    hits=[(name,line) for name,line in row['references'] if name in named]
    if hits:extra.add(path);graph_scores[path]=max(graph_scores[path],.12*max(scores.values(),default=1));reasons[path].append({'kind':'name_reference_candidate','matches':hits[:3],'confidence':'inferred_not_resolved_call'})
   for e in (project or {}).get('relations',[]):
    if e.get('visible_to')!=self.actor:raise ValueError('Foreign visible relation')
    if e.get('kind') in ('work_code_region','work_observed_region') and (not task_id or e['source']==task_id) and e.get('target') in self.rows:
     path=e['target'];current=e.get('version')==self.reference
     if current:extra.add(path);graph_scores[path]=max(graph_scores[path],(.3 if e['kind']=='work_code_region' else .15)*max(scores.values(),default=1));reasons[path].append({'kind':e['kind'],'relation_id':e['id'],'event':e.get('source_event'),'version':e.get('version'),'confidence':e['fact_status']})
  ranked=sorted((set(scores)|extra)-set(retained),key=lambda p:(-(scores.get(p,0)+graph_scores[p]),p));order=retained+ranked
  chosen=order[:limit]  # No forced graph quota; weak links may add nothing.
  hits=[]
  for path in chosen:
   r=self.rows[path];symbols=sorted(r['symbols'],key=lambda s:(-(2 if s['kind']=='class' else 1) if s['symbol'].split('.')[-1] in identifiers else 0,-len(q&set(terms(s['symbol']))),s['line']));anchor=symbols[0] if symbols else None
   line=anchor['line'] if anchor else next((i+1 for i,x in enumerate(r['lines']) if q&set(terms(x))),1)
   snippet=r['lines'][line-1][:180] if line<=len(r['lines']) else ''
   hits.append({'path':path,'file_sha256':r['sha256'],'symbol':anchor['symbol'] if anchor else None,'line':line,'end_line':anchor['end_line'] if anchor else line,'signature_excerpt':snippet,'is_test':r['is_test'],'parse_status':r['parse_status'],'reason':reasons[path][:3],'next_read':{'tool':'read_file','arguments':{'path':path,'start_line':max(1,line-3),'max_lines':50}},'score':round(scores.get(path,0)+graph_scores[path],4)})
  result={'version':VERSION,'actor':self.actor,'source_reference':self.reference,'query_excerpt':query[:256],'query_sha256':sha(query),'task_id':task_id,'hits':hits,'candidate_count':len(order),'global_lexical_top_paths':retained,'coverage':{'indexed_files':N,'skipped_files':len(self.stats.get('skipped_files',[])),'truncated_files':sum(r['truncated'] for r in self.rows.values())},'graph_expansion':use_graph,'inference_is_not_root_cause':True,'empty_or_missing_is_not_irrelevance':True,'next_if_missing':{'tool':'search_repository','instruction':'Use a public identifier or error string across the entire allowed repository; graph membership is not required.'},'output_limit_unit':'Unicode characters, not provider tokens'}
  result['source_id']=sha(json.dumps([self.actor,self.reference,[(p,r['sha256']) for p,r in self.rows.items()]],sort_keys=True))
  result['omitted_results']=len(order)-len(result['hits'])
  while len(json.dumps(result,ensure_ascii=False))>max_chars and result['hits']:
   result['hits'].pop();result['omitted_results']=len(order)-len(result['hits'])
  if len(json.dumps(result,ensure_ascii=False))>max_chars:raise ValueError('Metadata exceeds requested output allowance')
  return result
