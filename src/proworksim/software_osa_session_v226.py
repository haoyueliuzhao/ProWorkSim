"""OSA inference boundary. The coordinator supplies an authorized anomaly node.

The only advertised function returns a proposed change. Worker calls, consent,
policy fitting and official scoring use separate entry points.
"""
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field

from .software_project_relations_v217 import allowed_event

MEMBERS = ('member_001', 'member_002')
TYPES = ('A1', 'A2', 'A3', 'A4', 'A5', 'STABLE', 'UNKNOWN')
OPERATIONS = ('peer_diagnosis', 'transfer_remaining', 'assign_verifier',
              'review_published', 'adopt_upstream', 'focus_delivery', 'independent_close_check')
RESPONSE_TOOL = {
    'type': 'function',
    'function': {
        'name': 'propose_response',
        'description': 'Submit one evidence-linked proposal or KEEP. Each operation is a recommendation for the named workers.',
        'parameters': {
            'type': 'object',
            'properties': {
                'reason': {'type': 'string', 'minLength': 1, 'maxLength': 1600},
                'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
                'option_ids': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string'}},
            },
            'required': ['reason', 'evidence_ids', 'option_ids'],
            'additionalProperties': False,
        },
    },
}

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def safe_id(value):
    """Only machine IDs, paths, and test identities enter structured fields."""
    return isinstance(value, str) and 0 < len(value) <= 512 and not any(ord(c) < 32 for c in value)

def safe_ids(values):
    return [v for v in values if safe_id(v)] if isinstance(values, (list, tuple)) else []

def project_evidence(receipt):
    if not isinstance(receipt, dict):
        raise ValueError('Expected an authorized structured evidence reference')
    out = {}
    for key in ('opportunity', 'sequence', 'event_sequence', 'command_id', 'kind', 'tool',
                'actor_id', 'worker_id', 'task_id', 'patch_id', 'nodeid', 'target', 'version',
                'passed', 'executed', 'outcome', 'sha256'):
        value = receipt.get(key)
        if type(value) in (bool, int) or safe_id(value):
            out[key] = value
    ref = receipt.get('source_reference')
    if isinstance(ref, dict) and all(safe_id(ref.get(k)) for k in ('object_id', 'version_id')):
        out['source_reference'] = {k: ref[k] for k in ('object_id', 'version_id')}
    if not any(k in out for k in ('sequence', 'event_sequence', 'opportunity', 'command_id', 'sha256')):
        raise ValueError('Untraceable evidence')
    out['id'] = fingerprint(out)
    return out

def world_view(world, sequences, observer='member_001'):
    """Trusted adapter for raw live events. Secret or nonexistent receipts fail closed."""
    if observer not in MEMBERS:
        raise ValueError('Unknown observer')
    wanted = set(sequences)
    evidence = []
    for raw in world.state['software_events']:
        if raw['sequence'] in wanted:
            event = allowed_event(world, raw, observer)
            if event is None:
                raise PermissionError('Private event')
            evidence.append(project_evidence(event))
    if {e['sequence'] for e in evidence} != wanted:
        raise ValueError('Missing event')
    return evidence

def organizations(status):
    work = {}
    for tid, w in status['work'].items():
        if not safe_id(tid) or w.get('owner') not in MEMBERS:
            raise ValueError('Invalid organization snapshot')
        completion = w.get('completion') or {}
        patch = completion.get('patch_id')
        work[tid] = {
            'owner': w['owner'], 'reviewer': w.get('reviewer') if w.get('reviewer') in MEMBERS else None,
            'children': safe_ids(w.get('children')), 'authors': [m for m in MEMBERS if m in w.get('authors', [])],
            'depends_on': safe_ids(w.get('depends_on')), 'revision': w.get('task_revision', 1),
            'complete': bool(completion), 'patch': patch if safe_id(patch) else None,
            'mode': w.get('mode') if w.get('mode') in ('evidence','implementation') else 'implementation',
        }
        if type(work[tid]['revision']) is not int or work[tid]['revision'] < 1:
            raise ValueError('Invalid task revision')
    return work

def action(actor, tool, **arguments):
    return {'actor': actor, 'tool': tool, 'arguments': arguments}

