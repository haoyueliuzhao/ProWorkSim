from proworksim import software_benchmark_pressure_v079 as pressure

GIB = pressure.GIB


def row(index, model='DEEPSEEK'):
    return {'slot_id': f'v064:fixture-{index}:{model}_REF_B5000K:{index}',
            'model_key': model, 'ownership_token': f'owned-slot-{index:024d}', 'started_unix': index}


def setup(rows=()):
    state = {'current': 20*GIB, 'time': 10.0, 'fail': False}
    aborted = []
    def probe():
        if state['fail']:
            raise OSError('owner cgroup unavailable')
        return {'qualified': True, 'current_bytes': state['current'], 'max_bytes': 64*GIB}
    guard = pressure.PressureWatchdog(lambda: list(rows), lambda pair, event: aborted.append((pair, event)),
        coordinator_probe=probe, memory_probe=lambda: 900*GIB,
        parent_probe=lambda: {'qualified': True, 'current_bytes': 80*GIB, 'max_bytes': 224*GIB},
        require_parent=True, clock=lambda: state['time'], wall_clock=lambda: state['time']+1000)
    return guard, state, aborted


def test_owner_pause_is_separate_from_host_and_parent_and_preserves_hysteresis():
    guard, state, aborted = setup()
    assert guard.tick()['admit']
    state['current'] = 41*GIB
    value = guard.tick()
    assert not value['admit'] and value['reason'] == 'API_owner_hysteresis_pause'
    assert value['memory_available_bytes'] == 900*GIB
    assert value['parent_pressure']['current_bytes'] == 80*GIB
    assert value['owner_pressure']['current_bytes'] == 41*GIB
    state['current'] = 33*GIB
    assert not guard.tick()['admit']
    state['current'] = 32*GIB
    assert guard.tick()['admit']
    state['fail'] = True
    value = guard.tick()
    assert not value['fresh'] and not value['admit']
    assert value['owner_pressure']['available_bytes'] is None and aborted == []


def test_owner_emergency_only_requests_registered_API_pairs_once():
    guard, state, aborted = setup([row(1), row(3), row(999, 'QWEN'), row(2)])
    state['current'] = 57*GIB
    value = guard.tick()
    assert not value['admit'] and value['owner_pressure']['emergency']
    assert [pair['slot_id'] for pair, _ in aborted] == [row(3)['slot_id']]
    assert aborted[0][1]['reason'] == 'API_coordinator_memory_emergency'
    assert aborted[0][1]['technical_unknown'] and aborted[0][1]['automatic_retry'] is False
    guard.tick()
    assert len(aborted) == 1
    state['time'] += 1
    state['current'] = 61*GIB
    guard.tick()
    assert [pair['slot_id'] for pair, _ in aborted] == [row(i)['slot_id'] for i in (3, 2, 1)]
    assert all(pair['model_key'] == 'DEEPSEEK' for pair, _ in aborted)
