"""One current joint window, conditional member composition and independent work."""
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
from scripts.credit_pilot_v024 import publish_checkpoint, restore_endpoint
from scripts.evaluate_work_v022 import reference, write
from scripts.composition_evidence_v025 import checked
from scripts.learning_pilot_v023 import task

VERSION = 'member-composition-pilot-v0.25'
STAGES = ('support', 'train_base', 'train_probe', 'dev_base', 'dev_probe',
          'train_configured', 'confirm_base', 'confirm_configured', 'next_base', 'next_configured')
ACCEPTED = {'updated', 'zero_step_zero_actor_advantage_or_gradient', 'zero_step_no_admitted_own_actions'}


def collect_window(owner, catalog, contract, admission, output, assets_root):
    from proworksim.collaboration_training_v025 import export_training_episode, projection_summary, validate_window_declaration
    from proworksim.templates.retail_collaboration_v025 import build_case, runtime as make_runtime

    identity = owner.begin_window(contract['window_id'])
    pending, specs, initial_by_case = [], [], {}
    for slot in contract['slots']:
        folder = output / slot['slot_id']
        prepared = build_case(slot['case_id'], folder, assets_root=assets_root)
        runtime, capture, _ = make_runtime(owner, prepared, folder, 'compact_work', episode_key=f"{slot['case_id']}:{slot['seed']}")
        initial = prepared.prefix['prepared_business_state_sha256']
        if slot['case_id'] in initial_by_case and initial_by_case[slot['case_id']] != initial:
            raise ValueError('Exact repeated situation has different prepared state')
        initial_by_case[slot['case_id']] = initial
        specs.append({'slot_id': slot['slot_id'], 'xi_id': slot['case_id'],
            'xi_fingerprint': digest(json_bytes({'case': prepared.case, 'initial': initial})),
            'active_members': list(prepared.active_roles), 'policies': runtime.policy_identities,
            'mapping_spec_id': admission['mapping_spec_id']})
        pending.append((slot, prepared, folder, runtime, capture))
    declaration = declare_window(contract['window_id'], actor_identity=identity,
        gamma_identity={'version': VERSION, 'harness': admission['harness'], 'recipe': owner.recipe,
            'purpose': admission['purpose'], 'catalog_sha256': digest(json_bytes(catalog)),
            'training_admission': admission, 'seeds': [s['seed'] for s in contract['slots']], 'source': code_identity()},
        slot_specs=specs, min_class_count=2)
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
                projection=projection_summary(entry), record_validity=proof['record_validity'],
                validity=entry['rollout']['work_validity'], mapping=entry['mapping'])
            if (proof['record_validity'] is not True or not entry['reward']['eligible']
                    or proof.get('has_complete_trainable_actual_members') is not True):
                raise ValueError('Unknown or incomplete original actor evidence: retain and stop')
        except BaseException as error:
            row.update(status='interrupted_or_unassessed', ended_at=time.time(), error=str(error))
            write(folder / 'public-capture.json', capture)
            write(folder / 'runtime.json', runtime.snapshot())
            write(output / 'progress.json', rows)
            raise
        write(output / 'progress.json', rows)
        print(json_bytes({'stage': 'collection', 'closed_slots': len(rows)}).decode(), flush=True)
    write(output / 'entries.json', entries)
    return entries, declaration, rows


def support_collection(owner, plan, catalog, output, root):
    from proworksim.collaboration_training_v025 import diagnose_support, training_admission
    from proworksim.online_training import tensor_tree_digest

    prior = read_json(checked(plan['prior_endpoint']))
    original = read_json(checked(prior['checkpoint']))
    checked(original['state'])
    restored = owner.restore_checkpoint(prior['directory'])
    if (prior['label'] != 'mc' or prior['credit_assignment'] != 'terminal_mc'
            or owner.actor_steps != 2 or owner.critic_steps != 2
            or owner.freeze_identity() != prior['actor_identity']
            or tensor_tree_digest(owner._state_bundle(), owner.torch) != original['state_tensor_digest']):
        raise ValueError('The sole conditional start is the exact v024 planned MC final state')
    origin = publish_checkpoint(owner, output / 'common-origin', root, 'origin')
    if origin['state_tensor_digest'] != restored['state_tensor_digest']:
        raise ValueError('Saving the new study origin altered the chosen complete state')
    admission = training_admission(catalog, checked(plan['source_pin']))
    write(output / 'admission.json', admission)
    folder = output / 'collection'
    folder.mkdir()
    snapshot = owner.capture_evaluation_state()
    entries, declaration, rows = collect_window(owner, catalog, catalog['training_window'], admission, folder, plan['assets_root'])
    guard = owner.finish_evaluation_guard(snapshot)
    guard['scope'] = 'No-update support collection: learning unchanged, RNG restored. This is training data collection, not an evaluation claim.'
    if not guard['learning_unchanged'] or not guard['rng_restored_exactly']:
        raise ValueError('Support collection changed the chosen learning state')
    owner.phase = 'idle'
    task(output, 'support:current-member-support', 'boundary')
    support = diagnose_support(entries, declaration)
    support.pop('records', None)
    write(output / 'support.json', support)
    marker = {'source': code_identity(), 'origin': reference(root / 'checkpoints/origin.json'),
        'entries': reference(folder / 'entries.json'), 'declaration': reference(folder / 'declaration.json'),
        'admission': reference(output / 'admission.json'), 'support': reference(output / 'support.json'),
        'origin_checkpoint': origin, 'collection_state_guard': guard,
        'actual_new_episodes': len(rows), 'selected_block': support['selected_block'],
        'prior_endpoint': plan['prior_endpoint'], 'origin_precedes_collection': True}
    write(root / 'support-complete.json', marker)
    return {'status': 'complete', 'collection_state_guard': guard, 'support_reference': marker['support'],
            'selected_block': support['selected_block'], 'actual_new_episodes': len(rows)}


