"""Pure deployment bindings plus one real managed-public-test CPU route."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import pytest

from proworksim import software_benchmark_alignment_contract_v141 as contract
from proworksim import software_benchmark_managed_actor_v141 as actor
from proworksim import software_benchmark_runtime_inputs_v141 as inputs
from proworksim import software_role_baseline_contract_v141 as roles
from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim.software_benchmark_public_test_evidence_v141 import run_public_entry
from proworksim.repository_sources_v054 import snapshot_repository
from proworksim.storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]
TASK = 'fixture__repository-141'


def prepared(tmp_path, group):
    spec = roles.organization(group)
    condition = contract.condition(group)
    row = {'instance_id': TASK, 'seed': 141, 'source_slot_id': 'source-fixture',
           'condition_id': condition['condition_id'], 'group_id': group,
           'organization_id': group, 'arm': 'PROJECT', 'execution_arm': 'PROJECT',
           'model_key': 'DEEPSEEK', 'fixed_members': spec['fixed_members'],
           'member_count': spec['member_count'],
           'slot_id': f"v142:{TASK}:{condition['condition_id']}:141"}
    public = {'kind': 'official_image', 'image_id': 'sha256:'+'a'*64,
              'source_config_sha256': 'a'*64, 'public_python': '/public/bin/python',
              'environment': {'PATH': '/public/bin:/usr/bin:/bin', 'CONDA_PREFIX': '/public'}}
    entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': TASK,
             'argv': ['/public/bin/python', '-m', 'pytest'], 'cwd': '/testbed',
             'timeout_seconds': 60, 'hidden_material_used': False}
    base = {'instance_id': TASK, 'actor_image_id': public['image_id'],
            'baseline_head': 'c'*40, 'baseline_tree': 'd'*40, 'public_environment': public,
            'lifecycle_deadline': time.monotonic()+90,
            'maximum_lifecycle_seconds': 600, 'kept_outer_limit': 16*1024**3}
    binding = inputs.actor_inputs(base, public_test_entry=entry, row=row)
    config = binding['config']
    ready = {key: copy.deepcopy(config[key]) for key in (
        'organization_id', 'fixed_members', 'member_count', 'role_contract_version',
        'role_catalog_sha256', 'public_test_result_revision', 'public_test_contract_sha256')}
    ready.update(public_test_selection_revision=actor.PUBLIC_TEST_SELECTION_VERSION,
                 public_test_files_sha256={key: config[key] for key in inputs.PUBLIC_FILES},
                 public_dependency_admission_checked=True, public_dependency_profile=None)
    host = {key: row[key] for key in ('slot_id', 'seed', 'source_slot_id', 'condition_id')}
    host.update(configuration=write_new(tmp_path/(group+'-condition.json'), condition),
                public_task={'instance_id': TASK, 'repo': 'fixture/repository',
                             'base_commit': 'c'*40, 'problem_statement': 'A public fixture'},
                public_test_entry=entry, dataset_revision='e'*40)
    return row, public, entry, base, binding, ready, host


@pytest.mark.parametrize('group', ['S1', 'FREE2', 'REVIEW2'])
def test_inputs_reach_actual_new_condition_and_source_contract(tmp_path, group):
    row, public, entry, base, binding, ready, host = prepared(tmp_path, group)
    config = binding['config']
    assert config['kept_outer_limit'] == base['kept_outer_limit']
    assert 'organization_id' not in base
    assert 'public_fixture_diagnostic' not in config  # No old CHIEF/600s shortcut.
    assert actor.validate_role_actor_config(config)['id'] == group
    assert inputs.validate_actor_selection(ready, config)['public_test_result_revision'] == actor.RESULT_REVISION
    from proworksim.software_benchmark_public_context_v062 import VERSION as CONTEXT_VERSION
    context = {'version': CONTEXT_VERSION, 'instance_id': TASK,
               'visible_text': 'Public context', 'visible_facts': {'cwd': '/testbed'}}
    output = inputs.controller_inputs(host, row, ready,
        {'thinking': False, 'model': 'deepseek-flash', 'api_key': 'synthetic-private-key'}, {},
        public_context=context, public_environment=public, public_test_entry=entry,
        actor_config=config)
    controller = json.loads(output['controller-config.json'])
    assert controller['version'] == 'v142-role-baseline-controller-r1'
    assert controller['public_test_result_revision'] == actor.RESULT_REVISION
    assert controller['execution_alignment'] == contract.shared_strategy(group)
    assert controller['fixed_members'] == roles.organization(group)['fixed_members']
    assert 'api_key' not in controller['model_identity_value']
    contract.validate_controller_identity(controller)


@pytest.mark.parametrize('field', ['organization_id', 'role_catalog_sha256',
                                  'public_test_result_revision', 'public_test_files_sha256'])
def test_stale_ready_cannot_be_accepted(tmp_path, field):
    _, _, _, _, binding, ready, _ = prepared(tmp_path, 'REVIEW2')
    changed = copy.deepcopy(ready)
    changed[field] = 'stale'
    with pytest.raises(ValueError):
        inputs.validate_actor_selection(changed, binding['config'])


def test_read_only_runtime_bytes_are_bound_before_ready(tmp_path):
    _, _, _, _, binding, _, _ = prepared(tmp_path, 'FREE2')
    folder = tmp_path/'runtime'
    folder.mkdir()
    for key, name in actor.PUBLIC_FILE_NAMES.items():
        p = folder/name
        p.write_bytes(inputs.PUBLIC_FILES[key].read_bytes())
        p.chmod(0o444)
    public_contract = tmp_path/'public-test-contract.json'
    public_contract.write_bytes(binding['files']['public-test-contract.json'])
    public_contract.chmod(0o444)
    assert actor.verify_public_runtime_files(binding['config'], folder, public_contract) == {
        key: binding['config'][key] for key in inputs.PUBLIC_FILES}
    path = folder/'public-test-execution.py'
    path.chmod(0o644)
    path.write_text('stale implementation')
    path.chmod(0o444)
    with pytest.raises(ValueError, match='source differs'):
        actor.verify_public_runtime_files(binding['config'], folder, public_contract)


def test_real_managed_test_route_uses_v141_provenance(tmp_path, monkeypatch):
    from proworksim import software_benchmark_managed_actor_v064 as old_private_actor
    monkeypatch.setattr(old_private_actor, '_reap_private_children', lambda: None)
    checkout = tmp_path/'checkout'
    checkout.mkdir()
    (checkout/'test_small.py').write_text('def test_ok(): assert 2 + 2 == 4\n')
    baseline = snapshot_repository(checkout)
    spec = roles.organization('FREE2')
    config = {'instance_id': TASK, 'lifecycle_deadline': time.monotonic()+30,
              'organization_id': 'FREE2', 'fixed_members': spec['fixed_members'],
              'member_count': 2, 'role_contract_version': roles.VERSION,
              'role_catalog_sha256': roles.catalog_sha256(),
              'public_test_result_revision': actor.RESULT_REVISION,
              'public_test_contract_sha256': 'f'*64,
              **{key: digest(path.read_bytes()) for key, path in inputs.PUBLIC_FILES.items()}}
    entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': TASK,
             'argv': [sys.executable, '-m', 'pytest'], 'cwd': '/testbed',
             'timeout_seconds': 20, 'hidden_material_used': False}
    environment = {**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTEST_PLUGINS': ''}
    session = actor.ManagedOperationSession(config=config, baseline=baseline, entry=entry,
                                            environment=environment, root=checkout)
    ref = actor.baseline_source_reference(baseline)
    common = {'instance_id': TASK, 'source_reference': ref,
              'tree_sha256': baseline['tree']['tree_sha256'],
              'hard_deadline_monotonic': config['lifecycle_deadline'],
              'hidden_evaluation': False, 'arbitrary_command': False}
    preflight = actor.make_delta(baseline, baseline['files'], baseline['entry_metadata'],
                                request=dict(common, model_calls_before_preflight=0))
    session.execute('sync_preflight', preflight)
    request = dict(common, version=actor.WORLD_VERSION, actor_id='member_002', organization_id='FREE2',
                   call_index=1, public_test_selection_revision=actor.PUBLIC_TEST_SELECTION_VERSION,
                   public_test_selection={'kind': 'pytest', 'targets': ['test_small.py']})
    payload = actor.make_delta(baseline, baseline['files'], baseline['entry_metadata'], request=request)
    result, performed = session.execute('managed_public_test', payload)
    assert result['passed'] and result['counts']['passed'] == 1, result
    assert performed == {'operation_executed': True}
    assert result['execution']['public_test_result_revision'] == actor.RESULT_REVISION
    assert result['test_evidence']['root_counts_only']
    assert result['test_evidence']['source']['run_id']
    assert result['execution']['actor_id'] == 'member_002'
    assert result['execution']['managed_request_sha256'] == digest(json_bytes(request))
    assert actor.ManagedOperationSession.execute.__globals__['run_public_entry'] is run_public_entry
    invalid = actor.make_delta(baseline, baseline['files'], baseline['entry_metadata'],
                              request=dict(request, actor_id='member_003', call_index=2))
    with pytest.raises(ValueError, match='role, source'):
        session.execute('managed_public_test', invalid)
    assert session.test_calls == 1


def test_copied_worker_and_public_launcher_bind_new_implementation(monkeypatch):
    path = ROOT/'tools/run_managed_worker_docker_v141.py'
    spec = importlib.util.spec_from_file_location('v141_cpu_worker_binding', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.managed is actor
    assert module.serve.__globals__['managed'].run_public_entry is run_public_entry
    assert 'verify_public_runtime_files' in module.serve.__code__.co_names
    cli_path = ROOT/'tools/run_public_tests_v141.py'
    spec = importlib.util.spec_from_file_location('v141_cpu_cli_binding', cli_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    library = cli.library()
    assert 'public_test_execution_v141.py' in library.run_native_public_test.__code__.co_consts
    monkeypatch.setattr(cli, 'library', lambda: type('L', (), {'run_native_public_test': staticmethod(
        lambda *_: {'passed': False, 'timed_out': False, 'returncode': 0, 'output': '0 tests'})})())
    monkeypatch.setattr(cli.sys, 'argv', ['public-test.py'])
    assert cli.main() == 1
