from scripts.run_learning_v023 import CAPS, TASK_CAPS, dependency, ready_cards


def sample():
    return {'gpus': {'returncode': 0, 'stdout': '\n'.join([
        '2, card2, NVIDIA A100, 17000, 81920, 99',
        '6, card6, NVIDIA A100, 48000, 81920, 50',
        '7, card7, NVIDIA A100, 65000, 81920, 50',
        '3, card3, NVIDIA A100, 80000, 81920, 0'])},
        'processes': {'returncode': 0, 'stdout': 'card2, 12, 64000, another\ncard6, 16, 33000, another\ncard7, 17, 17000, another'}}


def test_stage_memory_admission_preserves_other_jobs():
    state = sample()
    assert ready_cards(state, training=True) == [3, 7]
    assert ready_cards(state, training=False, excluded=[3]) == [6, 7]
    state['processes']['returncode'] = 1
    assert ready_cards(state, training=True) == []


def test_final_waits_for_complete_training_endpoint(tmp_path):
    states = {'train': {'status': 'running'}}
    assert dependency('eval_initial', tmp_path, states) == 'ready'
    assert dependency('train', tmp_path, states) == 'waiting'
    (tmp_path / 'checkpoints').mkdir()
    (tmp_path / 'checkpoints/initial.json').write_text('{}')
    assert dependency('train', tmp_path, states) == 'ready'
    (tmp_path / 'checkpoints/final.json').write_text('{}')
    assert dependency('eval_final', tmp_path, states) == 'waiting'
    (tmp_path / 'training-complete.json').write_text('{}')
    assert dependency('eval_final', tmp_path, states) == 'ready'
    (tmp_path / 'checkpoints/final.json').unlink()
    states['train']['status'] = 'stopped'
    assert dependency('eval_final', tmp_path, states) == 'unavailable_endpoint'


def test_full_update_has_separate_cost_envelope():
    assert sum(v for k, v in CAPS.items() if not k.startswith('external')) == 24 * 3600
    assert sum(v for k, v in CAPS.items() if k.startswith('external')) == 2 * 3600
    assert TASK_CAPS['episode'] == 1200
    assert TASK_CAPS['update'] == 5 * 3600
    assert TASK_CAPS['update'] > TASK_CAPS['episode']
