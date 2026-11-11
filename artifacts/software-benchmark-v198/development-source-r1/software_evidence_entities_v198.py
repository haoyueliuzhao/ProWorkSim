"""Sourced entity identities; partial text stays a Reference, not a definition.

Only supplied, previously visible sources are consumed. Base Git commit and
private workspace revisions are explicitly different. No repository I/O.
"""
from __future__ import annotations
import ast,copy,json,re
from collections import defaultdict
from .software_context_compression_v175 import digest
from .software_context_graph_v196 import obj,safe_path,source_ref,GraphIntegrityError

VERSION='v198-observed-entity-and-evidence-registry-r1'


class EvidenceEntities:
    def __init__(self,snapshot,*,repo,base_commit,issue_id):
        if not re.fullmatch('[0-9a-f]{40}',base_commit):raise ValueError('Actual base commit SHA required')
        self.snapshot=snapshot;self.repo=repo;self.base_commit=base_commit;self.issue_id=issue_id
        self.scope=snapshot['scope'];self.entities={};self.edges={};self.event_bindings={};self.source_bindings={};self.fragments=[];self.full_files={};self.parse_errors=[]
        self.repository=self.entity('Repository',{'repo':repo})
        self.commit=self.entity('Commit',{'repo':repo,'commit':base_commit},base_commit_only=True)
        self.task=self.entity('Task',{'repo':repo,'issue':issue_id,'subtask':'root_goal'})
        self._build()

    def entity(self,kind,identity,**attrs):
        # Private scope is part of the storage key even for repository identities.
        key='ent:'+digest([self.scope,kind,identity])[:32]
        if key not in self.entities:self.entities[key]={'id':key,'kind':kind,'identity':copy.deepcopy(identity),'scope':self.scope,'attrs':copy.deepcopy(attrs)}
        return key

    def revision(self,reference):
        return {'base_commit':self.base_commit,'workspace_reference':reference,'edited_workspace_is_git_commit':False}

    def file(self,path,reference):
        if not safe_path(path):return None
        return self.entity('File',{'repo':self.repo,'revision':self.revision(reference),'path':path},definition_seen=False)

    def edge(self,left,right,relation,sources,*,status='Confirmed',proof='observed_binding',reference=None,spans=None):
        if left not in self.entities or right not in self.entities or not sources:raise GraphIntegrityError('Unbound edge')
        if any(s not in self.snapshot['sources'] for s in sources):raise GraphIntegrityError('Unseen edge source')
        if status=='Confirmed' and relation in {'resolves_to','runtime_calls','caused_by'}:raise GraphIntegrityError('Resolution/causality not verified by textual similarity')
        key='edge:'+digest([left,right,relation,status,proof,reference])[:32]
        first=min(self.snapshot['sources'][s]['first_seen_step'] for s in sources)
        row=self.edges.setdefault(key,{'edge_id':key,'source_entity_id':left,'target_entity_id':right,'relation_type':relation,
            'evidence_source_ids':[],'evidence_spans':[],'repository_commit':self.base_commit,'workspace_reference':reference,
            'valid_from':first,'valid_until':None,'confidence':'observed' if status=='Confirmed' else 'unverified_candidate',
            'verification_status':status,'proof':proof,'runtime_dispatch_verified':False})
        row['evidence_source_ids']=sorted(set(row['evidence_source_ids'])|set(sources))
        for span in spans or []:
            if span not in row['evidence_spans']:row['evidence_spans'].append(span)
        if reference and self.current_reference and reference!=self.current_reference:
            row['effective_for_current_workspace']=False
            later=[t for t,r in self.transitions if r!=reference and t>first]
            row['valid_until']=min(later) if later else None
        else:row['effective_for_current_workspace']=True
        return key

    def _build(self):
        s=self.snapshot;sources=s['sources'];self.current_reference=s['nodes'][s['current_version']]['attrs']['source_reference'] if s['current_version'] else None
        action_names={c['id']:c['function']['name'] for source in sources.values() for c in source['message'].get('tool_calls',[])}
        self.transitions=[];highest=-1;last=None
        for sid,source in sorted(sources.items(),key=lambda x:(x[1]['first_seen_step'],x[1]['message_index'],x[0])):
            m=source['message'];b=obj(m.get('content'));o=b.get('observation',{});r=b.get('result',{});r=r if isinstance(r,dict) else {}
            ref=o.get('workspace_reference') if isinstance(o,dict) else None
            if b.get('ok') is True and (m.get('name') or action_names.get(m.get('tool_call_id'))) in {'write_file','replace_file','create_file','delete_file','rename_file','integrate_patch'}:ref=source_ref(r)
            if ref and source['message_index']>=highest:
                highest=source['message_index']
                if ref!=last:self.transitions.append((source['first_seen_step'],ref));last=ref
        for sid,source in sources.items():
            eid=self.entity('Observation',{'episode':self.scope[0],'member':self.scope[1],'message_index':source['message_index'],'content_hash':source['message_sha256']},source_id=sid,role=source['message'].get('role'))
            self.source_bindings[sid]=eid
        for old,n in s['nodes'].items():
            if n['type']=='Version':self.entity('Version',{'repo':self.repo,'revision':self.revision(n['attrs']['source_reference'])},source_ids=n['sources'])
        for eid,e in s['events'].items():
            ref=s['nodes'][e['version']]['attrs']['source_reference'] if e.get('version') else None
            binding=[]
            for path in e['paths']:
                file=self.file(path,ref)
                if file:
                    binding.append(file)
                    for sid in e['sources']:self.edge(self.source_bindings[sid],file,'evidence_about', [sid],reference=ref,
                        spans=[{'source_id':sid,'kind':'observed_path_binding','path':path,'no_runtime_coverage_claim':True}])
            if e['kind']=='test':
                old_node=s['nodes'][e['node']];run=self.entity('TestRun',{'episode':self.scope[0],'member':self.scope[1],'report_id':old_node['attrs']['report_id']},
                    source_reference=ref,source_ids=e['sources'],passed=e.get('passed'),selector=old_node['attrs'].get('selector'))
                binding.append(run)
                if ref:
                    ver=self.entity('Version',{'repo':self.repo,'revision':self.revision(ref)})
                    self.edge(run,ver,'validates',e['sources'],reference=ref,proof='actual_selected_public_run_not_full_correctness',
                        spans=[{'source_id':sid,'pointer':'/result/source_reference'} for sid in e['sources']])
                for f in e['fields']:
                    if f['name']=='failed_test':
                        definition=self.entity('TestDefinition',{'repo':self.repo,'revision':self.revision(ref),'node_id':f['value']},
                            body_seen=False,identity_evidence='name_reported_in_visible_failure',source_ids=[f['origin']['source_id']])
                        binding.append(definition);self.edge(run,definition,'reports_test', [f['origin']['source_id']],reference=ref,spans=[f['origin']])
            elif e['kind']=='artifact':
                binding.append(self.entity('Artifact',{'episode':self.scope[0],'original_entity':e['node'],'revision':self.revision(ref)},source_ids=e['sources']))
            self.event_bindings[eid]=sorted(set(binding))
        groups=defaultdict(list)
        for sid,source in sources.items():
            m=source['message'];b=obj(m.get('content'));r=b.get('result',{});r=r if isinstance(r,dict) else {}
            if (m.get('name') or action_names.get(m.get('tool_call_id')))!='read_file' or b.get('ok') is not True or not isinstance(r.get('text'),str):continue
            path=safe_path(r.get('path'));ref=source_ref(r);a,z,total=r.get('start_character'),r.get('end_character'),r.get('total_characters')
            if not path or not ref:continue
            if all(type(x)is int for x in [a,z,total]) and 0<=a<=z<=total and z-a==len(r['text']):
                groups[(path,digest(ref))].append((a,z,total,r['text'],sid,ref))
            else:
                self.entity('Reference',{'repo':self.repo,'revision':self.revision(ref),'path':path,'fragment_hash':digest(r['text'])},
                    reason='missing_exact_file_coverage',qualified_name=None,source_ids=[sid])
        for (path,_),pieces in groups.items():
            pieces.sort(key=lambda p:(p[0],-p[1],p[4]));ref=pieces[0][5];total=pieces[0][2];text='';used=[];conflict=False
            for a,z,n,part,sid,_ in pieces:
                if n!=total:conflict=True;break
                if a>len(text):break
                overlap=min(len(text)-a,len(part))
                if overlap and text[a:a+overlap]!=part[:overlap]:conflict=True;break
                if z>len(text):text+=part[overlap:]
                used.append(sid)
            complete=not conflict and len(text)==total
            self.fragments.append({'path':path,'source_reference':ref,'complete':complete,'conflict':conflict,'visible_intervals':[(x[0],x[1]) for x in pieces]})
            if not complete:
                for a,z,n,part,sid,_ in pieces:
                    self.entity('Reference',{'repo':self.repo,'revision':self.revision(ref),'path':path,'span':[a,z],'fragment_hash':digest(part)},
                        reason='partial_file_not_qualified_definition',qualified_name=None,source_ids=[sid])
                continue
            try:tree=ast.parse(text)
            except (SyntaxError,ValueError) as error:self.parse_errors.append({'path':path,'reason':type(error).__name__});continue
            file=self.file(path,ref);self.entities[file]['attrs'].update(definition_seen=True,content_sha256=digest(text),source_ids=used)
            self.full_files[(path,digest(ref))]={'file':file,'text':text,'tree':tree,'sources':used,'reference':ref}
            def visit(body,parents=()):
                for n in body:
                    if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):continue
                    qual='.'.join((*parents,n.name));signature=ast.dump(n.args,include_attributes=False) if hasattr(n,'args') else ','.join(ast.unparse(v) for v in n.bases)
                    symbol=self.entity('Symbol',{'repo':self.repo,'revision':self.revision(ref),'path':path,'qualified_name':qual,'signature':signature},
                        source_ids=used,lines=[n.lineno,n.end_lineno],syntax_kind=type(n).__name__)
                    spans=[{'source_id':sid,'pointer':'/result/text','complete_file_lines':[n.lineno,n.end_lineno],'assembly_sources':used} for sid in used]
                    self.edge(file,symbol,'declares',used,reference=ref,proof='complete_visible_file_AST',spans=spans)
                    pending=list(n.body)
                    while pending:
                        node=pending.pop()
                        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)):continue
                        pending.extend(ast.iter_child_nodes(node))
                        if isinstance(node,ast.Call):
                            name=ast.unparse(node.func);target=self.entity('Reference',{'repo':self.repo,'revision':self.revision(ref),'path':path,'owner':qual,'name':name,'line':node.lineno},
                                qualified_name=None,reason='runtime_target_unresolved',source_ids=used)
                            self.edge(symbol,target,'references',used,reference=ref,proof='literal_call_expression_not_dispatch',
                                spans=[{'source_id':sid,'pointer':'/result/text','complete_file_lines':[node.lineno,node.end_lineno]} for sid in used])
                    visit(n.body,(*parents,n.name))
            visit(tree.body)
        # Static module targets are candidates, never promoted to runtime facts.
        for (path,version),f in self.full_files.items():
            for n in ast.walk(f['tree']):
                if not isinstance(n,ast.ImportFrom):continue
                package=path.split('/')[:-1];prefix=package[:len(package)-n.level+1] if n.level else []
                module='/'.join(prefix+(n.module or '').split('.')).strip('/')
                options=[t for (t,v) in self.full_files if v==version and t in {module+'.py',module+'/__init__.py'}]
                for target_path in options:
                    self.edge(f['file'],self.full_files[target_path,version]['file'],'resolves_to',f['sources']+self.full_files[target_path,version]['sources'],
                        status='Inferred',proof='complete_files_static_import_candidate_not_runtime_resolution',reference=f['reference'],
                        spans=[{'source_id':sid,'pointer':'/result/text','complete_file_lines':[n.lineno,n.end_lineno]} for sid in f['sources']])

    def as_json(self):
        return copy.deepcopy({'version':VERSION,'repo':self.repo,'base_commit':self.base_commit,'scope':self.scope,'entities':self.entities,
            'edges':self.edges,'event_bindings':self.event_bindings,'source_bindings':self.source_bindings,
            'coverage':self.fragments,'parse_errors':self.parse_errors,'runtime_resolution_claimed':False})
