"""Local transport isolation using the real async dispatch path, CPU-only."""
from collections import Counter
import copy
import json
import threading
from types import ModuleType

import pytest

from proworksim import software_benchmark_failure_scope_v088 as scope
from proworksim import software_benchmark_async_queue_v082 as queue
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace


def failure_fixture(root, row=None):
    if row is None:
        row = {'slot_id': 'original-api-task', 'instance_id': 'task', 'slot_index': 7,
               'configuration': write_new(root/'configuration.json', {'synthetic': True})}
    index = str(row['slot_index'])
    folder = root/'episodes'/index
    folder.mkdir(parents=True)
    claim_root = root/'resource-claims'
    claim_root.mkdir(exist_ok=True)
    claims = {role: write_new(claim_root/f'{role}-{index}.json', {
        'key': f'{role}-{index}', 'parent_actor_key': None if role == 'actor' else 'actor-'+index,
        'spec': {'role': role, 'slot_id': row['slot_id'], 'instance_id': row['instance_id']}})
        for role in ('actor', 'controller', 'volume')}
    cleanup = {'version': 'v066-owned-private-docker-actor-pair-r1', 'quiescent': True,
        'removed_roles': ['controller', 'actor', 'volume'], 'cleanup_errors': [],
        'create_result_unknown': False, 'create_result_unknown_roles': [], 'retained_objects': [],
        'all_owned_objects_removed': True, 'claims': claims, 'unrelated_objects_touched': False}
    writers = {'all_quiet': True, 'errors': [], 'create_result_unknown_roles': [],
        'writers': [{'role': role, 'container_id': digit*64, 'claim': claims[role],
            'state': {'Status': 'exited', 'Running': False, 'Paused': False, 'Restarting': False, 'Pid': 0}}
            for role, digit in [('actor', 'a'), ('controller', 'b')]]}
    transport = {'version': 'v064-controller-model-fifo-r1', 'status': 'technical_unknown',
        'ready': False, 'model_key_sent_to_container': False, 'host_listener': False,
        **dict.fromkeys(scope.COUNTERS, 0),
        'error': {'type': 'ValueError', 'message': 'filedescriptor out of range in select()'}}
    result = {'version': scope.original.VERSION, 'status': 'technical_unknown',
        'slot_id': row['slot_id'], 'instance_id': row['instance_id'], 'configuration': row['configuration'],
        'model_key': 'DEEPSEEK', 'shared_integrity_fault': scope.FAULT,
        'candidate_lock': None, 'model_calls': 0, 'model_dispatch_started': False,
        'model_bridge_thread_finished': True, 'lifecycle_deadline_reached': False,
        'automatic_replay': False, 'retained_objects': [],
        'error': {'type': 'RuntimeError', 'message': 'Trusted model FIFO bridge did not initialize'},
        'quiescence': write_new(folder/'quiescence.json', cleanup),
        'model_transport': write_new(folder/'model-transport.json', transport),
        'final_writer_quiescence': write_new(folder/'final-writer-quiescence.json', writers)}
    return result, cleanup


def replace_evidence(result, name, transform):
    path = scope.checked(result[name])
    data = json.loads(path.read_bytes())
    transform(data)
    path.write_text(json.dumps(data))
    result[name] = reference(path)


def test_proved_boundary_is_local_without_erasing_marker_cost_or_original_function(tmp_path):
    result, cleanup = failure_fixture(tmp_path)
    before = copy.deepcopy(result)
    assert scope.original.classify_failure_scope(result, cleanup) == 'global'
    assert scope.classify_failure_scope(result, cleanup) == 'local'
    assert result['shared_integrity_fault'] == before['shared_integrity_fault']
    assert result['local_failure_classification']['cash_amount_inferred_as_zero'] is False
    assert result['local_failure_classification']['automatic_retry'] is False
    assert scope.classify_failure_scope(result, cleanup) == 'local'
    assert scope.original.classify_failure_scope(result, cleanup) == 'global'
    result.update(failure_scope='local', batch_stop_required=False)
    reason = queue.base.generation_stop_reason(result, {'model_key': 'DEEPSEEK'},
        {'state': 'shared_halted'})
    assert reason['scope'] == 'provider'


@pytest.mark.parametrize('corruption', ['dispatch', 'request', 'writer', 'cleanup', 'identity', 'protocol', 'extra_fault'])
def test_incomplete_or_shared_evidence_cannot_be_downgraded(tmp_path, corruption):
    result, cleanup = failure_fixture(tmp_path)
    if corruption == 'dispatch':
        result['model_dispatch_started'] = True
    elif corruption == 'request':
        replace_evidence(result, 'model_transport', lambda value: value.update(generation_requests=1))
    elif corruption == 'writer':
        replace_evidence(result, 'final_writer_quiescence',
            lambda value: value['writers'][0]['state'].update(Running=True, Pid=123))
    elif corruption == 'cleanup':
        cleanup['quiescent'] = False
    elif corruption == 'identity':
        result['slot_id'] = 'another-task'
    elif corruption == 'protocol':
        replace_evidence(result, 'model_transport',
            lambda value: value.update(error={'type': 'ValueError', 'message': 'Model FIFO frame exceeds its bound'}))
    else:
        result['response_projection_fault'] = {'different': True}
    assert scope.classify_failure_scope(result, cleanup) == 'global'
    assert 'local_failure_classification' not in result


