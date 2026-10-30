"""Finite private-directory controls; no Docker, privilege, GPU or network."""
import copy
import importlib.util
from pathlib import Path

import pytest

from proworksim import software_benchmark_managed_actor_v103 as actor
from proworksim import software_benchmark_managed_v064 as managed
from proworksim import software_benchmark_world_v064 as world
from proworksim.harness_port import HarnessPort
from proworksim.repository_sources_v054 import capture_repository, snapshot_repository
from proworksim.software_organization_runtime_v047 import DispatchDeadline

ROOT = Path(__file__).resolve().parents[1]


def controller_module():
    spec = importlib.util.spec_from_file_location('controller_v103', ROOT / 'tools/run_project_controller_v103.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def fixture(tmp_path, monkeypatch):
    source = tmp_path / 'checkout'
    source.mkdir()
    (source / 'sample.py').write_text('old\n')
    baseline = snapshot_repository(source)
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    config = {'instance_id': 'fixture__103', 'lifecycle_deadline': deadline.hard_at}
    session = actor.ManagedOperationSession(config=config, baseline=baseline,
        entry={}, environment={}, root=source)
    executions = []

    def public(entry, *, request, candidate_tree_sha256, **kwargs):
        executions.append(copy.deepcopy(request))
        return {'passed': False, 'execution': {'executed': True,
            'input_tree_sha256': candidate_tree_sha256, 'source_reference': request['source_reference']},
            'groups': {'public_repository_tests': {'status': 'failed', 'executed': True,
                'passed': False, 'tests': []}}}

    monkeypatch.setattr(actor, 'run_public_entry', public)
    receiver = actor.ManagedUploadReceiver(tmp_path / 'uploads', hard_at=deadline.hard_at)

    class LocalRPC(controller_module().ManagedRPC):
        def __init__(self):
            self.failed = self.closed = False
            self.hard_at, self.directory = deadline.hard_at, tmp_path / 'rpc'
            self.directory.mkdir()

        def exchange(self, value, expected):
            tool, action = value['tool'], value['action']
            if tool in {actor.UPLOAD_BEGIN, actor.UPLOAD_CHUNK}:
                fn = receiver.begin if tool == actor.UPLOAD_BEGIN else receiver.chunk
                return {'type': expected, 'tool': tool, 'result': fn(action)}
            operation, payload, receipt = receiver.commit(action)
            result, execution = session.execute(operation, payload)
            return {'type': expected, 'tool': operation, 'result': result,
                    'upload_receipt': {**receipt, **execution}}

    rpc = LocalRPC()
    manifest = capture_repository(source, tmp_path / 'snapshot', task_id=config['instance_id'],
        problem_statement='Change old to new.', source_identity={'instance_id': config['instance_id'],
            'repo': 'fixture/test', 'base_commit': 'a' * 40, 'dataset_revision': 'b' * 40})

    def public_callback(**payload):
        return rpc.request('managed_public_test', actor.make_delta(baseline,
            payload['files'], payload['entry_metadata'], request=payload['request']))

    prepared = managed.prepare_case(manifest, tmp_path / 'world', max_total_tokens=5_000_000,
                                   public_test_callback=public_callback, deadline=deadline)
    port = HarnessPort(world.SoftwareCollaborationPort(prepared.world.session('member_001', world.PROJECT),
        'member_001'), 'member_001', project_id=world.PROJECT, public_sink=lambda *_: None,
        world_sink=lambda *_: None, harness_sink=lambda *_: None)
    sequence = 0

    def call(tool, **arguments):
        nonlocal sequence
        sequence += 1
        return port.call(tool, request_key=f'fixture-{sequence}', association={}, **arguments)

    return source, baseline, session, executions, rpc, prepared, call


def test_permission_refusal_keeps_rpc_live_and_cannot_authorize_delivery(tmp_path, monkeypatch):
    source, baseline, session, executions, rpc, prepared, call = fixture(tmp_path, monkeypatch)
    original = actor.synchronize_tree
    attempts = []

    def once(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise PermissionError(1, 'scripted private parent denial')
        return original(*args, **kwargs)

    monkeypatch.setattr(actor, 'synchronize_tree', once)
    assert call('write_file', path='sample.py', text='new\n')['ok']
    refused = call('run_tests')
    assert refused['ok'] and refused['result']['executed'] is False
    assert not executions and not rpc.failed and session.test_calls == 1
    assert call('fix_patch', task_ids=[], message='same version')['ok']
    denied = call('submit_integration', message='must not bypass the test gate')
    assert not denied['ok'] and 'Run real tests' in denied['error']['message']
    later = call('run_tests')
    assert later['ok'] and later['result']['executed'] is True
    assert len(executions) == 1 and session.test_calls == 2 and not rpc.failed
    assert call('submit_integration', message='now actually executed')['ok']
    assert source.joinpath('sample.py').read_text() == 'new\n'


def test_session_uses_repaired_sync_without_chmod_on_unchanged_files(tmp_path, monkeypatch):
    import os

    source, _, session, executions, _, _, call = fixture(tmp_path, monkeypatch)
    inode = (source / 'sample.py').stat().st_ino
    monkeypatch.setattr(os, 'chmod', lambda *_a, **_kw: (_ for _ in ()).throw(PermissionError('foreign inode')))
    monkeypatch.setattr(os, 'chown', lambda *_a, **_kw: pytest.fail('No ownership change'))
    result = call('run_tests')
    assert result['ok'] and result['result']['executed'] is True
    assert len(executions) == session.test_calls == 1 and (source / 'sample.py').stat().st_ino == inode
    assert call('write_file', path='sample.py', text='changed\n')['ok']
    assert call('run_tests')['result']['executed'] is True
    assert (source / 'sample.py').stat().st_ino != inode


@pytest.mark.parametrize('kind', ['invalid_tree', 'integrity_error', 'terminal_permission'])
def test_integrity_or_terminal_failures_remain_fatal(tmp_path, monkeypatch, kind):
    _, baseline, session, executions, rpc, _, _ = fixture(tmp_path, monkeypatch)
    request = {'instance_id': 'fixture__103', 'source_reference': {'object_id': 'source', 'version_id': 'v1'},
               'tree_sha256': baseline['tree']['tree_sha256'], 'call_index': 1,
               'hard_deadline_monotonic': session.config['lifecycle_deadline'],
               'hidden_evaluation': False, 'arbitrary_command': False}
    action = actor.make_delta(baseline, baseline['files'], baseline['entry_metadata'], request=request)
    operation = 'managed_public_test'
    if kind == 'invalid_tree':
        action['candidate_tree_sha256'] = '0' * 64
    elif kind == 'integrity_error':
        monkeypatch.setattr(actor, 'synchronize_tree', lambda *_a, **_kw: (_ for _ in ()).throw(ValueError('tree differs')))
    else:
        operation = 'sync_terminal'
        monkeypatch.setattr(actor, 'synchronize_tree', lambda *_a, **_kw: (_ for _ in ()).throw(PermissionError('cannot export')))
    with pytest.raises(actor.ManagedTransferError):
        rpc.request(operation, action)
    assert rpc.failed and not executions and not session.terminal_locked


def test_forged_refusal_cannot_turn_an_execution_into_nonfatal_failure():
    action = {'candidate_tree_sha256': 'f' * 64,
              'request': {'source_reference': {'object_id': 's', 'version_id': 'v1'}}}
    result = actor.permission_refusal(PermissionError('fixture'), action['request'],
                                      {'tree_sha256': action['candidate_tree_sha256']})
    response = {'result': result, 'upload_receipt': {'operation_executed': False,
                                                    'operation_rejected_before_test': True}}
    assert actor.valid_permission_refusal('managed_public_test', action, response)
    result['execution']['executed'] = True
    assert not actor.valid_permission_refusal('managed_public_test', action, response)


def test_future_bundle_selects_new_entrypoints_and_preserves_old_ref():
    from proworksim import software_benchmark_sdk_bundle_v066 as old
    from proworksim import software_benchmark_sdk_bundle_v103 as new

    globals_ = new.prepare_bundle.__globals__
    assert globals_['ENTRYPOINT_ALIASES']['managed-worker.py'] == 'run_managed_worker_docker_v103.py'
    assert globals_['ENTRYPOINT_ALIASES']['project-controller.py'] == 'run_project_controller_v103.py'
    assert globals_['ENTRYPOINT_ALIASES']['controller.py'] == old.ENTRYPOINT_ALIASES['controller.py']
    assert set(new.NEW_MODULES).issubset(globals_['PROJECT_MODULES'])
    compile(new.probe_source(), '<future bundle probe>', 'exec')
    assert 'software_benchmark_managed_v103 import worker_type' in new.probe_source()
    assert old.OUTPUT != new.OUTPUT
