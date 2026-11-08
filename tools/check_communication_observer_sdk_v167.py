"""Actual pinned SDK + physical fake transport + shared SQLite, zero real API."""
from __future__ import annotations
import argparse
import copy
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
    HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
ROOT = Path(__file__).resolve().parents[1]


def setup(folder):
    from proworksim import software_benchmark_deepseek_api_v157 as api
    from proworksim.software_benchmark_candidates_v054 import reference
    folder.mkdir(parents=True)
    rows = [{'slot_id': 'v157:cpu-sdk:'+g, 'instance_id': 'fixture__sdk-141',
        'condition': g, 'condition_id': g, 'group_id': g, 'organization_id': 'REVIEW2',
        'fixed_members': ['member_001', 'member_002'], 'budget_tokens': 5_000_000} for g in api.GROUP_IDS]
    rows.append({**rows[-1], 'slot_id': rows[-1]['slot_id']+':unknown-compressor', 'control_mode': 'compressor_network_unknown'})
    panel, ledger, authority = folder/'panel.json', folder/'cpu-ledger.sqlite', folder/'authority.json'
    panel.write_text(json.dumps({'rows': rows, 'real_model_calls': 0}))
    authority.write_text(json.dumps({'version': api.AUTHORITY_VERSION, 'ledger_path': str(ledger.resolve()),
        'cap_nanoyuan': api.CAP_NANOYUAN, 'panel_sha256': reference(panel)['sha256'], 'approved': True}))
    views = {g: api.group_api(g, ledger, max_concurrency=2, panel_ref=reference(panel),
        cash_authority_ref=reference(authority)) for g in api.GROUP_IDS}
    return views, rows


