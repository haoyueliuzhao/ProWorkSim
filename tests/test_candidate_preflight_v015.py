import json
from contextlib import nullcontext
from types import SimpleNamespace

from scripts.candidate_preflight_v015 import run_preflight


def arguments(tmp_path):
    return SimpleNamespace(output=tmp_path/'preflight', candidate='qwen3.5-9b',
        dtype='float32', devices=1, model_path='mock-not-real-weights', manifest='mock')


class NumericFailureOwner:
    inference_profile = {'scope': 'mock only'}
    actor_steps = critic_steps = 0
    recipe = {}
    torch = SimpleNamespace(no_grad=nullcontext)

    def begin_window(self, window):
        pass

    def complete(self, request, timeout_seconds):
        return {'http_status': 200, 'body': {'choices': [{'message': {
            'role': 'assistant', 'content': 'mock fixture'}}], 'token_trace': {
            'input_ids': [1], 'output_ids': [2], 'behavior_logprobs': [-1.0]}}}

    def finish_evaluation(self, entries, output):
        pass

    def learning_logprobs(self, trace):
        raise RuntimeError('mock numeric route unavailable')

    def save_checkpoint(self, output):
        return {'serialized_reload_exact': True, 'scope': 'mock only'}

    def restore_checkpoint(self, output):
        pass


def test_numeric_exception_preserves_inference_and_denies_training(tmp_path):
    args = arguments(tmp_path)
    report = run_preflight(args, actor_factory=lambda *a, **kw: NumericFailureOwner())
    assert report['inference_ready'] and not report['training_ready']
    assert report['exit_code'] == 0 and report['checkpoint_restored']
    assert report['errors'][0]['stage'] == 'probability_recomputation_0'
    assert 'mock numeric route unavailable' in (args.output/'calibration-errors.log').read_text()
    assert json.loads((args.output/'report.json').read_text()) == report


def test_load_exception_always_writes_report_and_denies_inference(tmp_path):
    def unavailable(*args, **kwargs):
        raise RuntimeError('mock weights unavailable')
    args = arguments(tmp_path)
    report = run_preflight(args, actor_factory=unavailable)
    assert not report['inference_ready'] and not report['training_ready']
    assert report['exit_code'] == 1 and report['calls'] == 0
    assert report['errors'][0]['stage'] == 'load'
    assert json.loads((args.output/'report.json').read_text()) == report
