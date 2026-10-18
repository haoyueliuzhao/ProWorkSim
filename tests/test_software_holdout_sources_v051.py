"""Synthetic-only HOLD engine/provider contracts, never business material."""
import hashlib
import json
from pathlib import Path

from proworksim.software_holdout_repo_tests_v051 import run_repository_tests

PROJECT = Path(__file__).resolve().parents[1]
ARTIFACT = PROJECT / 'artifacts/software-calibration-v051/hold-source-controls'


def environment():
    value = json.loads((PROJECT / 'artifacts/software-calibration-v051/hold-python310/environment-template.json').read_bytes())
    from proworksim.software_holdout_repo_tests_v051 import source_ref
    return {**{key: value[key] for key in ('python_minor', 'python_executable', 'runtime_paths', 'dependency_paths', 'metadata')},
        'environment_template': source_ref(PROJECT / 'artifacts/software-calibration-v051/hold-python310/environment-template.json')}


def spec(files, nodes, engine, target, **extra):
    env = environment()
    return {'nodeids': sorted(nodes), 'original_test_ids': sorted(nodes), 'test_engine': engine,
        'target_modules': [target], 'cpu_python': str(PROJECT / 'runs/v051-hold-cpu-venv/bin/python'),
        'engine_spec': {'environment': env, **extra}, 'config_relative_path': None,
        'frozen_test_hashes': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items() if k.startswith('test')},
        'initial_production_hashes': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items() if not k.startswith('test')}}


def test_pytest_same_name_config_capability_and_isolation():
    files = {'iniconfig/__init__.py': 'VALUE = 17\r\n', 'test_synthetic.py': '''import pathlib
import pytest
import iniconfig
from _pytest.config import findpaths

def test_candidate_and_capability():
    assert iniconfig.VALUE == 17
    assert pathlib.Path(iniconfig.__file__).is_relative_to(pathlib.Path.cwd())
    capability = findpaths.iniconfig
    assert capability is not iniconfig
    assert capability.__hold_frozen_config_only__ is True
    with pytest.raises(ValueError):
        capability.IniConfig('business.ini', data='x=123')
    with pytest.raises(ValueError):
        capability.IniConfig('business.ini')
    assert capability.IniConfig('.hold-empty-pytest.ini').sections == {'pytest': {}}
    with pytest.raises(PermissionError):
        pathlib.Path('/etc/passwd').read_bytes()

def test_known_failure():
    assert iniconfig.VALUE == 18
'''}
    task = spec(files, ['test_synthetic.py::test_candidate_and_capability', 'test_synthetic.py::test_known_failure'], 'pytest', 'iniconfig', frozen_ini_configs={})
    result = run_repository_tests(files=files, task=task, run_root=ARTIFACT / 'pytest-same-name')
    assert result['executed'], result['stdout']
    assert result['passed'] is False and result['returncode'] == 1
    assert result['source_unchanged'] and result['test_integrity']
    assert result['target_imports_from_this_tree'] and result['original_id_bijection']
    assert all(result['installed_target_packages_absent'].values())
    assert len(result['tests']) == 2 and result['isolation']['network'] == 'seccomp_denied'


def test_native_original_verbose_ids_under_python310():
    files = {'synthetic_target.py': 'VALUE = 17\r\n', 'test.py': '''import unittest
import synthetic_target
class Case(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(synthetic_target.VALUE, 17)
    def test_wrong(self):
        self.assertEqual(synthetic_target.VALUE, 18)
if __name__ == '__main__':
    unittest.main()
'''}
    task = spec(files, ['test_ok (__main__.Case)', 'test_wrong (__main__.Case)'], 'native_unittest', 'synthetic_target', script='test.py', argv=['--verbose'])
    result = run_repository_tests(files=files, task=task, run_root=ARTIFACT / 'native-ids')
    assert result['executed'], result['stdout']
    assert result['passed'] is False and result['returncode'] == 1
    assert result['source_unchanged'] and result['original_id_bijection']
    assert result['target_imports_from_this_tree'] and len(result['tests']) == 2
    assert [r['nodeid'] for r in result['tests']] == task['nodeids']
    assert [r['native_id'] for r in result['native_id_mapping']] == ['__main__.Case.test_ok', '__main__.Case.test_wrong']


