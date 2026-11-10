"""Deterministic critical-event cards derived only from the supplied private wire.

This module performs no I/O, model inference, World lookup or outcome lookup.
Cards stay at the original observation position and preserve its source identity.
"""
import copy,json
from .software_context_compression_v175 import canonical,digest,is_observation

VERSION='v191-five-recent-cycles-with-source-bound-critical-events-r1'
METHODS=('M1-5','M1-10','M1-5K')
RULES={'version':VERSION,'keep_recent_cycles':5,'maximum_critical_cards':8,
 'maximum_critical_tokens':4096,'maximum_card_tokens':768,
 'priorities':{'test_failure':100,'test_result':95,'delivery':90,'code_change':80,
               'diagnostic_error':75,'environment':70,'unresolved_note':60},
 'only_supplied_private_observations':True,'hidden_state_reads':False,'LLM_compressor':False,
 'obsolete_test_is_current_validation':False,'latest_observation_and_actions_unchanged':True,
 'newer_same_key_supersedes_older':True,'capacity_failure_does_not_shorten_recent_window':True}
MUTATIONS={'write_file','replace_file','create_file','delete_file','rename_file','integrate_patch','diff_workspace'}
DELIVERY={'fix_patch','submit_integration','delivery_status'}
TESTS={'run_tests','read_test_result'}
NOTES={'work_note','work_todo','read_task','create_task','revise_task'}
PREFIX='[Retained historical critical event; exact source available with context_read. '
PREFIX+='This is derived from previously visible data, not a new test or permission.]\n'


def parsed(content):
    try:value=json.loads(content)
    except (TypeError,ValueError):return {}
    return value if isinstance(value,dict) else {}


def source_identity(body):
    result=body.get('result',{});result=result if isinstance(result,dict) else {}
    execution=result.get('execution',{});execution=execution if isinstance(execution,dict) else {}
    observation=body.get('observation',{});observation=observation if isinstance(observation,dict) else {}
    value=result.get('source_reference') or execution.get('source_reference') or observation.get('workspace_reference')
    if not isinstance(value,dict):return None
    if not all(isinstance(value.get(k),str) and value[k] for k in ('object_id','version_id')):return None
    return {k:value[k] for k in ('object_id','version_id')}


def _pointer(body,pointer):
    value=body
    for key in pointer.strip('/').split('/'):
        if not isinstance(value,dict) or key not in value:return False,None
        value=value[key]
    return True,value


def _fields(body,pointers):
    kept=[];omitted=[]
    for pointer in pointers:
        exists,value=_pointer(body,pointer)
        if not exists or value is None:continue
        # Never invent a shortened command, path, version or hash.
        if len(canonical(value))<=2048:kept.append({'pointer':pointer,'value':copy.deepcopy(value)})
        elif pointer in ('/error/message','/result/text','/result/message') and isinstance(value,str):
            kept.append({'pointer':pointer,'value':value[:384],'excerpt':True,'start':0,'end':384,'complete_value':False})
        else:omitted.append(pointer)
    return kept,omitted


def inventory(payload):
    """Score-blind inventory including recent observations for supersession."""
    calls={};events=[];current=None
    for i,message in enumerate(payload['messages']):
        for call in message.get('tool_calls') or []:
            f=call.get('function',{});calls[call.get('id')]={'tool':f.get('name'),'arguments':parsed(f.get('arguments'))}
        if not is_observation(message):continue
        body=parsed(message['content']);identity=source_identity(body)
        if identity:current=identity
        if message.get('role')!='tool':continue
        call=calls.get(message.get('tool_call_id'),{});tool=call.get('tool') or message.get('name')
        arguments=call.get('arguments',{});result=body.get('result',{});result=result if isinstance(result,dict) else {}
        execution=result.get('execution',{});execution=execution if isinstance(execution,dict) else {}
        category=None;key=None;pointers=[]
        if body.get('ok') is False and isinstance(body.get('error'),dict):
            category='diagnostic_error';key=['diagnostic_error',tool,digest(arguments)]
            pointers=['/error/code','/error/type','/error/message','/error/path','/error/details']
        elif tool in TESTS:
            counts=result.get('counts') or execution.get('counts') or {}
            counts=counts if isinstance(counts,dict) else {}
            failed=any(type(counts.get(k)) is int and counts[k]>0 for k in ('failed','errors'))
            category='test_failure' if failed or result.get('passed') is False else 'test_result'
            selector=execution.get('public_test_selection') or result.get('public_test_selection') or arguments.get('selection')
            key=['test',selector if selector is not None else arguments.get('report_id',arguments),execution.get('environment_hash')]
            pointers=['/result/source_reference','/result/files_sha256','/result/tree_sha256',
                '/result/passed','/result/validation_status','/result/counts','/result/report_id',
                '/result/execution/source_reference','/result/execution/input_tree_sha256',
                '/result/execution/argv','/result/execution/returncode','/result/execution/public_test_selection',
                '/result/execution/environment_hash','/result/execution/validation_status','/result/execution/counts']
        elif tool in MUTATIONS:
            category='code_change';key=['code_change',arguments.get('path') or arguments.get('destination') or tool]
            pointers=['/result/source_reference','/result/files_sha256','/result/tree_sha256','/result/path',
                '/result/old_path','/result/new_path','/result/changed_paths','/result/diff_sha256','/result/patch_id']
        elif tool in DELIVERY:
            category='delivery';key=['delivery',tool]
            pointers=['/result/source_reference','/result/files_sha256','/result/tree_sha256','/result/patch_id',
                '/result/delivery_id','/result/status','/result/validation_status','/result/submitted',
                '/result/public_test_sequence','/result/author','/result/baseline_id']
        elif tool in NOTES:
            category='unresolved_note';key=['note',tool,arguments.get('key') or arguments.get('task_id')]
            pointers=['/result/key','/result/task_id','/result/status','/result/text','/result/message',
                '/result/blockers','/result/title','/result/owner','/result/dependencies']
        elif any(k in result for k in ('environment','public_python','dependency_profile')):
            category='environment';key=['environment']
            pointers=['/result/environment','/result/public_python','/result/dependency_profile','/result/configuration_hash']
        if category is None:continue
        fields,omitted=_fields(body,pointers)
        if not fields:continue
        events.append({'message_index':i,'tool':tool,'category':category,'semantic_key':digest(key),
            'source_reference':identity,'fields':fields,'omitted_large_fields':omitted,
            'source_sha256':digest(message),'tool_call_id':message.get('tool_call_id'),
            'priority':RULES['priorities'][category]})
    latest={}
    for event in events:latest[event['semantic_key']]=event['message_index']
    for event in events:
        event['superseded_by_message_index']=latest[event['semantic_key']] if latest[event['semantic_key']]!=event['message_index'] else None
        source=event['source_reference']
        event['version_status']=('unknown' if source is None or current is None else
            'same_as_latest_visible_workspace' if source==current else 'historical_workspace_version')
    return events,current


