"""Zero-model audit of exact public-test identities and already-presented history."""
import json,os,sqlite3
from collections import Counter,defaultdict
from pathlib import Path
from proworksim.software_context_compression_v175 import digest,canonical,is_observation
from proworksim.software_benchmark_candidates_v054 import reference

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v181/full-context-pilot-r1'
OUT=ROOT/'artifacts/software-benchmark-v191/offline-audit-r1'
FOCUS={18107,18124,18125,18126,18136,18137,18138,18111,18108,18141}

def read(path):return json.loads(Path(path).read_bytes())
def save(name,value):
    path=OUT/name;path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');return reference(path)
def current_version(messages):
    for m in reversed(messages):
        if m.get('role')!='user':continue
        try:v=json.loads(m.get('content',''))
        except (ValueError,TypeError):continue
        if isinstance(v,dict):
            observed=v.get('observation',{})
            if isinstance(observed,dict) and observed.get('workspace_reference'):return observed['workspace_reference']
    return None
def compact_observation(message):
    try:v=json.loads(message['content'])
    except (ValueError,TypeError):return {'structured':False,'characters':len(message['content'])}
    if not isinstance(v,dict):return {'structured':False}
    result=v.get('result',{});result=result if isinstance(result,dict) else {}
    execution=result.get('execution',{});execution=execution if isinstance(execution,dict) else {}
    return {'structured':True,'characters':len(message['content']),'ok':v.get('ok'),
        'top_keys':list(v),'result_keys':list(result),
        'source_reference':result.get('source_reference'),
        'path':result.get('path'),'counts':result.get('counts'),
        'error':v.get('error'),'validation_status':result.get('validation_status'),
        'public_test_selection':execution.get('public_test_selection'),
        'input_tree_sha256':execution.get('input_tree_sha256')}


def audit_tests(rows):
    tests=[];groups=defaultdict(Counter)
    for row in rows:
        folder=RUN/'episodes'/str(row['slot_index'])
        environment=read(folder/'public-environment.json');seen={};selection_trees=defaultdict(set)
        for request_path in sorted((folder/'controller-output/public-test-rpc').glob('test-*/request.json')):
            response_path=request_path.parent/'response.json';request=read(request_path)
            if not response_path.exists():
                groups[row['group_id']]['no_response']+=1;continue
            result=read(response_path);execution=result.get('execution',{})
            if not execution.get('executed'):
                groups[row['group_id']]['unexecuted']+=1;continue
            assert request['tree_sha256']==execution['input_tree_sha256']
            assert request['public_test_selection']==execution['public_test_selection']
            env={'image_id':environment['image_id'],'environment':environment['environment'],
                'public_python':environment['public_python'],'cwd':execution.get('cwd'),
                'public_dependency_profile':execution.get('public_dependency_profile')}
            identity={'episode':row['slot_id'],'tree_hash':request['tree_sha256'],
                'command':execution['argv'],'selector':request['public_test_selection'],
                'environment_hash':digest(env)}
            key=digest(identity);previous=seen.get(key)
            selection_key=digest({k:v for k,v in identity.items() if k!='tree_hash'})
            prior_trees=selection_trees[selection_key]
            item={'slot_index':row['slot_index'],'group_id':row['group_id'],'instance_id':row['instance_id'],
                'call_index':request['call_index'],'identity':identity,'identity_sha256':key,
                'source_reference':request.get('source_reference'),'wall_seconds':execution.get('wall_seconds'),
                'passed':result.get('passed'),'counts':result.get('counts'),
                'exact_identity_repeat':previous is not None,
                'previous_equal_identity_passed':previous.get('passed') if previous else None,
                'previous_equal_identity_call':previous.get('call_index') if previous else None,
                'same_selector_after_changed_tree':bool(prior_trees and identity['tree_hash'] not in prior_trees),
                'request':reference(request_path),'response':reference(response_path),
                'environment':reference(folder/'public-environment.json')}
            seen[key]=item;prior_trees.add(identity['tree_hash']);tests.append(item)
            g=groups[row['group_id']];g['executed']+=1;g['wall_seconds']+=item['wall_seconds'] or 0
            g['exact_identity_repeats']+=item['exact_identity_repeat']
            g['repeat_after_pass']+=bool(previous and previous.get('passed') is True)
            g['repeat_after_fail']+=bool(previous and previous.get('passed') is False)
            g['same_selector_new_tree']+=item['same_selector_after_changed_tree']
            if previous:g['repeat_wall_seconds']+=item['wall_seconds'] or 0
        observed=read(folder/'controller-output/model-ledger/collaboration-observation/summary.json')
        groups[row['group_id']]['observer_executed']+=observed['public_tests']['executed']
    for group,stats in groups.items():assert stats['executed']==stats['observer_executed'],(group,stats)
    return tests,{k:dict(v) for k,v in groups.items()}


