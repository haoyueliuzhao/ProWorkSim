"""Saved JSON fixtures only; no world/model/evaluator/optimizer is run."""
import copy
import hashlib
import json

import pytest

from scripts.learning_report_v015 import aggregate, build_report, write_report


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def identity(revision):
    return {'policy_version': str(revision), 'adapter_sha256': str(revision) * 64}


def fixture(tmp_path):
    protocol = {'mode': 'online', 'candidate_id': 'candidate-fixture', 'windows': []}
    cases = [
        [('uci-development-f0-implement', 'partial'), ('uci-development-f1-review', 'complete'), ('uci-development-f2-implement', 'missing')],
        [('uci-train-f0-pair', 'complete')],
        [('uci-locked-f0-review', 'unknown')],
    ]
    modes = ['evaluate', 'online', 'evaluate']
    stages = ['screen', 'pilot', 'pilot']
    nodes = ['initial', None, 'final']
    root = tmp_path / 'runs/fixture'
    records = []
    for wi, case_rows in enumerate(cases):
        # Intentionally uninformative names: labels must come from fields.
        spec = {'window_id': f'opaque-{wi}', 'mode': modes[wi], 'stage': stages[wi], 'node': nodes[wi],
                'phase': 'fixture-phase', 'slots': [{'slot_id': f's-{wi}-{si}', 'case_id': case, 'repeat': 2,
                                                    'sampling_seed': 10 + si} for si, (case, _) in enumerate(case_rows)]}
        protocol['windows'].append(spec)
        folder = root / f'online/window-{wi}'
        actor = identity(1 if wi == 2 else 0)
        save(folder / 'collection/declaration.json', {'actor_identity': actor, 'slots': [
            {'slot_id': s['slot_id'], 'active_members': ['provider', 'implementer'] if s['case_id'].endswith('pair') else ['implementer']} for s in spec['slots']]})
        rows = []
        for si, (case, status) in enumerate(case_rows):
            if status == 'missing':
                continue
            episode = folder / f'collection/slot-{si}/episode'
            body = {'id': f'g-{wi}-{si}', 'choices': [{'message': {'role': 'assistant', 'content': 'fixture'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}, 'actor_identity': actor,
                    'token_trace': {'input_ids': [1, 2, 3], 'output_ids': [4, 5], 'behavior_logprobs': [-1, -2]}}
            p = {'attempt_id': body['id'], 'call_id': body['id'], 'backend_id': 'resident_direct', 'stage': 'finished',
                 'status': 'success', 'response': {'body': body}, 'request': {'messages': []}}
            events = [{'sequence': 0, 'kind': 'model_attempt', 'worker_id': 'implementer', 'payload': {**p, 'stage': 'started'}},
                      {'sequence': 1, 'kind': 'model_attempt', 'worker_id': 'implementer', 'payload': p}]
            save(episode / 'experience.json', {'events': events})
            save(episode / 'manifest.json', {'status': 'closed', 'episode_id': body['id'], 'experience': {
                'path': 'experience.json', 'start': 0, 'end': 2,
                'sha256': hashlib.sha256((episode / 'experience.json').read_bytes()).hexdigest()}})
            known = status != 'unknown'
            completed = status == 'complete'
            reward = {'eligible': known, 'reward': 1.0 if completed else .2 if known else None, 'completed': completed,
                      'components': [{'term_id': 'correct_fixed_submission', 'achieved': completed,
                                      'score': 1.0 if completed else 0.0, 'weight': 1.0}]}
            rows.append({'slot_id': spec['slots'][si]['slot_id'], 'reward': reward,
                         'work_validity': {'value': completed, 'components': {'record': {'value': True}}}, 'boundary': 'fixed_deadline'})
            save(folder / f'collection/slot-{si}/mapping.json', {'class_id': 'method-' + str(wi), 'status': 'mapped'})
        save(folder / 'collection/summary.json', {'slots': rows})
        # Same xi, changed theta and frequencies; never pool these b records.
        support = {'window_id': spec['window_id'], 'actor_identity': actor,
                   'groups': [{'window': {'window_id': spec['window_id'], 'xi_id': 'same-xi', 'team_policy_fingerprint': str(wi)},
                               'active_members': ['provider', 'implementer'],
                               'support': {'blocks': {'provider': {'M': 4, 'n_positive': 4, 'b': {'a': 1.0} if wi == 0 else {'b': 1.0}}}}}]}
        save(folder / 'collection/support.json', support)
        step = int(modes[wi] == 'online')
        update = {'actor_optimizer_steps': step, 'critic_optimizer_steps': step,
                  'actor_steps_total': 99 if modes[wi] == 'evaluate' else 1,
                  'critic_steps_total': 99 if modes[wi] == 'evaluate' else 1,
                  'before_actor_identity': actor, 'after_actor_identity': identity(1) if step else actor, 'status': 'saved-fixture'}
        save(folder / ('evaluation' if modes[wi] == 'evaluate' else 'update') / 'report.json', update)
        if modes[wi] == 'evaluate':
            save(folder / 'evaluation-guard.json', {'learning_unchanged': True, 'rng_restored_exactly': True,
                 'learning_before_sha256': {'actor': str(wi)}, 'learning_after_sha256': {'actor': str(wi)}})
        records.append({'window_id': spec['window_id'], 'status': 'complete', 'mode': modes[wi], 'update': update})
    save(tmp_path / 'source/protocol.json', protocol)
    save(root / 'online/protocol.json', protocol)
    save(root / 'online/report.json', {'status': 'stopped_probability_mismatch', 'windows': records,
                                     'actor_steps_total': 1, 'critic_steps_total': 1})
    manifest = {'jobs': [{'name': 'fixture', 'protocol': 'protocol.json', 'run': 'runs/fixture', 'condition': 'mc',
                         'candidate_id': 'candidate-fixture'}],
                'baseline_references': [{'from_job': 'fixture', 'window_id': 'opaque-0', 'used_by': ['mc', 'rtg']}]}
    save(tmp_path / 'manifest.json', manifest)
    return tmp_path / 'manifest.json'


def report(tmp_path, manifest):
    return build_report(manifest, project_root=tmp_path, source_root=tmp_path/'source')


def test_original_completion_missing_denominator_and_pair_kept(tmp_path):
    data = report(tmp_path, fixture(tmp_path))
    counts = data['progress']['counts']
    assert counts['planned'] == 5 and counts['closed_known'] == 3
    assert counts['closed_unknown'] == 1 and counts['not_started'] == 1
    assert data['progress']['mean_reward'] is None
    screen = data['screening_primary'][0]
    assert screen['counts']['planned'] == 3 and screen['completed_work_count'] == 1
    assert screen['completed_work_rate'] is None
    assert screen['by_task']['implement']['completed_work_count'] == 0  # .2 is not success
    windows = data['runs'][0]['windows']
    missing = windows[0]['slots'][2]
    assert missing['state'] == 'not_started' and missing['reward'] is None
    assert missing['fact'] == 2 and missing['pool'] == 'development'
    pair = windows[1]['slots'][0]
    assert pair['task'] == 'pair' and pair['deployment'] == 'shared_weight_team'
    assert pair['repeat'] == 2 and pair['sampling_seed'] == 10


def test_theta_local_support_eval_zero_steps_and_actual_traces(tmp_path):
    data = report(tmp_path, fixture(tmp_path))
    windows = data['runs'][0]['windows']
    assert data['observed_optimizer_step_increments'] == {'actor': 1, 'critic': 1}
    assert windows[0]['steps']['actor'] == windows[2]['steps']['actor'] == 0
    assert windows[0]['steps']['recorded_cumulative_totals']['actor_steps_total'] == 99
    a = windows[0]['support']['groups'][0]['member_blocks']['provider']['b']
    b = windows[2]['support']['groups'][0]['member_blocks']['provider']['b']
    assert a == {'a': 1.0} and b == {'b': 1.0}
    assert windows[0]['collection_actor_identity'] != windows[2]['collection_actor_identity']
    assert 'b' not in data and 'support' not in data
    assert data['sampling']['trace_calls'] == 4
    assert data['sampling']['trace_input_tokens'] == 12 and data['sampling']['trace_output_tokens'] == 8
    assert data['sampling']['totals']['reported_prompt_tokens'] == 12
    assert data['declared_baseline_references']  # references add neither calls nor episodes


def test_duplicate_reference_counts_once_and_output_cannot_overwrite(tmp_path):
    data = report(tmp_path, fixture(tmp_path))
    slot = data['runs'][0]['windows'][0]['slots'][0]
    result = aggregate([slot, copy.deepcopy(slot)])
    assert result['counts']['duplicate_measurement_references'] == 1
    assert result['counts']['closed'] == 1 and result['observed_reward_count'] == 1
    out = tmp_path / 'new-report'
    write_report(data, out)
    with pytest.raises(FileExistsError):
        write_report(data, out)


def test_no_silent_history_mutation_or_duplicate_raw_run(tmp_path):
    manifest = fixture(tmp_path)
    history = tmp_path/'runs/fixture/online/window-0/collection/slot-0/episode/experience.json'
    value = json.loads(history.read_text())
    value['events'][1]['payload']['response']['body']['usage']['prompt_tokens'] = 99
    save(history, value)
    with pytest.raises(ValueError, match='hash differs'):
        report(tmp_path, manifest)
    m = json.loads(manifest.read_text())
    m['jobs'].append({**m['jobs'][0], 'name': 'misleading-duplicate'})
    save(manifest, m)
    with pytest.raises(ValueError, match='raw run must appear once'):
        report(tmp_path, manifest)
