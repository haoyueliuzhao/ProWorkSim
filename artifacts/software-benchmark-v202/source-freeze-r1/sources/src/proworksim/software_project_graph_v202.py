"""Transactional, evidence-scoped Project Graph over a normalized event stream.

File-level incremental analysis is intentionally conservative. Static import
targets are may-dependencies, never asserted runtime causality.
"""
from __future__ import annotations
import ast,copy,time,re
from .software_syntax_facts_v202 import sha,document,SyntaxFacts,IncrementalSyntax,SourceConflict
from .software_context_graph_v196 import safe_path

def identity(kind,*values):return kind+':'+sha(values)[:24]
def version_id(scope,actor,ref):return identity('Version',scope,actor,ref)

def empty_state(scope,repo,commit,members):
    return {'scope':scope,'repo':repo,'commit':commit,'members':list(members),'current':{},'versions':{},'files':{},
        'runs':{},'artifacts':{},'deliveries':{},'tasks':{},'task_dependencies':{},'adoptions':{},'issues':{}}

def reduce_event(state,event):
    s=copy.deepcopy(state);actor=event['actor'];kind=event['kind'];source=event['source_ids'];body=event['data']
    if actor not in s['members'] or not source:raise SourceConflict('Unknown member or unsourced event')
    def ver(ref):
        if not isinstance(ref,dict) or not all(isinstance(ref.get(k),str) for k in ('object_id','version_id')):raise SourceConflict('Exact private version required')
        vid=version_id(s['scope'],actor,ref);previous=s['current'].get(actor)
        s['versions'].setdefault(vid,{'reference':copy.deepcopy(ref),'actor':actor,'parent':previous,'source_ids':source})
        s['current'][actor]=vid;return vid
    def set_doc(path,doc):
        if not safe_path(path) or doc['scope']!=[s['scope'],actor] or doc['path']!=path:raise SourceConflict('Foreign or unsafe source document')
        if sha(doc['text'].encode())!=doc['source_hash']:raise SourceConflict('Document hash mismatch')
        key=actor+'\0'+path;s['files'][key]=copy.deepcopy(doc)
    if kind=='issue':
        ver(body['version']);s['issues'].setdefault('issue',{'description':body.get('description',''),'source_ids':source})
        s['tasks'].setdefault('root',{'id':'root','description':body.get('description',''),'targets':[],'owner':actor,'status':'open','source_ids':source})
    elif kind=='version':
        previous=s['current'].get(actor);new=ver(body['version'])
        if previous and previous!=new:
            for key,old in list(s['files'].items()):
                if key.startswith(actor+'\0'):
                    s['files'][key]=document('',scope=[s['scope'],actor],path=old['path'],version=body['version'],source_id=source[0],complete=False,
                        evidence=[{'reason':'unexplained_workspace_version_change','source_ids':source}])
    elif kind in {'file_observed','file_written'}:
        doc=body['document'];ref=doc['version']
        if kind=='file_written' or actor not in s['current']:ver(ref)
        if version_id(s['scope'],actor,ref)==s['current'][actor]:set_doc(doc['path'],doc)
        # Historical reads remain in the event log, never revert the current file.
    elif kind=='file_unknown':
        ver(body['version'])
        paths=body['paths'] or [d['path'] for k,d in s['files'].items() if k.startswith(actor+'\0')]
        for path in paths:
            doc=document('',scope=[s['scope'],actor],path=path,version=body['version'],source_id=source[0],complete=False,evidence=[{'reason':'successful_change_without_complete_postimage','source_ids':source}]);set_doc(path,doc)
    elif kind=='file_deleted':
        ver(body['version']);s['files'].pop(actor+'\0'+body['path'],None)
    elif kind=='file_renamed':
        ver(body['version']);old=s['files'].pop(actor+'\0'+body['old_path'],None)
        if old:
            old.update(path=body['new_path'],version=body['version'],source_id='rename:'+event['event_id'])
            old['evidence'].append({'rename_receipt':source});set_doc(body['new_path'],old)
        else:
            set_doc(body['new_path'],document('',scope=[s['scope'],actor],path=body['new_path'],version=body['version'],source_id=source[0],complete=False))
    elif kind=='test':
        if body.get('executed') is not True:return s
        key=actor+'\0'+body['report_id'];record={k:copy.deepcopy(body.get(k)) for k in ('report_id','version','passed','counts','selector','failure_text')}
        record.update(actor=actor,source_ids=source)
        vid=version_id(s['scope'],actor,body['version'])
        s['versions'].setdefault(vid,{'reference':body['version'],'actor':actor,'parent':None,'source_ids':source})
        prior=s['runs'].get(key)
        if prior:
            for k in ('version','passed','counts'):
                if prior[k] is not None and record[k] is not None and prior[k]!=record[k]:raise SourceConflict('Immutable TestRun changed')
            prior['source_ids']=sorted(set(prior['source_ids'])|set(source))
            if not prior.get('failure_text') and record.get('failure_text'):prior['failure_text']=record['failure_text']
        else:s['runs'][key]=record
    elif kind=='artifact':
        key=actor+'\0'+body['artifact_id'];record={**copy.deepcopy(body),'author':actor,'source_ids':source,'authorized_receivers':[]}
        if key in s['artifacts'] and s['artifacts'][key]['version']!=record['version']:raise SourceConflict('Artifact identity reused with another version')
        s['artifacts'].setdefault(key,record)
    elif kind=='share_artifact':
        artifact=s['artifacts'][body['artifact_key']]
        if artifact['author']!=actor or body['recipient'] not in s['members']:raise SourceConflict('Only author can publish a scoped handoff')
        artifact['authorized_receivers']=sorted(set(artifact['authorized_receivers'])|{body['recipient']})
    elif kind=='adopt_artifact':
        artifact=s['artifacts'][body['artifact_key']]
        if actor not in artifact['authorized_receivers']:raise SourceConflict('Artifact not shared with recipient')
        ver(body['version'])
        for path in body.get('paths',[]):
            set_doc(path,document('',scope=[s['scope'],actor],path=path,version=body['version'],source_id=source[0],complete=False,
                evidence=[{'artifact_key':body['artifact_key'],'merge_receipt':source,'merged_content_unknown':True}]))
        s['adoptions'][event['event_id']]={'actor':actor,'artifact_key':body['artifact_key'],'version':body['version'],'source_ids':source}
    elif kind=='delivery':
        vid=version_id(s['scope'],actor,body['version'])
        if s['current'].get(actor)!=vid:raise SourceConflict('Delivery version is not current actor version')
        s['deliveries'][actor+'\0'+body['delivery_id']]={**copy.deepcopy(body),'actor':actor,'source_ids':source}
    elif kind=='task':
        if body.get('owner') not in s['members']:raise SourceConflict('Task needs an explicit live owner')
        s['tasks'][body['id']]={**copy.deepcopy(body),'source_ids':source}
    elif kind=='task_dependency':
        if body['upstream'] not in s['tasks'] or body['downstream'] not in s['tasks']:raise SourceConflict('Unbound task dependency')
        s['task_dependencies'][sha(body)]={**copy.deepcopy(body),'source_ids':source}
    elif kind in {'rejected_operation','unknown_observation'}:pass
    else:raise SourceConflict('Unsupported normalized event kind: '+kind)
    return s

