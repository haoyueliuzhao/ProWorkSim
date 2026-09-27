"""Frozen Q=B training and paired evaluation stages; no score-driven successors."""
import argparse
import copy
import os
from pathlib import Path
import time

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.online_support import declare_window
from proworksim.storage import digest, json_bytes, read_json
from scripts.evaluate_work_v022 import checked, reference, write

VERSION = 'paired-work-learning-pilot-v0.23'
ACCEPTED = {'updated', 'zero_step_zero_actor_advantage_or_gradient', 'zero_step_no_admitted_own_actions'}


def task(output, name, kind):
    write(output / 'task.json', {'task': name, 'kind': kind, 'started_at': time.time(), 'pid': os.getpid()})


def publish_checkpoint(owner, folder, root, label):
    saved = owner.save_checkpoint(folder)
    marker = root / 'checkpoints' / f'{label}.json'
    if marker.exists():
        raise FileExistsError('Checkpoint endpoints cannot be silently replaced')
    write(marker, {'checkpoint': reference(folder / 'checkpoint.json'), 'directory': str(folder.resolve()),
                   'actor_identity': saved['actor_identity'], 'source': code_identity(), 'label': label})
    return saved


def collect_window(owner, catalog, contract, admission, output, assets_root):
    from proworksim.collaboration_training_v023 import export_training_episode, projection_summary, validate_window_declaration
    from proworksim.templates.retail_collaboration_v023 import build_case, runtime as make_runtime

    identity = owner.begin_window(contract['window_id'])
    pending, specs, initial_by_case = [], [], {}
    for slot in contract['slots']:
        folder = output / slot['slot_id']
        prepared = build_case(slot['case_id'], folder, assets_root=assets_root)
        runtime, capture, _ = make_runtime(owner, prepared, folder, 'compact_work')
        initial = prepared.prefix['prepared_business_state_sha256']
        if slot['case_id'] in initial_by_case and initial_by_case[slot['case_id']] != initial:
            raise ValueError('Repeated exact situation has a different initial business state')
        initial_by_case[slot['case_id']] = initial
        specs.append({'slot_id': slot['slot_id'], 'xi_id': slot['case_id'],
                      'xi_fingerprint': digest(json_bytes({'case': prepared.case, 'initial': initial})),
                      'active_members': list(prepared.active_roles), 'policies': runtime.policy_identities,
                      'mapping_spec_id': 'base-Q-equals-B-no-reconfiguration-v023'})
        pending.append((slot, prepared, folder, runtime, capture))
    declaration = declare_window(contract['window_id'], actor_identity=identity,
        gamma_identity={'version': VERSION, 'harness': admission['harness'], 'recipe': owner.recipe,
                        'catalog_sha256': digest(json_bytes(catalog)), 'training_admission': admission,
                        'seeds': [s['seed'] for s in contract['slots']], 'source': code_identity()}, slot_specs=specs)
    validate_window_declaration(declaration, admission)
    write(output / 'declaration.json', declaration)
    entries, rows = [], []
    for slot, prepared, folder, runtime, capture in pending:
        task(output.parent, f"{contract['window_id']}:{slot['slot_id']}", 'episode')
        owner.reseed(slot['seed'], label=slot['slot_id'])
        row = {**slot, 'status': 'started', 'started_at': time.time(),
               'initial_business_state_sha256': initial_by_case[slot['case_id']]}
        rows.append(row)
        write(output / 'progress.json', rows)
        episode = folder / 'episode'
        try:
            begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_nodes=['TEAM::build'],
                          work_ids=[], scenario=copy.deepcopy(prepared.scenario), policies=runtime.policy_identities)
            boundary = run_fragment(prepared, runtime, external_tick_per_sweep=1)
            finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
            write(folder / 'public-capture.json', capture)
            write(folder / 'runtime.json', runtime.snapshot())
            entry, proof = export_training_episode(prepared, episode, declaration=declaration,
                                                  slot_id=slot['slot_id'], captured=capture, admission=admission)
            write(folder / 'team-rollout.json', entry['rollout'])
            write(folder / 'projection.json', proof)
            entries.append(entry)
            row.update(status='closed', ended_at=time.time(), boundary=boundary, reward=entry['reward'],
                       projection=projection_summary(entry), record_validity=proof['record_validity'])
            if (proof['record_validity'] is not True or not entry['reward']['eligible']
                    or proof.get('has_complete_trainable_actual_members') is not True):
                raise ValueError('Unknown collection record: keep its scheduled slot, stop before update')
        except BaseException as error:
            row.update(status='interrupted_or_unassessed', ended_at=time.time(), error=str(error))
            write(folder / 'public-capture.json', capture)
            write(folder / 'runtime.json', runtime.snapshot())
            write(output / 'progress.json', rows)
            raise
        write(output / 'progress.json', rows)
    write(output / 'entries.json', entries)
    return entries, rows


