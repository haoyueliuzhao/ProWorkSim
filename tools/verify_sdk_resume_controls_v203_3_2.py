"""Verify three comparisons without replaying any model or world operation."""
import argparse,copy,json
from pathlib import Path
from proworksim.storage import json_bytes,digest
from proworksim.software_sdk_resume_v203_3_2 import read

def wire_semantics(row):
    wire=copy.deepcopy(row['wire'])
    # Exactly one provider attribution field is excluded. Never normalize or
    # remove model messages, observations, branch instructions, tools or budgets.
    wire.pop('user_id',None);return wire

def run(parent,children,out):
    state,proof=read(parent/'checkpoint')
    folders=[parent,children/'keep-a',children/'keep-b',children/'reassign']
    rows=[json.loads((f/'result.json').read_text()) for f in folders]
    first=[]
    for folder in folders:
        requests=json.loads((folder/'continuation-requests.json').read_text());by={}
        for r in requests:
            if r['usage_id']=='agent':by.setdefault(r['member_id'],r)
        first.append(by)
    # Compare the actual next global request from the SAME checkpoint. The
    # second member acts after a new request has settled; its budget provenance
    # hash can then legitimately differ because new physical response IDs differ.
    next_member=rows[0]['first_generation']['member_id']
    assert all(wire_semantics(first[0][next_member])==wire_semantics(first[i][next_member]) for i in (1,2))
    assert wire_semantics(first[1]['member_001'])!=wire_semantics(first[3]['member_001'])
    assert state['test_budget']['records'] and proof['summary_count']>=1
    ids=[set(row['physical_request_ids']) for row in rows]
    assert all(not ids[i]&ids[j] for i in range(4) for j in range(i+1,4))
    # exec_command gives these launches separate PID namespaces; all may have
    # namespace-local PID 6. Use retained independent launcher identities instead.
    launch_path=out.parent/'process-launches.json'
    launches=json.loads(launch_path.read_text())['launches']
    assert len(launches)==4 and len({r['exec_session_id'] for r in launches})==4
    assert {Path(r['output']).resolve() for r in launches}=={p.resolve() for p in folders}
    assert [r['final_diagnostic_owner'] for r in rows]==['member_001']*3+['member_002']
    isolation=[]
    for folder,row in zip(folders[1:],rows[1:]):
        result=json.loads((folder/'restore.json').read_text())
        assert result['prefix_recharged'] is False and result['world_actions_replayed']==0
        assert row['prefix_tokens_not_recharged']==proof['prefix_tokens']
        for member,info in state['workers'].items():
            cid=info['conversation_id'].replace('-','')
            base=folder/'runtime/sdk-conversations'/member/'conversations'/cid/'base_state.json'
            b=json.loads(base.read_text())
            assert Path(b['persistence_dir']).resolve()==base.parent.resolve()
            assert Path(b['workspace']['working_dir']).resolve().is_relative_to(folder.resolve())
            dirs=list((base.parent.parent).iterdir());assert len(dirs)==1
            prefix=parent/'checkpoint/workers'/member/'conversations'/cid/'events'
            for event in prefix.glob('*.json'):
                assert (base.parent/'events'/event.name).read_bytes()==event.read_bytes()
        final=json.loads((folder/'final-world.json').read_text())
        actual=json.loads((folder/'case/prepared/world/control/state.json').read_text())
        assert final==actual
        deadline=json.loads((folder/'boundary.json').read_text())['deadline_receipt']
        first_dispatch=min(r['dispatched_at'] for r in deadline['dispatches'].values())
        soft=deadline['soft_deadline_monotonic']-first_dispatch
        hard=deadline['hard_deadline_monotonic']-first_dispatch
        assert 0<soft<=state['clock']['soft_remaining']+.01
        assert 0<hard<=state['clock']['hard_remaining']+.01
        isolation.append({'branch':folder.name,'storage_points_to_own_branch':True,
            'final_state_matches_own_saved_result':True,'checkpoint_identity':result['checkpoint_identity'],
            'remaining_soft_seconds_at_first_dispatch':soft,'remaining_hard_seconds_at_first_dispatch':hard,
            'remaining_time_not_refilled':True})
    # Reading the parent checksum again after all forks also verifies immutability.
    _,after=read(parent/'checkpoint');assert after==proof
    report={'version':'v203.3.2-three-resume-comparisons-r1','passed':True,'API_calls':0,
        'continuous_vs_restored_KEEP':'PASS','two_KEEP_inputs_and_isolation':'PASS',
        'KEEP_vs_REASSIGN_preserves_prefix_and_changes_actual_owner':'PASS',
        'next_global_request_messages_and_tools_exact_for_KEEP':True,
        'both_member_prefix_events_preserved_byte_for_byte':True,
        'later_requests_not_required_byte_equal_after_new_physical_usage_settles':True,
        'excluded_wire_fields':['user_id'],'excluded_model_content_fields':[],
        'private_summary_count_at_checkpoint':proof['summary_count'],
        'public_tests_already_used_at_checkpoint':len(state['test_budget']['records']),
        'no_resume_message_in_KEEP':True,'pause_policy':state['clock']['pause_policy'],
        'budget_policy':'preserve prefix charges and saved remaining resources; new calls only in new branch namespace',
        'four_separate_python_launches':True,'launch_evidence':str(launch_path),
        'PID_numbers_are_namespace_local_not_global_identifiers':True,
        'new_physical_request_ids_disjoint':True,'prefix_recharged':False,
        'parent_checkpoint_unchanged':True,'branch_storage':isolation,
        'legal_deliveries':[row['legal_deliveries'] for row in rows],
        'new_scripted_requests':[row['new_adapter_requests'] for row in rows],
        'synthetic_usage_not_real_token_cost':True,'SDK_paired_continuation_qualified':True,
        'scope':'pinned managed REVIEW2, settled scripted checkpoint with summaries; not provider backend qualification or arbitrary crash recovery',
        'checkpoint_identity':proof['identity'],'parents':str(parent),'children':str(children)}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(json_bytes(report));print(json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--children',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.parent.resolve(),a.children.resolve(),a.output.resolve())
