"""One real SDK REVIEW2 chain with a private member002 summary; no model/API."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    folder = parser.parse_args().output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    os.environ['OH_PERSISTENCE_DIR'] = str(folder/'sdk-settings')
    def deny(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            raise AssertionError('No network or API in the scripted SDK control')
        if event == 'subprocess.Popen':
            argv = args[1]
            allowed = {'init', 'config', 'add', 'write-tree', 'diff', 'apply', 'ls-files',
                       'read-tree', 'hash-object', 'cat-file', 'update-index'}
            prefix = ['-c', 'core.hooksPath='+os.devnull, '-c', 'core.attributesFile='+os.devnull,
                      '-c', 'core.autocrlf=false', '-c', 'core.filemode=true']
            if (not isinstance(argv, (list, tuple)) or Path(argv[0]).name != 'git'
                    or list(argv[1:9]) != prefix or len(argv)<10 or argv[9] not in allowed
                    or 'proworksim-v054-candidate-' not in str(args[2])):
                raise AssertionError('Only local candidate-codec Git may execute in the CPU fixture')
    sys.addaudithook(deny)
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('fixture_v131', root/'tests/test_fixed_organization_v131.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    from proworksim import software_fixed_organization_runtime_v131 as runtime_module
    from proworksim.software_benchmark_alignment_contract_v131 import condition
    from proworksim.software_benchmark_project_closure_v131 import export_managed_closure, validate_delivery_evidence
    from proworksim.software_benchmark_candidates_v054 import reference, write_new, checked
    from proworksim.storage import digest, json_bytes
    prepared, deadline, public_calls = fixtures.fixture(folder/'case', 'REVIEW')
    group = 'REVIEW'
    cfg = condition(group)
    slot = f"v131:fixture__team-1:{cfg['condition_id']}:131"
    requests, agent_calls, summary_calls = [], {'member_001': 0, 'member_002': 0}, []
    private_marker = 'PRIVATE_NOTE_ONLY_MEMBER001_V131'
    owner_actions = [
        ('work_note', {'key': 'private', 'text': private_marker}),
        ('write_file', {'path': 'sample.py', 'text': 'value = 2\n'}),
        ('run_tests', {}), ('fix_patch', {'task_ids': [], 'message': 'public candidate'}),
        ('staff_wait', {'reason': 'Await independent member002 review'}),
        ('submit_integration', {'message': 'Reviewed same-version team delivery'}),
        ('staff_done', {'reason': 'Current work complete'}),
        ('staff_done', {'reason': 'Final self-review complete'})]
    holder = {}
    def post(route, payload):
        member = payload['member_id']
        assert member in agent_calls and payload['team_slot_id'] == slot
        wire = payload['wire']
        if member == 'member_002':
            assert private_marker not in json.dumps(wire['messages'])
        if route in {'/tokenize', '/tokenize-prefix'}:
            assert set(payload) == ({'wire', 'member_id', 'team_slot_id', 'pending_ids'}
                if route.endswith('prefix') else {'wire', 'member_id', 'team_slot_id'})
            return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(wire)),
                'method': 'scripted CPU count', 'count_only_not_dispatchable': route.endswith('prefix')}
        assert route == '/chat/completions' and payload['slot_id'] == slot
        assert payload['request_id'].startswith(slot+':'+member+':')
        requests.append(copy.deepcopy(payload))
        usage = payload['usage_id']
        if usage == 'condenser':
            assert member == 'member_002' and not wire.get('tools')
            summary_calls.append(copy.deepcopy(payload))
            holder['runtime'].policies[member].agent.condenser.max_size = 80
            message = {'role': 'assistant', 'content': 'Member002 inspected only its own source and the explicitly published candidate; private peer notes were not available.'}
            finish = 'stop'
        else:
            assert wire['tools'] == runtime_module.member_wire_tools(group, member)
            agent_calls[member] += 1
            n = agent_calls[member]
            if member == 'member_001':
                name, args = owner_actions[n-1] if n <= len(owner_actions) else ('staff_done', {'reason': 'No further current work'})
            elif n < 6 or not summary_calls:
                name, args = ('read_file', {'path': 'sample.py', 'cursor': None})
            elif n == 6:
                name, args = ('org_review_patch', {'patch_id': 'patch-1', 'decision': 'accept', 'reason': 'Independently reviewed exact candidate'})
            else:
                name, args = ('staff_done', {'reason': 'Review work complete'})
            assert n < 20
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': f'cpu-{member}-{n}',
                'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}
            finish = 'tool_calls'
        return {'id': 'cpu-response-'+str(len(requests)), 'model': 'deepseek-flash',
            'object': 'chat.completion', 'created': 0,
            'choices': [{'index': 0, 'finish_reason': finish, 'message': message}],
            'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
    owner = runtime_module.build_team_owner(post, organization_id=group, slot_id=slot,
        condition_id=cfg['condition_id'], folder=folder/'model-ledger', deadline=deadline,
        identity={'policy_version': 'scripted-CPU-only'})
    runtime, _, _ = runtime_module.build_runtime(owner, prepared, folder/'runtime', deadline=deadline,
        public_initial_message='Synthetic CPU source only; no benchmark answer or external service.')
    holder['runtime'] = runtime
    runtime.policies['member_002'].agent.condenser.max_size = 12  # fixture-only trigger
    sessions = {member: str(worker.conversation.id) for member, worker in runtime.policies.items()}
    assert len(set(sessions.values())) == 2
    try:
        boundary = runtime_module.run_fragment(prepared, runtime)
        write_new(folder/'boundary.json', boundary)
        assert boundary['execution_integrity_failure'] is None, boundary['execution_integrity_failure']
        assert summary_calls and boundary['cash_censored'] is False
        assert all(policy.used == 1 for policy in runtime.finish_review_policies.values())
        assert owner.adapter.ledger.actual == len(requests)*281 == runtime.team_budget.snapshot()['charged_tokens']
        assert owner.adapter.ledger.attempts == len(requests)
        assert sum(worker.meter['budget_accounted_tokens'] for worker in runtime.policies.values()) == owner.adapter.ledger.actual
        assert len({row['request_id'] for row in requests}) == len(requests)
        assert len(public_calls) == 1 and public_calls[0]['actor_id'] == 'member_001'
        assert len(prepared.world._software()['deliveries']) == 1
        actual_schemas = {member: [{'type': 'function', 'function': copy.deepcopy(item)} for item in worker.definitions]
                          for member, worker in runtime.policies.items()}
    finally:
        runtime_module.close_runtime(runtime)
    closure = export_managed_closure(prepared, folder/'closure', slot_id=slot, sdk_closed=True)
    evidence = json.loads(checked(closure['delivery_evidence']).read_bytes())
    snapshot = json.loads(checked(closure['delivery_snapshot']).read_bytes())
    baseline = json.loads(checked(closure['baseline_snapshot']).read_bytes())
    verdict = validate_delivery_evidence(evidence, snapshot, baseline)
    assert verdict['submitted'] and verdict['organization_submission_verified'] and verdict['same_tree']
    broken = copy.deepcopy(evidence)
    proof = next(iter(broken['organization_delivery_inventory'].values()))
    proof['organization_state']['review']['reviews'] = {}
    proof['guard_state_sha256'] = digest(json_bytes([proof['organization_state'], proof['tasks'], proof['patches']]))
    try:
        validate_delivery_evidence(broken, snapshot, baseline)
    except Exception:
        pass
    else:
        raise AssertionError('A submission without its independent review was accepted')
    result = {'passed': True, 'version': runtime_module.VERSION, 'organization_id': group,
        'private_session_ids': sessions, 'scripted_requests': len(requests),
        'scripted_agent_requests_per_member': agent_calls, 'scripted_summary_requests': len(summary_calls),
        'scripted_tokens': owner.adapter.ledger.actual, 'real_model_tokens': 0,
        'shared_pool_three_meters_equal': True, 'member002_summary_private_sources_only': True,
        'shared_summary_budget_and_attempt_charged': True,
        'actual_member_wire_tools': actual_schemas, 'closure': closure,
        'organization_submission_verified': True, 'missing_review_rejected': True,
        'old_offline_switch_used': False, 'API_calls': 0, 'Docker_operations': 0,
        'world_source': reference(root/'src/proworksim/software_fixed_organization_world_v131.py'),
        'runtime_source': reference(runtime_module.__file__)}
    result['closure'].pop('terminal_bundle', None)
    write_new(folder/'requests.json', requests)
    ref = write_new(folder/'summary.json', result)
    print(json.dumps(ref, ensure_ascii=False))


if __name__ == '__main__':
    main()
