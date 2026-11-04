"""Two actual v117 SDK paths; scripted responses only, with no task execution."""
from __future__ import annotations
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid


def control(output, arms=('REF', 'PROJECT')):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(output/'settings'),
        LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
        HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    def deny(event, _args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto', 'subprocess.Popen'}:
            raise AssertionError('CPU SDK fixture cannot dispatch network or processes')
    sys.addaudithook(deny)
    from proworksim import software_benchmark_managed_v117 as managed
    from proworksim import software_benchmark_public_test_world_v110 as world
    from proworksim.harness_port import HarnessPort
    from proworksim.model_policy import CONTROL_TOOLS
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_benchmark_alignment_contract_v117 import condition, validate_condition
    from proworksim.software_benchmark_candidates_v054 import checked
    from proworksim.software_benchmark_deepseek_adapter_v105 import DeepSeekEpisodeAdapter, NATIVE_TOOLS
    from proworksim.software_benchmark_native_control_v117 import run_controlled_conversation
    from proworksim.software_benchmark_sdk_bundle_v066 import NATIVE_SCHEMA_SOURCE
    from proworksim.software_calibration_collector_v051 import close_runtime, run_fragment
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest, json_bytes
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('actual_ref_controller_v117', root/'tools/run_ref_controller_v117.py')
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    # The precise malformed arguments of the original stopped episode are not
    # rewritten; only this synthetic response routes them to the public action.
    old = root/'runs/software-benchmark-v111/aligned-interface-r1/episodes/7251/controller-output/ref-ledger'
    ledger = json.loads((old/'ledger.json').read_bytes())
    original = json.loads((old/f"response-{ledger['attempts']:04d}.json").read_bytes())
    bad = original['choices'][0]['message']['tool_calls'][0]['function']['arguments']
    results = []
    for arm in arms:
        directory = output/arm
        directory.mkdir()
        requests = []
        def post(route, payload):
            wire = payload['wire']
            if route in {'/tokenize', '/tokenize-prefix'}:
                return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(wire)),
                    'method': 'scripted CPU count', 'count_only_not_dispatchable': route.endswith('prefix')}
            assert route == '/chat/completions'
            requests.append(copy.deepcopy(wire))
            index = len(requests)
            assert index <= 3
            name = ('terminal' if arm == 'REF' else 'read_file') if index == 1 else (
                'finish' if arm == 'REF' else 'staff_done')
            args = bad if index == 1 else json.dumps(
                {'message': 'Fixture complete', 'security_risk': 'LOW'} if arm == 'REF'
                else {'reason': 'Fixture complete'})
            return {'id': f'fixture-{arm}-{index}', 'object': 'chat.completion', 'created': 0,
                'model': 'deepseek-flash', 'choices': [{'index': 0, 'finish_reason': 'tool_calls',
                'message': {'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': f'fixture-call-{arm}-{index}', 'type': 'function',
                    'function': {'name': name, 'arguments': args}}]}}],
                'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                          'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
        source = directory/'source'
        source.mkdir()
        (source/'sample.py').write_text('value = 1\n')
        if arm == 'REF':
            adapter = DeepSeekEpisodeAdapter(post=post, arm=arm, slot_id='v117:fixture:REF',
                condition_id=condition(arm)['condition_id'], token_budget=5_000_000,
                folder=directory/'ledger', allowed_tool_names=NATIVE_TOOLS)
            rpc = SimpleNamespace(_bound=False, ready=json.loads(NATIVE_SCHEMA_SOURCE.read_bytes()),
                session_id='v117_rejected_'+uuid.uuid4().hex,
                request=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError('Bad arguments may not execute')))
            limits = validate_condition(condition(arm))
            conversation = controller.create_conversation({}, adapter, rpc, directory/'output', limits, workspace=source)
            try:
                now = time.monotonic()
                conversation.send_message('Synthetic CPU control only.')
                result = run_controlled_conversation(conversation, adapter=adapter,
                    started={'started': now, 'soft_at': now+21600, 'hard_at': now+23400}, limits=limits)
                assert result['final_sdk_status'] == 'finished'
                assert len(adapter.history.receipts) == 1
                assert any('_openhands_malformed_tool_call' in str(message) for message in requests[1]['messages'])
            finally:
                conversation.close()
        else:
            manifest = capture_repository(source, directory/'snapshot', task_id='fixture__117',
                problem_statement='CPU fixture: malformed response then explicit finish.',
                source_identity={'instance_id': 'fixture__117', 'repo': 'fixture/test',
                                 'base_commit': 'a'*40, 'dataset_revision': 'b'*40})
            deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
            entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': 'fixture__117',
                'argv': ['/fixture/python', '-m', 'pytest'], 'cwd': '/testbed',
                'timeout_seconds': 600, 'hidden_material_used': False}
            prepared = managed.prepare_case(manifest, directory/'world', max_total_tokens=5_000_000,
                public_test_callback=lambda **_: (_ for _ in ()).throw(AssertionError('No public test process')),
                deadline=deadline, public_test_entry=entry)
            gateway = HarnessPort(world.SoftwareCollaborationPort(
                prepared.world.session('member_001', world.PROJECT), 'member_001'), 'member_001',
                project_id=world.PROJECT, public_sink=lambda *_: None, world_sink=lambda *_: None,
                harness_sink=lambda *_: None)
            allowed = {row['name'] for row in [*gateway.tools(), *CONTROL_TOOLS]}
            adapter = DeepSeekEpisodeAdapter(post=post, arm=arm, slot_id='v117:fixture:PROJECT',
                condition_id=condition(arm)['condition_id'], token_budget=5_000_000,
                folder=directory/'ledger', allowed_tool_names=allowed,
                soft_at=deadline.soft_at, hard_at=deadline.hard_at)
            owner = managed.ProjectOwner(adapter, window_id='v117:fixture:PROJECT',
                                         identity={'policy_version': 'v117-cpu-rejection'})
            runtime, _, _ = managed.build_runtime(owner, prepared, directory/'runtime', deadline=deadline,
                public_initial_message='CPU fixture: no real model or test.')
            before = copy.deepcopy(prepared.world.store.load())
            try:
                boundary = run_fragment(prepared, runtime)
                worker = runtime.policies['member_001']
                assert boundary['execution_integrity_failure'] is None, boundary
                assert runtime.actions == 0 and prepared.world.store.load() == before
                assert len(worker._rejected_history_v117['receipts']) == 1
                assert worker.meter['budget_accounted_tokens'] == runtime.team_budget.snapshot()['charged_tokens'] == 843
                assert any('public_format_feedback' in str(message) for message in requests[1]['messages'])
                assert not any('_openhands_malformed_tool_call' in str(message) for message in requests[1]['messages'])
            finally:
                close_runtime(runtime)
        assert adapter.ledger.attempts == adapter.ledger.decisions == len(requests) == 3
        assert adapter.ledger.actual == 843
        saved = json.loads(checked(adapter.ledger.calls[0]['response']).read_bytes())
        assert saved['choices'][0]['message']['tool_calls'][0]['function']['arguments'] == bad
        results.append({'arm': arm, 'scripted_responses': 3, 'charged_tokens': 843,
            'original_bad_arguments_preserved': True, 'rejected_action_executed': False,
            'automatic_retry': False, 'actual_conversation_recovery': True})
    report = {'version': 'v117-rejected-history-real-SDK-control-r1', 'passed': True,
        'results': results, 'real_API_requests': 0, 'Docker_operations': 0, 'real_task_tests': 0}
    (output/'result.json').write_bytes(json_bytes(report))
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arms', nargs='+', choices=['REF', 'PROJECT'], default=['REF', 'PROJECT'])
    args = parser.parse_args()
    control(args.output, args.arms)
