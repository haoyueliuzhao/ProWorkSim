import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_api_scope_v085 as scope
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prepare = module('prepare85_test', 'prepare_api_recovery_v085.py')
runner = module('runner85_test', 'run_api_recovery_v085.py')
launcher = module('launcher85_test', 'launch_api_recovery_v085.py')


def test_terminal_recovery_keeps_exact_model_identity_and_administrative_boundary(tmp_path):
    row = {'slot_id': 'original', 'configuration': {'same': True}, 'condition_id': 'condition', 'model_key': 'DEEPSEEK'}
    quiet = write_new(tmp_path/'quiet.json', {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False})
    result = write_new(tmp_path/'result.json', {**row, 'status': 'closed', 'quiescence': quiet,
        'retained_objects': [], 'api_administrative_truncation': True})
    value = prepare.terminal_result(row, result)
    assert value['result'] == result and value['status'] == 'closed' and value['administrative_truncation']
    with pytest.raises(ValueError, match='another original identity'):
        prepare.terminal_result({**row, 'slot_id': 'other'}, result)


def test_terminal_recovery_refuses_unproven_cleanup(tmp_path):
    row = {'slot_id': 'original', 'configuration': {}, 'condition_id': 'c', 'model_key': 'DEEPSEEK'}
    quiet = write_new(tmp_path/'quiet.json', {'quiescent': False, 'cleanup_errors': [], 'create_result_unknown': False})
    result = write_new(tmp_path/'result.json', {**row, 'status': 'technical_unknown', 'quiescence': quiet})
    with pytest.raises(ValueError, match='quiescence'):
        prepare.terminal_result(row, result)


def score_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(scope.original, 'GRADING_ROOT', tmp_path)
    folder = tmp_path/'score-7'
    folder.mkdir()
    row = {'slot_id': 'original', 'slot_index': 7, 'configuration': {'same': True}}
    generation = {'status': 'closed', 'result': write_new(tmp_path/'result.json', {'frozen': True})}
    request = write_new(folder/'request.json', {'slot_id': row['slot_id'], 'configuration': row['configuration'],
        'resource_key': 'score-7', 'directory': str(folder), 'generation_result': generation['result']})
    return folder, row, generation, request


def test_unclaimed_fixed_score_may_resume_but_consumed_identity_never_replays(tmp_path, monkeypatch):
    folder, row, generation, request = score_fixture(tmp_path, monkeypatch)
    retained, job = prepare.original_score(row, generation, 'code')
    assert retained is None and job == ('code', row, request, True)
    (folder/'started.json').write_text('{}')
    retained, job = prepare.original_score(row, generation, 'code')
    assert retained['status'] == 'technical_unknown' and job is None


def test_existing_score_completion_is_imported_without_execution(tmp_path, monkeypatch):
    folder, row, generation, request = score_fixture(tmp_path, monkeypatch)
    completion = {'request': request, 'status': 'process_exited', 'returncode': 0}
    write_new(folder/'completion.json', completion)
    write_new(folder/'quiescence.json', {'resource_key': 'score-7', 'quiescent': True,
        'cleanup_errors': [], 'create_result_unknown': False})
    retained, job = prepare.original_score(row, generation, 'code')
    assert retained == {'request': request, 'completion': completion} and job is None


def test_episode_closures_use_new_parent_cycle_and_old_sources_stay_bound(tmp_path, monkeypatch):
    from proworksim import software_benchmark_episodes_v076 as original
    from proworksim import software_benchmark_api_parent_v076 as old_parent
    monkeypatch.setattr(scope, 'AUTH_FILE', tmp_path/'authorization.json')
    write_new(scope.AUTH_FILE, {'approved': True})
    policy, delegate = runner.episode_binding(lambda *args, **kwargs: {}, SimpleNamespace(admission=lambda: {}))
    assert delegate.OwnedActorPair.start.__globals__['parent'] is parent
    options = delegate.OwnedActorPair.create_container.__globals__['container_options']
    assert options.__globals__['parent'] is parent
    assert original.api_episode.__globals__['parent'] is old_parent
    assert policy.admission_snapshot.__globals__['pending_pairs'] is runner.resources.safe_pending_pairs


def test_new_unit_changes_only_its_own_NOFILE_and_preserves_compute_limits():
    spec = {**launcher.fixed_spec(), 'ownership_token': 'd'*32}
    command = launcher.command(spec)
    assert command[:2] == ['systemd-run', '--user']
    assert '--property=LimitNOFILE=16384' in command
    assert '--property=MemoryMax=64G' in command and '--property=CPUQuota=400%' in command
    assert not any(part in ('--system', 'restart', 'stop') for part in command)
    assert scope.prior.API_UNIT == 'proworksim-v083-api.service'
    assert scope.API_UNIT == 'proworksim-v085-api.service'


def test_new_API_runtime_initialization_uses_descriptor_managed_wrapper():
    import ast
    source = Path(runner.__file__).read_text()
    tree = ast.parse(source)
    calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == 'initialize_for_run']
    assert len(calls) == 1 and isinstance(calls[0].value, ast.Name) and calls[0].value.id == 'protected_api'


def test_pressure_probe_nested_binding_uses_new_service_identity():
    assert runner.OWNER_PROBE.__globals__['scope'] is scope
    namespace = {'scope': scope.prior}
    exec("def probe():\n return {'qualified': True, 'current_bytes': 0, 'max_bytes': scope.API_MEMORY_BYTES, 'cgroup': scope.API_UNIT}", namespace)

    class StatPath:
        def __truediv__(self, part):
            return self

        def read_text(self):
            return 'anon 0\nfile 0\ninactive_file 0\nfile_dirty 0\nfile_writeback 0\n'

    probe = runner.private_function(runner.OWNER_PROBE,
        previous=SimpleNamespace(owner_probe=namespace['probe']), Path=lambda _: StatPath())
    assert probe()['cgroup'] == 'proworksim-v085-api.service'
    assert namespace['scope'] is scope.prior
