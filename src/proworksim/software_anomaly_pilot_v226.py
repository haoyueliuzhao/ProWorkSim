"""Trusted adapter between an observer's world receipts and a separate proposal session."""
from copy import deepcopy
from dataclasses import dataclass,field
import json

from .software_anomaly_graph_v226 import AnomalyGraph
from .software_anomaly_selector_v226 import context_from,evaluate,panel_by_effect
from .software_osa_session_v226 import OSASession,fingerprint
from .software_project_relations_v217 import identity

@dataclass
class DecisionPoint:
    node:dict
    organization:dict
    remaining:int
    worker_request:dict
    osa_request:dict

@dataclass
class AnomalyPilot:
    theta:tuple
    observer:str='member_001'
    regression_targets:tuple=()
    points:list=field(default_factory=list,init=False)

    def __post_init__(self):
        if len(self.theta)!=5:raise ValueError('Five frozen coefficients required')
        self.graph=AnomalyGraph(self.observer,regression_targets=self.regression_targets)
        self.policy_sha=fingerprint(list(self.theta))
        self.osa=OSASession(self.policy_sha)
        self.worker=OSASession(self.policy_sha)
        self.offers=set()

    def observe(self,ordinal,outcome,world,remaining_tokens,*,worker_request):
        """Called after the real worker opportunity. No model dispatch or world tool here."""
        previous=len(self.graph.wakes)
        self.graph.observe(ordinal,outcome)
        candidate=world.protocol().get('proposal') or {}
        anomaly_id=candidate.get('anomaly_id')
        if anomaly_id in self.graph.nodes:
            record_execution(self.graph,self.graph.nodes[anomaly_id],candidate,outcome,ordinal,self.offers)
        if previous==len(self.graph.wakes) or world.protocol()['terminal']:return None
        node=deepcopy(self.graph.nodes[self.graph.wakes[-1]['anomaly_id']])
        status=world._action_dynamic_status(self.observer,'SOFTWARE27')
        if any(t not in status['work'] for t in node['affected_work']):raise ValueError('Unbound work')
        if (not worker_request or worker_request.get('member_id')!=self.observer or worker_request.get('usage_id')!='agent'
            or not isinstance(worker_request.get('wire',{}).get('messages'),list)):
            raise ValueError('Actual input of the designated worker required')
        worker_visible_messages=worker_request['wire']['messages']
        worker_wire=self.worker.request(node,status,remaining_tokens=remaining_tokens)
        osa_wire=self.osa.request(node,status,remaining_tokens=remaining_tokens)
        # Only the worker readout receives its own already-presented SDK transcript.
        worker_wire['messages'][0]['content']='Propose one response as the actual worker using your own observed state and the listed options. Cite actual receipts. KEEP uses an empty option list.'
        worker_wire['messages'].insert(1,{'role':'user','content':'Your previously seen conversation: '+json.dumps(worker_visible_messages,ensure_ascii=False)})
        point=DecisionPoint(node,{'work':deepcopy(status['work'])},remaining_tokens,worker_wire,osa_wire)
        self.points.append(point)
        return point

    def bank(self,point,worker_proposal,osa_proposal):
        if not self.points or point is not self.points[-1]:raise ValueError('Unknown decision point')
        plans=[('baseline',{'keep':True,'actions':[],'diagnosis':'current','response_categories':['KEEP']})]
        for source,proposal in [('worker',worker_proposal),('osa',osa_proposal)]:
            if proposal and proposal['anomaly_id']!=point.node['anomaly_id']:raise ValueError('Foreign response')
            if proposal:plans.append((source,proposal))
        support=panel_by_effect(plans)
        pressure=context_from(point.node,point.organization,point.remaining)
        return support,evaluate(point.node,pressure,support,self.theta)