def audit_trace(row):
    folder=RUN/'episodes'/str(row['slot_index']);requests=[]
    for path in (folder/'controller-output/model-ledger/request-capture-v181').glob('*/provenance.json'):
        manifest=read(path)
        if manifest['identity']['usage_id']=='agent':requests.append((manifest['identity']['request_time'],path.parent,manifest))
    requests.sort();known={};masked={};actions=[];repeated_reads=Counter();retrievals=Counter();wire_lengths=[]
    for when,path,manifest in requests:
        wire=read(path/'payload.json');projection=read(path/'projection-evidence.json')
        indices=projection['selected_indices'];treatment=projection.get('observation_history_projection',{}).get('context_treatment',{})
        assert len(indices)==len(wire['messages'])
        for i,message in enumerate(wire['messages']):
            if is_observation(message) and '[Earlier private observation retained at ctx:' not in message['content']:
                known[(indices[i],digest(message))]=message
        for item in treatment.get('masked',[]):
            i=item['index'];original=known.get((indices[i],item['source_sha256']))
            entry=masked.setdefault(item['reference'],{'reference':item['reference'],'original_index':indices[i],
                'source_sha256':item['source_sha256'],'presentations':0,'mapped_to_prior_visible_message':False})
            entry['presentations']+=1
            if original:
                entry['mapped_to_prior_visible_message']=True;entry['observation']=compact_observation(original)
                entry['source_message_sha256']=digest(original)
        response=read(path/'response-original.json')
        version=current_version(wire['messages'])
        for call in response['choices'][0]['message'].get('tool_calls') or []:
            function=call['function'];name=function['name']
            try:arguments=json.loads(function['arguments'])
            except (ValueError,TypeError):arguments={'unparsed_arguments':function['arguments']}
            if name in {'read_file','search_file','search_repository','read_test_result'}:
                repeated_reads[digest({'tool':name,'arguments':arguments,'observed_version':version})]+=1
            if name in {'context_read','work_history_read'}:retrievals[name]+=1
            actions.append({'request_id':manifest['identity']['request_id'],'tool':name,'arguments':arguments,
                'observed_workspace':version,'input_tokens':response['usage']['prompt_tokens'],
                'response':reference(path/'response-original.json')})
        wire_lengths.append({'request_id':manifest['identity']['request_id'],'input_tokens':response['usage']['prompt_tokens'],
            'masked_messages':len(treatment.get('masked',[])),'complete_recent_cycles':treatment.get('keep_complete_tool_cycles')})
    boundary=read(folder/'controller-output/managed-boundary.json')
    return {'slot_index':row['slot_index'],'instance_id':row['instance_id'],'group_id':row['group_id'],
        'agent_requests':len(requests),'masked_original_observations':list(masked.values()),
        'mapped_masked_originals':sum(v['mapped_to_prior_visible_message'] for v in masked.values()),
        'retrieval_tools':dict(retrievals),'same_arguments_and_observed_version_read_repeats':sum(n-1 for n in repeated_reads.values()),
        'read_repeat_identity_limit':'workspace version is from visible user observations; missing version is not proof of same tree',
        'actions':actions,'request_lengths':wire_lengths,
        'terminal_details':boundary.get('terminal_details',{}),
        'final_outcome_not_used_to_select_old_information':True,
        'historical_trace_not_counterfactual_causal_proof':True}


def main():
    os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-2:]))
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[r for r in read(RUN/'execution-plan.json')['rows'] if r['primary_panel']]
    tests,groups=audit_tests(rows);test_ref=save('test-identities.json',tests)
    focused=[]
    for row in rows:
        if row['slot_index'] in FOCUS:
            result=audit_trace(row);focused.append(save(str(row['slot_index'])+'-trace.json',result))
            print('trace',row['slot_index'],'masks',len(result['masked_original_observations']),'mapped',result['mapped_masked_originals'],flush=True)
    summary={'test_groups':groups,'test_records':test_ref,'focus_traces':focused,
        'dedup_identity':['episode','tree_hash','command','selector','environment_hash'],
        'time_metric':'public command wall time, not CPU-seconds or end-to-end episode duration',
        'duplicate_does_not_imply_waste':True,'new_API_calls':0,'new_Docker_objects':0,
        'model_facts_not_added_from_host':True,'raw_records_modified':False}
    save('summary.json',summary);print(json.dumps(groups,ensure_ascii=False))


if __name__=='__main__':main()
