"""Bounded native tool calibration; no work score and no optimizer update."""
import argparse
import json
import math
import time
from pathlib import Path

from proworksim.candidate_runtime_v015 import CandidateActor, candidate_profile
from proworksim.online_training import probability_check
from proworksim.storage import atomic_write, json_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-path', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--devices', type=int, default=1)
    parser.add_argument('--dtype', choices=['float32', 'bfloat16'], default='float32')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    profile = candidate_profile(args.candidate, dtype=args.dtype, devices=args.devices)
    recipe = {'seed': 2026092817, 'max_length': 16384, 'max_output_tokens': 2048,
              'diagnostic_max_groups': 0, 'post_update_max_decisions': 0,
              'max_rss_bytes': 192 * 1024**3}
    owner = CandidateActor.from_candidate(args.model_path, manifest=args.manifest,
        output=args.output / 'owner', profile=profile, recipe=recipe)
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
    calls = []
    tool_results = []
    for decision in range(2):
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
    owner.finish_evaluation([], args.output / 'closed-interface-window')
    checks = []
    for call in calls:
        if call['http_status'] != 200:
            continue
        trace = call['body']['token_trace']
        with owner.torch.no_grad():
            actual = owner.learning_logprobs(trace).cpu().tolist()
        checks.append(probability_check(actual, trace['behavior_logprobs'], owner.recipe))
    backward = {'executed': False, 'optimizer_steps': 0}
    if checks and all(c['passed'] for c in checks):
        trace = next(c['body']['token_trace'] for c in calls if c['http_status'] == 200)
        owner.actor_optimizer.zero_grad(set_to_none=True)
        values = owner.learning_logprobs(trace)
        loss = -values.mean()
        loss.backward()
        squares = sum(float(p.grad.detach().float().square().sum().cpu())
                      for p in owner.actor_parameters.values() if p.grad is not None)
        backward = {'executed': True, 'optimizer_steps': 0,
                    'diagnostic_loss_only': True, 'gradient_norm': math.sqrt(squares),
                    'gradient_finite_nonzero': math.isfinite(squares) and squares > 0}
        owner.actor_optimizer.zero_grad(set_to_none=True)
    checkpoint = owner.save_checkpoint(args.output / 'unchanged-checkpoint')
    owner.restore_checkpoint(args.output / 'unchanged-checkpoint')
    report = {'version': 'candidate-preflight-v0.15', 'scope':
        'Public interface and actual-token numerical calibration, not work ability or RL benefit',
        'candidate': args.candidate, 'profile': owner.inference_profile,
        'calls': len(calls), 'statuses': [c['http_status'] for c in calls],
        'tool_results': tool_results, 'probability_checks': checks, 'backward': backward,
        'checkpoint': checkpoint, 'actor_steps': owner.actor_steps, 'critic_steps': owner.critic_steps,
        'elapsed_seconds': time.time() - started}
    atomic_write(args.output / 'report.json', json_bytes(report))
    print(json.dumps({'candidate': args.candidate, 'calls': len(calls),
        'statuses': report['statuses'], 'probability_passed': bool(checks) and all(c['passed'] for c in checks),
        'backward': backward, 'elapsed_seconds': report['elapsed_seconds']}), flush=True)


if __name__ == '__main__':
    main()
