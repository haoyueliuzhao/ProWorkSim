"""Four real reserved training fragments, at most one update, two new dev fragments.

N1, paired W1 and the token projection are mandatory independent qualifications.
Each active member has four opportunities in this explicitly short new protocol;
no role acts automatically and no E/W1/CPU trajectory becomes a teacher target.
"""
import argparse
import copy
import os
from pathlib import Path
import time
from types import SimpleNamespace

from proworksim.audit import code_identity
from proworksim.collaboration_training_v022 import export_training_episode, projection_summary, training_admission
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.online_support import declare_window
from proworksim.storage import digest, json_bytes, read_json
from scripts.evaluate_work_v022 import checked, reference, task, write

VERSION = 'conditional-real-update-bridge-v0.22'
OPPORTUNITIES = 4


def fragment_runtime(owner, prepared, folder):
    from proworksim.work_view_v022 import runtime

    # Separate Gamma cap; actual case facts and reward stay unchanged. The
    # public policy identity records the actual smaller role opportunity limit.
    view = SimpleNamespace(world=prepared.world, scenario=prepared.scenario,
        case={**prepared.case, 'role_decision_limits': {r: OPPORTUNITIES for r in prepared.active_roles}})
    return runtime(owner, view, folder, 'compact_work')


def scenario_with_fragment(prepared, purpose):
    scenario = copy.deepcopy(prepared.scenario)
    scenario.setdefault('variation', {})['bridge_fragment'] = {
        'version': VERSION, 'purpose': purpose, 'per_active_role_opportunities': OPPORTUNITIES,
        'scope': 'Short predeclared fragment of the same fixed-material responsibility; partial outcomes and failures retained.',
        'not_W1_episode_budget': True}
    return scenario


def train_window(owner, catalog, admission, output, assets_root):
    from proworksim.templates.retail_collaboration_v022 import build_case

    identity = owner.begin_window('v022-b1-train')
    items, specs = [], []
    for i, case in enumerate(catalog['reserved_training']):
        folder = output / f'train-{i}'
        prepared = build_case(case, folder, assets_root=assets_root)
        runtime, capture, _ = fragment_runtime(owner, prepared, folder)
        scenario = scenario_with_fragment(prepared, 'online_training')
        sid = f'train-{i}'
        specs.append({'slot_id': sid, 'xi_id': case['case_id'],
                      'xi_fingerprint': digest(json_bytes({'case': case, 'initial': prepared.prefix['prepared_business_state_sha256']})),
                      'active_members': list(prepared.active_roles), 'policies': runtime.policy_identities,
                      'mapping_spec_id': 'base-Q-equals-B-no-composition-reconfiguration-v022'})
        items.append((prepared, folder, runtime, capture, scenario))
    declaration = declare_window('v022-b1-train', actor_identity=identity,
        gamma_identity={'version': VERSION, 'harness': 'native_v22_compact_work', 'recipe': owner.recipe,
                        'per_active_role_opportunities': OPPORTUNITIES, 'training_admission': admission,
                        'seeds': [202609290200+i for i in range(4)], 'source': code_identity()}, slot_specs=specs)
    write(output / 'train-declaration.json', declaration)
    entries, rows = [], []
    for i, (prepared, folder, runtime, capture, scenario) in enumerate(items):
        task(output, f'B1-train-{i}')
        owner.reseed(202609290200+i, label=f'train-{i}')
        row = {'slot': i, 'case_id': prepared.case['case_id'], 'status': 'started', 'started_at': time.time()}
        rows.append(row)
        write(output / 'train-progress.json', rows)
        episode = folder / 'episode'
        try:
            begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_nodes=['TEAM::build'],
                          work_ids=[], scenario=scenario, policies=runtime.policy_identities)
            boundary = run_fragment(prepared, runtime, external_tick_per_sweep=1)
            finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
            write(folder / 'public-capture.json', capture)
            write(folder / 'runtime.json', runtime.snapshot())
            entry, proof = export_training_episode(prepared, episode, declaration=declaration,
                                                   slot_id=f'train-{i}', captured=capture, admission=admission)
            write(folder / 'team-rollout.json', entry['rollout'])
            write(folder / 'projection.json', proof)
            entries.append(entry)
            row.update(status='closed', ended_at=time.time(), boundary=boundary, projection=projection_summary(entry),
                       reward=entry['reward'], record_validity=proof['record_validity'])
            if (proof['record_validity'] is not True or not entry['reward']['eligible']
                    or proof.get('has_complete_trainable_actual_members') is not True):
                raise ValueError('Unknown or untrusted bridge evidence; no partial-window update')
        except BaseException as error:
            row.update(status='interrupted_or_unassessed', ended_at=time.time(), error=str(error))
            write(folder / 'public-capture.json', capture)
            write(folder / 'runtime.json', runtime.snapshot())
            write(output / 'train-progress.json', rows)
            raise
        write(output / 'train-progress.json', rows)
        print(json_bytes({'train_slot': i, 'reward': entry['reward']['reward']}).decode(), flush=True)
    return entries, rows