def file_structure(doc,syntax,incremental):
    nodes={};edges={};key=(tuple(doc['scope']),doc['path']);started=time.process_time()
    file_id=identity('File',doc['scope'],doc['path'],doc['version'],doc['source_hash'])
    nodes[file_id]={'type':'File','scope':doc['scope'],'path':doc['path'],'version':doc['version'],'source_hash':doc['source_hash'],'complete':doc['complete'],'source_ids':[doc['source_id']]}
    result={'nodes':nodes,'edges':edges,'file_id':file_id,'imports':[],'symbols':{},'parse':None}
    if doc['complete']:
        tree,parse=syntax.parse(key,doc['text'],incremental=incremental);result['parse']=parse
        nodes[file_id]['syntax_status']='unparseable' if tree.root_node.has_error else 'complete'
    else:nodes[file_id]['syntax_status']='partial_source'
    facts=syntax.engine.extract(doc,'A2')
    for fact in facts['facts']:
        nodes[fact['fact_id']]={'type':'Fact',**fact};sid=fact['span_id'];nodes[sid]={'type':'EvidenceSpan',**facts['evidence_spans'][sid]}
        eid=identity('edge',fact['fact_id'],sid,'supported_by');edges[eid]={'source':fact['fact_id'],'target':sid,'type':'supported_by','status':'Confirmed','source_ids':[doc['source_id']]}
        if fact['parent_fact_id'] is None:
            eid=identity('edge',file_id,fact['fact_id'],'contains_observed_fact');edges[eid]={'source':file_id,'target':fact['fact_id'],'type':'contains_observed_fact','status':'Confirmed','source_ids':[doc['source_id']]}
    for link in facts['relations']:
        eid=identity('edge',link['from'],link['to'],'syntax_contains');edges[eid]={'source':link['from'],'target':link['to'],'type':'syntax_contains','status':'Confirmed','source_ids':[doc['source_id']]}
    if not doc['complete'] or tree.root_node.has_error:
        result['analysis_CPU_seconds']=time.process_time()-started;return result
    try:module=ast.parse(doc['text'])
    except SyntaxError:
        nodes[file_id]['python_AST_crosscheck']='unsupported_or_invalid';return result
    def visit(body,parents=()):
        for node in body:
            if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):continue
            qual='.'.join((*parents,node.name));sid=identity('Symbol',doc['scope'],doc['path'],doc['version'],qual)
            nodes[sid]={'type':'Symbol','qualified_name':qual,'path':doc['path'],'version':doc['version'],'source_ids':[doc['source_id']],
                'syntax_fingerprint':sha(ast.dump(node,include_attributes=False))}
            result['symbols'][qual]=nodes[sid]['syntax_fingerprint'];eid=identity('edge',file_id,sid,'declares');edges[eid]={'source':file_id,'target':sid,'type':'declares','status':'Confirmed','source_ids':[doc['source_id']]}
            visit(node.body,(*parents,node.name))
    visit(module.body)
    for node in ast.walk(module):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''];level=getattr(node,'level',0)
            for module_name in modules:
                rid=identity('Reference',doc['scope'],doc['path'],doc['version'],module_name,level,node.lineno)
                nodes[rid]={'type':'Reference','module':module_name,'level':level,'path':doc['path'],'version':doc['version'],'source_ids':[doc['source_id']]}
                eid=identity('edge',file_id,rid,'imports_syntax');edges[eid]={'source':file_id,'target':rid,'type':'imports_syntax','status':'Confirmed','source_ids':[doc['source_id']]}
                result['imports'].append({'reference_id':rid,'module':module_name,'level':level,'actor':doc['scope'][1],'path':doc['path']})
    result['analysis_CPU_seconds']=time.process_time()-started;return result

