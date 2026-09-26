"""Counterfactual precision diagnostic on fixed original outputs, never training."""

import argparse
import json
from pathlib import Path
import time

from proworksim.online_training import SharedActor, probability_check, selected_logprobs, tensor_tree_digest
from proworksim.storage import atomic_write, json_bytes


def cached_logprobs(model, trace, torch, device):
    ids = torch.tensor([trace['input_ids']], dtype=torch.long, device=device)
    kwargs = {'attention_mask': torch.ones_like(ids), 'use_cache': True, 'logits_to_keep': 1,
              'cache_position': torch.arange(ids.shape[1], device=device), 'past_key_values': None}
    values = []
    for target in trace['output_ids']:
        prepared = model.prepare_inputs_for_generation(ids, **kwargs)
        outputs = model(**prepared, return_dict=True)
        logits = outputs.logits[0, -1].float() / trace['sampling_temperature']
        values.append(float(logits.log_softmax(-1)[target]))
        kwargs = model._update_model_kwargs_for_generation(outputs, kwargs, is_encoder_decoder=False)
        ids = torch.cat((ids, torch.tensor([[target]], device=device)), dim=1)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--weight-manifest', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    first = json.loads(Path(manifest['cases'][0]['update_report']).read_text())
    owner = SharedActor.from_pretrained(args.model, weight_manifest=args.weight_manifest,
                                        output=args.output / 'diagnostic-owner', recipe=first['recipe'],
                                        matmul_precision='high')
    torch = owner.torch
    report = {'version': 'learning-numeric-diagnostic-v0.14', 'manifest': manifest, 'cases': [],
              'scope': 'Fixed worst failed original sequence per stopped run. No sampling, world execution, optimizer step, or old admission repair. Highest is a counterfactual numerical policy; its cached probabilities are not original high behavior probabilities.'}
    with torch.no_grad():
        for case in manifest['cases']:
            before = torch.load(case['state'], map_location='cpu', weights_only=True)
            assert set(before['actor']) == set(owner.actor_parameters)
            for name, parameter in owner.actor_parameters.items():
                parameter.copy_(before['actor'][name].to(owner.device))
            digest = tensor_tree_digest(owner.actor_state(), torch)
            assert digest == before['actor_identity']['adapter_sha256'] == case['actor_sha256']
            admission = json.loads(Path(case['admission']).read_text())
            row = next(row for row in admission['decisions'] if row['call_id'] == case['call_id'])
            trace = row['tokens']
            out = {**case, 'input_tokens': len(trace['input_ids']), 'output_tokens': len(trace['output_ids']),
                   'actual_actor_sha256': digest, 'precisions': []}
            for precision in ('high', 'highest'):
                torch.set_float32_matmul_precision(precision)
                owner.clear_generation_cache()
                owner.model.eval()
                started = time.time()
                cached = cached_logprobs(owner.model, trace, torch, owner.device)
                full = selected_logprobs(owner.model, trace, torch, owner.device).cpu().tolist()
                out['precisions'].append({'precision': precision, 'allow_tf32': torch.backends.cuda.matmul.allow_tf32,
                    'seconds': time.time() - started,
                    'cached_vs_original_high_behavior': probability_check(cached, trace['behavior_logprobs'], owner.recipe),
                    'full_vs_original_high_behavior': probability_check(full, trace['behavior_logprobs'], owner.recipe),
                    'full_vs_same_precision_cached': probability_check(full, cached, owner.recipe)})
                print(json.dumps({'case': case['job'], 'precision': precision,
                    'max_delta': out['precisions'][-1]['full_vs_same_precision_cached']['max_abs_delta']}, ensure_ascii=False), flush=True)
            assert tensor_tree_digest(owner.actor_state(), torch) == digest
            report['cases'].append(out)
            atomic_write(args.output / 'report.json', json_bytes(report))
    report['all_highest_internal_checks_passed'] = all(row['precisions'][1]['full_vs_same_precision_cached']['passed'] for row in report['cases'])
    report['optimizer_steps'] = 0
    atomic_write(args.output / 'report.json', json_bytes(report))


if __name__ == '__main__':
    main()
