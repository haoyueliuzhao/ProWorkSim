"""One bounded fixture: paired budgets, explicit profile binding, no score gate."""
import copy
import json
from pathlib import Path

import pytest

from proworksim.storage import digest, json_bytes
from scripts.build_harness_study_v016 import build_study, read, ref, validate_original_s1
from scripts.select_candidate_v015 import GUARD_KEYS


ROOT = Path(__file__).resolve().parents[1]


def test_h1_fixed_pairs_and_original_s1_binding_without_capability_claim(tmp_path):
    sources = [ROOT / 'examples/learning-v15' / name for name in
               ('screen-chatstop-qwen35-9b.json', 'screen-chatstop-qwen38-27b.json')]
    originals = [read(p) for p in sources]
    output = tmp_path / 'two-model-plan'
    manifest = build_study(sources, output, profile_root=ROOT)
    assert manifest['episodes'] == 48 and manifest['train_episodes'] == 0
    assert manifest['scope'] == 'two_model_harness_development_comparison'
    assert not manifest['selected_is_capability_certification'] and not manifest['Marshmallow_used']
    assert manifest['max_role_decisions_per_model'] == 356
    pairs = []
    for original in originals:
        protocol = read(output / f"h1-{original['candidate_id']}.json")
        assert protocol['runtime'] == original['runtime']
        assert protocol['recipe'] == {**original['recipe'], 'seed': 2026093041}
        assert protocol['mode'] == 'evaluate'
        assert protocol['expected_optimizer_steps'] == {'actor': 0, 'critic': 0}
        assert protocol['initialization']['restore_checkpoint_permitted'] is False
        assert protocol['collector'] == 'proworksim.harness_collection:collect_window'
        assert 'paired_original_protocol' not in protocol and 'change_scope' not in protocol
        assert [(w['harness'], w['node']) for w in protocol['windows']] == [
            ('native_v15', 'repeat-0'), ('openhands_v16', 'repeat-0'),
            ('openhands_v16', 'repeat-1'), ('native_v15', 'repeat-1')]
        slots = [s for w in protocol['windows'] for s in w['slots']]
        assert len(slots) == len({s['slot_id'] for s in slots}) == 24
        assert {s['pool'] for s in slots} == {'harness_development'}
        assert {s['family'] for s in slots} == {'uci-online-retail-352'}
        assert all('public_task_override' not in s for s in slots)
        assert sorted(s['task'] for s in protocol['windows'][0]['slots']) == sorted(['implement'] * 2 + ['review'] * 2 + ['pair', 'chain'])
        comparable = [[(s['case_id'], s['sampling_seed'], s['role_decision_limits']) for s in w['slots']] for w in protocol['windows']]
        assert comparable[0] == comparable[1] and comparable[2] == comparable[3]
        assert [s['sampling_seed'] for s in protocol['windows'][0]['slots']] == [2026093100 + 10 * i for i in range(6)]
        assert [s['sampling_seed'] for s in protocol['windows'][2]['slots']] == [2026093101 + 10 * i for i in range(6)]
        pairs.append(comparable)
    assert pairs[0] == pairs[1]
    single = build_study(sources[:1], tmp_path / 'one-model-plan', profile_root=ROOT)
    assert single['episodes'] == 24 and single['scope'] == 'single_model_harness_diagnostic'
    with pytest.raises(ValueError, match='new directory'):
        build_study(sources, output, profile_root=ROOT)
    with pytest.raises(ValueError, match='explicit original'):
        build_study(sources, tmp_path / 'missing-report', profile_root=ROOT, require_s1_complete=True)
    tampered = copy.deepcopy(originals[0])
    tampered['runtime']['profile']['temperature'] = 1.1
    tampered_path = tmp_path / 'changed.json'
    tampered_path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match='profile bytes'):
        build_study([tampered_path], tmp_path / 'bad-profile', profile_root=ROOT)
    assert not (tmp_path / 'bad-profile').exists()

    # Artificial original-record fixture, not a completed real S1 claim. Every
    # business score is zero: availability validation must preserve, not rank it.
    screen, screen_path = originals[0], sources[0]
    run_root = tmp_path / 'artificial-original-run'
    (run_root / 'online').mkdir(parents=True)
    (run_root / 'resident').mkdir()
    for path in (run_root / 'online/protocol.json', run_root / 'launch-protocol.json'):
        path.write_text(json.dumps(screen))
    runner = {'status': 'complete', 'protocol_sha256': digest(json_bytes(screen))}
    (run_root / 'online/report.json').write_text(json.dumps(runner))
    owner = {'recipe': screen['recipe'], 'inference_profile': screen['runtime']['profile']}
    (run_root / 'resident/owner.json').write_text(json.dumps(owner))
    fingerprint = {k: 'f' * 64 for k in GUARD_KEYS}
    run = {'candidate_id': screen['candidate_id'], 'root': str(run_root), 'runner_status': 'complete',
           'saved_protocol_equals_declared': True, 'protocol_ref': ref(screen_path), 'owner': owner,
           'progress': {'counts': {'planned': 36, 'distinct_planned_or_measured': 36, 'closed_known': 36,
                                  'closed_unknown': 0, 'open': 0, 'interrupted_open': 0, 'not_started': 0},
                        'completed_work_count': 0},
           'task_fact_summaries': [{'task': 'implement', 'fact': 0, 'completed_work_count': 0}],
           'unknown_step_windows': [], 'issues': [], 'observed_optimizer_step_increments': {'actor': 0, 'critic': 0},
           'windows': [{'window_id': screen['windows'][0]['window_id'], 'mode': 'evaluate', 'stage': 'screen',
                        'evaluation_guard': {'learning_unchanged': True, 'rng_restored_exactly': True,
                                             'learning_before_sha256': fingerprint, 'learning_after_sha256': fingerprint,
                                             'rng_before_sha256': 'b' * 64, 'rng_after_restore_sha256': 'b' * 64},
                        'steps': {'actor': 0, 'critic': 0, 'issues': [],
                                  'recorded_increment_fields': {'actor_optimizer_steps': 0, 'critic_optimizer_steps': 0}}}]}
    eligible = validate_original_s1(screen, screen_path, {'runs': [run]})
    assert eligible['status'] == 'original_completed_S1_profile_bound'
    assert eligible['original_progress']['completed_work_count'] == 0
    assert eligible['original_task_fact_summaries'] == run['task_fact_summaries']
    assert eligible['capability_certified'] is False
    run['runner_status'] = 'running'
    with pytest.raises(ValueError, match='has not completed'):
        validate_original_s1(screen, screen_path, {'runs': [run]})