def options(node, work):
    options_by_id = {}
    def add(kind, tid, steps):
        if kind not in OPERATIONS:
            raise ValueError('Unknown operation')
        oid = kind + ':' + fingerprint([tid, steps])[:16]
        options_by_id[oid] = {'operation': kind, 'task_id': tid, 'actions': steps}
    if node['anomaly_type']=='A5' and node.get('subject')=='delivery_ready':
        add('focus_delivery','root_goal', [
            action('member_002','send_message',task_id='root_goal',recipient='member_001',
                   body='Delivery evidence indicates readiness. Prioritize an exact final readiness check and decide whether to submit.'),
            action('member_001','delivery_readiness'),
        ])
        add('independent_close_check','root_goal', [
            action('member_001','send_message',task_id='root_goal',recipient='member_002',
                   body='Independently inspect the remaining delivery obligations and report your finding before closure.'),
            action('member_002','delivery_readiness'),
        ])
    for tid in node['affected_work']:
        w = work[tid]
        if w['children']:
            continue
        owner = w['owner']
        peer = next(m for m in MEMBERS if m != owner)
        if not w['complete']:
            add('peer_diagnosis', tid, [
                action(owner, 'add_collaboration', task_id=tid, peer=peer, reason='Exchange evidence for independent diagnosis'),
                action(owner, 'send_message', recipient=peer, task_id=tid, body='Please independently diagnose the anomaly and report your evidence; the owner continues the assigned work.'),
            ])
            if not w['authors']:
                add('transfer_remaining', tid, [
                    action(owner, 'offer_joint_arrangement', task_id=tid, to_member=peer,
                           reviewer=owner, mode=w['mode'], expected_revision=w['revision'],
                           reason='Propose moving this remaining work to the other member'),
                    {'actor': peer, 'tool': 'accept_joint_arrangement',
                     'arguments_from_real_receipt': {'offer_id':{'task_id':tid,'tool':'offer_joint_arrangement'}},
                     'refusal_is_preserved': True},
                ])
            if w['reviewer'] is None and peer not in w['authors']:
                add('assign_verifier', tid, [action(owner, 'assign_verification', task_id=tid, reviewer=peer,
                                                    reason='Assign independent verification')])
        elif w['patch'] and w['reviewer'] in MEMBERS and w['reviewer'] not in w['authors']:
            add('review_published', tid, [
                action(w['reviewer'], 'open_patch_review', patch_id=w['patch']),
                action(w['reviewer'], 'run_patch_review_tests', patch_id=w['patch']),
            ])
        for upstream in w['depends_on']:
            parent = work.get(upstream)
            if parent and parent['patch'] and parent['owner'] != owner and not w['complete']:
                add('adopt_upstream', tid, [action(owner, 'integrate_patch', patch_id=parent['patch'])])
    return options_by_id

