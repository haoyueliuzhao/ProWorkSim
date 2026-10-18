"""Prepare and, only after root release, execute the final shared v052 path."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from proworksim.software_bridge_sources_v052 import (
    TASK_IDS, RUNNER_SHA, HELPER_SHA, RepositorySources, checked, evaluation_identity,
    ordered_files, ref, run_repository_tests, tree_manifest, write_new,
)
from proworksim.storage import digest, json_bytes


VERSION = 'v052-shared-source-qualification-v1'
STATES = ('baseline', 'defect', 'reference')


def read(path):
    return json.loads(Path(path).read_bytes())


def files_at(path):
    root = Path(path).resolve()
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Original qualification trees cannot contain symlinks')
        if path.is_file():
            files[str(path.relative_to(root))] = path.read_bytes().decode('utf-8')
    return ordered_files(files)


def prepare(*, project_root, output_root):
    project, output = Path(project_root).resolve(), Path(output_root).resolve()
    if output.exists():
        raise FileExistsError('Prepare one new immutable qualification root')
    old = project / 'artifacts/software-calibration-v051/cal2-sources'
    r3 = project / 'runs/software-calibration-v051-cal2-r3'
    plan = read(r3 / 'plan.json')
    runner = Path(plan['source_root']) / 'src/proworksim/software_calibration_repo_tests_v051.py'
    helper = runner.with_name('software_calibration_shell_v051.py')
    if ref(runner)['sha256'] != RUNNER_SHA or ref(helper)['sha256'] != HELPER_SHA:
        raise ValueError('The exact final r3 engine/helper source must be reused')
    adapter_path = old / 'cal2/adapter-manifest.json'
    adapter = read(adapter_path)
    if [row['task_id'] for row in adapter['tasks']] != list(TASK_IDS):
        raise ValueError('Freeze the original six CAL2 task IDs without replacement')
    python = Path(adapter['cpu_venv_python_invocation']).absolute()
    prefix = python.parent.parent.resolve()
    environment_metadata = old / 'cal2/cpu-environment.json'
    environment = read(environment_metadata)
    if environment['python_executable'] != str(python) or environment['python_version'] != 'Python 3.12.3':
        raise ValueError('The original final CAL2 CPU interpreter declaration changed')
    runtime_roots = [prefix, Path('/usr/lib/python3.12')]
    libraries = [Path('/usr/lib/x86_64-linux-gnu') / name for name in
        ('libseccomp.so.2', 'libc.so.6', 'libm.so.6', 'libssl.so.3', 'libcrypto.so.3', 'libexpat.so.1', 'libz.so.1', 'libffi.so.8')]
    runtime = {'version': 'v052-final-r3-test-runtime-v1', 'fixture_only': False,
        'runner': ref(runner), 'shell_helper': ref(helper), 'python_invocation': str(python),
        'python_executable': ref(python.resolve()), 'original_environment': ref(environment_metadata),
        'python_version': environment['python_version'], 'pip_freeze': environment['pip_freeze'],
        'site_packages': [str(prefix / 'lib/python3.12/site-packages')],
        'runtime_file_trees': {str(root): tree_manifest(root) for root in runtime_roots},
        'os_library_refs': [ref(path) for path in libraries if path.exists()],
        'target_packages_installed': False, 'qualification_and_formal_entry': 'proworksim.software_bridge_sources_v052.run_repository_tests',
        'candidate_origin_scope': 'Fresh child; root/src prepend after pytest import; none of boltons/parse/xmltodict is installed or a pytest dependency; reference trees absent from Landlock allowlist',
        'original_r3_plan': ref(r3 / 'plan.json'), 'old_records_changed': False}
    output.mkdir(parents=True)
    runtime_path = output / 'runtime.json'
    write_new(runtime_path, runtime)
    provider = RepositorySources(old, runtime_manifest=runtime_path, expected_manifest_sha256=ref(adapter_path)['sha256'])
    downloads = {row['upstream']: row for row in read(old / 'source-download.json')['records']}
    bindings = {row['task_id']: row for row in read(old / 'initial-bindings.json')['records']}
    cells, physical = [], {}
    for row in adapter['tasks']:
        case = row['task_id']
        entry = provider._entry(case)
        clean = files_at(old / downloads[row['upstream_repository']]['clean_root'])
        defect = ordered_files(entry['files'])
        reference = files_at(old / bindings[case]['reference_root'])
        if clean != reference or {name: digest(text.encode()) for name, text in clean.items()} != downloads[row['upstream_repository']]['file_sha256']:
            raise ValueError('Existing reference/baseline full bytes changed')
        task = provider.runner_spec(case)
        # Qualification attribution baseline is common upstream, not an outcome.
        task['initial_production_hashes'] = {name: digest(clean[name].encode()) for name in entry['editable_paths']}
        for state, files in (('baseline', clean), ('defect', defect), ('reference', reference)):
            identity = evaluation_identity(files, task)
            cells.append({'task_id': case, 'state': state, 'execution_identity': identity,
                'source_row': ref(old / row['row_path']), 'files_sha256': digest(json_bytes(files)),
                'FAIL_TO_PASS': entry['FAIL_TO_PASS'], 'PASS_TO_PASS': entry['PASS_TO_PASS']})
            physical.setdefault(identity, {'files': files, 'task': copy.deepcopy(task)})
    if len(cells) != 18 or len(physical) > 18:
        raise ValueError('Exactly 18 logical source units; no extra qualification inventory')
    for identity, value in physical.items():
        write_new(output / 'inputs' / (identity + '.json'), value)
    new_plan = {'version': 'v052-source-qualification-plan-v1', 'runtime_manifest': ref(runtime_path),
        'source_root': str(old), 'adapter_manifest': ref(adapter_path),
        'logical_cells': cells, 'logical_unit_count': 18, 'physical_unit_count': len(physical),
        'physical_inputs': {identity: ref(output / 'inputs' / (identity + '.json')) for identity in physical},
        'existing_exact_execution_receipts_reused': 0,
        'reuse_analysis': 'Original maps/config/dependencies and r3 socket control reused. v051 three-state commands were unisolated with a different test entry/timeout. Final r3 model candidate results and 3-node control are not full original three-state identities. No old HOLD workspace is assessed.',
        'old_source_qualification': ref(old / 'cal2/qualification-v2/summary.json'),
        'old_socket_control': ref(project / 'artifacts/software-calibration-v051/socket-type-repair-r3/summary-r3.json'),
        'implementation_sources': {name: ref(project / name) for name in
            ('src/proworksim/software_bridge_sources_v052.py', 'scripts/software_bridge_sources_v052.py')},
        'qualification_executed': False, 'new_model_calls': 0,
        'requires_root_release_and_real_OH_terminal_entry_control': True}
    write_new(output / 'plan.json', new_plan)
    return {'plan': ref(output / 'plan.json'), 'runtime': ref(runtime_path), 'logical_unit_count': 18,
            'physical_unit_count': len(physical), 'new_test_executions': 0}


def qualify(*, output_root, release_path):
    output = Path(output_root).resolve()
    plan_ref = ref(output / 'plan.json')
    plan, release = read(output / 'plan.json'), read(release_path)
    if (release.get('version') != 'v052-shared-source-execution-release-v1' or release.get('released') is not True
            or release.get('plan') != plan_ref or release.get('logical_unit_bound') != 18
            or release.get('physical_unit_bound') != plan['physical_unit_count']
            or release.get('same_terminal_entry_control_passed') is not True):
        raise ValueError('Root must freeze the shared terminal path and exact finite source plan before execution')
    for reference in plan['implementation_sources'].values():
        checked(reference)
    checked(plan['runtime_manifest'])
    for reference in release['terminal_entry_control_refs']:
        checked(reference)
    runs = output / 'physical'
    runs.mkdir(exist_ok=False)
    def execute(item):
        identity, reference = item
        value = read(checked(reference))
        if evaluation_identity(value['files'], value['task']) != identity:
            raise ValueError('Predeclared full execution identity changed')
        execution = run_repository_tests(**value, run_root=runs / identity)
        return identity, execution
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(pool.map(execute, plan['physical_inputs'].items()))
    logical = []
    for cell in plan['logical_cells']:
        execution = results[cell['execution_identity']]
        statuses = {row['nodeid']: row['outcome'] for row in execution.get('tests', [])}
        f2p = {node: statuses.get(node, 'missing') for node in cell['FAIL_TO_PASS']}
        p2p = {node: statuses.get(node, 'missing') for node in cell['PASS_TO_PASS']}
        correct_behavior = all(status == 'passed' for status in p2p.values()) and all(
            status in ('failed', 'error') if cell['state'] == 'defect' else status == 'passed' for status in f2p.values())
        passed = bool(execution.get('executed') is True and execution.get('all_expected_tests_observed') is True
            and execution.get('source_unchanged') is True and execution.get('test_integrity') is True and correct_behavior)
        logical.append({**cell, 'passed': passed, 'F2P': f2p, 'P2P': p2p,
            'result': ref(runs / cell['execution_identity'] / 'result.json'),
            'bridge_binding': execution['bridge_binding']})
    qualified = [case for case in TASK_IDS if all(row['passed'] for row in logical if row['task_id'] == case)]
    summary = {'version': VERSION, 'completed': True, 'passed': len(qualified) == 6, 'fixture_only': False,
        'qualified_case_ids': qualified, 'blocked_case_ids': [case for case in TASK_IDS if case not in qualified],
        'source_root': plan['source_root'], 'adapter_manifest': plan['adapter_manifest'],
        'runtime_manifest': plan['runtime_manifest'], 'plan': plan_ref, 'release': ref(release_path),
        'logical_unit_count': 18, 'physical_runner_calls': len(results),
        'physical_command_completed': sum(value.get('command_executed') is True for value in results.values()),
        'logical_cells': logical, 'new_model_calls': 0, 'old_records_changed': False,
        'scope': 'One final shared interpreter/dependency/sandbox/test-entry qualification, complete identity dedup before outcomes, no retries or candidate selection.'}
    write_new(output / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'qualify'])
    parser.add_argument('--project-root')
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--release')
    args = parser.parse_args()
    if args.action == 'prepare':
        if not args.project_root:
            parser.error('--project-root is required for preparation')
        value = prepare(project_root=args.project_root, output_root=args.output_root)
    else:
        if not args.release:
            parser.error('--release is required for qualification')
        value = qualify(output_root=args.output_root, release_path=args.release)
    print(json.dumps({k: v for k, v in value.items() if k not in ('logical_cells',)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
