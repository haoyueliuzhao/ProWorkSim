"""Private, incremental work graph constructed ONLY from supplied visible messages.

No filesystem, network, repository, hidden evaluator, model or World access.
Confirmed means a sourced execution/representation fact or static syntax, never
runtime coverage, inferred module resolution, or causality.
"""
from __future__ import annotations
import ast
import copy
import json
import re
import textwrap
from collections import defaultdict
from .software_context_compression_v175 import canonical, digest, is_observation

VERSION='v196-private-observed-work-graph-r1'
MUTATIONS={'write_file','replace_file','create_file','delete_file','rename_file','integrate_patch'}
TEST_TOOLS={'run_tests','read_test_result'}
RELATIONS={'observed_in','contains','calls','imports','tests','modifies','validates','depends_on','supersedes','derived_from'}
FACT_PROOFS={'observed_source','successful_tool','report_binding','static_syntax','observed_version_transition','same_evidence_read'}
CONFIRMED_PROOFS={'observed_in':{'observed_source','same_evidence_read'},
    'contains':{'static_syntax','report_binding','successful_tool'},'calls':{'static_syntax'},
    'imports':{'static_syntax'},'tests':{'report_binding','successful_tool'},
    'modifies':{'successful_tool'},'validates':{'report_binding'},'depends_on':set(),
    'supersedes':{'observed_version_transition'},'derived_from':{'successful_tool'}}


class GraphIntegrityError(ValueError):pass
class GraphScopeError(PermissionError):pass


def obj(text):
    try:value=json.loads(text)
    except (TypeError,ValueError):return {}
    return value if isinstance(value,dict) else {}


def pointer(value,path):
    for part in path.strip('/').split('/') if path else []:
        key=part.replace('~1','/').replace('~0','~')
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value


def safe_path(value):
    if not isinstance(value,str):return None
    value=value.removeprefix('/testbed/').removeprefix('./').strip()
    if (not value or value.startswith('/') or '\\' in value or '\x00' in value
            or '..' in value.split('/')):return None
    return value


def file_of_test(value):
    match=re.match(r'(.+?\.py)(?::|$)',value) if isinstance(value,str) else None
    return safe_path(match.group(1)) if match else None


def source_ref(result):
    value=result.get('source_reference')
    if isinstance(value,dict) and all(isinstance(value.get(k),str) for k in ('object_id','version_id')):
        return {k:value[k] for k in ('object_id','version_id')}
    return None