def test_missing_or_changed_receipt_is_not_evidence(tmp_path):
    result, cleanup = failure_fixture(tmp_path)
    scope.checked(result['model_transport']).write_text('{}')
    assert scope.classify_failure_scope(result, cleanup) == 'global'


def test_private_binding_changes_actual_run_namespace_only():
    namespace = clone_namespace(scope.original)
    delegate = ModuleType('cpu-private-episode')
    delegate.__dict__.update(namespace)
    scope.bind_episode(delegate)
    assert delegate._run.__globals__['classify_failure_scope'] is scope.classify_failure_scope
    assert scope.original._run.__globals__['classify_failure_scope'] is scope.original.classify_failure_scope
    with pytest.raises(ValueError, match='untouched private'):
        scope.bind_episode(scope.original)


class API:
    def budget_status(self):
        return {'state': 'ready', 'can_start_generation': True}

    def logical_resident(self):
        return {'synthetic': True}

    def transport_factory(self, *_):
        raise AssertionError('No HTTP in this CPU fixture')


class Fixture:
    def __init__(self, root, shared_fault):
        self.root, self.shared_fault = root, shared_fault
        self.calls, self.scores = Counter(), Counter()
        self.entered = set()
        self.bad_collected = threading.Event()
        self.second_saw_stop = None

    def run(self, row, resident, **kwargs):
        slot = row['slot_id']
        self.calls[slot] += 1
        self.entered.add(slot)
        if row['slot_index'] == 0:
            result, cleanup = failure_fixture(self.root, row)
            if self.shared_fault:
                result['shared_integrity_fault'] = 'controller_identity_mismatch'
            result['failure_scope'] = scope.classify_failure_scope(result, cleanup)
            result['batch_stop_required'] = result['failure_scope'] == 'global'
            return write_new(self.root/'bad-result.json', result)
        if row['slot_index'] == 1:
            assert self.bad_collected.wait(5)
            self.second_saw_stop = kwargs['stop_event'].is_set()
        return write_new(self.root/f'{slot}-result.json', {
            'slot_id': slot, 'configuration': row['configuration'],
            'status': 'technical_unknown' if kwargs['stop_event'].is_set() else 'closed',
            'quiescence': {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False}})

    def prepare_score(self, ref, *, endpoint):
        result = queue.load(ref)
        folder = self.root/('score-'+result['slot_id'])
        folder.mkdir()
        return write_new(folder/'request.json', {'slot_id': result['slot_id'],
            'directory': str(folder), 'resource_key': folder.name})

    def run_request(self, ref, stop_event):
        request = queue.load(ref)
        self.scores[request['slot_id']] += 1
        done = {'request': ref, 'status': 'process_exited', 'returncode': 0}
        write_new(queue.Path(request['directory'])/'completion.json', done)
        return done

    def trustworthy_cleanup(self, _):
        return True


@pytest.mark.parametrize('shared_fault', [False, True])
def test_actual_async_queue_preserves_other_future_only_for_proved_local_fault(tmp_path, shared_fault):
    config = write_new(tmp_path/'configuration.json', {'synthetic': True})
    rows = [{'slot_id': f'task-{i}', 'slot_index': i, 'configuration': config,
             'instance_id': 'task', 'model_key': 'DEEPSEEK', 'arm': 'REF',
             'group_id': 'DEEPSEEK_REF', 'generation_token_upper_bound': 5000000}
            for i in range(8)]
    fixture = Fixture(tmp_path, shared_fault)
    stop = threading.Event()

    def event(kind, **value):
        if kind == 'generation_finished' and value['slot_id'] == 'task-0':
            fixture.bad_collected.set()

    result = queue.execute_queue(rows, controls=[], qualifications={'task': {'status': 'qualified'}},
        grading=fixture, runtime=object(), run_episode=fixture.run, api_runtime=API(),
        entered_probe=lambda row: row['slot_id'] in fixture.entered, generation_limit=lambda: 2,
        job_root=tmp_path/'jobs', stop_event=stop, event_sink=event, heartbeat_interval=.01)
    assert all(value == 1 for value in fixture.calls.values())
    assert result['automatic_replay'] is False
    if shared_fault:
        assert result['failure']['kind'] == 'shared_generation_integrity_failure'
        assert fixture.second_saw_stop is True
        assert len(fixture.calls) == 2 and len(result['unentered_generation']) == 6
    else:
        assert result['failure'] is None and fixture.second_saw_stop is False
        assert len(fixture.calls) == 8 and len(fixture.scores) == 7
        assert result['generation']['task-0']['status'] == 'technical_unknown'
        assert all(result['generation'][f'task-{i}']['status'] == 'closed' for i in range(1, 8))
        assert any(item['kind'] == 'generation_technical_unknown' for item in result['exceptions'])
