"""Dependency observability contract; no actor tool can self-confirm a dependency.

This observer never executes policy proposals or mutates the managed world.
The trusted verifier boundary is explicit; independent checks must cite original
version-bound artifacts, not a model's confidence or policy feedback.
"""
import copy,hashlib,json
from pathlib import Path

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
class EvidenceError(ValueError):pass

class DependencyEvidence:
    def __init__(self):self.sources={};self.relations={};self.events=[];self.blocked={}
    def source(self,path,pointer,origin,producer):
        if origin not in {'actor_proposal','harness_receipt','captured_input','independent_check','policy_feedback'}:raise EvidenceError('Unknown authority boundary')
        raw=Path(path).read_bytes();value=json.loads(raw)
        for part in pointer.strip('/').split('/') if pointer else []:
            part=part.replace('~1','/').replace('~0','~');value=value[int(part)] if isinstance(value,list) else value[part]
        row={'path':str(Path(path).resolve()),'pointer':pointer,'file_sha256':hashlib.sha256(raw).hexdigest(),'payload_sha256':digest(value),
            'payload':copy.deepcopy(value),'origin':origin,'producer':producer}
        sid='evidence:'+digest(row);self.sources[sid]=row;return sid
    def emit(self,kind,**data):
        event={'sequence':len(self.events)+1,'kind':kind,**copy.deepcopy(data)};self.events.append(event);return event
    def propose(self,source_entity,target_entity,relation_type,versions,evidence,proposer):
        layers={'code_depends_on':'software','task_depends_on':'task','crosses_region':'organization'}
        if relation_type not in layers or evidence not in self.sources or not versions:raise EvidenceError('Unbound relation')
        prefix='code:' if relation_type=='code_depends_on' else 'task:'
        if not source_entity.startswith(prefix) or not target_entity.startswith(prefix):raise EvidenceError('Code and task dependencies cannot substitute for one another')
        source=self.sources[evidence]
        if source['producer']!=proposer:raise EvidenceError('Proposal identity differs from source')
        rid='relation:'+digest([source_entity,target_entity,relation_type,versions,evidence]);existing=self.relations.get(rid)
        if existing:return rid
        row={'relation_id':rid,'source_entity':source_entity,'target_entity':target_entity,'relation_type':relation_type,'layer':layers[relation_type],
            'evidence_source':[evidence],'evidence_span':[source['pointer']],'source_version':copy.deepcopy(versions),'valid_from':len(self.events)+1,'valid_to':None,
            'evidence_level':'Inferred' if source['origin']!='policy_feedback' else 'Unknown','proposer':proposer,'verifier':None,'status':'candidate'}
        self.relations[rid]=row;self.emit('DEPENDENCY_PROPOSED',relation=rid,evidence=evidence);return rid
    def confirm(self,rid,evidence,verifier):
        r=self.relations[rid];src=self.sources[evidence];p=src['payload']
        if src['origin']!='independent_check' or src['producer']!=verifier or verifier==r['proposer']:raise EvidenceError('Self declarations, adoption and policy feedback cannot confirm dependency')
        required={'relation_id':rid,'source_entity':r['source_entity'],'target_entity':r['target_entity'],'source_version':r['source_version'],'verdict':'supported','verifier':verifier}
        if any(p.get(k)!=v for k,v in required.items()) or not p.get('checks') or not all(c.get('passed') is True and c.get('original_witness') for c in p['checks']):raise EvidenceError('Independent version-bound checks missing')
        for check in p['checks']:
            witness=self.sources.get(check['original_witness'])
            if not witness or witness['origin'] not in {'harness_receipt','independent_check'} or witness['payload'].get('source_version')!=r['source_version']:
                raise EvidenceError('Check must bind registered original evidence at the same versions')
        if r['status']=='invalidated':raise EvidenceError('Cannot revive old relation with stale proof')
        if not p.get('verification_scope'):raise EvidenceError('No universal dependency claims from a local check')
        r.update(status='confirmed',evidence_level='Confirmed',verifier=verifier,verification_scope=p['verification_scope']);r['evidence_source'].append(evidence)
        self.emit('DEPENDENCY_CONFIRMED',relation=rid,evidence=evidence,verifier=verifier)
    def invalidate(self,rid,new_versions,evidence,reason):
        r=self.relations[rid];src=self.sources[evidence]
        if src['origin'] not in {'harness_receipt','independent_check'} or not reason or src['payload'].get('new_versions')!=new_versions:raise EvidenceError('Version invalidation needs actual authoritative transition')
        if new_versions==r['source_version']:raise EvidenceError('Unchanged versions do not invalidate a relation')
        if r['status']=='invalidated':return
        r.update(status='invalidated',evidence_level='Invalidated',valid_to=len(self.events)+1)
        self.emit('DEPENDENCY_INVALIDATED',relation=rid,source_version=r['source_version'],new_versions=new_versions,evidence=evidence,reason=reason)
    def block(self,task,upstream,cause,evidence,relation=None):
        src=self.sources[evidence];p=src['payload'];strong=src['origin'] in {'harness_receipt','independent_check'} and p.get('task_id')==task and p.get('executed') is True and p.get('blocked') is True and p.get('cause')==cause
        supports_org=False
        if cause in {'missing_required_artifact','interface_incompatible'}:
            r=self.relations.get(relation,{})
            strong=strong and r.get('status')=='confirmed' and r.get('source_entity')==task and r.get('target_entity')==upstream and p.get('source_version')==r.get('source_version')
            supports_org=bool(strong)
        event=self.emit('TASK_BLOCKED' if strong else 'BLOCKING_INDICATION',task=task,upstream=upstream,cause=cause,evidence=evidence,
            supports_dependency_diagnosis=supports_org,organization_failure_proven=False)
        if strong:self.blocked[task]=event
        return event
    def unblock(self,task,evidence):
        src=self.sources[evidence];p=src['payload']
        if task not in self.blocked or src['origin'] not in {'harness_receipt','independent_check'} or p.get('task_id')!=task or p.get('executed') is not True or p.get('unblocked') is not True:raise EvidenceError('Unblocking requires a new executed receipt')
        old=self.blocked.pop(task);return self.emit('TASK_UNBLOCKED',task=task,prior_block=old['sequence'],evidence=evidence)
    def observe_transfer(self,tool,actor,args,response,evidence):
        src=self.sources[evidence]
        if src['origin']!='harness_receipt' or src['payload']!=response:raise EvidenceError('Transfer receipt differs from registered original')
        names={'offer_transfer':'OWNER_TRANSFER_OFFERED','accept_transfer':'OWNER_TRANSFER_ACCEPTED','decline_transfer':'OWNER_TRANSFER_REJECTED'}
        if tool not in names:raise EvidenceError('Not a transfer tool')
        return self.emit(names[tool] if response.get('ok') else 'OWNER_TRANSFER_REJECTED',actor=actor,arguments=args,result=response.get('result'),evidence=evidence,accepted=response.get('ok') is True)
    def observe_dependency_declaration(self,actor,args,response,evidence):
        src=self.sources[evidence];r=response.get('result',{});task=args.get('task_id');upstream=args.get('depends_on')
        if src['origin']!='harness_receipt' or src['producer']!=actor or src['payload']!=response or not response.get('ok'):raise EvidenceError('Successful original declaration receipt required')
        if r.get('task_id')!=task or r.get('owner')!=actor or upstream not in r.get('depends_on',[]) or upstream not in r.get('dependency_revisions',{}):raise EvidenceError('Declaration does not bind exact owned task and prerequisite revision')
        return self.propose('task:'+task,'task:'+upstream,'task_depends_on',{'task:'+task:r['revision'],'task:'+upstream:r['dependency_revisions'][upstream]},evidence,actor)
    def snapshot(self):return copy.deepcopy({'relations':self.relations,'events':self.events,'blocked':self.blocked})

def no_change(reason,*,evidence_sufficient,alternative=None):
    return {'action':'No-Change','reason':reason,'abstained_for_insufficient_evidence':not evidence_sufficient,
        'organization_mutation':False,'non_organizational_recovery':alternative,'not_a_task_failure':True}

def synchronization_event(kind,source,recipient,version):
    allowed={'HANDOFF_PRESENTED':'captured_input','HANDOFF_READ':'harness_receipt','HANDOFF_ADOPTED':'harness_receipt','HANDOFF_REJECTED':'harness_receipt'}
    p=source['payload']
    if kind not in allowed or source['origin']!=allowed[kind] or p.get('recipient')!=recipient or p.get('source_version')!=version:raise EvidenceError('Information lifecycle requires its own recipient/version-bound source')
    if kind=='HANDOFF_PRESENTED' and not p.get('request_payload_sha256'):raise EvidenceError('Sending or observation storage is not actual model input')
    if kind!='HANDOFF_PRESENTED' and p.get('executed') is not True:raise EvidenceError('Requested action is not executed action')
    return {'kind':kind,'recipient':recipient,'version':version,'source':source['payload_sha256'],'understood':None,'validated':None}
