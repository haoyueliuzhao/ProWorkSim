"""CPU-only fake queue and real host/client plumbing; no network or task launch."""
from __future__ import annotations

import base64
from concurrent.futures import Future
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools')]
from proworksim import software_benchmark_deepseek_api_v203_2_1 as api  # noqa: E402
from proworksim import software_benchmark_host_api_v203_2_1 as host  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import reference  # noqa: E402
from proworksim.software_benchmark_group_admission_v132 import DrainControl, FairAdmission  # noqa: E402
from proworksim.software_observer_journal_v203_2_1 import ObserverJournal  # noqa: E402
from proworksim.storage import digest, json_bytes  # noqa: E402

ART = ROOT / 'artifacts/software-benchmark-v203-2-1/queue-controls-r2'
RUN = ROOT / 'runs/software-benchmark-v203-2-1/queue-controls-r2'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def setup_api(folder):
    rows = [{'slot_id': f'cpu-v203.2.1:queue-{i}:REVIEW2:1', 'instance_id': f'fixture-{i}',
             'slot_index': 2032100 + i, 'organization_id': 'REVIEW2', 'group_id': 'REVIEW2',
             'condition_id': 'REVIEW2', 'fixed_members': ['member_001', 'member_002'], 'seed': 1}
            for i in range(12)]
    panel, ledger, authority = folder / 'panel.json', folder / 'pilot.sqlite', folder / 'authority.json'
    save(panel, {'rows': rows})
    save(authority, {'version': api.AUTHORITY_VERSION, 'ledger_path': str(ledger),
                    'cap_nanoyuan': 150_000_000_000, 'panel_sha256': reference(panel)['sha256'], 'approved': True})
    view = api.group_api('REVIEW2', ledger, max_concurrency=8, panel_ref=reference(panel),
                         cash_authority_ref=reference(authority))
    return rows, view


class HoldingExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, function, *args):
        future = Future()
        self.submitted.append({'function': function.__name__, 'row': args[0]})
        return future


