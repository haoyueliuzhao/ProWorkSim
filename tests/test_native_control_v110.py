"""Actual cold SDK control of the declared native history-wrapper chain."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
import uuid

os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
os.environ['OPENHANDS_SUPPRESS_BANNER'] = '1'
_SETTINGS = tempfile.TemporaryDirectory(prefix='v110-native-settings-')
os.environ['OH_PERSISTENCE_DIR'] = _SETTINGS.name


def prohibit_external_work(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
        raise AssertionError('No network in native binding SDK control')
    if event == 'open' and args and isinstance(args[0], (str, bytes)):
        name = os.fsdecode(args[0])
        if name.endswith(('.safetensors', '.gguf')) or 'pytorch_model' in name:
            raise AssertionError('No model weights')
        if name.startswith(('/dev/nvidia', '/dev/dri/')):
            raise AssertionError('No GPU')


sys.addaudithook(prohibit_external_work)

from openhands.sdk import Conversation  # noqa: E402
from proworksim.software_benchmark_alignment_contract_v110 import condition, validate_condition  # noqa: E402
from proworksim.software_benchmark_deepseek_adapter_v105 import (  # noqa: E402
    DeepSeekEpisodeAdapter, build_native_llm, NATIVE_TOOLS,
)
from proworksim.software_benchmark_exact_transport_v057 import ProjectionGuard  # noqa: E402
from proworksim.software_benchmark_finish_review_v110 import FINISH_REVIEW  # noqa: E402
from proworksim.software_benchmark_history_v110 import bind_ref_conversation, bind_ref_history  # noqa: E402
from proworksim.software_benchmark_native_control_v110 import (  # noqa: E402
    run_controlled_conversation, validate_ref_binding,
)
from proworksim.software_benchmark_native_binding_v054 import build_isolated_agent  # noqa: E402
from proworksim.software_benchmark_sdk_bundle_v066 import NATIVE_SCHEMA_SOURCE  # noqa: E402
from proworksim.storage import digest, json_bytes  # noqa: E402


@contextmanager
def fixture(*, bind_source=True, fail_history_after_response=False):
    with tempfile.TemporaryDirectory(prefix='v110-native-control-') as temporary:
        folder = Path(temporary)
        os.environ['OH_PERSISTENCE_DIR'] = str(folder/'empty-settings')
        requests, holder = [], {}
        def post(route, payload):
            wire = payload['wire']
            if route in {'/tokenize', '/tokenize-prefix'}:
                return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(wire)),
                        'method': 'scripted local count', 'count_only_not_dispatchable': route.endswith('prefix')}
            assert route == '/chat/completions'
            requests.append(wire)
            assert len(requests) <= 2
            if fail_history_after_response:
                holder['conversation'].agent.llm._adapter.trace.failure = RuntimeError('scripted history fault')
            number = len(requests)
            return {'id': f'cpu-native-review-{number}', 'object': 'chat.completion', 'created': 0,
                'model': 'deepseek-flash', 'choices': [{'index': 0, 'finish_reason': 'tool_calls',
                    'message': {'role': 'assistant', 'content': None, 'tool_calls': [{
                        'id': f'cpu-finish-{number}', 'type': 'function', 'function': {
                            'name': 'finish', 'arguments': json.dumps({'message': 'Scripted finish', 'security_risk': 'LOW'})}}]}}],
                'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                    'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
        adapter = DeepSeekEpisodeAdapter(post=post, arm='REF', slot_id='v110:native-control',
            condition_id='cpu', token_budget=5_000_000, folder=folder/'ledger', allowed_tool_names=NATIVE_TOOLS)
        llm = build_native_llm(adapter, normalization_folder=folder/'response-projections')
        condenser = bind_ref_history(llm, directory=folder/'history')
        rpc = SimpleNamespace(_bound=False, ready=json.loads(NATIVE_SCHEMA_SOURCE.read_bytes()),
            session_id='v110_native_control_' + uuid.uuid4().hex,
            request=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError('No commands or file tools in this control')))
        agent = build_isolated_agent(llm, rpc=rpc).model_copy(update={'condenser': condenser})
        workspace = folder/'workspace'
        workspace.mkdir()
        conversation = Conversation(agent=agent, workspace=workspace,
            persistence_dir=folder/'conversation', plugins=[], stuck_detection=True,
            max_iteration_per_run=512, visualizer=None, delete_on_close=False)
        holder['conversation'] = conversation
        try:
            if bind_source:
                bind_ref_conversation(conversation)
            now = time.monotonic()
            started = {'started': now, 'soft_at': now+21600, 'hard_at': now+23400}
            limits = validate_condition(condition('REF'))
            conversation.send_message('Only use the scripted finish fixture.')
            yield conversation, adapter, started, limits, requests
        finally:
            conversation.close()


class NativeBindingControls(unittest.TestCase):
    def test_actual_sdk_uses_shared_guard_and_one_final_review(self):
        with fixture() as (conversation, adapter, started, limits, requests):
            result = run_controlled_conversation(conversation, adapter=adapter, started=started, limits=limits)
            self.assertEqual(result['finish_reviews'], 1)
            self.assertEqual(result['stuck_corrections'], 0)
            self.assertEqual(result['final_sdk_status'], 'finished')
            self.assertEqual(adapter.ledger.attempts, 2)
            self.assertEqual(adapter.ledger.decisions, 2)
            self.assertEqual(adapter.ledger.actual, 562)
            self.assertEqual(sum(message.get('content') == FINISH_REVIEW for message in requests[1]['messages']), 1)
            self.assertIs(conversation.agent.llm._adapter.delegate, adapter._v057_projection_guard)
            self.assertIs(conversation.agent.condenser.llm._adapter, conversation.agent.llm._adapter)

    def test_missing_source_binding_is_rejected_before_any_response(self):
        with fixture(bind_source=False) as (conversation, adapter, started, limits, requests):
            with self.assertRaises(ValueError):
                run_controlled_conversation(conversation, adapter=adapter, started=started, limits=limits)
            self.assertEqual(requests, [])

    def test_wrong_or_changed_real_wrapper_chain_is_rejected(self):
        with fixture() as (conversation, adapter, _started, _limits, requests):
            binding = validate_ref_binding(conversation, adapter)
            guard = conversation.agent.llm._adapter
            original_projection = guard.delegate
            guard.delegate = ProjectionGuard(adapter, None)
            with self.assertRaises(ValueError):
                validate_ref_binding(conversation, adapter, expected=binding)
            guard.delegate = original_projection
            original_summary_llm = conversation.agent.condenser.llm
            conversation.agent.condenser.llm = original_summary_llm.model_copy()
            with self.assertRaises(RuntimeError):
                validate_ref_binding(conversation, adapter, expected=binding)
            conversation.agent.condenser.llm = original_summary_llm
            original_provider = guard.trace.event_provider
            guard.trace.event_provider = lambda: []
            with self.assertRaises((RuntimeError, ValueError)):
                validate_ref_binding(conversation, adapter, expected=binding)
            guard.trace.event_provider = original_provider
            self.assertEqual(requests, [])

    def test_sticky_history_failure_cannot_gain_a_review(self):
        with fixture(fail_history_after_response=True) as (conversation, adapter, started, limits, requests):
            with self.assertRaisesRegex(RuntimeError, 'scripted history fault'):
                run_controlled_conversation(conversation, adapter=adapter, started=started, limits=limits)
            self.assertEqual(len(requests), 1)
            self.assertEqual(adapter.ledger.attempts, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
