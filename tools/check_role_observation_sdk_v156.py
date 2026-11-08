"""Actual pinned SDK + scripted provider P0 control; no network/model/container."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
ROOT = Path(__file__).resolve().parents[1]


def run(folder, *, fail=False):
    from proworksim import software_role_baseline_runtime_v156 as runtime_module
    from proworksim.software_benchmark_alignment_contract_v141 import condition
    from proworksim.software_sdk_input_sources_v156 import SDKRequestCapture
    from proworksim.storage import digest, json_bytes
    spec = importlib.util.spec_from_file_location('v141_cpu_fixture', ROOT/'tools/check_role_baseline_sdk_v141.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    group = 'S1' if fail else 'REVIEW2'
    prepared, deadline, public_calls = fixture.fixture(folder/'case', group)
    cfg = condition(group)
    slot = f'cpu-v156:fixture__sdk-141:{group}:156'
    positions = {m: 0 for m in cfg['fixed_members']}
    actions = {'member_001': [('send_message', {'recipient': 'member_002', 'task_id': 'root_goal',
        'body': 'CPU peer message: inspect the fixed sample.py version and record the actual test result.'}),
        ('read_file', {'path': 'sample.py', 'cursor': None}),
        ('write_file', {'path': 'sample.py', 'text': 'value = 3\n'}), ('run_tests', {}),
        ('fix_patch', {'task_ids': [], 'message': 'Fixed candidate with observed failing public test'}),
        ('handoff_patch', {'patch_id': 'patch-1', 'to_member': 'member_002', 'message': 'Review actual version'}),
        ('WAIT_REVIEW', {}), ('submit_integration', {'message': 'Same-version protocol control'}),
        ('staff_done', {'reason': 'Work done'}), ('staff_done', {'reason': 'Self check done'})],
        'member_002': [('READ_MESSAGE', {}), ('WAIT_PATCH', {}), ('integrate_patch', {'patch_id': 'patch-1'}),
        ('run_tests', {}), ('org_review_patch', {'patch_id': 'patch-1', 'decision': 'accept',
            'reason': 'CPU contract control: actual public test failed; acceptance is a separate recorded decision.'}),
        ('staff_done', {'reason': 'Review done'}), ('staff_done', {'reason': 'Self check done'})]}
    requests, origins, responses, holder, summaries = [], [], [], {}, []
    source_capture = SDKRequestCapture(folder/'actual-request-capture')

    def capture(member, payload, worker, owner):
        source_capture.request(member, payload, worker, owner)
        if payload['usage_id'] == 'agent':
            assert worker is owner._v156_workers[member]
            assert worker._v156_input_origin_error is None, worker._v156_input_origin_error
            mapping = worker._v156_input_origins
            assert len(mapping) == len(payload['wire']['messages'])
            assert all(row['event_ids'] and row['content_search_used'] is False for row in mapping)
            origins.append({'request_id': payload['request_id'], 'member': member,
                'mapped_messages': len(mapping), 'event_ids': [r['event_ids'] for r in mapping],
                'event_types': [r['event_types'] for r in mapping]})
        else:
            pending = worker._history_trace_v110.pending
            assert pending and pending['event_ids']
            summaries.append({'request_id': payload['request_id'], 'source_event_ids': pending['event_ids']})

    def returned(member, payload, response, worker, owner):
        source_capture.response(member, payload, response, worker, owner)
        responses.append({'request_id': payload['request_id'], 'response_id': response.get('id') if response else None})

    def post(route, payload):
        wire, member = payload['wire'], payload['member_id']
        if route in {'/tokenize', '/tokenize-prefix'}:
            return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(wire)),
                    'method': 'scripted CPU count', 'count_only_not_dispatchable': route.endswith('prefix')}
        requests.append(payload)
        assert len(requests) < 60
        if fail:
            raise RuntimeError('synthetic provider interruption; no actual API')
        if payload['usage_id'] == 'condenser':
            holder['runtime'].policies[member].agent.condenser.max_size = 80
            message, finish = {'role': 'assistant', 'content': 'Private CPU summary of actual prior source events only.'}, 'stop'
        else:
            plan = actions[member]
            at = positions[member]
            name, args = plan[at] if at < len(plan) else ('staff_done', {'reason': 'No more work'})
            if name == 'READ_MESSAGE':
                sent = holder['runtime'].owner.observation.messages
                assert len(sent) == 1
                name, args = 'read_work_event', {'sequence': next(iter(sent))}
            if name.startswith('WAIT_'):
                available = ('patch-1' in prepared.world._software()['patches'] if name == 'WAIT_PATCH'
                             else any(r['decision'] == 'accept' for r in prepared.world.org_state()['reviews']))
                if not available:
                    name, args, at = 'staff_wait', {'reason': 'Wait for actual peer evidence'}, -1
                else:
                    positions[member] += 1
                    name, args = plan[positions[member]]
            if at >= 0:
                positions[member] += 1
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'cpu-call-'+str(len(requests)),
                'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}
            finish = 'tool_calls'
        return {'id': 'cpu-response-'+str(len(requests)), 'model': 'deepseek-flash', 'object': 'chat.completion',
            'system_fingerprint': 'scripted-not-provider', 'created': 0,
            'choices': [{'index': 0, 'finish_reason': finish, 'message': message}],
            'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                      'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}

    owner = runtime_module.build_team_owner(post, organization_id=group, slot_id=slot,
        condition_id=cfg['condition_id'], folder=folder/'model-ledger', deadline=deadline,
        identity={'policy_version': 'scripted-CPU-only'}, request_capture=capture, response_callback=returned)
    runtime, _, _ = runtime_module.build_runtime(owner, prepared, folder/'runtime', deadline=deadline,
        public_initial_message='CPU observer protocol control only, no real benchmark or model.')
    holder['runtime'] = runtime
    if not fail:
        runtime.policies['member_001'].agent.condenser.max_size = 12
    try:
        boundary = runtime_module.run_fragment(prepared, runtime)
    finally:
        runtime_module.close_runtime(runtime)
    if fail:
        assert boundary['execution_integrity_failure'] is not None
        summary = json.loads((owner.observation.folder/'summary.json').read_text())
        assert summary['completion_status'] == 'partial' and not any(summary['coverage'].values())
        assert summary['usage']['actual_total_tokens'] is None
    else:
        assert boundary['execution_integrity_failure'] is None, boundary
        assert len(prepared.world._software()['deliveries']) == 1
        assert len(public_calls) == 2
        assert owner.adapter.ledger.actual == len(requests)*281 == runtime.team_budget.snapshot()['charged_tokens']
        runtime_module.lock_fixed_candidates(prepared, folder/'closure', sdk_closed=True)
        summary = json.loads((owner.observation.folder/'summary.json').read_text())
        assert not owner.observation.errors, owner.observation.errors
        assert summary['review']['accept_decisions'] == 1
        assert summary['public_tests']['executed'] == 2 and summary['public_tests']['passed'] == 0
        assert summary['public_tests']['reports_presented'] > 0
        assert summary['lifecycle']['delivered'] == 1
        assert summaries, 'Actual SDK condenser control must run once'
        assert len(origins)+len(summaries) == len(requests) == len(responses)
    value = {'passed': True, 'exception_control': fail, 'real_model_calls': 0, 'API_calls': 0,
        'Docker_operations': 0, 'scripted_requests': len(requests), 'scripted_summaries': len(summaries),
        'actual_CPU_public_test_calls': len(public_calls), 'input_origins': origins,
        'summary_sources': summaries, 'responses': responses, 'observation': summary,
        'source_capture_directory': str(source_capture.directory),
        'source_capture_completed': len(source_capture.completed),
        'source_capture_pending': len(source_capture.pending),
        'source_capture_diagnostics': [{'request_id': row['response']['request_id'],
            **{k: v for k, v in row.items() if k in {'source_mapping', 'reason',
                'unattributed_message_indices', 'verified_event_message_pairs', 'condenser_template'}}}
            for row in source_capture.completed]}
    (folder/'summary.json').write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    os.environ['OH_PERSISTENCE_DIR'] = str(folder/'sdk-settings')

    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            raise AssertionError('No network in CPU observer control')
        if event == 'subprocess.Popen':
            argv, cwd = args[1], str(args[2])
            public = (isinstance(argv, (tuple, list)) and list(argv) ==
                [str(ROOT/'.venv/bin/python'), '-m', 'pytest', '-q', 'test_sample.py']
                and str(folder) in cwd and '/actual-public-tests/' in cwd)
            codec = isinstance(argv, (tuple, list)) and Path(argv[0]).name == 'git' and 'proworksim-v054-candidate-' in cwd
            if not (public or codec):
                raise AssertionError('Only CPU public tests and candidate codec subprocesses are allowed')
    sys.addaudithook(audit)
    results = [run(folder/'normal'), run(folder/'exception', fail=True)]
    path = folder/'summary.json'
    path.write_text(json.dumps({'passed': True, 'controls': results}, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'passed': True, 'path': str(path)}))


if __name__ == '__main__':
    main()