def test_qualification_deduplicates_full_identity_before_outcomes(tmp_path, monkeypatch):
    import copy
    import pytest
    from scripts import software_holdout_sources_v051 as sources
    from proworksim.storage import json_bytes
    from proworksim.software_holdout_repo_tests_v051 import source_ref
    files = {'synthetic_target.py': 'VALUE = 17\n', 'test.py': '# original synthetic test\n'}
    task = spec(files, ['test_ok (__main__.Case)'], 'native_unittest', 'synthetic_target', script='test.py', argv=['--verbose'])
    cells = [{'task_id': case, 'state': state, 'files': files, 'task': task,
              'FAIL_TO_PASS': ['test_ok (__main__.Case)'], 'PASS_TO_PASS': []}
             for case in sources.HOLD_IDS for state in sources.STATES]
    logical, physical = sources.logical_plan(cells, {'runner': 'synthetic-frozen-sha'})
    assert len(logical) == 24 and len(physical) == 1
    changed = copy.deepcopy(cells[0])
    changed['task']['engine_spec']['argv'] = ['--verbose', 'changed']
    _, separated = sources.logical_plan([cells[0], changed], {'runner': 'synthetic-frozen-sha'})
    assert len(separated) == 2
    gates = {key: {'path': 'synthetic-' + key, 'sha256': 'synthetic', 'bytes': 1}
             for key in ('source_access_release', 'common_implementation_freeze', 'environment_template')}
    monkeypatch.setattr(sources, 'release_gate', lambda *args: gates)
    for identity, value in physical.items():
        sources.write(tmp_path / 'qualification/inputs' / (identity + '.json'), value)
    plan = {**gates, 'logical_cells': logical, 'runtime_sources': {'runner': 'synthetic-frozen-sha'},
        'tasks': [{'task_id': case, 'partition': 'HOLD', 'qualification_passed': False} for case in sources.HOLD_IDS],
        'physical_inputs': {identity: source_ref(tmp_path / 'qualification/inputs' / (identity + '.json')) for identity in physical},
        'cpu_venv_python_invocation': task['cpu_python'], 'repo_environments': {}}
    sources.write(tmp_path / 'qualification/plan.json', plan)
    calls = []
    def fake_runner(*, files, task, run_root):
        calls.append(run_root)
        run_root.mkdir()
        result = {'executed': False, 'passed': None, 'command_executed': False, 'tests': [], 'environment_errors': ['synthetic failure']}
        (run_root / 'result.json').write_bytes(json_bytes(result))
        return result
    summary = sources.qualify_sources(project_root=tmp_path, source_root=tmp_path, release_path='synthetic', runner=fake_runner)
    assert len(calls) == 1 and summary['physical_runner_invocation_count'] == 1
    assert summary['physical_execution_count'] is None and summary['known_physical_execution_count'] == 0
    assert summary['unresolved_physical_execution_count'] == 1
    assert summary['logical_state_count'] == len(summary['logical_cells']) == 24
    assert summary['completed'] and summary['qualified_case_ids'] == []
    assert summary['blocked_case_ids'] == list(sources.HOLD_IDS)
    assert len({row['physical_result']['sha256'] for row in summary['logical_cells']}) == 1
    with pytest.raises(FileExistsError):
        sources.qualify_sources(project_root=tmp_path, source_root=tmp_path, release_path='synthetic', runner=fake_runner)
    assert len(calls) == 1
    assert sources.declared_dependencies({'setup.py': "REQS=['thirdparty>=1']\nsetup(install_requires=REQS)\n"})[0] == ['thirdparty>=1']
    with pytest.raises(ValueError):
        sources.declared_dependencies({'setup.py': 'setup(**unknown)\n'})