def train(owner, plan, catalog, output, root, *, recovery=None):
    from proworksim.collaboration_training_v023 import training_admission
    from proworksim.work_learning_diagnostics_v023 import select_post_update_rows, summarize_work_signals

    admission = training_admission(catalog, checked(plan['source_pin']))
    write(output / 'admission.json', admission)
    restored = None
    if recovery is None:
        marker = read_json(root / 'checkpoints/initial.json')
        checked(marker['checkpoint'])
        if marker['source'] != code_identity() or marker['label'] != 'initial':
            raise ValueError('Training must restore the actual common fresh initial checkpoint')
        initial = owner.restore_checkpoint(marker['directory'])
        if owner.freeze_identity() != marker['actor_identity'] or owner.actor_steps or owner.critic_steps:
            raise ValueError('Training initial state differs or already contains learning')
        windows, first = [], 0
    else:
        from proworksim.pilot_recovery_v023 import restore_window
        restored = restore_window(owner, recovery)
        write(output / 'recovery.json', restored)
        marker = read_json(root / 'checkpoints/initial.json')
        initial = read_json(checked(marker['checkpoint']))
        windows = copy.deepcopy(recovery['completed_rows'])
        first = recovery['original_window_index']
    write(output / 'training-progress.json', windows)
    for contract in catalog['training_windows'][first:]:
        folder = output / f"window-{contract['window_index']}"
        folder.mkdir()
        row = {'window_id': contract['window_id'], 'window_index': contract['window_index'],
               'status': 'collecting', 'started_at': time.time()}
        windows.append(row)
        write(output / 'training-progress.json', windows)
        if restored is not None and contract['window_index'] == first:
            entries = restored['entries']
            slots = read_json(Path(recovery['original_window_folder']) / 'progress.json')
            write(folder / 'entries.json', entries)
            write(folder / 'restored-from.json', recovery)
            write(folder / 'declaration.json', read_json(Path(recovery['original_window_folder']) / 'declaration.json'))
        else:
            entries, slots = collect_window(owner, catalog, contract, admission, folder, plan['assets_root'])
        row.update(status='updating', entries=reference(folder / 'entries.json'), slots=slots)
        write(output / 'training-progress.json', windows)
        task(output, contract['window_id'] + ':update', 'update')
        update = owner.update_window(entries, folder / 'update', post_update_selector=select_post_update_rows)
        row['update'] = update
        write(output / 'training-progress.json', windows)
        if update['status'] not in ACCEPTED or owner.actor_steps > 4 or owner.critic_steps > 4:
            raise ValueError('Update not qualified; no automatic next window or final checkpoint')
        task(output, contract['window_id'] + ':save', 'boundary')
        row['signals'] = summarize_work_signals(entries, folder / 'update')
        write(folder / 'work-signals.json', row['signals'])
        row['checkpoint'] = owner.save_checkpoint(folder / 'checkpoint')
        row.update(status='closed', ended_at=time.time())
        write(output / 'training-progress.json', windows)
    final = publish_checkpoint(owner, output / 'checkpoint-final', root, 'final')
    result = {'status': 'complete', 'initial_checkpoint': initial, 'final_checkpoint': final,
              'windows': windows, 'actor_steps': owner.actor_steps, 'critic_steps': owner.critic_steps}
    write(root / 'training-complete.json', {'source': code_identity(), 'progress': reference(output / 'training-progress.json'),
                                         'final_checkpoint': reference(root / 'checkpoints/final.json')})
    return result


