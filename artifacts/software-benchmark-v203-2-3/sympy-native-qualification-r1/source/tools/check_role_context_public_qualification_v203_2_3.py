"""Four bounded task-interpreter controls, retained raw journals, zero API calls."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import time
from proworksim import software_benchmark_scope_v203_2_3 as scope
from proworksim import software_benchmark_alignment_contract_v203_2_3 as alignment
from proworksim.software_benchmark_candidates_v054 import reference, checked, write_new

OUT=scope.ARTIFACT_ROOT/'public-qualification-r1'
AUTH=scope.ARTIFACT_ROOT/'public-qualification-authorization-r1'
VERSION='v203.2.3-public-task-interpreter-qualification-r1'
RUNNER=r'''
import ast, hashlib, importlib.util, io, json, os, sys, types
from pathlib import Path
from tempfile import NamedTemporaryFile
root=Path('/tmp/pws-public-qualification')
config=json.loads((root/'config.json').read_text())
# Only the unchanged atomic_write/json_bytes functions are needed. Loading the
# full host Store package would impose unrelated Python>=3.10 annotations on
# the task's Python3.9. These exact function bytes are recorded in the result.
pkg=types.ModuleType('proworksim');pkg.__path__=[str(root/'proworksim')]
sys.modules['proworksim']=pkg
storage=types.ModuleType('proworksim.storage')
source=(root/'proworksim/storage.py').read_text();tree=ast.parse(source)
functions={node.name:ast.get_source_segment(source,node) for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in ('atomic_write','json_bytes')}
storage.__dict__.update(os=os,Path=Path,NamedTemporaryFile=NamedTemporaryFile,json=json)
for code in functions.values():exec(compile(code,'exact-storage-function','exec'),storage.__dict__)
sys.modules['proworksim.storage']=storage
from proworksim.software_public_test_retention_v203_2_3 import retaining_executor,load_base
out=root/'evidence';out.mkdir()
fixture=root/'fixtures';fixture.mkdir()
(fixture/'pytest.ini').write_text('[pytest]\nfilterwarnings = error\n')
files={
'pass/test_case.py':'def test_real():\n    assert 2 + 2 == 4\n',
'nested/test_case.py':'import pytest\nfrom pathlib import Path\ndef test_nested(tmpdir):\n    p=Path(str(tmpdir))/"test_child.py"\n    p.write_text("def test_bad(): assert False")\n    assert pytest.main(["-q","--rootdir="+str(p.parent),str(p)]) == 1\n',
'incomplete/test_case.py':'import os\ndef test_incomplete():\n    os._exit(0)\n'}
for name,body in files.items():
    p=fixture/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body)
fixture_sha=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
binding={'source_reference':config['configuration'],'candidate_tree_sha256':fixture_sha,
    'synthetic_fixture_not_solver_candidate':True,'task_instance_id':config['instance_id']}
execute=retaining_executor(out/'raw',binding=binding,root=root)
env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTEST_PLUGINS':'','HTTP_PROXY':'','HTTPS_PROXY':'','ALL_PROXY':'','PYTHONDONTWRITEBYTECODE':'1'}
results={}
for name in ('pass','nested','incomplete'):
    results[name]=execute({'argv':[config['public_python'],'-m','pytest','-q',str(fixture/name/'test_case.py')]},root=fixture,environment=env,timeout_seconds=45)
base=load_base(root)
reparsed={}
for name,value in results.items():
    retained=value['test_evidence']['retained_journal'];receipt=json.loads(Path(retained['binding_receipt']).read_text())
    raw=Path(receipt['journal']['path']).read_bytes();stdout=Path(receipt['stdout']['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==receipt['journal']['sha256']==retained['journal_sha256']
    assert hashlib.sha256(stdout).hexdigest()==receipt['stdout']['sha256']
    assert receipt['full_original_bytes_retained'] and receipt['binding']==binding
    reparsed[name]=base.parse_test_evidence(raw,framework='pytest',token=receipt['observer_token'],process_group=receipt['process_group'],returncode=receipt['returncode'],timed_out=receipt['timed_out'])
    assert reparsed[name]['validation_status']==value['validation_status']
p=results['pass'];n=results['nested'];u=results['incomplete']
children=[v for v in n['test_evidence']['sessions'] if not v['root']]
passed=(p['passed'] is True and p['counts']['passed']==1 and n['passed'] is True
    and n['counts']['passed']==1 and n['counts']['failed']==0 and len(children)==1
    and children[0]['counts']['failed']==1 and u['passed'] is False and u['validation_status']=='unknown_collection')
result={'passed':passed,'instance_id':config['instance_id'],'task_interpreter':sys.version,
    'task_python_executable':sys.executable,'declared_task_python':config['public_python'],
    'same_pinned_execution_and_observer_bytes':True,'unchanged_storage_function_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in functions.items()},
    'results':results,'raw_reparse_statuses':{k:v['validation_status'] for k,v in reparsed.items()},
    'synthetic_fixture_controls':True,'repository_suite_pass_claimed':False,'model_calls':0}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'passed':passed,'instance_id':config['instance_id'],'statuses':result['raw_reparse_statuses']}))
if not passed:raise RuntimeError('Task interpreter or original raw-journal controls failed')
'''


def sources():
    return [Path(__file__).resolve(),Path(scope.__file__),Path(alignment.__file__),scope.PLAN_FILE,
        scope.ROOT/'src/proworksim/software_public_test_retention_v203_2_3.py',
        scope.ROOT/'src/proworksim/storage.py',scope.ROOT/'tools/public_test_execution_v175.py',
        scope.ROOT/'tools/public_test_evidence_v175.py']


def prepare():
    if any((OUT/spec['instance_id']/'intent.json').exists() for spec in scope.load(reference(scope.PLAN_FILE))['public_qualifications']):
        raise PermissionError('Consumed qualification identities cannot be prepared again')
    index=scope.retain(AUTH/'sources.json',{'version':VERSION,'files':[reference(p) for p in sources()]})
    return scope.retain(AUTH/'authorization.json',{'version':VERSION,'status':'approved',
        'plan':reference(scope.PLAN_FILE),'source_index':index,'uid':os.getuid(),
        'execution_alignment_version':alignment.VERSION,'API_calls_allowed':0,'maximum_containers':4,
        'maximum_concurrency':1,'cpu_per_container':2,'memory_per_container':8*scope.GIB,
        'network':'none','cap_drop':['ALL'],'host_binds':[],'maximum_named_volumes':0,
        'authority_source':'Existing user authorization for noninterfering experimental Docker; four necessary zero-model public task-interpreter controls within the new fixed panel.',
        'new_cash_budget':False,'host_root_operations':False,'shared_host_changes':False})


def archive_payload(config,configuration):
    files={'runner.py':RUNNER.encode(),'config.json':json.dumps({'instance_id':config['instance_id'],
        'configuration':configuration,'public_python':config['public_test_entry']['public_python']}).encode()}
    for rel in ('src/proworksim/software_public_test_retention_v203_2_3.py','src/proworksim/storage.py',
                'tools/public_test_execution_v175.py','tools/public_test_evidence_v175.py'):
        target=rel.removeprefix('src/')
        files[target]=(scope.ROOT/rel).read_bytes()
    payload=io.BytesIO()
    with tarfile.open(fileobj=payload,mode='w') as archive:
        for name,raw in files.items():
            info=tarfile.TarInfo('pws-public-qualification/'+name);info.size=len(raw);info.mode=0o444
            archive.addfile(info,io.BytesIO(raw))
    return payload.getvalue()


def collect_archive(container,folder):
    chunks,_=container.get_archive('/tmp/pws-public-qualification/evidence')
    raw=bytearray()
    for chunk in chunks:
        raw.extend(chunk)
        if len(raw)>64*1024**2:raise ValueError('Public qualification output exceeded 64MiB')
    archive_path=folder/'raw-evidence.tar'
    archive_path.write_bytes(raw)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        names=[m for m in archive.getmembers() if m.isfile() and m.name.endswith('/result.json')]
        if len(names)!=1:raise ValueError('The exact result file is missing from retained output')
        result=json.loads(archive.extractfile(names[0]).read())
    return result,reference(archive_path)


def run_one(spec,client,policy):
    task=spec['instance_id'];folder=OUT/task;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'intent.json').exists():raise PermissionError('Never replay a consumed qualification container')
    plan=scope.load(reference(scope.PLAN_FILE));cref=plan['environments'][task]['configuration'];config=scope.load(cref)
    claim=policy.claim_resource(spec['resource_key']);claim_value=scope.load(claim)
    name=claim_value['docker_name'];labels={'proworksim.role_context_qualification':VERSION,'proworksim.claim':claim['sha256']}
    owned=None;result=None;error=None;removed=False
    write_new(folder/'intent.json',{'claim':claim,'authorization':reference(AUTH/'authorization.json'),'unix':time.time()})
    try:
        try:client.containers.get(name)
        except __import__('docker').errors.NotFound:pass
        else:raise PermissionError('The new qualification Docker identity already exists')
        scope.require_preparation_allowed(instance_id=task)
        owned=client.containers.create(image=spec_image(plan,spec),name=name,entrypoint=[],command=['sleep','600'],
            network_mode='none',cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
            nano_cpus=2_000_000_000,mem_limit=8*scope.GIB,memswap_limit=8*scope.GIB,pids_limit=256,
            cpuset_cpus=scope.cpu_set('public_qualification'),labels=labels,user='0:0',detach=True)
        owned.reload();attrs=owned.attrs;host=attrs['HostConfig']
        if (host['NetworkMode']!='none' or host.get('Binds') or attrs.get('Mounts') or host.get('Privileged')
                or host.get('CapAdd') or host.get('CapDrop')!=['ALL'] or host['NanoCpus']!=2_000_000_000
                or host['Memory']!=8*scope.GIB or host['MemorySwap']!=8*scope.GIB
                or host['CpusetCpus']!=scope.cpu_set('public_qualification')):
            raise PermissionError('Actual container settings differ from the bounded qualification')
        write_new(folder/'created.json',{'id':owned.id,'name':name,'host_config':host,'image_id':attrs['Image'],'claim':claim})
        owned.start()
        if not owned.put_archive('/tmp',archive_payload(config,cref)):raise RuntimeError('Public fixture upload failed')
        value=owned.exec_run([config['public_test_entry']['public_python'],'/tmp/pws-public-qualification/runner.py'],
            environment={'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':'/tmp/pws-public-qualification','HTTP_PROXY':'','HTTPS_PROXY':'','ALL_PROXY':''})
        write_new(folder/'execution.json',{'exit_code':value.exit_code,'output':value.output.decode('utf-8','replace')})
        result,raw=collect_archive(owned,folder)
        result['retained_archive']=raw;result['claim']=claim
        if value.exit_code!=0 or result.get('passed') is not True:raise RuntimeError('Actual task-interpreter controls did not pass')
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if owned is not None:
            owned.reload()
            if any(owned.attrs['Config']['Labels'].get(k)!=v for k,v in labels.items()):
                raise PermissionError('Cannot clean a foreign container')
            if owned.attrs['State']['Running']:owned.stop(timeout=10)
            owned.remove(v=True)
            try:client.containers.get(owned.id)
            except __import__('docker').errors.NotFound:removed=True
        else:
            try:found=client.containers.get(name)
            except __import__('docker').errors.NotFound:removed=True
            else:
                raise PermissionError('Ambiguous container creation needs explicit ownership recovery')
        cleanup=write_new(folder/'cleanup.json',{'removed':removed,'claim':claim,'other_objects_touched':False})
        if not removed:raise PermissionError('Qualification cleanup is not proven')
        policy.release_resource(claim,quiescent=True)
    value={'version':VERSION,'instance_id':task,'passed':error is None,'result':result,'error':error,
        'cleanup':cleanup,'model_calls':0,'repository_suite_pass_claimed':False}
    write_new(folder/'summary.json',value);return value


def spec_image(plan,spec):
    return plan['resources'][spec['resource_key']]['image_id']


def run():
    scope.require_preparation_allowed()
    from proworksim.software_benchmark_scorer_v054 import install_offline_guard
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    config=scope.load(next(iter(plan['environments'].values()))['configuration'])
    socket=config['scorer_request_base']['docker_socket'];install_offline_guard(Path(socket))
    import docker
    client=docker.DockerClient(base_url='unix://'+socket,timeout=240)
    policy=scope.preparation_dispatch_view()
    rows=[]
    for spec in plan['public_qualifications']:
        rows.append(run_one(spec,client,policy))
    value={'version':VERSION,'passed':all(r['passed'] for r in rows),'rows':rows,'plan':reference(scope.PLAN_FILE),
        'model_calls':0,'API_calls':0,'maximum_concurrency':1,'maximum_containers':4,
        'network':'none','host_changes':False,'raw_journals_and_stdout_retained':True,
        'repository_suite_pass_claimed':False}
    write_new(OUT/'summary.json',value);return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(run() if args.execute else {'authorization':prepare()},ensure_ascii=False))
