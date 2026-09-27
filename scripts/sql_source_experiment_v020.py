"""Pinned public-source CPU controls, explicitly not model/support/learning data."""
import argparse
import ast
import copy
import json
from pathlib import Path
import time

from proworksim.sql_source_v020 import (
    CASES, DB_PATH, DB_SHA, VERSION, WITNESSES, WRONG_VALID,
    assess_build, build_world, independent_expected, lineage, native_control,
    public_task, reference, rows_equal, task,
)
from proworksim.storage import atomic_write, digest, json_bytes


def _write(path, value):
    atomic_write(Path(path), json_bytes(value))


def run_case(assets, instance_id, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    row = task(assets, instance_id)
    _write(output / 'private/upstream-task.json', row)
    test_sources = row['test_cases']
    parsed = []
    for source in test_sources:
        try:
            tree = ast.parse(source)
            parsed.append({'syntax_valid': True,
                           'function_names': [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
                           'sha256': digest(source.encode()), 'executed': False})
        except SyntaxError as error:
            parsed.append({'syntax_valid': False, 'message': str(error), 'executed': False})
    _write(output / 'private/upstream-python-static.json', parsed)
    native = native_control(assets, row)
    _write(output / 'private/native-control.json', native)
    expected = independent_expected(instance_id, native['tables'])
    _write(output / 'private/independent-expected.json', expected)
    if not expected:
        raise AssertionError('Controls require a nonempty independent expected result')
    native_checks = {label: {'status': result['status'],
                            'rows': len(result.get('rows', [])),
                            'matches_independent': result['status'] == 'success' and rows_equal(result['rows'], expected),
                            'error': result.get('message')}
                     for label, result in native['queries'].items()}
    world = build_world(row, native['tables'], output)
    port = world.session('implementer', 'TEAM')
    initial = port.observe()
    _write(output / 'public-initial-observation.json', initial)
    calls = []

    def call(name, **arguments):
        response = port.call(name, request_key=instance_id + ':' + str(len(calls)), **arguments)
        calls.append({'tool': name, 'arguments': arguments, 'response': response})
        _write(output / 'calls.json', calls)
        if not response['ok']:
            raise ValueError(response)
        return response['result']

    data = call('read_alias', alias='data', work_id='TEAM::build')
    source_ref = data['reference']
    call('adopt', alias='data', **source_ref, policy='fixed', work_ids=['TEAM::build'])
    managed = {}
    good_ref = None
    good_product = None
    for label, sql in [('original_issue', None), ('host_witness', WITNESSES[instance_id]),
                       ('wrong_valid', WRONG_VALID[instance_id])]:
        if sql is not None:
            call('write_object', alias='code', work_id='TEAM::build', dependencies=[source_ref],
                 data={'models': [{'name': 'repair', 'sql': sql}], 'tests': [], 'config': {'exports': ['repair']}})
        call('read_alias', alias='code', work_id='TEAM::build')
        built = call('sql_build', work_id='TEAM::build', code_alias='code', output_alias='result', input_aliases=['data'])
        product = call('read_version', reference=built['reference'], work_id='TEAM::build')['data']
        assessed = assess_build(world, built['reference'], expected)
        provenance = world.state['artifacts'][built['reference']['object_id']]['versions'][built['reference']['version_id']]['execution_provenance']
        managed[label] = {**assessed, 'execution_status': built['execution_status'], 'error': built['error'],
                          'source_refs_match_adoption': provenance['source_references'] == {'data': source_ref},
                          'execution_provenance': provenance}
        if label == 'host_witness':
            good_ref, good_product = built['reference'], copy.deepcopy(product)
    # Editable JSON claims cannot forge the kernel's version-level build evidence.
    fake_ref = call('write_object', alias='result', data=good_product, dependencies=[source_ref], work_id='TEAM::build')
    managed['copied_correct_product_without_build'] = assess_build(world, fake_ref, expected)
    managed['old_good_version_after_wrong_build_and_copy'] = assess_build(world, good_ref, expected)
    initial_files = {alias: json.loads(world.store.version_path(world.state['artifacts'][oid], 'v1').read_text())
                     for alias, oid in initial['workspaces']['TEAM'].items()}
    public_bytes = json_bytes({'observation': initial, 'files': initial_files})
    private_excluded = all(key not in public_bytes for key in (b'"sol_sql"', b'"test_cases"', b'"independent-expected"'))
    for text in [*row['sol_sql'], *row['test_cases']]:
        private_excluded = private_excluded and text.encode() not in public_bytes
    checks = {
        'native_reference_and_witness_match_independent': all(native_checks[k]['matches_independent'] for k in ('private_reference', 'host_witness')),
        'native_original_issue_is_distinguishable': not native_checks['original_issue']['matches_independent'],
        'native_valid_wrong_is_distinguishable': native_checks['wrong_valid']['status'] == 'success' and not native_checks['wrong_valid']['matches_independent'],
        'native_write_attach_extension_denied': all(native_checks[k]['status'] == 'rejected_or_error' for k in ('write_negative', 'attach_negative', 'extension_negative')),
        'managed_real_witness_matches_independent': managed['host_witness']['passed'],
        'managed_original_issue_is_distinguishable': not managed['original_issue']['passed'],
        'managed_valid_wrong_is_distinguishable': managed['wrong_valid']['execution_status'] == 'success' and not managed['wrong_valid']['passed'],
        'editable_correct_product_cannot_forge_build': not managed['copied_correct_product_without_build']['passed'] and managed['copied_correct_product_without_build']['independent_rows_match'],
        'old_good_version_stays_good': managed['old_good_version_after_wrong_build_and_copy']['passed'],
        'exact_source_adoption_preserved': all(managed[k]['source_refs_match_adoption'] for k in ('original_issue', 'host_witness', 'wrong_valid')),
        'private_reference_tests_oracle_excluded_from_initial_role_view': private_excluded,
    }
    report = {'instance_id': instance_id, 'public_task': public_task(row),
              'projected_table_rows': {k: len(v['rows']) for k, v in native['tables'].items()},
              'sqlite_version': native['sqlite_version'], 'native': native_checks, 'managed': managed,
              'upstream_python_static': parsed, 'checks': checks, 'passed': all(checks.values()),
              'calls': len(calls), 'source_adoption': source_ref,
              'raw_refs': {name: reference(output / name) for name in ['calls.json', 'public-initial-observation.json', 'private/upstream-task.json', 'private/native-control.json', 'private/independent-expected.json']}}
    _write(output / 'report.json', report)
    return report


def main(assets, output):
    assets, output = Path(assets), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    report = {'version': VERSION, 'started_epoch': started, 'status': 'in_progress',
              'scope': 'CPU source admission, program witnesses and negative controls only; no model support, collaborative performance, official benchmark score or training evidence.',
              'case_ids': list(CASES), 'source_usage': 'interface_development_only',
              'gpu_calls': 0, 'model_calls': 0, 'training_examples': 0, 'parameter_updates': 0,
              'official_python_tests_executed': False, 'cases': []}
    try:
        report['lineage'] = lineage(assets)
        report['database_before'] = reference(assets / DB_PATH)
        for case in CASES:
            report['cases'].append(run_case(assets, case, output / case))
        report['database_after'] = reference(assets / DB_PATH)
        report['database_unchanged'] = report['database_before'] == report['database_after'] and report['database_after']['sha256'] == DB_SHA
        report['all_controls_pass'] = report['database_unchanged'] and all(r['passed'] for r in report['cases'])
        report['status'] = 'completed' if report['all_controls_pass'] else 'control_failure'
    except Exception as error:
        report.update(status='environment_or_control_error', error={'type': type(error).__name__, 'message': str(error)}, all_controls_pass=False)
        raise
    finally:
        report.update(finished_epoch=time.time(), elapsed_seconds=time.time() - started)
        _write(output / 'report.json', report)
    print(json.dumps({'output': str(output), 'cases': len(report['cases']), 'status': report['status'], 'all_controls_pass': report['all_controls_pass']}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', default='runs/assets/sql-v020')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = main(args.assets, args.output)
    raise SystemExit(0 if result['all_controls_pass'] else 1)
