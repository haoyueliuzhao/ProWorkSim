"""Cold real SDK regression with recorded bad arguments and scripted responses."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
import uuid

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
SETTINGS = tempfile.TemporaryDirectory(prefix='v126-rejected-settings-')
os.environ['OH_PERSISTENCE_DIR'] = SETTINGS.name


def deny(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto', 'subprocess.Popen'}:
        raise AssertionError('This SDK regression cannot dispatch network or subprocess work')
    if event == 'open' and args and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if path.endswith(('.safetensors', '.gguf')) or path.startswith(('/dev/nvidia', '/dev/dri/')):
            raise AssertionError('No weights or GPU in the CPU SDK control')


sys.addaudithook(deny)

from proworksim.software_benchmark_alignment_contract_v110 import condition, validate_condition  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import checked  # noqa: E402
from proworksim.software_benchmark_deepseek_adapter_v105 import DeepSeekEpisodeAdapter, NATIVE_TOOLS  # noqa: E402
from proworksim.software_benchmark_native_control_v110 import run_controlled_conversation  # noqa: E402
from proworksim.software_benchmark_sdk_bundle_v066 import NATIVE_SCHEMA_SOURCE  # noqa: E402
from proworksim.storage import digest, json_bytes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_controller_spec = importlib.util.spec_from_file_location('actual_ref_controller_v126',
    ROOT/'tools/run_ref_controller_v126.py')
_controller = importlib.util.module_from_spec(_controller_spec)
_controller_spec.loader.exec_module(_controller)
create_ref_conversation = _controller.create_conversation


class RejectedHistorySDKControls(unittest.TestCase):
    def exercise(self, slot):
        old = ROOT/f'runs/software-benchmark-v111/aligned-interface-r1/episodes/{slot}/controller-output'
        ledger = json.loads((old/'ref-ledger/ledger.json').read_bytes())
        original = json.loads((old/'ref-ledger'/f"response-{ledger['attempts']:04d}.json").read_bytes())
        bad_arguments = original['choices'][0]['message']['tool_calls'][0]['function']['arguments']
        with self.assertRaises(json.JSONDecodeError):
            json.loads(bad_arguments)
        with tempfile.TemporaryDirectory(prefix='v126-rejected-history-') as temporary:
            folder = Path(temporary)
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
                if index == 1:
                    message = copy.deepcopy(original['choices'][0]['message'])
                else:
                    message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                        'id': f'fixture-finish-{index}', 'type': 'function', 'function': {
                            'name': 'finish', 'arguments': json.dumps({'message': 'CPU scripted finish', 'security_risk': 'LOW'})}}]}
                return {'id': original['id'] if index == 1 else f'fixture-response-{index}',
                    'object': 'chat.completion', 'created': 0, 'model': 'deepseek-flash',
                    'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': message}],
                    'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                        'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}
            adapter = DeepSeekEpisodeAdapter(post=post, arm='REF', slot_id=f'v126:fixture:{slot}',
                condition_id='fixture', token_budget=5_000_000, folder=folder/'ledger', allowed_tool_names=NATIVE_TOOLS)
            rpc = SimpleNamespace(_bound=False, ready=json.loads(NATIVE_SCHEMA_SOURCE.read_bytes()),
                session_id='v126_rejected_'+uuid.uuid4().hex,
                request=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError('The malformed tool must never execute')))
            limits = validate_condition(condition('REF'))
            workspace = folder/'workspace'
            workspace.mkdir()
            conversation = create_ref_conversation({}, adapter, rpc, folder/'output', limits, workspace=workspace)
            try:
                now = time.monotonic()
                started = {'started': now, 'soft_at': now+21600, 'hard_at': now+23400}
                conversation.send_message('Synthetic control: return one scripted error and then finish.')
                result = run_controlled_conversation(conversation, adapter=adapter, started=started, limits=limits)
                self.assertEqual(result['final_sdk_status'], 'finished')
                self.assertEqual(result['finish_reviews'], 1)
                self.assertEqual(adapter.ledger.attempts, 3)
                self.assertEqual(adapter.ledger.decisions, 3)
                self.assertEqual(adapter.ledger.actual, 843)
                self.assertEqual(len(adapter.history.receipts), 1)
                saved = json.loads(checked(adapter.ledger.calls[0]['response']).read_bytes())
                self.assertEqual(saved['choices'][0]['message']['tool_calls'][0]['function']['arguments'], bad_arguments)
                retained = [call for message in requests[1]['messages'] for call in message.get('tool_calls', [])
                            if call['id'] == original['choices'][0]['message']['tool_calls'][0]['id']]
                self.assertEqual(len(retained), 1)
                marker = json.loads(retained[0]['function']['arguments'])
                self.assertIs(marker['_openhands_malformed_tool_call'], True)
                prefix = [{'role': 'assistant', 'content': None, 'tool_calls': retained}]
                self.assertEqual(adapter.history.restore_prefix(prefix)[0]['tool_calls'], retained)
                self.assertTrue(any(message.get('role') == 'tool' and message.get('content') == marker['error']
                                    for message in requests[1]['messages']))
                # A caller cannot forge the SDK sentinel or bind another source.
                changed = copy.deepcopy(requests[1]['messages'])
                for message in changed:
                    for call in message.get('tool_calls', []):
                        if call['id'] == retained[0]['id']:
                            call['function']['arguments'] = json.dumps({**marker, 'error': 'invented permission'})
                with self.assertRaises(ValueError):
                    adapter.history.restore(changed, thinking=False)
                with self.assertRaises(ValueError):
                    adapter.history.bind_conversation(conversation)
                self.assertEqual(adapter.ledger.attempts, 3)
            finally:
                conversation.close()

    def test_actual_invalid_control_character_remains_an_unexecuted_sdk_error(self):
        self.exercise(7244)

    def test_actual_truncated_arguments_remain_an_unexecuted_sdk_error(self):
        self.exercise(7251)


if __name__ == '__main__':
    unittest.main(verbosity=2)
