"""Preserve an addressable ORIGINAL prefix when adopting a generated summary.

This is a forward repair after v175 replay, not a change to that frozen trial.
The archive includes assistant actions as well as their original observations;
the generated summary cannot remove its one deterministic recall reference.
"""
from __future__ import annotations
import copy
import hashlib

from .software_context_compression_v175 import EvidenceStore,canonical,digest,is_observation

VERSION='v176-addressable-original-prefix-r1'


class HistoryEvidenceStore(EvidenceStore):
    def put_history(self,messages,start,end):
        # Offsets let a second bounded read jump to one needed action/result;
        # callers need not sequentially expand an entire 100KB history first.
        text='{"message_range":'+canonical([start,end])+',"messages":['
        offsets=[]
        for i,message in enumerate(messages):
            if i:text+=','
            begin=len(text);text+=canonical(message)
            offsets.append({'message_index':start+i,'role':message.get('role'),
                'tool_names':[t.get('function',{}).get('name') for t in message.get('tool_calls',[])],
                'tool_call_id':message.get('tool_call_id'),'start':begin,'end':len(text)})
        text+=']}'
        raw={'point_id':self.point_id,'slot_id':self.slot_id,'member_id':self.member_id,
             'kind':'original_closed_private_history','message_range':[start,end],
             'message_offsets':offsets,'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        ref='ctx:'+digest(raw)[:24]
        if ref in self.entries and self.entries[ref]!=raw:raise ValueError('History reference collision')
        self.entries[ref]=raw
        return ref

    def read(self,arguments,*,point_id,slot_id,member_id):
        value=super().read(arguments,point_id=point_id,slot_id=slot_id,member_id=member_id)
        entry=self.entries[arguments['reference']]
        if entry.get('kind')=='original_closed_private_history':
            value['scope']='previously_presented_private_history'
            value['message_range']=entry['message_range']
            if value['start']==0:value['message_offsets']=entry['message_offsets']
        return value


def apply_recoverable_summary(masked_payload,prefix,summary,*,original_payload,store,count):
    """Check the same private input and retain its original pre-masking prefix.

The caller persists this store alongside the request. Adding a pointer alone
without retaining these exact bytes is not a completed deployment.
"""
    if not isinstance(summary,str) or not summary.strip():raise ValueError('Empty summary')
    if not isinstance(store,HistoryEvidenceStore):raise ValueError('Use the full-history recall implementation')
    start,end=prefix['start'],prefix['end']
    masked=masked_payload['messages'];original=original_payload['messages']
    if digest(masked[start:end])!=prefix['sha256'] or len(masked)!=len(original):
        raise ValueError('The frozen summary prefix changed')
    for i,(raw,view) in enumerate(zip(original,masked)):
        if raw==view:continue
        if not is_observation(raw) or {k:v for k,v in raw.items() if k!='content'}!={k:v for k,v in view.items() if k!='content'}:
            raise ValueError('Only verified observation masking may precede this summary')
        matching=[ref for ref,entry in store.entries.items() if entry.get('message_index')==i
                  and entry['text']==raw['content'] and entry['point_id']==store.point_id
                  and entry['slot_id']==store.slot_id and entry['member_id']==store.member_id]
        if len(matching)!=1 or matching[0] not in view.get('content',''):
            raise ValueError('Original observation is not bound to this private view')
    messages=copy.deepcopy(original[start:end])
    called={t['id'] for m in messages for t in m.get('tool_calls',[])}
    returned={m.get('tool_call_id') for m in messages if m.get('role')=='tool'}
    if called!=returned:raise ValueError('Archive must preserve a closed action/result prefix')
    archive=store.put_history(messages,start,end)
    protected=('Original private history, including actions and exact pre-masking observations, is retained at '+archive+
        '. Use context_read for its exact text; this is old evidence, not current-version validation. '
        'Omission from this derived summary does not establish that an event did not occur.\n')
    replacement={'role':'user','content':'[Derived private context summary]\n'+protected+summary}
    before=count(canonical(masked[start:end]));after=count(canonical(replacement))
    if after>=before:
        return copy.deepcopy(masked_payload),{'version':VERSION,'adopted':False,'reason':'summary_plus_recall_index_not_shorter',
            'original_prefix_reference':archive,'original_prefix_sha256':digest(messages)}
    result=copy.deepcopy(masked_payload)
    result['messages']=masked[:start]+[replacement]+masked[end:]
    return result,{'version':VERSION,'adopted':True,'original_prefix_reference':archive,
        'original_prefix_sha256':digest(messages),'protected_reference_visible':True,
        'archive_includes_original_actions_and_observations':True,'summary_tokens_include_recall_index':True,
        'local_prefix_token_saving':before-after,'model_quality_after_repair_tested':False}
