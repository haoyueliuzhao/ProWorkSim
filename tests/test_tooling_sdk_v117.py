"""One actual cold SDK no-tool recovery control, all responses scripted."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
SETTINGS = tempfile.TemporaryDirectory(prefix='v117-tooling-settings-')
os.environ['OH_PERSISTENCE_DIR'] = SETTINGS.name


def deny(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto', 'subprocess.Popen'}:
        raise AssertionError('No network or subprocess work in the SDK control')
    if event == 'open' and args and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if path.endswith(('.safetensors', '.gguf')) or path.startswith(('/dev/nvidia', '/dev/dri/')):
            raise AssertionError('No weights or GPU in the SDK control')


sys.addaudithook(deny)

_fixture_spec = importlib.util.spec_from_file_location(
    'v117_tooling_fixture', Path(__file__).with_name('test_tooling_v117.py'))
_fixture_module = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(_fixture_module)
fixture = _fixture_module.fixture
from proworksim import software_benchmark_managed_v117 as managed  # noqa: E402
from proworksim import software_benchmark_tooling_v117 as tooling  # noqa: E402
from proworksim.harness_port import HarnessPort  # noqa: E402
from proworksim.model_policy import CONTROL_TOOLS  # noqa: E402
from proworksim.software_benchmark_alignment_contract_v117 import condition  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import checked  # noqa: E402
from proworksim.software_benchmark_deepseek_adapter_v105 import DeepSeekEpisodeAdapter  # noqa: E402
from proworksim.software_calibration_collector_v051 import close_runtime, run_fragment  # noqa: E402
from proworksim.software_organization_runtime_v047 import DispatchDeadline  # noqa: E402
from proworksim.storage import digest, json_bytes  # noqa: E402


class ToolingSDKControl(unittest.TestCase):
    def test_actual_no_tool_then_one_later_action_keeps_original_charge_and_feedback(self):
        with tempfile.TemporaryDirectory(prefix='v117-tooling-sdk-') as temporary:
            folder = Path(temporary)
            prepared, port, public_calls = fixture(folder)
            deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
            # The callback and runtime share the same deadline, not a longer reset.
            deadline.hard_at = prepared.source_provider.runner.hard_at
            deadline.soft_at = deadline.hard_at - (deadline.hard_seconds - deadline.soft_seconds)
            gateway = HarnessPort(port, 'member_001', project_id=tooling.PROJECT,
                public_sink=lambda *_: None, world_sink=lambda *_: None, harness_sink=lambda *_: None)
            allowed = {row['name'] for row in [*gateway.tools(), *CONTROL_TOOLS]}
            requests = []
            original = {'role': 'assistant', 'content': 'Work is finished.'}
            actions = [('search_repository', {'text': 'first', 'cursor': None}),
                       ('staff_done', {'reason': 'First scripted completion request'}),
                       ('staff_done', {'reason': 'Second scripted completion request'})]

            def post(route, payload):
                wire = payload['wire']
                if route in {'/tokenize', '/tokenize-prefix'}:
                    return {'prompt_tokens': 256, 'request_sha256': digest(json_bytes(wire)),
                        'method': 'scripted CPU count', 'count_only_not_dispatchable': route.endswith('prefix')}
                assert route == '/chat/completions' and wire.get('tools')
                requests.append(copy.deepcopy(wire))
                index = len(requests)
                assert index <= 4
                if index == 1:
                    message, finish = copy.deepcopy(original), 'stop'
                else:
                    name, arguments = actions[index-2]
                    message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                        'id': f'fixture-tool-{index}', 'type': 'function', 'function': {
                            'name': name, 'arguments': json.dumps(arguments)}}]}
                    finish = 'tool_calls'
                return {'id': f'fixture-no-tool-{index}', 'model': 'deepseek-flash',
                    'object': 'chat.completion', 'created': 0,
                    'choices': [{'index': 0, 'finish_reason': finish, 'message': message}],
                    'usage': {'prompt_tokens': 256, 'completion_tokens': 25, 'total_tokens': 281,
                        'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 256}}

            slot = 'v117:fixture__tooling117:'+condition('PROJECT')['condition_id']+':117'
            adapter = DeepSeekEpisodeAdapter(post=post, arm='PROJECT', slot_id=slot,
                condition_id=condition('PROJECT')['condition_id'], token_budget=5_000_000,
                folder=folder/'ledger', allowed_tool_names=allowed,
                soft_at=deadline.soft_at, hard_at=deadline.hard_at)
            owner = managed.ProjectOwner(adapter, window_id=slot, identity={'policy_version': 'CPU fixture'})
            runtime, _, _ = managed.build_runtime(owner, prepared, folder/'runtime', deadline=deadline,
                public_initial_message='Synthetic no-tool feedback control, no external services.')
            worker = runtime.policies['member_001']
            initial_source = port.observe()['workspace_reference']
            try:
                def after(outcome):
                    if len(requests) == 1:
                        self.assertEqual(outcome['status'], 'model_format_feedback')
                        self.assertIsNone(worker._done)
                        self.assertEqual(runtime.actions, 0)
                        self.assertEqual(adapter.ledger.actual, 281)
                        self.assertEqual(worker.meter['budget_accounted_tokens'], 281)
                        self.assertEqual(adapter.ledger.attempts, 1)
                result = run_fragment(prepared, runtime, on_opportunity=after)
                self.assertIsNone(result['execution_integrity_failure'])
                self.assertEqual(len(requests), 4)
                self.assertIn(tooling.NO_TOOL_RECOVERY, json.dumps(requests[1]['messages']))
                saved = json.loads(checked(adapter.ledger.calls[0]['response']).read_bytes())
                self.assertEqual(saved['choices'][0]['message'], original)
                self.assertEqual(adapter.ledger.actual, 1124)
                budget = runtime.team_budget.snapshot()
                self.assertEqual(worker.meter['budget_accounted_tokens'], budget['charged_tokens'])
                self.assertEqual(budget['charged_tokens'], adapter.ledger.actual)
                self.assertEqual(adapter.ledger.decisions, 4)
                self.assertEqual(adapter.ledger.attempts, 4)
                self.assertEqual(runtime.actions, 1)
                self.assertEqual(set(worker._nullable_cursor_v117['tools']), tooling.CURSOR_TOOLS)
                second = json.loads(checked(adapter.ledger.calls[1]['response']).read_bytes())
                self.assertIsNone(json.loads(second['choices'][0]['message']['tool_calls'][0]['function']['arguments'])['cursor'])
                self.assertEqual(runtime.finish_review_policy_v117.used, 1)
                self.assertEqual(len(worker._rejected_history_v117['receipts']), 1)
                self.assertEqual(port.observe()['workspace_reference'], initial_source)
                self.assertEqual(public_calls, [])
                self.assertEqual(port.observe()['delivery_count'], 0)
            finally:
                close_runtime(runtime)


if __name__ == '__main__':
    unittest.main(verbosity=2)
