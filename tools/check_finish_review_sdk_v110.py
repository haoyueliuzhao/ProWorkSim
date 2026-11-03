"""Two scripted responses through the actual managed SDK; no network or Docker."""
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
        raise PermissionError('Use an ordinary user and a new /tmp directory')
    output.mkdir(parents=True, exist_ok=False)
    os.environ['OH_PERSISTENCE_DIR'] = str(output/'sdk-settings')
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
    os.environ['OPENHANDS_SUPPRESS_BANNER'] = '1'
    prohibited = {'network': 0, 'weights': 0, 'gpu': 0}

    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            prohibited['network'] += 1
            raise AssertionError('This CPU SDK control cannot use the network')
        if event == 'open' and args and isinstance(args[0], (str, bytes)):
            path = os.fsdecode(args[0])
            if path.endswith(('.safetensors', '.gguf')) or 'pytorch_model' in path:
                prohibited['weights'] += 1
                raise AssertionError('No model weights are permitted')
            if path.startswith(('/dev/nvidia', '/dev/dri/')):
                prohibited['gpu'] += 1
                raise AssertionError('No GPU is permitted')

    sys.addaudithook(audit)
    from proworksim import software_benchmark_managed_v105 as managed
    from proworksim import software_benchmark_world_v064 as world
    from proworksim.harness_port import HarnessPort
    from proworksim.model_policy import CONTROL_TOOLS
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_benchmark_deepseek_adapter_v105 import DeepSeekEpisodeAdapter
    from proworksim.software_benchmark_deepseek_contract_v105 import condition, validate_condition
    from proworksim.software_benchmark_finish_review_v110 import FINISH_REVIEW, DONE_DESCRIPTION
    from proworksim.software_benchmark_review_runtime_v110 import FinishReviewWorkerMixin, decorate_runtime
    from proworksim.software_calibration_collector_v051 import close_runtime, run_fragment
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest, json_bytes

    source = output/'public'
    source.mkdir()
    (source/'sample.py').write_text('value = 1\n')
    manifest = capture_repository(source, output/'snapshot', task_id='fixture__110',
        problem_statement='Scripted finish-review lifecycle control.',
        source_identity={'instance_id': 'fixture__110', 'repo': 'fixture/test',
                         'base_commit': 'a'*40, 'dataset_revision': 'b'*40})
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = managed.prepare_case(manifest, output/'world', max_total_tokens=5_000_000,
        public_test_callback=lambda **_: (_ for _ in ()).throw(AssertionError('No test process permitted')),
        deadline=deadline)
    gateway = HarnessPort(world.SoftwareCollaborationPort(
        prepared.world.session('member_001', world.PROJECT), 'member_001'),
        'member_001', project_id=world.PROJECT, public_sink=lambda *_: None,
        world_sink=lambda *_: None, harness_sink=lambda *_: None)
    allowed = {row['name'] for row in [*gateway.tools(), *CONTROL_TOOLS]}
    requests = []

    def post(path, payload):
        wire = payload['wire']
        assert wire['thinking'] == {'type': 'disabled'}
        if path in {'/tokenize', '/tokenize-prefix'}:
            return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(wire)),
                    'method': 'scripted CPU bound', 'count_only_not_dispatchable': path.endswith('prefix')}
        assert path == '/chat/completions'
        requests.append(copy.deepcopy(wire))
        assert len(requests) <= 2, 'A final review cannot introduce a third scripted response'
        index = len(requests)
        description = next(tool['function']['description'] for tool in wire['tools']
                           if tool['function']['name'] == 'staff_done')
        assert description == DONE_DESCRIPTION
        if index == 1:
            assert not any(message.get('content') == FINISH_REVIEW for message in wire['messages'])
        else:
            assert sum(message.get('content') == FINISH_REVIEW for message in wire['messages']) == 1
        return {'id': f'fixture-review-response-{index}', 'model': 'deepseek-flash',
            'object': 'chat.completion', 'created': 0,
            'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': f'fixture-review-call-{index}', 'type': 'function', 'function': {
                        'name': 'staff_done', 'arguments': json.dumps({'reason': 'finished' if index == 1 else 'reviewed'})}}]}}],
            'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                      'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}

    adapter = DeepSeekEpisodeAdapter(post=post, arm='PROJECT', slot_id='v105:fixture-review',
        condition_id='fixture', token_budget=5_000_000, folder=output/'ledger',
        allowed_tool_names=allowed, soft_at=deadline.soft_at, hard_at=deadline.hard_at)
    owner = managed.ProjectOwner(adapter, window_id='v105:fixture-review',
                                 identity={'policy_version': 'cpu-finish-review'})
    class Worker(FinishReviewWorkerMixin, managed.worker_type()):
        pass
    runtime, _, _ = managed.build_runtime(owner, prepared, output/'runtime', deadline=deadline,
        public_initial_message='Scripted finish-review control; do not call any real model.', worker_factory=Worker)
    limits = validate_condition(condition('PROJECT'))
    decorate_runtime(runtime, adapter=adapter, started={
        'started': deadline.started, 'soft_at': deadline.soft_at, 'hard_at': deadline.hard_at}, limits=limits)
    world_before = copy.deepcopy(prepared.world.store.load())
    first = None
    try:
        def after_opportunity(outcome):
            nonlocal first
            worker = runtime.policies['member_001']
            if first is None:
                assert outcome['status'] == 'running'
                assert worker._done is None
                assert runtime.waiting == runtime.work_ended == runtime.stopped == {}
                first = {'status': outcome['status'], 'worker_done': worker._done,
                         'actual_requests': len(requests), 'actual_tokens': adapter.ledger.actual}
        boundary = run_fragment(prepared, runtime, on_opportunity=after_opportunity)
        worker = runtime.policies['member_001']
        assert boundary['execution_integrity_failure'] is None
        assert len(requests) == adapter.ledger.attempts == adapter.ledger.decisions == 2
        assert worker.meter['budget_accounted_tokens'] == runtime.team_budget.snapshot()['charged_tokens'] == adapter.ledger.actual == 562
        assert worker._done == 'reviewed' and runtime.actions == 0
        assert runtime.finish_review_policy_v110.used == 1
        assert prepared.world.store.load() == world_before
        assert not any(prohibited.values())
        result = {'version': 'v110-real-managed-SDK-finish-review-control-r1', 'passed': True,
            'first_finish': first, 'scripted_responses': 2, 'scripted_total_tokens': 562,
            'actual_sdk_path': True, 'first_finish_never_accepted': True,
            'second_finish_accepted': True, 'same_identity_and_world': True,
            'accounting_layers_equal': True, 'final_review': runtime.finish_review_policy_v110.snapshot(),
            'world_actions': 0, 'public_test_processes': 0, 'model_calls': 0,
            'Docker_operations': 0, 'GPU_operations': 0, 'prohibited_operations': prohibited}
        (output/'result.json').write_bytes(json_bytes(result))
        print(json.dumps(result, ensure_ascii=False))
    finally:
        close_runtime(runtime)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    control(parser.parse_args().output)
