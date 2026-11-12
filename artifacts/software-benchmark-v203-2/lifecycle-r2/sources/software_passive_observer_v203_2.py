"""Passive, durable observations; never alters tools, model inputs or world actions."""
from __future__ import annotations
import copy,hashlib,json,os
from pathlib import Path

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def parse(text):
    try:return json.loads(text) if isinstance(text,str) else {}
    except (ValueError,TypeError):return {}

def blocked_cause(tool,response,status=None):
    """Classify only explicit evidence; test failure is not an organization label."""
    if status in {'model_budget_exhausted','cash_budget_boundary'}:return 'Budget Exhaustion'
    if status in {'waiting','staff_wait'} or tool=='staff_wait':return 'Normal Waiting'
    error=response.get('error') or {};rejection=error.get('rejection') or {};code=rejection.get('code') or error.get('code')
    if code in {'environment_unavailable','executor_unavailable','container_unavailable'}:return 'Environment Failure'
    if code in {'upstream_artifact_required','unsatisfied_task_dependency'}:return 'Upstream Dependency'
    if code in {'public_argument_schema','replacement_not_unique','unknown_task_id','unknown_published_patch','tool_not_enabled','organization_assignment','organization_contract','review_required','fixed_organization_edge','fixed_organization_schedule','fixed_delivery_member'}:return 'Tool Failure'
    if status=='model_format_feedback':return 'Model Failure'
    return 'Unknown'

