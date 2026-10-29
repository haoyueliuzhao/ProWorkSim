"""CPU-only dispatch tests: no Docker, models, HTTP or host resource changes."""
from collections import Counter
import threading
import time

import pytest

from proworksim import software_benchmark_async_queue_v082 as queue
from proworksim.software_benchmark_candidates_v054 import write_new


class API:
    def __init__(self, state='ready'):
        self.state = state
        self.cancelled = False

    def budget_status(self):
        return {'state': self.state, 'can_start_generation': self.state == 'ready'}

    def logical_resident(self):
        return {'endpoint': 'cpu-fixture'}

    def transport_factory(self, *_):
        raise AssertionError('No network is allowed in this fixture')

    def cancel_all(self):
        self.cancelled = True


def planned(path, count=8, arm='REF'):
    configuration = write_new(path/'configuration.json', {'fixture': True})
    return [{'slot_id': f'slot-{i}', 'slot_index': i, 'configuration': configuration,
             'instance_id': 'task', 'group_id': f'DEEPSEEK-{arm}', 'arm': arm,
             'model_key': 'DEEPSEEK', 'generation_token_upper_bound': 5000000}
            for i in range(count)]


class Fixture:
    def __init__(self, path):
        self.path = path
        self.calls = Counter()
        self.prepare_calls = Counter()
        self.score_calls = Counter()
        self.delivery_calls = Counter()
        self.entered = set()
        self.lock = threading.Lock()
        self.preparing = threading.Event()
        self.checking_delivery = threading.Event()
        self.release_prepare = threading.Event()
        self.release_delivery = threading.Event()
        self.block_prepare = self.block_delivery = False
        self.bad_preparation = None
        self.unquiet = None
        self.separate_delivery = False
        self.active_scores = self.maximum_scores = 0
        self.generation_during_prepare = self.generation_during_delivery = False

    def episode(self, row, resident, **kwargs):
        assert resident == {'endpoint': 'cpu-fixture'}
        assert kwargs['api_transport_factory']
        with self.lock:
            slot = row['slot_id']
            self.calls[slot] += 1
            self.entered.add(slot)
            self.generation_during_prepare |= self.preparing.is_set() and not self.release_prepare.is_set()
            self.generation_during_delivery |= self.checking_delivery.is_set() and not self.release_delivery.is_set()
        time.sleep(.025)
        return write_new(self.path/f'{slot}-result.json', {
            'slot_id': slot, 'configuration': row['configuration'], 'status': 'closed', 'model_calls': 1,
            'ledger': {'known_actual_tokens': 10, 'complete_actual_tokens': 10, 'inflight': None,
                       'uncertain_reserved_tokens': 0},
            'quiescence': {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False}})

    def prepare_score(self, result_ref, *, endpoint='code'):
        slot = queue.load(result_ref)['slot_id']
        with self.lock:
            self.prepare_calls[(slot, endpoint)] += 1
        if self.block_prepare and slot == 'slot-0':
            self.preparing.set()
            assert self.release_prepare.wait(5)
        if self.bad_preparation == slot:
            raise ValueError('fixture original candidate failed archive validation')
        folder = self.path/f'{slot}-{endpoint}'
        folder.mkdir(exist_ok=True)
        return write_new(folder/'request.json', {'slot_id': slot, 'endpoint': endpoint,
            'resource_key': f'fixture-{slot}-{endpoint}', 'directory': str(folder)})

    def run_request(self, request_ref, stop_event):
        request = queue.load(request_ref)
        with self.lock:
            self.score_calls[(request['slot_id'], request['endpoint'])] += 1
            self.active_scores += 1
            self.maximum_scores = max(self.maximum_scores, self.active_scores)
        time.sleep(.01)
        completion = {'status': 'process_exited', 'returncode': 0, 'request': request_ref}
        write_new(queue.Path(request['directory'])/'completion.json', completion)
        with self.lock:
            self.active_scores -= 1
        return completion

    def trustworthy_cleanup(self, request_ref):
        return queue.load(request_ref)['slot_id'] != self.unquiet

    def delivery_disposition(self, result_ref, request_ref):
        slot = queue.load(result_ref)['slot_id']
        with self.lock:
            self.delivery_calls[slot] += 1
        if self.block_delivery and slot == 'slot-0':
            self.checking_delivery.set()
            assert self.release_delivery.wait(5)
        if self.separate_delivery:
            return {'status': 'requires_official_attempt', 'resolved': None,
                    'scoring_request': self.prepare_score(result_ref, endpoint='delivery')}
        return {'status': 'no_legal_delivery', 'resolved': False, 'scoring_request': None}


