"""Cold private-SDK CPU controls: no API, Docker, GPU, or benchmark execution."""
from __future__ import annotations

import ast
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openhands.sdk.conversation.exceptions import ConversationRunError
from proworksim import software_benchmark_normal_boundary_v108 as boundary
from proworksim import software_benchmark_deepseek_adapter_v105 as remote
from proworksim import software_benchmark_deepseek_contract_v105 as contract
from proworksim import software_benchmark_candidates_v054 as candidates
from proworksim import software_benchmark_native_binding_v054 as binding
from proworksim import software_benchmark_model_fifo_v064 as fifo
from proworksim import software_benchmark_public_context_v062 as context
from proworksim.software_benchmark_exact_transport_v057 import ProjectionGuard
from proworksim.storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]


def controller():
    path = ROOT / 'tools/run_ref_controller_v108.py'
    spec = importlib.util.spec_from_file_location('ref_v108_cpu', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BoundaryControls(unittest.TestCase):
    def test_exact_type_and_trusted_sdk_cause_only(self):
        error = remote.RemoteEpisodeBoundary(boundary.NORMAL_REASON)
        self.assertIsNone(boundary.previous(error))
        self.assertIs(boundary.unwrap_normal_boundary(error), error)
        wrapped = ConversationRunError('cpu-control', error)
        wrapped.__cause__ = error
        self.assertIs(boundary.unwrap_normal_boundary(wrapped), error)
        wrapped.__cause__ = RuntimeError(boundary.NORMAL_REASON)
        self.assertIsNone(boundary.unwrap_normal_boundary(wrapped))
        for rejected in (RuntimeError(boundary.NORMAL_REASON),
                         remote.RemoteEpisodeBoundary('episode_closed_or_uncertain_usage'),
                         remote.RemoteEpisodeBoundary('conservative_context_reservation_exhausted')):
            self.assertIsNone(boundary.unwrap_normal_boundary(rejected))

    def test_controller_has_exactly_one_import_change(self):
        old = ast.parse((ROOT / 'tools/run_ref_controller_v105.py').read_text())
        new = ast.parse((ROOT / 'tools/run_ref_controller_v108.py').read_text())
        changes = 0
        for node in ast.walk(new):
            if isinstance(node, ast.ImportFrom) and node.module == 'proworksim.software_benchmark_normal_boundary_v108':
                node.module = 'proworksim.software_benchmark_normal_boundary_v064'
                changes += 1
        self.assertEqual(changes, 1)
        self.assertEqual(ast.dump(old), ast.dump(new))

    def run_controller(self, *, uncertain=False):
        module = controller()
        with tempfile.TemporaryDirectory(prefix='v108-ref-boundary-') as temporary:
            folder = Path(temporary)
            output = folder / 'output'
            output.mkdir()
            (folder / 'testbed').mkdir()
            condition = contract.condition('REF')
            condition_file = folder / 'condition.json'
            condition_file.write_bytes(json_bytes(condition))
            config = {'version': 'v064-private-native-controller-r1', 'slot_id': 'v105:cpu',
                'source_slot_id': 'cpu', 'seed': 1, 'condition_id': condition['condition_id'],
                'execution_arm': 'REF', 'model_key': 'DEEPSEEK',
                'configuration': {**candidates.reference(condition_file), 'path': '/pws/control/condition.json'},
                'output': '/pws/output', 'start': '/pws/control/start.json', 'ready': '/pws/control/actor-ready.json',
                'ref_endpoint': 'cpu-only-no-network', 'model_identity_value': {'thinking': False},
                'diagnostic': False, 'measurement_kind': 'full_verified_comparison',
                'public_task': {'instance_id': 'cpu', 'repo': 'cpu/repo', 'base_commit': 'a'*40,
                                'problem_statement': 'Scripted closure control'},
                'public_context': {'version': 'cpu', 'visible_text': 'Scripted public context', 'visible_facts': {}},
                'public_environment': {'public_python': '/scripted/python'}}
            config_file = folder / 'config.json'
            config_file.write_bytes(json_bytes(config))
            now = time.monotonic()
            start = {'guard_path': '/pws/output/guard.json', 'started': now, 'soft_at': now+100, 'hard_at': now+200}
            (folder / 'start.json').write_bytes(json_bytes(start))
            (folder / 'ready.json').write_text('{}')
            mappings = {'/pws/output': output, '/testbed': folder/'testbed',
                        '/pws/control/start.json': folder/'start.json', '/pws/control/actor-ready.json': folder/'ready.json'}
            events, posts, messages = [], [], []
            class Transport:
                def __init__(self, *_args): pass
                def post(self, route, payload):
                    posts.append(route)
                    if route != '/tokenize':
                        raise AssertionError('No model dispatch is permitted')
                    return {'prompt_tokens': 1024, 'method': 'scripted CPU-only count',
                            'request_sha256': digest(json_bytes(payload['wire']))}
                def close(self): events.append('transport_close')
            class RPC:
                def __init__(self, **_kwargs): self.transcript, self.feedback_events = [], []
                def request(self, *_args, **_kwargs): return {'cpu': True}
                def close(self, **_kwargs): events.append('rpc_close')
            def make_conversation(_config, adapter, _rpc, _output, _limits):
                guard = ProjectionGuard(adapter, None)
                adapter._v057_projection_guard = guard
                class Conversation:
                    state = SimpleNamespace(execution_status='idle')
                    stuck_detector = object()
                    agent = SimpleNamespace(llm=SimpleNamespace(_adapter=guard), condenser=None)
                    def send_message(self, message, **_kwargs): messages.append(message)
                    def run(self):
                        events.append('sdk_run')
                        # Synthetic settled history within this scripted SDK segment.
                        # It is not a claim about any real request or old task.
                        adapter.ledger.actual = 4_999_900
                        adapter.ledger.attempts = adapter.ledger.decisions = 10
                        self.state.execution_status = 'error'
                        if uncertain:
                            adapter.ledger.inflight = {'reservation': 100}
                            raise remote.RemoteEpisodeBoundary(boundary.NORMAL_REASON)
                        tools = [{'type': 'function', 'function': {'name': name,
                            'parameters': {'type': 'object', 'properties': {}}}}
                            for name in sorted(remote.NATIVE_TOOLS)]
                        wire = adapter.request([{'role': 'user', 'content': 'cpu'}], tools)
                        try:
                            adapter.complete(wire)
                        except remote.RemoteEpisodeBoundary as error:
                            raise ConversationRunError('cpu-control', error) from error
                    def close(self): events.append('conversation_close')
                return Conversation()
            with ExitStack() as stack:
                for target, name, value in (
                    (module, 'Path', lambda value: mappings.get(str(value), Path(value))),
                    (module.os, 'getpid', lambda: 1),
                    (module.signal, 'signal', lambda *_a: None),
                    (module, 'install_lifecycle_deadline', lambda _c: None),
                    (module, 'create_conversation', make_conversation),
                    (module, 'feedback_rpc_class', lambda _base: RPC),
                    (candidates, 'checked', lambda _ref: condition_file),
                    (binding, 'NativeToolRPC', RPC), (fifo, 'FifoModelTransport', Transport),
                    (context, 'terminal_initialization_action', lambda _env: {}),
                    (context, 'validate_terminal_initialization', lambda *_a, **_k: {'cpu': True}),
                    (module.sys, 'argv', ['controller', '--config', str(config_file)])):
                    stack.enter_context(patch.object(target, name, value))
                code = module.main()
            return code, json.loads((output/'controller-result.json').read_text()), events, posts, messages

    def test_actual_controller_closes_after_budget_without_another_request(self):
        code, result, events, posts, messages = self.run_controller()
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'closed')
        self.assertEqual(result['terminal_boundary'], {'reason': boundary.NORMAL_REASON, 'known_usage': True})
        self.assertFalse(result['normal_completion'])
        self.assertEqual(result['ledger']['known_actual_tokens'], 4_999_900)
        self.assertEqual(result['ledger']['attempts'], 10)
        self.assertEqual(posts, ['/tokenize'])
        self.assertEqual(events, ['sdk_run', 'conversation_close', 'rpc_close', 'transport_close'])
        self.assertEqual(len(messages), 1)

    def test_actual_controller_does_not_close_uncertain_usage(self):
        code, result, events, posts, messages = self.run_controller(uncertain=True)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'technical_unknown')
        self.assertIn('cannot conceal uncertain usage', result['error']['message'])
        self.assertNotIn('rpc_close', events)
        self.assertEqual(posts, [])
        self.assertEqual(len(messages), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
