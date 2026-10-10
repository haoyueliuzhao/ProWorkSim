"""Finite CPU admission for the new v045 roots and organization initialization.

Reuse unchanged v044 feedback/page evidence; measure only new native materials.
Programmed responses are CPU fixtures and never frozen-actor behavior samples.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
from types import SimpleNamespace

from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import reference, write

SOURCE = Path(__file__).resolve().parents[1]
VERSION = 'software-organization-diagnostic-v0.45'
PARENT_COMMIT = '4903232'
TEST_FILES = ('tests/test_software_organization_tasks_v045.py', 'tests/test_software_organization_v045.py',
    'tests/test_software_organization_runtime_v045.py', 'tests/test_measure_organization_work_v045.py',
    'tests/test_software_organization_execution_v045.py')
ENTRY_FILES = ('event_time.py', 'event_store.py', 'rules.py', 'migration.py')


def inherited_source_receipt():
    archive = subprocess.check_output(['git', 'archive', PARENT_COMMIT, 'src', 'scripts', 'tests'], cwd=SOURCE)
    rows = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as files:
        for item in files:
            if not item.isfile() or not item.name.endswith('.py'):
                continue
            before = files.extractfile(item).read()
            now = (SOURCE / item.name).read_bytes()
            rows[item.name] = {'sha256': digest(before), 'bytes': len(before), 'unchanged': now == before}
    parent = SOURCE / 'runs/v044-completion-controls/qualification/qualification.json'
    return {'kind': 'unchanged_inherited_source_and_evidence_reuse', 'parent_commit': PARENT_COMMIT,
        'passed': bool(rows) and all(x['unchanged'] for x in rows.values()), 'files': rows,
        'prior_qualification': reference(parent),
        'scope': 'Original tools, context projection, paging and local-stop algorithms remain byte-identical in their historical modules. New modules specialize v045 identities, populations, tasks and measurement. No old tokenizer/request/acceptance replay.',
        'old_model_slots_replayed': 0, 'historical_tokenizer_requests_replayed': 0}


def native_routes(destination, plan_path):
    from scripts.software_organization_v045 import assignments
    from scripts.software_context_replay_v044 import load_cpu_measurement
    from scripts.software_feedback_qualification_v044 import ProgrammedOutput, RecordingContext, RouteStopped
    from proworksim.software_organization_runtime_v038 import _CollectionOwner, close_runtime
    from proworksim.software_organization_runtime_v045 import build_runtime
    from proworksim.software_organization_v045 import build_software_collaboration_case, case_spec

    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    started = time.time()
    measurement = load_cpu_measurement(plan_path)
    rows, failures = [], []
    # One representative seed per distinct root/regime; the second seed changes
    # sampling only, not required initial material or neutral work instruction.
    units = [(r, u) for r in range(4) for u in assignments()[f'block-r{r}-s0']]
    for root_index, unit in units:
        route_id = unit['root_label'] + '-' + unit['condition']
        folder = destination / route_id
        folder.mkdir(exist_ok=False)
        identity = {'policy_version': 'cpu-private-program-v045', 'adapter_sha256': 'no-model-weights'}
        owner = SimpleNamespace(window_id='cpu-v045:' + route_id, recipe=copy.deepcopy(measurement.recipe),
            prepare_request=measurement.render, tokenizer=measurement.tokenizer, freeze_identity=lambda: copy.deepcopy(identity))
        program = ProgrammedOutput(owner, measurement)
        owner.transport = program
        context = RecordingContext(owner, folder / 'raw-transport', measurement, folder / 'measurements')
        prepared = build_software_collaboration_case(case_spec(unit['case_id'], condition=unit['condition'], first_member=unit['first_member']), folder / 'prepared')
        runtime, captured, interfaces = build_runtime(_CollectionOwner(owner, context), prepared, folder / 'runtime', require_exact_resident=True)
        actions, failure, previous_home = [], None, None
        initial_labels = list(runtime.labels)
        try:
            first = unit['first_member']
            actions_to_run = [(first, 'initial_read', 'read_file', {'path': ENTRY_FILES[root_index], 'start_line': 1, 'max_lines': 30}),
                (first, 'public_test', 'run_tests', {}),
                (first, 'consume_exact_home', 'read_file', {'path': ENTRY_FILES[root_index], 'start_line': 1, 'max_lines': 30})]
            actions_to_run += [(member, 'other_initial_member', 'read_file', {'path': ENTRY_FILES[root_index], 'start_line': 1, 'max_lines': 30})
                               for member in initial_labels if member != first]
            for member, stage, name, arguments in actions_to_run:
                runtime.sync_members()
                runtime.cursor = runtime.labels.index(member)
                context.stage = stage
                program.action = {'name': name, 'arguments': arguments}
                before_rows, before_responses = len(context.rows), len(program.responses)
                outcome = runtime.step()
                runtime.after_completed_opportunity(outcome)
                runtime.sync_members()
                checks = {'one_prepared_request': len(context.rows) == before_rows + 1,
                    'one_programmed_response': len(program.responses) == before_responses + 1,
                    'declared_action': outcome.get('decision', {}).get('action') == name,
                    'declared_arguments': outcome.get('decision', {}).get('arguments') == arguments}
                if len(context.rows) > before_rows:
                    checks['member_and_stage'] = context.rows[-1]['member'] == member and context.rows[-1]['stage'] == stage
                if stage == 'consume_exact_home' and len(context.rows) > before_rows:
                    selected_ref = next(r for r in context.rows[-1]['artifacts'] if Path(r['path']).name == 'selected-request.json')
                    messages = read_json(Path(selected_ref['path']))['messages']
                    decoded = []
                    for message in messages:
                        try:
                            decoded.append(json.loads(message.get('content', '')))
                        except (TypeError, ValueError):
                            pass
                    checks['exact_original_test_home_consumed'] = previous_home is not None and previous_home in decoded
                if stage == 'public_test':
                    previous_home = copy.deepcopy(outcome.get('response'))
                actions.append({'member': member, 'stage': stage, 'programmed_action': copy.deepcopy(program.action), 'outcome': outcome, 'checks': checks})
                write(folder / 'program-actions.json', actions)
                if not context.rows or context.rows[-1]['selected_hard_capacity_passed'] is not True:
                    raise RouteStopped('required_new_material_hard_context:' + stage)
                if (not all(checks.values()) or outcome.get('status') != 'running' or outcome.get('response', {}).get('ok') is not True
                        or not all(context.rows[-1]['preservation_checks'].values())
                        or not all(context.rows[-1]['protected_preservation_checks'].values())):
                    raise RouteStopped('required_cpu_action_or_preservation_failed:' + stage)
            expected_members = 1 if unit['condition'] == 'S1' else 2
            if len(initial_labels) != expected_members or len(runtime.labels) != expected_members:
                raise RouteStopped('unexpected_initial_or_hidden_member')
        except Exception as error:
            failure = {'type': type(error).__name__, 'message': str(error)}
            failures.append({'route_id': route_id, **failure})
        finally:
            snapshot = runtime.snapshot()
            close_runtime(runtime)
            row = {'route_id': route_id, 'case_id': unit['case_id'], 'condition': unit['condition'],
                'first_member': unit['first_member'], 'initial_labels': initial_labels,
                'passed': failure is None, 'failure': failure, 'measurements': context.rows,
                'programmed_responses': program.responses, 'runtime_snapshot': snapshot,
                'environment_preparation_cost': prepared.world._software()['environment_preparation_cost'],
                'new_model_calls': 0, 'model_weights_loaded': False, 'origin': 'cpu_programmed_fixture'}
            write(folder / 'route.json', row)
            rows.append({'route_id': route_id, 'passed': row['passed'], 'receipt': reference(folder / 'route.json'),
                'prepared_requests': len(context.rows), 'programmed_responses': len(program.responses),
                'minimum_selected_headroom': min((r['headroom_tokens'] for r in context.rows), default=None),
                'protected_margin_deficits': sum(r['protected_headroom_after_margin_tokens'] < 0 for r in context.rows)})
    result = {'version': VERSION, 'kind': 'twelve_new_material_native_cpu_routes', 'required_route_ids': [u['root_label']+'-'+u['condition'] for _,u in units],
        'passed': len(rows) == 12 and not failures, 'routes': rows, 'failures': failures,
        'native_measurement_identity': measurement.identity, 'tokenizer_statistics': measurement.statistics,
        'new_model_calls': 0, 'model_weights_loaded': False, 'new_backward_calls': 0, 'actual_gpu_work': 0,
        'programmed_responses': sum(r['programmed_responses'] for r in rows), 'prepared_requests': sum(r['prepared_requests'] for r in rows),
        'old_112_requests_replayed': 0, 'historical_routes_replayed': 0,
        'elapsed_seconds': time.time()-started,
        'scope': 'New root/regime initial request, file feedback, one original public-test home, actual subsequent SDK input, and every initial member. Finite legal-material evidence only, not arbitrary future exploration fit or model cooperation. Protected1024 margin diagnostic only. Program output/token accounting is separate CPU fixture cost, not real actor samples.'}
    write(destination / 'native-routes.json', result)
    return result


def qualify(destination):
    from scripts.software_organization_v045 import source_files
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    started = time.time()
    before = source_files()
    reuse = inherited_source_receipt()
    write(destination / 'inherited-source-reuse.json', reuse)
    if not reuse['passed']:
        raise ValueError('Undeclared inherited source change; preserve qualification failure evidence')
    runtime_plan = read_json(SOURCE/'runs/software-organization-v044-completion/plan.json')
    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'PYTHONDONTWRITEBYTECODE': '1', 'TOKENIZERS_PARALLELISM': 'false', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'OPENHANDS_SUPPRESS_BANNER': '1',
           'PYTHONPATH': os.pathsep.join([runtime_plan['runtime_dependency_path'], str(SOURCE/'src'), str(SOURCE)])}
    commands = [[str(SOURCE / '.venv/bin/python'), '-m', 'pytest', '-q', *TEST_FILES, '-k', 'not native_sdk', '--basetemp', str(destination / 'pytest-tmp')],
                [str(SOURCE / '.venv/bin/python'), '-m', 'ruff', 'check', 'src', 'tests', 'scripts'],
                [str(SOURCE/'runs/v016-sdk/resident-venv/bin/python'), '-m', 'pytest', '-q',
                 'tests/test_software_organization_runtime_v045.py::test_native_sdk_o3_birth_is_same_actor_private_session_and_shared_charged_pool',
                 '--basetemp', str(destination/'native-sdk-pytest-tmp')]]
    checks = []
    for i, argv in enumerate(commands):
        t = time.time()
        with (destination / f'check-{i}.log').open('x') as log:
            completed = subprocess.run(argv, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT)
        checks.append({'command': argv, 'exit_code': completed.returncode, 'elapsed_seconds': time.time()-t,
                       'skipped': 'skipped' in (destination/f'check-{i}.log').read_text(), 'log': reference(destination/f'check-{i}.log')})
    write(destination/'cpu-checks.json', {'checks': checks})
    # Native renderer/tokenizer uses the existing resident Python environment,
    # but no weights, optimizer, checkpoint or CUDA worker is loaded.
    plan = SOURCE/'runs/software-organization-v044-completion/plan.json'
    argv = [str(SOURCE/'runs/v016-sdk/resident-venv/bin/python'), '-m', 'scripts.software_organization_qualification_v045',
            '--native-routes', '--output', str(destination/'native'), '--plan', str(plan)]
    native = None
    if all(c['exit_code'] == 0 and not c.get('skipped') for c in checks):
        t = time.time()
        with (destination/'native.log').open('x') as log:
            completed = subprocess.run(argv, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT)
        checks.append({'command': argv, 'exit_code': completed.returncode, 'elapsed_seconds': time.time()-t, 'log': reference(destination/'native.log')})
        if (destination/'native/native-routes.json').exists():
            native = read_json(destination/'native/native-routes.json')
    evidence = {'source_reuse': reference(destination/'inherited-source-reuse.json'), 'cpu_checks': reference(destination/'cpu-checks.json')}
    if native:
        evidence['native_routes'] = reference(destination/'native/native-routes.json')
    for i, check in enumerate(checks):
        evidence[f'check_log_{i}'] = check['log']
    value = {'version': VERSION, 'passed': bool(native and native['passed'] and all(c['exit_code'] == 0 and not c.get('skipped') for c in checks) and before == source_files()),
        'source_files': source_files(), 'checks': checks, 'evidence': evidence,
        'new_model_calls': 0, 'model_weights_loaded': False, 'new_backward_calls': 0,
        'elapsed_seconds': time.time()-started, 'old_model_slots_replayed': 0,
        'scope': 'Affected v045 CPU contracts and twelve finite new-material native routes. Existing tools, page permissions and feedback qualification reused exactly; no historical tokenizer or model replay.'}
    write(destination/'qualification.json', value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-routes', action='store_true')
    parser.add_argument('--plan', type=Path)
    args = parser.parse_args()
    result = native_routes(args.output, args.plan) if args.native_routes else qualify(args.output)
    if not result['passed']:
        sys.exit(1)


if __name__ == '__main__':
    main()