def run(folder, row, host_runtime):
    from proworksim import software_role_baseline_runtime_v167 as managed
    from proworksim.software_benchmark_host_api_v157 import HostTeamTransport
    from proworksim.software_benchmark_deepseek_contract_v105 import slot_user_id
    from proworksim.software_communication_pilot_v156 import FIELDS
    spec = importlib.util.spec_from_file_location('old_cpu_fixture', ROOT/'tools/check_role_baseline_sdk_v141.py')
    fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    prepared, deadline, public_calls = fixture.fixture(folder/'case', 'REVIEW2')
    condition, slot = row['condition'], row['slot_id']
    unknown_control = row.get('control_mode') == 'compressor_network_unknown'
    response_prefix = condition+('-unknown' if unknown_control else '')
    private_marker = 'UNPUBLISHED_PRIVATE_NOTE_MUST_NEVER_REACH_COMPRESSOR'
    peer_text = ('Changed internal handling because ' + 'a simpler implementation avoids duplicated branches '*14 +
        '.\nTests: public validation is still unknown.\nNext action: review patch-1 after publication.')
    actions = {'member_001': [
        ('work_note', {'key': 'private', 'text': private_marker}),
        ('send_message', {'recipient': 'member_002', 'task_id': 'root_goal', 'body': peer_text}),
        ('read_file', {'path': 'sample.py', 'cursor': None}),
        ('write_file', {'path': 'sample.py', 'text': 'value = 2\n'}), ('run_tests', {}),
        ('fix_patch', {'task_ids': [], 'message': 'Fixed actual public-tested version'}),
        ('handoff_patch', {'patch_id': 'patch-1', 'to_member': 'member_002', 'message': 'Next action: review patch-1.'}),
        ('WAIT_REVIEW', {}), ('submit_integration', {'message': 'Same-version CPU closure'}),
        ('staff_done', {'reason': 'Work done'}), ('staff_done', {'reason': 'Self check done'})],
        'member_002': [('WAIT_MESSAGE', {}), ('READ_L2', {}), ('READ_L3', {}), ('WAIT_PATCH', {}),
        ('integrate_patch', {'patch_id': 'patch-1'}), ('run_tests', {}),
        ('write_file', {'path': 'sample.py', 'text': 'value = 999\n'}),
        ('org_review_patch', {'patch_id': 'patch-1', 'decision': 'request_changes', 'reason': 'Review after edit; old test is not current.'}),
        ('write_file', {'path': 'sample.py', 'text': 'value = 2\n'}), ('run_tests', {}),
        ('org_review_patch', {'patch_id': 'patch-1', 'decision': 'accept', 'reason': 'Actual same-version test passed.'}),
        ('staff_done', {'reason': 'Review done'}), ('staff_done', {'reason': 'Self check done'})]}
    positions = {m: 0 for m in row['fixed_members']}
    holder, requests, compression_requests, condenser_requests = {}, [], [], []
    rejected_once = set()

    class Script:
        def abort(self): pass
        def request(self, method, path, wire):
            assert (method, path) == ('POST', '/chat/completions')
            requests.append(copy.deepcopy(wire))
            assert len(requests) < 70
            member = next(m for m in row['fixed_members'] if wire['user_id'] == slot_user_id(slot+':'+m, condition))
            if wire['temperature'] == .2:
                assert private_marker not in json.dumps(wire)
                compression_requests.append(copy.deepcopy(wire))
                if unknown_control and len(compression_requests) == 1:
                    from proworksim.software_benchmark_deepseek_api_v157 import TransportFailure
                    raise TransportFailure('incomplete_response_body', phase='body', status=200)
                data = json.loads(wire['messages'][1]['content'])
                selected = {field: [f['fact_id'] for f in data['facts'] if f['field'] == field and
                    (condition == 'C1' or f['critical'])] for field in FIELDS}
                message, finish = {'role': 'assistant', 'content': json.dumps({
                    'source_id': data['source_id'], 'version_hash': data['version_hash'], 'fields': selected})}, 'stop'
            elif not wire.get('tools'):
                condenser_requests.append(copy.deepcopy(wire))
                holder['runtime'].policies[member].agent.condenser.max_size = 80
                message, finish = {'role': 'assistant', 'content': 'Private summary of the observed events only.'}, 'stop'
            elif member not in rejected_once:
                rejected_once.add(member)
                message, finish = {'role': 'assistant', 'content': 'I will inspect the task next.'}, 'stop'
            else:
                plan, at = actions[member], positions[member]
                name, args = plan[at] if at < len(plan) else ('staff_done', {'reason': 'No more work'})
                while name.startswith('WAIT_'):
                    bridge = holder['runtime'].owner.communication_v157
                    available = (bool(bridge.records) if name == 'WAIT_MESSAGE' else
                        'patch-1' in prepared.world._software()['patches'] if name == 'WAIT_PATCH' else
                        any(r['decision'] == 'accept' for r in prepared.world.org_state()['reviews']))
                    if not available:
                        name, args, at = 'staff_wait', {'reason': 'Wait for actual peer evidence'}, -1
                        break
                    positions[member] += 1
                    name, args = plan[positions[member]]
                if name.startswith('READ_L'):
                    records = holder['runtime'].owner.communication_v157.records
                    record = next(r for r in records.values() if r['kind'] == 'work_message')
                    name, args = 'read_work_event', {'sequence': record['sequence'], 'level': name[-2:],
                        'version_hash': record['ref']['version_hash'], 'start_character': 0, 'max_characters': 8192}
                if at >= 0:
                    positions[member] += 1
                message, finish = {'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': condition+'-tool-'+str(len(requests)), 'type': 'function',
                    'function': {'name': name, 'arguments': json.dumps(args)}}]}, 'tool_calls'
            return {'id': response_prefix+'-response-'+str(len(requests)), 'model': 'deepseek-flash',
                'system_fingerprint': 'cpu-script-not-provider', 'object': 'chat.completion', 'created': 0,
                'choices': [{'index': 0, 'finish_reason': finish, 'message': message}],
                'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                          'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
    names = {t['function']['name'] for t in host_runtime.schemas[condition]['member_001']}
    client = host_runtime.apis[condition].DeepSeekClient(api_key='cpu-not-used', allowed_tool_names=names,
        transport=Script(), http_slots=host_runtime.http_slots, sleep=lambda _: None, jitter=lambda: 0)
    host_runtime.clients[condition].fork_for_episode = lambda: client
    route = HostTeamTransport(host_runtime, row, folder/'host')
    owner = managed.build_team_owner(route.post, organization_id='REVIEW2', slot_id=slot, condition_id=condition,
        folder=folder/'model-ledger', deadline=deadline, identity={'policy_version': 'cpu-v157-scripted'},
        communication_condition=condition, observation_token_counter=lambda s: len(s.split()),
        observation_tokenizer_id='CPU_word_estimate_not_provider_exact', require_content_counter=True)
    runtime, _, _ = managed.build_runtime(owner, prepared, folder/'runtime', deadline=deadline,
        public_initial_message='CPU-only complete communication integration control; no benchmark/model.')
    holder['runtime'] = runtime
    runtime.policies['member_001'].agent.condenser.max_size = 12
    if condition == 'C0':
        def metric_fault():
            raise ValueError('CPU synthetic auxiliary metric failure')
        owner.observation.safely('actions', metric_fault)
    try:
        boundary = managed.run_fragment(prepared, runtime)
    finally:
        managed.close_runtime(runtime)
    assert boundary['execution_integrity_failure'] is None, boundary
    assert len(prepared.world._software()['deliveries']) == 1
    assert len(public_calls) == 3
    authority = owner.shared_provider_budget()
    assert owner.adapter.ledger.actual == (len(requests)-int(unknown_control))*281
    assert runtime.team_budget.snapshot()['charged_tokens'] == authority['known_actual_tokens']+authority['uncertain_reserved_tokens']
    assert prepared.world.model_budget_snapshot()['available_tokens'] == authority['available_tokens']
    if unknown_control:
        assert authority['uncertain_reserved_tokens'] == 768 and authority['actual_usage_complete'] is False
        assert owner.adapter.ledger.snapshot()['complete_actual_tokens'] is None
        assert owner.compressor_failures and all(p.used == 1 for p in runtime.finish_review_policies.values())
    assert (not compression_requests) if condition == 'C0' else bool(compression_requests)
    assert condenser_requests
    assert rejected_once == set(row['fixed_members'])
    assert all(worker.transport.feedback_ledger.records for worker in runtime.policies.values())
    assert len(client.provenance_capture.receipts()) == len(requests)
    assert not client.provenance_capture.errors()
    assert len(owner.observation.errors) == int(condition == 'C0'), owner.observation.errors
    assert bool(boundary.get('measurement_partial')) == (condition == 'C0')
    assert len(prepared.world.org_state()['reviews']) == 2
    assert owner.observation.log.summary()['review']['accept_decisions'] == 1
    assert not owner.source_capture_v157.pending
    assert owner.observation.source_presentation_coverage_proof()['complete']
    bridge = owner.communication_v157
    pulls = [e for e in bridge.events if e['kind'] == 'retrieved']
    assert {e['level'] for e in pulls} == {'L2', 'L3'}
    if condition != 'C0':
        assert any(r['representation'] != 'raw' for r in bridge.rendered.values())
    managed.lock_fixed_candidates(prepared, folder/'closure', sdk_closed=True)
    summary = {'passed': True, 'condition': condition, 'unknown_compressor_control': unknown_control, 'API_calls': 0, 'Docker_operations': 0,
        'scripted_physical_requests': len(requests), 'real_runner_format_rejections': len(rejected_once), 'review_after_edit_restore_uses_actual_same_version_test': True, 'request_changes_with_stale_old_test_works': True, 'auxiliary_metric_fault_does_not_interrupt': condition == 'C0', 'feedback_origin_bound_before_condensation': True, 'scripted_compressor_requests': len(compression_requests),
        'scripted_condenser_requests': len(condenser_requests), 'actual_CPU_public_test_calls': len(public_calls),
        'team_authority': owner.shared_provider_budget(), 'physical_capture_count': len(client.provenance_capture.receipts()),
        'presentation_coverage': owner.observation.source_presentation_coverage_proof(),
        'source_capture_completed': len(owner.source_capture_v157.completed), 'pulls': pulls,
        'representations': [r['representation'] for r in bridge.rendered.values()],
        'same_shared_pool_all_purposes': True, 'preview_C0_characters': 500,
        'budget_synthetic_usage_not_actual_spend': True, 'private_sender_note_exposed_to_compressor': False}
    (folder/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    folder = args.output.resolve(); folder.mkdir(parents=True, exist_ok=False)
    os.environ['OH_PERSISTENCE_DIR'] = str(folder/'sdk-settings')
    def audit(event, values):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            raise AssertionError('No networking in scripted SDK control')
        if event == 'subprocess.Popen':
            argv, cwd = values[1], str(values[2])
            public = isinstance(argv, (list, tuple)) and list(argv) == [str(ROOT/'.venv/bin/python'),
                '-m', 'pytest', '-q', 'test_sample.py'] and str(folder) in cwd and '/actual-public-tests/' in cwd
            codec = isinstance(argv, (list, tuple)) and Path(argv[0]).name == 'git' and 'proworksim-v054-candidate-' in cwd
            if not (public or codec): raise AssertionError('Only actual CPU pytest and candidate codec subprocesses')
    sys.addaudithook(audit)
    sources = [ROOT/'src/proworksim'/name for name in ('software_role_baseline_runtime_v167.py','software_sdk_input_sources_v159.py','software_condenser_input_sources_v159.py','software_collaboration_runtime_observer_v167.py','software_collaboration_observation_v167.py')]+[Path(__file__).resolve()]
    initial_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (folder/'loaded-source-hashes.json').write_text(json.dumps(initial_hashes, sort_keys=True, indent=2)+'\n')
    from proworksim import software_benchmark_host_api_v157 as host
    from proworksim.software_role_baseline_runtime_v167 import prepare_schema_inventory
    from proworksim.storage import digest, json_bytes
    views, rows = setup(folder/'authority')
    runtime = host.runtime_for(apis=views, schemas=prepare_schema_inventory()['schemas'],
        counter=lambda w: {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(w)), 'method': 'scripted_CPU_reservation_not_provider_exact'},
        authorize=lambda *args, **kwargs: None, api_key='cpu-not-used', max_concurrency=2)
    results = [run(folder/(row['condition']+('-unknown' if row.get('control_mode') else '')), row, runtime) for row in rows if row['condition'] in {'C0','C2'} and not row.get('control_mode')]
    final_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    assert final_hashes == initial_hashes, 'Sources changed during the controlled SDK run'
    output = folder/'summary.json'
    output.write_text(json.dumps({'passed': True, 'controls': results, 'real_API_calls': 0, 'source_hashes': initial_hashes, 'sources_unchanged_during_run': True}, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'passed': True, 'summary': str(output)}))


if __name__ == '__main__':
    main()
