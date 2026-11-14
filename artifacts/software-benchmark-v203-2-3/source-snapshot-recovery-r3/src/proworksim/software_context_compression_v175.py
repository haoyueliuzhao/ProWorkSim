"""Recoverable observation masking and whole-observation neural extraction.

Only already-presented text is placed in the private evidence store. Tool call
IDs/actions, system/task input and the latest observation remain intact. No
code/diff token deletion or fresh World read is performed by this module.
"""
from __future__ import annotations
import copy
import hashlib
import json

VERSION='v175-recoverable-source-aware-context-views-r2'
METHODS=('M0','M1','M2','M3')
KEEP_RECENT=5
HYBRID_THRESHOLD=32768
EXTRACTIVE_OLD_KEEP_RATE=.5
CONTEXT_READ_TOOL={'type':'function','function':{'name':'context_read',
    'description':'Read exact retained text previously present in this private request history. This is not a new repository read or current-version validation. Use only a supplied context reference.',
    'parameters':{'type':'object','additionalProperties':False,'required':['reference'],
        'properties':{'reference':{'type':'string','maxLength':80},
            'start':{'type':'integer','minimum':0},'characters':{'type':'integer','minimum':1,'maximum':8192}}}}}


def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(v):return hashlib.sha256(v if isinstance(v,bytes) else canonical(v).encode()).hexdigest()


