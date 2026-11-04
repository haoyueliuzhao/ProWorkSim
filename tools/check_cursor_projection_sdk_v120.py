"""Cold SDK replay of argument bytes only, with no real model/task execution."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile


def control(output):
    root = Path(__file__).resolve().parents[1]
    output = Path(output).resolve()
    if os.geteuid() == 0 or not output.is_relative_to(root/'artifacts/software-benchmark-v120'):
        raise PermissionError('Use an ordinary user and a fresh CPU evidence directory')
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(output/'sdk-settings'),
        LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
        HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    def deny(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto', 'subprocess.Popen'}:
            raise AssertionError('Only local CPU files and scripted requests are permitted')
        if event == 'open' and args and isinstance(args[0], (str, bytes)):
            path = os.fsdecode(args[0])
            if path.endswith(('.safetensors', '.gguf')) or path.startswith(('/dev/nvidia', '/dev/dri/')):
                raise AssertionError('No model weights or GPU')
    sys.addaudithook(deny)
    from proworksim import software_benchmark_managed_v117 as managed
    from proworksim import software_benchmark_tooling_v117 as original_tooling
    from proworksim import software_benchmark_tooling_v120 as fixed
    from proworksim.harness_port import HarnessPort
    from proworksim.model_policy import CONTROL_TOOLS
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_benchmark_candidates_v054 import reference, write_new, checked
    from proworksim.software_benchmark_deepseek_adapter_v105 import DeepSeekEpisodeAdapter
    from proworksim.software_benchmark_review_runtime_v117 import FinishReviewWorkerMixin
    from proworksim.software_benchmark_history_v117 import history_worker_type
    from proworksim.software_calibration_collector_v051 import close_runtime, run_fragment
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest, json_bytes

    original_path = root/'runs/software-benchmark-v118/project-repaired-r1/episodes/8000/controller-output/model-ledger/response-0005.json'
    original = json.loads(original_path.read_bytes())
    raw_arguments = original['choices'][0]['message']['tool_calls'][0]['function']['arguments']
    raw = json.loads(raw_arguments)
    assert raw == {'path_prefix': 'pylint/checkers/similar.py', 'text': 'min_lines'}
    calls, public_calls = [], []
    with tempfile.TemporaryDirectory(prefix='fixture-', dir=output) as temporary:
        folder = Path(temporary)
        source = folder/'public'
        (source/'pylint/checkers').mkdir(parents=True)
        (source/'pylint/checkers/similar.py').write_text('min_lines = 1\n')
        task = 'fixture__v120-argument-order'
        manifest = capture_repository(source, folder/'snapshot', task_id=task,
            problem_statement='Synthetic search-only argument bridge control.',
            source_identity={'instance_id': task, 'repo': 'fixture/control', 'base_commit': 'a'*40,
                             'dataset_revision': 'b'*40})
        deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
        def no_public(**_):
            public_calls.append(True)
            raise AssertionError('No public tests may execute')
        prepared = fixed.prepare_case(manifest, folder/'world', max_total_tokens=5_000_000,
            public_test_callback=no_public, deadline=deadline,
            public_test_entry={'version': 'v064-repository-public-test-entry-r1', 'instance_id': task,
                'argv': ['/never/python', '-m', 'pytest'], 'cwd': '/testbed',
                'timeout_seconds': 600, 'hidden_material_used': False})
        port = fixed.SoftwareCollaborationPort(prepared.world.session('member_001', fixed.PROJECT), 'member_001')
        gateway = HarnessPort(port, 'member_001', project_id=fixed.PROJECT,
            public_sink=lambda *_: None, world_sink=lambda *_: None, harness_sink=lambda *_: None)
        allowed = {row['name'] for row in [*gateway.tools(), *CONTROL_TOOLS]}
        def post(route, payload):
            wire = payload['wire']
            if route in {'/tokenize', '/tokenize-prefix'}:
                return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(wire)),
                    'method': 'CPU scripted', 'count_only_not_dispatchable': route.endswith('prefix')}
            assert route == '/chat/completions' and wire.get('tools')
            calls.append(copy.deepcopy(wire))
            index = len(calls)
            assert index <= 5
            name = 'search_repository' if index <= 2 else 'read_file' if index == 3 else 'staff_done'
            arguments = (raw_arguments if index == 1 else
                json.dumps({'cursor': None, 'path_prefix': raw['path_prefix'], 'text': raw['text']}) if index == 2 else
                json.dumps({'start_line': 1.0, 'path': raw['path_prefix']}) if index == 3 else
                json.dumps({'reason': 'CPU scripted completion '+str(index)}))
            return {'id': 'fixture-'+str(index), 'model': 'deepseek-flash', 'object': 'chat.completion', 'created': 0,
                'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                    'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'fixture-call-'+str(index),
                    'type': 'function', 'function': {'name': name, 'arguments': arguments}}]}}],
                'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                    'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
        slot = 'v120:'+task+':CPU:1'
        adapter = DeepSeekEpisodeAdapter(post=post, arm='PROJECT', slot_id=slot, condition_id='CPU',
            token_budget=5_000_000, folder=folder/'ledger', allowed_tool_names=allowed,
            soft_at=deadline.soft_at, hard_at=deadline.hard_at)
        owner = managed.ProjectOwner(adapter, window_id=slot, identity={'policy_version': 'CPU-order-regression'})
        class RepairedWorker(fixed.ToolFeedbackWorkerMixin, FinishReviewWorkerMixin, history_worker_type()):
            pass
        runtime, _, _ = managed.build_runtime(owner, prepared, folder/'runtime', deadline=deadline,
            public_initial_message='CPU script; do not use any external service.', worker_factory=RepairedWorker)
        worker = runtime.policies['member_001']
        try:
            actual_tool = worker.agent.tools_map['search_repository']
            action = actual_tool.action_from_arguments(raw)
            projected = action.model_dump(mode='json', by_alias=True, exclude_unset=True, exclude_computed_fields=True)
            assert projected == raw and list(projected) != list(raw)
            called_before = []
            # Reproduce the old bug against the actual SDK action, before any
            # model opportunity, with a delegate that must never be entered.
            old = original_tooling._NullableCursorExecutor(
                lambda *_: called_before.append(True), worker, 'search_repository',
                next(row['parameters'] for row in worker.definitions if row['name'] == 'search_repository'))
            worker._pending = {'name': 'search_repository', 'arguments': raw, 'tool_call_id': 'CPU-original'}
            try:
                old(action, worker.conversation)
            except ValueError as error:
                old_error = str(error)
                assert 'SDK changed managed arguments' in old_error
            else:
                raise AssertionError('The frozen old wrapper did not reproduce its known false rejection')
            finally:
                worker._pending = None
            assert called_before == [] and adapter.ledger.attempts == 0
            before = port.observe()['workspace_reference']
            result = run_fragment(prepared, runtime)
            assert result['execution_integrity_failure'] is None
            assert len(calls) == adapter.ledger.attempts == adapter.ledger.decisions == 5
            assert worker.meter['budget_accounted_tokens'] == runtime.team_budget.snapshot()['charged_tokens'] == adapter.ledger.actual == 1405
            assert runtime.actions == 3 and runtime.finish_review_policy_v117.used == 1
            saved = json.loads(checked(adapter.ledger.calls[0]['response']).read_bytes())
            assert saved['choices'][0]['message']['tool_calls'][0]['function']['arguments'] == raw_arguments
            assert before == port.observe()['workspace_reference'] and not public_calls
            numeric = json.loads(checked(adapter.ledger.calls[2]['response']).read_bytes())
            numeric_raw = json.loads(numeric['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
            assert type(numeric_raw['start_line']) is float
            assert any(item.get('decision', {}).get('action') == 'read_file'
                and item.get('response', {}).get('ok') is False for item in result['outcomes'])
            report = {'version': fixed.VERSION, 'passed': True, 'original_failure_source': reference(original_path),
                'original_raw_arguments': raw_arguments, 'actual_SDK_projected_arguments': projected,
                'JSON_values_equal': projected == raw, 'JSON_object_order_differs': list(projected) != list(raw),
                'old_wrapper_error': old_error, 'old_wrapper_delegate_calls': len(called_before),
                'new_full_runtime_executed_searches': 2, 'scripted_responses': 5, 'scripted_tokens': 1405,
                'three_accounting_layers_equal': True, 'raw_argument_bytes_preserved': True,
                'one_finish_review': True, 'source_version_unchanged': True,
                'numeric_raw_1_point_0_preserved': True, 'numeric_world_schema_rejection_did_not_crash_SDK': True}
        finally:
            close_runtime(runtime)
    report.update(source_control=reference(__file__), implementation=reference(fixed.__file__),
        real_API_calls=0, real_model_calls=0, Docker_operations=0, GPU_operations=0,
        public_test_processes=0, original_attempts_reopened=0, temporary_fixture_removed=True)
    print(json.dumps(write_new(output/'summary.json', report), ensure_ascii=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    control(args.output)