def execute(path, fixture, rows, **extra):
    progress, cursor, events = [], [], []
    kwargs = dict(controls=[], qualifications={'task': {'status': 'qualified'}}, grading=fixture,
        runtime=object(), run_episode=fixture.episode, api_runtime=API(),
        entered_probe=lambda row: row['slot_id'] in fixture.entered,
        generation_limit=lambda: 2, job_root=path/'jobs', heartbeat_interval=.02,
        progress_sink=lambda value: progress.append((time.monotonic(), value)),
        cursor_sink=cursor.append, event_sink=lambda name, **fields: events.append((name, fields)))
    kwargs.update(extra)
    result = queue.execute_queue(rows, **kwargs)
    return result, progress, cursor, events


@pytest.mark.parametrize('stage', ['prepare', 'delivery'])
def test_slow_candidate_validation_and_delivery_do_not_block_generation_or_progress(tmp_path, stage):
    fixture = Fixture(tmp_path)
    setattr(fixture, f'block_{stage}', True)
    rows = planned(tmp_path, 18, arm='PROJECT')
    blocked = getattr(fixture, 'preparing' if stage == 'prepare' else 'checking_delivery')
    release = getattr(fixture, f'release_{stage}')
    observed = {}

    def release_after_other_work():
        assert blocked.wait(5)
        start = time.monotonic()
        while len(fixture.entered) < 10 and time.monotonic()-start < 3:
            time.sleep(.01)
        observed['entered_before_release'] = len(fixture.entered)
        observed['interval'] = (start, time.monotonic())
        release.set()

    helper = threading.Thread(target=release_after_other_work)
    helper.start()
    result, progress, cursor, _ = execute(tmp_path, fixture, rows)
    helper.join()
    assert result['failure'] is None
    assert len(result['scores']) == len(result['generation']) == 18
    assert observed['entered_before_release'] >= 10
    assert getattr(fixture, f'generation_during_{stage}')
    start, end = observed['interval']
    during = [(when, value) for when, value in progress if start <= when <= end]
    assert len(during) >= 3
    assert any(value['heartbeat_only'] for _, value in during)
    assert max(b-a for (a, _), (b, _) in zip(progress, progress[1:])) < .5
    assert not any(value['scheduler_stale'] for _, value in during)
    assert all(count == 1 for count in fixture.calls.values())
    assert all(count == 1 for count in fixture.score_calls.values())
    assert fixture.maximum_scores <= 3
    assert any(value['active_grading_jobs'] for value in cursor)
    assert all(value['pending_scores'] == [] for value in cursor)


