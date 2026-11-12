"""Read-only identities for legacy real request captures, never model outputs.

Wire positions can reset after SDK condensation. Derived IDs are explicitly
not claimed to be original SDK history indices. Registered static omissions
are matched only to an earlier complete observation actually seen on wire.
"""
import copy,hashlib,json
from collections import Counter
from .software_context_compression_v175 import digest,canonical
from .software_context_graph_v196 import obj,GraphIntegrityError

STATIC_MARKER='_v117_same_input_static_fields'

class WireIdentity:
    def __init__(self):
        self.identities={};self.original_observations={};self.witnesses=[];self.static_links=[]

    def assign(self,payload,request_id):
        indices=[];seen=Counter()
        for pos,m in enumerate(payload['messages']):
            role=m.get('role');body=obj(m.get('content'));marker=body.get(STATIC_MARKER)
            if role=='user' and isinstance(body.get('observation'),dict):
                if marker:
                    raw_hash=marker['original_content_sha256'];original=self.original_observations.get(raw_hash)
                    if original is None:raise GraphIntegrityError('Static reference original was never a complete visible observation')
                    anchor=marker['anchor_message_index']
                    if not isinstance(anchor,int) or not pos<anchor<len(payload['messages']):raise GraphIntegrityError('Invalid same-input anchor')
                    text=payload['messages'][anchor]['content']
                    if hashlib.sha256(text.encode()).hexdigest()!=marker['anchor_content_sha256']:raise GraphIntegrityError('Static anchor hash mismatch')
                    restored=copy.deepcopy(body);del restored[STATIC_MARKER];anchor_body=obj(text)
                    for path in marker['omitted_equal_paths']:
                        keys=path.strip('/').split('/');parent=restored;source=anchor_body
                        for key in keys[:-1]:parent=parent[key];source=source[key]
                        if keys[-1] in parent:raise GraphIntegrityError('Static referenced field was not omitted')
                        parent[keys[-1]]=copy.deepcopy(source[keys[-1]])
                    if canonical(restored)!=canonical(obj(original)):raise GraphIntegrityError('Static projection changed source semantics')
                    self.static_links.append({'request_id':request_id,'wire_position':pos,'original_content_sha256':raw_hash,'anchor_position':anchor})
                else:
                    raw_hash=hashlib.sha256(m['content'].encode()).hexdigest();self.original_observations[raw_hash]=m['content']
                key=('registered_observation',raw_hash)
            elif role=='tool':key=('tool_result',m.get('tool_call_id'))
            elif role=='assistant' and m.get('tool_calls'):key=('assistant_action',tuple(c['id'] for c in m['tool_calls']))
            else:key=(role,digest(m))
            occurrence=seen[key];seen[key]+=1;identity=(key,occurrence)
            if identity not in self.identities:self.identities[identity]=len(self.identities)
            index=self.identities[identity];indices.append(index)
            self.witnesses.append({'request_id':request_id,'wire_position':pos,'derived_index':index,'message_sha256':digest(m)})
        if len(set(indices))!=len(indices):raise GraphIntegrityError('Two request positions got one source index')
        return indices

def verify_request_capture(path,call,provider,*,expected_slot):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=call['request']['sha256']:raise GraphIntegrityError('Client capture hash mismatch')
    record=json.loads(raw);payload=record['request']
    if provider.get('slot_id')!=expected_slot or provider.get('usage_id')!='agent' or not call.get('request_id','').startswith(expected_slot+':member_001:'):
        raise GraphIntegrityError('Captured request is outside the declared task/member scope')
    if provider['status']!='settled' or provider['request_sha256']!=digest(payload):raise GraphIntegrityError('No settled provider receipt for exact payload')
    if record['usage_id']!='agent' or call['usage_id']!='agent':raise GraphIntegrityError('Not an Agent decision input')
    return payload
