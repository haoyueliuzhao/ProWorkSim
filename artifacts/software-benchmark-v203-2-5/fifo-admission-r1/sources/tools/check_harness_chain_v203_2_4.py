"""Zero-provider real SDK/managed actor control in one owned offline container.

The provider is scripted. Docker archive transport is diagnostic-only; the
production FIFO/chunk dispatcher and benchmark tasks are not qualified here.
"""
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, inspect, io, json, os
from pathlib import Path
import shutil, sys, tarfile, time, threading, struct
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'sha256:1550cadc5d78107065acea41020d508dbcd7952f8c85e03b983679d48903bb9a'
SOCKET = '/data0/zhuxinrui/projects/ProWorkSim/runs/software-panel-v053/docker/docker.sock'
VERSION = 'v203.2.4-sealed-actor-sdk-control-r1'

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

def actor(wire=False):
    assert os.getpid() == 1 and os.getuid() != 0
    from proworksim import software_benchmark_managed_actor_v203_2_3_r5 as impl
    from proworksim import software_public_test_retention_v203_2_3_r5 as retain
    from proworksim import software_role_baseline_contract_v141 as roles
    from proworksim.repository_sources_v054 import snapshot_repository
    from proworksim.storage import digest, json_bytes
    control = Path('/pws/control')
    init = json.loads((control/'init.json').read_text())
    root = Path('/pws/testbed'); root.mkdir()
    for name, text in init['files'].items(): (root/name).write_text(text)
    baseline = snapshot_repository(root)
    entry = dict(init['entry'], argv=[sys.executable, '-m', 'pytest', '-q', 'test_sample.py'])
    spec = roles.organization('REVIEW2')
    cfg = {'instance_id': entry['instance_id'], 'organization_id':'REVIEW2',
        'fixed_members':spec['fixed_members'], 'member_count':spec['member_count'],
        'role_contract_version':roles.VERSION,'role_catalog_sha256':roles.catalog_sha256(),
        'public_test_result_revision':impl.RESULT_REVISION,
        'public_test_contract_sha256':digest(json_bytes(entry)),
        'lifecycle_deadline':init['deadline'], 'public_test_dependencies':None}
    files = {'public_test_library_sha256':'public_test_library_v175.py',
        'public_test_launcher_sha256':'run_public_tests_v175.py',
        'public_test_dependency_helper_sha256':'public_test_dependencies_v130.py',
        'public_test_execution_sha256':'public_test_execution_v175.py',
        'public_test_evidence_sha256':'public_test_evidence_v175.py'}
    cfg.update({k:digest((ROOT/'tools'/v).read_bytes()) for k,v in files.items()})
    session = impl.ManagedOperationSession(config=cfg,baseline=baseline,entry=entry,
        environment={'PATH':'/opt/miniconda3/envs/testbed/bin:/usr/bin:/bin',
                     'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1'},root=root)
    uploads=impl.ManagedUploadReceiver('/pws/control/uploads',hard_at=init['deadline'])
    import ctypes
    assert ctypes.CDLL(None).prctl(4,0,0,0,0)==0
    status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    isolation={'pid':os.getpid(),'capabilities_all_zero':all(int(status[k].strip(),16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')),
               'no_new_privileges':status['NoNewPrivs'].strip()=='1','dumpable':False}
    cached = retain.load_base()
    shutil.rmtree(ROOT)  # Only the uploaded private copy in this owned container.
    assert retain.load_base(None) is cached
    ready={'pid':os.getpid(),'uid':os.getuid(),
        'private_sources_removed':not ROOT.exists(),'cache_shared_after_seal':True,
        'baseline':baseline,'entry':entry,'actor_deployment_revision':impl.DEPLOYMENT_VERSION,
        'version':impl.VERSION,'implementation':'v064-private-docker-managed-worker-r1',
        'managed_operations':['sync_preflight','managed_public_test','sync_terminal'],
        'preflight_revision':impl.PREFLIGHT_VERSION,'managed_upload_protocol':impl.upload_protocol(),
        'isolation':isolation}
    dump(control/'ready.json',ready)
    if wire:
        sequence=0
        for line in sys.stdin.buffer:
            if len(line)>impl.MAX_RPC_BYTES:raise ValueError('Frame too large')
            request=json.loads(line);sequence+=1
            if request.get('id')!=sequence:raise ValueError('Replayed or reordered frame')
            if request.get('op')=='close':
                if uploads.pending:raise ValueError('Cannot close an incomplete upload')
                impl._reap_private_children()
                print(json.dumps({'type':'closed','id':sequence,'model_calls':0,
                    'owned_children_quiescent':True,'managed_public_test_calls':session.test_calls,
                    'terminal_synchronized':session.terminal_locked}),flush=True);return
            try:
                tool=request['tool']
                if session.terminal_locked:raise impl.ManagedTransferError('Actor terminal already locked')
                if tool in {impl.UPLOAD_BEGIN,impl.UPLOAD_CHUNK}:
                    method=uploads.begin if tool==impl.UPLOAD_BEGIN else uploads.chunk
                    response={'type':'observation','id':sequence,'tool':tool,'result':method(request['action'])}
                elif tool==impl.UPLOAD_COMMIT:
                    operation,payload,receipt=uploads.commit(request['action'])
                    fault_file=control/'inject-test-environment-failure.json'
                    if fault_file.exists() and payload['request'].get('call_index')==json.loads(fault_file.read_text())['call_index']:
                        session.public_test_environment_v141['PYTEST_ADDOPTS']='--pws-invalid-environment-option'
                    result,execution=session.execute(operation,payload)
                    response={'type':'observation','id':sequence,'tool':operation,'result':result,'upload_receipt':{**receipt,**execution}}
                else:raise ValueError('Unknown transport operation')
            except Exception as error:
                uploads.abort()
                response={'type':'error','id':sequence,'tool':request.get('tool'),
                    'error_type':type(error).__name__,'error':str(error),
                    'classification':getattr(error,'classification','technical_unknown')}
            finally:session.public_test_environment_v141.pop('PYTEST_ADDOPTS',None)
            print(json.dumps(response),flush=True)
        return
    index = 1
    while time.monotonic() < init['deadline']:
        request_path = control/f'request-{index}.json'
        if not request_path.exists(): time.sleep(.02); continue
        request = json.loads(request_path.read_text())
        try:
            if request['operation'] == 'stop':
                dump(control/f'response-{index}.json', {'ok':True}); return
            injected = request.get('test_environment_failure',False)
            if injected: session.public_test_environment_v141['PYTEST_ADDOPTS']='--pws-invalid-environment-option'
            result, receipt = session.execute(request['operation'],request['payload'])
            response = {'ok':True,'result':result,'receipt':receipt,'test_calls':session.test_calls}
        except Exception as error:
            response = {'ok':False,'error':{'type':type(error).__name__,'message':str(error)}}
        finally:
            session.public_test_environment_v141.pop('PYTEST_ADDOPTS',None)
        dump(control/f'response-{index}.json',response); index += 1

def archive(values):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as tar:
        parents={str(p) for name in values for p in Path(name).parents if str(p)!='.'}
        for name in sorted(parents,key=lambda s:(s.count('/'),s)):
            info=tarfile.TarInfo(name);info.type=tarfile.DIRTYPE;info.uid=info.gid=1000;info.mode=0o755;tar.addfile(info)
        for name,raw in values.items():
            info=tarfile.TarInfo(name); info.size=len(raw);info.uid=info.gid=1000;info.mode=0o644
            tar.addfile(info,io.BytesIO(raw))
    return stream.getvalue()

class ActorBridge:
    def __init__(self,client,folder,init):
        self.client,self.folder,self.index,self.failed,self.closed=client,folder,0,False,False
        self.receipts={}; self.container=None
        name='pws-v20324-'+folder.parent.name+'-'+str(os.getpid())
        self.container=client.containers.create(IMAGE,name=name,
            entrypoint=['/opt/miniconda3/envs/testbed/bin/python'],
            command=['-u','/pws/project/tools/check_harness_chain_v203_2_4.py','--actor','--wire'],
            user='1000:1000',working_dir='/pws',network_mode='none',cap_drop=['ALL'],
            security_opt=['no-new-privileges'],nano_cpus=2_000_000_000,
            mem_limit='4g',memswap_limit='4g',pids_limit=128,stdin_open=True,
            environment={'PYTHONPATH':'/pws/project/src','PYTHONDONTWRITEBYTECODE':'1'},
            labels={'proworksim.batch':'v203.2.4','proworksim.purpose':'zero-api-harness-gate'})
        dump(folder/'created.json',{'id':self.container.id,'image':IMAGE,'name':name,
            'CPU':2,'memory_GiB':4,'network':'none','user':'1000:1000','capabilities':[],
            'host_mounts':[],'volumes':[],'model_calls':0})
        values={'pws/control/init.json':json.dumps(init).encode()}
        for parent in ('src/proworksim','tools'):
            for path in (ROOT/parent).rglob('*.py'):
                values['pws/project/'+str(path.relative_to(ROOT))]=path.read_bytes()
        # The package initializer imports spreadsheet support even in coding-only
        # execution. Reuse the existing pure-Python dependencies; no installation.
        for package in ('openpyxl','et_xmlfile'):
            package_root=ROOT/'runs/software-benchmark-v203-2-3/sdk-recovery-bundle-r3/stage/opt/pws-runtime/site'/package
            for path in package_root.rglob('*.py'):
                values['pws/project/src/'+package+'/'+str(path.relative_to(package_root))]=path.read_bytes()
        # Explicit parent ownership, without host binds or a root exec process.
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as tar:
            for d in ['pws','pws/control','pws/output','pws/project','pws/project/src','pws/project/src/proworksim','pws/project/tools']:
                info=tarfile.TarInfo(d);info.type=tarfile.DIRTYPE;info.uid=info.gid=1000;info.mode=0o755;tar.addfile(info)
        self.container.put_archive('/',stream.getvalue())
        self.container.put_archive('/',archive(values)); self.container.start()
        self.ready=self.read('/pws/control/ready.json',60)
        dump(folder/'ready.json',self.ready)
        self.socket=self.container.attach_socket(params={'stdin':True,'stdout':True,'stderr':True,'stream':True})
        raw_socket=self.socket._sock
        readfd,writefd=os.pipe()
        self.reader=os.fdopen(readfd,'rb',buffering=0)
        def recv_exact(size):
            data=b''
            while len(data)<size:
                part=raw_socket.recv(size-len(data))
                if not part:raise EOFError('Actor stream closed')
                data+=part
            return data
        def pump():
            try:
                while True:
                    header=recv_exact(8);size=struct.unpack('>I',header[4:])[0]
                    data=recv_exact(size)
                    if header[0]==1:
                        view=memoryview(data)
                        while view:view=view[os.write(writefd,view):]
                    else:
                        with (folder/'wire-stderr.log').open('ab') as stream:stream.write(data)
            except (OSError,EOFError):pass
            finally:os.close(writefd)
        self.pump_thread=threading.Thread(target=pump,daemon=True);self.pump_thread.start()
        class Writer:
            def write(self,raw):raw_socket.sendall(raw.encode())
            def flush(self):pass
        spec=importlib.util.spec_from_file_location('production_rpc',ROOT/'tools/run_fixed_organization_controller_v132.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.rpc=module.ManagedRPC(self.ready,reader=self.reader,writer=Writer(),directory=folder/'production-rpc',hard_at=init['deadline'])

    def read(self,path,timeout=30):
        import docker
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            try:
                chunks,_=self.container.get_archive(path)
                with tarfile.open(fileobj=io.BytesIO(b''.join(chunks))) as tar:
                    raw=tar.extractfile(tar.getmembers()[0]).read()
                return json.loads(raw)
            except docker.errors.NotFound: pass
            except json.JSONDecodeError: pass
            self.container.reload()
            if self.container.status=='exited':
                raise RuntimeError(self.container.logs().decode(errors='replace')[-5000:])
            time.sleep(.1)
        raise TimeoutError(path)

    def request(self,operation,payload,*,key=None,inject=False):
        if self.failed or self.closed: raise RuntimeError('No replay of failed actor transfer')
        fingerprint=hashlib.sha256(json.dumps([operation,payload,inject],sort_keys=True).encode()).hexdigest()
        if key in self.receipts:
            old,reply=self.receipts[key]
            if old!=fingerprint: raise ValueError('Same request key changed its payload')
            return copy.deepcopy(reply)
        self.index+=1
        request={'operation':operation,'payload':payload,'test_environment_failure':inject}
        dump(self.folder/f'{self.index:04d}-request.json',request)
        try:
            if operation=='stop':
                reply={'ok':True,'result':self.rpc.exchange({'op':'close'},'closed')}
            else:
                if inject:
                    self.container.put_archive('/pws/control',archive({'inject-test-environment-failure.json':json.dumps({'call_index':payload['request']['call_index']}).encode()}))
                reply={'ok':True,'result':self.rpc.request(operation,payload)}
            dump(self.folder/f'{self.index:04d}-response.json',reply)
            if not reply['ok']: raise RuntimeError(str(reply['error']))
            if key is not None:self.receipts[key]=(fingerprint,copy.deepcopy(reply))
            return reply
        except Exception:
            self.failed=True;raise

    def cleanup(self):
        if not self.container:return
        cid=self.container.id
        try:
            self.container.reload()
            if self.container.status=='running':
                if not self.failed:self.request('stop',{})
                self.container.wait(timeout=20)
        except Exception:self.container.stop(timeout=5)
        try:
            chunks,_=self.container.get_archive('/pws/output')
            with (self.folder/'actor-output.tar').open('wb') as stream:
                for chunk in chunks:stream.write(chunk)
        except Exception as error:dump(self.folder/'archive-error.json',{'error':str(error)})
        logs=self.container.logs();(self.folder/'actor.log').write_bytes(logs)
        self.container.remove();self.closed=True
        if hasattr(self,'socket'):self.socket.close()
        if hasattr(self,'reader'):self.reader.close()
        dump(self.folder/'cleanup.json',{'container_id':cid,'removed':True,'shared_host_changes':0})

def run(output):
    import docker
    from proworksim import software_role_baseline_runtime_v203_2_1 as runtime_base
    from proworksim.software_benchmark_managed_actor_v106 import make_delta, baseline_source_reference
    from proworksim.repository_sources_v054 import tree_manifest
    output.mkdir(parents=True,exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(output/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1')
    spec=importlib.util.spec_from_file_location('fixture_v20324',ROOT/'tools/check_role_baseline_sdk_v141.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    fixture_namespace=dict(fixture.__dict__)
    fixture_source=inspect.getsource(fixture.fixture).replace("str(ROOT/'.venv/bin/python')", "'/opt/miniconda3/envs/testbed/bin/python'")
    exec(compile(fixture_source,__file__+':container-interpreter-fixture','exec'),fixture_namespace)
    holder={}; client=docker.DockerClient(base_url='unix://'+SOCKET,timeout=120)
    bridge=None
    def make_case(folder,group):
        nonlocal bridge
        prepared,deadline,calls=fixture_namespace['fixture'](folder,group)
        holder.update(prepared=prepared,deadline=deadline,calls=calls,results=[])
        entry=prepared.source_provider.runner.entry if hasattr(prepared.source_provider.runner,'entry') else {
            'version':'v064-repository-public-test-entry-r1','instance_id':'fixture__sdk-141',
            'argv':[],'cwd':'/testbed','timeout_seconds':20,'hidden_material_used':False}
        init={'files':{'sample.py':'value = 1\n','test_sample.py':'def test_value():\n    from sample import value\n    assert value == 2\n'},
              'entry':entry,'deadline':time.monotonic()+900}
        # World and actor share the actual world deadline; process has a bounded lifecycle.
        deadline.hard_at=min(deadline.hard_at,init['deadline'])
        deadline.soft_at=deadline.hard_at-120
        deadline.hard_seconds=deadline.hard_at-deadline.started
        deadline.soft_seconds=deadline.soft_at-deadline.started
        prepared.source_provider.runner.hard_at=deadline.hard_at
        bridge=object.__new__(ActorBridge)
        bridge.__init__(client,output/'actor',init)
        baseline=bridge.ready['baseline'];holder['baseline']=baseline
        request={'instance_id':'fixture__sdk-141','source_reference':baseline_source_reference(baseline),
            'tree_sha256':baseline['tree']['tree_sha256'],'hard_deadline_monotonic':deadline.hard_at,
            'hidden_evaluation':False,'arbitrary_command':False,'model_calls_before_preflight':0}
        bridge.request('sync_preflight',make_delta(baseline,baseline['files'],baseline['entry_metadata'],request=request))
        def public_test(*,files,entry_metadata,request):
            calls.append(copy.deepcopy(request))
            payload=make_delta(baseline,files,entry_metadata,request=request)
            key='test-'+str(request['call_index'])
            value=bridge.request('managed_public_test',payload,key=key)
            before=bridge.index
            assert bridge.request('managed_public_test',payload,key=key)==value and bridge.index==before
            holder['results'].append(value)
            return value['result']
        prepared.source_provider.runner.callback=public_test
        return prepared,deadline,calls
    def build_runtime(*args,**kwargs):
        result=runtime_base.build_runtime(*args,**kwargs);holder['runtime']=result[0];return result
    ns={**fixture.__dict__,'fixture':make_case,'_runtime':SimpleNamespace(**{**runtime_base.__dict__,'build_runtime':build_runtime})}
    source=inspect.getsource(fixture.run)
    source=source.replace('from proworksim import software_role_baseline_runtime_v141 as runtime_module','runtime_module = _runtime')
    source=source.replace("('read_file', {'path': 'sample.py', 'cursor': None})]", "('read_file', {'path': 'sample.py', 'cursor': None}), ('run_tests', {})]")
    source=source.replace("summary['usage']['actual_total_tokens']", "summary['usage']['known_actual_tokens']['total_tokens']")
    exec(compile(source,__file__+':scripted-real-sdk','exec'),ns)
    try:
        result=ns['run'](output/'sdk','REVIEW2')
        values=holder['results']
        assert any(not v['result']['passed'] and v['result']['counts']['failed']>0 for v in values)
        assert sum(v['result']['passed'] for v in values)>=3
        prepared=holder['prepared'];artifact,version,bundle=prepared.world._bundle('member_001')
        tree=tree_manifest(bundle['files'],bundle['entry_metadata'])
        request={'instance_id':'fixture__sdk-141','source_reference':{'object_id':artifact['artifact_id'],'version_id':version},
            'tree_sha256':tree['tree_sha256'],'hard_deadline_monotonic':holder['deadline'].hard_at,
            'hidden_evaluation':False,'arbitrary_command':False}
        payload=make_delta(holder['baseline'],bundle['files'],bundle['entry_metadata'],request=request)
        # Correct fixture code, deliberately broken test-runner configuration.
        fault_request={**holder['calls'][-1],**request,'actor_id':'member_001','call_index':len(holder['calls'])+1}
        fault=bridge.request('managed_public_test',make_delta(holder['baseline'],bundle['files'],bundle['entry_metadata'],request=fault_request),inject=True)
        # A startup failure has no trustworthy collected-test count; None must
        # remain unknown instead of being manufactured into zero passed tests.
        assert not fault['result']['passed'] and fault['result']['counts']['tests_run'] in (None,0)
        assert fault['result']['validation_status']!='verified'
        assert fault['result']['execution']['returncode']!=0
        synchronized=bridge.request('sync_terminal',payload)
        lock=json.loads(Path(result['lock']['path']).read_text())
        assert lock['same_tree'] and lock['submitted'] and synchronized['result']['tree_sha256']==tree['tree_sha256']
        dump(output/'controls.json',{'F1':bridge.ready['cache_shared_after_seal'],
            'F2':bridge.ready['private_sources_removed'],'F3':True,'F4':len(values),
            'F5':{'wrong_code_valid_tests':True,'correct_code_broken_test_environment':True},
            'F7':{'same_final_delivery_and_sync_tree':True,'tree_sha256':tree['tree_sha256'],'lock':result['lock']},
            'F8':{'same_request_returns_retained_result_without_world_replay':True},
            'test_results':[{'passed':v['result']['passed'],'counts':v['result']['counts'],'execution':v['result']['execution']} for v in values],
            'environment_failure':fault,'scripted_sdk_result':result})
        # Exercise permanent failure through a real actor refusal, then guard next opportunity.
        rejected=False
        try:bridge.request('sync_terminal',payload)
        except (RuntimeError, ValueError):rejected=bridge.failed and bridge.rpc.failed
        controller_spec=importlib.util.spec_from_file_location('guard_r5',ROOT/'tools/run_role_context_controller_v203_2_3_r5.py')
        guard=importlib.util.module_from_spec(controller_spec);controller_spec.loader.exec_module(guard)
        prevented=False
        try:guard.guard_actor_transfer(bridge)
        except RuntimeError:prevented=True
        assert rejected and prevented
        dump(output/'permanent-failure.json',{'F6':True,'actor_refused_after_terminal_lock':rejected,
            'guard_prevents_next_opportunity':prevented,'new_provider_calls':0})
        report={'version':VERSION,'passed':True,'API_calls':0,'cash_CNY':0,
            'actual_SDK':True,'actual_actor_execute':True,'actor_private_PID1':True,
            'scripted_provider_not_model_efficacy':True,'production_FIFO_dispatcher_tested':False,
            'production_ManagedRPC_and_chunk_receiver_tested':True,
            'full_production_deployment_gate':False,'benchmark_environments_qualified':False}
    finally:
        if bridge:bridge.cleanup()
        client.close()
    dump(output/'summary.json',report)
    print(json.dumps(report),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--actor',action='store_true');p.add_argument('--wire',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.actor:actor(args.wire)
    else:run(args.output.resolve())