@dataclass
class OSASession:
    policy_sha256: str
    _memory: list = field(default_factory=list, init=False, repr=False)
    _seen: set = field(default_factory=set, init=False, repr=False)
    _pending: dict | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if not re.fullmatch('[0-9a-f]{64}', self.policy_sha256):
            raise ValueError('Bind frozen policy identity')

    def request(self, node, authorized_status, *, remaining_tokens):
        if self._pending is not None or len(self._memory) >= 2:
            raise ValueError('A pending or third decision cannot be opened')
        if type(remaining_tokens) is not int or not 0 < remaining_tokens <= 5_000_000:
            raise ValueError('Invalid team budget')
        work = organizations(authorized_status)
        if node['anomaly_type'] not in TYPES or not safe_id(node['anomaly_id']):
            raise ValueError('Unknown anomaly')
        if node['status'] not in ('OPEN', 'ACTIVE', 'REOPENED', 'RESOLVED', 'UNKNOWN', 'STABLE'):
            raise ValueError('Unknown status')
        refs = [project_evidence(e) for e in node['evidence_refs']]
        if not refs:
            raise ValueError('Each observation requires evidence')
        affected = sorted(set(safe_ids(node['affected_work'])))
        if not set(affected) <= set(work):
            raise ValueError('Unbound work in anomaly')
        node_view = {'anomaly_id':node['anomaly_id'], 'anomaly_type':node['anomaly_type'], 'status':node['status'],
                     'affected_work':affected,'affected_agents':[m for m in MEMBERS if m in node.get('affected_agents', [])],
                     'evidence_refs':refs}
        if safe_id(node.get('subject')):
            node_view['subject']=node['subject']
        node_view['resolution_history']=[
            {k:v for k,v in row.items() if (k=='opportunity' and type(v) is int) or
             (k in ('from','to') and v in ('OPEN','ACTIVE','RESOLVED','REOPENED','UNKNOWN'))}
            for row in node.get('resolution_history',[]) if isinstance(row,dict)]
        for key in ('confidence','recurrence'):
            value = node.get(key)
            if type(value) in (int,float) or value in ('high','medium','low','unknown','receipt_supported'):
                node_view[key] = value
        evidence = {e['id'] for e in refs}
        # A new log offset or request ID alone is not new project evidence.
        material = {fingerprint([node_view['anomaly_id'], node_view['status'],
                                 node_view.get('recurrence'), node_view.get('subject'),
                                 {k:e[k] for k in ('actor_id','worker_id','task_id','kind','tool','source_reference',
                                                    'version','patch_id','nodeid','target','passed','outcome') if k in e}])
                    for e in refs}
        if not material - self._seen:
            raise ValueError('No new material evidence')
        menu = options(node_view,work)
        self._pending = {'anomaly': node_view, 'menu':menu, 'evidence': evidence, 'material':material}
        return {'messages':[{'role':'system','content':'You are the independent organizational strategy agent. Interpret only the provided evidence. Propose one local response using compatible options, or KEEP with option_ids=[]. Anchor the reason to the cited receipts. Do not treat planned actions as observed consent, execution or resolution.'},
                            {'role':'user','content':canonical({'policy_sha256':self.policy_sha256,'remaining_tokens':remaining_tokens,
                                                               'anomaly':node_view,'organization':work,'available_options':menu,
                                                               'own_prior_proposals':self._memory})}],
                'tools':[copy.deepcopy(RESPONSE_TOOL)]}

    def receive(self, function_name, arguments):
        if function_name != 'propose_response':
            raise PermissionError('Only propose_response is exposed')
        if not self._pending:
            raise ValueError('No open decision')
        if set(arguments) != {'reason','option_ids','evidence_ids'}:
            raise ValueError('Unexpected fields')
        reason = arguments['reason']
        if not isinstance(reason,str) or not 0 < len(reason.strip()) <= 1600:
            raise ValueError('Bounded explanation required')
        ids, cited = arguments['option_ids'],arguments['evidence_ids']
        pending = self._pending
        if (not isinstance(ids,list) or len(ids)>5 or any(not isinstance(k,str) for k in ids)
            or len(set(ids))!=len(ids) or not set(ids)<=pending['menu'].keys()
            or not isinstance(cited,list) or any(not isinstance(k,str) for k in cited)
            or not cited or not set(cited)<=pending['evidence']):
            raise ValueError('Unbound option or evidence')
        selected = [pending['menu'][k] for k in ids]
        # An old-owner instruction cannot be stacked with a change of owner on the same task.
        for item in selected:
            if item['operation']=='transfer_remaining' and sum(s['task_id']==item['task_id'] for s in selected)>1:
                raise ValueError('Incompatible instructions for the same work')
        categories = sorted({option['operation'] for option in selected}) or ['KEEP']
        diagnosis = ('independent' if set(categories) & {'peer_diagnosis','independent_close_check'}
                     else 'current')
        candidate = {'diagnosis': diagnosis,'keep':not ids,'reason':reason,'anomaly_id':pending['anomaly']['anomaly_id'],
                     'evidence_ids':sorted(set(cited)), 'option_ids':list(ids),
                     'actions':[copy.deepcopy(a) for opt in selected for a in opt['actions']],
                     'response_categories':categories,
                     'candidate_id':'osa-'+fingerprint([pending['anomaly']['anomaly_id'], sorted(ids), sorted(cited)]), 'host_execution':False}
        self._seen.update(pending['material'])
        self._memory.append(copy.deepcopy(candidate))
        self._pending = None
        return candidate
