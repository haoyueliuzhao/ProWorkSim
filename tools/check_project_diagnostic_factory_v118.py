"""Actual v118 zero-model adapter through the complete managed SDK factory."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import sys
import tempfile


def control(output):
    root = Path(__file__).resolve().parents[1]
    output = Path(output).resolve()
    if os.geteuid() == 0 or not output.is_relative_to(root/'artifacts/software-benchmark-v118'):
        raise PermissionError('Use a fresh project CPU evidence directory as ordinary user')
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(output/'sdk-settings'),
        LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
        HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    forbidden = {'network': 0, 'process': 0, 'weights_or_GPU': 0}
    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            forbidden['network'] += 1
            raise AssertionError('The zero-model factory control cannot use networking')
        if event in {'subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'}:
            forbidden['process'] += 1
            raise AssertionError('The zero-model factory control cannot start any process')
        if event == 'open' and args and isinstance(args[0], (str, bytes)):
            path = os.fsdecode(args[0])
            if path.endswith(('.safetensors', '.gguf')) or path.startswith(('/dev/nvidia', '/dev/dri/')):
                forbidden['weights_or_GPU'] += 1
                raise AssertionError('No model weights or GPU are permitted')
    sys.addaudithook(audit)
    from proworksim import software_benchmark_managed_v117 as managed
    from proworksim.software_benchmark_alignment_contract_v117 import condition
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_calibration_collector_v051 import close_runtime
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest

    controller = root/'tools/run_project_controller_v118.py'
    parsed = ast.parse(controller.read_text())
    classes = [node for node in ast.walk(parsed) if isinstance(node, ast.ClassDef) and node.name == 'NeverGenerate']
    if len(classes) != 1:
        raise ValueError('Require the unique actual diagnostic adapter class')
    module = ast.fix_missing_locations(ast.Module(body=classes, type_ignores=[]))
    namespace = {'condition': condition('PROJECT')}
    exec(compile(module, str(controller), 'exec'), namespace)
    adapter = namespace['NeverGenerate']()
    assert adapter.arm == 'PROJECT'
    count_calls, public_calls = [], []
    # The actual methods already refuse; count any accidental invocation too.
    original_count = adapter.count
    def forbidden_count(*args, **kwargs):
        count_calls.append(True)
        return original_count(*args, **kwargs)
    adapter.count = adapter.complete = adapter.request = forbidden_count
    def forbidden_public(**_):
        public_calls.append(True)
        raise AssertionError('No public test executes during zero-model SDK construction')
    with tempfile.TemporaryDirectory(prefix='fixture-', dir=output) as temporary:
        folder = Path(temporary)
        source = folder/'public'
        source.mkdir()
        (source/'sample.py').write_text('value = 1\n')
        task = 'fixture__v118-diagnostic-factory'
        manifest = capture_repository(source, folder/'snapshot', task_id=task,
            problem_statement='Synthetic zero-model construction fixture.',
            source_identity={'instance_id': task, 'repo': 'fixture/diagnostic',
                'base_commit': 'a'*40, 'dataset_revision': 'b'*40})
        entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': task,
            'argv': ['/never-executed/python', '-m', 'pytest'], 'cwd': '/testbed',
            'timeout_seconds': 600, 'hidden_material_used': False}
        deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
        prepared = managed.prepare_case(manifest, folder/'world', max_total_tokens=5_000_000,
            public_test_callback=forbidden_public, deadline=deadline, public_test_entry=entry)
        slot = 'v117:'+task+':'+condition('PROJECT')['condition_id']+':118'
        owner = managed.ProjectOwner(adapter, window_id=slot,
            identity={'policy_version': 'CPU-zero-model-diagnostic-factory'})
        before = prepared.world.store.load()
        runtime, _, _ = managed.build_runtime(owner, prepared, folder/'runtime', deadline=deadline,
            public_initial_message='Synthetic zero-model diagnostic; never generate or run a tool.')
        worker = runtime.policies['member_001']
        try:
            worker._history_trace_v110.assert_bound_to(worker.conversation)
            worker._history_trace_v110.assert_healthy()
            assert worker._rejected_history_v117['conversation'] is worker.conversation
            assert len(worker._nullable_cursor_v117['tools']) == 6
            assert worker.meter['decisions'] == 0 and not worker._in_step
            assert worker._pending is None and worker._done is None
            assert adapter.ledger.attempts == adapter.ledger.decisions == adapter.ledger.actual == 0
            assert adapter.ledger.inflight is None
            assert runtime.team_budget.snapshot()['charged_tokens'] == 0
            assert runtime.actions == 0
            assert before == prepared.world.store.load()
            initialized = {'actual_SDK_initialized': True,
                'worker_type': type(worker).__name__, 'conversation_type': type(worker.conversation).__name__,
                'same_conversation_summary_and_rejection_hooks': True,
                'nullable_cursor_tools': worker._nullable_cursor_v117['tools'],
                'finish_review_used': runtime.finish_review_policy_v117.used,
                'ledger_attempts': adapter.ledger.attempts, 'ledger_decisions': adapter.ledger.decisions,
                'ledger_tokens': adapter.ledger.actual, 'team_charged_tokens': runtime.team_budget.snapshot()['charged_tokens']}
        finally:
            close_runtime(runtime)
        assert count_calls == public_calls == [] and not any(forbidden.values())
        assert before == prepared.world.store.load()
    result = {'version': 'v118-real-zero-model-managed-factory-control-r1', 'passed': True,
        'controller': reference(controller), 'source_control': reference(__file__),
        'adapter_class_AST_sha256': digest(ast.dump(classes[0], include_attributes=False).encode()),
        'constructor_only': False, 'full_actual_managed_factory': True, 'closed_cleanly': True,
        'initialization': initialized, 'count_complete_request_invocations': 0,
        'public_test_callback_invocations': 0, 'real_API_requests': 0, 'real_model_calls': 0,
        'Docker_operations': 0, 'GPU_operations': 0, 'task_test_processes': 0,
        'shared_host_changes': 0, 'forbidden_operation_counts': forbidden,
        'temporary_public_world_removed': True}
    print(json.dumps(write_new(output/'summary.json', result), ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    control(args.output)
