"""Pinned OpenHands + original REVIEW2 Harness with scripted CPU transport only."""
import copy
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'runs/v016-sdk/resident-venv/lib/python3.12/site-packages'))
sys.path.insert(0, str(ROOT / 'src'))
os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
mode = sys.argv[1]
folder = ROOT / 'runs/software-benchmark-v203-2-1/sdk-controls-r1' / mode
folder.mkdir(parents=True, exist_ok=False)
os.environ['OH_PERSISTENCE_DIR'] = str(folder / 'sdk-settings')


def audit(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
        raise AssertionError('No network in actual SDK CPU control')
    if event == 'subprocess.Popen':
        argv, cwd = args[1], str(args[2])
        public = isinstance(argv, (tuple, list)) and list(argv) == [str(ROOT / '.venv/bin/python'), '-m', 'pytest', '-q', 'test_sample.py'] and str(folder) in cwd and '/actual-public-tests/' in cwd
        codec = isinstance(argv, (tuple, list)) and Path(argv[0]).name == 'git' and 'proworksim-v054-candidate-' in cwd
        if not (public or codec):
            raise AssertionError('Only original CPU public test and candidate codec processes are allowed')


sys.addaudithook(audit)
from proworksim import software_role_baseline_runtime_v203_2_1 as managed
from proworksim import software_role_baseline_runtime_v141 as original
from proworksim.software_observer_journal_v203_2_1 import ObserverJournal
from proworksim.software_benchmark_alignment_contract_v141 import condition
from proworksim.storage import digest, json_bytes

spec = importlib.util.spec_from_file_location('original_review2_fixture', ROOT / 'tools/check_role_baseline_sdk_v141.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
prepared, deadline, public_calls = fixture.fixture(folder / 'case', 'REVIEW2')
cfg = condition('REVIEW2')
slot = 'cpu-v203.2.1:fixture__sdk-141:REVIEW2:' + mode
positions = {m: 0 for m in cfg['fixed_members']}
actions = {
    'member_001': [('work_note', {'key': 'private', 'text': 'PRIVATE_001_ONLY'}),
                   ('read_file', {'path': 'sample.py', 'cursor': None}),
                   ('write_file', {'path': 'sample.py', 'text': 'value = 2\n'}),
                   ('run_tests', {}), ('fix_patch', {'task_ids': [], 'message': 'CPU fixed candidate'}),
                   ('handoff_patch', {'patch_id': 'patch-1', 'to_member': 'member_002', 'message': 'Review actual same version'}),
                   ('WAIT_REVIEW', {}), ('submit_integration', {'message': 'CPU same-version delivery'}),
                   ('staff_done', {'reason': 'Complete'}), ('staff_done', {'reason': 'Private review complete'})],
    'member_002': [('WAIT_PATCH', {}), ('integrate_patch', {'patch_id': 'patch-1'}),
                   ('run_tests', {}), ('org_review_patch', {'patch_id': 'patch-1', 'decision': 'accept', 'reason': 'Actual same-version public test passed'}),
                   ('staff_done', {'reason': 'Review complete'}), ('staff_done', {'reason': 'Private self-review complete'})],
}
primary_requests, primary_responses, primary_actions, response_identities = [], [], [], []
holder = {}


def post(route, payload):
    if route in {'/tokenize', '/tokenize-prefix'}:
        return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(payload['wire'])),
                'method': 'scripted CPU count', 'count_only_not_dispatchable': route.endswith('prefix')}
    assert route == '/chat/completions'
    primary_requests.append(copy.deepcopy(payload))
    assert len(primary_requests) < 60
    member = payload['member_id']
    wire = payload['wire']
    if member == 'member_002':
        assert 'PRIVATE_001_ONLY' not in json.dumps(wire['messages'])
    if mode == 'provider-exception':
        raise RuntimeError('original_scripted_provider_interruption')
    if payload['usage_id'] == 'condenser':
        holder['runtime'].policies[member].agent.condenser.max_size = 80
        message, finish = {'role': 'assistant', 'content': 'Private summary of actual own history only.'}, 'stop'
    else:
        assert wire['tools'] == original.member_wire_tools('REVIEW2', member) == managed.member_wire_tools('REVIEW2', member)
        index = positions[member]
        plan = actions[member]
        name, arguments = plan[index] if index < len(plan) else ('staff_done', {'reason': 'No further work'})
        if name.startswith('WAIT_'):
            available = ('patch-1' in prepared.world._software()['patches'] if name == 'WAIT_PATCH'
                         else any(row.get('decision') == 'accept' for row in prepared.world.org_state()['reviews']))
            if available:
                positions[member] += 1
                name, arguments = plan[positions[member]]
            else:
                name, arguments, index = 'staff_wait', {'reason': 'Await actual peer evidence'}, -1
        if index >= 0:
            positions[member] += 1
        message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'script-tool-' + str(len(primary_requests)),
                   'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}
        finish = 'tool_calls'
    response = {'id': 'script-response-' + str(len(primary_requests)), 'model': 'deepseek-flash',
                'system_fingerprint': 'cpu-script-not-provider', 'object': 'chat.completion', 'created': 0,
                'choices': [{'index': 0, 'finish_reason': finish, 'message': message}],
                'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                          'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
    primary_responses.append({'request_id': payload['request_id'], 'body': copy.deepcopy(response)})
    response_identities.append(response)
    return response


owner = managed.build_team_owner(post, organization_id='REVIEW2', slot_id=slot,
    condition_id=cfg['condition_id'], folder=folder / 'model-ledger', deadline=deadline,
    identity={'policy_version': 'CPU-scripted-no-model'},
    observation_token_counter=lambda text: len(text.split()),
    observation_tokenizer_id='CPU-word-estimate-not-provider-exact')
runtime, _, _ = managed.build_runtime(owner, prepared, folder / 'runtime', deadline=deadline,
    public_initial_message='Synthetic CPU SDK/Harness control only. No real model or benchmark task.')
holder['runtime'] = runtime
runtime.policies['member_001'].agent.condenser.max_size = 12
assert all(type(port).__name__ == 'HarnessPort' for port in runtime.ports.values())
# Capture independent execution entries/results outside the observer wrapper.
execute = runtime.execute
fault_state = {'dropped_intents': 0, 'after_commit_errors': 0}
if mode == 'observer-fault':
    record = owner.passive_sidecar.record
    def failing_record(kind, key, payload, source=None):
        journal = owner.passive_sidecar.journal
        old_fault = journal._fault
        inject = (kind == 'INTENT' and payload.get('tool') == 'read_file' and not fault_state['dropped_intents'])
        uncertain = kind == 'MODEL_RESPONSE' and not fault_state['after_commit_errors']
        if inject or uncertain:
            stage = 'before_write' if inject else 'after_commit'
            def fail(where):
                if where == stage:
                    raise OSError('scripted_sidecar_unavailable_' + stage)
            journal._fault = fail
            fault_state['dropped_intents' if inject else 'after_commit_errors'] += 1
        try:
            return record(kind, key, payload, source)
        finally:
            journal._fault = old_fault
    owner.passive_sidecar.record = failing_record


def primary_execute(actor, tool, arguments, association):
    response = execute(actor, tool, arguments, association)
    primary_actions.append({'actor': actor, 'tool': tool, 'arguments': copy.deepcopy(arguments),
                            'association': copy.deepcopy(association), 'response': copy.deepcopy(response)})
    return response


runtime.execute = primary_execute
try:
    boundary = managed.run_fragment(prepared, runtime)
finally:
    managed.close_runtime(runtime)

raw_folder = folder / 'primary'
raw_folder.mkdir()
for name, value in [('requests', primary_requests), ('responses', primary_responses), ('actions', primary_actions), ('boundary', boundary)]:
    (raw_folder / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
with ObserverJournal(owner.passive_sidecar.folder / 'events.sqlite') as journal:
    rows = list(journal.records())
    proof = journal.integrity()
by_kind = {}
for row in rows:
    by_kind.setdefault(row['kind'], []).append(row)
assert len(by_kind['MODEL_REQUEST']) == len(primary_requests)
assert all(row['payload'] == primary for row, primary in zip(by_kind['MODEL_REQUEST'], primary_requests))
assert len(by_kind.get('MODEL_RESPONSE', [])) == len(primary_responses)
assert all(row['payload']['body'] == primary['body'] and row['payload']['request_id'] == primary['request_id']
           for row, primary in zip(by_kind.get('MODEL_RESPONSE', []), primary_responses))
assert len(by_kind.get('RECEIPT', [])) == len(primary_actions)
assert all(row['payload'] == primary for row, primary in zip(by_kind.get('RECEIPT', []), primary_actions))
associations = [row['association'] for row in primary_actions]
assert len({(row['model_call_id'], row['model_tool_call_id']) for row in associations}) == len(associations)
request_ids = {row['request_id'] for row in primary_requests}
# Association IDs identify SDK calls; provider requests keep that ID in model_call_id.
association_matches = [any(req['member_id'] == action['actor'] and req.get('model_call_id') == action['association']['model_call_id']
                           for req in primary_requests) for action in primary_actions]
if primary_actions:
    assert all(association_matches), [(r.get('model_call_id'), r['request_id']) for r in primary_requests]
if mode == 'provider-exception':
    assert len(primary_requests) == 1 and not primary_responses and not primary_actions
    assert boundary['execution_integrity_failure'] is not None
    assert len(by_kind['MODEL_EXCEPTION']) == 1 and not public_calls
else:
    assert boundary['execution_integrity_failure'] is None, boundary
    assert len(prepared.world._software()['deliveries']) == 1
    assert len(public_calls) == 2
    assert owner.adapter.ledger.actual == len(primary_requests) * 281 == runtime.team_budget.snapshot()['charged_tokens']
    assert len(by_kind['INTENT']) == len(primary_actions) - fault_state['dropped_intents']
    assert any(row['usage_id'] == 'condenser' for row in primary_requests)
    managed.lock_fixed_candidates(prepared, folder / 'closure', sdk_closed=True)
summary = {'passed': True, 'mode': mode, 'sdk_version': importlib.metadata.version('openhands-sdk'),
           'private_SDK_sessions': len(runtime.policies), 'actual_HarnessPort': True,
           'scripted_physical_requests': len(primary_requests), 'scripted_responses': len(primary_responses),
           'scripted_condenser_requests': sum(row['usage_id'] == 'condenser' for row in primary_requests),
           'actual_CPU_public_test_calls': len(public_calls), 'primary_action_count': len(primary_actions),
           'request_payloads_exactly_match_durable_capture': True, 'response_and_usage_exactly_match_durable_capture': True,
           'action_and_association_exactly_match_primary': True, 'association_to_request_matched': all(association_matches),
           'schemas_equal_original_v141': True, 'private_peer_notes_leaked': False,
           'fault_injection': fault_state, 'observer_fault_count': owner.passive_sidecar.fault_count,
           'journal_integrity': proof, 'boundary_status': boundary['status'],
           'world_call_replay_count': 0, 'API_calls': 0, 'Docker_operations': 0,
           'source_sha256': hashlib.sha256((ROOT / 'src/proworksim/software_role_baseline_runtime_v203_2_1.py').read_bytes()).hexdigest()}
(folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, sort_keys=True))
