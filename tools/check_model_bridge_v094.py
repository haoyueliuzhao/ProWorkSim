"""Real FIFO/SDK/counter/client settlement control with scripted provider replies.

No Docker, HTTP, GPU or model execution. The write-capable client uses a temporary
copy of the original ledger; the two real FIFO endpoints are temporary files.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT/'runs/software-benchmark-v066/sdk-bundle-r1/stage/opt/pws-runtime'
VERSION = 'v094-real-FIFO-SDK-accounting-CPU-control-r1'


def offline_guard(attempts):
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
    os.environ['OPENHANDS_SUPPRESS_BANNER'] = '1'
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    os.environ['CUDA_VISIBLE_DEVICES'] = ''

    def audit(event, values):
        if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto', 'socket.bind'}:
            attempts.append(event)
            raise AssertionError('No network in the FIFO CPU control, including dependency imports')
        if event == 'open' and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.startswith(('/dev/nvidia', '/dev/dri/')) or path.endswith(('.safetensors', '.gguf')):
                raise AssertionError('No GPU or model weights in the FIFO CPU control')
    sys.addaudithook(audit)


def fifo_child(control):
    offline_guard([])
    from proworksim.software_benchmark_io_v088 import fifo_module
    from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
    fifo = fifo_module()
    private_function(fifo.container_bridge, CONTROL=Path(control).resolve())(Path(control).resolve())


def load_tool(name):
    spec = importlib.util.spec_from_file_location('v094_CPU_'+name, ROOT/'tools'/name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_control():
    forbidden = []
    offline_guard(forbidden)
    from openhands.sdk.llm import Message, TextContent
    from proworksim import software_benchmark_api_scope_v094 as scope
    from proworksim import software_benchmark_recovery_runtime_v094 as runtime
    from proworksim import software_benchmark_deepseek_budget_v089 as budget
    from proworksim import software_benchmark_api_bridge_v094 as bridge
    from proworksim.software_benchmark_candidates_v054 import reference
    from proworksim.software_benchmark_deepseek_adapter_v064 import DeepSeekEpisodeAdapter, build_native_llm
    from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
    from proworksim.software_benchmark_fd_v085 import FDGuard
    from proworksim.software_benchmark_io_v088 import fifo_module
    from proworksim import software_benchmark_deepseek_contract_v064 as contract

    if os.getuid() == 0:
        raise PermissionError('Ordinary-user CPU control only')
    rows = scope.load(reference(scope.INVENTORY_FILE))['rows']

    def no_network(*_args, **_kwargs):
        forbidden.append(True)
        raise AssertionError('No socket, HTTP or DNS in the FIFO CPU control')

    result = {'version': VERSION, 'passed': False, 'model_calls': 0, 'HTTP_calls': 0,
        'Docker_operations': 0, 'GPU_operations': 0, 'real_FIFO_files': True,
        'actual_episode_thread_global_entry_called': True, 'cases': [],
        'provider_responses_scripted': True, 'manager_parent_cgroups_are_explicit_fixtures': True,
        'full_system_runtime_verified': False,
        'uncovered_stages': ['real Docker stdio frame transport and PID1 startup',
                             'actual provider/model generation', 'candidate export and official scoring']}
    fifo = fifo_module()
    fixture = load_tool('check_api_episode_v093.py')
    with tempfile.TemporaryDirectory(prefix='v094-FIFO-CPU-') as temporary:
        folder = Path(temporary)
        guard, auth, sources, operations = private_function(fixture.fixture_guard, scope=scope, runtime=runtime)(folder)
        cpu_scope = SimpleNamespace(**{**vars(scope), 'AUTH_FILE': Path(auth['path']), 'SOURCE_FILE': Path(sources['path'])})
        dispatch = private_function(runtime.bindings.dispatch_view, scope=cpu_scope)
        policy_factory = private_function(runtime.bindings.policy, scope=cpu_scope, dispatch_view=dispatch)
        policy = policy_factory(guard, watchdog_guard=lambda: {'fresh': True, 'admit': True},
            authorization_ref=auth, qwen_target=0, capacity_probe=lambda: {})
        # This is the final new episode factory, after the IO/failure wrappers.
        episode = runtime.bindings.episode(policy)
        actual_entry = episode._run.__globals__['serve_model_channel']
        assert actual_entry is episode.serve_model_channel
        assert actual_entry.func is bridge.serve_model_channel
        assert actual_entry.keywords['scope_guard'] is policy.require_v066_allowed
        copied = folder/'cash.sqlite3'
        with closing(sqlite3.connect(budget.LEDGER.resolve().as_uri()+'?mode=ro', uri=True)) as live:
            before = live.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
            with closing(sqlite3.connect(copied)) as target:
                live.backup(target)
        with patch.object(socket.socket, 'connect', no_network), \
             patch.object(socket.socket, 'connect_ex', no_network), patch.object(socket, 'getaddrinfo', no_network):
            raw = budget.build_runtime(scope_guard=guard, retry_rows=scope.canonical_rows(),
                inventory_ref=reference(scope.CANONICAL_INVENTORY_FILE), identity_file=folder/'api/identity.json')
            # Original initializer code, with only key/DB IO injected locally;
            # no module globals, old dispatch guards or client classes patched.
            cpu_api = SimpleNamespace(**{**vars(budget.API_VIEW), 'load_api_key': lambda _: 'CPU-unused-key'})
            private_function(raw.initialize_for_run.__func__, LEDGER=copied, api=cpu_api)(raw)
            assert raw.client.ledger.path == copied.resolve()
            api = runtime.PhysicalRuntimeView(budget.RuntimeView(raw, FDGuard()), rows)

            class Schema:
                def __init__(self, value):
                    self.value = value
                def to_openai_tool(self, **_kwargs):
                    return copy.deepcopy(self.value)

            class PipeChannel:
                def __init__(self, process):
                    self.process = process
                    self.reader = fifo.LineReader(process.stdout.fileno())
                    self.buffer = self.reader.pending
                    self.decoder = SimpleNamespace(buffer=bytearray())
                def readline(self, deadline):
                    try:
                        return fifo.encoded_frame(self.reader.read(deadline))
                    except EOFError:
                        return b''
                def write(self, payload):
                    fifo.write_frame(self.process.stdin.fileno(), fifo.decode_frame(payload), time.monotonic()+10)

            for arm in ('REF', 'PROJECT'):
                row = next(r for r in rows if r['arm'] == arm)
                case = folder/arm
                case.mkdir()
                control = case/'fifo'
                control.mkdir()
                broker = api.transport_factory(row, case)
                tool_name = 'think' if arm == 'REF' else 'staff_wait'

                class ScriptedProvider:
                    def __init__(self):
                        self.calls = 0
                    def abort(self):
                        pass
                    def request(self, method, path, payload):
                        assert (method, path) == ('POST', '/chat/completions')
                        self.calls += 1
                        if self.calls == 3:
                            raise contract.APIUncertainFailure('scripted CPU unknown response')
                        measured = raw.counter(payload)['prompt_tokens']
                        tools = ([{'id': arm+'-tool-'+str(i), 'type': 'function',
                            'function': {'name': tool_name, 'arguments': '{}'}} for i in (1, 2)]
                                 if self.calls == 1 else [])
                        return {'id': 'cpu-v094-'+arm+'-'+str(self.calls), 'object': 'chat.completion',
                            'created': 0, 'model': contract.MODEL,
                            'choices': [{'index': 0, 'finish_reason': 'tool_calls' if tools else 'stop',
                                'message': {'role': 'assistant', 'content': None if tools else '',
                                    'reasoning_content': 'Scripted CPU reasoning' if tools else '', 'tool_calls': tools}}],
                            'usage': {'prompt_tokens': measured, 'completion_tokens': 16,
                                'total_tokens': measured+16, 'prompt_cache_hit_tokens': 0,
                                'prompt_cache_miss_tokens': measured,
                                'completion_tokens_details': {'reasoning_tokens': 4 if tools else 0}}}

                provider = ScriptedProvider()
                broker.client.transport = provider
                env = os.environ.copy()
                env.update(PYTHONPATH=os.pathsep.join(map(str, [ROOT/'src', SDK/'site', SDK/'overlay', SDK/'upstream-tools'])),
                    PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1', CUDA_VISIBLE_DEVICES='', NVIDIA_VISIBLE_DEVICES='void')
                stderr = (case/'fifo-child.stderr').open('wb')
                process = subprocess.Popen([str(SDK/'bin/python'), str(Path(__file__).resolve()),
                    '--fifo-child', str(control)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, env=env)
                channel, stopped, ready, served = PipeChannel(process), threading.Event(), threading.Event(), {}
                thread = threading.Thread(target=lambda: served.update(actual_entry(channel,
                    endpoint='http://127.0.0.1:18219', key_file=None, deadline=time.monotonic()+60,
                    stop_event=stopped, slot_id=row['slot_id'], on_ready=ready.set, transport=broker)))
                transport = None
                thread.start()
                try:
                    assert ready.wait(10), served
                    transport = fifo.FifoModelTransport('http://127.0.0.1:18219', control=control)
                    adapter = DeepSeekEpisodeAdapter(post=transport.post, arm=arm, slot_id=row['slot_id'],
                        condition_id=row['condition_id'], token_budget=5_000_000, folder=case/'controller-ledger',
                        allowed_tool_names=raw.schemas['tool_names'][arm])
                    llm = build_native_llm(adapter, normalization_folder=case/'SDK-projections')
                    schemas = [Schema(t) for t in raw.schemas['schemas'][arm]]
                    messages = [Message(role='user', content=[TextContent(text='CPU fixture; no repository task.')])]
                    assert llm.get_token_count(messages, tools=schemas) > 0
                    first = llm.completion(messages, tools=schemas)
                    messages.append(first.message)
                    messages.append(Message(role='tool', name=tool_name, tool_call_id=arm+'-tool-1',
                                            content=[TextContent(text='Scripted first result')]))
                    assert llm.get_token_count(messages, tools=schemas) > 0  # real /tokenize-prefix
                    messages.append(Message(role='tool', name=tool_name, tool_call_id=arm+'-tool-2',
                                            content=[TextContent(text='Scripted second result')]))
                    second = llm.completion(messages, tools=schemas)
                    assert not second.message.tool_calls and all(
                        not getattr(part, 'text', '').strip() for part in second.message.content)
                    messages.extend([second.message, Message(role='user', content=[TextContent(text='CPU error case')])])
                    try:
                        llm.completion(messages, tools=schemas)
                    except contract.APIUncertainFailure:
                        pass
                    else:
                        raise AssertionError('Scripted provider error did not cross the actual FIFO')
                    ledger = adapter.ledger.snapshot()
                    assert ledger['attempts'] == 3 and len(ledger['calls']) == 2
                    assert ledger['complete_actual_tokens'] is None and ledger['uncertain_reserved_tokens'] > 0
                    assert (case/'controller-ledger/response-0001.json').is_file()
                    assert (case/'controller-ledger/response-0002.json').is_file()
                    assert not (case/'controller-ledger/response-0003.json').exists()
                    with closing(sqlite3.connect(copied)) as db:
                        statuses = dict(db.execute('SELECT status,COUNT(*) FROM requests WHERE slot_id=? GROUP BY status',
                                                   (row['slot_id'],)))
                        actual = sum(json.loads(r[0])['total_tokens'] for r in db.execute(
                            'SELECT usage_json FROM requests WHERE slot_id=? AND status="settled"', (row['slot_id'],)))
                    assert statuses == {'settled': 2, 'uncertain': 1}
                    assert actual == ledger['known_actual_tokens']
                finally:
                    stopped.set()
                    thread.join(12)
                    if transport is not None:
                        transport.close()
                    if process.poll() is None:
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.terminate()  # only the exact child spawned above
                            process.wait(timeout=5)
                    process.stdin.close()
                    process.stdout.close()
                    stderr.close()
                assert not thread.is_alive() and process.returncode == 0, served
                assert served['status'] == 'stopped_after_controller'
                assert served['count_requests'] >= 5 and served['generation_requests'] == 3 and served['failed_requests'] == 1
                assert provider.calls == 3
                result['cases'].append({'arm': arm, 'physical_slot_index': row['slot_index'],
                    'canonical_slot_index': api.canonical_row(row)['slot_index'], 'bridge': served,
                    'temporary_cash_statuses': statuses, 'controller_known_tokens': actual,
                    'real_count_prefix_and_completion': True, 'known_settlements': 2,
                    'uncertain_reservation_preserved': True, 'actual_provider_calls': 0,
                    'scripted_provider_calls': provider.calls, 'controller_originals_persisted': True})

            class UnreadChannel:
                def readline(self, **_kwargs):
                    raise AssertionError('Rejected bridge must not read the channel')
            rejected = actual_entry(UnreadChannel(), endpoint='http://127.0.0.1:18219', key_file=None,
                deadline=time.monotonic()+5, stop_event=threading.Event(), slot_id='not-in-the-registry', transport=broker)
            assert rejected['status'] == 'technical_unknown' and not rejected['ready'] and not rejected['requests']
            result['initial_guard_failure_receipt'] = rejected
            assert not forbidden
        with closing(sqlite3.connect(budget.LEDGER.resolve().as_uri()+'?mode=ro', uri=True)) as live:
            assert live.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == before
        result.update(passed=True, full_required_CPU_control_complete=True, broker_controls_complete=True,
            interfaces_checked=['REF', 'PROJECT'], live_ledger_requests_unchanged=before,
            scope_operations=operations, HTTP_socket_DNS_attempts=len(forbidden))
    result['sources'] = [reference(__file__), reference(bridge.__file__), reference(runtime.__file__), reference(scope.__file__)]
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fifo-child', type=Path)
    args = parser.parse_args()
    if args.fifo_child:
        fifo_child(args.fifo_child)
    else:
        from proworksim.software_benchmark_candidates_v054 import write_new
        value = run_control()
        output = ROOT/'artifacts/software-benchmark-v094/real-FIFO-control-r1/summary.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        write_new(output, value)
        print(json.dumps({'passed': value['passed'], 'cases': len(value['cases']), 'model_calls': 0}))
