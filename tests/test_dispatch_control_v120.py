"""Admission drain keeps actual async-queue work/grades alive; no external I/O."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import threading

import pytest

from proworksim import software_benchmark_dispatch_control_v120 as control
from proworksim.software_benchmark_candidates_v054 import write_new


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('No networking or subprocess in drain controls')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)


def plan(tmp_path, monkeypatch):
    monkeypatch.setattr(control, 'ROOT', tmp_path)
    batch = tmp_path/'runs/batch'
    batch.mkdir(parents=True)
    value = {'root': str(batch), 'dispatch_admission': control.declaration(batch)}
    return batch, write_new(batch/'plan.json', value)


def test_owned_control_is_admission_only_and_corruption_never_cancels_existing_work(tmp_path, monkeypatch):
    batch, ref = plan(tmp_path, monkeypatch)
    gate = control.DispatchAdmissionController(ref)
    assert gate.limit(16) == 16
    receipt = control.write_control(ref, mode='drain', reason='Preserve active work while reviewing a defect')
    assert gate.limit(16) == 0 and receipt['service_or_API_operations'] == 0
    running = gate.annotate({'active_generation': 2, 'active_grading': 1, 'pending_scores': 1})
    assert running['dispatch_admission']['state'] == 'draining'
    assert running['dispatch_admission']['scoring_allowed'] is True
    assert running['dispatch_admission']['existing_generation_cancelled'] is False
    saved = gate.path.read_bytes()
    gate.path.write_bytes(b'{"incomplete":')
    assert gate.limit(16) == 0
    assert gate.read()['control_error'] is not None
    gate.path.write_bytes(saved)
    assert gate.annotate({'active_generation': 0, 'active_grading': 0, 'pending_scores': 0})['dispatch_admission']['state'] == 'paused_drained'
    control.write_control(ref, mode='run', reason='Resume after review')
    assert gate.limit(16) == 16
    gate.path.unlink()
    assert gate.limit(16) == 0  # A missing prior instruction is not implicit resume.
    assert len(list((batch/'operator-controls').glob('dispatch-admission-*.json'))) == 2
    old = write_new(batch/'old-plan.json', {'root': str(batch)})
    with pytest.raises(PermissionError, match='does not declare'):
        control.write_control(old, mode='drain', reason='Cannot retrofit an old owner')


def test_actual_async_queue_drains_generation_and_both_score_endpoints_then_resumes(tmp_path, monkeypatch):
    project = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('drain_queue_fixture_v120', project/'tests/test_async_queue_v082.py')
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    batch, plan_ref = plan(tmp_path, monkeypatch)
    gate = control.DispatchAdmissionController(plan_ref)
    fixture = fixture_module.Fixture(batch)
    fixture.separate_delivery = True
    rows = fixture_module.planned(batch, count=3, arm='PROJECT')
    api = fixture_module.API()
    first_started, release_first, drained = threading.Event(), threading.Event(), threading.Event()
    stop, finished = threading.Event(), {}
    def episode(row, resident, **kwargs):
        if row['slot_id'] == 'slot-0':
            first_started.set()
            assert release_first.wait(5)
        return fixture.episode(row, resident, **kwargs)
    def progress(value):
        shown = gate.annotate(value)
        if (shown['dispatch_admission']['state'] == 'paused_drained'
                and value['finished_generation'] == 1 and value['finished_code_scores'] == 1
                and value['finished_delivery_endpoints'] == 1):
            drained.set()
    def run():
        try:
            finished['result'] = fixture_module.execute(batch, fixture, rows, api_runtime=api,
                run_episode=episode, generation_limit=lambda: gate.limit(1),
                stop_event=stop, progress_sink=progress)[0]
        except BaseException as error:
            finished['error'] = error
            drained.set()
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert first_started.wait(5)
        control.write_control(plan_ref, mode='drain', reason='CPU fixture pause new dispatch only')
        release_first.set()
        assert drained.wait(5), finished
        if 'error' in finished:
            raise finished['error']
        assert thread.is_alive() and not stop.is_set() and api.cancelled is False
        assert fixture.entered == {'slot-0'}
        assert fixture.score_calls[('slot-0', 'code')] == fixture.score_calls[('slot-0', 'delivery')] == 1
        control.write_control(plan_ref, mode='run', reason='CPU fixture resume')
        thread.join(5)
        assert not thread.is_alive(), finished
        assert finished['result']['failure'] is None
        assert len(finished['result']['generation']) == len(finished['result']['scores']) == 3
        assert all(fixture.calls[row['slot_id']] == 1 for row in rows)
        assert json.loads(gate.path.read_bytes())['mode'] == 'run'
    finally:
        if thread.is_alive():
            stop.set()
            release_first.set()
            thread.join(5)