def test_provider_fixture_reuses_same_receipt_and_preserves_readonly(tmp_path):
    import pytest
    from proworksim.repository_sources_holdout_v051 import RepositorySources, PURPOSE
    from proworksim.storage import digest, json_bytes
    raw = json.loads((ARTIFACT / 'pytest-same-name/input.json').read_bytes())
    files, task = raw['files'], raw['task']
    result = json.loads((ARTIFACT / 'pytest-same-name/result.json').read_bytes())
    directory = tmp_path / 'holdout'
    directory.mkdir()
    initial = json_bytes({'files': files})
    (directory / 'initial.json').write_bytes(initial)
    original = json_bytes({'problem_statement': 'Synthetic task only.',
        'FAIL_TO_PASS': ['test_synthetic.py::test_known_failure'],
        'PASS_TO_PASS': ['test_synthetic.py::test_candidate_and_capability']})
    (directory / 'task.json').write_bytes(original)
    row = {'task_id': 'cpu-hold-iniconfig', 'partition': 'HOLD', 'qualification_passed': True,
        'source_binding': {'initial_files_path': 'holdout/initial.json', 'initial_files_sha256': digest(initial),
            'file_sha256': {name: digest(value.encode()) for name, value in files.items()}},
        'row_path': 'holdout/task.json', 'row_sha256': digest(original), 'public_test_nodeids': task['nodeids'],
        'editable_production_paths': ['iniconfig/__init__.py'], 'upstream_repository': 'synthetic/fixture',
        'upstream_commit': 'synthetic', 'instance_id': 'synthetic', 'source_roots': ['iniconfig'],
        'pytest_config_in_repo': None, 'original_test_files': ['test_synthetic.py'],
        'test_engine': 'pytest', 'engine_spec': task['engine_spec'], 'target_modules': ['iniconfig']}
    manifest = {'version': 'v051-holdout-adapter-source-manifest-v1', 'purpose': PURPOSE, 'fixture_only': True,
        'cpu_venv_python_invocation': task['cpu_python'], 'tasks': [row]}
    (directory / 'adapter-manifest.json').write_bytes(json_bytes(manifest))
    with pytest.raises(ValueError):
        RepositorySources(tmp_path)
    provider = RepositorySources(tmp_path, allow_cpu_fixture=True, runner=lambda **kwargs: result)
    case = provider.build_case('cpu-hold-iniconfig')
    assert case['purpose'] == PURPOSE and case['holdout_evaluation'] and not case['training_eligible']
    assert 'FAIL_TO_PASS' not in json.dumps(case) and 'PASS_TO_PASS' not in json.dumps(case)
    changed = {**files, 'test_synthetic.py': '# replaced tests'}
    with pytest.raises(ValueError):
        provider.validate_files('cpu-hold-iniconfig', changed)
    assessed = provider.assess_files('cpu-hold-iniconfig', files, run_root=tmp_path / 'assessment')
    assert assessed['executed'] and assessed['passed'] is False
    assert assessed['observed_pass_fraction'] == .5 and assessed['test_nodes_observed'] == 2


def test_frozen_environment_and_environment_fault_attribution():
    import copy
    import pytest
    from proworksim.software_holdout_repo_tests_v051 import validate_environment, _attribution
    env = environment()
    assert validate_environment(env)
    changed = copy.deepcopy(env)
    changed['runtime_paths'] = ['/unbound']
    with pytest.raises(ValueError):
        validate_environment(changed)
    evidence = {'exceptions': [{'nodeid': 'synthetic', 'exception_chain': ['ImportError'],
        'trace_paths': ['/external/dependency.py']}], 'collection_errors': []}
    assert _attribution(evidence, {'module.py': 'x=1'}, {}, Path('/tmp/synthetic-tree'))['environment_errors']
