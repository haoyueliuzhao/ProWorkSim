"""R1: recompute the same unstepped B1 window, then its two unstarted dev cases."""
import argparse
import os
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.bridge_resume_v022 import (
    VERSION, checked, rebuild_entries, reference, restore_before_update, validate_resume_plan,
)
from proworksim.storage import read_json
from scripts.bridge_work_v022 import post_development
from scripts.evaluate_work_v022 import task, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = read_json(args.plan)
    proof = validate_resume_plan(plan)
    source = code_identity()
    if source['code_dirty'] or os.environ.get('CUDA_VISIBLE_DEVICES') not in set(map(str, range(8))):
        raise ValueError('R1 needs frozen source and one supervisor-bound physical GPU')
    old_report = read_json(checked(plan['inputs']['old_bridge_report']))
    old_update = read_json(checked(plan['inputs']['old_update_report']))
    b1_plan = read_json(checked(plan['inputs']['old_b1_plan']))
    prior = read_json(checked(b1_plan['prior_model_plan']))
    catalog = read_json(checked(b1_plan['catalog']))
    # Before loading, prove the exact saved contexts, fixed denominators and
    # old identity still yield the same admission. This reads no current world.
    entries, admission = rebuild_entries(plan, old_update['before_actor_identity'], old_update['recipe'])
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'status': 'loading', 'plan': reference(args.plan),
              'source_before': source, 'old_B1_status_preserved': 'stopped_task_time_budget',
              'no_step_proof': proof, 'admission_reconstruction': admission,
              'old_actual': plan['old_actual'], 'prior_gpu_seconds': plan['prior_gpu_seconds'],
              'new_training_model_calls': 0, 'last_persisted_discarded_backward_decisions': 12,
              'unpersisted_in_progress_backward_work': 'unknown and discarded, never credited as a completed row',
              'learner_execution_profile': old_report['learner_execution_profile'],
              'legacy_update_report_terminology': 'Inherited full-sequence recomputation means complete original context through the unchanged functional recurrent learner; it does not mean the old no-cache full forward.',
              'recomputed_training_decisions_planned': 24, 'original_window': 'v022-b1-train',
              'scope': 'Same on-policy window resumed from pre-update snapshot. No training recollection, teacher/SFT conversion or changed loss. R1 cost is additional.'}
    write(out / 'report.json', report)
    owner = None
    try:
        from proworksim.collaboration_actor_v022 import FunctionalCandidateActor
        task(out, 'R1-model-loading')
        owner = FunctionalCandidateActor.from_candidate(prior['model'], manifest=checked(prior['manifest']),
            profile=prior['runtime_profile'], recipe=old_update['recipe'], output=out / 'resident')
        report['restoration'] = restore_before_update(owner, plan['inputs']['shared_before'], old_report['initial_actor_identity'])
        entries, report['admission_after_restore'] = rebuild_entries(plan, owner.freeze_identity(), owner.recipe)
        report['status'] = 'recomputing_original_update'
        write(out / 'report.json', report)
        task(out, 'R1-recompute-update')
        update = owner.update_window(entries, out / 'update')
        report.update(update=update, after_update_actor_identity=owner.freeze_identity())
        write(out / 'report.json', report)
        if owner.actor_steps > 1 or owner.critic_steps > 1:
            raise ValueError('Recovery exceeded the same one-step window')
        if update['status'] not in {'updated', 'zero_step_zero_actor_advantage_or_gradient', 'zero_step_no_admitted_own_actions'}:
            report['status'] = 'stopped_recomputed_update_unqualified'
            return 2
        report['checkpoint'] = owner.save_checkpoint(out / 'checkpoint')
        report['status'] = 'post_update_development'
        write(out / 'report.json', report)
        report['post_rows'] = post_development(owner, catalog, out, b1_plan['assets_root'])
        report['status'] = 'complete'
    except BaseException as error:
        report.update(status='interrupted_or_error', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                          final_actor_identity=owner._make_identity())
        report['source_after'] = code_identity()
        report['source_unchanged'] = source == report['source_after']
        write(out / 'report.json', report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