def train_branch(owner, plan, catalog, output, root, branch):
    from proworksim.collaboration_training_v025 import records_from_entries, training_admission, validate_window_declaration
    from proworksim.composition_training_v025 import baseline_configuration, materialize_composition, probe_configuration
    from proworksim.online_support import bind_rollout
    from proworksim.online_training import tensor_tree_digest
    from proworksim.work_learning_diagnostics_v023 import select_post_update_rows
    from proworksim.work_composition_diagnostics_v025 import summarize_work_signals

    common = read_json(root / 'support-complete.json')
    if common['source'] != code_identity():
        raise ValueError('Current common collection source differs')
    entries = read_json(checked(common['entries']))
    declaration = read_json(checked(common['declaration']))
    admission = read_json(checked(common['admission']))
    support = read_json(checked(common['support']))
    if admission != training_admission(catalog, checked(plan['source_pin'])):
        raise ValueError('Frozen current support admission changed')
    validate_window_declaration(declaration, admission)
    restored = restore_endpoint(owner, root, 'origin')
    state_digest = tensor_tree_digest(owner._state_bundle(), owner.torch)
    if (state_digest != common['origin_checkpoint']['state_tensor_digest']
            or owner.freeze_identity() != declaration['actor_identity']
            or owner.actor_steps != 2 or owner.critic_steps != 2):
        raise ValueError('Every consumption must start at the same exact original complete state')
    if [e['slot_id'] for e in entries] != [s['slot_id'] for s in declaration['slots']]:
        raise ValueError('The entire 16-slot raw inventory must remain')
    for entry in entries:
        bind_rollout(declaration, entry['slot_id'], entry['rollout'])
    records = records_from_entries(entries)
    selected = support['selected_block']
    if branch == 'base':
        q = baseline_configuration(support['supports_by_xi'])
    elif branch == 'probe':
        if selected is None:
            raise ValueError('No degree of freedom: do not run an identical probe')
        q = probe_configuration(support['supports_by_xi'], selected, epsilon=plan['composition']['epsilon'])['q_by_xi']
    else:
        decision = read_json(root / 'configuration-decision.json')
        if not decision['changed'] or not decision['development_complete']:
            raise ValueError('A new configured update requires a known changed configuration')
        q = decision['q_by_xi']
    composition = materialize_composition(entries, declaration, records, q_by_xi=q, selected_block=selected)
    write(output / 'composition.json', composition)
    write(output / 'consumption.json', {'branch': branch, 'consumption_id': 'v025-' + branch,
        'raw_entries': common['entries'], 'declaration': common['declaration'], 'support': common['support'],
        'restored_state_tensor_digest': state_digest, 'restored_checkpoint': restored,
        'same_complete_origin': True, 'composition': reference(output / 'composition.json'),
        'original_episode_window_call_identities_preserved': True})
    owner.begin_window(declaration['window_id'])
    task(output, 'v025-' + branch + ':one-update', 'update')
    update = owner.update_window(entries, output / 'update', composition=composition,
                                post_update_selector=select_post_update_rows)
    write(output / 'update-result.json', update)
    if (update['status'] not in ACCEPTED or owner.actor_steps != 2 + update.get('actor_optimizer_steps', 0)
            or owner.critic_steps != 2 + update.get('critic_optimizer_steps', 0)
            or owner.actor_steps > 3 or owner.critic_steps > 3):
        raise ValueError('Unqualified single update: no alternative checkpoint may replace it')
    task(output, 'v025-' + branch + ':save', 'boundary')
    signal = summarize_work_signals(entries, output / 'update')
    signal.update(version='member-composition-work-signals-v0.25',
        scope='Terminal MC targets and original denominators; composition scales actor loss, not reward or causal action value.',
        composition_reference=reference(output / 'composition.json'))
    write(output / 'work-signals.json', signal)
    final = publish_checkpoint(owner, output / 'checkpoint-final', root, branch)
    write(root / f'{branch}-complete.json', {'source': code_identity(), 'endpoint': reference(root / 'checkpoints' / f'{branch}.json'),
        'update': reference(output / 'update-result.json'), 'consumption': reference(output / 'consumption.json')})
    return {'status': 'complete', 'update': update, 'final_checkpoint': final,
            'training_episode_consumptions': 16, 'actual_new_episodes': 0,
            'common_complete_state_matches': True, 'composition_reference': reference(output / 'composition.json')}


