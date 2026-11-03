"""CPU-only public selection/world/actor controls; no benchmark process runs."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')

from proworksim import software_benchmark_public_tests_v110 as selection
from proworksim import software_benchmark_public_test_world_v110 as world
from proworksim import software_benchmark_managed_actor_v110 as actor
from proworksim.repository_sources_v054 import capture_repository
from proworksim.software_organization_runtime_v047 import DispatchDeadline


def entry(kind='pytest'):
    commands = {'pytest': ['-m', 'pytest'], 'sympy': ['bin/test'],
                'django': ['tests/runtests.py', '--noinput', '--parallel', '1']}
    return {'version': 'v064-repository-public-test-entry-r1', 'instance_id': 'fixture__v110',
            'argv': ['/public/python', *commands[kind]], 'cwd': '/testbed',
            'timeout_seconds': 600, 'hidden_material_used': False}


def tree():
    files = {'tests/test_math.py': 'def test_ok(): pass\n',
             'tests/i18n/tests.py': '# public Django test module\n',
             'sympy/core/tests/test_basic.py': '# public Sympy test module\n'}
    metadata = {name: {'kind': 'file', 'encoding': 'utf-8', 'mode': '100644'} for name in files}
    return files, metadata


def test_three_verified_frontends_compile_literals_and_keep_limits():
    files, metadata = tree()
    for kind in ('pytest', 'django', 'sympy'):
        original = entry(kind)
        selected, value = selection.selected_entry(original, files=files, entry_metadata=metadata)
        assert selected == original and value == {'kind': 'full'}
    selected, _ = selection.selected_entry(entry(), {'kind': 'pytest',
        'targets': ['tests/test_math.py::test_ok'], 'keyword': 'ok and not slow', 'markers': 'not slow'},
        files=files, entry_metadata=metadata)
    assert selected['argv'] == ['/public/python', '-m', 'pytest', '-k', 'ok and not slow',
                                 '-m', 'not slow', '--', 'tests/test_math.py::test_ok']
    selected, _ = selection.selected_entry(entry('django'), {'kind': 'django',
        'targets': ['i18n.tests.TranslationTests.test_lazy_objects']}, files=files, entry_metadata=metadata)
    assert selected['argv'] == ['/public/python', 'tests/runtests.py', '--noinput', '--parallel', '1',
                                 'i18n.tests.TranslationTests.test_lazy_objects']
    selected, _ = selection.selected_entry(entry('sympy'), {'kind': 'sympy',
        'targets': ['sympy/core/tests/test_basic.py'], 'keywords': ['test_ok', 'test_other']},
        files=files, entry_metadata=metadata)
    assert selected['argv'] == ['/public/python', 'bin/test', 'sympy/core/tests/test_basic.py',
                                 '-k', 'test_ok', 'test_other']
    assert selected['timeout_seconds'] == 600 and selected['cwd'] == '/testbed'
    assert selected['hidden_material_used'] is False


def test_unsupported_or_escaping_selections_cannot_build_a_command(tmp_path):
    files, metadata = tree()
    values = [
        {'kind': 'pytest', 'argv': ['sh', '-c', 'echo unsafe']},
        {'kind': 'pytest', 'targets': ['/tmp/test_x.py']},
        {'kind': 'pytest', 'targets': ['../test_x.py']},
        {'kind': 'pytest', 'targets': ['.git/config']},
        {'kind': 'pytest', 'targets': ['-p']},
        {'kind': 'pytest', 'keyword': '__import__(os)'},
        {'kind': 'pytest', 'markers': "foo or '__import__'"},
        {'kind': 'pytest', 'targets': ['tests/missing.py']},
        {'kind': 'django', 'targets': ['i18n']},
        {'kind': 'full', 'targets': ['tests/test_math.py']},
    ]
    for value in values:
        with pytest.raises(selection.PublicTestSelectionError):
            selection.selected_entry(entry(), value, files=files, entry_metadata=metadata)
    linked = {**files, 'tests/alias.py': '../tests/test_math.py'}
    metadata = {**metadata, 'tests/alias.py': {'kind': 'symlink', 'encoding': 'symlink-target', 'mode': '120000'}}
    with pytest.raises(selection.PublicTestSelectionError):
        selection.selected_entry(entry(), {'kind': 'pytest', 'targets': ['tests/alias.py']},
                                 files=linked, entry_metadata=metadata)
    repo = tmp_path/'repo'
    repo.mkdir()
    (repo/'alias').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(selection.PublicTestSelectionError):
        selection.selected_entry(entry(), {'kind': 'pytest', 'targets': ['alias']}, root=repo)


def test_real_managed_world_and_actor_preserve_version_quota_and_final_lock(tmp_path):
    public = tmp_path/'public'
    (public/'tests').mkdir(parents=True)
    (public/'tests/test_math.py').write_text('def test_ok(): pass\n')
    manifest = capture_repository(public, tmp_path/'snapshot', task_id='fixture__v110',
        problem_statement='Choose only publicly visible tests.', source_identity={
            'instance_id': 'fixture__v110', 'repo': 'fixture/repo', 'base_commit': 'a'*40,
            'dataset_revision': 'b'*40})
    baseline = json.loads((manifest.parent/'initial-tree.json').read_text())
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    session = actor.ManagedOperationSession(config={'instance_id': 'fixture__v110',
        'lifecycle_deadline': deadline.hard_at+100}, baseline=baseline, entry=entry(),
        environment={}, root=public)
    source = actor.baseline_source_reference(baseline)
    preflight = actor.make_delta(baseline, baseline['files'], baseline['entry_metadata'], request={
        'instance_id': 'fixture__v110', 'source_reference': source,
        'tree_sha256': baseline['tree']['tree_sha256'], 'hard_deadline_monotonic': deadline.hard_at,
        'hidden_evaluation': False, 'arbitrary_command': False, 'model_calls_before_preflight': 0})
    session.execute('sync_preflight', preflight)
    called = []
    def callback(**value):
        payload = actor.make_delta(baseline, value['files'], value['entry_metadata'], request=value['request'])
        result, receipt = session.execute('managed_public_test', payload)
        assert receipt['operation_executed'] is True
        return result
    def execute(chosen_entry, *, root, environment, request, candidate_tree_sha256):
        called.append(copy.deepcopy(chosen_entry))
        return {'passed': True, 'execution': {'executed': True,
            'input_tree_sha256': candidate_tree_sha256, 'source_reference': request['source_reference'],
            'argv': chosen_entry['argv'], 'cwd': '/testbed'},
            'groups': {'public_repository_tests': {'status': 'passed', 'passed': True,
                'executed': True, 'output': 'scripted CPU callback, no test process',
                'tests': [{'test_id': 'scripted-public', 'passed': True}]}},
            'repository_collection_errors': []}
    prepared = world.prepare_case(manifest, tmp_path/'world', max_total_tokens=5_000_000,
        public_test_callback=callback, deadline=deadline, public_test_entry=entry())
    port = world.SoftwareCollaborationPort(prepared.world.session('member_001', world.PROJECT), 'member_001')
    with patch.object(actor, 'run_public_entry', execute):
        rejected = port.call('run_tests', request_key='invalid', selection={
            'kind': 'pytest', 'targets': ['../private.py']})
        assert rejected['ok'] is False
        assert prepared.world.test_budget.snapshot()['used'] == session.test_calls == 0
        selected = {'kind': 'pytest', 'targets': ['tests/test_math.py::test_ok']}
        response = port.call('run_tests', request_key='selected', selection=selected)
        assert response['ok'] is True, response
        response = port.call('run_tests', request_key='full')
        assert response['ok'] is True, response
    assert prepared.world.test_budget.snapshot()['used'] == session.test_calls == len(called) == 2
    assert called[0]['argv'][-2:] == ['--', 'tests/test_math.py::test_ok']
    assert called[1] == entry()
    state = prepared.world.store.load()
    tests = [event for event in state['software_events'] if event['kind'] == 'test']
    assert tests[0]['public_test_selection'] == selected
    assert tests[0]['source_reference'] == tests[1]['source_reference']
    assert not state['projects'][world.PROJECT]['software']['deliveries']
    assert not session.terminal_locked
    final_request = {'instance_id': 'fixture__v110', 'source_reference': tests[0]['source_reference'],
        'tree_sha256': baseline['tree']['tree_sha256'], 'hard_deadline_monotonic': deadline.hard_at,
        'hidden_evaluation': False, 'arbitrary_command': False}
    payload = actor.make_delta(baseline, baseline['files'], baseline['entry_metadata'], request=final_request)
    session.execute('sync_terminal', payload)
    with pytest.raises(actor.ManagedTransferError):
        session.execute('managed_public_test', payload)


def test_contract_only_accepts_the_frozen_public_environment_and_identity():
    config = {'instance_id': 'fixture__v110', 'actor_image_id': 'sha256:'+'a'*64,
        'baseline_head': 'b'*40, 'baseline_tree': 'c'*40, 'public_test_entry': entry(),
        'lifecycle_deadline': time.monotonic()+24000,
        'public_environment': {'public_python': '/public/python',
            'environment': {'PATH': '/public:/usr/bin:/bin'}}}
    contract = selection.contract_for_actor(config)
    assert contract['environment'] == config['public_environment']['environment']
    for bad in ({**contract, 'instance_id': 'other'},
                {**contract, 'environment': {'PATH': '/public:/data0/private'}},
                {**contract, 'entry': {**entry(), 'cwd': '/tmp'}},
                {**contract, 'entry': {**entry(), 'timeout_seconds': 1801}}):
        with pytest.raises(selection.PublicTestSelectionError):
            selection.validate_contract(bad)


def test_public_launcher_refuses_host_execution_before_starting_a_process():
    with patch.object(selection.run_native_public_test.__globals__['subprocess'], 'Popen',
                      side_effect=AssertionError('No host test process is permitted')):
        with pytest.raises(selection.PublicTestSelectionError):
            selection.run_native_public_test({'kind': 'full'})


def test_copied_public_launcher_has_no_private_runtime_dependency(tmp_path):
    tools = Path(__file__).resolve().parents[1]/'tools'
    for source, target in (('public_test_library_v110.py', 'public-test-library.py'),
                           ('run_public_tests_v110.py', 'public-test.py')):
        (tmp_path/target).write_bytes((tools/source).read_bytes())
    # Only a standalone Python CLI runs; its actor guard must refuse before tests.
    value = subprocess.run([sys.executable, '-I', str(tmp_path/'public-test.py'),
                            '--selection', '{"kind":"full"}'], cwd=tmp_path,
                           capture_output=True, text=True, timeout=10, check=False)
    assert value.returncode == 2 and 'only through the native actor terminal' in value.stderr
    assert 'Traceback' not in value.stderr
