"""Private temp-file RPC controls; no network, shell, container or model work."""
import copy
import importlib.util
from pathlib import Path
import time

import pytest

from proworksim import software_benchmark_managed_actor_v106 as actor
from proworksim.repository_sources_v054 import snapshot_repository

ROOT = Path(__file__).resolve().parents[1]
TASK = 'matplotlib__matplotlib-23476'


def fixture(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('controller_v106', ROOT/'tools/run_project_controller_v106.py')
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    checkout = tmp_path/'checkout'
    checkout.mkdir()
    (checkout/'sample.py').write_text('unchanged\n')
    baseline = snapshot_repository(checkout)
    hard_at = time.monotonic() + 60
    session = actor.ManagedOperationSession(config={'instance_id': TASK, 'lifecycle_deadline': hard_at},
        baseline=baseline, entry={}, environment={}, root=checkout)
    public_calls = []
    def public(*_args, request, candidate_tree_sha256, **_kwargs):
        public_calls.append(copy.deepcopy(request))
        return {'passed': False, 'execution': {'executed': True, 'input_tree_sha256': candidate_tree_sha256}}
    monkeypatch.setattr(actor, 'run_public_entry', public)
    receiver = actor.ManagedUploadReceiver(tmp_path/'uploads', hard_at=hard_at)
    class LocalRPC(controller.ManagedRPC):
        def __init__(self):
            self.failed = self.closed = False
            self.hard_at, self.directory = hard_at, tmp_path/'rpc'
            self.directory.mkdir()
        def exchange(self, value, expected):
            tool, action = value['tool'], value['action']
            if tool in {actor.UPLOAD_BEGIN, actor.UPLOAD_CHUNK}:
                method = receiver.begin if tool == actor.UPLOAD_BEGIN else receiver.chunk
                return {'type': expected, 'tool': tool, 'result': method(action)}
            operation, payload, receipt = receiver.commit(action)
            result, execution = session.execute(operation, payload)
            return {'type': expected, 'tool': operation, 'result': result,
                    'upload_receipt': {**receipt, **execution}}
    return controller, LocalRPC(), checkout, baseline, session, public_calls


def action(session, baseline, *, preflight=False, changed=False):
    files = {**baseline['files']}
    if changed:
        files['sample.py'] = 'changed\n'
    from proworksim.repository_sources_v054 import tree_manifest
    request = {'instance_id': TASK, 'source_reference': actor.baseline_source_reference(baseline),
               'tree_sha256': tree_manifest(files, baseline['entry_metadata'])['tree_sha256'],
               'hard_deadline_monotonic': session.config['lifecycle_deadline'],
               'hidden_evaluation': False, 'arbitrary_command': False}
    request.update({'model_calls_before_preflight': 0} if preflight else {'call_index': 1})
    return actor.make_delta(baseline, files, baseline['entry_metadata'], request=request)


def test_actual_internal_upload_preflight_retains_test_and_final_sync(tmp_path, monkeypatch):
    controller, rpc, checkout, baseline, session, calls = fixture(tmp_path, monkeypatch)
    inode = (checkout/'sample.py').stat().st_ino
    proof = controller.initial_sync_preflight(rpc, baseline, instance_id=TASK, hard_at=rpc.hard_at)
    assert proof['passed'] and proof['exact_complete_tree']
    assert not proof['terminal_locked'] and not proof['delivery_test_evidence']
    assert proof['model_calls_before_preflight'] == proof['public_test_calls'] == 0
    assert session.test_calls == 0 and not session.terminal_locked and calls == []
    assert (checkout/'sample.py').stat().st_ino == inode
    public = rpc.request('managed_public_test', action(session, baseline, changed=True))
    assert public['execution']['executed'] is True and len(calls) == session.test_calls == 1
    final = rpc.request('sync_terminal', action(session, baseline, changed=True))
    assert final['terminal_locked'] is True and session.terminal_locked
    assert (checkout/'sample.py').read_text() == 'changed\n'
    with pytest.raises(actor.ManagedTransferError):
        rpc.request('managed_public_test', action(session, baseline))


@pytest.mark.parametrize('kind', ['different_candidate', 'wrong_version', 'model_started', 'repeat'])
def test_preflight_refuses_modified_version_late_and_repeated_attempts(tmp_path, monkeypatch, kind):
    controller, rpc, checkout, baseline, session, calls = fixture(tmp_path, monkeypatch)
    payload = action(session, baseline, preflight=True, changed=kind == 'different_candidate')
    if kind == 'wrong_version':
        payload['request']['source_reference']['version_id'] = 'wrong-version'
    elif kind == 'model_started':
        payload['request']['model_calls_before_preflight'] = 1
    elif kind == 'repeat':
        controller.initial_sync_preflight(rpc, baseline, instance_id=TASK, hard_at=rpc.hard_at)
    with pytest.raises(actor.ManagedTransferError):
        rpc.request('sync_preflight', payload)
    assert calls == [] and session.test_calls == 0 and not session.terminal_locked
    assert (checkout/'sample.py').read_text() == 'unchanged\n'
    assert rpc.failed and session.preflight_attempted


@pytest.mark.parametrize('operation', ['managed_public_test', 'sync_terminal'])
def test_regular_operations_cannot_bypass_initial_preflight(tmp_path, monkeypatch, operation):
    _, rpc, _, baseline, session, calls = fixture(tmp_path, monkeypatch)
    with pytest.raises(actor.ManagedTransferError, match='before model work'):
        rpc.request(operation, action(session, baseline))
    assert not calls and not session.terminal_locked and not session.preflight_passed
