"""Gated HOLD export and unique qualification. Never opens content on import.

Run from the frozen common source with an explicit project root. Export prepares
only data/dependencies after release; it cannot change shared executable code.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import copy
import json
import os
from pathlib import Path
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor

from proworksim.repository_sources_holdout_v051 import HOLD_IDS, PURPOSE, _safe_files
from proworksim.software_holdout_repo_tests_v051 import run_repository_tests, source_ref
from proworksim.storage import digest, json_bytes

VERSION = 'v051-holdout-source-qualification-v1'
STATES = ('baseline', 'defect', 'reference')
PROFILE_SHA = 'eadf29551ca2e706950d3f2311b47a3d08c2ccee3c8dd217fa299014a08e4286'
TARGETS = {'Suor/funcy': ('funcy', 'funcy'), 'un33k/python-slugify': ('slugify', 'slugify'),
           'pytest-dev/iniconfig': ('iniconfig', 'src/iniconfig'), 'Knio/dominate': ('dominate', 'dominate')}
PROTECTED = {'funcy', 'python-slugify', 'iniconfig', 'dominate'}


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError('Immutable qualification output already exists: ' + str(path))
    path.write_bytes(json_bytes(value))


def checked(ref):
    path = Path(ref['path'])
    if not path.is_absolute() or source_ref(path) != ref:
        raise ValueError('Use an intact absolute path/sha256/bytes reference')
    return path


def release_gate(project_root, release_path):
    """Only public gate records may be opened before this returns."""
    project = Path(project_root).resolve()
    release_path = Path(release_path).resolve()
    release = read(release_path)
    if (release.get('version') != 'v051-holdout-source-access-release-v1'
            or release.get('released') is not True or release.get('purpose') != PURPOSE):
        raise ValueError('Explicit post-CAL2 HOLD source access release is required')
    common_ref = release['common_implementation_freeze']
    common = read(checked(common_ref))
    if (common.get('version') != 'v051-holdout-common-implementation-freeze-v1'
            or common.get('frozen_before_business_material') is not True):
        raise ValueError('Shared implementation must be frozen before business material')
    snapshot = Path(common['source_root']).resolve()
    # A main checkout edited after content access cannot silently become active.
    for name, sha in common['source_files'].items():
        if digest((snapshot / name).read_bytes()) != sha:
            raise ValueError('Common implementation snapshot changed: ' + name)
    script = Path(__file__).resolve()
    if not script.is_relative_to(snapshot) or digest(script.read_bytes()) != common['source_files'].get(str(script.relative_to(snapshot))):
        raise ValueError('Execute the exporter from the sealed common source snapshot')
    env_ref = common['environment_template']
    checked(env_ref)
    return {'project': project, 'source_access_release': source_ref(release_path),
            'common_implementation_freeze': common_ref, 'environment_template': env_ref, 'common': common}


def file_map(root):
    root = Path(root)
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlink material requires an unsupported source adapter')
        if path.is_file():
            if '.git' in path.relative_to(root).parts:
                raise ValueError('Git history is not a public candidate file')
            files[str(path.relative_to(root))] = path.read_bytes().decode('utf-8')
    _safe_files(files)
    return files


def _literal(node, values):
    if isinstance(node, ast.Name) and node.id in values:
        return values[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal(node.left, values) + _literal(node.right, values)
    return ast.literal_eval(node)


def declared_dependencies(files):
    """Static profile default pip -e . metadata only; never execute setup.py.

    Unsupported dynamic declarations block the fixed repository. Extras not
    present in the upstream profile are not added, and target code is not built.
    """
    requirements, provenance = [], []
    if 'pyproject.toml' in files:
        import tomllib
        data = tomllib.loads(files['pyproject.toml'])
        project = data.get('project', {})
        if 'dependencies' in project.get('dynamic', []):
            raise ValueError('Dynamic pyproject dependencies cannot be frozen by this static adapter')
        requirements.extend(project.get('dependencies', []))
        provenance.append('pyproject.toml:project.dependencies')
    if 'setup.cfg' in files:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(files['setup.cfg'])
        if parser.has_option('options', 'install_requires'):
            requirements.extend(line.strip() for line in parser.get('options', 'install_requires').splitlines() if line.strip())
            provenance.append('setup.cfg:options.install_requires')
    if 'setup.py' in files:
        tree, values = ast.parse(files['setup.py']), {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                try:
                    value = _literal(node.value, values)
                except (ValueError, TypeError):
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        values[target.id] = value
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ((isinstance(node.func, ast.Name) and node.func.id == 'setup')
                    or (isinstance(node.func, ast.Attribute) and node.func.attr == 'setup')):
                for keyword in node.keywords:
                    if keyword.arg is None:
                        raise ValueError('Dynamic setup keyword dictionaries are unsupported')
                    if keyword.arg == 'install_requires':
                        requirements.extend(_literal(keyword.value, values))
                        provenance.append('setup.py:install_requires static literal')
    if any(not isinstance(value, str) or not value.strip() for value in requirements):
        raise ValueError('Only literal dependency requirement strings are admitted')
    return sorted(set(requirements)), provenance


def prepare_environment(template, files, destination, *, template_ref):
    """Resolve declared third-party wheels once, without touching frozen engine."""
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    destination = Path(destination)
    destination.mkdir(parents=True)
    requirements, metadata = declared_dependencies(files)
    for value in requirements:
        req = Requirement(value)
        if canonicalize_name(req.name) in PROTECTED or req.url:
            raise ValueError('Target packages and direct source URLs cannot enter the candidate environment')
    protected = {canonicalize_name(k): v for k, v in template['metadata']['packages'].items()}
    constraints = destination / 'protected-versions.txt'
    constraints.write_text(''.join(f'{name}=={version}\n' for name, version in sorted(protected.items())))
    dependencies, wheel_refs = destination / 'dependencies', []
    dependencies.mkdir()
    if requirements:
        wheels = destination / 'wheels'
        wheels.mkdir()
        command = [template['python_invocation'], '-m', 'pip', 'download', '--only-binary=:all:',
            '--dest', str(wheels), '--constraint', str(constraints), *requirements]
        with (destination / 'download.log').open('w') as output:
            subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=True)
        install = []
        for path in sorted(wheels.glob('*.whl')):
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                meta = [name for name in names if name.endswith('.dist-info/METADATA')]
                if len(meta) != 1:
                    raise ValueError('Wheel must have exactly one metadata record')
                from email.parser import Parser
                package = Parser().parsestr(archive.read(meta[0]).decode())
                name, version = canonicalize_name(package['Name']), package['Version']
                if name in PROTECTED or any(n.split('/')[0] in {'funcy', 'slugify', 'iniconfig', 'dominate'} for n in names):
                    raise ValueError('Dependency wheel contains a held-out target package')
                if name in protected:
                    if version != protected[name]:
                        raise ValueError('Frozen test-engine dependency replacement is prohibited')
                else:
                    install.append(str(path))
            wheel_refs.append(source_ref(path))
        if install:
            with (destination / 'install.log').open('w') as output:
                subprocess.run([template['python_invocation'], '-m', 'pip', 'install', '--no-deps', '--no-index',
                                '--target', str(dependencies), *install], stdout=output, stderr=subprocess.STDOUT, check=True)
    # No .pth/startup hook, target alias or replacement engine can hide here.
    for path in dependencies.rglob('*'):
        if path.suffix == '.pth' or path.name in {'sitecustomize.py', 'usercustomize.py'}:
            raise ValueError('Dependency startup injection is unsupported')
    value = {key: copy.deepcopy(template[key]) for key in ('python_minor', 'python_executable', 'runtime_paths', 'metadata')}
    value.update({'environment_template': template_ref, 'dependency_paths': [str(dependencies.resolve())], 'environment_template_sha256': digest(json_bytes(template)), 'declared_requirements': requirements,
        'declaration_sources': metadata, 'wheels': wheel_refs,
        'dependency_file_sha256': {str(path.relative_to(dependencies)): digest(path.read_bytes())
            for path in sorted(dependencies.rglob('*')) if path.is_file() and '__pycache__' not in path.parts},
        'correct_target_installed': False, 'engine_versions_unchanged': True})
    write(destination / 'environment.json', value)
    return value, source_ref(destination / 'environment.json')


def frozen_configuration(files):
    """Same pytest config precedence, with readonly byte-bound host parsing."""
    import iniconfig
    import tomllib
    chosen, entries = None, {}
    parser_ref = source_ref(iniconfig.__file__)
    for name in ('pytest.ini', '.pytest.ini', 'pyproject.toml', 'tox.ini', 'setup.cfg'):
        if name not in files:
            continue
        if name.endswith('.toml'):
            if 'ini_options' in tomllib.loads(files[name]).get('tool', {}).get('pytest', {}):
                chosen = name
                break
        else:
            parsed = iniconfig.IniConfig(name, data=files[name])
            entries[name] = {'sha256': digest(files[name].encode()), 'sections': parsed.sections}
            section = 'tool:pytest' if name == 'setup.cfg' else 'pytest'
            if section in parsed or name in {'pytest.ini', '.pytest.ini'}:
                chosen = name
                break
    return chosen, entries, parser_ref


def execution_identity(files, task, runtime_sources):
    """Computed before outcomes. Labels, case ID and state never affect execution."""
    payload = {'files': {name: files[name] for name in sorted(files)},
        'task': {key: copy.deepcopy(task[key]) for key in ('nodeids', 'test_engine', 'engine_spec', 'target_modules',
            'cpu_python', 'config_relative_path', 'frozen_test_hashes')},
        'runtime_sources': runtime_sources, 'limits': {'wall_seconds': 60, 'cpu_seconds': 55,
            'memory_bytes': 4294967296, 'file_bytes': 8388608, 'uid_thread_margin': 32},
        'file_mode_policy': 'UTF8 regular files materialized by fixed executor; no executable/symlink inputs',
        'initial_production_hashes': task.get('initial_production_hashes', {})}
    return digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def logical_plan(cells, runtime_sources):
    result, physical = [], {}
    for cell in cells:
        identity = execution_identity(cell['files'], cell['task'], runtime_sources)
        row = {key: value for key, value in cell.items() if key not in {'files', 'task'}}
        row['execution_identity'] = identity
        result.append(row)
        physical.setdefault(identity, {'files': cell['files'], 'task': cell['task']})
    return result, physical


def export_sources(*, project_root, source_root, release_path):
    gates = release_gate(project_root, release_path)
    project, output = gates['project'], Path(source_root).resolve()
    if output.exists():
        raise FileExistsError('A new immutable HOLD source destination is required')
    old = project / 'artifacts/software-calibration-v051/cal2-sources'
    metadata = read(old / 'task-selection.json')
    tasks = [row for row in metadata['selected'] if row['partition'] == 'HOLD']
    if [row['task_id'] for row in tasks] != list(HOLD_IDS):
        raise ValueError('Only the original eight ordered HOLD tasks may be exported')
    sources = {row['upstream']: row for row in read(old / 'source-download.json')['records']}
    bindings = {row['task_id']: row for row in read(old / 'initial-bindings.json')['records']}
    profile = source_ref(old / 'metadata/python-profiles.py')
    if profile['sha256'] != PROFILE_SHA:
        raise ValueError('The original fixed Python profile changed')
    template = read(checked(gates['environment_template']))
    output.mkdir(parents=True)
    exported, cells, environments = [], [], {}
    runtime = {name: source_ref(Path(__file__).resolve().parents[1] / 'src/proworksim' / name)
        for name in ('software_holdout_repo_tests_v051.py', 'software_calibration_shell_v051.py')}
    for selected in tasks:
        case = selected['task_id']
        row_out = {**copy.deepcopy(selected), 'qualification_passed': False}
        try:
            source, binding = sources[selected['upstream_repository']], bindings[case]
            raw_task = (old / selected['row_path']).read_bytes()
            if digest(raw_task) != selected['row_sha256']:
                raise ValueError('Original dataset row SHA changed')
            original = json.loads(raw_task)
            initial_raw = (old / binding['initial_files_path']).read_bytes()
            if digest(initial_raw) != binding['initial_files_sha256']:
                raise ValueError('Initial file-map SHA changed')
            initial = read(old / binding['initial_files_path'])['files']
            _safe_files(initial)
            if {name: digest(text.encode()) for name, text in initial.items()} != binding['file_sha256']:
                raise ValueError('Original initial source binding changed')
            clean = file_map(old / source['clean_root'])
            if {name: digest(text.encode()) for name, text in clean.items()} != source['file_sha256']:
                raise ValueError('Original clean repository binding changed')
            root = output / 'holdout' / case
            root.mkdir(parents=True)
            reference_root = root / 'private-reference'
            reference_root.mkdir()
            for name, text in initial.items():
                path = reference_root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode())
            patch = root / 'private-defect.diff'
            patch.write_bytes(original['patch'].encode())
            if digest(patch.read_bytes()) != binding['defect_patch_sha256']:
                raise ValueError('Original defect patch binding changed')
            command = ['git', 'apply', '--reverse', str(patch)]
            process = subprocess.run(command, cwd=reference_root, capture_output=True, text=True,
                env={**os.environ, 'GIT_CEILING_DIRECTORIES': str(reference_root.parent),
                     'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'})
            write(root / 'reference-application.json', {'command': command, 'returncode': process.returncode,
                  'stdout': process.stdout, 'stderr': process.stderr})
            if process.returncode:
                raise ValueError('The original inverse defect did not apply')
            reference = file_map(reference_root)
            if reference != clean:
                raise ValueError('Inverse-defect reference is not byte-identical to original baseline')
            repo = selected['upstream_repository']
            if repo not in environments:
                try:
                    env, env_ref = prepare_environment(template, clean, output / 'environments' / repo.replace('/', '__'), template_ref=gates['environment_template'])
                    environments[repo] = {'environment': env, 'reference': env_ref}
                except (ValueError, OSError, subprocess.SubprocessError) as error:
                    environments[repo] = {'blocked_reason': type(error).__name__ + ': ' + str(error)}
            if 'blocked_reason' in environments[repo]:
                raise ValueError(environments[repo]['blocked_reason'])
            env, env_ref = environments[repo]['environment'], environments[repo]['reference']
            target, source_root = TARGETS[repo]
            editable = [name for name in initial if name.startswith(source_root + '/') and name.endswith('.py')
                        and Path(name).name != 'conftest.py' and '/tests/' not in name]
            if not editable:
                raise ValueError('No original editable production files')
            f2p, p2p = original['FAIL_TO_PASS'], original['PASS_TO_PASS']
            ids = sorted(set(f2p + p2p))
            if not ids or set(f2p) & set(p2p):
                raise ValueError('Original F2P/P2P IDs must be disjoint and nonempty in union')
            engine_name = 'native_unittest' if target == 'slugify' else 'pytest'
            config, capabilities, parser = frozen_configuration(initial) if engine_name == 'pytest' else (None, {}, None)
            test_files = ['test.py'] if target == 'slugify' else sorted({name.split('::', 1)[0] for name in ids})
            if not set(test_files) <= set(initial):
                raise ValueError('An original test file is absent')
            # Every non-production byte is authoritative, including data/config/support.
            frozen = {name: digest(text.encode()) for name, text in initial.items() if name not in editable}
            engine = {'environment': env, 'environment_ref': env_ref, 'profile': profile,
                'frozen_ini_configs': capabilities, 'host_config_parser': parser,
                'script': 'test.py' if target == 'slugify' else None,
                'argv': ['--verbose'] if target == 'slugify' else None}
            row_out.update({'row_path': str((root / 'task.json').relative_to(output)),
                'source_binding': {'initial_files_path': str((root / 'initial-files.json').relative_to(output)),
                    'initial_files_sha256': digest(initial_raw), 'file_sha256': binding['file_sha256']},
                'public_test_nodeids': ids, 'editable_production_paths': editable, 'source_roots': [source_root],
                'pytest_config_in_repo': config, 'original_test_files': test_files,
                'test_engine': engine_name, 'engine_spec': engine, 'target_modules': [target],
                'cpu_python': template['python_invocation'], 'original_readonly_file_sha256': frozen})
            (root / 'task.json').write_bytes(raw_task)
            (root / 'initial-files.json').write_bytes(initial_raw)
            for state, files in (('baseline', clean), ('defect', initial), ('reference', reference)):
                files_path = root / (state + '-files.json')
                write(files_path, {'files': files})
                task = {'nodeids': ids, 'original_test_ids': ids, 'test_engine': engine_name, 'engine_spec': engine,
                    'target_modules': [target], 'cpu_python': template['python_invocation'], 'config_relative_path': config,
                    'frozen_test_hashes': frozen, 'initial_production_hashes': {name: digest(clean[name].encode()) for name in editable}}
                cells.append({'task_id': case, 'state': state, 'files': files, 'task': task,
                    'files_source': source_ref(files_path), 'task_row_source': source_ref(root / 'task.json'),
                    'FAIL_TO_PASS': f2p, 'PASS_TO_PASS': p2p})
        except Exception as error:
            row_out['blocked_reason'] = type(error).__name__ + ': ' + str(error)
        exported.append(row_out)
    logical, physical = logical_plan(cells, runtime)
    for row in exported:
        if 'blocked_reason' in row:
            logical.extend({'task_id': row['task_id'], 'state': state, 'execution_identity': None,
                'blocked_reason': row['blocked_reason'], 'passed': False} for state in STATES)
    order = {case: index for index, case in enumerate(HOLD_IDS)}
    logical.sort(key=lambda row: (order[row['task_id']], STATES.index(row['state'])))
    for identity, entry in physical.items():
        write(output / 'qualification/inputs' / (identity + '.json'), entry)
    plan = {'version': 'v051-holdout-source-execution-plan-v1', 'fixture_only': False, 'purpose': PURPOSE,
        'tasks': exported, 'logical_cells': logical, 'logical_state_count': 24,
        'prepared_logical_count': sum(row['execution_identity'] is not None for row in logical), 'planned_physical_execution_count': len(physical),
        'execution_identity_rule': 'Complete candidate map/test IDs/config/environment/runtime/limits before outcomes; failures also reused',
        'physical_inputs': {key: source_ref(output / 'qualification/inputs' / (key + '.json')) for key in physical},
        'runtime_sources': runtime, 'environment_template': gates['environment_template'],
        'repo_environments': environments, 'source_access_release': gates['source_access_release'],
        'common_implementation_freeze': gates['common_implementation_freeze'],
        'cpu_venv_python_invocation': template['python_invocation'],
        'original_static_sources': {name: source_ref(old / name) for name in
            ('task-selection.json', 'source-download.json', 'initial-bindings.json')},
        'new_model_calls': 0, 'new_test_executions': 0}
    write(output / 'qualification/plan.json', plan)
    return plan


def qualify_sources(*, project_root, source_root, release_path, runner=run_repository_tests):
    gates = release_gate(project_root, release_path)
    output = Path(source_root).resolve()
    plan_path = output / 'qualification/plan.json'
    plan = read(plan_path)
    if any(plan[key] != gates[key] for key in ('source_access_release', 'common_implementation_freeze', 'environment_template')):
        raise ValueError('Qualification must bind the same released pre-content implementation')
    run_root = output / 'qualification/physical'
    if run_root.exists():
        raise FileExistsError('Unique qualification already entered; do not automatically retry')
    run_root.mkdir()
    def execute(item):
        identity, ref = item
        value = read(checked(ref))
        if execution_identity(value['files'], value['task'], plan['runtime_sources']) != identity:
            raise ValueError('Pre-outcome execution identity changed')
        try:
            result = runner(**value, run_root=run_root / identity)
        except Exception as error:
            result = {'executed': False, 'passed': None, 'execution_fault': type(error).__name__ + ': ' + str(error)}
            write(run_root / identity / 'fault.json', result)
        return identity, result
    with ThreadPoolExecutor(max_workers=4) as pool:
        physical = dict(pool.map(execute, plan['physical_inputs'].items()))
    logical = []
    for row in plan['logical_cells']:
        if row['execution_identity'] is None:
            logical.append({**row, 'physical_result': None})
            continue
        result = physical[row['execution_identity']]
        statuses = {test['nodeid']: test['outcome'] for test in result.get('tests', [])}
        f2p = {node: statuses.get(node, 'missing') for node in row['FAIL_TO_PASS']}
        p2p = {node: statuses.get(node, 'missing') for node in row['PASS_TO_PASS']}
        behavior = (all(value in {'failed', 'error'} for value in f2p.values()) if row['state'] == 'defect'
                    else all(value == 'passed' for value in f2p.values())) and all(value == 'passed' for value in p2p.values())
        passed = bool(result.get('executed') is True and result.get('all_expected_tests_observed') is True
            and result.get('source_unchanged') is True and result.get('target_imports_from_this_tree') is True
            and result.get('original_id_bijection') is True and behavior)
        original = run_root / row['execution_identity'] / ('fault.json' if 'execution_fault' in result else 'result.json')
        logical.append({**row, 'F2P': f2p, 'P2P': p2p, 'passed': passed, 'physical_result': source_ref(original)})
    task_rows, qualified = [], []
    for row in plan['tasks']:
        row = copy.deepcopy(row)
        records = [entry for entry in logical if entry['task_id'] == row['task_id']]
        row['qualification_passed'] = len(records) == 3 and all(entry['passed'] for entry in records)
        if row['qualification_passed']:
            qualified.append(row['task_id'])
        else:
            row.setdefault('blocked_reason', 'Original three-state behavior or full formal execution provenance did not qualify')
        task_rows.append(row)
    manifest = {'version': 'v051-holdout-adapter-source-manifest-v1', 'purpose': PURPOSE,
        'fixture_only': False, 'source_qualification_complete': True, 'tasks': task_rows,
        **{key: plan[key] for key in ('cpu_venv_python_invocation', 'source_access_release', 'common_implementation_freeze', 'environment_template')}}
    manifest_path = output / 'holdout/adapter-manifest.json'
    write(manifest_path, manifest)
    summary = {'version': VERSION, 'fixture_only': False, 'completed': True, 'passed': len(qualified) == 8,
        'purpose': PURPOSE, 'source_root': str(output), 'adapter_manifest': source_ref(manifest_path),
        'qualified_case_ids': qualified, 'blocked_case_ids': [case for case in HOLD_IDS if case not in qualified],
        'task_count': 8, 'logical_state_count': 24, 'executed_logical_state_count': sum(row['execution_identity'] is not None for row in logical),
        'physical_execution_count': len(physical) if all(v.get('command_executed') is True for v in physical.values()) else None,
        'physical_runner_invocation_count': len(physical),
        'known_physical_execution_count': sum(v.get('command_executed') is True for v in physical.values()),
        'unresolved_physical_execution_count': sum(v.get('command_executed') is not True for v in physical.values()),
        'logical_cells': logical, 'tasks': [{'task_id': row['task_id'], 'passed': row['qualification_passed'],
            'blocked_reason': row.get('blocked_reason')} for row in task_rows],
        'pre_outcome_plan': source_ref(plan_path), 'new_model_calls': 0, 'CAL2_executions': 0,
        **{key: plan[key] for key in ('source_access_release', 'common_implementation_freeze', 'environment_template', 'repo_environments')},
        'scope': 'Fixed eight tasks, 24 logical states; execution deduplicated only by full pre-outcome identity; blocked tasks keep all four inventory rows and no transferred budget.'}
    write(output / 'qualification/summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export', 'qualify'])
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--source-access-release', required=True)
    args = parser.parse_args()
    function = export_sources if args.action == 'export' else qualify_sources
    value = function(project_root=args.project_root, source_root=args.source_root, release_path=args.source_access_release)
    print(json.dumps({key: value.get(key) for key in ('version', 'qualified_case_ids', 'blocked_case_ids', 'planned_physical_execution_count', 'physical_execution_count')}))


if __name__ == '__main__':
    main()
