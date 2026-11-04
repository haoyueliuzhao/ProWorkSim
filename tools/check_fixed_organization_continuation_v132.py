"""Narrow offline coordinator/host integration controls; no experiment dispatch."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    def deny(event, unused):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto', 'subprocess.Popen'}:
            raise AssertionError('No subprocess, model, network or Docker in the continuation CPU fixture')

    sys.addaudithook(deny)
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('continuation_fixture132', root / 'tools/run_fixed_organization_v132.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    from proworksim import software_benchmark_host_api_v132 as host
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    from proworksim.software_benchmark_group_admission_v132 import DrainControl, FairAdmission
    from proworksim.software_benchmark_host_memory_v132 import HostMemoryGate

    # This is a read-only schema check against the actual original wire/bundle;
    # the fixture never constructs a real client or reads the API key.
    schema_ref = host.prepare_schemas()
    plan_ref = reference(runner.scope.PLAN_FILE)
    plan = runner.scope.load(plan_ref)
    rows = [next(row for row in plan['rows'] if row['organization_id'] == group)
            for group in ('CHIEF', 'PIPELINE', 'REVIEW')]
    rejected = []
    for label, changed in (
        ('changed_seed', [{**rows[0], 'seed': rows[0]['seed'] + 1}]),
        ('duplicate_identity', [rows[0], rows[0]]),
    ):
        try:
            host.validate_fresh_rows({'eligible_first_generation': changed}, check_unused=False)
        except ValueError:
            rejected.append(label)
        else:
            raise AssertionError('Invalid first-attempt inventory accepted')
    original_never = runner.scope.never_consumed
    runner.scope.never_consumed = lambda row: False
    try:
        host.validate_fresh_rows({'eligible_first_generation': [rows[0]]})
    except ValueError:
        rejected.append('consumed_identity')
    else:
        raise AssertionError('An old consumed identity was admitted')
    finally:
        runner.scope.never_consumed = original_never

    class View:
        def __init__(self, owner, group):
            self.owner, self.group = owner, group

        def settled_route_witnesses(self):
            return {'PROJECT': 'existing-original-formal-response'}

        def logical_resident(self):
            return {'fixture': True}

        def transport_factory(self, row, folder):
            self.owner.routes.append(row['slot_id'])
            return {'fixture': True}

        @staticmethod
        def usage_for_slot(row):
            return {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': True}

    class Runtime:
        def __init__(self):
            self.routes = []

        def for_group(self, group):
            return View(self, group)

    def case(name, selected, *, induce_drain=False):
        path = output / name
        path.mkdir()
        control_path = path / 'admission.json'
        control = DrainControl(control_path, batch_root=path, groups=runner.GROUP_IDS, maximum=48)
        admission = FairAdmission(runner.GROUP_IDS, control=control, maximum=48, maximum_startups=8)
        memory, runtime = HostMemoryGate(), Runtime()
        entered, grades = set(), []
        original = write_new(path / 'old-unknown.json', {'status': 'technical_unknown',
            'error': {'type': 'FileNotFoundError', 'message': 'old missing controller, retained'}})
        continuation = {'original_plan': plan_ref, 'eligible_first_generation': selected,
            'original_results': [{'row': {**rows[2], 'slot_index': 9999, 'slot_id': 'fixture-old-unknown'},
                                  'result': original}]}
        local_continuation = path / 'continuation.json'
        write_new(local_continuation, continuation)

        def run_episode(row, resident, *, stop_event, api_transport_factory):
            assert not stop_event.is_set()
            if induce_drain:
                write_new(control_path, {'version': 'v132-fair-group-admission-r1', 'batch_root': str(path),
                    'mode': 'drain', 'groups': [], 'maximum_generations': 48, 'revision': 1, 'reason': 'CPU fixture'})
                admission.require_start(row)
                raise AssertionError('Drain must refuse before the first owned operation')
            if row['organization_id'] == 'CHIEF':
                raise RuntimeError('Scripted local preparation failure')
            admission.require_start(row)
            entered.add(row['slot_id'])
            folder = path / str(row['slot_index'])
            folder.mkdir()
            api_transport_factory(row, folder)
            return write_new(folder / 'result.json', {'status': 'closed', 'slot_id': row['slot_id'],
                'fixture_only': True, 'actual_model_calls': 0})

        class Grading:
            def prepare_score(self, result_ref, *, endpoint='code'):
                result = runner.scope.load(result_ref)
                directory = path / ('score-' + result['slot_id'].split(':')[2])
                directory.mkdir()
                return write_new(directory / 'request.json', {'directory': str(directory),
                    'resource_key': directory.name, 'slot_id': result['slot_id'], 'endpoint': endpoint,
                    'generation_result': result_ref})

            def run_request(self, request, *, stop_event):
                assert not stop_event.is_set()
                grades.append(request)
                return {'status': 'scripted_completion_only', 'actual_grading_calls': 0}

            def delivery_disposition(self, result_ref, code_request_ref):
                assert code_request_ref in grades
                return {'status': 'scripted_same_tree_delivery', 'scoring_request': None}

            @staticmethod
            def trustworthy_cleanup(ref):
                return True

        previous = (runner.scope.never_consumed, runner.scope.CONTINUATION_FILE)
        runner.scope.never_consumed = lambda row: row['slot_id'] not in entered
        runner.scope.CONTINUATION_FILE = local_continuation
        try:
            coordinator = runner.Coordinator(runtime=runtime, implementation=SimpleNamespace(run_episode=run_episode),
                grading=Grading(), memory=memory, admission=admission, continuation=continuation,
                qualifications={row['instance_id']: {'passed': True} for row in selected}, output=path / 'coordinator',
                cash_status=lambda group: {'state': 'ready', 'can_start_generation': True, 'cap_CNY': '100.00'})
            result = coordinator.execute()
            assert not coordinator.entered_stop.is_set()
            if induce_drain:
                assert not entered and not runtime.routes and not grades
                assert selected[0]['slot_id'] in result['deferred']
                assert not result['task_exceptions'] and not result['generation_records']
                assert admission.snapshot()['active_generation'] == 0
                assert not result['historical_started'] and len(result['historical_pending']) == 1
                assert not result['normal_phase_complete'] and result['normal_phase_closure'] is None
            else:
                assert len(entered) == len(runtime.routes) == len(grades) == 2
                assert set(result['task_exceptions']) == {rows[0]['slot_id']}
                assert result['generation_records']['fixture-old-unknown']['status'] == 'original_unknown_preserved'
                assert len(result['delivery_endpoints']) == 2
                assert not coordinator.stop_new_generation.is_set()
                assert result['normal_phase_complete'] and result['historical_started']
                phase = runner.scope.load(result['normal_phase_closure'])
                assert phase['scores_terminal'] == phase['delivery_endpoints_terminal'] == 2
                assert 'fixture-old-unknown' not in phase['task_exceptions_terminal']
                phase_time = Path(result['normal_phase_closure']['path']).stat().st_mtime_ns
                assert phase_time <= (path / 'coordinator/generation-records/9999.json').stat().st_mtime_ns
            return reference(path / 'coordinator/run-summary.json')
        finally:
            runner.scope.never_consumed, runner.scope.CONTINUATION_FILE = previous
            memory.close()

    normal = case('local-error-and-asynchronous-scoring', copy.deepcopy(rows))
    drain = case('drain-before-claim', [copy.deepcopy(rows[1])], induce_drain=True)
    summary = {'passed': True, 'version': runner.VERSION, 'actual_original_schema': schema_ref,
        'first_attempt_negative_controls': rejected, 'real_coordinator_scripted_control': normal,
        'real_coordinator_drain_control': drain, 'local_task_error_does_not_block_other_groups': True,
        'historical_missing_controller_not_promoted': True, 'drain_keeps_unentered_pending': True,
        'normal_code_and_delivery_terminal_before_historical_recovery': True,
        'drain_with_pending_does_not_start_historical_recovery': True,
        'entered_work_cancelled': False, 'new_diagnostics': 0, 'model_API_calls': 0,
        'Docker_operations': 0, 'actual_scoring_calls': 0, 'subprocesses': 0,
        'sources': [reference(host.__file__), reference(runner.__file__), reference(__file__)]}
    print(json.dumps(write_new(output / 'summary.json', summary)))


if __name__ == '__main__':
    main()
