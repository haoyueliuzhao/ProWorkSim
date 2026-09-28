"""Frozen sampling shares and nonbusiness identity controls."""
import copy
import json

from proworksim.candidate_runtime_v017 import parse_candidate_generated
from proworksim.deterministic_work_v024 import deterministic_tool_ids
from proworksim.storage import read_json
from proworksim.templates import retail_collaboration_v024 as world
from scripts.retail_work_controls_v024 import ProgramOwner


def test_catalog_new_entities_matched_second_window_and_interleaved_evaluation():
    catalog = world.registry()
    assert read_json(world.PIN_PATH.parent/'catalog.json') == catalog
    assert len(catalog['all_cases']) == 14
    assert len(catalog['evaluation_cases']) == 6
    assert len(catalog['evaluation_slots']) == 12
    assert [s['task'] for s in catalog['evaluation_slots']] == ['joint_a', 'joint_b', 'maintenance'] * 4
    manifest = read_json(world.PIN_PATH)
    seen = {k: set() for k in ('customers', 'invoice_ids', 'source_rows')}
    old = dict(zip(seen, ['excluded_customers', 'excluded_invoices', 'excluded_source_rows']))
    for entry in manifest['slices']:
        assert max(entry['complete_invoice_rows'].values()) <= 3
        for key in seen:
            values = set(entry[key])
            assert not values & (seen[key] | set(manifest[old[key]]))
            seen[key].update(values)
    common, mc, rtg = catalog['sampling_windows']
    assert mc['slots'] == rtg['slots']
    assert len({w['window_id'] for w in (common, mc, rtg)}) == 3
    for window in catalog['training_windows']:
        assert [s['task'] for s in window['slots']] == ['joint_a', 'joint_b', 'implement', 'review', 'joint_a', 'joint_b']
    assert catalog['qualities']['training_b_by_window'] == ['correct', 'wrong_count']
    assert catalog['qualities']['training_review_by_window'] == ['wrong_amount', 'correct']
    assert [c['maintenance']['expected_result_change'] for c in catalog['evaluation_cases'][4:]] == [True, False]


def test_actual_world_runtime_keeps_real_identities_and_visible_requests_repeat(tmp_path):
    case = world.registry()['evaluation_cases'][0]
    observations, identities, commands = [], [], []
    for side in ('one', 'two'):
        folder = tmp_path/side
        prepared = world.build_case(case, folder)
        owner = ProgramOwner(case['task'])
        runtime, captures, _ = world.runtime(owner, prepared, folder, episode_key=103)
        for _ in range(4):
            assert runtime.step()['status'] in {'running', 'completed'}
        identities.append(read_json(folder/'visible-identity.json'))
        observations.append([r['messages'] for r in owner.requests])
        commands.append({r: [x for x in rows if x['kind'] == 'tool_call'] for r, rows in captures.items()})
    assert identities[0]['actual_instance_id'] != identities[1]['actual_instance_id']
    assert identities[0]['actual_branch_id'] != identities[1]['actual_branch_id']
    assert identities[0]['actual_run_id'] != identities[1]['actual_run_id']
    assert identities[0]['visible_runtime_id'] == identities[1]['visible_runtime_id']
    assert observations[0] == observations[1]
    assert commands[0] == commands[1]
    body = json.loads(observations[0][0][-1]['content'])
    assert body['observation']['actor_id'] == 'provider'
    assert body['observation']['workspaces']['TEAM']['basis'] != body['observation']['workspaces']['TEAM']['data']


def test_native_host_call_ids_depend_on_exact_reference_and_permissions():
    request = {'messages': [{'role': 'user', 'content': 'read exact work evidence'}], 'tools': []}
    raw = '<tool_call>\n<function=read_alias>\n<parameter=alias>basis</parameter>\n</function>\n</tool_call>'
    a, error = parse_candidate_generated(raw, request)
    b, error2 = parse_candidate_generated(raw, request)
    assert error is None and error2 is None
    assert a['tool_calls'][0]['id'] != b['tool_calls'][0]['id']
    a, b = deterministic_tool_ids(a, request, raw), deterministic_tool_ids(b, request, raw)
    assert a == b
    assert deterministic_tool_ids(a, request, 'different freeform preamble') == a
    other = copy.deepcopy(a)
    other['tool_calls'][0]['function']['arguments'] = '{"reference":{"object_id":"data","version_id":"v2"}}'
    assert deterministic_tool_ids(other, request, raw)['tool_calls'][0]['id'] != a['tool_calls'][0]['id']
    changed_permissions = {**request, 'tools': [{'type': 'function', 'function': {'name': 'write_object'}}]}
    assert deterministic_tool_ids(a, changed_permissions, raw)['tool_calls'][0]['id'] != a['tool_calls'][0]['id']


def test_canonical_receipt_checks_exact_raw_hash_arguments_and_object(tmp_path):
    from proworksim.deterministic_work_v024 import DeterministicWorkInterface
    from proworksim.presentations import MARKER, response_matches_receipt
    case = world.registry()['evaluation_cases'][2]
    prepared = world.build_case(case, tmp_path/'world')
    interface = DeterministicWorkInterface(prepared.world.session('reviewer', 'TEAM'), 'reviewer', variant='v14', presentation='compact_v14')
    sid = prepared.world.state['work_items'][world.WORK]['submissions'][-1]['submission_id']
    args = {'work_id': world.WORK, 'submission_id': sid}
    response = interface.call('inspect_submission', request_key='test-canonical', **args)
    commit = prepared.world.state['operation_commits'][response['command_id']]
    assert response_matches_receipt(commit, response, action='inspect_submission', arguments=args)
    for altered in ('hash', 'object', 'scope'):
        forged = copy.deepcopy(response)
        if altered == 'hash':
            forged[MARKER]['raw_response_sha256'] = '0'*64
        elif altered == 'object':
            forged['result']['artifact_versions']['wrong-object'] = 'v99'
        else:
            forged[MARKER]['project_id'] = 'OTHER'
        assert not response_matches_receipt(commit, forged, action='inspect_submission', arguments=args)
    assert not response_matches_receipt(commit, response, action='inspect_submission', arguments={**args, 'include_contract': True})
