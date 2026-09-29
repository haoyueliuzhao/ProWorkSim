"""One authorized full-window recomputation, then the original unstarted work."""
import argparse
import os
from pathlib import Path
import time

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.composition_evidence_v025 import checked
from scripts.composition_pilot_v025 import ACCEPTED, continuation, evaluate
from scripts.credit_pilot_v024 import publish_checkpoint, restore_endpoint
from scripts.evaluate_work_v022 import reference, write
from scripts.learning_pilot_v023 import task

VERSION = 'same-window-composition-recovery-v0.25-r1'
STAGES = ('train_base', 'confirm_base', 'next_base')


def recompute(owner, plan, output, root):
    from proworksim.composition_recovery_v025 import restore_failed_window
    from proworksim.work_composition_diagnostics_v025 import summarize_work_signals
    from proworksim.work_learning_diagnostics_v023 import select_post_update_rows

    task(output, 'R1-restore-original-preupdate-state', 'boundary')
    entries, composition, proof = restore_failed_window(owner, plan['original_run'], plan['recovery'], output)
    write(output / 'restoration-proof.json', proof)
    write(output / 'composition.json', composition)
    task(output, 'R1-recompute-all-original-decisions', 'update')
    result = owner.update_window(entries, output / 'update', composition=composition,
                                post_update_selector=select_post_update_rows)
    write(output / 'update-result.json', result)
    if (result['status'] not in ACCEPTED or owner.actor_steps != 2 + result.get('actor_optimizer_steps', 0)
            or owner.critic_steps != 2 + result.get('critic_optimizer_steps', 0)
            or owner.actor_steps > 3 or owner.critic_steps > 3):
        raise ValueError('R1 update not qualified; retain attempt without publishing an alternative endpoint')
    task(output, 'R1-save-original-window-result', 'boundary')
    signal = summarize_work_signals(entries, output / 'update')
    signal.update(recovery='Explicitly authorized recomputation of the original unstepped window; no new training collection.')
    write(output / 'work-signals.json', signal)
    saved = publish_checkpoint(owner, output / 'checkpoint-final', root, 'base')
    write(root / 'base-complete.json', {'source': code_identity(),
        'endpoint': reference(root / 'checkpoints/base.json'),
        'update': reference(output / 'update-result.json'),
        'restoration': reference(output / 'restoration-proof.json'),
        'original_failure_preserved': True, 'recomputed_original_window': True})
    return {'status': 'complete', 'update': result, 'final_checkpoint': saved,
        'restoration_reference': reference(output / 'restoration-proof.json'),
        'actual_new_episodes': 0, 'new_training_model_calls': 0,
        'training_episode_consumptions': len(entries), 'original_failure_replaced': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--stage', choices=STAGES, required=True)
    args = parser.parse_args()
    plan, root, output = read_json(args.plan), args.run_root.resolve(), args.output.resolve()
    source = code_identity()
    if (plan['version'] != VERSION or source['code_dirty']
            or os.environ.get('CUDA_VISIBLE_DEVICES') not in set(map(str, range(8)))):
        raise ValueError('R1 needs committed frozen source and exactly one physical GPU')
    source_root = Path(__file__).resolve().parents[1]
    for relative, expected in plan['unchanged_learning_source_sha256'].items():
        if digest((source_root / relative).read_bytes()) != expected:
            raise ValueError('The original learning, world or model path changed: ' + relative)
    original_plan = read_json(checked(plan['original_plan']))
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.templates.retail_collaboration_v025 import registry
    from proworksim.composition_recovery_v025 import build_recovery_binding

    if build_recovery_binding(plan['original_run']) != plan['recovery']:
        raise ValueError('Original stopped-run evidence or inputs changed')
    for item in original_plan['qualification_refs']:
        checked(item)
    for item in plan['qualification_refs']:
        checked(item)
    prior = read_json(checked(original_plan['prior_model_plan']))
    catalog = read_json(checked(plan['catalog']))
    if catalog != registry() or plan['catalog'] != original_plan['catalog'] or plan['source_pin'] != original_plan['source_pin']:
        raise ValueError('Keep original confirmation, continuation and source materials')
    recipe = original_plan['base_recipe']
    if recipe != read_json(checked(original_plan['prior_owner']))['recipe'] or recipe['credit_assignment'] != 'terminal_mc':
        raise ValueError('No new precision/credit/optimizer configuration in R1')
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'stage': args.stage, 'status': 'loading',
        'source_before': source, 'plan': reference(args.plan), 'started_at': time.time(),
        'model_api_calls': 0, 'original_run': plan['original_run'],
        'original_failure_preserved': True, 'new_support_collection': False}
    write(output / 'report.json', report)
    owner = None
    try:
        task(output, 'R1-model-loading', 'loading')
        owner = DeterministicCandidateActor.from_candidate(prior['model'], manifest=checked(prior['manifest']),
            profile=prior['runtime_profile'], recipe=recipe, output=output / 'resident')
        report.update(status='running')
        write(output / 'report.json', report)
        if args.stage == 'train_base':
            result = recompute(owner, plan, output, root)
        elif args.stage == 'confirm_base':
            report['restored_checkpoint'] = restore_endpoint(owner, root, 'base')
            result = evaluate(owner, plan, catalog, output, 'base', 'confirmation')
        else:
            result = continuation(owner, plan, catalog, output, root, 'base')
        report.update(result)
    except BaseException as error:
        report.update(status='interrupted_or_error', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        if owner:
            report.update(final_actor_identity=owner._make_identity(), actor_steps=owner.actor_steps, critic_steps=owner.critic_steps)
        report.update(ended_at=time.time(), source_after=code_identity())
        report['source_unchanged'] = source == report['source_after']
        write(output / 'report.json', report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
