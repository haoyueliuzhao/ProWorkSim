import copy
from contextlib import nullcontext
from types import SimpleNamespace

from proworksim.candidate_runtime_v0151 import candidate_profile, inspect_chat_stop
from scripts.candidate_preflight_v0151 import run_preflight


def body(ids):
    return {'choices': [{'message': {'role': 'assistant', 'content': 'mock fixture'}}],
        'token_trace': {'input_ids': [1], 'output_ids': list(ids),
            'raw_output_ids': list(ids), 'behavior_logprobs': [-1.0]*len(ids),
            'raw_behavior_logprobs': [-1.0]*len(ids)}}


def test_first_native_terminator_must_end_actual_generation_not_just_crop():
    profile = candidate_profile('qwen3.5-9b')
    assert inspect_chat_stop(body([2, 248046]), profile)['passed']
    crossed = body([2, 248046, 3, 248044])
    assert not inspect_chat_stop(crossed, profile)['passed']
    cropped = copy.deepcopy(crossed)
    cropped['token_trace']['output_ids'] = [2, 248046]
    cropped['token_trace']['behavior_logprobs'] = [-1.0, -1.0]
    assert not inspect_chat_stop(cropped, profile)['passed']
    missing = body([2, 248046])
    del missing['token_trace']['raw_output_ids']
    assert not inspect_chat_stop(missing, profile)['passed']


class MockOwner:
    inference_profile = candidate_profile('qwen3.5-9b')
    actor_steps = critic_steps = 0
    recipe = {}
    torch = SimpleNamespace(no_grad=nullcontext)

    def begin_window(self, window):
        pass

    def complete(self, request, timeout_seconds):
        return {'http_status': 200, 'body': body([2, 248046])}

    def finish_evaluation(self, entries, output):
        pass

    def learning_logprobs(self, trace):
        raise RuntimeError('mock numeric failure after valid chat stop')

    def save_checkpoint(self, output):
        return {'serialized_reload_exact': True, 'scope': 'mock only'}

    def restore_checkpoint(self, output):
        pass


def args(tmp_path):
    return SimpleNamespace(output=tmp_path/'new-preflight', candidate='qwen3.5-9b',
        dtype='float32', devices=1, model_path='mock', manifest='mock', replay_call=[])


def test_valid_chat_numeric_failure_still_admits_only_inference(tmp_path):
    report = run_preflight(args(tmp_path), actor_factory=lambda *a, **kw: MockOwner())
    assert report['inference_ready'] and not report['training_ready']
    assert report['native_chat_end_observed'] and report['exit_code'] == 0


def test_raw_chat_overrun_never_admits_inference_or_training(tmp_path):
    class Overrun(MockOwner):
        def complete(self, request, timeout_seconds):
            return {'http_status': 200, 'body': body([2, 248046, 3, 248044])}
    report = run_preflight(args(tmp_path), actor_factory=lambda *a, **kw: Overrun())
    assert report['generation_observed'] and not report['inference_ready']
    assert not report['training_ready'] and report['exit_code'] == 1
    assert report['probability_checks'] == []
