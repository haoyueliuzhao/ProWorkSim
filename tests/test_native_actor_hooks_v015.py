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


def test_declared_stop_does_not_silently_crop_real_generated_suffix(tmp_path):
    torch = pytest.importorskip('torch')
    actor = _owner(tmp_path, torch)
    actor.model.generation_config.eos_token_id = 3

    def invalid_generator(self, input_ids, logits_processor, **kwargs):
        ids = input_ids
        for chosen in [3, 4]:
            logits_processor[0](ids, self.lora_logits[None, :])
            ids = torch.cat([ids, torch.tensor([[chosen]], device=ids.device)], dim=1)
        return ids

    actor.model.generate = types.MethodType(invalid_generator, actor.model)
    actor.begin_window('invalid-stop')
    result = actor.complete({'messages': [], 'model': 'fixture', 'temperature': .7, 'max_tokens': 2}, timeout_seconds=10)
    assert result['http_status'] == 503
    assert 'no output cropping' in result['body']['error']['message']
    import json
    record = json.loads(next((actor.output / 'calls').glob('*.json')).read_text())
    assert record['raw_output_ids'] == [3, 4]
    assert len(record['raw_behavior_logprobs']) == 2
    assert actor.actor_steps == 0


def test_member_projection_rejects_saved_raw_suffix_cropping():
    from proworksim.member_views import _tokens
    from test_online_training_v13 import _identity, _response
    response = _response(_identity())
    trace = response['token_trace']
    trace['raw_output_ids'] = trace['output_ids'] + [5]
    trace['raw_behavior_logprobs'] = trace['behavior_logprobs'] + [-3.0]
    tokens, errors = _tokens(response)
    assert tokens is None
    assert errors == ['actual_generated_suffix_was_cropped_or_changed']
