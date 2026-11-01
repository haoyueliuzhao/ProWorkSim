"""Exercise two real SDK sessions with thirteen scripted CPU responses only."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys


def control(output):
    output = Path(output).resolve()
    if os.geteuid() == 0 or not output.is_relative_to(Path('/tmp')):
        raise PermissionError('Use an ordinary user and a fresh /tmp directory')
    output.mkdir(parents=True, exist_ok=False)
    os.environ['OH_PERSISTENCE_DIR'] = str(output / 'empty-user-config')
    forbidden = {'network': 0, 'weights': 0, 'gpu': 0}

    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            forbidden['network'] += 1
            raise AssertionError('Scripted SDK fixture cannot access the network')
        if event == 'open' and args and isinstance(args[0], (str, bytes)):
            path = os.fsdecode(args[0])
            if path.endswith(('.safetensors', '.gguf')) or 'pytorch_model' in path:
                forbidden['weights'] += 1
                raise AssertionError('No model weights in the CPU fixture')
            if path.startswith(('/dev/nvidia', '/dev/dri/')):
                forbidden['gpu'] += 1
                raise AssertionError('No GPU in the CPU fixture')

    sys.addaudithook(audit)
    from proworksim import software_fixed_organization_runtime_v104 as runtime_module
    from proworksim.repository_sources_v054 import capture_repository, tree_manifest
    from proworksim.software_benchmark_candidates_v054 import read_episode_candidates
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest, json_bytes

    members = ('member_001', 'member_002')
    scripts = {
        members[0]: [
            ('work_note', {'key': 'private', 'text': 'PRIVATE_AUTHOR_NOTE_V104'}),
            ('list_files', {'cursor': None}),
            ('write_file', {'path': 'sample.py', 'text': 'value = 1\n'}),
            ('run_tests', {}),
            ('fix_patch', {'task_ids': [], 'message': 'Scripted fixed candidate'}),
            ('submit_integration', {'message': 'Same-version scripted delivery'}),
            ('staff_done', {'reason': 'Scripted current work complete'}),
        ],
        members[1]: [
            ('work_note', {'key': 'private', 'text': 'PRIVATE_REVIEWER_NOTE_V104'}),
            ('read_file', {'path': 'sample.py'}),
            ('read_file', {'path': 'sample.py'}),
            ('staff_wait', {'reason': 'Wait for the actual author publication'}),
            ('org_review_patch', {'patch_id': 'patch-1', 'decision': 'accept',
                                  'reason': 'Scripted independent review of this exact version'}),
            ('staff_done', {'reason': 'Scripted review complete'}),
        ],
    }

    class ScriptedModel:
        limits = {'context_limit': 131072}
        maximum_input_tokens, maximum_output_tokens = 98304, 32768
        model, thinking = 'programmed-five-organization-cpu-v104', True
        fixture_only, external_resources_enabled = True, False

        def __init__(self):
            self.runtime = None
            self.requests, self.responses = [], []
            self.member_counts = dict.fromkeys(members, 0)

        def request(self, messages, tools):
            return {'model': self.model, 'messages': copy.deepcopy(messages),
                    'tools': copy.deepcopy(tools), 'max_tokens': 32768, 'stream': False}

        def count(self, wire):
            return {'prompt_tokens': 1000, 'context_limit': 131072,
                'method': 'programmed CPU bound, not measured token usage',
                'request_sha256': digest(json_bytes(wire)), 'exact_provider_token_ids_available': False}

        def complete(self, wire, usage_id):
            assert usage_id == 'agent'
            member = self.runtime._active['label']
            ordinal = self.member_counts[member]
            assert ordinal < len(scripts[member]), (member, ordinal)
            name, arguments = scripts[member][ordinal]
            self.member_counts[member] += 1
            index = len(self.responses)
            self.requests.append({'member': member, 'wire': copy.deepcopy(wire)})
            body = {'id': f'programmed-v104-{index}', 'created': 0, 'model': self.model,
                'object': 'chat.completion', 'choices': [{'index': 0, 'finish_reason': 'tool_calls',
                'message': {'role': 'assistant', 'content': '',
                    'reasoning': f'Programmed private reasoning for {member}',
                    'tool_calls': [{'id': f'programmed-call-{index}', 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(arguments)}}]}}],
                'usage': {'prompt_tokens': 1000, 'completion_tokens': 17, 'total_tokens': 1017}}
            self.responses.append(copy.deepcopy(body))
            return body

    source = output / 'public'
    source.mkdir()
    (source / 'sample.py').write_text('value = 0\n')
    manifest = capture_repository(source, output / 'snapshot', task_id='fixture__org104',
        problem_statement='Synthetic public source: set value to one.', source_identity={
            'instance_id': 'fixture__org104', 'repo': 'fixture/sdk',
            'base_commit': 'a' * 40, 'dataset_revision': 'b' * 40})
    public_calls = []

    def public_test(**payload):
        public_calls.append(copy.deepcopy(payload))
        return {'passed': False, 'execution': {'executed': True,
            'input_tree_sha256': tree_manifest(payload['files'], payload['entry_metadata'])['tree_sha256']},
            'groups': {'fixture': {'status': 'failed', 'executed': True, 'passed': False, 'tests': []}}}

    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = runtime_module.prepare_case(manifest, output / 'world', organization_id='REVIEW',
        max_total_tokens=5_000_000, public_test_callback=public_test, deadline=deadline, max_decisions=13)
    adapter = ScriptedModel()
    owner = runtime_module.ProjectOwner(adapter, window_id='fixture-org104',
        identity={'policy_version': 'scripted-cpu-control'})
    runtime, _, _ = runtime_module.build_runtime(owner, prepared, output / 'runtime', deadline=deadline,
        public_initial_message=prepared.case['root_goal'], offline_fixture=True)
    try:
        adapter.runtime = runtime
        boundary = runtime_module.run_fragment(prepared, runtime)
        budget = runtime.team_budget.snapshot()
        assert boundary['execution_integrity_failure'] is None, boundary
        assert len(adapter.responses) == budget['decisions'] == budget['attempts'] == 13
        assert budget['charged_tokens'] == 13 * 1017
        assert adapter.member_counts == {'member_001': 7, 'member_002': 6}
        assert len(public_calls) == 1 and public_calls[0]['files']['sample.py'] == 'value = 1\n'
        assert all('PRIVATE_AUTHOR_NOTE_V104' not in json.dumps(r['wire'])
                   for r in adapter.requests if r['member'] != members[0])
        assert all('PRIVATE_REVIEWER_NOTE_V104' not in json.dumps(r['wire'])
                   for r in adapter.requests if r['member'] != members[1])
        assert all((r.get('response') or {}).get('ok', True) is True for r in boundary['outcomes'])
        assert any(r.get('decision', {}).get('action') == 'org_review_patch' for r in boundary['outcomes'])
        cursor = [r for r in boundary['outcomes'] if r.get('decision', {}).get('action') == 'list_files']
        assert len(cursor) == 1 and cursor[0]['decision']['arguments'] == {'cursor': None}
        assert not any(forbidden.values())
    finally:
        runtime_module.close_runtime(runtime)
    lock = runtime_module.lock_fixed_candidates(prepared, output / 'candidates', sdk_closed=True)
    candidates = read_episode_candidates(lock)
    assert candidates['terminal_code']['files']['sample.py'] == 'value = 1\n'
    assert candidates['last_legal_delivery']['files']['sample.py'] == 'value = 1\n'
    result = {'version': 'v104-scripted-real-sdk-review-control-r1', 'passed': True,
        'actual_openhands_private_conversations': 2, 'scripted_responses': 13,
        'scripted_tokens_not_model_usage': budget['charged_tokens'],
        'private_histories_verified': True, 'cursor_null_preserved': True,
        'organization_review_dispatched_through_real_SDK': True,
        'same_version_review_test_fix_submission_and_unique_candidate': True,
        'world_opportunities_recorded': boundary['opportunities'], 'model_calls': 0,
        'API_calls': 0, 'GPU_operations': 0, 'Docker_operations': 0, 'official_scoring_calls': 0,
        'public_fixture_callbacks': 1, 'forbidden_operations': forbidden}
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    control(parser.parse_args().output)
