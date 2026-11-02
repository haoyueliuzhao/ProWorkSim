"""Scripted non-thinking SDK tool roundtrips through native and managed factories."""
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
    os.environ['OH_PERSISTENCE_DIR'] = str(output / 'sdk-settings')
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
    os.environ['OPENHANDS_SUPPRESS_BANNER'] = '1'
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
    from proworksim import software_benchmark_managed_v105 as managed
    from proworksim import software_benchmark_world_v064 as world
    from proworksim.harness_port import HarnessPort
    from proworksim.model_policy import CONTROL_TOOLS
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_benchmark_deepseek_adapter_v105 import DeepSeekEpisodeAdapter, build_native_llm
    from proworksim.software_calibration_collector_v051 import close_runtime
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest, json_bytes

    source = output / 'public'
    source.mkdir()
    (source / 'sample.py').write_text('value = 1\n')
    manifest = capture_repository(source, output / 'snapshot', task_id='fixture__105',
        problem_statement='Read the permitted repository.', source_identity={
            'instance_id': 'fixture__105', 'repo': 'fixture/test', 'base_commit': 'a' * 40,
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
        assert wire['thinking'] == {'type': 'disabled'}
        assert wire['temperature'] == wire['top_p'] == 1
        assert all('reasoning_content' not in m for m in wire['messages'])
        if path in {'/tokenize', '/tokenize-prefix'}:
            return {'prompt_tokens': 98304, 'request_sha256': digest(json_bytes(wire)),
                    'method': 'scripted CPU bound', 'count_only_not_dispatchable': path.endswith('prefix')}
        assert path == '/chat/completions'
        requests.append(copy.deepcopy(wire))
        return {'id': 'fixture-response', 'model': 'deepseek-flash', 'object': 'chat.completion',
            'created': 0, 'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'content': None,
                'tool_calls': [{'id': 'fixture-call', 'type': 'function',
                    'function': {'name': 'list_files', 'arguments': '{"cursor":null}'}}]}}],
            'usage': {'prompt_tokens': 98304, 'completion_tokens': 30, 'total_tokens': 98334,
                'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 98304}}

    adapter = DeepSeekEpisodeAdapter(post=post, arm='PROJECT', slot_id='v105:fixture',
        condition_id='fixture', token_budget=5_000_000, folder=output / 'ledger', allowed_tool_names=allowed)
    owner = managed.ProjectOwner(adapter, window_id='v105:fixture', identity={'policy_version': 'cpu-fixture'})
    runtime, _, _ = managed.build_runtime(owner, prepared, output / 'runtime', deadline=deadline,
        public_initial_message='Read the permitted repository; CPU scripted control only.')
    try:
        worker = runtime.policies['member_001']
        assert worker.config['thinking'] is False
        assert adapter.thinking is False
        assert managed.worker_config(owner, prepared.case, public_initial_message='fixture')['thinking'] is False
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
        native = native_control(output, build_native_llm, DeepSeekEpisodeAdapter)
        (output / 'project-tool-schemas.json').write_text(json.dumps(requests[0]['tools'], indent=2) + '\n')
        result = {'version': 'v105-nonthinking-real-sdk-controls-r1', 'passed': True,
            'native': native, 'managed_thinking': False, 'wire_thinking_disabled': True, 'actual_worker': type(worker).__name__,
            'scripted_SDK_responses': 2, 'scripted_prompt_tokens': 98304,
            'scripted_output_tokens': 30, 'actual_output_cap': requests[0]['max_tokens'],
            'exact_cursor_null_dispatched_once': True, 'accounting_layers_equal': True,
            'model_calls': 0, 'public_test_calls': 0, 'Docker_operations': 0,
            'forbidden_operations': forbidden, 'deployment_or_benchmark': False}
        assert not any(forbidden.values())
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        close_runtime(runtime)


def native_control(output, build_native_llm, Adapter):
    from types import SimpleNamespace
    from openhands.sdk import Conversation
    from openhands.sdk.llm import Message, TextContent
    from proworksim.software_benchmark_native_binding_v054 import build_isolated_agent
    from proworksim.software_benchmark_sdk_bundle_v066 import NATIVE_SCHEMA_SOURCE
    from proworksim.storage import digest, json_bytes

    requests, tools_seen = [], []
    def post(path, payload):
        wire = payload['wire']
        assert wire['thinking'] == {'type': 'disabled'}
        assert all('reasoning_content' not in m for m in wire['messages'])
        if path in {'/tokenize', '/tokenize-prefix'}:
            return {'prompt_tokens': 98304, 'request_sha256': digest(json_bytes(wire)),
                    'method': 'scripted CPU bound', 'count_only_not_dispatchable': path.endswith('prefix')}
        requests.append(copy.deepcopy(wire))
        return {'id': 'native-fixture-response', 'model': 'deepseek-flash', 'object': 'chat.completion',
            'created': 0, 'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'content': None,
                'tool_calls': [{'id': 'native-fixture-call', 'type': 'function',
                    'function': {'name': 'terminal', 'arguments': '{"command":"echo fixture","security_risk":"LOW"}'}}]}}],
            'usage': {'prompt_tokens': 98304, 'completion_tokens': 30, 'total_tokens': 98334,
                'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 98304}}

    def fake_rpc(tool, action, **kwargs):
        tools_seen.append((tool, action))
        return {'id': 1, 'type': 'observation', 'tool': tool,
            'observation': {'is_error': False, 'kind': 'TerminalObservation', 'exit_code': 0},
            'llm_content': [{'type': 'text', 'text': 'Scripted local observation; command not executed.'}]}

    names = {'file_editor', 'finish', 'task_tracker', 'terminal', 'think'}
    adapter = Adapter(post=post, arm='REF', slot_id='v105:native-fixture', condition_id='fixture',
        token_budget=5_000_000, folder=output / 'native-ledger', allowed_tool_names=names)
    adapter.ledger.actual = 4_883_127
    llm = build_native_llm(adapter, normalization_folder=output / 'native-projections')
    rpc = SimpleNamespace(_bound=False, ready=json.loads(NATIVE_SCHEMA_SOURCE.read_bytes()),
                          session_id='v105_cpu_nonthinking', request=fake_rpc)
    agent = build_isolated_agent(llm, rpc=rpc)
    workspace = output / 'native-workspace'
    workspace.mkdir()
    conversation = Conversation(agent=agent, workspace=workspace, plugins=[],
        persistence_dir=output / 'native-conversation', max_iteration_per_run=1, visualizer=None)
    try:
        conversation.send_message('Scripted CPU initialization; do not dispatch a model.')
        tools = list(conversation.agent.tools_map.values())
        messages = [Message(role='user', content=[TextContent(text='Scripted CPU tool roundtrip')])]
        answer = llm.completion(messages, tools, add_security_risk_prediction=True)
        assert answer.message.reasoning_content is None
        call = answer.message.tool_calls[0]
        terminal = next(tool for tool in tools if tool.name == 'terminal')
        arguments = json.loads(call.arguments)
        # Use the SDK's own normalization before its tool action parser; the
        # security annotation is part of the model schema, not TerminalAction.
        conversation.agent._extract_security_risk(arguments,
            terminal.annotations.readOnlyHint if terminal.annotations else False, None)
        conversation.agent._extract_summary(terminal.name, arguments, tool=terminal)
        action = terminal.action_from_arguments(arguments)
        observation = terminal.executor(action, conversation)
        assert len(tools_seen) == 1 and tools_seen[0][0] == 'terminal'
        tool_message = Message(role='tool', tool_call_id=call.id, name='terminal', content=observation.to_llm_content)
        llm.get_token_count([*messages, answer.message, tool_message], tools, add_security_risk_prediction=True)
        assert len(requests) == 1 and requests[0]['max_tokens'] == 18569
        assert adapter.thinking is False
        (output / 'native-tool-schemas.json').write_text(json.dumps(requests[0]['tools'], indent=2) + '\n')
        return {'passed': True, 'same_five_native_tools': {tool.name for tool in tools} == names,
                'actual_tool_transport_roundtrip': True, 'thinking': False,
                'reasoning_field_absent_accepted': True, 'actual_output_cap': 18569,
                'scripted_responses': 1, 'commands_executed': 0, 'model_calls': 0}
    finally:
        conversation.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    control(parser.parse_args().output)
