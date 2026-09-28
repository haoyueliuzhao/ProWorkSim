"""Three frozen endpoints and two independent current-policy credit branches."""
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
from scripts.learning_pilot_v023 import task

VERSION = 'paired-temporal-credit-pilot-v0.24'
ARMS = ('mc', 'handoff_rtg')
ACCEPTED = {'updated', 'zero_step_zero_actor_advantage_or_gradient', 'zero_step_no_admitted_own_actions'}


def publish_checkpoint(owner, folder, root, label):
    saved = owner.save_checkpoint(folder)
    marker = root / 'checkpoints' / f'{label}.json'
    if marker.exists():
        raise FileExistsError('Do not replace a declared checkpoint endpoint')
    write(marker, {'checkpoint': reference(folder / 'checkpoint.json'), 'directory': str(folder.resolve()),
                   'actor_identity': saved['actor_identity'], 'source': code_identity(), 'label': label,
                   'credit_assignment': owner.recipe['credit_assignment']})
    return saved


def restore_endpoint(owner, root, label):
    marker = read_json(root / 'checkpoints' / f'{label}.json')
    checked(marker['checkpoint'])
    if marker['source'] != code_identity() or marker['label'] != label:
        raise ValueError('Endpoint source/label differs')
    saved = owner.restore_checkpoint(marker['directory'])
    if owner.freeze_identity() != marker['actor_identity']:
        raise ValueError('Restored tensor identity differs from the actual checkpoint')
    return saved