def project_state(state,cache,syntax,mode):
    nodes={};edges={};structures={};parses_before=syntax.parses;changed=[]
    def node(kind,key,**attrs):
        nid=identity(kind,state['scope'],key);nodes[nid]={'type':kind,**attrs};return nid
    def edge(kind,a,b,sources,status='Confirmed',**attrs):
        eid=identity('edge',a,b,kind,attrs);edges[eid]={'source':a,'target':b,'type':kind,'status':status,'source_ids':sources,**attrs}
    repo=node('Repository',state['repo'],repo=state['repo']);commit=node('Commit',state['commit'],sha=state['commit'],is_real_base_commit=True)
    edge('base_commit',repo,commit,['initial_repository_metadata'])
    for key,doc in sorted(state['files'].items()):
        signature=sha(doc);prior=cache.get(key)
        if mode in {'PG2','PG3'} and prior and prior[0]==signature:structure=prior[1]
        else:structure=file_structure(doc,syntax,mode in {'PG2','PG3'});changed.append(key)
        structures[key]=structure;cache[key]=(signature,structure);nodes.update(structure['nodes']);edges.update(structure['edges'])
        edge('observed_file',repo,structure['file_id'],[doc['source_id']])
    for key in set(cache)-set(state['files']):del cache[key];changed.append(key)
    for key,structure in structures.items():
        for imp in structure['imports']:
            parts=imp['path'].split('/')[:-1];prefix=parts[:len(parts)-imp['level']+1] if imp['level'] else []
            module='/'.join(prefix+imp['module'].split('.')).strip('/')
            for path in (module+'.py',module+'/__init__.py'):
                target=structures.get(imp['actor']+'\0'+path)
                if target:edge('may_import',structure['file_id'],target['file_id'],nodes[imp['reference_id']]['source_ids'],'Inferred',reason='static_observed_path_candidate_not_runtime_resolution')
    for vid,v in state['versions'].items():nodes[vid]={'type':'Version',**v,'is_git_commit':False}
    for key,structure in structures.items():
        actor=key.split('\0',1)[0];doc=state['files'][key]
        if actor in state['current']:edge('known_file_in_workspace',state['current'][actor],structure['file_id'],[doc['source_id']],
            continuity='known_content_carried_only_across_explicit_changes_to_other_paths')
    for key,run in state['runs'].items():
        rid=node('TestRun',key,**run);vid=version_id(state['scope'],run['actor'],run['version'])
        edge('validates_selected_scope',rid,vid,run['source_ids'],effective=(state['current'].get(run['actor'])==vid),passed=run['passed'],selector=run['selector'])
        if run['selector'] is not None:
            definition=node('TestDefinition',[state['repo'],run['selector']],selector=run['selector'],definition_scope='invoked_selector_not_inferred_test_case_body')
            edge('executes_definition',rid,definition,run['source_ids'])
        if run['passed'] is False:
            fid=node('FailureEvidence',key,text=run.get('failure_text'),counts=run['counts'],source_ids=run['source_ids'],not_proven_code_cause=True);edge('has_failure',rid,fid,run['source_ids'])
    for key,a in state['artifacts'].items():
        aid=node('Artifact',key,**a);vid=version_id(state['scope'],a['author'],a['version'])
        nodes.setdefault(vid,{'type':'Version','reference':a['version'],'actor':a['author'],'is_git_commit':False,'source_ids':a['source_ids']})
        edge('derived_from',aid,vid,a['source_ids'])
    for key,a in state['adoptions'].items():
        nid=node('Adoption',key,**a);aid=identity('Artifact',state['scope'],a['artifact_key']);edge('adopts',nid,aid,a['source_ids'],does_not_validate=True)
    for key,d in state['deliveries'].items():
        nid=node('Delivery',key,**d);vid=version_id(state['scope'],d['actor'],d['version']);edge('submitted_version',nid,vid,d['source_ids'],official_acceptance_not_inferred=True)
    for key,t in state['tasks'].items():node('Task',key,**t)
    for key,i in state['issues'].items():
        iid=node('Issue',key,**i);edge('addresses_issue',identity('Task',state['scope'],'root'),iid,i['source_ids'])
    for d in state['task_dependencies'].values():edge('declared_task_dependency',identity('Task',state['scope'],d['downstream']),identity('Task',state['scope'],d['upstream']),d['source_ids'],semantics='explicit_task_contract_not_code_causality')
    assert all(e['source'] in nodes and e['target'] in nodes for e in edges.values())
    return {'nodes':nodes,'edges':edges,'current_versions':copy.deepcopy(state['current']),'observed_material_scope_only':True},cache,{'reanalysed_file_keys':changed,'tree_parses':syntax.parses-parses_before}