def project(payload,method,store,*,count,original=None,selected_indices=None):
    if method not in METHODS:raise ValueError('Unknown critical-event treatment')
    original=payload if original is None else original
    indices=list(range(len(original['messages']))) if selected_indices is None else selected_indices
    if len(indices)!=len(payload['messages']):raise ValueError('Selected message positions lost their original mapping')
    output=copy.deepcopy(payload);messages=output['messages'];keep=10 if method=='M1-10' else 5
    tools=[i for i,m in enumerate(messages) if m.get('role')=='tool']
    observed=[i for i,m in enumerate(messages) if is_observation(m)]
    masked=[]
    if len(tools)>keep:
        cutoff=tools[-keep]
        for i in observed:
            if i>=cutoff or i==observed[0] or i==len(messages)-1:continue
            source=original['messages'][indices[i]]
            ref=store.put(source,indices[i])
            marker='[Earlier private observation retained at '+ref+'. Use context_read for the exact original; it is historical evidence.]'
            if count(marker)>=count(messages[i]['content']):continue
            messages[i]['content']=marker
            masked.append({'index':i,'reference':ref,'source_sha256':digest(source)})
    proof={'version':VERSION,'condition':method,'masked':masked,'keep_complete_tool_cycles':keep,
        'original_actions_unchanged':True,'latest_observation_unchanged':True,'ordinary_summary_disabled':True,
        'critical_cards':[],'critical_card_tokens_estimate':0,'critical_budget_tokens':RULES['maximum_critical_tokens'],
        'critical_fallbacks':[],'token_counts_are_local_estimates':True}
    if method!='M1-5K' or not masked:return output,proof
    events,current=inventory(payload);mask_by_index={m['index']:m for m in masked};candidates=[]
    for event in events:
        if event['message_index'] not in mask_by_index or event['superseded_by_message_index'] is not None:continue
        candidates.append(event)
    for event in sorted(candidates,key=lambda e:(-e['priority'],-e['message_index'],e['semantic_key'])):
        i=event['message_index'];mapping=mask_by_index[i];source=original['messages'][indices[i]]
        # Fields came from the supplied selected observation. Bind it separately
        # from the full original SDK source archived by v181's static projection.
        card={'category':event['category'],'tool':event['tool'],'source_reference':event['source_reference'],
            'version_status':event['version_status'],'current_version_validated':False,
            'fields':event['fields'],'omitted_large_fields':event['omitted_large_fields'],
            'original':{'reference':mapping['reference'],'message_index':indices[i],
                'message_sha256':digest(source),'tool_call_id':event['tool_call_id']},
            'selected_observation_sha256':event['source_sha256']}
        text=PREFIX+canonical(card);tokens=count(text)
        if (tokens>RULES['maximum_card_tokens'] or len(proof['critical_cards'])>=RULES['maximum_critical_cards']
            or proof['critical_card_tokens_estimate']+tokens>RULES['maximum_critical_tokens']):
            proof['critical_fallbacks'].append({'index':i,'reference':mapping['reference'],'reason':'critical_card_budget','tokens':tokens})
            continue
        messages[i]['content']=text;proof['critical_card_tokens_estimate']+=tokens
        proof['critical_cards'].append({'index':i,'reference':mapping['reference'],'category':event['category'],
            'tokens_estimate':tokens,'fields':event['fields'],'version_status':event['version_status'],
            'source_sha256':digest(source),'selected_observation_sha256':event['source_sha256']})
    assert output['messages'][-1]==payload['messages'][-1]
    return output,proof
