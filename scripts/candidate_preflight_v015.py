"""Bounded native tool calibration; no work score and no optimizer update."""
import argparse
import json
import math
import time
import traceback
from pathlib import Path

from proworksim.candidate_runtime_v015 import CandidateActor, candidate_profile
from proworksim.online_training import probability_check
from proworksim.storage import atomic_write, json_bytes


def run_preflight(args, *, actor_factory=None):
    """Separate actual inference admission from training integration outcomes."""
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    owner = None
    calls, tool_results, checks, errors = [], [], [], []
    backward = {'executed': False, 'optimizer_steps': 0}
    checkpoint = None
    checkpoint_restored = False
    closed = False
    stage = 'load'
    report = {'version': 'candidate-preflight-v0.15', 'scope':
        'Public interface and actual-token numerical calibration, not work ability or RL benefit',
        'candidate': args.candidate, 'inference_ready': False, 'training_ready': False}

    def record_error(failed_stage, error):
        detail = traceback.format_exc()
        errors.append({'stage': failed_stage, 'type': type(error).__name__, 'message': str(error)})
        with (args.output / 'calibration-errors.log').open('a') as stream:
            stream.write(f'\nSTAGE: {failed_stage}\n{detail}')

    try:
        profile = candidate_profile(args.candidate, dtype=args.dtype, devices=args.devices)
        recipe = {'seed': 2026092817, 'max_length': 16384, 'max_output_tokens': 2048,
                  'diagnostic_max_groups': 0, 'post_update_max_decisions': 0,
                  'max_rss_bytes': 192 * 1024**3}
        factory = actor_factory or CandidateActor.from_candidate
        owner = factory(args.model_path, manifest=args.manifest,
            output=args.output / 'owner', profile=profile, recipe=recipe)
        report['profile'] = owner.inference_profile
        stage = 'interface_collection'
        tools = [{"type": "function", "function": {"name": "read_public_note",
            "description": "Read the actual public calibration note.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                           "required": ["path"]}}},
            {"type": "function", "function": {"name": "record_fact",
            "description": "Record the note code and integer revision after reading it.",
            "parameters": {"type": "object", "properties": {"code": {"type": "string"},
                           "revision": {"type": "integer"}}, "required": ["code", "revision"]}}}]
        note = args.output / 'public-note.json'
        atomic_write(note, json_bytes({'code': 'CALIBRATION-BLUE', 'revision': 7}))
        request = {'model': args.candidate, 'temperature': 0.7, 'max_tokens': 2048,
            'tools': tools, 'messages': [{'role': 'user', 'content':
            'Read public-note.json with read_public_note, then record its actual code and revision with record_fact.'}]}
        owner.begin_window('public-interface-calibration')
        for _ in range(2):
            response = owner.complete(request, timeout_seconds=600)
            calls.append(response)
            if response['http_status'] != 200:
                break
            message = response['body']['choices'][0]['message']
            request['messages'].append(message)
            native_calls = message.get('tool_calls', [])
            if len(native_calls) != 1:
                break
            call = native_calls[0]
            arguments = json.loads(call['function']['arguments'])
            if call['function']['name'] == 'read_public_note' and arguments == {'path': 'public-note.json'}:
                result = json.loads(note.read_text())
            elif call['function']['name'] == 'record_fact':
                result = {'recorded': arguments,
                          'matches_public_note': arguments == json.loads(note.read_text())}
            else:
                result = {'error': 'Unknown tool or invalid public calibration arguments'}
            tool_results.append(result)
            request['messages'].append({'role': 'tool', 'tool_call_id': call['id'],
                                        'content': json.dumps(result)})
        stage = 'close_interface_window'
        owner.finish_evaluation([], args.output / 'closed-interface-window')
        closed = True
    except Exception as error:
        record_error(stage, error)

    real_traces = [call['body']['token_trace'] for call in calls
                   if isinstance(call, dict) and call.get('http_status') == 200
                   and isinstance(call.get('body'), dict)
                   and isinstance(call['body'].get('token_trace'), dict)
                   and call['body']['token_trace'].get('input_ids')
                   and call['body']['token_trace'].get('output_ids')]
    report['inference_ready'] = bool(real_traces)
    if owner is not None and closed and real_traces:
        try:
            for index, trace in enumerate(real_traces):
                stage = f'probability_recomputation_{index}'
                with owner.torch.no_grad():
                    actual = owner.learning_logprobs(trace).cpu().tolist()
                checks.append(probability_check(actual, trace['behavior_logprobs'], owner.recipe))
        except Exception as error:
            record_error(stage, error)
        probability_passed = len(checks) == len(real_traces) and all(c['passed'] for c in checks)
        if probability_passed:
            try:
                stage = 'differentiable_recomputation_and_backward'
                owner.actor_optimizer.zero_grad(set_to_none=True)
                values = owner.learning_logprobs(real_traces[0])
                gradient_check = probability_check(values.detach().cpu().tolist(),
                    real_traces[0]['behavior_logprobs'], owner.recipe)
                backward['probability_check'] = gradient_check
                if gradient_check['passed']:
                    loss = -values.mean()
                    backward['executed'] = True
                    loss.backward()
                    squares = sum(float(p.grad.detach().float().square().sum().cpu())
                                  for p in owner.actor_parameters.values() if p.grad is not None)
                    finite = math.isfinite(squares) and squares >= 0
                    backward.update(diagnostic_loss_only=True,
                                    gradient_norm=math.sqrt(squares) if finite else None,
                                    gradient_finite_nonzero=finite and squares > 0)
                else:
                    backward['skip_reason'] = 'Differentiable probability path failed the unchanged gate'
            except Exception as error:
                record_error(stage, error)
            finally:
                try:
                    owner.actor_optimizer.zero_grad(set_to_none=True)
                except Exception as error:
                    record_error('clear_diagnostic_gradients', error)
        else:
            backward['skip_reason'] = 'Probability calibration did not fully pass; no backward attempted'
        try:
            stage = 'checkpoint_save'
            checkpoint = owner.save_checkpoint(args.output / 'unchanged-checkpoint')
            stage = 'checkpoint_restore'
            owner.restore_checkpoint(args.output / 'unchanged-checkpoint')
            checkpoint_restored = True
        except Exception as error:
            record_error(stage, error)
    else:
        probability_passed = False
        backward['skip_reason'] = 'No completed interface boundary with actual generation'

    report.update(calls=len(calls), statuses=[c.get('http_status') if isinstance(c, dict) else None for c in calls],
        actual_nonempty_traces=len(real_traces), tool_results=tool_results,
        probability_checks=checks, probability_calibration_passed=probability_passed,
        backward=backward, checkpoint=checkpoint, checkpoint_restored=checkpoint_restored,
        interface_window_closed=closed, errors=errors,
        actor_steps=getattr(owner, 'actor_steps', None), critic_steps=getattr(owner, 'critic_steps', None),
        elapsed_seconds=time.time()-started)
    report['training_ready'] = bool(report['inference_ready'] and closed and not errors
        and len(real_traces) == len(calls) and probability_passed
        and backward.get('gradient_finite_nonzero') and checkpoint_restored
        and checkpoint and checkpoint.get('serialized_reload_exact'))
    report['status'] = ('measured_training_ready' if report['training_ready'] else
                        'measured_training_not_ready' if report['inference_ready'] else
                        'inference_not_ready')
    report['exit_code'] = 0 if report['inference_ready'] else 1
    atomic_write(args.output / 'report.json', json_bytes(report))
    print(json.dumps({k: report[k] for k in ['candidate', 'status', 'inference_ready',
        'training_ready', 'calls', 'statuses', 'errors', 'elapsed_seconds']}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-path', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--devices', type=int, default=1)
    parser.add_argument('--dtype', choices=['float32', 'bfloat16'], default='float32')
    parser.add_argument('--output', type=Path, required=True)
    report = run_preflight(parser.parse_args())
    raise SystemExit(report['exit_code'])


if __name__ == '__main__':
    main()
