"""Native interface dispatch still retains original output likelihood targets."""

import types

import pytest

from test_online_training_v13 import _owner, _entry, _features


def test_native_hooks_execute_inside_actual_sampling_and_learning(tmp_path):
    torch = pytest.importorskip('torch')
    actor = _owner(tmp_path, torch)
    calls = []

    def prepare(self, request):
        calls.append(('prepare', request['model']))
        return 'native actual input', request['messages'], {'version': 'native-test'}

    def parse(self, raw, request):
        calls.append(('parse', raw, request['model']))
        return {'role': 'assistant', 'content': 'transport decoded'}, None

    actor.prepare_request = types.MethodType(prepare, actor)
    actor.parse_response = types.MethodType(parse, actor)
    original = actor.learning_logprobs

    def logps(self, trace):
        calls.append(('logps', tuple(trace['output_ids'])))
        return original(trace)

    actor.learning_logprobs = types.MethodType(logps, actor)
    actor.begin_window('native-window')
    response = actor.complete({'messages': [{'role': 'user', 'content': 'public'}],
        'model': 'native-test', 'temperature': .7, 'max_tokens': 2}, timeout_seconds=10)
    assert response['http_status'] == 200
    body = response['body']
    assert body['choices'][0]['message']['content'] == 'transport decoded'
    assert body['raw_generated_text'] != 'transport decoded'
    entry = _entry(actor.freeze_identity(), body, reward=1, window=actor.window_id)
    result = actor.update_window([entry], tmp_path / 'update', feature_function=_features)
    assert result['status'] == 'updated'
    assert result['behavior_probability_passed']
    assert result['admitted_output_tokens'] == 2
    assert [c[0] for c in calls[:2]] == ['prepare', 'parse']
    assert all(c[1] == tuple(body['token_trace']['output_ids']) for c in calls[2:])
    assert result['actor_optimizer_steps'] == 1