def queue_controls():
    spec = importlib.util.spec_from_file_location('cpu_passive_queue', ROOT / 'tools/run_passive_pilot_v203_2_1.py')
    queue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(queue)
    class ResourceBusy(RuntimeError):
        pass
    queue.scope = SimpleNamespace(MAX_GENERATIONS=8, MAX_STARTUPS=4, ResourceBusy=ResourceBusy,
        never_consumed=lambda row: True, load=lambda ref: json.loads(Path(ref['path']).read_text()))
    rows, api_view = setup_api(RUN / 'queue-cash')
    view = SimpleNamespace(settled_route_witnesses=lambda: {'PROJECT': 'cpu-only'},
                           logical_resident=lambda: {}, transport_factory=lambda *args: None)
    runtime = SimpleNamespace(for_group=lambda group: view)
    def build(name, plan_rows=rows):
        out = RUN / name
        admission = FairAdmission(('REVIEW2',), control=DrainControl(out / 'control.json',
            batch_root=out, groups=('REVIEW2',), maximum=8), maximum=8, maximum_startups=4)
        coordinator = queue.Coordinator(runtime=runtime, implementation=SimpleNamespace(), grading=None,
            memory=None, admission=admission, plan={'rows': copy.deepcopy(plan_rows)},
            qualifications={row['instance_id']: {'passed': True} for row in plan_rows}, output=out,
            cash_status=lambda group: {'state': 'ready', 'can_start_generation': True})
        return coordinator
    results = {}
    controller = build('gate-complete-score-false')
    executor = HoldingExecutor()
    controller._admit(executor)
    assert [item['row']['slot_index'] for item in executor.submitted] == [2032100, 2032101]
    assert len(controller.pending['REVIEW2']) == 10
    results['first_two_only'] = {'passed': True, 'first_wave': [2032100, 2032101], 'planned_denominator': 12,
                                 'submissions_are_unexecuted_futures': True}
    for row in rows[:2]:
        controller.admission.leave(row)
        measurement = controller.output / (str(row['slot_index']) + '-measurement.json')
        save(measurement, {'integrity': {'status': 'COMPLETE'}})
        controller.finished[row['slot_id']] = {'status': 'closed', 'row': row, 'measurement': reference(measurement)}
        controller.usage_records[row['slot_id']] = {'complete': True, 'called': True, 'unresolved_requests': 0}
        controller.completed_scores[row['slot_id'] + ':code'] = {'official_endpoint': {'resolved': False}}
    controller.generation.clear()
    controller._admit(executor)
    assert len(executor.submitted) > 2 and not controller.stop_new_generation.is_set()
    gate = json.loads((controller.output / 'engineering-gate.json').read_text())
    assert gate['passed'] and gate['scores_used_for_gate'] is False and gate['included_in_planned_denominator'] is True
    results['measurement_complete_with_failed_scores_proceeds'] = {'passed': True, 'gate': gate,
                                                                   'later_fake_submissions': len(executor.submitted) - 2}
    partial = build('gate-partial-score-true')
    partial.pending['REVIEW2'].popleft()
    partial.pending['REVIEW2'].popleft()
    partial.admission.remove_pending('REVIEW2', [row['slot_id'] for row in rows[:2]])
    for row in rows[:2]:
        measurement = partial.output / (str(row['slot_index']) + '-measurement.json')
        save(measurement, {'integrity': {'status': 'PARTIAL' if row == rows[0] else 'COMPLETE'}})
        partial.finished[row['slot_id']] = {'status': 'closed', 'measurement': reference(measurement)}
        partial.usage_records[row['slot_id']] = {'complete': True, 'called': True, 'unresolved_requests': 0}
        partial.completed_scores[row['slot_id'] + ':code'] = {'official_endpoint': {'resolved': True}}
    stopped_executor = HoldingExecutor()
    partial._admit(stopped_executor)
    assert partial.stop_new_generation.is_set() and not stopped_executor.submitted
    assert not partial.entered_stop.is_set() and not partial.stop_new_scoring.is_set()
    results['partial_measurement_with_passed_scores_holds'] = {'passed': True, 'entered_work_cancelled': False}
    usage_failures = []
    for name, evidence in [('retry-usage-unknown', {'complete': False, 'called': True, 'unresolved_requests': 1}),
                           ('no-provider-request', {'complete': True, 'called': False, 'unresolved_requests': 0})]:
        unknown = build(name)
        unknown.pending['REVIEW2'].popleft()
        unknown.pending['REVIEW2'].popleft()
        unknown.admission.remove_pending('REVIEW2', [row['slot_id'] for row in rows[:2]])
        for row in rows[:2]:
            measurement = unknown.output / (str(row['slot_index']) + '-measurement.json')
            save(measurement, {'integrity': {'status': 'COMPLETE'}})
            unknown.finished[row['slot_id']] = {'status': 'closed', 'measurement': reference(measurement)}
            unknown.usage_records[row['slot_id']] = evidence if row == rows[0] else {
                'complete': True, 'called': True, 'unresolved_requests': 0}
            unknown.completed_scores[row['slot_id'] + ':code'] = {'official_endpoint': {'resolved': True}}
        waiting = HoldingExecutor()
        unknown._admit(waiting)
        assert unknown.stop_new_generation.is_set() and not waiting.submitted and not unknown.entered_stop.is_set()
        gate = json.loads((unknown.output / 'engineering-gate.json').read_text())
        assert gate['passed'] is False and gate['shared_host_usage_complete'] is False
        usage_failures.append({'scenario': name, 'gate': gate})
    results['physical_usage_unknown_or_uncalled_holds_despite_complete_projection'] = {
        'passed': True, 'cases': usage_failures, 'entered_work_cancelled': False}
    isolated = build('local-exception')
    isolated._record_exception('candidate_preparation', rows[3], RuntimeError('local CPU preparation failure'))
    assert not isolated.stop_new_generation.is_set() and not isolated.stop_new_scoring.is_set()
    isolated._record_exception('generation', rows[4], PermissionError('shared authority inconsistency'))
    assert isolated.stop_new_generation.is_set() and isolated.stop_new_scoring.is_set()
    assert not isolated.entered_stop.is_set()
    results['local_error_isolated_shared_authority_drains'] = {'passed': True, 'entered_work_cancelled': False}
    saved_api = host.api_for
    try:
        host.api_for = lambda group: api_view
        # Exercise the actual _generation finally after cash admission but before
        # any fake episode enters. Three deferrals must not strand CNY120 of holds.
        deferred = build('preentry-resource-deferred')
        def busy(*args, **kwargs):
            raise ResourceBusy('fake capacity busy before entry')
        deferred.implementation = SimpleNamespace(run_episode=busy)
        for row in rows[:3]:
            assert deferred.admission.try_enter(row)
            result = deferred._generation(row)
            assert result['status'] == 'deferred'
        cash = api_view.BudgetLedger().cash_admission()
        assert cash['active_team_count'] == 0 and cash['remaining_team_holds_nanoyuan'] == 0 and cash['can_start']
        results['preentry_deferrals_release_cash'] = {'passed': True, 'cash': cash, 'fake_episodes_attempted': 3,
                                                     'actual_episode_objects': 0, 'physical_requests': 0}
        local = build('preentry-local-exception')
        def broken(*args, **kwargs):
            raise RuntimeError('fake local error before entry')
        local.implementation = SimpleNamespace(run_episode=broken)
        row = rows[3]
        assert local.admission.try_enter(row)
        try:
            local._generation(row)
        except RuntimeError as error:
            assert str(error) == 'fake local error before entry'
        else:
            raise AssertionError('Original local error was replaced')
        assert api_view.BudgetLedger().cash_admission()['active_team_count'] == 0
        results['preentry_local_exception_releases_cash'] = {'passed': True, 'original_error_preserved': True}
    finally:
        host.api_for = saved_api
    return results