class EvidenceStore:
    def __init__(self,point_id,slot_id,member_id):
        self.point_id,self.slot_id,self.member_id=point_id,slot_id,member_id
        self.entries={}

    def put(self,message,index):
        text=message.get('content')
        if not isinstance(text,str) or not is_observation(message):
            raise ValueError('Only actual environment/tool observations enter this private recall store')
        raw={'point_id':self.point_id,'slot_id':self.slot_id,'member_id':self.member_id,
            'message_index':index,'tool_call_id':message.get('tool_call_id'),
            'tool_name':message.get('name'),'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        ref='ctx:'+digest(raw)[:24]
        if ref in self.entries and self.entries[ref]!=raw:raise ValueError('Evidence collision')
        self.entries[ref]=raw
        return ref

    def read(self,arguments,*,point_id,slot_id,member_id):
        if (point_id,slot_id,member_id)!=(self.point_id,self.slot_id,self.member_id):
            raise PermissionError('Cross-episode/member/private-state recall is forbidden')
        if set(arguments)-{'reference','start','characters'}:raise ValueError('Unknown recall argument')
        ref=arguments.get('reference');entry=self.entries.get(ref)
        if entry is None:raise ValueError('Unknown retained context reference')
        start,size=arguments.get('start',0),arguments.get('characters',8192)
        if type(start) is not int or start<0 or type(size) is not int or not 1<=size<=8192:
            raise ValueError('Recall uses bounded exact character pages')
        text=entry['text'];page=text[start:start+size]
        return {'reference':ref,'text':page,'start':start,'next_start':start+len(page) if start+len(page)<len(text) else None,
            'total_characters':len(text),'text_sha256':entry['text_sha256'],
            'scope':'previously_presented_private_environment_observation','new_world_read':False,
            'current_version_validated':False}


def is_observation(message):
    if not isinstance(message.get('content'),str):return False
    if message.get('role')=='tool':return True
    if message.get('role')!='user':return False
    try:value=json.loads(message['content'])
    except (TypeError,ValueError):return False
    return isinstance(value,dict) and isinstance(value.get('observation'),dict)


def observations(payload):
    return [i for i,m in enumerate(payload['messages']) if is_observation(m)]


def eligible_observations(payload):
    indices=observations(payload)
    tools=[i for i in indices if payload['messages'][i]['role']=='tool']
    if len(tools)<=KEEP_RECENT or not indices:return []
    # A harness turn can contain a tool result AND a fresh user-role World
    # observation. Both are old environment output, never assistant reasoning.
    cutoff=tools[-KEEP_RECENT]
    return [i for i in indices if i<cutoff and i!=indices[0] and i!=len(payload['messages'])-1]


def baseline(payload,store):
    result=copy.deepcopy(payload)
    if any(t['function']['name']=='context_read' for t in result.get('tools',[])):
        raise ValueError('The common recall tool must be attached only once')
    result['tools'].append(copy.deepcopy(CONTEXT_READ_TOOL))
    refs={i:store.put(result['messages'][i],i) for i in observations(result)}
    return result,refs


def apply(payload,method,store,*,count,neural_scores=None):
    if method not in METHODS:raise ValueError('Unknown frozen context method')
    result,refs=baseline(payload,store);indices=observations(result)
    # First observation and latest5 are preserved. All assistant actions remain.
    candidates=eligible_observations(result)
    selected=[]
    if method in {'M1','M3'}:
        selected=candidates
    elif method=='M2' and candidates:
        if neural_scores is None:raise ValueError('M2 requires real frozen LLMLingua-2 scores')
        amounts={i:count(result['messages'][i]['content']) for i in candidates}
        target=sum(amounts.values())*EXTRACTIVE_OLD_KEEP_RATE
        kept=set();current=0
        for i in sorted(candidates,key=lambda i:(-neural_scores[refs[i]],i)):
            if current<target:kept.add(i);current+=amounts[i]
        selected=[i for i in candidates if i not in kept]
    replaced=[]
    for i in selected:
        old=result['messages'][i]['content']
        marker='[Earlier tool observation retained at '+refs[i]+'. Use context_read for the exact original.]'
        if count(marker)>=count(old):continue
        result['messages'][i]['content']=marker
        replaced.append({'message_index':i,'reference':refs[i],'original_characters':len(old),
            'original_estimated_tokens':count(old),'replacement_estimated_tokens':count(marker)})
    before=count(canonical({k:v for k,v in baseline(payload,EvidenceStore(store.point_id,store.slot_id,store.member_id))[0].items() if k in {'messages','tools'}}))
    after=count(canonical({k:v for k,v in result.items() if k in {'messages','tools'}}))
    assert payload['messages'][0]==result['messages'][0]
    assert payload['messages'][-1]==result['messages'][-1]
    assert [(m.get('role'),m.get('tool_call_id'),m.get('tool_calls')) for m in payload['messages']]==[
        (m.get('role'),m.get('tool_call_id'),m.get('tool_calls')) for m in result['messages']]
    return result,{'method':method,'version':VERSION,'keep_recent_tool_observations':KEEP_RECENT,
        'preserve_first_observation':True,'replaced':replaced,'baseline_local_tokens':before,
        'transformed_local_tokens':after,'local_token_saving':before-after,
        'extra_common_tool_all_conditions':True,'method_is_original_paper_full_replication':False,
        'hybrid_summary_needed':method=='M3' and after>HYBRID_THRESHOLD and bool(candidates),
        'hybrid_threshold':HYBRID_THRESHOLD,'observed_tool_count':len(indices)}


def summary_prefix(payload):
    """Choose a closed old action/observation prefix; never orphan tool results."""
    indices=[i for i in observations(payload) if payload['messages'][i]['role']=='tool']
    if len(indices)<=KEEP_RECENT+1:return None
    first_recent=indices[-KEEP_RECENT]
    cutoff=first_recent
    # Include the matching assistant tool call in the retained suffix.
    wanted=payload['messages'][first_recent].get('tool_call_id')
    for i in range(first_recent-1,1,-1):
        if any(t.get('id')==wanted for t in payload['messages'][i].get('tool_calls',[])):
            cutoff=i;break
    if cutoff<=2:return None
    prefix=copy.deepcopy(payload['messages'][2:cutoff])
    called={t['id'] for m in prefix for t in m.get('tool_calls',[])}
    returned={m.get('tool_call_id') for m in prefix if m.get('role')=='tool'}
    if called!=returned:return None
    return {'start':2,'end':cutoff,'messages':prefix,'sha256':digest(prefix)}


def apply_summary(payload,prefix,text,*,count):
    if not isinstance(text,str) or not text.strip():raise ValueError('Empty generated summary')
    if digest(payload['messages'][prefix['start']:prefix['end']])!=prefix['sha256']:
        raise ValueError('Summary must bind this exact private closed prefix')
    replacement={'role':'user','content':'[Derived private context summary; not a new observation, permission, or test result.]\n'+text}
    if count(canonical(replacement))>=count(canonical(prefix['messages'])):
        return copy.deepcopy(payload),{'adopted':False,'reason':'summary_not_shorter'}
    result=copy.deepcopy(payload)
    result['messages']=result['messages'][:prefix['start']]+[replacement]+result['messages'][prefix['end']:]
    return result,{'adopted':True,'prefix_sha256':prefix['sha256'],'removed_messages':prefix['end']-prefix['start'],
        'summary_sha256':digest(text),'not_current_world_evidence':True}
