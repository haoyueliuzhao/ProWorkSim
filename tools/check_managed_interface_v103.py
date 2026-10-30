"""One scripted CPU SDK opportunity through the new actual managed factory."""
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
        raise PermissionError('Use an ordinary user and fresh /tmp output')
    output.mkdir(parents=True, exist_ok=False)
    forbidden = {'network': 0, 'weights': 0, 'gpu': 0}

    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            forbidden['network'] += 1
            raise AssertionError('No network in scripted SDK control')
        if event == 'open' and args and isinstance(args[0], (str, bytes)):
            path = os.fsdecode(args[0])
            if path.endswith(('.safetensors', '.gguf')) or 'pytorch_model' in path:
                forbidden['weights'] += 1
                raise AssertionError('No weights')
            if path.startswith(('/dev/nvidia', '/dev/dri/')):
                forbidden['gpu'] += 1
                raise AssertionError('No GPU')

    sys.addaudithook(audit)
    from proworksim import software_benchmark_managed_v103 as managed
    from proworksim import software_benchmark_world_v064 as world
    from proworksim.harness_port import HarnessPort
    from proworksim.model_policy import CONTROL_TOOLS
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_benchmark_budget_closure_v103 import RemainingBudgetDeepSeekAdapter
    from proworksim.software_calibration_collector_v051 import close_runtime
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest, json_bytes

    source = output / 'public'
    source.mkdir()
    (source / 'sample.py').write_text('value = 1\n')
    manifest = capture_repository(source, output / 'snapshot', task_id='fixture__103',
        problem_statement='Read the permitted repository.', source_identity={
            'instance_id': 'fixture__103', 'repo': 'fixture/test', 'base_commit': 'a' * 40,
            'dataset_revision': 'b' * 40})
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = managed.prepare_case(manifest, output / 'world', max_total_tokens=5_000_000,
        public_test_callback=lambda **_: (_ for _ in ()).throw(AssertionError('No public test here')),
        deadline=deadline)
    gateway = HarnessPort(world.SoftwareCollaborationPort(
        prepared.world.session('member_001', world.PROJECT), 'member_001'),
        'member_001', project_id=world.PROJECT, public_sink=lambda *_: None,
        world_sink=lambda *_: None, harness_sink=lambda *_: None)
    allowed = {row['name'] for row in [*gateway.tools(), *CONTROL_TOOLS]}
    requests = []

    def post(path, payload):
        wire = payload['wire']
        if path in {'/tokenize', '/tokenize-prefix'}:
            return {'prompt_tokens': 98304, 'request_sha256': digest(json_bytes(wire)),
                    'method': 'scripted CPU bound', 'count_only_not_dispatchable': path.endswith('prefix')}
        assert path == '/chat/completions'
        requests.append(copy.deepcopy(wire))
        return {'id': 'fixture-response', 'model': 'deepseek-flash', 'object': 'chat.completion',
            'created': 0, 'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'content': None, 'reasoning_content': 'Scripted CPU fixture.',
                'tool_calls': [{'id': 'fixture-call', 'type': 'function',
                    'function': {'name': 'list_files', 'arguments': '{"cursor":null}'}}]}}],
            'usage': {'prompt_tokens': 98304, 'completion_tokens': 30, 'total_tokens': 98334,
                'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 98304}}

    adapter = RemainingBudgetDeepSeekAdapter(post=post, arm='PROJECT', slot_id='fixture-103',
        condition_id='fixture', token_budget=5_000_000, folder=output / 'ledger', allowed_tool_names=allowed)
    owner = managed.ProjectOwner(adapter, window_id='fixture-103', identity={'policy_version': 'cpu-fixture'})
    runtime, _, _ = managed.build_runtime(owner, prepared, output / 'runtime', deadline=deadline,
        public_initial_message='Read the permitted repository; CPU scripted control only.')
    try:
        worker = runtime.policies['member_001']
        used = 4_883_127
        # Entirely synthetic pre-call usage in this new temporary fixture.
        adapter.ledger.actual = used
        worker.meter.update(budget_accounted_tokens=used, reported_total_tokens=used,
                            reported_prompt_tokens=used)
        budget = runtime.team_budget
        budget.consume_decision('member_001', 'fixture-history')
        budget.reserve('member_001', 'fixture-history', {'token_reservation': used})
        budget.begin_attempt('member_001', 'fixture-history')
        budget.settle('member_001', 'fixture-history', {'id': 'fixture-history', 'usage': {
            'prompt_tokens': used, 'completion_tokens': 0, 'total_tokens': used}})
        outcome = runtime.step()
        assert outcome.get('action_performed') is True, outcome
        assert outcome['response']['ok'] is True
        assert outcome['decision']['action'] == 'list_files'
        assert outcome['decision']['arguments'] == {'cursor': None}
        assert len(requests) == 1 and requests[0]['max_tokens'] == 18569
        assert adapter.ledger.actual == 4_981_461
        assert worker.meter['budget_accounted_tokens'] == budget.snapshot()['charged_tokens'] == adapter.ledger.actual
        result = {'passed': True, 'actual_worker': type(worker).__name__,
            'scripted_SDK_responses': 1, 'scripted_prompt_tokens': 98304,
            'scripted_output_tokens': 30, 'actual_output_cap': requests[0]['max_tokens'],
            'exact_cursor_null_dispatched_once': True, 'accounting_layers_equal': True,
            'model_calls': 0, 'public_test_calls': 0, 'Docker_operations': 0,
            'forbidden_operations': forbidden, 'deployment_or_benchmark': False}
        assert not any(forbidden.values())
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        close_runtime(runtime)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    control(parser.parse_args().output)
