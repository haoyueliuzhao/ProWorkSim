"""Cold combined v110 SDK control using scripted replies and public-test receipts.

This is a synthetic CPU fixture, not a benchmark episode. No API request,
container, GPU, real model or task test process is permitted.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys


def control(output, *, force_summary=False):
    output = Path(output).resolve()
    project = Path(__file__).resolve().parents[1]
    if os.geteuid() == 0 or not output.is_relative_to(project/'runs/software-benchmark-v110/cpu-controls'):
        raise PermissionError('Use an ordinary user and a fresh project CPU control directory')
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(output/'sdk-settings'),
        LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
        HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    import tempfile
    scratch = output/'scratch'
    scratch.mkdir()
    tempfile.tempdir = str(scratch)  # This child process only, for isolated candidate Git encoding.
    prohibited = {'network': 0, 'weights': 0, 'gpu': 0, 'subprocess': 0}
    local_git = []

    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            prohibited['network'] += 1
            raise AssertionError('The combined CPU control cannot use the network')
        if event == 'subprocess.Popen':
            executable, argv, cwd, environment = args
            if (executable in {'/bin/git', '/usr/bin/git'} and isinstance(argv, list) and len(argv) > 9
                    and argv[1:9] == ['-c', 'core.hooksPath=/dev/null', '-c', 'core.attributesFile=/dev/null',
                        '-c', 'core.autocrlf=false', '-c', 'core.filemode=true']
                    and argv[9] in {'init', 'hash-object', 'read-tree', 'update-index', 'write-tree', 'diff', 'apply'}
                    and cwd is not None and Path(cwd).resolve().is_relative_to(scratch)
                    and environment.get('GIT_CONFIG_NOSYSTEM') == '1'
                    and environment.get('GIT_CONFIG_GLOBAL') == '/dev/null'):
                local_git.append(argv[9])
            else:
                prohibited['subprocess'] += 1
                raise AssertionError('Only isolated local candidate Git encoding is permitted')
        if event == 'open' and args and isinstance(args[0], (str, bytes)):
            path = os.fsdecode(args[0])
            if path.endswith(('.safetensors', '.gguf')) or 'pytorch_model' in path:
                prohibited['weights'] += 1
                raise AssertionError('No model weights are permitted')
            if path.startswith(('/dev/nvidia', '/dev/dri/')):
                prohibited['gpu'] += 1
                raise AssertionError('No GPU is permitted')

    sys.addaudithook(audit)
    from proworksim import software_benchmark_managed_v110 as managed
    from proworksim import software_benchmark_public_test_world_v110 as world
    from proworksim.harness_port import HarnessPort
    from proworksim.model_policy import CONTROL_TOOLS
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_benchmark_alignment_contract_v110 import condition
    from proworksim.software_benchmark_candidates_v054 import checked
    from proworksim.software_benchmark_deepseek_adapter_v105 import DeepSeekEpisodeAdapter
    from proworksim.software_benchmark_finish_review_v110 import FINISH_REVIEW, DONE_DESCRIPTION
    from proworksim.software_benchmark_history_v110 import SUMMARY_LABEL
    from proworksim.software_benchmark_project_closure_v110 import export_managed_closure
    from proworksim.software_benchmark_public_tests_v110 import VERSION, selected_entry
    from proworksim.software_calibration_collector_v051 import close_runtime, run_fragment
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest, json_bytes

    instance = 'fixture__alignment-110'
    slot = 'v110:' + instance + ':' + condition('PROJECT')['condition_id'] + ':11'
    source = output/'public'
    (source/'tests').mkdir(parents=True)
    (source/'sample.py').write_text('value = 1\n')
    (source/'tests/test_sample.py').write_text('def test_value(): pass\n')
    manifest = capture_repository(source, output/'snapshot', task_id=instance,
        problem_statement='Synthetic SDK control; edit, select public tests and deliver explicitly.',
        source_identity={'instance_id': instance, 'repo': 'fixture/test',
                         'base_commit': 'a'*40, 'dataset_revision': 'b'*40})
    entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': instance,
        'argv': ['/scripted/python', '-m', 'pytest'], 'cwd': '/testbed',
        'timeout_seconds': 600, 'hidden_material_used': False}
    selection = {'kind': 'pytest', 'targets': ['tests/test_sample.py::test_value']}
    public_receipts = []

    def public_callback(*, files, entry_metadata, request):
        assert files['sample.py'] == 'value = 2\n'
        assert request['public_test_selection'] == selection
        selected, chosen = selected_entry(entry, selection, files=files, entry_metadata=entry_metadata)
        result = {'passed': True, 'execution': {'executed': True,
            'input_tree_sha256': request['tree_sha256'], 'source_reference': request['source_reference'],
            'argv': selected['argv'], 'cwd': selected['cwd'],
            'public_test_selection': chosen, 'public_test_selection_revision': VERSION,
            'fixture_execution_only': True, 'actual_test_processes': 0},
            'groups': {'public_repository_tests': {'status': 'passed', 'passed': True,
                'executed': True, 'output': 'SCRIPTED receipt; no public tests were actually run.',
                'tests': [{'test_id': 'scripted-test-value', 'passed': True}]}},
            'repository_collection_errors': []}
        public_receipts.append({'request': copy.deepcopy(request), 'response': copy.deepcopy(result)})
        return result

    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = managed.prepare_case(manifest, output/'world', max_total_tokens=5_000_000,
        public_test_callback=public_callback, deadline=deadline, public_test_entry=entry)
    gateway = HarnessPort(world.SoftwareCollaborationPort(
        prepared.world.session('member_001', world.PROJECT), 'member_001'),
        'member_001', project_id=world.PROJECT, public_sink=lambda *_: None,
        world_sink=lambda *_: None, harness_sink=lambda *_: None)
    allowed = {row['name'] for row in [*gateway.tools(), *CONTROL_TOOLS]}
    actions = [
        ('replace_file', {'path': 'sample.py', 'old': 'value = 1', 'new': 'value = 2'}),
        ('run_tests', {'selection': selection}),
        ('fix_patch', {'task_ids': [], 'message': 'Explicit fixture patch of tested version'}),
        ('submit_integration', {'message': 'Explicit delivery before final review'}),
        ('staff_done', {'reason': 'First completion intent'}),
        ('replace_file', {'path': 'sample.py', 'old': 'value = 2', 'new': 'value = 3'}),
        ('staff_done', {'reason': 'Second completion intent, without delivering new version'}),
    ]
    agent_requests, summary_requests, holder = [], [], {}
    expected_tokens = {'agent': 281, 'summary': 273}

    def post(path, payload):
        wire = payload['wire']
        assert wire['thinking'] == {'type': 'disabled'}
        if path in {'/tokenize', '/tokenize-prefix'}:
            return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(wire)),
                'method': 'scripted CPU count', 'count_only_not_dispatchable': path.endswith('prefix')}
        assert path == '/chat/completions'
        if not wire.get('tools'):
            summary_requests.append(copy.deepcopy(wire))
            assert force_summary and len(summary_requests) == 1
            worker = holder['runtime'].policies['member_001']
            assert worker._in_step and worker._history_trace_v110.pending is not None
            worker.agent.condenser.max_size = 80  # Restore production threshold after this fixture-only trigger.
            message = {'role': 'assistant', 'content': 'Fixture history: changed value to 2, tested and explicitly submitted it.'}
            used, finish_reason = expected_tokens['summary'], 'stop'
            identifier = 'summary-1'
        else:
            agent_requests.append(copy.deepcopy(wire))
            index = len(agent_requests)
            assert index <= len(actions), 'No extra scripted action may be invented'
            description = next(tool['function']['description'] for tool in wire['tools']
                               if tool['function']['name'] == 'staff_done')
            assert description == DONE_DESCRIPTION
            review_count = sum(message.get('content') == FINISH_REVIEW for message in wire['messages'])
            assert review_count == (1 if index > 5 else 0)
            if force_summary and index >= 5:
                assert any(SUMMARY_LABEL in str(message.get('content')) for message in wire['messages'])
            name, arguments = actions[index-1]
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': f'fixture-action-{index}', 'type': 'function', 'function': {
                    'name': name, 'arguments': json.dumps(arguments)}}]}
            used, finish_reason, identifier = expected_tokens['agent'], 'tool_calls', f'agent-{index}'
        return {'id': 'fixture-alignment-'+identifier, 'model': 'deepseek-flash',
            'object': 'chat.completion', 'created': 0,
            'choices': [{'index': 0, 'finish_reason': finish_reason, 'message': message}],
            'usage': {'prompt_tokens': 256, 'completion_tokens': used-256, 'total_tokens': used,
                      'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}

    adapter = DeepSeekEpisodeAdapter(post=post, arm='PROJECT', slot_id=slot,
        condition_id=condition('PROJECT')['condition_id'], token_budget=5_000_000,
        folder=output/'ledger', allowed_tool_names=allowed,
        soft_at=deadline.soft_at, hard_at=deadline.hard_at)
    owner = managed.ProjectOwner(adapter, window_id=slot, identity={'policy_version': 'cpu-combined-v110'})
    runtime, _, _ = managed.build_runtime(owner, prepared, output/'runtime', deadline=deadline,
        public_initial_message='Only execute the seven scripted fixture actions; do not use external services.')
    holder['runtime'] = runtime
    worker = runtime.policies['member_001']
    assert worker.agent.condenser.max_size == 80 and worker.agent.condenser.keep_first == 4
    identities = (id(worker.conversation), id(adapter.ledger), id(runtime.team_budget), id(worker.meter))
    transitions, closed = [], False
    try:
        def after_opportunity(outcome):
            assert outcome['status'] in {'running', 'completed'}, outcome
            assert identities == (id(worker.conversation), id(adapter.ledger), id(runtime.team_budget), id(worker.meter))
            state = prepared.world.store.load()
            facts = state['projects'][world.PROJECT]['software']
            transitions.append({'response': len(agent_requests), 'status': outcome['status'],
                'worker_done': worker._done, 'deliveries': len(facts['deliveries']),
                'public_tests': prepared.world.test_budget.snapshot()['used'],
                'patches': len(facts['patches']), 'world_actions': runtime.actions})
            if len(agent_requests) == 4 and force_summary:
                worker.agent.condenser.max_size = 12  # Valid with keep_first=4; fixture only.
            if len(agent_requests) == 5:
                assert worker._done is None and outcome['status'] == 'running'
                assert runtime.waiting == runtime.work_ended == runtime.stopped == {}
                assert len(facts['deliveries']) == len(facts['patches']) == len(public_receipts) == 1

        boundary = run_fragment(prepared, runtime, on_opportunity=after_opportunity)
        assert boundary['execution_integrity_failure'] is None, boundary
        assert len(agent_requests) == 7 and len(summary_requests) == int(force_summary)
        assert worker._done == actions[-1][1]['reason']
        assert runtime.finish_review_policy_v110.used == 1
        assert runtime.actions == 5
        assert len(public_receipts) == prepared.world.test_budget.snapshot()['used'] == 1
        amount = len(agent_requests)*expected_tokens['agent'] + len(summary_requests)*expected_tokens['summary']
        budget = runtime.team_budget.snapshot()
        assert worker.meter['budget_accounted_tokens'] == budget['charged_tokens'] == adapter.ledger.actual == amount
        assert adapter.ledger.decisions == budget['decisions'] == 7
        assert adapter.ledger.attempts == budget['attempts'] == 7 + int(force_summary)
        assert budget['auxiliary_records'] == worker._history_trace_v110.counter == int(force_summary)
        assert worker.agent.condenser.max_size == 80
        worker._history_trace_v110.assert_healthy()
        assert worker._history_trace_v110.pending is None
        close_runtime(runtime)
        closed = True
        closure = export_managed_closure(prepared, output/'closure', slot_id=slot, sdk_closed=True)
        evidence = json.loads(checked(closure['delivery_evidence']).read_bytes())
        delivery = json.loads(checked(closure['delivery_snapshot']).read_bytes())
        assert closure['terminal_bundle']['files']['sample.py'] == 'value = 3\n'
        assert delivery['candidate']['files']['sample.py'] == 'value = 2\n'
        assert evidence['submitted'] is True and evidence['same_tree'] is False
        assert evidence['terminal_source_reference'] != delivery['source_reference']
        assert len(evidence['delivery_inventory']) == 1
        assert evidence['binding']['public_test_event']['public_test_selection'] == selection
        assert not any(prohibited.values())
        result = {'version': 'v110-combined-real-SDK-control-r1', 'passed': True,
            'synthetic_fixture_only': True, 'actual_managed_v110_factory': True,
            'scripted_agent_responses': len(agent_requests), 'scripted_summary_responses': len(summary_requests),
            'scripted_total_tokens': amount, 'accounting_layers_equal': True,
            'summary_uses_same_pool': bool(force_summary),
            'fixture_summary_threshold': {'production': 80, 'temporary': 12, 'restored': 80} if force_summary else None,
            'shared_review_text_once': True, 'first_finish_never_accepted': True,
            'same_conversation_and_budgets': True, 'transitions': transitions,
            'one_explicit_selected_test': selection, 'one_explicit_fixed_patch': True,
            'one_explicit_submission': True, 'final_tree_automatically_tested_or_delivered': False,
            'old_legal_delivery_preserved': True, 'old_delivery_is_final_tree': evidence['same_tree'],
            'closure_evidence': closure['delivery_evidence'], 'final_review': runtime.finish_review_policy_v110.snapshot(),
            'real_API_requests': 0, 'real_model_calls': 0, 'real_task_test_processes': 0,
            'isolated_local_candidate_git_commands': local_git,
            'Docker_operations': 0, 'GPU_operations': 0, 'prohibited_operations': prohibited}
        (output/'result.json').write_bytes(json_bytes(result))
        print(json.dumps(result, ensure_ascii=False))
        return result
    finally:
        if not closed:
            close_runtime(runtime)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--force-summary', action='store_true', help='One fixture-only max_size=12 trigger')
    options = parser.parse_args()
    control(options.output, force_summary=options.force_summary)
