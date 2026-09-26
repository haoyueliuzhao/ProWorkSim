"""Small saved-record fixtures, never training or model/world execution."""

import copy
import hashlib
import json

import pytest

from scripts.learning_study_report_v014 import build_report, steps_for_window


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def identity(seed):
    return {'version': 'explicit-fixture-identity', 'policy_version': f'initial-{seed}',
            'adapter_sha256': str(seed) * 64, 'base_manifest_sha256': 'b' * 64,
            'inference_profile_sha256': 'p' * 64}


def learning_guard(seed):
    values = {key: f'{seed}-{key}' for key in ('actor', 'critic', 'actor_optimizer', 'critic_optimizer',
                                             'policy_revision', 'actor_steps', 'critic_steps', 'critic_has_nonzero_reward_history')}
    return {'learning_before_sha256': values, 'learning_after_sha256': values,
            'learning_unchanged': True, 'rng_restored_exactly': True}


def fixture(tmp_path):
    source = tmp_path / 'frozen'
    jobs, states = [], []
    for seed in range(3):
        for condition in ('mc', 'rtg'):
            name = f'{condition}-seed{seed}'
            windows = []
            names = ['dev-initial'] + (['locked-initial-common'] if condition == 'mc' else []) + ['train-0', 'dev-2', 'dev-4', 'locked-final']
            for suffix in names:
                pool = 'locked_facts' if suffix.startswith('locked') else 'train' if suffix.startswith('train') else 'development'
                tasks = ['implement', 'chain'] if suffix.startswith('locked') else ['implement']
                windows.append({'window_id': f'{condition}-s{seed}-{suffix}',
                                'mode': 'online' if suffix.startswith('train') else 'evaluate',
                                'slots': [{'slot_id': f'{name}-{suffix}-{task}', 'case_id': f'{pool}-v14-f0-{task}',
                                           'sampling_seed': seed * 100 + pos} for pos, task in enumerate(tasks)]})
            protocol = {'mode': 'online', 'condition': condition, 'replicate_index': seed, 'windows': windows}
            job = {'name': name, 'protocol': f'{name}.json', 'run': f'runs/{name}', 'launch': f'launch/{name}'}
            jobs.append(job)
            states.append({**job, 'status': 'finished'})
            save(source / job['protocol'], protocol)
            root = tmp_path / job['run']
            save(root / 'online/protocol.json', protocol)
            save(root / 'source-before.json', {'code_commit': 'frozen-test', 'code_dirty': False, 'source_tree_sha256': 'tree'})
            save(root / 'resident/owner.json', {'initial_actor_identity': identity(seed)})
            save(root / 'online/initial-checkpoint/checkpoint.json', {'actor_identity': identity(seed), 'actor_steps': 0,
                 'critic_steps': 0, 'serialized_reload_exact': True, 'state_tensor_digest': f'{condition}-recipe-dependent'})
            actual_windows = []
            for index, window in enumerate(windows):
                if window['window_id'].endswith(('dev-2', 'dev-4', 'locked-final')):
                    continue
                folder = root / f'online/window-{index}'
                active = identity(seed)
                declare = {'window_id': window['window_id'], 'actor_identity': active,
                           'slots': [{'slot_id': s['slot_id'], 'active_members': ['implementer'] if s['case_id'].endswith('implement') else ['provider', 'implementer', 'reviewer']} for s in window['slots']]}
                save(folder / 'collection/declaration.json', declare)
                summaries = []
                for si, slot in enumerate(window['slots']):
                    episode = folder / f'collection/slot-{si}/episode'
                    body = {'id': f'{name}-{index}-{si}', 'choices': [{'message': {'role': 'assistant', 'content': 'fixture'}}],
                            'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}}
                    attempt = {'attempt_id': body['id'], 'call_id': body['id'], 'backend_id': 'resident_direct',
                               'stage': 'finished', 'status': 'success', 'response': {'body': body}, 'request': {'messages': []}}
                    events = [{'sequence': 0, 'kind': 'model_attempt', 'worker_id': 'implementer',
                               'payload': {**attempt, 'stage': 'started'}},
                              {'sequence': 1, 'kind': 'model_attempt', 'worker_id': 'implementer', 'payload': attempt}]
                    history = episode / 'experience.json'
                    save(history, {'events': events})
                    save(episode / 'manifest.json', {'status': 'closed', 'episode_id': body['id'],
                         'experience': {'path': 'experience.json', 'start': 0, 'end': len(events),
                                        'sha256': hashlib.sha256(history.read_bytes()).hexdigest()}})
                    reward = {'eligible': True, 'reward': 0.25 if slot['case_id'].endswith('implement') else 0.0,
                              'completed': False, 'components': [{'term_id': 'fixture_outcome', 'achieved': False, 'score': 0, 'weight': 1}]}
                    # One honest closed unknown cannot be filled as R=0.
                    if seed == 1 and condition == 'rtg' and window['mode'] == 'online':
                        reward.update(eligible=False, reward=None)
                    summaries.append({'slot_id': slot['slot_id'], 'reward': reward,
                                      'work_validity': {'value': False, 'components': {'record': {'value': True}}}, 'boundary': 'fixture'})
                save(folder / 'collection/summary.json', {'slots': summaries})
                steps = 1 if window['mode'] == 'online' and seed == 0 else 0
                update = {'actor_optimizer_steps': steps, 'critic_optimizer_steps': steps,
                          'actor_steps_total': 99 if window['mode'] == 'evaluate' else steps,
                          'critic_steps_total': 99 if window['mode'] == 'evaluate' else steps,
                          'status': 'fixture_zero_or_step', 'before_actor_identity': active, 'after_actor_identity': active}
                save(folder / ('evaluation' if window['mode'] == 'evaluate' else 'update') / 'report.json', update)
                if window['mode'] == 'evaluate':
                    save(folder / 'evaluation-guard.json', learning_guard(seed))
                save(folder / 'checkpoint/checkpoint.json', {'actor_identity': active, 'actor_steps': steps, 'critic_steps': steps})
                actual_windows.append({'window_id': window['window_id'], 'status': 'complete', 'mode': window['mode'],
                                       'before_actor_identity': active, 'after_actor_identity': active, 'update': update})
            total_steps = int(seed == 0)
            save(root / 'online/report.json', {'status': 'stopped_probability_mismatch', 'windows': actual_windows,
                 'actor_steps_total': total_steps, 'critic_steps_total': total_steps, 'final_actor_identity': identity(seed)})
            save(tmp_path / (job['launch'] + '.launch.json'), {'exit_code': 0, 'fixture_only': True})
    path = tmp_path / 'supervisor/scheduler.json'
    save(path, {'manifest': {'jobs': jobs}, 'source': str(source), 'status': 'finished_with_incomplete_jobs', 'jobs': states})
    return path


def test_mode_specific_step_counts_never_sum_evaluation_cumulative_totals():
    update = {'actor_optimizer_steps': 0, 'critic_optimizer_steps': 0, 'actor_steps_total': 17, 'critic_steps_total': 21}
    result = steps_for_window('evaluate', update, True)
    assert (result['actor'], result['critic']) == (0, 0)
    assert result['recorded_cumulative_totals']['actor_steps_total'] == 17
    assert steps_for_window('online', None, True)['actor'] is None
    assert steps_for_window('online', None, False)['actor'] == 0


def test_final_stopped_study_keeps_unknown_and_future_nodes_and_counts_baseline_once(tmp_path):
    scheduler = fixture(tmp_path)
    report = build_report(scheduler, project_root=tmp_path, allow_incomplete=True)
    assert report['status'] == 'terminated_incomplete_study'
    assert report['planned_runs'] == 6 and report['all_declared_runs_terminal']
    assert report['observed_optimizer_step_increments'] == {'actor': 2, 'critic': 2}
    counts = report['progress']['counts']
    assert counts == {'closed_known': 17, 'closed_unknown': 1, 'open': 0, 'interrupted_open': 0, 'not_started': 24, 'planned': 42, 'closed': 18}
    assert report['progress']['mean_reward'] is None
    assert len(report['shared_initial_locked_baselines']) == 3
    assert all(b['reuse_allowed'] and b['initial_actor_critic_optimizer_fingerprints_match'] for b in report['shared_initial_locked_baselines'])
    # 18 distinct saved episodes; reuse references do not add 6 extra episodes/tokens.
    assert report['observed_sampling_totals']['reported_prompt_tokens'] == 180
    assert report['observed_sampling_totals']['resident_direct_attempts_started'] == 18
    assert report['observed_sampling_totals'].get('network_http_attempts_started', 0) == 0
    assert all(r['delta_mean_reward'] is None and not r['comparison_ready'] for r in report['locked_comparisons'])
    for run in report['runs']:
        future = [r for r in run['task_summaries'] if r['node'] in {'2', '4', 'final'}]
        assert future and all(r['mean_reward'] is None and r['counts']['not_started'] for r in future)
        assert all(r['reward'] is None for w in run['windows'] for r in w['slots'] if r['state'] == 'not_started')
    with pytest.raises(ValueError, match='incomplete'):
        build_report(scheduler, project_root=tmp_path)


def test_actual_initial_identity_mismatch_blocks_shared_baseline_and_learning_mismatch_is_visible(tmp_path):
    scheduler = fixture(tmp_path)
    root = tmp_path / 'runs/rtg-seed2'
    path = root / 'online/initial-checkpoint/checkpoint.json'
    data = json.loads(path.read_text())
    data['actor_identity']['adapter_sha256'] = 'x' * 64
    save(path, data)
    guard_path = root / 'online/window-0/evaluation-guard.json'
    guard = json.loads(guard_path.read_text())
    guard['learning_before_sha256']['critic_optimizer'] = 'different-real-saved-fingerprint'
    save(guard_path, guard)
    result = build_report(scheduler, project_root=tmp_path, allow_incomplete=True)
    baseline = next(b for b in result['shared_initial_locked_baselines'] if b['seed'] == 2)
    assert baseline['reuse_allowed'] is False
    assert baseline['initial_actor_identity_match'] is False
    assert baseline['initial_actor_critic_optimizer_fingerprints_match'] is False
    assert all(r['initial_mean_reward'] is None for r in result['locked_comparisons'] if r['seed'] == 2)


def test_closed_record_hash_is_not_silently_accepted_after_mutation(tmp_path):
    scheduler = fixture(tmp_path)
    history = tmp_path / 'runs/mc-seed0/online/window-0/collection/slot-0/episode/experience.json'
    original = copy.deepcopy(json.loads(history.read_text()))
    original['events'][1]['payload']['response']['body']['usage']['prompt_tokens'] = 999
    save(history, original)
    with pytest.raises(ValueError, match='hash differs'):
        build_report(scheduler, project_root=tmp_path, allow_incomplete=True)