class PassiveState:
    def __init__(self,scope,members):
        self.scope=scope;self.members=list(members);self.initial_condition={};self.tasks={};self.owner_intervals=[];self.versions={};self.files={};self.artifacts={};self.adoptions=[];self.reads=[];self.tests={};self.deliveries=[];self.events=[];self.pending_blocks={};self.inputs={};self.phases={};self.receipt_count=0;self.seen_failed_test=set()
    def snapshot(self):
        tests=[{**t,'current_effective':t['version']==self.versions.get(t['actor'])} for t in self.tests.values()]
        return copy.deepcopy({'scope':self.scope,'members':self.members,'initial_condition':self.initial_condition,'tasks':self.tasks,'owner_intervals':self.owner_intervals,'versions':self.versions,
            'files':list(self.files.values()),'artifacts':self.artifacts,'adoptions':self.adoptions,'reads':self.reads,'tests':tests,'deliveries':self.deliveries,
            'event_count':len(self.events),'receipt_count':self.receipt_count,'observer_only':True,'not_automatically_agent_visible':True})
    def phase(self,name,source,**metadata):
        if name not in self.phases:self.phases[name]={'phase':name,'source':copy.deepcopy(source),'metadata':metadata,'state':self.snapshot()}
    def event(self,kind,source,**body):
        e={'event_id':f'{self.scope}:e{len(self.events)+1}','kind':kind,'source':copy.deepcopy(source),**copy.deepcopy(body)};self.events.append(e);return e
    def apply(self,record):
        kind=record['kind'];source=record['source'];p=record['payload'];actor=p.get('actor')
        if kind=='INITIAL':self.initial_condition=copy.deepcopy(p);self.phase('T0',source,meaning='frozen_initial_condition');return
        if actor not in self.members:raise ValueError('Unknown observation member')
        if kind=='INTENT':
            if p['tool']=='submit_integration':self.phase('T6',source,meaning='before_first_submission_attempt',future_result_included=False)
            return
        if kind=='INPUT_ACCEPTED':
            mode=p['mode'];wire=p['wire'];self.inputs[p['request_id']]={'actor':actor,'source':source,'mode':mode}
            for mi,m in enumerate(wire.get('messages',[])):
                if m.get('role')!='user':continue
                o=parse(m.get('content')).get('observation',{})
                if not isinstance(o,dict) or o.get('actor_id')!=actor:continue
                for h in o.get('handoffs',[]):
                    if h.get('recipient')==actor:self.event('Handoff Presented',source,actor=actor,request_id=p['request_id'],message_index=mi,sequence=h.get('sequence'),
                        patch_id=h.get('patch_id'),source_version=h.get('source_reference'),evidence_mode=mode,full_message_read_not_inferred=True)
            return
        if kind=='LIFECYCLE':
            cause=blocked_cause(p.get('tool'),{},p.get('status'))
            self.event('Member Execution Boundary',source,actor=actor,status=p.get('status'),cause=cause,task_dependency_not_inferred=True);return
        if kind!='RECEIPT':raise ValueError('Unknown observer event')
        self.receipt_count+=1;tool=p['tool'];args=p['arguments'];response=p['response'];r=response.get('result') or {};ok=response.get('ok') is True
        if not ok:
            cause=blocked_cause(tool,response);task=args.get('task_id');e=self.event('Operation Rejected',source,actor=actor,tool=tool,task_id=task,cause=cause,
                error=response.get('error'),organization_misalignment_not_inferred=True)
            if task:self.pending_blocks[(actor,tool,task)]=e['event_id']
            return
        task=r.get('task_id') if isinstance(r,dict) else None
        if (actor,tool,args.get('task_id')) in self.pending_blocks:
            prior=self.pending_blocks.pop((actor,tool,args['task_id']));self.event('Operation Resumed',source,actor=actor,tool=tool,task_id=args['task_id'],prior_rejection=prior,causal_necessity_not_inferred=True)
        if tool in {'create_task','claim_task','return_task','revise_task','accept_transfer','declare_dependency','clear_dependency'} and task:
            old=self.tasks.get(task);self.tasks[task]=copy.deepcopy(r)
            if old is None or old.get('owner')!=r.get('owner') or old.get('revision')!=r.get('revision'):
                for interval in self.owner_intervals:
                    if interval['task_id']==task and interval['valid_to'] is None:interval['valid_to']=len(self.events)+1
                if r.get('owner'):self.owner_intervals.append({'task_id':task,'owner':r['owner'],'revision':r.get('revision'),'created_by':r.get('created_by'),
                    'valid_from':len(self.events)+1,'valid_to':None,'source':copy.deepcopy(source),'not_file_ownership':True})
            self.event({'create_task':'Task Created','claim_task':'Task Claimed','return_task':'Task Returned','revise_task':'Task Revised','accept_transfer':'Owner Transfer Accepted',
                'declare_dependency':'Dependency Proposed','clear_dependency':'Dependency Declaration Removed'}[tool],source,actor=actor,task=copy.deepcopy(r),semantic_dependency_confirmed=False)
            if tool in {'create_task','claim_task'}:self.phase('T1',source,meaning='first_task_board_activity',ownership_may_still_be_unclaimed=True)
            if tool=='accept_transfer':self.phase('T5',source,meaning='accepted_responsibility_change')
        if tool in {'org_matrix_scope','org_chief_assign'} and r.get('assignee'):self.event('Task Assigned',source,actor=actor,assignment=r,ownership_not_inferred=True)
        if tool in {'offer_transfer','decline_transfer'}:self.event('Owner Transfer Offered' if tool=='offer_transfer' else 'Owner Transfer Rejected',source,actor=actor,record=r)
        version=r.get('source_reference');mutations={'write_file','replace_file','create_file','delete_file','rename_file','integrate_patch'}
        if tool in mutations:
            previous=self.versions.get(actor);self.versions[actor]=version;paths=r.get('paths') or r.get('changed_paths') or ([args['path']] if args.get('path') else [])
            for path in paths:self.files[(actor,path)]={'path':path,'actor':actor,'last_observed_change_version':version,'observed_tree_hash':r.get('files_sha256'),'source':copy.deepcopy(source)}
            self.event('Code State Changed',source,actor=actor,tool=tool,version=version,paths=paths,previous_known_version=previous,
                content_change=p.get('content_change','not_verified'),whole_source_not_lifted_to_business_graph=True)
            if tool!='integrate_patch' and p.get('content_change') is not False:self.phase('T2',source,meaning='first_accepted_edit',exact_content_change=p.get('content_change','not_verified'))
            if actor in self.seen_failed_test and tool!='integrate_patch':self.phase('T5',source,meaning='edit_after_observed_failed_test',rework_cause_not_proven=True)
        if tool=='fix_patch' and r.get('patch_id'):
            self.artifacts[r['patch_id']]={**copy.deepcopy(r),'source':copy.deepcopy(source),'published':True,'author':r.get('author',actor)}
            self.event('Artifact Created',source,actor=actor,patch_id=r['patch_id'],version=version,author=r.get('author',actor))
            self.event('Artifact Published',source,actor=actor,patch_id=r['patch_id'],version=version,publication_contract='existing_exact_fixed_version_grant',read_or_adoption_not_inferred=True)
            self.phase('T3',source,meaning='first_published_artifact_or_peer_consumption',does_not_prove_received=True)
        if tool=='handoff_patch':self.event('Handoff Sent',source,actor=actor,record=r,presented_not_inferred=True)
        if tool=='read_file':
            self.versions.setdefault(actor,version) if not args.get('patch_id') else None
            if args.get('patch_id'):
                patch=self.artifacts.get(args['patch_id']);record={'reader':actor,'patch_id':args['patch_id'],'version':version,'path':r.get('path'),'source':copy.deepcopy(source),
                    'author':patch.get('author') if patch else None,'source_bound':bool(patch and patch.get('source_reference')==version)}
                self.reads.append(record);self.event('Artifact Read',source,**{k:v for k,v in record.items() if k!='source'},task_dependency_not_inferred=True)
                if patch and patch['author']!=actor:self.phase('T3',source,meaning='first_peer_artifact_read')
        if tool=='integrate_patch':
            patch=self.artifacts.get(args.get('patch_id'));record={'adopter':actor,'patch_id':args.get('patch_id'),'recipient_version':version,'author':patch.get('author') if patch else None,
                'original_source_version':patch.get('source_reference') if patch else None,'source':copy.deepcopy(source),'source_bound':bool(patch)}
            self.adoptions.append(record);self.event('Artifact Adopted',source,**{k:v for k,v in record.items() if k!='source'},validation_not_inferred=True)
            self.phase('T5',source,meaning='first_integration')
        if tool in {'run_tests','read_test_result'} and r.get('report_id') and r.get('executed') is True:
            if tool=='run_tests':self.versions.setdefault(actor,version)
            key=(actor,r['report_id']);old=self.tests.get(key)
            if old and (old['version']!=version or old['passed']!=r.get('passed')):raise ValueError('Immutable test identity mismatch')
            if old is None:
                self.tests[key]={'actor':actor,'report_id':r['report_id'],'version':version,'selector':args.get('selection'),'passed':r.get('passed'),'source':copy.deepcopy(source)}
                self.event('Test Executed',source,**{k:v for k,v in self.tests[key].items() if k!='source'},public_only=True)
                if r.get('passed') is False:
                    self.seen_failed_test.add(actor);self.phase('T4',source,meaning='first_observed_executed_failed_test',environment_or_code_cause_not_inferred=True)
        if tool=='submit_integration':
            self.deliveries.append({'actor':actor,**copy.deepcopy(r),'source':copy.deepcopy(source)})
            self.event('Delivery Recorded',source,actor=actor,delivery=r,official_score_not_inferred=True)