def may_impact(before,after,changed_keys):
    # Include old edges too, so removing an import still identifies its former consumer.
    graphs=[before,after];adj={};files={}
    for g in graphs:
        if not g:continue
        for nid,n in g['nodes'].items():
            if n['type']=='File':files[nid]=n['scope'][1]+'\0'+n['path']
        for e in g['edges'].values():
            if e['type']=='may_import':adj.setdefault(e['target'],set()).add(e['source'])
    frontier=[nid for nid,key in files.items() if key in changed_keys];reached=set(frontier)
    while frontier:
        for nxt in adj.get(frontier.pop(),()):
            if nxt not in reached:reached.add(nxt);frontier.append(nxt)
    affected=sorted({files[n] for n in reached}|set(changed_keys))
    return {'changed':sorted(set(changed_keys)),'potentially_affected':affected,'basis':'reverse_union_of_old_and_new_static_may_import_edges',
        'confidence':'conservative_candidate_not_runtime_causality'}

class ProjectGraph:
    def __init__(self,*,scope,repo,commit,members,mode='PG2'):
        if mode not in {'PG0','PG1','PG2','PG3'}:raise ValueError('Unknown maintenance condition')
        if not scope or not re.fullmatch('[0-9a-f]{40}',commit) or not members:raise SourceConflict('Explicit scope, actual base commit identity and members required')
        self.state=empty_state(scope,repo,commit,members);self.mode=mode;self.syntax=IncrementalSyntax();self.cache={};self.events=[];self.attempts=[];self.snapshots=[];self.snapshot=None;self.ids={};self.static_frozen=False
    def apply(self,event,*,fail_after_reduce=False,fail_after_project=False):
        start=time.process_time();fingerprint=sha(event);eid=event['event_id']
        if eid in self.ids:
            if self.ids[eid]!=fingerprint:raise SourceConflict('Event ID reused for different content')
            return {'idempotent':True,'CPU_seconds':time.process_time()-start,'tree_parses':0}
        try:
            state=reduce_event(self.state,event)
            if fail_after_reduce:raise RuntimeError('synthetic transaction fault')
            cache=dict(self.cache);syntax=self.syntax.fork()
            version_changed=any(actor in self.state['current'] and self.state['current'][actor]!=vid for actor,vid in state['current'].items())
            frozen=self.static_frozen or (self.mode=='PG0' and version_changed)
            if frozen and self.mode=='PG0':snapshot=copy.deepcopy(self.snapshot);cost={'reanalysed_file_keys':[],'tree_parses':0}
            else:snapshot,cache,cost=project_state(state,cache,syntax,self.mode)
            def material(d):return None if d is None else (d['source_hash'],d['complete'],None if d['complete'] else d['version'])
            material_changes=[key for key in set(self.state['files'])|set(state['files']) if material(self.state['files'].get(key))!=material(state['files'].get(key))]
            impacted=may_impact(self.snapshot,snapshot,material_changes) if self.mode=='PG3' else None
            if fail_after_project:raise RuntimeError('synthetic failure after syntax/graph computation')
        except Exception as error:
            self.attempts.append({'event_id':eid,'event_sha256':fingerprint,'committed':False,'error':repr(error)});raise
        self.state,self.cache,self.syntax,self.snapshot=state,cache,syntax,snapshot;self.static_frozen=frozen
        self.events.append(copy.deepcopy(event));self.ids[eid]=fingerprint;self.snapshots.append(copy.deepcopy(snapshot));self.attempts.append({'event_id':eid,'event_sha256':fingerprint,'committed':True})
        return {**cost,'CPU_seconds':time.process_time()-start,'impact':impacted,'snapshot_sha256':sha(snapshot),'event_log_sha256':sha(self.events)}
