"""CPU deployment wiring only: no episode, API, container, process or service runs."""
from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
import pytest
from proworksim import software_benchmark_alignment_contract_v130 as contract
from proworksim import software_benchmark_episode_v130 as episode
from proworksim import software_benchmark_runtime_inputs_v130 as inputs
from proworksim import software_benchmark_sdk_bundle_v130 as bundle
from proworksim.software_benchmark_candidates_v054 import checked, write_new
from proworksim.software_benchmark_project_closure_v130 import validate_slot_identity
from proworksim.software_benchmark_public_context_v062 import VERSION as CONTEXT_VERSION
from proworksim.software_benchmark_public_tests_v110 import VERSION as TEST_VERSION
from proworksim.storage import digest
ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(autouse=True)
def prohibit_external_work(monkeypatch):

    def refuse(*_args, **_kwargs):
        raise AssertionError('This preparation wiring control cannot dispatch external work')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(os, 'system', refuse)

def load_controller(arm):
    name = f'run_{arm.lower()}_controller_v130'
    spec = importlib.util.spec_from_file_location('deployment_control_' + name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def frozen_fixture(tmp_path, arm='PROJECT'):
    task = {'instance_id': 'fixture__alignment-110', 'repo': 'fixture/repo', 'base_commit': 'a' * 40, 'problem_statement': 'The original unchanged public issue.'}
    condition = contract.condition(arm)
    row = {'slot_id': f"v130:{task['instance_id']}:{condition['condition_id']}:11", 'slot_index': 11000, 'instance_id': task['instance_id'], 'repo': task['repo'], 'seed': 11, 'source_slot_id': 'frozen-public-fixture', 'replicate': 1, 'arm': arm, 'execution_arm': arm, 'condition_id': condition['condition_id'], 'model_key': 'DEEPSEEK', 'thinking': False, 'measurement_kind': 'full_verified_comparison', 'generation_token_upper_bound': 5000000}
    config = {key: row[key] for key in ('slot_id', 'slot_index', 'seed', 'source_slot_id', 'replicate', 'execution_arm', 'condition_id')}
    config.update(configuration=write_new(tmp_path / 'condition.json', condition), public_task=task, dataset_revision='b' * 40)
    row['configuration'] = write_new(tmp_path / 'host-config.json', config)
    plan = write_new(tmp_path / 'plan.json', {'rows': [row], 'resources': {}})
    source_index = write_new(tmp_path / 'sources.json', {'fixture_only': True})
    authority = {'status': 'approved', 'execution_alignment_version': contract.VERSION, 'source_index': source_index, 'plan': plan}
    calls = []

    def guard(operation, **identity):
        calls.append((operation, identity))
        return copy.deepcopy(authority)
    policy = SimpleNamespace(ROOT=ROOT, BATCH_ROOT=tmp_path / 'batch', AUTHORIZATION_FILE=tmp_path / 'never-created-authorization.json', require_v066_allowed=guard)
    scope = SimpleNamespace(ROOT=ROOT, BATCH_ROOT=tmp_path / 'batch', dispatch_view=lambda supplied: policy if supplied is guard else None, load=lambda reference: json.loads(checked(reference).read_bytes()))
    return SimpleNamespace(row=row, config=config, condition=condition, authority=authority, scope=scope, guard=guard, calls=calls, policy=policy)

def test_real_builder_binds_all_six_call_sites_without_executing_episode(tmp_path):
    fixture = frozen_fixture(tmp_path)
    value = episode.build_episode(scope=fixture.scope, guard=fixture.guard)
    namespace = value._run.__globals__
    assert value.run_episode.__globals__['_run'] is value._run
    assert value.integration_points == {name: 1 for name in ('closure', 'actor_binding', 'actor_upload', 'ready', 'controller_inputs', 'controller_result', 'effective_deadline')}
    assert value.runtime is namespace['runtime'] is bundle
    assert value.runtime.actor_inputs is inputs.actor_inputs
    assert value.runtime.controller_inputs is inputs.controller_inputs
    assert namespace['validate_actor_ready'] is episode.validate_actor_ready
    assert namespace['validate_controller_result'] is episode.validate_controller_result
    assert 'software_benchmark_project_closure_v130' in value._run.__code__.co_names
    assert 'software_benchmark_project_closure_v064' not in value._run.__code__.co_names
    assert 'actor_inputs' in value._run.__code__.co_names
    assert 'controller_inputs' in value._run.__code__.co_names
    assert 'validate_actor_ready' in value._run.__code__.co_names
    assert 'validate_controller_result' in value._run.__code__.co_names
    assert '/pws/control/public-test-contract.json' in value._run.__code__.co_consts
    assert value.OwnedActorPair.__init__.__globals__['policy'] is fixture.policy
    assert fixture.calls == [('v066.run', {})]
    config, condition, limits = value._row_and_config(fixture.row, False)
    assert config == fixture.config and condition == fixture.condition
    assert limits['input_plus_output_tokens'] == 5000000
    fixture.calls.clear()
    with pytest.raises(ValueError, match='new v130'):
        value._row_and_config({**fixture.row, 'slot_id': fixture.row['slot_id'].replace('v130:', 'v108:', 1)}, False)
    assert fixture.calls == [], 'Stale identity must fail before the scope or any resource admission'
    assert not fixture.scope.BATCH_ROOT.exists()

def test_real_builder_rejects_missing_or_prior_experiment_grants(tmp_path):
    fixture = frozen_fixture(tmp_path)
    with pytest.raises(PermissionError):
        episode.build_episode()
    for authority in ({'status': 'approved', 'source_index': fixture.authority['source_index']}, {**fixture.authority, 'execution_alignment_version': 'v108-resume'}, {**fixture.authority, 'status': 'prepared'}, {**fixture.authority, 'source_index': None}):
        with pytest.raises(PermissionError, match='earlier experiment grant'):
            episode.build_episode(scope=fixture.scope, guard=lambda *_a, **_kw: authority)
    assert fixture.calls == []
    assert not fixture.scope.BATCH_ROOT.exists()

@pytest.mark.parametrize('arm', ['REF', 'PROJECT'])
def test_pure_actor_controller_inputs_reach_real_controller_validation(tmp_path, arm):
    fixture = frozen_fixture(tmp_path, arm)
    environment = {'kind': 'official_image', 'image_id': 'sha256:' + 'c' * 64, 'source_config_sha256': 'c' * 64, 'public_python': '/public/bin/python', 'environment': {'PATH': '/public/bin:/usr/bin:/bin', 'CONDA_PREFIX': '/public', 'UNRELATED_PRIVATE_VALUE': 'must-not-enter-controller'}}
    entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': fixture.row['instance_id'], 'argv': ['/public/bin/python', '-m', 'pytest'], 'cwd': '/testbed', 'timeout_seconds': 600, 'hidden_material_used': False}
    actor = {'instance_id': fixture.row['instance_id'], 'actor_image_id': environment['image_id'], 'baseline_head': 'a' * 40, 'baseline_tree': 'd' * 40, 'public_environment': environment, 'lifecycle_deadline': 90000, 'existing_outer_limits': {'cpu': 4, 'memory': 16 * 1024 ** 3}}
    original_actor = copy.deepcopy(actor)
    binding = inputs.actor_inputs(actor, public_test_entry=entry)
    assert actor == original_actor
    assert binding['config']['existing_outer_limits'] == actor['existing_outer_limits']
    assert binding['config']['public_test_contract_sha256'] == digest(binding['files']['public-test-contract.json'])
    assert binding['Docker_operations'] == 0 and binding['REF_file_is_immutable_authority'] is False
    assert binding['initial_file_mode'] == 292
    with pytest.raises(ValueError, match='bound once'):
        inputs.actor_inputs(binding['config'], public_test_entry=entry)
    ready = {'public_test_result_revision': inputs.RESULT_REVISION, 'public_test_selection_revision': TEST_VERSION, 'public_test_contract_sha256': binding['config']['public_test_contract_sha256'], 'public_dependency_admission_checked': True, 'public_dependency_profile': None}
    context = {'version': CONTEXT_VERSION, 'instance_id': fixture.row['instance_id'], 'visible_text': 'The same publicly admitted environment.', 'visible_facts': {'cwd': '/testbed'}, 'sources': {'private_fixture_reference': 'must-not-enter-controller'}}
    identity = {'thinking': False, 'model': 'deepseek-flash', 'model_key': 'DEEPSEEK', 'api_key': 'synthetic-not-a-credential'}
    result = inputs.controller_inputs(fixture.config, fixture.row, ready, identity, {'kind': 'fixture_fifo_only'}, public_context=context, public_environment=environment, public_test_entry=entry, actor_config=binding['config'])
    assert result['condition.json'] == checked(fixture.config['configuration']).read_bytes()
    config = json.loads(result['controller-config.json'])
    assert config['execution_alignment'] == contract.shared_strategy()
    assert config['public_test_entry'] == binding['config']['public_test_entry']
    assert config['public_test_contract_sha256'] == ready['public_test_contract_sha256']
    assert config['public_task'] == fixture.config['public_task']
    assert config['public_environment']['environment'] == {'PATH': '/public/bin:/usr/bin:/bin', 'CONDA_PREFIX': '/public'}
    assert 'sources' not in config['public_context'] and 'api_key' not in config['model_identity_value']
    assert ('/opt/pws-runtime/public-test.py' in config['public_context']['visible_text']) is (arm == 'REF')
    assert ('run_tests(selection=' in config['public_context']['visible_text']) is (arm == 'PROJECT')
    if arm == 'PROJECT':
        assert config['dataset_revision'] == fixture.config['dataset_revision'] and 'file_policy' in config
    else:
        assert 'dataset_revision' not in config and 'file_policy' not in config
    controller = load_controller(arm)
    assert controller.validate_config(config) == config
    for changes in ({'slot_id': config['slot_id'].replace('v130:', 'v108:', 1)}, {'execution_alignment': {}}, {'public_test_contract_sha256': 'unbound'}, {'execution_arm': 'PROJECT' if arm == 'REF' else 'REF'}, {'api_key': 'synthetic-not-a-credential'}):
        with pytest.raises(ValueError):
            controller.validate_config({**config, **changes})
    with pytest.raises(ValueError, match='exact selected-test protocol'):
        inputs.controller_inputs(fixture.config, fixture.row, {**ready, 'public_test_contract_sha256': '0' * 64}, identity, {}, public_context=context, public_environment=environment, public_test_entry=entry, actor_config=binding['config'])
    diagnostic = inputs.controller_inputs(fixture.config, fixture.row, ready, {}, {}, diagnostic=True, public_context=context, public_environment=environment, public_test_entry=entry, actor_config=binding['config'])
    assert controller.validate_config(json.loads(diagnostic['controller-config.json']))['diagnostic'] is True

def test_closure_accepts_only_exact_new_project_identity(tmp_path):
    fixture = frozen_fixture(tmp_path)
    expected = validate_slot_identity(fixture.row['slot_id'], fixture.row['instance_id'])
    assert expected['condition_id'] == contract.condition('PROJECT')['condition_id'] and expected['seed'] == 11
    for slot, task in ((fixture.row['slot_id'].replace('v130:', 'v108:', 1), fixture.row['instance_id']), (fixture.row['slot_id'].replace('PROJECT', 'REF'), fixture.row['instance_id']), (fixture.row['slot_id'], 'fixture__other-111'), (fixture.row['slot_id'][:-2] + '011', fixture.row['instance_id'])):
        with pytest.raises(ValueError):
            validate_slot_identity(slot, task)


def test_stale_actor_evidence_is_rejected_before_controller_dispatch():
    expected = {'public_test_result_revision': inputs.RESULT_REVISION,
                'public_test_contract_sha256': 'e'*64, 'public_test_dependencies': None}
    ready = {'public_test_selection_revision': TEST_VERSION,
             'public_test_contract_sha256': 'e'*64,
             'public_dependency_admission_checked': True, 'public_dependency_profile': None}
    with pytest.raises(ValueError, match='selected-test protocol'):
        inputs.validate_actor_selection(ready, expected)
    ready['public_test_result_revision'] = inputs.RESULT_REVISION
    assert inputs.validate_actor_selection(ready, expected)['public_test_result_revision'] == inputs.RESULT_REVISION


def test_actual_managed_executor_is_bound_to_new_evidence_function():
    from proworksim import software_benchmark_managed_actor_v130 as actor
    from proworksim import software_benchmark_managed_actor_v110 as old_actor
    from proworksim.software_benchmark_public_test_evidence_v130 import run_public_entry
    assert actor.ManagedOperationSession.execute.__globals__['run_public_entry'] is run_public_entry
    assert old_actor.ManagedOperationSession.execute.__globals__['run_public_entry'] is not run_public_entry
    assert 'public_test_environment_v130' in actor.ManagedOperationSession.execute.__code__.co_names


def test_ref_convenience_reports_zero_tests_as_failure(monkeypatch):
    spec = importlib.util.spec_from_file_location('v130_public_cli_test', ROOT/'tools/run_public_tests_v130.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from types import SimpleNamespace
    monkeypatch.setattr(module, 'library', lambda: SimpleNamespace(run_native_public_test=lambda _selection:
        {'passed': False, 'timed_out': False, 'returncode': 0, 'validation_status': 'no_tests', 'output': '0 passed'}))
    monkeypatch.setattr(module.sys, 'argv', ['public-test.py'])
    assert module.main() == 1