class ObservedWorkGraph:
    def __init__(self,episode,member,*,dependencies_enabled=True):
        if not episode or not member:raise GraphScopeError('Explicit private scope is required')
        self.episode,self.member=episode,member
        self.nodes={};self.edges={};self.sources={};self.events={};self.actions={}
        self.report_alias={};self.current_version=None;self.version_source=None
        self.current_version_index=-1
        self.step=-1;self.last_index=-1;self.action_order=[];self._seen=set();self.ast_attempts={}
        self._file_nodes={};self._symbol_nodes={};self.task=None;self.warnings=[]
        self.dependencies_enabled=dependencies_enabled

    def _id(self,kind,key):return kind+':'+digest([self.episode,self.member,key])[:24]

    def node(self,kind,key,*,attrs=None,sources=()):
        nid=self._id(kind,key)
        if nid not in self.nodes:
            self.nodes[nid]={'id':nid,'type':kind,'scope':[self.episode,self.member],
                'first_seen_step':self.step,'attrs':{},'sources':[]}
        n=self.nodes[nid]
        n['attrs'].update(copy.deepcopy(attrs or {}))
        for sid in sources:
            if sid not in self.sources:raise GraphIntegrityError('Node has an unknown source')
            if sid not in n['sources']:n['sources'].append(sid)
        return nid

    def edge(self,kind,left,right,*,sources,status='Confirmed',proof='observed_source',attrs=None):
        if kind not in RELATIONS or left not in self.nodes or right not in self.nodes:
            raise GraphIntegrityError('Invalid graph relation')
        if status not in {'Confirmed','Inferred'} or not sources or any(s not in self.sources for s in sources):
            raise GraphIntegrityError('Every edge needs accessible, explicit evidence')
        if status=='Confirmed' and proof not in CONFIRMED_PROOFS[kind]:
            raise GraphIntegrityError('Inference cannot become a confirmed edge')
        eid=self._id('edge',[kind,left,right,status,proof,attrs or {}])
        if eid not in self.edges:
            self.edges[eid]={'id':eid,'type':kind,'source':left,'target':right,'status':status,
                'proof':proof,'attrs':copy.deepcopy(attrs or {}),'sources':[], 'first_seen_step':self.step}
        e=self.edges[eid]
        e['sources']=sorted(set(e['sources'])|set(sources))
        return eid

    def hypothesis(self,left,right,sources,description):
        return self.edge('depends_on',left,right,sources=sources,status='Inferred',
            proof='explicit_unverified_hypothesis',attrs={'description':description,'causality_confirmed':False})

    def _source(self,message,index):
        sid=self._id('source',[index,digest(message)])
        if sid not in self.sources:
            self.sources[sid]={'id':sid,'scope':[self.episode,self.member],'message_index':index,
                'message_sha256':digest(message),'message':copy.deepcopy(message),'first_seen_step':self.step}
        return sid

    def field(self,sid,channel,path,*,call_index=None,span=None):
        m=self.sources[sid]['message']
        if channel=='body':value=pointer(obj(m.get('content')),path)
        elif channel=='arguments':value=pointer(obj(m['tool_calls'][call_index]['function']['arguments']),path)
        elif channel=='message':value=pointer(m,path)
        else:raise GraphIntegrityError('Unknown field provenance channel')
        origin={'source_id':sid,'channel':channel,'pointer':path}
        if call_index is not None:origin['call_index']=call_index
        if span is not None:
            if not isinstance(value,str):raise GraphIntegrityError('Only text fields have spans')
            begin,end=span
            if not (0<=begin<=end<=len(value)):raise GraphIntegrityError('Invalid observed excerpt')
            value=value[begin:end];origin['span']=[begin,end]
        return {'value':copy.deepcopy(value),'origin':origin}

    def _add(self,event,name,field):
        if name=='validation_status':
            # This is a presentation-time applicability label, not a second
            # immutable test outcome. Old source messages remain archived.
            event['fields']=[f for f in event['fields'] if f['name']!=name or f['value']==field['value']]
        if event['kind']=='test' and name in {'passed','counts','report_id'}:
            prior_values=[f['value'] for f in event['fields'] if f['name']==name]
            if prior_values and any(v!=field['value'] for v in prior_values):
                raise GraphIntegrityError('Conflicting immutable test field: '+name)
        key=digest([name,field['value']])
        prior=next((f for f in event['fields'] if f['key']==key),None)
        if prior is None:
            event['fields'].append({'name':name,'key':key,**field})
        elif field['origin']!=prior['origin'] and field['origin'] not in prior.setdefault('supporting_origins',[]):
            prior['supporting_origins'].append(copy.deepcopy(field['origin']))

    def _try(self,event,name,sid,channel,path,**kwargs):
        try:field=self.field(sid,channel,path,**kwargs)
        except (KeyError,IndexError,TypeError,ValueError):return
        if field['value'] is not None:self._add(event,name,field)

    def _version(self,reference,files_hash,sid,*,current=False):
        if reference is None:return None
        nid=self.node('Version',reference,attrs={'source_reference':reference},sources=[sid])
        if files_hash:
            prior=self.nodes[nid]['attrs'].get('files_sha256')
            if prior and prior!=files_hash:raise GraphIntegrityError('One code version has conflicting file hashes')
            self.nodes[nid]['attrs']['files_sha256']=files_hash
        if current and self.sources[sid]['message_index']>=self.current_version_index:
            old=self.current_version
            if old and old!=nid:
                self.edge('supersedes',nid,old,sources=[sid],proof='observed_version_transition',
                    attrs={'old_history_preserved':True,'old_tests_do_not_validate_new_version':True})
            self.current_version=nid;self.version_source=sid
            self.current_version_index=self.sources[sid]['message_index']
        return nid

    def _file(self,path,sid):
        path=safe_path(path)
        if not path:return None
        nid=self.node('Code',{'path':path},attrs={'path':path,'entity_kind':'file'},sources=[sid])
        self._file_nodes[path]=nid
        return nid

    def _event(self,key,kind,sid,index,*,node=None,version=None):
        eid=self._id('event',key)
        if eid not in self.events:
            self.events[eid]={'id':eid,'kind':kind,'node':node,'version':version,'sources':[],
                'fields':[],'paths':[],'symbols':[],'first_index':index,'last_index':index,
                'first_seen_step':self.step,'anchors':[]}
        e=self.events[eid]
        if e['kind']!=kind:raise GraphIntegrityError('Event category changed')
        if e['version'] and version and e['version']!=version:raise GraphIntegrityError('Event version changed')
        e['version']=version or e['version'];e['node']=node or e['node']
        if sid not in e['sources']:e['sources'].append(sid)
        e['last_index']=max(e['last_index'],index)
        if index not in e['anchors']:e['anchors'].append(index)
        return e

    def _path(self,event,path,sid,*,relation='observed_in',proof='observed_source',status='Confirmed'):
        path=safe_path(path)
        if not path:return
        if path not in event['paths']:event['paths'].append(path)
        code=self._file(path,sid)
        if event['node']:
            left,right=(code,event['node']) if relation=='observed_in' else (event['node'],code)
            attrs={'version':event.get('version')}
            if relation=='tests':attrs['semantics']='reported_or_selected_location_not_runtime_coverage'
            self.edge(relation,left,right,sources=list(dict.fromkeys([sid,*event['sources']])),proof=proof,status=status,attrs=attrs)

    def _diagnostics(self,event,sid,path):
        try:text=self.field(sid,'body',path)['value']
        except (KeyError,TypeError):return
        if not isinstance(text,str):return
        # Keep exact observed substrings, including escaped log newlines.
        failure_patterns=[r'(?:FAILED|ERROR)\s+([^\s"\\]+\.py(?:::[^\s"\\]+)*)',
                          r'_{3,}\s+([\w./-]+\.py:test_[\w\[\].-]+)']
        failure_matches=sorted((m for pattern in failure_patterns for m in re.finditer(pattern,text)),key=lambda m:m.start())
        for match in failure_matches[:6]:
            self._add(event,'failed_test',self.field(sid,'body',path,span=match.span(1)))
            target=file_of_test(match.group(1));self._path(event,target,sid,relation='tests',proof='report_binding')
            test=self.node('Test',[match.group(1),event.get('version')],
                attrs={'node_id':match.group(1),'reported_failed':True,'version':event.get('version')},sources=[sid])
            self.edge('contains',event['node'],test,sources=[sid],proof='report_binding',
                attrs={'semantics':'failure_name_in_observed_public_report'})
        for match in list(re.finditer(r'(?:[A-Za-z_][\w.]*(?:Error|Exception)|AssertionError)(?::[^\n\\]{0,200})?',text))[:3]:
            self._add(event,'error_excerpt',self.field(sid,'body',path,span=match.span()))
        # Escaped JSON newlines are delimiters, not the first letter of a
        # relative path ("\\n/testbed/x.py" must never become "n/testbed/x.py").
        location_patterns=[r'''(?:^|[\s"'(=]|\\[nrt])(?:/testbed/)?([\w./-]+\.py)(?::\d+|::[\w\[\].-]+)''',
                           r'''File\s+\\?"(?:/testbed/)?([\w./-]+\.py)\\?",\s+line\s+\d+''']
        locations=sorted((m for pattern in location_patterns for m in re.finditer(pattern,text)),key=lambda m:m.start())
        for match in locations[:6]:
            self._add(event,'reported_location',self.field(sid,'body',path,span=match.span(1)))
            self._path(event,match.group(1),sid,relation='tests',proof='report_binding')
        for match in re.finditer(r'"argv"\s*:\s*',text):
            try:value,end=json.JSONDecoder().raw_decode(text,match.end())
            except ValueError:continue
            if isinstance(value,list) and value and all(isinstance(x,str) for x in value):
                # Store the exact JSON array text; do not fabricate a shell command.
                self._add(event,'observed_command_json',self.field(sid,'body',path,span=(match.end(),end)))
                break

    def _ast(self,path,text,sid,version,*,complete=False):
        if not self.dependencies_enabled:return
        if not isinstance(text,str) or not path.endswith('.py'):return
        key=digest([path,text,version])
        if key in self.ast_attempts:return
        self.ast_attempts[key]={'source':sid,'path':path,'version':version,'complete_file':complete,'parsed':False}
        try:tree=ast.parse(textwrap.dedent(text))
        except (SyntaxError,ValueError,MemoryError):return
        self.ast_attempts[key]['parsed']=True
        file_node=self._file(path,sid);symbols={}
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                symbol=self.node('Code',[path,version,key,node.name,node.lineno],
                    attrs={'path':path,'symbol':node.name,'entity_kind':'symbol','version':version,
                           'source_line':node.lineno,'fragment_sha256':digest(text),
                           'line_scope':'observed_fragment','syntax_only':True},sources=[sid])
                symbols.setdefault(node.name,[]).append(symbol)
                self._symbol_nodes[(path,node.name,version)]=symbol
                self.edge('contains',file_node,symbol,sources=[sid],proof='static_syntax',
                    attrs={'version':version,'complete_file':complete})
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=([alias.name for alias in node.names] if isinstance(node,ast.Import) else [('.'*node.level)+(node.module or '')])
                for name in names:
                    module=self.node('Code',['module_reference',name],attrs={'module':name,'entity_kind':'module_reference'},sources=[sid])
                    self.edge('imports',file_node,module,sources=[sid],proof='static_syntax',attrs={'version':version,'semantics':'literal_import_statement'})
        for function in ast.walk(tree):
            if not isinstance(function,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
            owner=next(n for n in symbols[function.name] if self.nodes[n]['attrs']['source_line']==function.lineno)
            pending=list(function.body)
            while pending:
                node=pending.pop()
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)):continue
                pending.extend(ast.iter_child_nodes(node))
                if not isinstance(node,ast.Call):continue
                try:name=ast.unparse(node.func)
                except (ValueError,RecursionError):continue
                target=self.node('Code',['call_reference',path,version,name],
                    attrs={'path':path,'symbol':name,'entity_kind':'call_reference','version':version},sources=[sid])
                self.edge('calls',owner,target,sources=[sid],proof='static_syntax',
                    attrs={'semantics':'call_expression_not_confirmed_runtime_dispatch','version':version})
                if isinstance(node.func,ast.Name) and len(symbols.get(name,[]))==1:
                    self.edge('depends_on',target,symbols[name][0],sources=[sid],status='Inferred',proof='lexical_symbol_candidate',
                        attrs={'runtime_target_confirmed':False})
        self._resolve_imports()

    def _resolve_imports(self):
        if not self.dependencies_enabled:return
        # Resolution uses the already observed path set only. A possible Python
        # module match is an inference, even when only one such path is known.
        for n in list(self.nodes.values()):
            if n['type']!='Code' or n['attrs'].get('entity_kind')!='module_reference':continue
            module=n['attrs']['module'].lstrip('.');suffix=module.replace('.','/')
            if not suffix:continue
            matches=[nid for path,nid in self._file_nodes.items() if path in {suffix+'.py',suffix+'/__init__.py'} or path.endswith('/'+suffix+'.py')]
            if len(matches)==1:
                self.edge('depends_on',n['id'],matches[0],sources=n['sources'],status='Inferred',proof='observed_path_module_match',
                    attrs={'runtime_import_resolution_confirmed':False})

    def _observe_test(self,result,action,sid,index,observation):
        report=result.get('report_id')
        if not isinstance(report,str) or not report:return
        operation=(result.get('report_event') or {}).get('operation_id')
        prior=self.report_alias.get(report)
        run_key=prior or self._id('test-run',report)
        reference=source_ref(result);version=self._version(reference,result.get('files_sha256'),sid)
        attrs={'report_id':report}
        for key,value in {'run_id':operation,'version':version,'files_sha256':result.get('files_sha256'),
                          'body_sha256':result.get('body_sha256'),'tree_hash':result.get('tree_sha256')}.items():
            if value is not None:attrs[key]=value
        existing=self.nodes.get(run_key)
        if existing:
            for key,value in attrs.items():
                if key in existing['attrs'] and existing['attrs'][key]!=value:
                    raise GraphIntegrityError('Conflicting identity for one test report: '+key)
        else:
            self.nodes[run_key]={'id':run_key,'type':'TestRun','scope':[self.episode,self.member],
                'first_seen_step':self.step,'attrs':{},'sources':[]}
        self.nodes[run_key]['attrs'].update(attrs)
        if sid not in self.nodes[run_key]['sources']:self.nodes[run_key]['sources'].append(sid)
        self.report_alias[report]=run_key
        self.edge('observed_in',run_key,observation,sources=[sid],proof='same_evidence_read')
        if version and result.get('executed') is True:
            self.edge('validates',run_key,version,sources=[sid],proof='report_binding',
                attrs={'scope':'selected_public_tests_only','attempt_not_full_correctness':True,
                       'passed':result.get('passed') is True})
        event=self._event(['test-run',run_key],'test',sid,index,node=run_key,version=version)
        for name,key in [('passed','passed'),('counts','counts'),('report_id','report_id'),('validation_status','validation_status')]:
            self._try(event,name,sid,'body','/result/'+key)
        if 'passed' in result:
            previous=event.get('passed')
            if previous is not None and previous!=result['passed']:raise GraphIntegrityError('Immutable test result changed on read')
            event['passed']=result['passed']
        event['critical_failure']=event.get('passed') is False
        if action and action['tool']=='run_tests':
            self._try(event,'declared_selection',action['source'],'arguments','/selection',call_index=action['call_index'])
            selection=action['arguments'].get('selection')
            if selection is not None:self.nodes[run_key]['attrs']['selector']=copy.deepcopy(selection)
            for target in (selection or {}).get('targets',[]):
                self._path(event,file_of_test(target),action['source'],relation='tests',proof='successful_tool')
                test=self.node('Test',[target,version],attrs={'node_id':target,'version':version,
                    'selected_not_necessarily_executed':True},sources=[action['source'],sid])
                self.edge('contains',run_key,test,sources=[action['source'],sid],proof='successful_tool',
                    attrs={'semantics':'declared_public_test_selection'})
        for key,name in [('argv','observed_command'),('public_test_selection','observed_selection'),('environment_hash','environment_hash'),('input_tree_sha256','tree_hash')]:
            self._try(event,name,sid,'body','/result/execution/'+key)
            value=(result.get('execution') or {}).get(key)
            if value is not None:self.nodes[run_key]['attrs'][name]=copy.deepcopy(value)
        self._diagnostics(event,sid,'/result/page/text');self._diagnostics(event,sid,'/result/text')

    def ingest(self,payload,*,step,source_indices=None,episode=None,member=None):
        if (episode not in (None,self.episode) or member not in (None,self.member)):
            raise GraphScopeError('Cross-episode or cross-member graph input')
        if step<self.step:raise GraphIntegrityError('A later graph cannot answer an earlier decision')
        indices=source_indices if source_indices is not None else list(range(len(payload['messages'])))
        if len(indices)!=len(payload['messages']) or len(set(indices))!=len(indices):raise GraphIntegrityError('Source positions are ambiguous')
        self.step=step
        for index,message in zip(indices,payload['messages']):
            key=(index,digest(message))
            if key in self._seen:continue
            self._seen.add(key);sid=self._source(message,index);self.last_index=max(self.last_index,index)
            for call_index,call in enumerate(message.get('tool_calls') or []):
                name=call.get('function',{}).get('name');arguments=obj(call.get('function',{}).get('arguments'))
                action={'tool':name,'arguments':arguments,'source':sid,'index':index,'call_index':call_index}
                previous=self.actions.get(call['id'])
                if previous and (previous['tool'],previous['arguments'])!=(name,arguments):
                    raise GraphIntegrityError('A tool-call identity changed')
                if not previous:self.actions[call['id']]=action;self.action_order.append(call['id'])
                node=self.node('Action',call['id'],attrs={'tool':name,'tool_call_id':call['id'],'index':index},sources=[sid])
                self.actions[call['id']]['node']=node
            if message.get('role')=='user' and self.task is None:
                self.task=self.node('Task','issue',attrs={'kind':'visible_original_issue'},sources=[sid])
            if not is_observation(message):continue
            body=obj(message['content']);result=body.get('result',{});result=result if isinstance(result,dict) else {}
            observed=body.get('observation',{})
            if isinstance(observed,dict) and isinstance(observed.get('workspace_reference'),dict):
                self._version(source_ref({'source_reference':observed['workspace_reference']}),None,sid,current=True)
            observation=self.node('Observation',[index,digest(message)],attrs={'message_index':index,'source_id':sid},sources=[sid])
            action=self.actions.get(message.get('tool_call_id'));tool=action['tool'] if action else message.get('name')
            if action:self.edge('observed_in',action['node'],observation,sources=[sid],proof='observed_source')
            reference=source_ref(result)
            is_current=(body.get('ok') is True and tool in MUTATIONS)
            if self.current_version is None and tool=='read_file' and action and not action['arguments'].get('patch_id'):
                is_current=True
            version=self._version(reference,result.get('files_sha256'),sid,current=is_current)
            if body.get('ok') is False:
                event=self._event(['error',message.get('tool_call_id'),sid],'error',sid,index,node=observation,version=None)
                self._try(event,'error_type',sid,'body','/error/type')
                if isinstance(body.get('error',{}).get('message'),str):
                    text=body['error']['message'];self._try(event,'error_excerpt',sid,'body','/error/message',span=(0,min(len(text),320)))
                if action and safe_path(action['arguments'].get('path')):
                    self._try(event,'path',action['source'],'arguments','/path',call_index=action['call_index'])
                    self._path(event,action['arguments']['path'],action['source'])
                if action:
                    for target in (action['arguments'].get('selection') or {}).get('targets',[]):
                        self._path(event,file_of_test(target),action['source'])
                continue
            if tool in TEST_TOOLS:
                self._observe_test(result,action,sid,index,observation)
            elif tool in MUTATIONS and body.get('ok') is True and action:
                event=self._event(['mutation',message.get('tool_call_id')],'change',sid,index,node=action['node'],version=version)
                for path in result.get('paths',result.get('changed_paths',[])):
                    self._path(event,path,sid,relation='modifies',proof='successful_tool')
                for arg in ('path','destination','old_path','new_path'):
                    if safe_path(action['arguments'].get(arg)):
                        self._try(event,'path',action['source'],'arguments','/'+arg,call_index=action['call_index'])
                        self._path(event,action['arguments'][arg],action['source'],relation='modifies',proof='successful_tool')
                for arg,name in [('old','change_before'),('new','change_after'),('text','written_text')]:
                    text=action['arguments'].get(arg)
                    if isinstance(text,str):
                        self._try(event,name,action['source'],'arguments','/'+arg,call_index=action['call_index'],span=(0,min(len(text),320)))
                if tool in {'write_file','create_file'} and isinstance(action['arguments'].get('text'),str):
                    path=safe_path(action['arguments'].get('path'))
                    if path:self._ast(path,action['arguments']['text'],action['source'],version,complete=True)
            elif tool=='read_file' and action:
                path=safe_path(result.get('path') or action['arguments'].get('path'))
                if not path:continue
                event=self._event(['read',message.get('tool_call_id')],'code',sid,index,node=observation,version=version)
                self._try(event,'path',sid,'body','/result/path');self._path(event,path,sid)
                text=result.get('text');complete=result.get('start_character')==0 and result.get('end_character')==result.get('total_characters')
                self._ast(path,text,sid,version,complete=complete)
            elif tool=='diff_workspace':
                event=self._event(['diff',message.get('tool_call_id')],'diff',sid,index,node=observation,version=version)
                text=result.get('text','')
                if isinstance(text,str):
                    self._try(event,'diff_excerpt',sid,'body','/result/text',span=(0,min(len(text),500)))
                    for match in re.finditer(r'^(?:---|\+\+\+) [ab]/([^\n]+)',text,re.M):
                        self._add(event,'path',self.field(sid,'body','/result/text',span=match.span(1)))
                        self._path(event,match.group(1),sid)
            elif tool in {'fix_patch','submit_integration','delivery_status'}:
                artifact=self.node('Artifact',[tool,result.get('patch_id') or result.get('delivery_id') or message.get('tool_call_id')],sources=[sid])
                if version:self.edge('derived_from',artifact,version,sources=[sid],proof='successful_tool')
                event=self._event(['artifact',artifact],'artifact',sid,index,node=artifact,version=version)
                for key in ('patch_id','delivery_id','status','changed_paths'):
                    self._try(event,key,sid,'body','/result/'+key)
                for path in result.get('changed_paths',[]):self._path(event,path,sid)
        self._resolve_imports()
        return self

    def version_status(self,event):
        if event.get('version') is None or self.current_version is None:return 'unknown'
        return 'current_observed_version' if event['version']==self.current_version else 'historical_version'

    def focus(self):
        paths=[];sources=[]
        for aid in reversed(self.action_order):
            a=self.actions[aid];args=a['arguments'];found=[]
            if safe_path(args.get('path')):found.append(safe_path(args['path']))
            for target in (args.get('selection') or {}).get('targets',[]):
                if file_of_test(target):found.append(file_of_test(target))
            if a['tool']=='read_test_result' and args.get('report_id') in self.report_alias:
                nid=self.report_alias[args['report_id']]
                found += [p for e in self.events.values() if e['node']==nid for p in e['paths']]
            if found:
                paths.extend(found);sources.append(a['source'])
                if len(sources)==3:break
        if not paths:
            changes=sorted((e for e in self.events.values() if e['kind']=='change'),key=lambda e:e['last_index'],reverse=True)
            if changes:paths=changes[0]['paths'];sources=changes[0]['sources']
        if not paths and self.task:
            for sid in self.nodes[self.task]['sources']:
                text=self.sources[sid]['message'].get('content','')
                for match in re.finditer(r'[\w./-]+\.py\b',text):
                    path=safe_path(match.group())
                    if path:paths.append(path);sources.append(sid)
        return {'paths':sorted(set(paths)),'sources':sorted(set(sources)),
            'query_uses_future_action':False}

    def snapshot(self):
        return copy.deepcopy({'version':VERSION,'scope':[self.episode,self.member],'step':self.step,
            'current_version':self.current_version,'version_source':self.version_source,
            'nodes':self.nodes,'edges':self.edges,'events':self.events,'sources':self.sources,
            'focus':self.focus(),'ast_attempts':self.ast_attempts,
            'full_repository_graph_claimed':False,'runtime_coverage_claimed':False})
