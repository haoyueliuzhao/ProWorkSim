"""Predeclared paired frozen work comparison; same actor, budgets and facts."""
import argparse
import copy
import os
from pathlib import Path
import time

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.storage import atomic_write, digest, json_bytes, read_json

VERSION = 'paired-work-presentation-v0.22'


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': digest(path.read_bytes())}


def checked(value):
    path = Path(value['path'])
    if reference(path) != value:
        raise ValueError('Frozen input changed')
    return path


def task(out, name):
    write(out / 'task.json', {'task': name, 'started_at': time.time(), 'pid': os.getpid()})


def paired_order(catalog):
    result = []
    for i, case in enumerate(catalog['situations']):
        arms = ['original_history', 'compact_work']
        if i % 2:
            arms.reverse()
        result.extend({'slot': 2*i+j, 'case_id': case['case_id'], 'arm': arm,
                       'sampling_seed': 202609290100 + i} for j, arm in enumerate(arms))
    return result


def execute(owner, catalog, output, order, *, assets_root=None):
    from proworksim.templates.retail_collaboration_v022 import assess_episode, build_case
    from proworksim.work_view_v022 import runtime as make_runtime

    if order != paired_order(catalog) or len(order) != 12:
        raise ValueError('Use all six predeclared cases with alternating paired order')
    rows, initial = [], owner.freeze_identity()
    for row_spec in order:
        row = copy.deepcopy(row_spec)
        i = row['slot']
        task(output, f'W1-{i}-{row["arm"]}')
        folder = output / f'slot-{i}'
        prepared = build_case(row['case_id'], folder, assets_root=assets_root)
        snapshot = owner.capture_evaluation_state()
        identity = owner.begin_window(f'v022-w1-{i}')
        if identity != initial:
            raise ValueError('Frozen actor changed between paired episodes')
        runtime, captured, _ = make_runtime(owner, prepared, folder, row['arm'])
        scenario = copy.deepcopy(prepared.scenario)
        scenario.setdefault('variation', {})['paired_evaluation'] = {
            'version': VERSION, 'arm': row['arm'], 'sampling_seed': row['sampling_seed'],
            'training_projection': False, 'old_v021_reassessment': False,
        }
        owner.reseed(row['sampling_seed'], label=f'{row["case_id"]}:{row["arm"]}')
        episode = folder / 'episode'
        row.update(status='started', started_at=time.time(), actor_identity=identity)
        rows.append(row)
        write(output / 'progress.json', rows)
        try:
            begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(),
                          work_nodes=['TEAM::build'], work_ids=[], scenario=scenario,
                          policies=runtime.policy_identities)
            boundary = run_fragment(prepared, runtime, external_tick_per_sweep=1)
            finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
            write(folder / 'public-capture.json', captured)
            write(folder / 'runtime.json', runtime.snapshot())
            assessment = assess_episode(episode)
            write(folder / 'assessment.json', assessment)
            row.update(status='closed', boundary=boundary, assessment=assessment,
                       assessment_ref=reference(folder / 'assessment.json'), ended_at=time.time())
            owner.finish_evaluation([{'slot_id': str(i), 'active_members': prepared.active_roles,
                                      'reward': assessment}], folder / 'frozen-evaluation')
            guard = owner.finish_evaluation_guard(snapshot)
            write(folder / 'evaluation-guard.json', guard)
            row['evaluation_guard'] = guard
            if not guard['learning_unchanged'] or not guard['rng_restored_exactly']:
                raise ValueError('Frozen learning or RNG state check failed')
        except BaseException as error:
            row.update(status='interrupted_or_unassessed', ended_at=time.time(),
                       error={'type': type(error).__name__, 'message': str(error)})
            write(folder / 'public-capture.json', captured)
            write(folder / 'runtime.json', runtime.snapshot())
            write(output / 'progress.json', rows)
            raise
        write(output / 'progress.json', rows)
        print(json_bytes({'slot': i, 'case_id': row['case_id'], 'arm': row['arm'],
                          'reward': assessment['reward'], 'completed': assessment['completed']}).decode(), flush=True)
        if not assessment['eligible']:
            return {'status': 'stopped_unassessable', 'rows': rows,
                    'not_started': order[len(rows):]}
    return {'status': 'complete', 'rows': rows, 'not_started': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    plan = read_json(args.plan)
    if plan['version'] != VERSION or plan['parameter_updates'] != 0 or plan['model_api_calls'] != 0:
        raise ValueError('Only the fixed new paired frozen evaluation is allowed')
    from proworksim.templates.retail_collaboration_v022 import registry
    catalog = read_json(checked(plan['catalog']))
    if registry() != catalog or plan['order'] != paired_order(catalog):
        raise ValueError('Paired cases/order changed')
    for value in plan.get('source_refs', []):
        checked(value)
    prior = read_json(checked(plan['prior_model_plan']))
    source = code_identity()
    if source['code_dirty'] or os.environ.get('CUDA_VISIBLE_DEVICES') not in set(map(str, range(8))):
        raise ValueError('Use frozen source and exactly one physical card')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'status': 'loading', 'source_before': source, 'plan': reference(args.plan),
              'parameter_updates': 0, 'model_api_calls': 0, 'planned_episodes': 12,
              'training_projection': False, 'order': plan['order']}
    write(out / 'report.json', report)
    owner = None
    try:
        from proworksim.candidate_runtime_v0201 import CandidateActor
        task(out, 'W1-model-loading')
        owner = CandidateActor.from_candidate(prior['model'], manifest=checked(prior['manifest']),
            profile=prior['runtime_profile'], recipe=prior['recipe'], output=out / 'resident')
        expected = read_json(checked(plan['initial_identity_response']))['response']['actor_identity']
        if owner.freeze_identity() != expected:
            raise ValueError('Actual W1 initialization differs from v020.1 candidate')
        report.update(status='evaluating', initial_actor_identity=owner.freeze_identity())
        write(out / 'report.json', report)
        report.update(execute(owner, catalog, out, plan['order'], assets_root=plan['assets_root']))
    except BaseException as error:
        report.update(status='interrupted_or_error', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        report.update(final_actor_identity=None, actor_steps=owner.actor_steps if owner else None,
                      critic_steps=owner.critic_steps if owner else None)
        if owner:
            try:
                report['final_actor_identity'] = owner._make_identity()
                report['final_identity_matches_initial'] = report['final_actor_identity'] == report.get('initial_actor_identity')
            except BaseException as error:
                report['identity_check_error'] = str(error)
        try:
            report['source_after'] = code_identity()
            report['source_unchanged'] = source == report['source_after']
        except BaseException as error:
            report['source_check_error'] = str(error)
        write(out / 'report.json', report)
    return 0 if report['status'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
