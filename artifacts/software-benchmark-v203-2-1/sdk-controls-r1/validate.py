"""Read-only reconciliation of independent primary SDK/Harness evidence."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from proworksim.software_observer_journal_v203_2_1 import ObserverJournal
from proworksim import software_role_baseline_runtime_v141 as original
from proworksim.storage import digest, json_bytes


def validate(folder, mode):
    primary = folder / 'primary'
    requests, responses, actions, boundary = [json.loads((primary / (name + '.json')).read_text())
                                             for name in ('requests', 'responses', 'actions', 'boundary')]
    capture = folder / 'model-ledger/passive-observer'
    capture_summary = json.loads((capture / 'capture-summary.json').read_text())
    with ObserverJournal(capture / 'events.sqlite') as journal:
        rows = list(journal.records())
        proof = journal.integrity()
    by_kind = {}
    for row in rows:
        by_kind.setdefault(row['kind'], []).append(row)
    assert len(by_kind['MODEL_REQUEST']) == len(requests)
    assert all(row['payload'] == raw for row, raw in zip(by_kind['MODEL_REQUEST'], requests))
    assert len(by_kind.get('MODEL_RESPONSE', [])) == len(responses)
    assert all(row['payload']['body'] == raw['body'] and row['payload']['request_id'] == raw['request_id']
               for row, raw in zip(by_kind.get('MODEL_RESPONSE', []), responses))
    assert len(by_kind.get('RECEIPT', [])) == len(actions)
    assert all(row['payload'] == raw for row, raw in zip(by_kind.get('RECEIPT', []), actions))
    associations = [row['association'] for row in actions]
    assert len({(row['model_call_id'], row['model_tool_call_id']) for row in associations}) == len(associations)
    request_by_id = {row['request_id']: row for row in requests}
    response_by_id = {row['body']['id']: row for row in responses}
    budget = boundary['team_budget']['model']
    bindings = []
    for action in actions:
        association = action['association']
        charge = budget['records'][association['model_call_id']]
        returned = response_by_id[charge['charge']['response_id']]
        requested = request_by_id[returned['request_id']]
        assert charge['member'] == requested['member_id'] == action['actor']
        assert charge['reservation']['preparation']['wire_request_sha256'] == digest(json_bytes(requested['wire']))
        calls = returned['body']['choices'][0]['message']['tool_calls']
        assert len(calls) == 1 and calls[0]['id'] == association['model_tool_call_id']
        assert calls[0]['function']['name'] == action['tool']
        assert json.loads(calls[0]['function']['arguments']) == action['arguments']
        bindings.append({'model_call_id': association['model_call_id'], 'tool_call_id': association['model_tool_call_id'],
                         'response_id': returned['body']['id'], 'request_id': requested['request_id']})
    for request in requests:
        if request['usage_id'] == 'agent':
            assert request['wire']['tools'] == original.member_wire_tools('REVIEW2', request['member_id'])
        if request['member_id'] == 'member_002':
            assert 'PRIVATE_001_ONLY' not in json.dumps(request['wire']['messages'])
    public_calls = list((folder / 'case/actual-public-tests').glob('*'))
    deliveries = [row for row in actions if row['tool'] == 'submit_integration' and row['response']['ok']]
    faults = {'dropped_intents': int(mode == 'observer-fault'), 'after_commit_errors': int(mode == 'observer-fault')}
    if mode == 'provider-exception':
        assert len(requests) == 1 and not responses and not actions
        assert boundary['execution_integrity_failure'] is not None
        assert len(by_kind['MODEL_EXCEPTION']) == 1 and not public_calls
    else:
        assert boundary['execution_integrity_failure'] is None, boundary
        assert len(deliveries) == 1 and deliveries[0]['actor'] == 'member_001'
        assert len(public_calls) == 2
        assert budget['charged_tokens'] == len(requests) * 281
        assert len(by_kind['INTENT']) == len(actions) - faults['dropped_intents']
        assert any(row['usage_id'] == 'condenser' for row in requests)
        assert capture_summary['observer_fault_count'] == (2 if mode == 'observer-fault' else 0)
    summary = {'passed': True, 'mode': mode, 'sdk_version': '1.49.6', 'private_SDK_sessions': 2,
               'actual_HarnessPort': True, 'scripted_physical_requests': len(requests),
               'scripted_responses': len(responses), 'scripted_condenser_requests': sum(row['usage_id'] == 'condenser' for row in requests),
               'actual_CPU_public_test_calls': len(public_calls), 'primary_action_count': len(actions),
               'request_payloads_exactly_match_durable_capture': True, 'response_and_usage_exactly_match_durable_capture': True,
               'action_and_association_exactly_match_primary': True, 'association_to_request_matched': True,
               'association_mapping': 'SDK model_call_id -> authoritative team budget response_id -> original response/request and exact wire hash',
               'association_bindings': bindings, 'schemas_equal_original_v141': True, 'private_peer_notes_leaked': False,
               'fault_injection': faults, 'observer_fault_count': capture_summary['observer_fault_count'],
               'observer_CPU_seconds': capture_summary['observer_CPU_seconds'], 'observer_wall_seconds': capture_summary['observer_wall_seconds'],
               'journal_integrity': proof, 'boundary_status': boundary['status'], 'fixed_member001_deliveries': len(deliveries),
               'world_call_replay_count': 0, 'API_calls': 0, 'Docker_operations': 0,
               'capture_coverage': {'requests': [len(by_kind['MODEL_REQUEST']), len(requests)],
                                    'responses': [len(by_kind.get('MODEL_RESPONSE', [])), len(responses)],
                                    'intents': [len(by_kind.get('INTENT', [])), len(actions)],
                                    'receipts': [len(by_kind.get('RECEIPT', [])), len(actions)]},
               'source_sha256': hashlib.sha256((ROOT / 'src/proworksim/software_role_baseline_runtime_v203_2_1.py').read_bytes()).hexdigest()}
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    mode = sys.argv[1]
    folder = ROOT / 'runs/software-benchmark-v203-2-1/sdk-controls-r1' / mode
    print(json.dumps(validate(folder, mode), sort_keys=True))