def collect_window(owner, catalog, contract, admission, output, assets_root):
    from proworksim.collaboration_training_v024 import export_training_episode, projection_summary, validate_window_declaration
    from proworksim.templates.retail_collaboration_v024 import build_case, runtime as make_runtime

    identity = owner.begin_window(contract['window_id'])
    pending, specs, initial_by_case = [], [], {}
    for slot in contract['slots']:
        folder = output / slot['slot_id']
        prepared = build_case(slot['case_id'], folder, assets_root=assets_root)
        runtime, capture, _ = make_runtime(owner, prepared, folder, 'compact_work', episode_key=f"{slot['case_id']}:{slot['seed']}")
        initial = prepared.prefix['prepared_business_state_sha256']
        if slot['case_id'] in initial_by_case and initial_by_case[slot['case_id']] != initial:
            raise ValueError('Repeated exact situation has a different initial business state')
        initial_by_case[slot['case_id']] = initial
        specs.append({'slot_id': slot['slot_id'], 'xi_id': slot['case_id'],
                      'xi_fingerprint': digest(json_bytes({'case': prepared.case, 'initial': initial})),
                      'active_members': list(prepared.active_roles), 'policies': runtime.policy_identities,
                      'mapping_spec_id': 'base-Q-equals-B-no-reconfiguration-v024'})
        pending.append((slot, prepared, folder, runtime, capture))
    declaration = declare_window(contract['window_id'], actor_identity=identity,
        gamma_identity={'version': VERSION, 'harness': admission['harness'], 'recipe': owner.recipe, 'credit_arm': contract['credit_arm'],
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


def evaluate(owner, plan, catalog, output, endpoint):
    from proworksim.templates.retail_collaboration_v024 import assess_episode, build_case, runtime as make_runtime

    rows = []
    identity = owner.freeze_identity()
    for slot in catalog['evaluation_slots']:
        task(output, f"{endpoint}:{slot['slot_id']}", 'episode')
        folder = output / slot['slot_id']
        prepared = build_case(slot['case_id'], folder, assets_root=plan['assets_root'])
        snapshot = owner.capture_evaluation_state()
        owner.begin_window(f"v024-{endpoint}-{slot['slot_id']}")
        owner.reseed(slot['seed'], label=f"{endpoint}:{slot['slot_id']}")
        runtime, capture, _ = make_runtime(owner, prepared, folder, 'compact_work', episode_key=f"{slot['case_id']}:{slot['seed']}")
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
            if not assessment['eligible']:
                raise ValueError('Evaluation outcome unknown; retain slot and stop stage')
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



def common_collection(owner, plan, catalog, output, root):
    from proworksim.collaboration_training_v024 import training_admission
    from proworksim.credit_consumption_v024 import save_common_origin

    restore_endpoint(owner, root, 'initial')
    admission = training_admission(catalog, checked(plan['source_pin']))
    write(output / 'admission.json', admission)
    folder = output / 'collection'
    folder.mkdir()
    contract = next(w for w in catalog['sampling_windows'] if w['collection_id'] == 'common')
    entries, rows = collect_window(owner, catalog, contract, admission, folder, plan['assets_root'])
    declaration = read_json(folder / 'declaration.json')
    task(output, 'common:snapshot-for-consumption', 'boundary')
    origin = save_common_origin(owner, output / 'common-origin', entries, declaration, admission)
    marker = {'source': code_identity(), 'origin_dir': str((output / 'common-origin').resolve()),
              'entries': reference(folder / 'entries.json'), 'declaration': reference(folder / 'declaration.json'),
              'admission': reference(output / 'admission.json'), 'origin': origin,
              'initial_checkpoint': reference(root / 'checkpoints/initial.json')}
    write(root / 'common-complete.json', marker)
    return {'status': 'complete', 'rows': rows, 'shared_origin': marker,
            'actual_new_training_episodes': 6, 'actor_steps': owner.actor_steps, 'critic_steps': owner.critic_steps}


def credit_signals(entries, folder, owner):
    from proworksim.work_learning_diagnostics_v023 import summarize_work_signals
    signal = summarize_work_signals(entries, folder / 'update')
    admission = read_json(folder / 'update/admission.json')
    by_call = {row['call_id']: row for row in admission['decisions']}
    signal.update(version='work-credit-diagnostics-v0.24', credit_assignment=owner.recipe['credit_assignment'],
                  scope='Same terminal contract and random realized member-token denominator; alternative temporal surrogates, not claimed unbiased-equivalent estimators or causal action credit.')
    for row in signal['decisions']:
        original = by_call[row['call_id']]
        row['credit'] = original['credit']
        entry = next(e for e in entries if e['slot_id'] == row['slot_id'])
        row['reward_ledger'] = entry['reward']['ledger']
        starts = [e for e in entry['rollout']['events'] if e['kind'] == 'model_call'
                  and e.get('worker_id') == row['member_id'] and e['payload'].get('stage') == 'started'
                  and e['payload'].get('call_id') == row['call_id']]
        if len(starts) != 1:
            raise ValueError('Unique original decision sequence needed for temporal diagnostics')
        sequence = starts[0]['sequence']
        early = [e['sequence'] for e in row['reward_ledger']['events'] if e['settlement'] == 'event']
        row['decision_sequence'] = sequence
        row['handoff_temporal_region'] = ('no_early_handoff' if not early else
            'before_or_producing_handoff' if sequence <= min(early) else 'after_handoff')
        from proworksim.online_signals import joint_return
        row['mc_target_same_trace'] = joint_return(entry['reward'], sequence, 'terminal_mc', entry['rollout']['events'])[0]
        row['rtg_target_same_trace'] = joint_return(entry['reward'], sequence, 'joint_reward_to_go', entry['rollout']['events'])[0]
    # v023 helper produced only a new v024 output; replace its metadata with the
    # actual arm immediately, never relabel an old experimental artifact.
    signal['positive_achieved_term_scope'] = 'Slot-level achieved terminal terms associated with some positive advantage; not necessarily remaining credit for that decision or a causal action attribution.'
    write(folder / 'update/work-signal-diagnostics.json', signal)
    write(folder / 'work-signals.json', signal)
    return signal


def branch_train(owner, plan, catalog, output, root, arm):
    from proworksim.collaboration_training_v024 import training_admission
    from proworksim.credit_consumption_v024 import prepare_common_consumption
    from proworksim.work_learning_diagnostics_v023 import select_post_update_rows

    common = read_json(root / 'common-complete.json')
    if common['source'] != code_identity():
        raise ValueError('Common raw collection source differs from branch source')
    entries = read_json(checked(common['entries']))
    declaration = read_json(checked(common['declaration']))
    admission = read_json(checked(common['admission']))
    if admission != training_admission(catalog, checked(plan['source_pin'])):
        raise ValueError('Raw common collection admission changed')
    proof = prepare_common_consumption(owner, common['origin_dir'], entries, declaration, admission, arm)
    write(output / 'common-consumption.json', proof)
    write(output / 'admission.json', admission)
    rows = []
    for index in range(2):
        folder = output / f'window-{index}'
        folder.mkdir()
        row = {'window_index': index, 'credit_arm': arm, 'status': 'preparing', 'started_at': time.time(),
               'new_collection': index == 1, 'consumption_id': f'v024-{arm}-update-{index+1}'}
        rows.append(row)
        write(output / 'training-progress.json', rows)
        if index == 0:
            write(folder / 'entries.json', entries)
            write(folder / 'declaration.json', declaration)
            row['raw_collection_reference'] = common['entries']
            row['window_id'] = declaration['window_id']
        else:
            contract = next(w for w in catalog['sampling_windows'] if w['credit_arm'] == arm)
            row.update(status='collecting', window_id=contract['window_id'])
            write(output / 'training-progress.json', rows)
            entries, collected = collect_window(owner, catalog, contract, admission, folder, plan['assets_root'])
            row['slots'] = collected
        row.update(status='updating', entries=reference(folder / 'entries.json'))
        write(output / 'training-progress.json', rows)
        task(output, row['consumption_id'], 'update')
        update = owner.update_window(entries, folder / 'update', post_update_selector=select_post_update_rows)
        row['update'] = update
        write(output / 'training-progress.json', rows)
        if update['status'] not in ACCEPTED or owner.actor_steps > 2 or owner.critic_steps > 2:
            raise ValueError('Unqualified update: do not publish a replacement final endpoint')
        task(output, row['consumption_id'] + ':save', 'boundary')
        row['signals'] = credit_signals(entries, folder, owner)
        row['checkpoint'] = owner.save_checkpoint(folder / 'checkpoint')
        row.update(status='closed', ended_at=time.time())
        write(output / 'training-progress.json', rows)
    final = publish_checkpoint(owner, output / 'checkpoint-final', root, arm)
    write(root / f'{arm}-complete.json', {'source': code_identity(),
        'progress': reference(output / 'training-progress.json'), 'endpoint': reference(root / 'checkpoints' / f'{arm}.json')})
    return {'status': 'complete', 'windows': rows, 'final_checkpoint': final,
            'actual_new_training_episodes': 6, 'training_episode_consumptions': 12,
            'common_consumption_reference': reference(output / 'common-consumption.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--stage', choices=['eval_initial', 'common', 'train_mc', 'train_handoff_rtg', 'eval_mc', 'eval_handoff_rtg'], required=True)
    args = parser.parse_args()
    plan, root, output = read_json(args.plan), args.run_root.resolve(), args.output.resolve()
    source = code_identity()
    if plan['version'] != VERSION or source['code_dirty'] or os.environ.get('CUDA_VISIBLE_DEVICES') not in set(map(str, range(8))):
        raise ValueError('Committed frozen v024 source and one physical GPU required')
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.templates.retail_collaboration_v024 import registry
    from proworksim import functional_qwen_v022
    if digest(Path(functional_qwen_v022.__file__).read_bytes()) != plan['qualified_functional_sha256']:
        raise ValueError('The existing qualified learning function changed')
    for value in plan['qualification_refs']:
        checked(value)
    prior = read_json(checked(plan['prior_model_plan']))
    catalog = read_json(checked(plan['catalog']))
    if registry() != catalog:
        raise ValueError('Frozen material inventory differs')
    recipe = {**prior['recipe'], 'post_update_max_decisions': 6}
    if recipe != plan['base_recipe']:
        raise ValueError('Common fixed recipe changed')
    # A branch first restores the canonical MC origin, then explicitly changes
    # only the credit target. Its final evaluator restores that arm's recipe.
    if args.stage == 'eval_handoff_rtg':
        recipe['credit_assignment'] = 'joint_reward_to_go'
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'stage': args.stage, 'status': 'loading', 'source_before': source,
              'plan': reference(args.plan), 'started_at': time.time(), 'model_api_calls': 0}
    write(output / 'report.json', report)
    owner = None
    try:
        task(output, args.stage + ':loading', 'loading')
        owner = DeterministicCandidateActor.from_candidate(prior['model'], manifest=checked(prior['manifest']),
            profile=prior['runtime_profile'], recipe=recipe, output=output / 'resident')
        if owner.actor_steps or owner.critic_steps or owner.actor_optimizer.state or owner.critic_optimizer.state:
            raise ValueError('Candidate construction must create a fresh learning state')
        report.update(status='running', fresh_initial_identity=owner.freeze_identity())
        write(output / 'report.json', report)
        if args.stage.startswith('train_'):
            result = branch_train(owner, plan, catalog, output, root, args.stage[len('train_'):])
        elif args.stage == 'common':
            result = common_collection(owner, plan, catalog, output, root)
        else:
            endpoint = args.stage[len('eval_'):]
            if endpoint == 'initial':
                task(output, 'publish-fresh-initial', 'boundary')
                report['initial_checkpoint'] = publish_checkpoint(owner, output / 'checkpoint-initial', root, 'initial')
            else:
                report['restored_checkpoint'] = restore_endpoint(owner, root, endpoint)
            write(output / 'report.json', report)
            result = evaluate(owner, plan, catalog, output, endpoint)
            if endpoint == 'initial':
                write(root / 'baseline-complete.json', {'source': source, 'closed_slots': 12,
                    'progress': reference(output / 'progress.json'), 'checkpoint': reference(root / 'checkpoints/initial.json'),
                    'business_results_used_for_selection': False})
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
