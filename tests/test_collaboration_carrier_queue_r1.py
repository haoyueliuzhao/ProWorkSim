"""Specified-card waiting, idle races, finite deadlines and retained failed cost."""

import copy

import pytest

from scripts import collaboration_carrier_v026 as worker
from scripts import run_collaboration_carrier_v026 as supervisor
from scripts.evaluate_work_v022 import reference, write


def sample(*, occupied=(), busy=()):
    return {
        'gpus': {'returncode': 0, 'stdout': ''.join(
            f'{gpu}, GPU-{gpu}, NVIDIA A100-SXM4-80GB, 80000, 81920, '
            f'{100 if gpu in busy else 0}\n' for gpu in range(8))},
        'processes': {'returncode': 0, 'stdout': ''.join(
            f'GPU-{gpu}, 1234, 0, other-job\n' for gpu in occupied)},
    }


def test_admission_requires_specified_released_cards_even_when_free_memory_is_high():
    plan = worker.FIXED_LIMITS
    assert worker.released_gpus(plan, sample()) == [0, 4, 5, 7]
    assert worker.released_gpus(plan, sample(occupied=[4], busy=[5])) == [0, 7]
    assert worker.released_gpus(plan, sample(), excluded=[0, 7]) == [4, 5]
    broken = sample()
    broken['gpus']['stdout'] = broken['gpus']['stdout'].replace('80000', 'nan', 1)
    assert worker.released_gpus(plan, broken) == [4, 5, 7]
    broken['processes']['returncode'] = 1
    assert worker.released_gpus(plan, broken) == []


def test_idle_observation_resets_on_competing_process_or_telemetry_failure():
    gate = supervisor.StableIdleAdmission(worker.FIXED_LIMITS)
    assert gate.observe(sample(), now=1000) == []
    assert gate.observe(sample(), now=1119) == []
    assert gate.observe(sample(occupied=[4]), now=1120) == [0, 5, 7]
    assert gate.observe(sample(), now=1121) == [0, 5, 7]
    assert gate.observe(sample(), now=1241) == [0, 4, 5, 7]
    failed = sample()
    failed['gpus']['returncode'] = 1
    assert gate.observe(failed, now=1242) == []
    assert gate.observe(sample(), now=1243) == []


def test_wait_deadline_does_not_cut_active_worker_gpu_budget():
    plan = worker.FIXED_LIMITS
    deadline = plan['queue_deadline_at']
    gate = supervisor.StableIdleAdmission(plan)
    assert gate.observe(sample(), now=deadline-121) == []
    assert gate.observe(sample(), now=deadline-1) == [0, 4, 5, 7]
    assert gate.observe(sample(), now=deadline) == []
    state = {'started_at': deadline-60, 'budget_seconds': worker.RESOURCE_CAPS['worker-0']}
    task = {'kind': 'episode', 'started_at': deadline-30}
    limits = {'root_started': deadline-3600, 'own_rss': 0, 'all_rss': 0,
              'size': 0, 'free_bytes': 2*1024**3}
    assert supervisor.stop_reason(plan, state, task, now=deadline+5, **limits) is None
    assert not supervisor.wall_expired(plan, deadline+5, deadline-3600)
    assert supervisor.wall_expired(plan, plan['wall_deadline_at']-60, deadline-3600)


