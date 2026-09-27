"""Prepare the fixed external D2 variant, or run explicit CPU transport controls.

Real inference is run by run_checkpoint(existing_owner, assets=..., output=...,
checkpoint_label=...) in the resident stage worker; this CLI never loads a model.
"""
import argparse
import copy
import json
from pathlib import Path

from proworksim.online_training import recipe_config
from proworksim.storage import json_bytes
from proworksim.teambench_model_v023 import VERSION, SEEDS, generate, run_episode, write
from scripts.teambench_admission_v021 import D2_WITNESS

# Programmatic mechanism control used only on old development seed 0. The
# source is never offered to any real model or added to any training record.
CHECKER = D2_WITNESS[:D2_WITNESS.index("os.makedirs('data/output'")] + '''
import json
print(json.dumps({'columns':columns,'rows':[[row[col] for col in columns] for row in clean]}))
'''


class ExplicitFakeOwner:
    recipe = recipe_config({'credit_assignment': 'terminal_mc', 'max_output_tokens': 2048, 'max_length': 16384, 'temperature': .7})

    def __init__(self, variant):
        self.variant, self.transport = variant, self
        self.calls, self.requests = {}, []

    def freeze_identity(self):
        return {'policy_version': 'EXPLICIT_CPU_FIXTURE_NOT_REAL_MODEL'}

    def complete(self, request, *, timeout_seconds):
        self.requests.append(copy.deepcopy(request))
        obs = json.loads(request['messages'][-1]['content'])['observation']
        role = obs['actor_id']
        step = self.calls.get(role, 0)
        self.calls[role] = step + 1
        if role == 'executor':
            code = D2_WITNESS if self.variant != 'wrong_pipeline' else D2_WITNESS.replace("row[department] = 'review_needed'", 'pass')
            actions = [('read_material', {'material': 'instructions'}), ('read_material', {'material': 'code'}),
                       ('read_material', {'material': 'input'}), ('write_pipeline', {'source': code}),
                       ('run_pipeline', {}), ('read_material', {'material': 'output'}), ('submit', {})]
        else:
            attest = {'verdict': 'fail' if self.variant == 'wrong_pipeline' else 'pass',
                      'reason': 'Explicit CPU fake fixture checks fixed contents',
                      'submission_id': obs['fixed_submission']['submission_id'],
                      'verification_id': '' if self.variant == 'forged_pass' else 'check-0'}
            if self.variant == 'forged_pass':
                actions = [('attest', attest)]
            else:
                checker = 'print("pass")' if self.variant == 'string_only' else CHECKER
                actions = [('read_material', {'material': name}) for name in ('spec', 'code', 'input', 'output')]
                actions += [('verify_submission', {'source': checker}), ('attest', attest)]
        name, args = actions[step]
        body = {'id': f'fake-{role}-{step}', 'model': 'explicit-fake-cpu',
                'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                    'role': 'assistant', 'content': 'EXPLICIT_FAKE_CPU_CONTROL',
                    'tool_calls': [{'id': f'fake-call-{role}-{step}', 'type': 'function',
                                    'function': {'name': name, 'arguments': json.dumps(args)}}]}}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
        return {'http_status': 200, 'body': body, 'raw_body': json_bytes(body).decode(), 'response_headers': {}}


def cpu_controls(output, development_assets):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'declaration.json', {'version': VERSION, 'control_seed': 0,
          'variants': ['correct', 'forged_pass', 'string_only', 'wrong_pipeline'],
          'model_calls': 0, 'model_episodes': 0, 'api_calls': 0, 'gpu_seconds': 0,
          'fixtures': 'explicit_fake_transport_only_not_training_or_evaluation'})
    rows = []
    for variant in ('correct', 'forged_pass', 'string_only', 'wrong_pipeline'):
        owner = ExplicitFakeOwner(variant)
        result = run_episode(owner, development_assets / 'generated/seed0',
                             development_assets / 'reviewed-source/tasks/D2_data_quality/grade.sh',
                             output / variant, seed=0)
        r = result['responsibility']
        expected = (result['grader']['score']['pass'] is (variant != 'wrong_pipeline')
                    and r['full_joint_responsibility'] is (variant == 'correct')
                    and r['supported_attestation'] is (variant in {'correct', 'wrong_pipeline'}))
        rows.append({'variant': variant, 'matches_declared_expectation': expected,
                     'fake_transport_calls': len(owner.requests), 'result': result})
    report = {'version': VERSION, 'status': 'complete', 'all_declared_controls_passed': all(x['matches_declared_expectation'] for x in rows),
              'controls': rows, 'model_calls': 0, 'model_episodes': 0, 'api_calls': 0, 'gpu_seconds': 0,
              'held_out_model_seeds': list(SEEDS), 'held_out_model_seeds_used_in_controls': False}
    write(output / 'report.json', report)
    return report


