"""CPU serve/alias/config/ready/preflight route, with only isolation represented.

No container, root operation, mount, namespace or public task is executed. The
private PID1 seal is represented; source, contract, native config, dependency,
managed-session and upload/preflight validation are the actual implementations.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_managed_actor_v143 as actor
from proworksim.repository_sources_v054 import snapshot_repository
from proworksim.storage import json_bytes

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class ContractFile:
    def __init__(self, path, owner=0):
        self.path, self.owner = path, owner

    def lstat(self):
        value = self.path.lstat()
        return SimpleNamespace(st_mode=value.st_mode, st_uid=self.owner)

    def read_bytes(self):
        return self.path.read_bytes()


def prepare(tmp_path, monkeypatch, group='S1', *, old_alias=False):
    fixture = module('v143_frozen_inputs_fixture', ROOT/'tests/test_public_runtime_bindings_v141.py')
    row, public, entry, base, binding, _, _ = fixture.prepared(tmp_path, group)
    config = dict(base)
    runtime, control, checkout = (tmp_path/'runtime', tmp_path/'control', tmp_path/'checkout')
    (runtime/'project/tools').mkdir(parents=True)
    control.mkdir()
    checkout.mkdir()
    for key, name in actor.PUBLIC_FILE_NAMES.items():
        shutil.copyfile(fixture.inputs.PUBLIC_FILES[key], runtime/name)
        (runtime/name).chmod(0o444)
    for source, target in (
            ('run_managed_worker_docker_v143.py', 'managed-worker.py'),
            ('run_native_worker_docker_v130.py' if old_alias else 'run_native_worker_docker_v143.py', 'worker.py'),
            ('run_native_worker_docker_v066.py', 'project/tools/run_native_worker_docker_v066.py')):
        shutil.copyfile(ROOT/'tools'/source, runtime/target)
    (checkout/'sample.py').write_text('value = 1\n')
    subprocess.run(['/usr/bin/git','init','-q',str(checkout)], check=True, capture_output=True)
    subprocess.run(['/usr/bin/git','-C',str(checkout),'add','sample.py'], check=True, capture_output=True)
    subprocess.run(['/usr/bin/git','-C',str(checkout),'-c','user.name=CPU fixture',
                    '-c','user.email=fixture@example.invalid','commit','-qm','fixture'], check=True, capture_output=True)
    identity = subprocess.run(['/usr/bin/git','-C',str(checkout),'rev-parse','HEAD','HEAD^{tree}'],
                              check=True,capture_output=True,text=True).stdout.splitlines()
    config.update(version='v064-private-docker-managed-worker-r1', private_roots=[
        '/opt/pws-runtime/'+name for name in ('site','overlay','upstream-tools','project')],
        stdlib='/opt/pws-runtime/sysroot/usr/lib/python3.12', vision_enabled=False,
        official_task_admitted=True, baseline_head=identity[0], baseline_tree=identity[1],
        public_environment_sha256=hashlib.sha256(json_bytes(public)).hexdigest())
    # Rebuild only the fixture's admitted bytes after choosing its real Git baseline.
    binding = fixture.inputs.actor_inputs(config,public_test_entry=entry,row=row)
    config = binding['config']
    for name, raw in binding['files'].items():
        (control/name).write_bytes(raw)
        (control/name).chmod(0o444)
    (control/'public-environment.json').write_bytes(json_bytes(public))
    worker = module('v143_full_serve_control', runtime/'managed-worker.py')
    monkeypatch.setattr(worker,'__file__','/opt/pws-runtime/managed-worker.py')
    def mapped_path(value):
        path = Path(value)
        for original, replacement in (('/opt/pws-runtime',runtime),('/pws/control',control),('/testbed',checkout)):
            if path.is_relative_to(original):
                return replacement/path.relative_to(original)
        return path
    monkeypatch.setattr(worker,'Path',mapped_path)
    native = worker.native_isolation_module()
    monkeypatch.setattr(native,'Path',mapped_path)
    owned_contract = ContractFile(control/'public-test-contract.json')
    monkeypatch.setitem(native.public_tests.read_actor_contract.__globals__,'CONTRACT_PATH',owned_contract)
    timer = []
    monkeypatch.setattr(native._legacy.signal,'signal',lambda *args: timer.append(('signal',len(args))))
    monkeypatch.setattr(native._legacy.signal,'setitimer',lambda *args: timer.append(('timer',args[1])))
    seals = []
    def isolated_boundary(actual_public):
        assert actual_public == public
        seals.append(actual_public)
        return {'pid':1,'uid':os.getuid(),'capabilities_all_zero':True,
                'no_new_privileges':True,'dumpable':False,'CPU_fixture_only':True}
    monkeypatch.setattr(native,'_original_seal',isolated_boundary)
    monkeypatch.setattr(worker,'native_isolation_module',lambda: native)
    run = subprocess.run
    def public_git(argv, **kwargs):
        assert argv[0] in {'/usr/bin/git','/bin/git'}
        return run([str(checkout) if value=='/testbed' else value for value in argv],**kwargs)
    monkeypatch.setattr(worker.subprocess,'run',public_git)
    snap = worker.snapshot_repository
    monkeypatch.setattr(worker,'snapshot_repository',lambda path,**kwargs: snap(mapped_path(path),**kwargs))
    receiver, session, verify = actor.ManagedUploadReceiver, actor.ManagedOperationSession, actor.verify_public_runtime_files
    monkeypatch.setattr(worker.managed,'ManagedUploadReceiver',lambda _root,**kwargs: receiver(tmp_path/'uploads',**kwargs))
    monkeypatch.setattr(worker.managed,'ManagedOperationSession',lambda **kwargs: session(root=checkout,**kwargs))
    monkeypatch.setattr(worker.managed,'verify_public_runtime_files',lambda value: verify(value,runtime,control/'public-test-contract.json'))
    emitted = []
    monkeypatch.setattr(worker,'emit',emitted.append)
    return SimpleNamespace(worker=worker,native=native,config=config,runtime=runtime,control=control,
                           checkout=checkout,seals=seals,timer=timer,emitted=emitted,contract=owned_contract)


def preflight_input(fixture, tmp_path):
    baseline = snapshot_repository(fixture.checkout)
    request = {'instance_id':fixture.config['instance_id'],
        'source_reference':actor.baseline_source_reference(baseline),
        'tree_sha256':baseline['tree']['tree_sha256'],
        'hard_deadline_monotonic':fixture.config['lifecycle_deadline'],
        'hidden_evaluation':False,'arbitrary_command':False,'model_calls_before_preflight':0}
    payload = actor.make_delta(baseline,baseline['files'],baseline['entry_metadata'],request=request)
    rows = []
    with actor.prepare_payload_upload(payload,'sync_preflight',directory=tmp_path/'spool',
            hard_at=fixture.config['lifecycle_deadline']) as (manifest,stream):
        rows.append({'tool':actor.UPLOAD_BEGIN,'action':manifest})
        rows += [{'tool':actor.UPLOAD_CHUNK,'action':value} for value in actor.upload_chunks(manifest,stream)]
        rows.append({'tool':actor.UPLOAD_COMMIT,'action':{key:manifest[key]
            for key in ('version','upload_id','payload_bytes','payload_sha256')}})
    return b''.join((json.dumps({'id':index+1,**row},separators=(',',':'))+'\n').encode()
                    for index,row in enumerate(rows))


@pytest.mark.parametrize('group',['S1','FREE2','REVIEW2'])
def test_actual_serve_alias_native_validation_ready_and_preflight(tmp_path,monkeypatch,group):
    fixture = prepare(tmp_path,monkeypatch,group)
    monkeypatch.setattr(fixture.worker.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(preflight_input(fixture,tmp_path))))
    fixture.worker.serve(fixture.config)
    ready = fixture.emitted[0]
    assert ready['type']=='ready' and ready['public_test_result_revision']==actor.RESULT_REVISION
    assert ready['actor_deployment_revision']==actor.DEPLOYMENT_VERSION
    assert ready['organization_id']==group and ready['fixed_members']==fixture.config['fixed_members']
    assert ready['public_test_files_sha256']=={key:fixture.config[key] for key in actor.PUBLIC_FILE_NAMES}
    assert ready['preflight_revision']=='v106-initial-baseline-sync-preflight-r1'
    assert fixture.emitted[-1]['result']['passed'] is True
    assert fixture.emitted[-1]['result']['model_calls_before_preflight']==0
    assert len(fixture.seals)==1 and fixture.timer[0][0]=='signal' and fixture.timer[1][0]=='timer'


@pytest.mark.parametrize('change',['revision','layout','file_hash','contract_owner','dependency_record'])
def test_real_serve_preserves_each_preseal_refusal(tmp_path,monkeypatch,change):
    fixture = prepare(tmp_path,monkeypatch)
    if change=='revision':
        fixture.config['public_test_result_revision']='v130-public-test-evidence-r1'
    elif change=='layout':
        fixture.config['private_roots']=[]
    elif change=='file_hash':
        fixture.config['public_test_execution_sha256']='0'*64
    elif change=='contract_owner':
        fixture.contract.owner=12345
    else:
        (fixture.control/'public-test-dependencies.json').chmod(0o644)
        (fixture.control/'public-test-dependencies.json').write_text('{}')
    with pytest.raises(ValueError):
        fixture.worker.serve(fixture.config)
    assert not fixture.emitted and not fixture.seals


def test_wrong_packaged_alias_fails_before_serve_validation(tmp_path,monkeypatch):
    with pytest.raises(ValueError,match='packaged native isolation alias'):
        prepare(tmp_path,monkeypatch,old_alias=True)


def test_original_private_pid_gate_is_not_removed():
    native = module('v143_real_private_seal_gate',ROOT/'tools/run_native_worker_docker_v143.py')
    assert native._original_seal is native._legacy.seal_actor
    assert native._original_validate is native._legacy.validate_config
    with pytest.raises(RuntimeError,match='PID 1'):
        native._original_seal({})


def test_file_hash_is_rechecked_after_private_seal(tmp_path,monkeypatch):
    fixture = prepare(tmp_path,monkeypatch)
    original = fixture.native._original_seal
    def altered(public):
        result = original(public)
        target = fixture.runtime/'public-test-evidence.py'
        target.chmod(0o644)
        target.write_text('# changed during seal')
        return result
    monkeypatch.setattr(fixture.native,'_original_seal',altered)
    with pytest.raises(ValueError,match='source changed during'):
        fixture.worker.serve(fixture.config)
    assert not fixture.emitted and len(fixture.seals)==1