def post_development(owner, catalog, output, assets_root):
    from proworksim.templates.retail_collaboration_v022 import assess_episode, build_case

    rows = []
    for i, case in enumerate(catalog['reserved_bridge']):
        task(output, f'B1-post-{i}')
        folder = output / f'post-{i}'
        prepared = build_case(case, folder, assets_root=assets_root)
        before = owner.capture_evaluation_state()
        identity = owner.begin_window(f'v022-b1-post-{i}')
        runtime, capture, _ = fragment_runtime(owner, prepared, folder)
        scenario = scenario_with_fragment(prepared, 'post_update_development_not_effect_estimate')
        owner.reseed(202609290300+i, label=f'post-{i}')
        episode = folder / 'episode'
        row = {'slot': i, 'case_id': case['case_id'], 'actor_identity': identity,
               'status': 'started', 'started_at': time.time()}
        rows.append(row)
        write(output / 'post-progress.json', rows)
        try:
            begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_nodes=['TEAM::build'],
                          work_ids=[], scenario=scenario, policies=runtime.policy_identities)
            boundary = run_fragment(prepared, runtime, external_tick_per_sweep=1)
            finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
            assessment = assess_episode(episode)
            write(folder / 'assessment.json', assessment)
            write(folder / 'public-capture.json', capture)
            write(folder / 'runtime.json', runtime.snapshot())
            owner.finish_evaluation([{'slot_id': f'post-{i}', 'active_members': prepared.active_roles,
                                      'reward': assessment}], folder / 'frozen-evaluation')
            guard = owner.finish_evaluation_guard(before)
            row.update(status='closed', ended_at=time.time(), assessment=assessment, boundary=boundary,
                       evaluation_guard=guard)
            if not assessment['eligible'] or not guard['learning_unchanged'] or not guard['rng_restored_exactly']:
                raise ValueError('Post-update evaluation record or frozen guard failed')
        except BaseException as error:
            row.update(status='interrupted_or_unassessed', ended_at=time.time(), error=str(error))
            write(output / 'post-progress.json', rows)
            raise
        write(output / 'post-progress.json', rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = read_json(args.plan)
    if (plan.get('version') != VERSION or plan.get('per_active_role_opportunities') != OPPORTUNITIES
            or plan.get('max_actor_steps') != 1 or plan.get('max_critic_steps') != 1 or plan.get('model_api_calls') != 0):
        raise ValueError('Bridge finite contract changed')
    from scripts.run_bounded_v022 import validate
    qualification_plan = {**plan['supervisor_qualification'], 'experiment_plan': reference(args.plan)}
    validate(qualification_plan)
    from proworksim.bridge_admission_v022 import validate_bridge_qualification
    qualification = validate_bridge_qualification(qualification_plan)
    from proworksim.collaboration_actor_v022 import FunctionalCandidateActor
    from proworksim import functional_qwen_v022
    from proworksim.templates.retail_collaboration_v022 import registry
    catalog = read_json(checked(plan['catalog']))
    if catalog != registry():
        raise ValueError('Reserved training/development catalog changed')
    if digest(Path(functional_qwen_v022.__file__).read_bytes()) != plan['qualified_functional_module']['sha256']:
        raise ValueError('Bridge learner is not the N1 qualified exact implementation')
    checked(plan['qualified_functional_module'])
    admission = training_admission(catalog, checked(plan['source_pin']))
    prior = read_json(checked(plan['prior_model_plan']))
    source = code_identity()
    if source['code_dirty'] or os.environ.get('CUDA_VISIBLE_DEVICES') not in set(map(str, range(8))):
        raise ValueError('Freeze bridge source and bind one physical GPU')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'status': 'loading', 'source_before': source, 'plan': reference(args.plan),
              'training_admission': admission, 'N1_qualified_module': plan['qualified_functional_module'],
              'prerequisite_qualification': qualification,
              'learner_execution_profile': functional_qwen_v022.CONTRACT,
              'legacy_update_report_terminology': 'full-sequence recomputation in inherited update diagnostics means complete original context through this functional recurrent learner, not the old no-cache full forward.',
              'max_actor_steps': 1, 'max_critic_steps': 1, 'model_api_calls': 0,
              'scope': 'New combination integration only, not a learning-effect comparison or ID-VTDO intervention'}
    write(output / 'report.json', report)
    owner = None
    try:
        task(output, 'B1-model-loading')
        owner = FunctionalCandidateActor.from_candidate(prior['model'], manifest=checked(prior['manifest']),
            profile=prior['runtime_profile'], recipe=prior['recipe'], output=output / 'resident')
        expected = read_json(checked(plan['initial_identity_response']))['response']['actor_identity']
        if owner.freeze_identity() != expected or owner.recipe['credit_assignment'] != 'terminal_mc':
            raise ValueError('Bridge changed the shared initialization or base credit recipe')
        report.update(initial_actor_identity=owner.freeze_identity(), status='collecting_train')
        write(output / 'report.json', report)
        entries, rows = train_window(owner, catalog, admission, output, plan['assets_root'])
        report.update(train_rows=rows, status='updating')
        write(output / 'report.json', report)
        task(output, 'B1-single-shared-update')
        update = owner.update_window(entries, output / 'update')
        report.update(update=update, after_update_actor_identity=owner.freeze_identity())
        write(output / 'report.json', report)
        if owner.actor_steps > 1 or owner.critic_steps > 1:
            raise ValueError('More than one declared shared update')
        acceptable = {'updated', 'zero_step_zero_actor_advantage_or_gradient', 'zero_step_no_admitted_own_actions'}
        if update['status'] not in acceptable:
            report['status'] = 'stopped_update_not_qualified'
            return 2
        report['checkpoint'] = owner.save_checkpoint(output / 'checkpoint')
        report.update(status='post_update_development')
        write(output / 'report.json', report)
        report['post_rows'] = post_development(owner, catalog, output, plan['assets_root'])
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
        write(output / 'report.json', report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
