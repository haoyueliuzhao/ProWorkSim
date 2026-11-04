"""Real async orchestration with scripted work; no API, Docker, or services."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import subprocess
import threading
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('The queue control has no external-operation authority')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    monkeypatch.setattr(subprocess, 'Popen', deny)


def test_group_cash_drains_new_work_but_existing_and_other_group_complete(tmp_path):
    manager = load('tools/run_fixed_organization_v131.py', 'actual_group_manager_CPU')
    fixture_module = load('tests/test_async_queue_v082.py', 'old_queue_fixture_CPU')
    first_started, release_first, admission_stopped = threading.Event(), threading.Event(), threading.Event()
    results, errors, apis, fixtures = {}, {}, {}, {}

    def run_group(group):
        folder = tmp_path/group
        folder.mkdir()
        fixture = fixtures[group] = fixture_module.Fixture(folder)
        api = apis[group] = fixture_module.API()
        rows = fixture_module.planned(folder, count=2, arm='PROJECT')
        def episode(row, resident, **kwargs):
            if group == 'A' and row['slot_id'] == 'slot-0':
                first_started.set()
                assert release_first.wait(5)
                assert not kwargs['stop_event'].is_set(), 'Cash drain cancelled existing work'
            return fixture.episode(row, resident, **kwargs)
        def event(name, **values):
            if group == 'A' and name == 'group_admission_stopped':
                assert values['inflight_cancelled'] is False
                admission_stopped.set()
        try:
            results[group] = manager.queue_module().execute_queue(rows, controls=[],
                qualifications={'task': {'status':'qualified'}}, grading=fixture,
                runtime=object(), run_episode=episode, api_runtime=api,
                entered_probe=lambda row: row['slot_id'] in fixture.entered,
                generation_limit=lambda: 1, job_root=folder/'jobs', event_sink=event,
                heartbeat_interval=.02)
        except BaseException as error:
            errors[group] = error
    first = threading.Thread(target=run_group, args=('A',))
    other = threading.Thread(target=run_group, args=('B',))
    first.start()
    assert first_started.wait(5)
    apis['A'].state = 'cash_exhausted'
    other.start()
    try:
        assert admission_stopped.wait(5), errors
        other.join(5)
        assert not other.is_alive() and not errors
        assert len(results['B']['scores']) == 2 and apis['B'].cancelled is False
        release_first.set()
        first.join(5)
        assert not first.is_alive() and not errors
        assert apis['A'].cancelled is False
        assert results['A']['failure'] is None
        assert results['A']['generation']['slot-0']['status'] == 'closed'
        assert results['A']['generation']['slot-1']['status'] == 'not_started'
        assert fixtures['A'].score_calls[('slot-0','code')] == 1
    finally:
        release_first.set()
        first.join(5)
        other.join(5)


def test_startup_ticket_release_does_not_release_the_live_generation_pair(monkeypatch):
    manager = load('tools/run_fixed_organization_v131.py', 'group_startup_CPU')
    monkeypatch.setattr(manager.scope, 'MAX_GENERATIONS', 2)
    monkeypatch.setattr(manager.scope, 'MAX_STARTUPS', 1)
    gate = manager.SharedAdmission(SimpleNamespace())
    stop = threading.Event()
    rows = [{'slot_id':f'team-{i}','organization_id':'CHIEF'} for i in range(3)]
    gate.enter(rows[0], stop)
    second_in, third_in = threading.Event(), threading.Event()
    second = threading.Thread(target=lambda: (gate.enter(rows[1], stop), second_in.set()))
    third = threading.Thread(target=lambda: (gate.enter(rows[2], stop), third_in.set()))
    second.start()
    assert not second_in.wait(.1)
    gate.ready(rows[0])
    assert second_in.wait(2)
    assert gate.snapshot()['generation_tickets_held'] == 2
    gate.ready(rows[1])
    third.start()
    assert not third_in.wait(.1)
    gate.leave(rows[0])
    assert third_in.wait(2)
    assert gate.snapshot()['generation_tickets_held'] == 2
    gate.leave(rows[1])
    gate.leave(rows[2])
    second.join(2)
    third.join(2)
    assert gate.snapshot()['generation_tickets_held'] == gate.snapshot()['startup_tickets_held'] == 0


def test_preentry_exception_is_deferred_without_stopping_the_group(tmp_path, monkeypatch):
    manager = load('tools/run_fixed_organization_v131.py', 'preentry_defer_manager_CPU')
    fixture_module = load('tests/test_async_queue_v082.py', 'preentry_defer_fixture_CPU')
    fixture = fixture_module.Fixture(tmp_path)
    monkeypatch.setattr(manager.scope, 'BATCH_ROOT', tmp_path)
    rows = fixture_module.planned(tmp_path, count=2, arm='PROJECT')
    def episode(row, resident, **kwargs):
        if row['slot_id'] == 'slot-0':
            raise FileNotFoundError(2, 'CPU fixture: private task output is absent',
                                    str(tmp_path/'episodes/0/input.json'))
        return fixture.episode(row, resident, **kwargs)
    result = manager.queue_module().execute_queue(rows, controls=[],
        qualifications={'task': {'status':'qualified'}}, grading=fixture,
        runtime=object(), run_episode=episode, api_runtime=fixture_module.API(),
        entered_probe=lambda row: row['slot_id'] in fixture.entered,
        generation_limit=lambda: 1, job_root=tmp_path/'jobs', heartbeat_interval=.02)
    assert result['failure'] is None
    assert result['generation']['slot-0']['status'] == 'technical_unknown'
    assert result['generation']['slot-0']['entered'] is False
    assert result['generation']['slot-1']['status'] == 'closed'
    assert len(result['scores']) == 1


def test_common_authorization_failure_still_stops_group_admission(tmp_path):
    manager = load('tools/run_fixed_organization_v131.py', 'guard_failure_manager_CPU')
    fixture_module = load('tests/test_async_queue_v082.py', 'guard_failure_fixture_CPU')
    fixture = fixture_module.Fixture(tmp_path)
    rows = fixture_module.planned(tmp_path, count=2, arm='PROJECT')
    def episode(*args, **kwargs):
        raise PermissionError('CPU fixture: common frozen grant is invalid')
    result = manager.queue_module().execute_queue(rows, controls=[],
        qualifications={'task': {'status':'qualified'}}, grading=fixture,
        runtime=object(), run_episode=episode, api_runtime=fixture_module.API(),
        entered_probe=lambda row: False, generation_limit=lambda: 1,
        job_root=tmp_path/'jobs', heartbeat_interval=.02)
    assert result['failure']['kind'] == 'generation_failed_without_trusted_result'
    assert not fixture.entered and not result['scores']
    assert manager.local_preentry_error(ValueError('Frozen source digest changed'), rows[0]) is False
