"""Evidence-only cross-graph projection; policy proposals never rewrite receipts."""
from __future__ import annotations
import copy,hashlib,json
from .storage import json_bytes,digest

def identity(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def completeness(fact):
    """Independent axes; no complete enclosing scope invented from a fragment."""
    statement_types={'Assign','AnnAssign','AugAssign','Return','Assert','Import','ImportFrom','Expr'}
    return {'span_complete':True,'statement_complete':bool(fact.get('node_syntax_complete') and fact.get('syntax_node_type') in statement_types),
        'scope_complete':bool(fact.get('qualified_scope_known')),'file_complete':bool(fact.get('file_source_complete')),
        'semantic_relevance_established':False}

class CrossGraph:
    """Read-only projection of actual managed receipts, not a new task manager."""
    def __init__(self,scope,members):
        self.scope=scope;self.members=set(members);self.tasks={};self.patches={};self.versions={};self.tests={};self.edges=[];self.events=[];self.ids={};self.snapshots=[]
    def edge(self,kind,src,dst,evidence,step,**fields):
        row={'kind':kind,'source':src,'target':dst,'evidence_ids':[evidence],'valid_from':step,'valid_to':None,'status':'Confirmed Structural',**fields}
        row['id']='edge:'+identity([self.scope,row]);self.edges.append(row);return row
    def observe(self,event):
        eid=event['id'];signature=identity(event)
        if eid in self.ids:
            if self.ids[eid]!=signature:raise ValueError('Conflicting event identity')
            return
        retained={'events','snapshots'};before={k:copy.deepcopy(v) for k,v in self.__dict__.items() if k not in retained};lengths={k:len(getattr(self,k)) for k in retained}
        try:
            actor=event['actor'];action=event['action'];args=event['arguments'];r=event['result'];step=event['step']
            if actor not in self.members or not event['source']:raise ValueError('Unbound member/source')
            if event.get('ok') is True:
                version=r.get('source_reference')
                if version and action in {'write_file','replace_file','create_file','delete_file','rename_file','integrate_patch'}:self.versions[actor]=version
                elif version and action in {'read_file','run_tests'} and not args.get('patch_id') and not args.get('source_reference'):self.versions.setdefault(actor,version)
                if action in {'create_task','claim_task','return_task','revise_task','accept_transfer','declare_dependency','clear_dependency'} and r.get('task_id'):
                    task=r['task_id'];old=self.tasks.get(task);self.tasks[task]=copy.deepcopy(r)
                    for e in self.edges:
                        if e['valid_to'] is None and ((e['kind']=='owns' and e['target']==task) or (e['kind']=='depends_on' and e['source']==task)):e['valid_to']=step
                    if r.get('owner'):
                        if r['owner'] not in self.members:raise ValueError('Foreign task owner')
                        self.edge('owns',r['owner'],task,eid,step,task_revision=r.get('revision'),not_file_ownership=True)
                    for dependency in r.get('depends_on',[]):self.edge('depends_on',task,dependency,eid,step,task_revision=r.get('revision'),upstream_revision=r.get('dependency_revisions',{}).get(dependency))
                if action in {'org_matrix_scope','org_chief_assign'} and r.get('assignee') and r.get('task_id'):
                    self.edge('assigned_to',r['task_id'],r['assignee'],eid,step,task_revision=r.get('task_revision'),does_not_claim_ownership=True)
                if action=='fix_patch' and r.get('patch_id'):
                    self.patches[r['patch_id']]={**r,'source_event':eid}
                    self.edge('authored',r.get('author',actor),r['patch_id'],eid,step,version=version)
                    for task in args.get('task_ids',[]):self.edge('artifact_for_task',r['patch_id'],task,eid,step,version=version)
                if action=='handoff_patch':
                    patch=self.patches.get(r.get('patch_id'));recipient=r.get('recipient')
                    if not patch or recipient not in self.members:raise ValueError('Unbound handoff')
                    self.edge('handoff_to',r['patch_id'],recipient,eid,step,version=patch['source_reference'],sender=actor,delivered_to_harness=True,presented=None,used=None)
                if action=='integrate_patch':
                    patch=self.patches.get(args.get('patch_id'))
                    if not patch:raise ValueError('Unbound adopted artifact')
                    self.edge('adopts',actor,args['patch_id'],eid,step,author=patch['author'],source_version=patch['source_reference'],recipient_version=version,does_not_validate=True)
                if action in {'run_tests','read_test_result'} and r.get('executed') is True and r.get('report_id'):
                    key=actor+':'+r['report_id'];prior=self.tests.get(key)
                    if prior and (prior['version']!=version or prior['passed']!=r['passed']):raise ValueError('TestRun identity conflict')
                    if prior is None:
                        self.tests[key]={'version':version,'passed':r['passed'],'actor':actor}
                        self.edge('validates',key,identity(version),eid,step,version=version,actor=actor,passed=r['passed'],selector=args.get('selection'),scope='actual_public_test_only')
                if action in {'org_review_patch','org_review_decide','org_matrix_review'} and args.get('patch_id'):
                    self.edge('reviews',actor,args['patch_id'],eid,step,decision=args.get('decision'),not_task_owner=True)
            self.events.append(copy.deepcopy(event));self.ids[eid]=signature
            active=[copy.deepcopy(e) for e in self.edges if e['valid_to'] is None]
            for e in active:
                if e['kind']=='validates':e['current_effective']=self.versions.get(e['actor'])==e['version']
            self.snapshots.append({'step':step,'tasks':copy.deepcopy(self.tasks),'versions':copy.deepcopy(self.versions),'edges':active})
        except Exception:
            self.__dict__.update(before)
            for k,n in lengths.items():del getattr(self,k)[n:]
            raise

class CompleteSourceReplay:
    """Observer-side reconstruction checked against original whole-tree hashes.

    Initial bytes remain observer material, never fabricated historical inputs.
    Complex/conflicting merges are left Unknown; no source is guessed.
    """
    def __init__(self,baseline,members):
        self.baseline=copy.deepcopy(baseline);self.files={m:dict(baseline['files']) for m in members};self.metadata={m:dict(baseline['entry_metadata']) for m in members};self.patches={};self.records=[]
    def observe(self,event):
        if not event['ok']:return None
        a=event['actor'];tool=event['action'];args=event['arguments'];r=event['result'];current=self.files[a];meta=self.metadata[a]
        mutations={'write_file','replace_file','create_file','delete_file','rename_file','integrate_patch'}
        if tool not in mutations|{'fix_patch'}:return None
        rec={'event_id':event['id'],'actor':a,'action':tool,'version':r.get('source_reference'),'files_sha256':r.get('files_sha256'),'source':event['source'],'status':'unknown','documents':[]}
        try:
            if current is None:raise ValueError('Earlier unresolved edit in this private workspace')
            after=dict(current);newmeta=dict(meta);paths=list(r.get('paths',r.get('changed_paths',[])))
            if tool in {'write_file','create_file'}:
                after[args['path']]=args['text']
                if tool=='create_file':newmeta[args['path']]={'kind':'file','encoding':'utf-8','mode':'100644'}
            elif tool=='replace_file':
                old=args['old'];text=after[args['path']]
                if not old or text.count(old)!=1:raise ValueError('Exact replacement precondition mismatch')
                after[args['path']]=text.replace(old,args['new'],1)
            elif tool=='delete_file':del after[args['path']];del newmeta[args['path']]
            elif tool=='rename_file':after[args['new_path']]=after.pop(args['path']);newmeta[args['new_path']]=newmeta.pop(args['path'])
            elif tool=='integrate_patch':
                remote=self.patches[args['patch_id']]
                # Structural equality cases of the existing Harness's diff3.
                # Nontrivial overlapping edits remain unknown in this audit.
                def entry(files,metadata,path):return (files[path],metadata[path]) if path in files else None
                for p in sorted(set(self.baseline['files'])|set(after)|set(remote['files'])):
                    base=entry(self.baseline['files'],self.baseline['entry_metadata'],p);local=entry(after,newmeta,p);incoming=entry(remote['files'],remote['metadata'],p)
                    if local==base or local==incoming:merged=incoming
                    elif incoming==base:merged=local
                    else:raise ValueError('Nontrivial merge needs original immutable postimage')
                    if merged is None:after.pop(p,None);newmeta.pop(p,None)
                    else:after[p],newmeta[p]=merged
            if not r.get('files_sha256') or digest(json_bytes(after))!=r['files_sha256']:raise ValueError('Full files hash differs from original receipt')
            if r.get('entry_metadata_sha256') and digest(json_bytes(newmeta))!=r['entry_metadata_sha256']:raise ValueError('Metadata hash differs from original receipt')
            rec['status']='complete_verified'
            for p in paths:
                if p in after and isinstance(after[p],str):rec['documents'].append({'path':p,'text':after[p],'source_hash':digest(after[p].encode()),'version':r['source_reference'],
                    'file_complete':True,'observer_only':True,'historical_agent_presented':False,'derivation':'initial_captured_tree_plus_prior_accepted_edits_plus_whole_tree_receipt_hash'})
            if tool=='fix_patch':self.patches[r['patch_id']]={'files':dict(after),'metadata':dict(newmeta),'author':a,'version':r['source_reference']}
            else:self.files[a],self.metadata[a]=after,newmeta
        except (ValueError,KeyError,TypeError) as error:
            rec['reason']=str(error)
            if tool in mutations:self.files[a]=None;self.metadata[a]=None
        self.records.append(rec);return rec
