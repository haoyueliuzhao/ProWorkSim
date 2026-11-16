"""One labeled, networkless task actor; trusted host SDK has no model shell tool."""
from __future__ import annotations
import importlib.util, io, json, tarfile, time, uuid, os
from pathlib import Path
from .storage import json_bytes,digest
from .software_benchmark_candidates_v054 import checked,reference
from .software_benchmark_episode_v066 import public_environment,archive_bundle,PRIVATE_ROOTS
from .software_benchmark_sdk_bundle_v066 import runtime_environment,python_argv
from .software_benchmark_docker_actor_v066 import DockerStdioChannel,validate_actor_ready
from .software_benchmark_runtime_inputs_v203_2_3_r3 import PUBLIC_FILES,RESULT_REVISION,validate_actor_selection
from .software_benchmark_public_tests_v110 import contract_for_actor
from . import software_role_baseline_contract_v141 as roles
from .repository_sources_v054 import normalize_policy,MANIFEST_VERSION
from .software_benchmark_managed_actor_v110 import make_delta
ROOT=Path(__file__).resolve().parents[2]
BUNDLE=ROOT/'runs/software-benchmark-v203-2-3/sdk-recovery-bundle-r3/runtime.tar.gz'
LABEL='proworksim.v20333.owner'

def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(json_bytes(value))
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def upload(container,files):
    b=io.BytesIO()
    with tarfile.open(fileobj=b,mode='w') as t:
        for name,(data,mode) in files.items():
            info=tarfile.TarInfo(name.lstrip('/'));info.size=len(data);info.mode=mode;info.uid=info.gid=0
            t.addfile(info,io.BytesIO(data))
    if not container.put_archive('/',b.getvalue()):raise RuntimeError('Actor upload failed')

