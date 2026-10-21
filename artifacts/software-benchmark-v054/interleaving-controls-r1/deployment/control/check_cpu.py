"""Pure CPU controls for new launch selection, bounded permit and exact comparisons."""
import ast
import copy
import json
from pathlib import Path
import re
import tempfile
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_benchmark_match_v054 import TOOL_NAMES

stage=Path('/tmp/v054-interleave-deploy-r1')
checks={}
def check(name, condition):
    checks[name]=bool(condition)
    assert condition,name

def rejected(callback):
    try: callback()
    except (ValueError,KeyError): return True
    return False

def extracted(path,names,context):
    tree=ast.parse(path.read_text())
    nodes=[item for item in tree.body if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)) and item.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),context)
    return context

with tempfile.TemporaryDirectory(prefix='v054-launch-control-',dir=stage/'control') as directory:
    root=Path(directory)
    entry=root/'tools/serve_interleaved_owner_v054.py'; entry.parent.mkdir()
    entry.write_text('fixed trusted entry source\n')
    manager=root/'src/proworksim/software_benchmark_interleaved_owner_v054.py';manager.parent.mkdir(parents=True)
    manager.write_text('fixed manager source\n')
    launch=extracted(stage/'tools/run_match_resident_v054.py',{'owner_program'},
                     {'ROOT':root,'Path':Path,'checked':checked})['owner_program']
    check('legacy_v2_stays_fixed_single_session',launch({'version':'v054-match-resident-spec-v2'})==(root/'tools/serve_resident_owner_v054.py',[]))
    spec={'version':'v054-match-resident-spec-v3','session_protocol':'mp-interleave-v1','maximum_sessions':2,
          'owner_entrypoint':reference(entry),'sources':[reference(entry),reference(manager)]}
    check('v3_only_fixed_entrypoint_and_two_sessions',launch(spec)==(entry,['--max-sessions','2']))
    other=root/'tools/other.py';other.write_text('not permitted\n')
    bad={**spec,'owner_entrypoint':reference(other),'sources':[reference(other),reference(manager)]}
    check('arbitrary_script_rejected',rejected(lambda:launch(bad)))
    check('wrong_or_boolean_capacity_rejected',all(rejected(lambda n=n:launch({**spec,'maximum_sessions':n})) for n in (1,3,True)))
    check('legacy_cannot_silently_change_semantics',rejected(lambda:launch({'version':'v054-match-resident-spec-v2','maximum_sessions':2})))
    check('unsealed_manager_rejected',rejected(lambda:launch({**spec,'sources':[reference(entry)]})))
    namespace=extracted(stage/'tools/check_match_interleave_v054.py',
        {'plan','make_permit','preparation_permit','validate_permit','comparisons','serialized_turns','projection','read_ref'},
        {'Path':Path,'re':re,'copy':copy,'json':json,'checked':checked,'TOOL_NAMES':TOOL_NAMES,
         'PERMIT_VERSION':'v054-resident-interleave-control-v1','PROTOCOL':'mp-interleave-v1'})
    permit=namespace['preparation_permit'](resident_id='synthetic-control',gpu_index=3,
        gpu_uuid='GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',source_manifest=reference(entry))
    namespace['validate_permit'](permit)
    check('permit_exactly_four_sessions_six_calls',len(permit['sessions'])==4 and sum(s['maximum_generation_requests'] for s in permit['sessions'])==6)
    check('paired_seeds_and_distinct_A_B',permit['sessions'][0]['seed']==permit['sessions'][2]['seed']!=permit['sessions'][1]['seed']==permit['sessions'][3]['seed'])
    check('condenser_preserves_original_empty_tool_contract',permit['requests']['A2']['tools']==[] and permit['usage_ids']['A2']=='condenser' and permit['requests']['A2']['max_tokens']==2048)
    bad=copy.deepcopy(permit);bad['maximum_generation_requests']=7
    check('extra_request_authorization_rejected',rejected(lambda:namespace['validate_permit'](bad)))
    bad=copy.deepcopy(permit);bad['requests']['A1']['messages'][0]['content']='changed'
    check('changed_synthetic_prompt_rejected',rejected(lambda:namespace['validate_permit'](bad)))
    values={(phase,label):{'output':{'text':'complete'},'token_trace':{'input_ids':[1,2],'output_ids':[3],'behavior_logprobs':[-.5]},'rng':{'before':'a','after':'b'}} for phase in ('baseline','interleaved') for label in ('A1','A2','B1')}
    check('exact_comparisons_accept_identical_values',all(all(row.values()) for row in namespace['comparisons'](values).values()))
    values[('interleaved','A2')]['token_trace']['output_ids']=[4]
    values[('interleaved','B1')]['rng']['after']='changed'
    compared=namespace['comparisons'](values)
    check('token_and_rng_changes_rejected',not compared['A2']['token_trace'] and not compared['B1']['rng'])
    turns=[{'turn':{'ordinal':i,'started_monotonic':float(i),'finished_monotonic':i+.5}} for i in range(6)]
    check('observed_fifo_turns_accept_serial_order',namespace['serialized_turns'](turns))
    turns[3]['turn']['started_monotonic']=2.4
    check('overlapping_turns_rejected',not namespace['serialized_turns'](turns))
    body={'http_status':200,'body':{'id':'unimportant','online_window_id':'window-A','usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3},'raw_generated_text':'complete original text','native_finish_reason':'stop','choices':[{'index':0,'message':{'role':'assistant','content':None,'tool_calls':[{'id':'random1','type':'function','function':{'name':'terminal','arguments':'{"id": "meaningful"}'}}]},'finish_reason':'tool_calls'}],'token_trace':{'input_ids':[1,2],'output_ids':[3],'behavior_logprobs':[-.5]}}}
    otherbody=copy.deepcopy(body);otherbody['body']['id']='other';otherbody['body']['online_window_id']='otherwindow';otherbody['body']['choices'][0]['message']['tool_calls'][0]['id']='random2'
    check('transport_ids_excluded_but_full_output_retained',namespace['projection'](body,'PROJECT')==namespace['projection'](otherbody,'PROJECT'))
    otherbody['body']['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{"id": "changed"}'
    check('actual_tool_arguments_not_erased',namespace['projection'](body,'PROJECT')!=namespace['projection'](otherbody,'PROJECT'))
report={'version':'v054-interleave-deployment-cpu-control-r1','passed':all(checks.values()),'checks':checks,
        'model_calls':0,'GPU_queries':0,'GPU_loads':0,'formal_slots_claimed':0,
        'scope':'actual new function ASTs; synthetic plain JSON and private temp files only; not the pending real GPU control'}
(stage/'control/receipt.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