def test_preparation_failure_is_local_and_delivery_request_is_never_prepared_twice(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.bad_preparation = 'slot-0'
    fixture.separate_delivery = True
    result, _, _, _ = execute(tmp_path, fixture, planned(tmp_path, 6, arm='PROJECT'))
    assert result['failure'] is None and len(result['generation']) == 6
    assert result['scores']['slot-0']['status'] == 'technical_unknown'
    assert result['deliveries']['slot-0']['status'] == 'technical_unknown'
    assert all(result['deliveries'][f'slot-{i}']['status'] == 'official_attempt_completed' for i in range(1, 6))
    assert len(fixture.score_calls) == 10
    assert all(count == 1 for count in fixture.score_calls.values())
    assert all(count == 1 for count in fixture.prepare_calls.values())
    assert all(count == 1 for count in fixture.delivery_calls.values())
    assert any(item['kind'] == 'score_preparation' for item in result['exceptions'])


def test_slow_reporting_cannot_hold_generation_dispatch_or_heartbeat(tmp_path):
    fixture = Fixture(tmp_path)
    started, release = threading.Event(), threading.Event()
    calls = []

    class Sink:
        def refresh_active(self, _):
            started.set()
            assert release.wait(5)

        def __call__(self, row, entry, result, score, delivery):
            calls.append(row['slot_id'])

    def unblock():
        assert started.wait(5)
        end = time.monotonic()+3
        while len(fixture.entered) < 8 and time.monotonic() < end:
            time.sleep(.01)
        assert len(fixture.entered) == 8
        release.set()

    helper = threading.Thread(target=unblock)
    helper.start()
    result, progress, _, _ = execute(tmp_path, fixture, planned(tmp_path), result_sink=Sink())
    helper.join()
    assert result['failure'] is None and len(result['generation']) == 8
    assert len(calls) == 16 and any(value['heartbeat_only'] for _, value in progress)


def test_cancelled_preparation_has_durable_descriptor_and_resumes_once(tmp_path):
    fixture = Fixture(tmp_path)
    row = planned(tmp_path, 1)[0]
    result_ref = fixture.episode(row, {'endpoint': 'cpu-fixture'}, api_transport_factory=object())
    stop = threading.Event()
    store = queue.JobStore(tmp_path/'jobs')
    descriptor = store.prepare('code', row, result_ref, False, result_ref)
    original_prepare = fixture.prepare_score

    def stop_after_prepare(*args, **kwargs):
        request = original_prepare(*args, **kwargs)
        stop.set()
        return request

    fixture.prepare_score = stop_after_prepare
    outcome = store.run(descriptor, fixture, stop)
    assert outcome['status'] == 'deferred'
    assert (queue.Path(descriptor['path']).parent/'prepared-request.json').exists()
    assert not fixture.score_calls
    fixture.prepare_score = original_prepare
    initial = {'generation': {row['slot_id']: {'result': result_ref, 'entered': True, 'status': 'closed'}},
               'pending_grading_jobs': [descriptor]}
    result, _, _, _ = execute(tmp_path, fixture, [row], initial_state=initial)
    assert result['failure'] is None and len(result['scores']) == 1
    assert fixture.prepare_calls == {('slot-0', 'code'): 1}
    assert fixture.score_calls == {('slot-0', 'code'): 1}
    assert fixture.calls == {'slot-0': 1}
    queue.JobStore(tmp_path/'jobs').run(descriptor, fixture, threading.Event())
    assert fixture.score_calls == {('slot-0', 'code'): 1}
    with pytest.raises(ValueError, match='different candidate'):
        store.prepare('code', row, {'path': 'other', 'sha256': 'other'}, False, result_ref)


@pytest.mark.parametrize('has_local_intent', [False, True])
def test_existing_official_completion_is_recovered_without_replaying_score(tmp_path, has_local_intent):
    fixture = Fixture(tmp_path)
    row = planned(tmp_path, 1, arm='PROJECT')[0]
    result_ref = fixture.episode(row, {'endpoint': 'cpu-fixture'}, api_transport_factory=object())
    request = fixture.prepare_score(result_ref)
    store = queue.JobStore(tmp_path/'jobs', consumed_check=lambda _: False)
    descriptor = store.prepare('code', row, request, True, result_ref)
    folder = queue.Path(descriptor['path']).parent
    if has_local_intent:
        write_new(folder/'execution-intent.json', {'job': descriptor, 'request': request})
    fixture.run_request(request, threading.Event())
    outcome = store.run(descriptor, fixture, threading.Event())
    assert outcome['status'] == 'completed' and outcome['cleanup_proven']
    assert fixture.score_calls == {('slot-0', 'code'): 1}
    assert fixture.delivery_calls == {'slot-0': 1}


def test_consumed_identity_without_completion_cannot_be_replayed(tmp_path):
    fixture = Fixture(tmp_path)
    row = planned(tmp_path, 1)[0]
    result_ref = fixture.episode(row, {'endpoint': 'cpu-fixture'}, api_transport_factory=object())
    request = fixture.prepare_score(result_ref)
    store = queue.JobStore(tmp_path/'jobs', consumed_check=lambda _: False)
    descriptor = store.prepare('code', row, request, True, result_ref)
    write_new(queue.Path(descriptor['path']).parent/'execution-intent.json', {'job': descriptor, 'request': request})
    with pytest.raises(ValueError, match='cannot be replayed'):
        store.run(descriptor, fixture, threading.Event())
    assert not fixture.score_calls


def test_cleanup_uncertainty_remains_hard_stop(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.unquiet = 'slot-0'
    result, _, _, _ = execute(tmp_path, fixture, planned(tmp_path, 40))
    assert result['failure']['kind'] == 'unproven_grader_cleanup'
    assert result['unentered_generation']
    assert len(fixture.entered) < 40


def test_cash_guard_remains_authoritative_and_starts_no_generation(tmp_path):
    fixture, api = Fixture(tmp_path), API('cash_exhausted')
    result, _, _, _ = execute(tmp_path, fixture, planned(tmp_path), api_runtime=api)
    assert not fixture.calls and api.cancelled
    assert result['failure'] is None
    assert all(value['not_started_reason'] == 'api_monetary_budget_exhausted'
               for value in result['generation'].values())


def test_api_only_adapter_refuses_qwen_and_new_controls(tmp_path):
    fixture, rows = Fixture(tmp_path), planned(tmp_path, 1)
    rows[0]['model_key'] = 'QWEN'
    with pytest.raises(ValueError, match='API generation'):
        execute(tmp_path, fixture, rows)
    rows[0]['model_key'] = 'DEEPSEEK'
    with pytest.raises(ValueError, match='API generation'):
        execute(tmp_path, fixture, rows, controls=[{'new': 'control'}])


def test_external_owner_handoff_imports_old_score_without_generation_or_score_replay(tmp_path):
    fixture, rows = Fixture(tmp_path), planned(tmp_path, 5, arm='PROJECT')
    old = rows[0]
    old_result = fixture.episode(old, {'endpoint': 'cpu-fixture'}, api_transport_factory=object())
    old_request = fixture.prepare_score(old_result)
    fixture.run_request(old_request, threading.Event())
    initial = {'generation': {old['slot_id']: {'status': 'external_running', 'entered': False}}}
    pending = True

    def poll():
        nonlocal pending
        time.sleep(.3)
        pending = False
        return {'generation': {old['slot_id']: {'status': 'closed', 'entered': True, 'result': old_result}},
                'pending_score_jobs': [('code', old, old_request, True)]}

    result, progress, _, events = execute(tmp_path, fixture, rows, initial_state=initial,
        external_poll=poll, external_pending=lambda: pending)
    assert result['failure'] is None and len(result['generation']) == len(result['scores']) == 5
    assert result['generation']['slot-0']['status'] == 'closed'
    assert all(count == 1 for count in fixture.calls.values())
    assert all(count == 1 for count in fixture.score_calls.values())
    assert any(name == 'external_handoff_imported' for name, _ in events)
    assert any(value['finished_generation'] == 4 for _, value in progress)
    assert not result['external_handoff_requires_review']


def test_external_conflict_is_isolated_and_does_not_overwrite_finished_generation(tmp_path):
    fixture, rows = Fixture(tmp_path), planned(tmp_path, 5)
    old = rows[0]
    initial_entry = {'status': 'closed', 'entered': True, 'result': {'path': 'frozen', 'sha256': 'frozen'}}
    initial = {'generation': {old['slot_id']: initial_entry}}
    result, _, _, _ = execute(tmp_path, fixture, rows, initial_state=initial,
        external_poll=lambda: {'generation': {old['slot_id']: {'status': 'technical_unknown', 'entered': True}}},
        external_pending=lambda: True)
    assert result['failure'] is None
    assert result['external_handoff_requires_review']
    assert result['generation']['slot-0'] == initial_entry
    assert len(fixture.calls) == 4 and len(result['scores']) == 4


def test_distinct_heartbeat_sink_keeps_main_progress_updates(tmp_path):
    fixture, heartbeat = Fixture(tmp_path), []
    result, progress, _, _ = execute(tmp_path, fixture, planned(tmp_path, 5), heartbeat_sink=heartbeat.append)
    assert result['failure'] is None
    assert progress and progress[-1][1]['finished_generation'] == 5
    assert all(value['heartbeat_only'] is False for _, value in progress)
    assert any(value['heartbeat_only'] is True for value in heartbeat)
    assert heartbeat[-1]['finished_generation'] == 5


@pytest.mark.parametrize('old_status', ['waiting_for_own_code_score', 'requires_separate_official_score'])
def test_external_pending_delivery_advances_to_same_request_final_result(tmp_path, old_status):
    fixture, rows = Fixture(tmp_path), planned(tmp_path, 1, arm='PROJECT')
    row = rows[0]
    result_ref = fixture.episode(row, {'endpoint': 'cpu-fixture'}, api_transport_factory=object())
    request = fixture.prepare_score(result_ref, endpoint='delivery')
    old = {'status': old_status, 'scoring_request': request if old_status == 'requires_separate_official_score' else None}
    terminal = {'status': 'official_attempt_completed', 'request': request, 'completion': {'status': 'process_exited'}}
    pending = True

    def poll():
        nonlocal pending
        pending = False
        return {'deliveries': {row['slot_id']: terminal}}

    initial = {'generation': {row['slot_id']: {'status': 'closed', 'entered': True, 'result': result_ref}},
               'deliveries': {row['slot_id']: old}}
    result, _, _, _ = execute(tmp_path, fixture, rows, initial_state=initial,
                             external_poll=poll, external_pending=lambda: pending)
    assert result['failure'] is None and not result['external_handoff_requires_review']
    assert result['deliveries']['slot-0'] == terminal
    assert not fixture.score_calls


@pytest.mark.parametrize('request_matches', [True, False])
def test_external_pending_delivery_job_requires_matching_disposition(tmp_path, request_matches):
    fixture, rows = Fixture(tmp_path), planned(tmp_path, 1, arm='PROJECT')
    row = rows[0]
    result_ref = fixture.episode(row, {'endpoint': 'cpu-fixture'}, api_transport_factory=object())
    request = fixture.prepare_score(result_ref, endpoint='delivery')
    old = {'status': 'waiting_for_own_code_score', 'scoring_request': None}
    disposition = {'status': 'requires_separate_official_score',
                   'scoring_request': request if request_matches else {'path': 'other', 'sha256': 'other'}}
    pending = True

    def poll():
        nonlocal pending
        pending = False
        return {'deliveries': {row['slot_id']: disposition},
                'pending_score_jobs': [('delivery', row, request, True)]}

    initial = {'generation': {row['slot_id']: {'status': 'closed', 'entered': True, 'result': result_ref}},
               'deliveries': {row['slot_id']: old}}
    result, _, _, _ = execute(tmp_path, fixture, rows, initial_state=initial,
                             external_poll=poll, external_pending=lambda: pending)
    assert result['failure'] is None
    if request_matches:
        assert not result['external_handoff_requires_review']
        assert result['deliveries']['slot-0']['status'] == 'official_attempt_completed'
        assert fixture.score_calls == {('slot-0', 'delivery'): 1}
    else:
        assert result['external_handoff_requires_review']
        assert result['deliveries']['slot-0'] == old and not fixture.score_calls


def test_delivery_transition_never_replaces_terminal_or_changes_fixed_request():
    terminal = {'status': 'official_attempt_completed', 'request': {'path': 'original', 'sha256': 'original'}}
    assert not queue.delivery_can_advance(terminal, {'status': 'technical_unknown'})
    old = {'status': 'requires_separate_official_score', 'scoring_request': terminal['request']}
    assert not queue.delivery_can_advance(old, {**terminal, 'request': {'path': 'other', 'sha256': 'other'}})
    assert not queue.delivery_can_advance(old, {'status': 'no_legal_delivery'})