def register_response(world,candidate,source,node,*,evidence_ids):
    """Record a new proposal without altering ownership. Keep earlier decisions auditable."""
    refs=frozenset(evidence_ids)
    if not refs or node['status'] not in ('OPEN','ACTIVE','REOPENED','STABLE'):raise ValueError('Missing evidence or inactive node')
    if candidate.get('anomaly_id')!=node['anomaly_id']:raise ValueError('Foreign anomaly response')
    known=set()
    from .software_osa_session_v226 import project_evidence
    known.update(project_evidence(r)['id'] for r in node['evidence_refs'])
    if not refs<=known or not set(candidate.get('evidence_ids',()))<=refs:raise ValueError('Unrecognized evidence')
    with world.store.lock():
        world.state=world.store.load();p=world.protocol()
        history=p.setdefault('v226_decisions',[])
        if p['terminal'] or len(history)>=2 or (p.get('proposal') and not p.get('choice')):
            raise ValueError('No available decision opportunity')
        if not refs-set().union(*(set(h['evidence_ids']) for h in history)):raise ValueError('Repeated evidence')
        if p.get('proposal') and not history:raise ValueError('Existing experiment proposal')
        if history:
            history[-1]['choice']=deepcopy(p['choice'])
        history.append({'anomaly_id':node['anomaly_id'],'candidate':deepcopy(candidate),'source':deepcopy(source),'evidence_ids':sorted(refs)})
        p['choice']=None
        p['proposal']={**deepcopy(candidate),'source':deepcopy(source),'host_effects_only_proposal_metadata':True}
        world.store.save(world.state)

def stable_control_node(graph, samples, *, affected_work):
    """Negative-control probe at a predeclared window. Samples are actor-owned public-test returns."""
    if any(n['status'] in ('OPEN','ACTIVE','REOPENED','UNKNOWN') for n in graph.nodes.values()):
        raise ValueError('Stable control already has an open or uncertain obligation')
    proofs=[]
    for ordinal,item in samples:
        if item.get('worker_id')!=graph.observer: continue
        tool=item.get('decision',{}).get('action')
        resp=item.get('response',{})
        result=resp.get('result',{})
        counts=result.get('counts') or {}
        if (tool not in ('run_tests','run_patch_review_tests') or resp.get('ok') is not True
            or result.get('executed') is not True or result.get('passed') is not True
            or (counts.get('passed') or 0)<1 or not result.get('source_reference')):continue
        if graph.seen.get(resp.get('command_id'))!=identity(resp):raise ValueError('Missing observer-owned receipt')
        proofs.append({'opportunity':ordinal,'command_id':resp['command_id'],'tool':tool,
                       'source_reference':result['source_reference'],'sha256':identity(resp)})
    if len({fingerprint(p['source_reference']) for p in proofs})<2:raise ValueError('Negative control lacks two verified versions')
    return {'anomaly_id':identity(['stable',graph.observer,proofs]),'anomaly_type':'STABLE','subject':'normal_progress',
            'affected_work':sorted(set(affected_work)),'affected_agents':[graph.observer],
            'evidence_refs':proofs,'status':'STABLE','confidence':'receipt_supported','recurrence':0,'resolution_history':[]}

def record_execution(graph, node, candidate, outcome, ordinal, offers):
    """Match a successful visible action to the chosen response. Unseen peer consent stays unknown."""
    if outcome.get('worker_id')!=graph.observer or outcome.get('response',{}).get('ok') is not True:return
    decision=outcome.get('decision') or {}
    name,args=decision.get('action'),decision.get('arguments') or {}
    cid=candidate['candidate_id']
    disposition=None
    if name=='select_arrangement' and args.get('candidate_id')==cid:
        disposition='selected'
    elif name in ('accept_joint_arrangement','decline_joint_arrangement') and (args.get('offer_id'),graph.observer,cid) in offers:
        disposition='accepted' if name.startswith('accept') else 'declined'
    else:
        for action in candidate['actions']:
            if action['actor']!=graph.observer or name!=action['tool'] or action.get('arguments')!=args:continue
            disposition='executed'
            if name=='offer_joint_arrangement':
                offer=outcome['response']['result']['offer_id']
                offers.add((offer,args['to_member'],cid))
            break
    if disposition:graph.record_worker_response(node['anomaly_id'],outcome,ordinal,candidate_id=cid,disposition=disposition)
