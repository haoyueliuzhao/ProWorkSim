"""Mechanical application of the registered complete-screen selection ordering.

This reads saved measurements only. It neither scores worlds nor imputes missing
conditions, trains a model, or substitutes inference failure for business failure.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from scripts.learning_report_v015 import build_report, write_report
from scripts.learning_resources_v015 import resource_report
from scripts.run_candidate_screen_v015 import preflight_outcome, stage_commands

CANDIDATES = {'qwen25-7b', 'qwen35-9b', 'qwen38-27b'}
NEW_CANDIDATES = {'qwen35-9b', 'qwen38-27b'}


def ref(path):
    path = Path(path).resolve()
    payload = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}


GUARD_KEYS = {'actor', 'critic', 'actor_optimizer', 'critic_optimizer', 'actor_steps', 'critic_steps'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as error:
        raise ValueError('Required original record unavailable: ' + str(path)) from error


def same_path(left, right):
    return bool(left and right and Path(left).resolve() == Path(right).resolve())


def validate_guard(window):
    guard = window.get('evaluation_guard') or {}
    before, after = guard.get('learning_before_sha256'), guard.get('learning_after_sha256')
    steps = window.get('steps') or {}
    increments = steps.get('recorded_increment_fields') or {}
    require(window.get('mode') == 'evaluate' and window.get('stage') == 'screen'
            and guard.get('learning_unchanged') is True and guard.get('rng_restored_exactly') is True
            and isinstance(before, dict) and GUARD_KEYS <= set(before)
            and all(isinstance(v, str) and v for v in before.values()) and before == after
            and isinstance(guard.get('rng_before_sha256'), str) and bool(guard['rng_before_sha256'])
            and guard['rng_before_sha256'] == guard.get('rng_after_restore_sha256')
            and steps.get('issues') == []
            and all(type(steps.get(k)) is int and steps[k] == 0 for k in ('actor', 'critic'))
            and all(type(increments.get(k)) is int and increments[k] == 0
                    for k in ('actor_optimizer_steps', 'critic_optimizer_steps')),
            'Actual screen learning/RNG guard or recorded zero-step evidence not confirmed')


def validated_readiness(supervisor: dict, report: dict) -> dict[str, bool]:
    """Return {new_candidate_id: actual_S0_training_ready}, after exact binding.

    Reads original JSON and small hash-addressed calibration evidence only. No
    weights/checkpoint tensors are loaded; numerical probabilities are not rerun.
    Missing, contradictory or foreign records raise ValueError, never False/zero.
    """
    jobs = supervisor.get('jobs', [])
    configs = supervisor.get('config', {}).get('candidates', [])
    require(supervisor.get('status') == 'complete' and len(jobs) == len(configs) == 2
            and {j.get('name') for j in jobs} == {c.get('name') for c in configs} == NEW_CANDIDATES
            and all(j.get('status') == 'complete' for j in jobs),
            'Both new candidate screens must finish; absent conditions are never zeros')
    runs = report.get('runs', [])
    require(len(runs) == 3 and {r.get('candidate_id') for r in runs} == CANDIDATES,
            'All three distinct, predeclared conditions are required')
    config = supervisor['config']
    source = Path(config['source']).resolve()
    source_record = supervisor.get('source_identity') or {}
    commit = source_record.get('commit')
    require(isinstance(commit, str) and bool(commit)
            and isinstance(config.get('source_commit'), str) and bool(config['source_commit'])
            and commit.startswith(config['source_commit']), 'Queue frozen source identity is missing or inconsistent')
    source_files = source_record.get('files') or {}
    inspected = {}

    def frozen_file(path):
        resolved = str(Path(path).resolve())
        if resolved not in inspected:
            inspected[resolved] = ref(path)
        require(source_files.get(resolved) == inspected[resolved]['sha256'],
                'Selected source/protocol file differs from original queue freeze: ' + resolved)
        return inspected[resolved]

    readiness = {}
    try:
        for candidate in sorted(NEW_CANDIDATES):
            job = next(c for c in configs if c['name'] == candidate)
            state = next(j for j in jobs if j['name'] == candidate)
            run = next(r for r in runs if r['candidate_id'] == candidate)
            require(run.get('runner_status') == 'complete'
                    and same_path(run.get('root'), job['screen_output']),
                    'S1 output does not match its candidate queue binding')
            protocol_path = Path(job['screen_protocol'])
            protocol_ref = frozen_file(protocol_path)
            protocol = read_json(protocol_path)
            runtime = protocol['runtime']
            expected_script = {'qwen_hybrid_chatstop': 'candidate_preflight_v0151.py',
                               'qwen_hybrid': 'candidate_preflight_v015.py'}.get(runtime.get('kind'))
            script = Path(job.get('preflight_script', source/'scripts/candidate_preflight_v015.py'))
            require(expected_script is not None and script.resolve() == source/'scripts'/expected_script,
                    'S0 runtime/script differs from S1 runtime')
            frozen_file(script)
            frozen_file(source/'scripts/online_learning_v015.py')
            frozen_file(source/'src/proworksim/candidate_runtime_v015.py')
            if runtime['kind'] == 'qwen_hybrid_chatstop':
                frozen_file(source/'src/proworksim/candidate_runtime_v0151.py')
            if runtime.get('profile_source'):
                profile_ref = frozen_file(source/runtime['profile_source'])
                require(profile_ref['sha256'] == runtime.get('profile_sha256')
                        and read_json(profile_ref['path']) == runtime['profile'], 'Frozen profile source differs')
            require(same_path(run.get('protocol_ref', {}).get('path'), protocol_path)
                    and run.get('protocol_ref', {}).get('sha256') == protocol_ref['sha256']
                    and read_json(Path(run['root'])/'online/protocol.json') == protocol
                    and read_json(Path(run['root'])/'launch-protocol.json') == protocol
                    and run.get('saved_protocol_equals_declared') is True
                    and protocol.get('candidate_id') == candidate and protocol.get('condition') == run.get('condition'),
                    'S1 actual/declared protocol differs from original queue protocol')
            before, after = run.get('source_before') or {}, run.get('source_after') or {}
            require(before.get('code_commit') == commit and before.get('code_dirty') is False
                    and before.get('source_tree_sha256') and before == after
                    and (run.get('source_comparison') or {}).get('unchanged') is True,
                    'S1 source does not match the original S0 queue source')
            for stage in ('preflight', 'screen'):
                entry = state.get(stage) or {}
                actual_launch = read_json(Path(job[stage+'_launch']).with_suffix('.launch.json'))
                _, command = stage_commands(config, job, stage)
                require(entry.get('status') == 'finished' and entry.get('exit_code') == 0
                        and actual_launch.get('exit_code') == 0 and entry.get('launch_meta') == actual_launch
                        and actual_launch.get('command') == command
                        and same_path(actual_launch.get('cwd'), source)
                        and actual_launch.get('CUDA_VISIBLE_DEVICES') == ','.join(map(str, job['gpus']))
                        and same_path(actual_launch.get('PYTHONPATH'), source/'src'),
                        'Actual ' + stage + ' launch does not match its frozen candidate command')
                if stage == 'screen':
                    require(run.get('launch_record') == actual_launch,
                            'S1 report launch differs from the queue-completed launch')
            preflight_root = Path(job['preflight_output'])
            original = read_json(preflight_root/'report.json')
            pre_owner = read_json(preflight_root/'owner/owner.json')
            screen_owner = read_json(Path(job['screen_output'])/'resident/owner.json')
            manifest = ref(job['weight_manifest'])
            manifest_body = read_json(job['weight_manifest'])
            require(original.get('candidate') == job['candidate']
                    and runtime['profile'].get('candidate_id') == job['candidate']
                    and original.get('profile') == pre_owner.get('inference_profile') == screen_owner.get('inference_profile')
                    and all(pre_owner['inference_profile'].get(k) == v for k, v in runtime['profile'].items())
                    and pre_owner.get('recipe') == screen_owner.get('recipe') == protocol.get('recipe')
                    and pre_owner.get('base_identity') == screen_owner.get('base_identity')
                    and pre_owner.get('initial_actor_identity') == screen_owner.get('initial_actor_identity')
                    and isinstance(pre_owner.get('initial_actor_identity'), dict)
                    and pre_owner['initial_actor_identity'].get('base_manifest_sha256') == manifest['sha256']
                    and run.get('owner') == screen_owner,
                    'S0/S1 candidate, runtime, recipe, profile or initial actor identity differs')
            base = pre_owner['base_identity']
            require(same_path(base.get('path'), job['model_path'])
                    and base.get('manifest') == manifest
                    and base.get('revision') == manifest_body.get('declared_hf_revision'),
                    'S0/S1 model or weight manifest does not match the registered asset')
            saved = state['preflight'].get('outcome') or {}
            observed = preflight_outcome(preflight_root, 0, job=job)
            for key in ('inference_ready_for_screen', 'training_ready', 'probability_gate_passed',
                        'backward_gate_passed', 'checkpoint_serialized_reload_exact', 'actual_generations',
                        'chat_stop_gate_passed', 'original_prompt_replay_gate_passed', 'recorded_errors'):
                require(saved.get(key) == observed.get(key), 'Original S0 outcome differs from its saved evidence: ' + key)
            require(observed['inference_ready_for_screen'] is True
                    and type(state.get('training_ready')) is bool
                    and state['training_ready'] == observed['training_ready'] == original.get('training_ready')
                    and original.get('inference_ready') is True
                    and original.get('actor_steps') == original.get('critic_steps') == 0,
                    'S0 training readiness is missing or contradicts the original calibration')
            if state['training_ready']:
                checkpoint = read_json(preflight_root/'unchanged-checkpoint/checkpoint.json')
                require(checkpoint == original.get('checkpoint')
                        and checkpoint.get('serialized_reload_exact') is True
                        and checkpoint.get('actor_identity') == pre_owner['initial_actor_identity']
                        and checkpoint.get('actor_steps') == checkpoint.get('critic_steps') == 0
                        and original.get('checkpoint_restored') is True,
                        'S0 saved/reloaded checkpoint metadata does not identify the same untouched actor')
            readiness[candidate] = state['training_ready']
    except (KeyError, TypeError, StopIteration, OSError, AttributeError) as error:
        raise ValueError('Missing or malformed original S0/S1 binding evidence') from error
    return readiness


def choose(report, resources, readiness):
    """Rank full responsibility counts; retain separate inference/training axes."""
    runs = report['runs']
    if len(runs) != 3 or {r['candidate_id'] for r in runs} != CANDIDATES:
        raise ValueError('All three distinct, predeclared conditions are required')
    if report.get('unknown_step_runs') or report['observed_optimizer_step_increments'] != {'actor': 0, 'critic': 0}:
        raise ValueError('Screening must be measured pure evaluation')
    resource_by_name = {r['name']: r for r in resources['runs']}
    rows = []
    paired_slots = None
    for run in runs:
        counts = run['progress']['counts']
        if (run['runner_status'] != 'complete' or run.get('issues')
                or run.get('saved_protocol_equals_declared') is not True
                or run.get('source_comparison', {}).get('unchanged') is not True
                or counts['planned'] != 36 or counts['closed_known'] != 36
                or run['progress']['completed_work_measured_count'] != 36
                or run['unknown_step_windows']):
            raise ValueError('Complete immutable 36-case records required: ' + run['name'])
        slots = []
        for window in run['windows']:
            validate_guard(window)
            slots.extend(window['slots'])
        case_repeats = Counter((r['case_id'], r['repeat']) for r in slots)
        if (len(case_repeats) != 36 or set(case_repeats.values()) != {1}
                or Counter(r['task'] for r in slots) != {t: 9 for t in ('implement', 'review', 'pair', 'chain')}
                or any(r['state'] != 'closed_known' or r['record_validity'] is not True
                       or type(r['reward'].get('completed')) is not bool for r in slots)):
            raise ValueError('Task/repetition identity or original record validity differs')
        require(all(r['case_id'] == f"uci-development-f{r['fact']}-{r['task']}"
                    and type(r.get('fact')) is int and type(r.get('repeat')) is int
                    and type(r.get('sampling_seed')) is int for r in slots),
                'Frozen development cases and explicit sampling seeds are required')
        paired = sorted((r['case_id'], r['task'], r['fact'], r['repeat'], r['sampling_seed']) for r in slots)
        if paired_slots is None:
            paired_slots = paired
        require(paired == paired_slots, 'Three conditions must use the same frozen case/repetition/sampling-seed inventory')
        launch = run['launch_record']
        key = Path(run['declared_job']['launch']).name
        resource = resource_by_name[key]
        allocated = resource['allocated_device_seconds']
        if (type(allocated) not in (int, float) or not math.isfinite(allocated) or allocated <= 0
                or launch.get('exit_code') != 0 or resource['pid'] != launch['pid']):
            raise ValueError('Measured completed resource record required')
        details = []
        for task in ('implement', 'review', 'pair', 'chain'):
            for fact in range(3):
                own = [r for r in slots if r['task'] == task and r['fact'] == fact]
                if len(own) != 3 or {r['repeat'] for r in own} != {0, 1, 2}:
                    raise ValueError('All three factual repetitions must be observed')
                details.append({'task': task, 'fact': fact,
                    'completed_by_repeat': [next(r['reward']['completed'] for r in own if r['repeat'] == i) for i in range(3)]})
        candidate = run['candidate_id']
        ready = readiness.get(candidate)
        if candidate in NEW_CANDIDATES and not isinstance(ready, bool):
            raise ValueError('New candidate needs its actual independent S0 training outcome')
        rows.append({'candidate_id': candidate, 'condition': run['condition'], 'run_name': run['name'],
            'screen_protocol': run['protocol_ref'], 'run_root': run['root'],
            'primary_completed_implement_review': sum(r['reward']['completed'] for r in slots if r['task'] in {'implement', 'review'}),
            'secondary_completed_pair_chain': sum(r['reward']['completed'] for r in slots if r['task'] in {'pair', 'chain'}),
            'mean_reward_auxiliary_only': run['progress']['mean_reward'],
            'allocated_device_seconds': allocated, 'training_ready': ready,
            'eligibility': 'candidate_for_new_shared_initialization' if candidate in NEW_CANDIDATES and ready else
                           'training_integration_not_ready' if candidate in NEW_CANDIDATES else 'historical_model_reference',
            'fact_repeat_completions': details,
            'sort_key': [-sum(r['reward']['completed'] for r in slots if r['task'] in {'implement', 'review'}),
                         -sum(r['reward']['completed'] for r in slots if r['task'] in {'pair', 'chain'}), allocated, candidate]})
    ranking = sorted(rows, key=lambda r: r['sort_key'])
    eligible = [r for r in ranking if r['eligibility'] == 'candidate_for_new_shared_initialization']
    return {'version': 'candidate-selection-v0.15', 'status': 'selected' if eligible else 'no_training_ready_candidate',
        'selected': eligible[0] if eligible else None, 'all_capability_results_ranked': ranking,
        'decision_rule': 'Complete implement+review count, then complete pair+chain count, then measured allocated device seconds. Mean R and partial delivery do not determine rank.',
        'scope': 'Development initialization choice among the registered new candidates. Historical 7B remains in the capability table; S0 integration failure is not a business score. N0 is still required before N1.',
        'repeat_scope': 'Every fact and repetition remains visible; counts do not establish universal competence, a powered performance difference or learning benefit.',
        'no_outcome_based_extension': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--supervisor', type=Path, required=True)
    parser.add_argument('--launch-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    supervisor = json.loads(args.supervisor.read_text())
    report = build_report(args.manifest, project_root=args.project, source_root=args.source)
    resources = resource_report(args.launch_directory)
    selection = choose(report, resources, validated_readiness(supervisor, report))
    selection['inputs'] = {'supervisor': ref(args.supervisor), 'study_manifest': ref(args.manifest)}
    write_report(report, args.output)
    (args.output/'resources.json').write_text(json.dumps(resources, indent=2)+'\n')
    selection['report'] = ref(args.output/'report.json')
    selection['resources'] = ref(args.output/'resources.json')
    (args.output/'selection.json').write_text(json.dumps(selection, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'status': selection['status'], 'selected': (selection['selected'] or {}).get('candidate_id')}))


if __name__ == '__main__':
    main()