def evaluate(owner, plan, catalog, output, endpoint, purpose):
    from proworksim.templates.retail_collaboration_v025 import assess_episode, build_case, runtime as make_runtime

    rows, identity = [], owner.freeze_identity()
    for slot in catalog[purpose + '_slots']:
        task(output, f'{purpose}:{endpoint}:{slot["slot_id"]}', 'episode')
        folder = output / slot['slot_id']
        prepared = build_case(slot['case_id'], folder, assets_root=plan['assets_root'])
        snapshot = owner.capture_evaluation_state()
        owner.begin_window(f'v025-{purpose}-{endpoint}-{slot["slot_id"]}')
        owner.reseed(slot['seed'], label=f'{purpose}:{endpoint}:{slot["slot_id"]}')
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
            if (not assessment['eligible'] or not guard['learning_unchanged'] or not guard['rng_restored_exactly']
                    or owner.freeze_identity() != identity):
                raise ValueError('Unknown outcome or frozen evaluation state mismatch')
        except BaseException as error:
            row.update(status='interrupted_or_unassessed', ended_at=time.time(), error=str(error))
            write(folder / 'public-capture.json', capture)
            write(folder / 'runtime.json', runtime.snapshot())
            write(output / 'progress.json', rows)
            raise
        write(output / 'progress.json', rows)
        print(json_bytes({'stage': purpose, 'endpoint': endpoint, 'closed_slots': len(rows)}).decode(), flush=True)
    return {'status': 'complete', 'rows': rows, 'actual_new_episodes': len(rows)}


def continuation(owner, plan, catalog, output, root, endpoint):
    from proworksim.collaboration_training_v025 import diagnose_support, training_admission

    restore_endpoint(owner, root, endpoint)
    admission = training_admission(catalog, checked(plan['source_pin']), purpose='continuation_training')
    write(output / 'admission.json', admission)
    snapshot = owner.capture_evaluation_state()
    contract = {'window_id': 'v025-next-' + endpoint, 'slots': catalog['continuation_slots']}
    entries, declaration, rows = collect_window(owner, catalog, contract, admission, output / 'collection', plan['assets_root'])
    support = diagnose_support(entries, declaration)
    support.pop('records', None)
    guard = owner.finish_evaluation_guard(snapshot)
    guard['scope'] = 'New on-policy continuation and support diagnosis only; zero further optimizer steps.'
    if not guard['learning_unchanged'] or not guard['rng_restored_exactly']:
        raise ValueError('No second optimization is authorized')
    owner.phase = 'idle'
    write(output / 'support.json', support)
    write(output / 'state-guard.json', guard)
    return {'status': 'complete', 'actual_new_episodes': len(rows), 'extra_updates': 0,
            'support_reference': reference(output / 'support.json'), 'guard': guard}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--stage', choices=STAGES, required=True)
    args = parser.parse_args()
    plan, root, output = read_json(args.plan), args.run_root.resolve(), args.output.resolve()
    source = code_identity()
    if plan['version'] != VERSION or source['code_dirty'] or os.environ.get('CUDA_VISIBLE_DEVICES') not in set(map(str, range(8))):
        raise ValueError('A frozen committed source and single physical GPU are required')
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.templates.retail_collaboration_v025 import registry
    from proworksim import functional_qwen_v022
    if digest(Path(functional_qwen_v022.__file__).read_bytes()) != plan['qualified_functional_sha256']:
        raise ValueError('The already qualified model path changed')
    for value in plan['qualification_refs']:
        checked(value)
    prior = read_json(checked(plan['prior_model_plan']))
    catalog = read_json(checked(plan['catalog']))
    if registry() != catalog:
        raise ValueError('Predeclared materials changed')
    recipe = plan['base_recipe']
    if recipe != read_json(checked(plan['prior_owner']))['recipe'] or recipe['credit_assignment'] != 'terminal_mc':
        raise ValueError('Keep the exact existing terminal MC learner recipe')
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'stage': args.stage, 'status': 'loading', 'source_before': source,
              'plan': reference(args.plan), 'started_at': time.time(), 'model_api_calls': 0}
    write(output / 'report.json', report)
    owner = None
    try:
        task(output, args.stage + ':loading', 'loading')
        owner = DeterministicCandidateActor.from_candidate(prior['model'], manifest=checked(prior['manifest']),
            profile=prior['runtime_profile'], recipe=recipe, output=output / 'resident')
        report.update(status='running')
        write(output / 'report.json', report)
        if args.stage == 'support':
            result = support_collection(owner, plan, catalog, output, root)
        elif args.stage.startswith('train_'):
            result = train_branch(owner, plan, catalog, output, root, args.stage[6:])
        elif args.stage.startswith('next_'):
            result = continuation(owner, plan, catalog, output, root, args.stage[5:])
        else:
            kind, endpoint = args.stage.split('_', 1)
            report['restored_checkpoint'] = restore_endpoint(owner, root, endpoint)
            result = evaluate(owner, plan, catalog, output, endpoint, 'development' if kind == 'dev' else 'confirmation')
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