class Actor:
    def __init__(self,row,folder,*,resume_test_calls=0):
        self.row,self.folder=row,Path(folder);self.folder.mkdir(parents=True,exist_ok=False)
        self.container=self.client=self.channel=self.rpc=self.err=None
        self.token=str(uuid.uuid4());self.closed=False;self.resume_test_calls=resume_test_calls
        self.config=json.loads(checked(row['configuration']).read_bytes())
    def start(self):
        import docker
        cfg=self.config;mapping,public=public_environment(cfg);self.public=public
        self.hard_at=time.monotonic()+24000
        self.entry={'version':'v064-repository-public-test-entry-r1','instance_id':self.row['instance_id'],
            'argv':cfg['public_test_entry']['argv'],'cwd':'/testbed','timeout_seconds':1800,'hidden_material_used':False}
        links=[{'path':x['path'],'oid':x['official_commit']} for x in mapping.get('submodules',[])]
        spec=roles.organization('REVIEW2')
        a={'version':'v064-private-docker-managed-worker-r1','private_roots':PRIVATE_ROOTS,
            'stdlib':'/opt/pws-runtime/sysroot/usr/lib/python3.12','vision_enabled':False,
            'public_environment':public,'public_environment_sha256':digest(json_bytes(public)),
            'instance_id':self.row['instance_id'],'actor_image_id':mapping['actor_image_id'],
            'baseline_head':mapping['actor_head'],'baseline_tree':mapping['actor_tree'],'official_task_admitted':True,
            'lifecycle_deadline':self.hard_at,'maximum_lifecycle_seconds':24000,'public_test_entry':self.entry,
            'file_policy':normalize_policy(),'gitlinks':links,'organization_id':'REVIEW2',
            'fixed_members':spec['fixed_members'],'member_count':2,'role_contract_version':roles.VERSION,
            'role_catalog_sha256':roles.catalog_sha256(),'public_test_dependencies':None,'public_test_result_revision':RESULT_REVISION,
            'resume_public_test_calls':self.resume_test_calls}
        contract=contract_for_actor(a);a.update(public_test_contract_sha256=digest(json_bytes(contract)),**{k:digest(p.read_bytes()) for k,p in PUBLIC_FILES.items()})
        self.client=docker.DockerClient(base_url='unix://'+str(Path(cfg['scorer_request_base']['docker_socket']).resolve()),timeout=180)
        name='pws-v20333-'+self.token
        intent={'name':name,'owner':self.token,'image':mapping['actor_image_id'],'configuration':a,
            'network':'none','host_mounts':[],'cpu':4,'memory_GiB':16,'no_GPU':True}
        save(self.folder/'create-intent.json',intent)
        self.container=self.client.containers.create(image=mapping['actor_image_id'],name=name,labels={LABEL:self.token},
            entrypoint=python_argv(['/opt/pws-runtime/managed-worker.py','--config','/pws/control/actor-config.json']),command=[],
            detach=True,stdin_open=True,tty=False,user='0:0',network_mode='none',ipc_mode='private',
            cap_drop=['ALL'],cap_add=[],privileged=False,security_opt=['no-new-privileges:true'],
            mem_limit=16*1024**3,memswap_limit=16*1024**3,nano_cpus=4*10**9,pids_limit=512,
            environment=runtime_environment(),working_dir='/testbed',auto_remove=False,init=False)
        save(self.folder/'created.json',{'id':self.container.id,'owner':self.token})
        self.container.reload()
        if self.container.attrs.get('Mounts'):raise ValueError('Unexpected image-created volume: no existing host mounts permitted')
        stream,_=self.container.get_archive('/testbed')
        archive=self.folder/'baseline.tar'
        with archive.open('xb') as f:
            total=0
            for chunk in stream:
                total+=len(chunk)
                if total>8*1024**3:raise ValueError('Baseline archive exceeds 8 GiB')
                f.write(chunk)
        self.baseline=archive_bundle(archive,gitlinks=links)
        self.baseline['capture_scope']='complete_preisolated_public_worktree'
        self.baseline['transport_capture_scope']='complete_new_owned_stopped_container_before_writer_start'
        snap=self.folder/'initial-tree.json';save(snap,self.baseline)
        public_task=cfg['public_task']
        save(self.folder/'source-manifest.json',{'version':MANIFEST_VERSION,'tasks':[{'task_id':self.row['instance_id'],
            'problem_statement':public_task['problem_statement'],'source_identity':{**{k:public_task[k] for k in ('instance_id','repo','base_commit')},
                'dataset_revision':'78f471bf655a3137b2e8a75af1501690ec009ec3'},
            'file_policy':self.baseline['file_policy'],'initial_tree':{**reference(snap),'path':'initial-tree.json'},
            'tree_sha256':self.baseline['tree']['tree_sha256']}]})
        with BUNDLE.open('rb') as f:
            if not self.container.put_archive('/',f):raise RuntimeError('Runtime archive upload failed')
        worker=(ROOT/'tools/run_managed_worker_docker_v203_2_3.py').read_text().replace('software_benchmark_managed_actor_v203_2_3 as managed','software_benchmark_managed_actor_v203_2_3_r5 as managed')
        # Rebind only the trusted transport counter after the original zero-test
        # preflight. World test budgets and immutable checkpoint records remain N.
        needle='result, execution = session.execute(operation, payload)'
        assert worker.count(needle)==1
        worker=worker.replace(needle,needle+'\n            if operation == "sync_preflight":\n                n=config["resume_public_test_calls"]\n                if type(n) is not int or not 0 <= n <= 512: raise ValueError("Bad saved test counter")\n                session.test_calls=n\n                result["restored_public_test_calls_after_preflight"]=n')
        native=(ROOT/'tools/run_native_worker_docker_v203_2_3.py').read_text().replace('software_benchmark_public_test_evidence_v203_2_3 import','software_benchmark_public_test_evidence_v203_2_3_r5 import').replace('v203.2.3-managed-v175-retained-journal-r1','v203.2.3-managed-v175-canonical-preload-retained-journal-r5')
        files={'/opt/pws-runtime/managed-worker.py':(worker.encode(),0o444),'/opt/pws-runtime/worker.py':(native.encode(),0o444),
            '/pws/control/actor-config.json':(json_bytes(a),0o444),'/pws/control/public-environment.json':(json_bytes(public),0o444),
            '/pws/control/public-test-contract.json':(json_bytes(contract),0o444),'/pws/control/public-test-dependencies.json':(json_bytes(None),0o444)}
        for name in ('software_benchmark_managed_actor_v203_2_3_r5.py','software_benchmark_public_test_evidence_v203_2_3_r5.py','software_public_test_retention_v203_2_3_r5.py'):
            files['/opt/pws-runtime/project/src/proworksim/'+name]=((ROOT/'src/proworksim'/name).read_bytes(),0o444)
        from .software_benchmark_managed_actor_v203_2_3_r5 import PUBLIC_FILE_NAMES
        for k,p in PUBLIC_FILES.items():files['/opt/pws-runtime/'+PUBLIC_FILE_NAMES[k]]=(p.read_bytes(),0o444)
        upload(self.container,files)
        self.err=(self.folder/'actor.stderr').open('xb')
        socket=self.client.api.attach_socket(self.container.id,params={'stdin':1,'stdout':1,'stderr':1,'stream':1})
        self.channel=DockerStdioChannel(socket,self.err);self.container.start()
        ready=json.loads(self.channel.readline(time.monotonic()+240));save(self.folder/'ready.json',ready)
        from .software_benchmark_docker_actor_v066 import validate_original_actor_ready
        validate_original_actor_ready(ready)
        if ready.get('public_environment_sha256')!=a['public_environment_sha256']:raise ValueError('Environment identity')
        isolation=ready['isolation']
        if any(isolation['namespaces'].get(n)==os.stat('/proc/self/ns/'+n).st_ino for n in ('mnt','pid','net','ipc')):raise ValueError('Shared namespace')
        if isolation.get('private_packages')!={p:'removed_before_first_tool' for p in PRIVATE_ROOTS}:raise ValueError('Private source visible')
        aliases={'/opt/pws-runtime/'+n:'removed_before_first_tool' for n in ('worker.py','controller.py','managed-worker.py','project-controller.py')}
        if isolation.get('private_aliases')!=aliases:raise ValueError('Private entrypoint visible')
        validate_actor_selection(ready,a)
        if ready['initial_tree_sha256']!=self.baseline['tree']['tree_sha256']:raise ValueError('Host/actor complete baseline differs')
        m=module('v20333_rpc',ROOT/'tools/run_fixed_organization_controller_v132.py')
        channel=self.channel
        class Writer:
            def write(self,text):channel.write(text.encode())
            def flush(self):pass
        self.rpc=m.ManagedRPC(ready,reader=None,writer=Writer(),directory=self.folder/'rpc',hard_at=self.hard_at)
        self.rpc.receive=lambda:json.loads(channel.readline(self.hard_at))
        proof=m.initial_sync_preflight(self.rpc,self.baseline,instance_id=self.row['instance_id'],hard_at=self.hard_at)
        if proof['restored_public_test_calls_after_preflight']!=self.resume_test_calls:raise ValueError('Resume test counter not bound')
        save(self.folder/'preflight.json',proof)
        return self
    def test(self,*,files,entry_metadata,request):
        return self.rpc.request('managed_public_test',make_delta(self.baseline,files,entry_metadata,request=request))
    def close(self):
        if self.closed:return
        errors=[]
        if self.rpc and not self.rpc.failed and not self.rpc.closed:
            try:save(self.folder/'close-rpc.json',self.rpc.close())
            except Exception as e:errors.append(type(e).__name__+':'+str(e))
        if self.channel:self.channel.close()
        if self.container:
            self.container.reload()
            if self.container.labels.get(LABEL)!=self.token:raise RuntimeError('Refuse cleanup of another object')
            if self.container.status=='running':self.container.stop(timeout=10)
            self.container.remove(force=False,v=True)
        if self.err:self.err.close()
        if self.client:self.client.close()
        self.closed=True;save(self.folder/'cleanup.json',{'owned_actor_removed':True,'transport_errors':errors,'other_objects_touched':False})