def evaluate(owner, plan, catalog, output, endpoint):
    from proworksim.templates.retail_collaboration_v023 import assess_episode, build_case, runtime as make_runtime

    rows = []
    identity = owner.freeze_identity()
    for slot in catalog['evaluation_slots']:
        task(output, f"{endpoint}:{slot['slot_id']}", 'episode')
        folder = output / slot['slot_id']
        prepared = build_case(slot['case_id'], folder, assets_root=plan['assets_root'])
        snapshot = owner.capture_evaluation_state()
        owner.begin_window(f"v023-{endpoint}-{slot['slot_id']}")
        owner.reseed(slot['seed'], label=f"{endpoint}:{slot['slot_id']}")
        runtime, capture, _ = make_runtime(owner, prepared, folder, 'compact_work')
        row = {**slot, 'status': 'started', 'started_at': time.time(), 'actor_identity': identity,
               'initial_business_state_sha256': prepared.prefix['prepared_business_state_sha256']}
        rows.append(row)
        write(output / 'progress.json', rows)
        episode = folder / 'episode'
        try:
            begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_nodes=['TEAM::build'],
                          work_ids=[], scenario=copy.deepcopy(prepared.scenario), policies=runtime.policy_identities)
            boundary = run_fragment(prepared, runtime, external_tick_per_sweep=1)
            finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
            assessment = assess_episode(episode)
            write(folder / 'assessment.json', assessment)
            write(folder / 'public-capture.json', capture)
            write(folder / 'runtime.json', runtime.snapshot())
            owner.finish_evaluation([{'slot_id': slot['slot_id'], 'active_members': prepared.active_roles,
                                      'reward': assessment}], folder / 'frozen-evaluation')
            guard = owner.finish_evaluation_guard(snapshot)
            row.update(status='closed', ended_at=time.time(), assessment_ref=reference(folder / 'assessment.json'),
                       assessment=assessment, boundary=boundary, evaluation_guard=guard)
            if not guard['learning_unchanged'] or not guard['rng_restored_exactly'] or owner.freeze_identity() != identity:
                raise ValueError('Frozen evaluation changed actual learning state')
        except BaseException as error:
            row.update(status='interrupted_or_unassessed', ended_at=time.time(), error=str(error))
            write(folder / 'public-capture.json', capture)
            write(folder / 'runtime.json', runtime.snapshot())
            write(output / 'progress.json', rows)
            raise
        write(output / 'progress.json', rows)
        # Operational progress only. No evaluation scores are consumed by training.
        print(json_bytes({'endpoint': endpoint, 'closed_evaluation_slots': len(rows)}).decode(), flush=True)
    return {'status': 'complete', 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--stage', choices=['train', 'train_recovery', 'eval_initial', 'eval_final', 'external_initial', 'external_final'], required=True)
    args = parser.parse_args()
    plan, output, root = read_json(args.plan), args.output.resolve(), args.run_root.resolve()
    if plan['version'] != VERSION or os.environ.get('CUDA_VISIBLE_DEVICES') not in set(map(str, range(8))):
        raise ValueError('Frozen v023 protocol and one physical GPU required')
    source = code_identity()
    if source['code_dirty']:
        raise ValueError('Execute only committed frozen source')
    from proworksim.collaboration_actor_v022 import FunctionalCandidateActor
    from proworksim.templates.retail_collaboration_v023 import registry
    from proworksim import functional_qwen_v022
    if digest(Path(functional_qwen_v022.__file__).read_bytes()) != plan['qualified_functional_sha256']:
        raise ValueError('The qualified learner path changed')
    for value in plan['qualification_refs']:
        checked(value)
    catalog = read_json(checked(plan['catalog']))
    if registry() != catalog:
        raise ValueError('Task catalog changed')
    prior = read_json(checked(plan['prior_model_plan']))
    recipe = {**prior['recipe'], 'post_update_max_decisions': 6}
    if recipe != plan['recipe']:
        raise ValueError('Frozen base recipe changed')
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'stage': args.stage, 'status': 'loading', 'source_before': source,
              'plan': reference(args.plan), 'started_at': time.time(), 'model_api_calls': 0}
    write(output / 'report.json', report)
    owner = None
    try:
        task(output, args.stage + ':loading', 'loading')
        owner = FunctionalCandidateActor.from_candidate(prior['model'], manifest=checked(prior['manifest']),
            profile=prior['runtime_profile'], recipe=recipe, output=output / 'resident')
        report['fresh_initial_identity'] = owner.freeze_identity()
        if owner.actor_steps or owner.critic_steps or owner.actor_optimizer.state or owner.critic_optimizer.state:
            raise ValueError('The candidate must start with fresh adapters, critic and optimizers')
        report['status'] = 'running'
        write(output / 'report.json', report)
        if args.stage in {'train', 'train_recovery'}:
            recovery = None
            if args.stage == 'train_recovery':
                from proworksim.pilot_recovery_v023 import admit_recovery
                recovery = admit_recovery(root / 'train', plan)
                if recovery != read_json(root / 'recovery-admission.json'):
                    raise ValueError('Original no-step recovery binding changed')
            result = train(owner, plan, catalog, output, root, recovery=recovery)
        else:
            endpoint = args.stage.split('_', 1)[1]
            if args.stage == 'eval_initial':
                task(output, 'publish-common-fresh-initial', 'boundary')
                report['initial_checkpoint'] = publish_checkpoint(owner, output / 'checkpoint-initial', root, 'initial')
                write(output / 'report.json', report)
            marker = read_json(root / 'checkpoints' / f'{endpoint}.json')
            checked(marker['checkpoint'])
            if marker['source'] != source or marker['label'] != endpoint:
                raise ValueError('Evaluation endpoint source differs')
            owner.restore_checkpoint(marker['directory'])
            if owner.freeze_identity() != marker['actor_identity']:
                raise ValueError('Actual restored endpoint identity differs')
            report['restored_checkpoint'] = marker
            write(output / 'report.json', report)
            if args.stage.startswith('eval_'):
                result = evaluate(owner, plan, catalog, output, endpoint)
            else:
                from proworksim.teambench_model_v023 import run_checkpoint
                result = run_checkpoint(owner, assets=plan['external_assets_root'], output=output / 'external',
                    checkpoint_label=endpoint,
                    on_episode_start=lambda seed: task(output, f'external-{endpoint}-{seed}', 'episode'))
        report.update(result)
        report['status'] = 'complete'
    except BaseException as error:
        report.update(status='interrupted_or_error', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        if owner:
            report.update(final_actor_identity=owner._make_identity(), actor_steps=owner.actor_steps,
                          critic_steps=owner.critic_steps)
        report.update(ended_at=time.time(), source_after=code_identity())
        report['source_unchanged'] = source == report['source_after']
        write(output / 'report.json', report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