def serializable_state(state):
    return state.snapshot()

class PassiveRecorder:
    def __init__(self,folder,scope,members,*,writer=None):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.state=PassiveState(scope,members);self.pending=[];self.faults=[];self.seen={};self.head=None;self.writer=writer or self._append
        if (self.folder/'events.jsonl').exists():raise ValueError('Existing observation segment must be replayed or resumed explicitly')
    def _append(self,row):
        with (self.folder/'events.jsonl').open('ab') as f:f.write((json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n').encode());f.flush();os.fsync(f.fileno())
    def submit(self,kind,key,payload,source=None):
        record={'kind':kind,'key':key,'payload':copy.deepcopy(payload),'source':copy.deepcopy(source or {'capture_key':key,'payload_structure_sha256':digest(payload)})}
        self.pending.append(record);self.flush()
    def flush(self):
        while self.pending:
            r=self.pending[0];signature=digest(r)
            try:
                if r['key'] in self.seen:
                    if self.seen[r['key']]!=signature:raise ValueError('Observation key reused for different bytes')
                    self.pending.pop(0);continue
                staged=copy.deepcopy(self.state);staged.apply(r);row={'previous':self.head,'record':r};row['sha256']=digest(row);self.writer(row)
                self.head=row['sha256'];self.state=staged;self.seen[r['key']]=signature;self.pending.pop(0)
            except Exception as e:
                self.faults.append({'key':r['key'],'error':repr(e),'world_action_must_not_be_replayed':True});break
    def initialize(self,source,initial_condition=None):self.submit('INITIAL','initial',initial_condition or {},source)
    def intent(self,actor,tool,args,key):self.submit('INTENT','intent:'+actor+':'+key,{'actor':actor,'tool':tool,'arguments':args})
    def receipt(self,actor,tool,args,response,key):self.submit('RECEIPT','receipt:'+actor+':'+key,{'actor':actor,'tool':tool,'arguments':args,'response':response})
    def input_accepted(self,actor,request_id,wire,provider_receipt,*,mode='real_provider'):
        if mode not in {'real_provider','cpu_scripted'}:raise ValueError('Unknown transport evidence mode')
        if not provider_receipt.get('id') or not isinstance(provider_receipt.get('usage'),dict):raise ValueError('Prepared input alone does not prove accepted model request')
        usage=provider_receipt['usage'];values=[usage.get(k) for k in ['prompt_tokens','completion_tokens','total_tokens']]
        if any(type(v) is not int or v<0 for v in values) or values[0]+values[1]!=values[2]:raise ValueError('Accepted-input witness needs consistent actual usage')
        self.submit('INPUT_ACCEPTED','input:'+request_id,{'actor':actor,'request_id':request_id,'wire':wire,'provider_receipt':provider_receipt,'mode':mode})
    @staticmethod
    def replay(path,scope,members):
        raw=Path(path).read_bytes();lines=raw.splitlines(keepends=True);state=PassiveState(scope,members);head=None;complete=0;incomplete=False
        for i,line in enumerate(lines):
            if not line.endswith(b'\n'):
                if i==len(lines)-1:incomplete=True;break
                raise ValueError('Nonfinal incomplete journal record')
            row=json.loads(line);claimed=row.pop('sha256')
            if row['previous']!=head or digest(row)!=claimed:raise ValueError('Observer journal chain mismatch')
            state.apply(row['record']);head=claimed;complete+=1
        return state,{'complete_records':complete,'incomplete_tail':incomplete,'last_hash':head,'original_bytes_sha256':hashlib.sha256(raw).hexdigest()}

class ObservedPort:
    """Explicit optional wrapper of the existing HarnessPort, no new tool names."""
    def __init__(self,port,actor,observer):self.inner=port;self.actor=actor;self.observer=observer;self.ordinal=0
    def __getattr__(self,name):return getattr(self.inner,name)
    def call(self,tool,**kwargs):
        key=kwargs.get('request_key') or f'local-{self.ordinal}';self.ordinal+=1
        args={k:v for k,v in kwargs.items() if k not in {'request_key','association'}}
        try:self.observer.intent(self.actor,tool,args,key)
        except Exception as e:self.observer.faults.append({'key':key,'error':repr(e),'stage':'intent','primary_execution_continues':True})
        response=self.inner.call(tool,**kwargs)
        try:self.observer.receipt(self.actor,tool,args,response,key)
        except Exception as e:self.observer.faults.append({'key':key,'error':repr(e),'stage':'receipt','original_result_retained':True})
        return response

def observed_model_invoke(observer,actor,request_id,wire,invoke,*,mode='real_provider'):
    """Caller supplies the existing transport; returns its original result unchanged."""
    result=invoke(wire)
    try:observer.input_accepted(actor,request_id,wire,{'id':result.get('id'),'usage':result.get('usage')},mode=mode)
    except Exception as e:observer.faults.append({'request_id':request_id,'error':repr(e),'original_result_retained':True})
    return result