def physical_capture_controls():
    rows, view = setup_api(RUN / 'physical-host')
    row = rows[0]
    schemas = {'REVIEW2': {member: [] for member in row['fixed_members']}}
    runtime = host.runtime_for(apis={'REVIEW2': view}, schemas=schemas,
        counter=lambda wire: {'prompt_tokens': 10, 'request_sha256': digest(json_bytes(wire))},
        authorize=lambda *args, **kwargs: None, api_key='cpu-unused-placeholder', max_concurrency=8)
    view.BudgetLedger().cash_admission(row['slot_id'])
    route = host.HostTeamTransport(runtime, row, RUN / 'physical-host/route')
    packets, bodies = [], []
    class Response:
        status, length, chunked, chunk_left = 200, 0, False, None
        def __init__(self, body):
            self.body, self.offset = body, 0
        def read1(self, maximum):
            data = self.body[self.offset:self.offset + maximum]
            self.offset += len(data)
            return data
    class Connection:
        def __init__(self, *args, **kwargs):
            self.sock = SimpleNamespace(settimeout=lambda value: None)
        def connect(self):
            pass
        def request(self, method, path, *, body, headers):
            assert (method, path) == ('POST', '/chat/completions')
            packets.append(body)
        def getresponse(self):
            body = {'id': 'cpu-body-' + str(len(packets)), 'model': 'deepseek-flash',
                    'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'CPU'}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 1, 'total_tokens': 11,
                              'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 10}}
            raw = b'\n \n' + json.dumps(body, indent=2).encode()
            bodies.append(raw)
            return Response(raw)
        def close(self):
            pass
    original_connection = api.http.client.HTTPSConnection
    api.http.client.HTTPSConnection = Connection
    outputs, errors = [], []
    try:
        def call(ordinal):
            wire = {'model': view.MODEL, 'messages': [{'role': 'user', 'content': 'CPU scripted condenser'}],
                    'max_tokens': 10, 'thinking': {'type': 'disabled'}, 'temperature': 1.0,
                    'top_p': 1.0, 'stream': False, 'user_id': view.slot_user_id(row['slot_id'] + ':member_001', 'REVIEW2')}
            payload = {'wire': wire, 'member_id': 'member_001', 'team_slot_id': row['slot_id'],
                       'request_id': row['slot_id'] + f':member_001:{ordinal:04d}', 'slot_id': row['slot_id'],
                       'condition': 'REVIEW2', 'usage_id': 'condenser', 'prompt_upper_bound': 10}
            before = copy.deepcopy(payload)
            try:
                outputs.append(route.post('/chat/completions', payload))
                assert payload == before
            except Exception as error:
                errors.append(repr(error))
        thread = threading.Thread(target=call, args=(1,), name='cpu-fifo-capture-control')
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive() and not errors, errors
        with ObserverJournal(route.physical_journal_path) as journal:
            records = list(journal.records())
        assert len(records) == 2
        assert base64.b64decode(records[0]['payload']['raw_base64']) == packets[0]
        assert base64.b64decode(records[1]['payload']['raw_base64']) == bodies[0]
        assert outputs[0] == json.loads(bodies[0])
        def unavailable(*args, **kwargs):
            raise OSError('CPU physical observer unavailable')
        route.client.transport.physical_capture = unavailable
        thread = threading.Thread(target=call, args=(2,), name='cpu-fifo-capture-failure')
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive() and not errors, errors
        assert outputs[1] == json.loads(bodies[1]) and len(packets) == 2
        assert route.client.transport.capture_faults == 2
        assert view.BudgetLedger().team_snapshot(row['slot_id'])['known_actual_tokens'] == 22
    finally:
        api.http.client.HTTPSConnection = original_connection
    return {'passed': True, 'construction_thread_differs_from_post_thread': True,
            'fake_HTTP_requests': len(packets), 'real_network_requests': 0,
            'request_body_bytes_exact': True, 'response_including_keepalive_whitespace_bytes_exact': True,
            'capture_failure_preserved_return_and_settlement': True, 'replayed_requests': 0,
            'observed_request_and_response_records': len(records), 'capture_faults': 2,
            'raw_response_hashes': [hashlib.sha256(body).hexdigest() for body in bodies]}


def main():
    ART.mkdir(parents=True, exist_ok=False)
    RUN.mkdir(parents=True, exist_ok=False)
    source_names = ['tools/run_passive_pilot_v203_2_1.py',
                    'src/proworksim/software_benchmark_deepseek_api_v203_2_1.py',
                    'src/proworksim/software_benchmark_host_api_v203_2_1.py']
    sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_names}
    cases = queue_controls()
    cases['host_raw_cross_thread_and_fail_open'] = physical_capture_controls()
    summary = {'passed': True, 'cases': cases, 'case_count': len(cases), 'source_sha256': sources,
               'source_unchanged_during_control': all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value
                                                    for name, value in sources.items()),
               'real_model_API_calls': 0, 'actual_teams_launched': 0, 'Docker_objects': 0,
               'fake_plan_denominator': 12, 'production_gate_qualification_not_inferred': True}
    save(ART / 'summary.json', summary)
    print(json.dumps({'passed': True, 'cases': len(cases), 'summary': str(ART / 'summary.json')}))


if __name__ == '__main__':
    main()