def measure_token_lengths(output, model):
    """Tokenizer-only existence check on old seed 0; never a model trajectory."""
    from transformers import AutoTokenizer
    from proworksim.candidate_runtime_v015 import prepare_candidate_prompt
    from proworksim.candidate_runtime_v017 import parse_candidate_generated
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    rows = []
    for role in ('executor', 'verifier'):
        events = [json.loads(path.read_text()) for path in (output / 'correct/model-calls' / role).glob('*.json')]
        finished = {event['payload']['decision_index']: event['payload'] for event in events
                    if event['kind'] == 'model_attempt' and event['payload'].get('stage') == 'finished'}
        for event in events:
            payload = event.get('payload', {})
            if event['kind'] != 'model_attempt' or payload.get('stage') != 'started':
                continue
            request = payload['request']
            rendered, _, _ = prepare_candidate_prompt(request, tokenizer, {'chat_template_kwargs': {'enable_thinking': False}})
            response = finished[payload['decision_index']]['response']['body']['choices'][0]['message']
            call = response['tool_calls'][0]['function']
            arguments = json.loads(call['arguments'])
            raw = '<tool_call>\n<function=' + call['name'] + '>\n'
            raw += ''.join('<parameter=' + key + '>\n' + value + '\n</parameter>\n' for key, value in arguments.items())
            raw += '</function>\n</tool_call>'
            parsed, error = parse_candidate_generated(raw, request)
            if error or parsed['tool_calls'][0]['function']['name'] != call['name']:
                raise ValueError('CPU witness cannot be represented by the actual native parser')
            parsed_args = json.loads(parsed['tool_calls'][0]['function']['arguments'])
            if {key: value.strip() for key, value in parsed_args.items()} != {key: value.strip() for key, value in arguments.items()}:
                raise ValueError('Native fixture encoding changed argument contents')
            inputs = len(tokenizer(rendered, add_special_tokens=False)['input_ids'])
            outputs = len(tokenizer(raw, add_special_tokens=False)['input_ids'])
            rows.append({'role': role, 'decision_index': payload['decision_index'], 'input_tokens': inputs,
                         'witness_native_output_tokens': outputs, 'max_output_tokens': request['max_tokens'],
                         'total_reserved': inputs + request['max_tokens']})
    rows.sort(key=lambda row: (row['role'], row['decision_index']))
    report = {'version': VERSION, 'seed': 0, 'model_calls': 0, 'gpu_seconds': 0, 'rows': rows,
              'maximum_input_tokens': max(row['input_tokens'] for row in rows),
              'maximum_witness_output_tokens': max(row['witness_native_output_tokens'] for row in rows),
              'all_fit': all(row['total_reserved'] <= 16384 and row['witness_native_output_tokens'] <= row['max_output_tokens'] for row in rows),
              'scope': 'One old development seed program witness through actual tools, official tokenizer and native parser. Not a minimum route, held-out result or arbitrary model trace bound.'}
    write(output / 'token-lengths.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('prepare', 'cpu-controls', 'token-lengths'), required=True)
    parser.add_argument('--assets', type=Path, default=Path('runs/assets/domain-v021/TeamBench'))
    parser.add_argument('--development-assets', type=Path, default=Path('runs/teambench-v022-os-isolation-verified'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=Path('runs/assets/models/Qwen3.5-9B-c20223623576'))
    args = parser.parse_args()
    if args.mode == 'prepare':
        generated, grader = generate(args.assets, args.output)
        print(json.dumps({'generated': str(generated), 'grader': str(grader), 'model_calls': 0}))
    elif args.mode == 'token-lengths':
        print(json.dumps(measure_token_lengths(args.output, args.model)))
    else:
        report = cpu_controls(args.output, args.development_assets)
        print(json.dumps({'all_declared_controls_passed': report['all_declared_controls_passed'], 'model_calls': 0}))


if __name__ == '__main__':
    main()