def previous_fixture(tmp_path):
    slots = {'worker-0': [{'slot_id': 'fixture-zero'}], 'worker-1': [{'slot_id': 'fixture-one'}]}
    original = {'version': 'reciprocal-carrier-development-v0.26',
                'resource_caps': {'worker-0': 7200, 'worker-1': 7200}, 'internal_gpu_seconds': 14400}
    write(tmp_path/'original.json', original)
    original_ref = reference(tmp_path/'original.json')
    write(tmp_path/'supervisor.json', {'status': 'closed_with_incomplete_workers',
          'plan': original_ref, 'parameter_updates': 0, 'worker_assignments': slots})
    refs = {}
    for index, name in enumerate(worker.RESOURCE_CAPS):
        state = {'worker': name, 'status': 'stopped', 'stop_reason': 'worker_failed',
                 'completed_slot_count': 0, 'task': {'kind': 'loading'},
                 'elapsed_gpu_seconds': 25.7-index*.3, 'slots': slots[name]}
        report = {'status': 'interrupted_or_error', 'error': {'type': 'OutOfMemoryError'},
                  'source_unchanged': True, 'new_actor_steps': 0, 'new_critic_steps': 0,
                  'model_api_calls': 0, 'slots': slots[name]}
        write(tmp_path/(name+'-state.json'), state)
        write(tmp_path/(name+'-report.json'), report)
        refs[name] = {'state': reference(tmp_path/(name+'-state.json')),
                      'report': reference(tmp_path/(name+'-report.json'))}
    return {**copy.deepcopy(worker.FIXED_LIMITS), 'previous_attempt': {
        'plan': original_ref, 'supervisor': reference(tmp_path/'supervisor.json'), 'workers': refs,
        'actual_gpu_seconds': 25.7+25.4, 'budget_charge_seconds': 52}}


def test_loading_cost_is_debited_and_started_episodes_cannot_be_silently_repeated(tmp_path):
    plan = previous_fixture(tmp_path)
    assert sum(worker.validate_previous_loading_attempt(plan).values()) == 25.7+25.4
    assert plan['internal_gpu_seconds']+plan['previous_attempt']['budget_charge_seconds'] == 14400
    report_path = tmp_path/'worker-0-report.json'
    from proworksim.storage import read_json
    report = read_json(report_path)
    report['rows'] = [{'slot_id': 'fixture-zero', 'status': 'closed'}]
    write(report_path, report)
    plan['previous_attempt']['workers']['worker-0']['report'] = reference(report_path)
    with pytest.raises(ValueError, match='pre-episode loading failure'):
        worker.validate_previous_loading_attempt(plan)


def test_deadline_extension_accepts_only_an_unused_previous_queue(tmp_path):
    previous = {**copy.deepcopy(worker.FIXED_LIMITS),
                'version': 'reciprocal-carrier-development-v0.26-r1',
                'queue_deadline_at': 1790827200, 'wall_deadline_at': 1790834400}
    write(tmp_path/'previous-wait-plan.json', previous)
    plan_ref = reference(tmp_path/'previous-wait-plan.json')
    assignments = {name: [{'slot_id': name+'-unstarted-fixture'}] for name in worker.RESOURCE_CAPS}
    summary = {'plan': plan_ref, 'status': 'supervisor_error',
               'error': {'type': 'KeyboardInterrupt'}, 'terminated_gpu_seconds': 0,
               'running_gpu_seconds': 0, 'worker_assignments': assignments}
    write(tmp_path/'previous-wait-supervisor.json', summary)
    write(tmp_path/'transition.json', {'operation': 'user_requested_wait_extension',
          'new_queue_deadline_beijing': '2026-10-02T00:00:00+08:00'})
    refs = {}
    for name in worker.RESOURCE_CAPS:
        folder = tmp_path/name
        folder.mkdir()
        write(folder/'state.json', {'status': 'not_started_supervisor_interrupted',
              'attempted': False, 'slots': assignments[name]})
        refs[name] = reference(folder/'state.json')
    plan = {**copy.deepcopy(worker.FIXED_LIMITS), 'version': worker.VERSION, 'previous_queue': {
        'plan': plan_ref, 'supervisor': reference(tmp_path/'previous-wait-supervisor.json'),
        'transition': reference(tmp_path/'transition.json'), 'workers': refs}}
    assert worker.validate_previous_waiting_queue(plan)['previous_queue_gpu_seconds'] == 0
    write(tmp_path/'worker-0/state.json', {'status': 'not_started_supervisor_interrupted',
          'attempted': True, 'slots': assignments['worker-0']})
    plan['previous_queue']['workers']['worker-0'] = reference(tmp_path/'worker-0/state.json')
    with pytest.raises(ValueError, match='started worker cannot be repeated'):
        worker.validate_previous_waiting_queue(plan)
