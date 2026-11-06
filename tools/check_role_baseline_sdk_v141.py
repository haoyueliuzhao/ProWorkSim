"""Actual OpenHands SDK/private history, scripted provider and real CPU public tests."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
ROOT = Path(__file__).resolve().parents[1]


def fixture(folder, group):
    from proworksim import software_role_baseline_world_v141 as world
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest, json_bytes
    source = folder/'source'
    source.mkdir(parents=True)
    (source/'sample.py').write_text('value = 1\n')
    (source/'test_sample.py').write_text('def test_value():\n    from sample import value\n    assert value == 2\n')
    manifest = capture_repository(source, folder/'snapshot', task_id='fixture__sdk-141',
        problem_statement='Synthetic CPU fixture: repair value to 2.',
        source_identity={'instance_id': 'fixture__sdk-141', 'repo': 'fixture/sdk',
                         'base_commit': 'a'*40, 'dataset_revision': 'b'*40})
    argv = [str(ROOT/'.venv/bin/python'), '-m', 'pytest', '-q', 'test_sample.py']
    entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': 'fixture__sdk-141',
             'argv': argv, 'cwd': '/testbed', 'timeout_seconds': 20, 'hidden_material_used': False}
    calls = []

    def public_test(*, files, entry_metadata, request):
        calls.append(copy.deepcopy(request))
        target = folder/'actual-public-tests'/str(len(calls))
        target.mkdir(parents=True)
        for name in ('sample.py', 'test_sample.py'):
            (target/name).write_text(files[name])
        proc = subprocess.run(argv, cwd=target, capture_output=True, text=True, timeout=20,
                              env={'PATH': '/usr/bin:/bin', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'})
        passed = proc.returncode == 0
        counts = {'collected': 1, 'passed': int(passed), 'failed': int(not passed),
                  'errors': 0, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 1}
        return {'passed': passed, 'execution': {'executed': True,
            'input_tree_sha256': request['tree_sha256'], 'actor_id': request['actor_id'],
            'organization_id': group, 'managed_request_sha256': digest(json_bytes(request)),
            'argv': argv, 'public_test_selection': request['public_test_selection'],
            'public_test_selection_revision': 'v110-public-test-selection-r1',
            'validation_status': 'verified' if passed else 'failed', 'counts': counts,
            'test_evidence': {'source': 'actual CPU pytest', 'returncode': proc.returncode}},
            'groups': {'public_repository_tests': {'passed': passed, 'executed': True,
                'status': 'passed' if passed else 'failed', 'output': proc.stdout[-4000:],
                'tests': [{'test_id': 'test_sample.py::test_value', 'passed': passed}]}},
            'repository_collection_errors': []}
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    return world.prepare_case(manifest, folder/'prepared', organization_id=group,
        public_test_callback=public_test, deadline=deadline, public_test_entry=entry), deadline, calls


def run(folder, group):
    from proworksim import software_role_baseline_runtime_v141 as runtime_module
    from proworksim.software_benchmark_alignment_contract_v141 import condition
    from proworksim.software_benchmark_candidates_v054 import write_new
    from proworksim.storage import digest, json_bytes
    prepared, deadline, public_calls = fixture(folder/'case', group)
    cfg = condition(group)
    slot = f"cpu-v141:fixture__sdk-141:{cfg['condition_id']}:141"
    requests, counts, summaries = [], {m: 0 for m in cfg['fixed_members']}, []
    marker = 'PRIVATE_ONLY_MEMBER001_V141'
    holder, positions = {}, {m: 0 for m in cfg['fixed_members']}
    author = [('work_note', {'key': 'private', 'text': marker}),
        ('org_declare_role', {'role_label': 'Integrator', 'responsibility': 'Deliver exact tested code', 'reason': 'Explicit focus'}),
        ('read_file', {'path': 'sample.py', 'cursor': None})]
    if group == 'S1':
        author += [('write_file', {'path': 'sample.py', 'text': 'value = 2\n'}), ('run_tests', {}),
            ('fix_patch', {'task_ids': [], 'message': 'Tested final'}), ('submit_integration', {'message': 'Final'})]
    else:
        author += [('send_message', {'recipient': 'member_002', 'task_id': 'root_goal', 'body': 'Please implement value = 2; I will integrate.'}),
                   ('WAIT_PATCH', {}), ('integrate_patch', {'patch_id': 'patch-1'}), ('run_tests', {}),
                   ('fix_patch', {'task_ids': [], 'message': 'Integrated final'})]
        if group == 'REVIEW2':
            author += [('handoff_patch', {'patch_id': 'patch-2', 'to_member': 'member_002', 'message': 'Review the exact final version'}),
                       ('WAIT_REVIEW', {})]
        author += [('submit_integration', {'message': 'Final explicitly integrated version'})]
    author += [('staff_done', {'reason': 'Current work done'}), ('staff_done', {'reason': 'Final private review complete'})]
    peer = [('org_declare_role', {'role_label': 'Partner', 'responsibility': 'Produce and validate candidate', 'reason': 'Explicit focus'}),
        ('read_file', {'path': 'sample.py', 'cursor': None}),
        ('write_file', {'path': 'sample.py', 'text': 'value = 2\n'}), ('run_tests', {}),
        ('fix_patch', {'task_ids': [], 'message': 'Distinct partner code'}),
        ('handoff_patch', {'patch_id': 'patch-1', 'to_member': 'member_001', 'message': 'Please adopt and test'})]
    if group == 'REVIEW2':
        peer += [('WAIT_FINAL', {}), ('integrate_patch', {'patch_id': 'patch-2'}), ('run_tests', {}),
                 ('org_review_patch', {'patch_id': 'patch-2', 'decision': 'accept', 'reason': 'Actual independent same-version public test passed'})]
    peer += [('staff_done', {'reason': 'Current partner work done'}), ('staff_done', {'reason': 'Final private review complete'})]

    def post(route, payload):
        member, wire = payload['member_id'], payload['wire']
        if member != 'member_001':
            assert marker not in json.dumps(wire['messages'])
        if route in {'/tokenize', '/tokenize-prefix'}:
            return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(wire)),
                    'method': 'scripted CPU count', 'count_only_not_dispatchable': route.endswith('prefix')}
        assert route == '/chat/completions'
        requests.append(copy.deepcopy(payload))
        assert len(requests) < 90, 'A scripted fixture looped'
        if payload['usage_id'] == 'condenser':
            summaries.append(payload['request_id'])
            holder['runtime'].policies[member].agent.condenser.max_size = 80
            message, finish = {'role': 'assistant', 'content': 'Private summary of my own explicitly observed source and shared patch only.'}, 'stop'
        else:
            assert wire['tools'] == runtime_module.member_wire_tools(group, member)
            counts[member] += 1
            actions = author if member == 'member_001' else peer
            index = positions[member]
            name, arguments = actions[index] if index < len(actions) else ('staff_done', {'reason': 'No further work'})
            if name.startswith('WAIT_'):
                facts = prepared.world._software()
                available = {'WAIT_PATCH': 'patch-1' in facts['patches'],
                             'WAIT_FINAL': 'patch-2' in facts['patches'],
                             'WAIT_REVIEW': any(r.get('decision') == 'accept' for r in prepared.world.org_state()['reviews'])}
                if available[name]:
                    positions[member] += 1
                    name, arguments = actions[positions[member]]
                else:
                    name, arguments = 'staff_wait', {'reason': 'Await actual peer evidence'}
                    index = -1
            if index >= 0:
                positions[member] += 1
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': f'cpu-{member}-{counts[member]}',
                'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}
            finish = 'tool_calls'
        return {'id': 'cpu-'+str(len(requests)), 'model': 'deepseek-flash', 'object': 'chat.completion', 'created': 0,
            'choices': [{'index': 0, 'finish_reason': finish, 'message': message}],
            'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                      'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
    owner = runtime_module.build_team_owner(post, organization_id=group, slot_id=slot,
        condition_id=cfg['condition_id'], folder=folder/'model-ledger', deadline=deadline,
        identity={'policy_version': 'scripted-CPU-only'}, observation_token_counter=lambda s: len(s.split()),
        observation_tokenizer_id='fixture-word-counter-NOT-provider-billing')
    runtime, _, _ = runtime_module.build_runtime(owner, prepared, folder/'runtime', deadline=deadline,
        public_initial_message='Synthetic CPU control. No benchmark or external service.')
    holder['runtime'] = runtime
    if group == 'REVIEW2':
        runtime.policies['member_002'].agent.condenser.max_size = 12
    try:
        boundary = runtime_module.run_fragment(prepared, runtime)
        write_new(folder/'boundary.json', boundary)
        assert boundary['execution_integrity_failure'] is None, boundary
        assert len(prepared.world._software()['deliveries']) == 1, boundary
        assert owner.adapter.ledger.actual == len(requests)*281 == runtime.team_budget.snapshot()['charged_tokens']
        assert all(p.used == 1 for p in runtime.finish_review_policies.values())
    finally:
        runtime_module.close_runtime(runtime)
    lock = runtime_module.lock_fixed_candidates(prepared, folder/'closure', sdk_closed=True)
    assert owner.observation.errors == [], owner.observation.errors
    summary = json.loads((owner.observation.folder/'summary.json').read_bytes())
    assert summary['usage']['actual_total_tokens'] == owner.adapter.ledger.actual
    if group != 'S1':
        assert summary['artifacts']['entered_legal_delivery_chain'] == 1, summary
        assert summary['messages']['unique_obtained_pairs'] == 1, summary
    if group == 'REVIEW2':
        assert summaries and summary['artifacts']['independent_review_events'] == 1
    result = {'passed': True, 'group': group, 'real_model_calls': 0, 'API_calls': 0, 'Docker_operations': 0,
        'scripted_requests': len(requests), 'scripted_summary_requests': len(summaries),
        'scripted_tokens': owner.adapter.ledger.actual, 'actual_public_test_calls': len(public_calls),
        'source_actor_ids': [p['actor_id'] for p in public_calls], 'private_sessions': len(runtime.policies),
        'observation': summary, 'lock': lock}
    write_new(folder/'requests.json', requests)
    write_new(folder/'summary.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--groups', nargs='+', choices=('S1', 'FREE2', 'REVIEW2'), default=['S1', 'FREE2', 'REVIEW2'])
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    os.environ['OH_PERSISTENCE_DIR'] = str(folder/'sdk-settings')

    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            raise AssertionError('No network in CPU SDK control')
        if event == 'subprocess.Popen':
            argv, cwd = args[1], str(args[2])
            is_test = (isinstance(argv, (tuple, list)) and list(argv) == [str(ROOT/'.venv/bin/python'), '-m', 'pytest', '-q', 'test_sample.py']
                       and str(folder) in cwd and '/actual-public-tests/' in cwd)
            is_codec = (isinstance(argv, (tuple, list)) and Path(argv[0]).name == 'git'
                        and 'proworksim-v054-candidate-' in cwd)
            if not (is_test or is_codec):
                raise AssertionError('Only CPU public tests and candidate codec subprocesses are allowed')
    sys.addaudithook(audit)
    results = [run(folder/group, group) for group in args.groups]
    (folder/'summary.json').write_text(json.dumps({'passed': True, 'groups': results}, indent=2)+'\n')
    print(json.dumps({'passed': True, 'path': str(folder/'summary.json')}))


if __name__ == '__main__':
    main()
