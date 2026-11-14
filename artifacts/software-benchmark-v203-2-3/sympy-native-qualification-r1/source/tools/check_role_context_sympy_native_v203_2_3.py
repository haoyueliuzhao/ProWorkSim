"""One new owned Sympy native-runner control; preserve the previous pytest mismatch."""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import time
from proworksim import software_benchmark_scope_v203_2_3 as scope
from proworksim.software_benchmark_candidates_v054 import reference,checked,write_new

VERSION='v203.2.3-sympy-native-public-qualification-r1'
OUT=scope.ARTIFACT_ROOT/'sympy-native-qualification-r1'
TASK='sympy__sympy-17655'
SOURCE_FILES=('tools/check_role_context_sympy_native_v203_2_3.py','tools/check_role_context_public_qualification_v203_2_3.py',
    'src/proworksim/software_public_test_retention_v203_2_3.py','src/proworksim/storage.py',
    'tools/public_test_execution_v175.py','tools/public_test_evidence_v175.py')


def helper():
    spec=importlib.util.spec_from_file_location('qualification_helpers',scope.ROOT/SOURCE_FILES[1])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def runner():
    prefix=helper().RUNNER.split("fixture=root/'fixtures';fixture.mkdir()",1)[0]
    return prefix+r'''
checkout=Path('/testbed')
files={
'sympy/core/tests/test_pws_qual_pass.py':'def test_pws_pass():\n    assert 2 + 2 == 4\n',
'sympy/core/tests/test_pws_qual_child.py':'def test_pws_child():\n    assert False\n',
'sympy/core/tests/test_pws_qual_nested.py':'import subprocess,sys\ndef test_pws_nested():\n    assert subprocess.call([sys.executable,"bin/test","sympy/core/tests/test_pws_qual_child.py"]) == 1\n',
'sympy/core/tests/test_pws_qual_incomplete.py':'import os\ndef test_pws_incomplete():\n    os._exit(0)\n'}
for name,body in files.items():
    p=checkout/name
    if p.exists():raise RuntimeError('Diagnostic filename already exists in the public baseline')
    p.write_text(body)
binding={'source_reference':config['configuration'],'candidate_tree_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
    'synthetic_fixture_not_solver_candidate':True,'task_instance_id':config['instance_id']}
execute=retaining_executor(out/'raw',binding=binding,root=root)
env={**os.environ,'HTTP_PROXY':'','HTTPS_PROXY':'','ALL_PROXY':'','PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0'}
public='sympy/deprecated/tests/test_class_registry.py'
public_hash=hashlib.sha256((checkout/public).read_bytes()).hexdigest()
results={}
for name,target in [('public',public),('pass','sympy/core/tests/test_pws_qual_pass.py'),('nested','sympy/core/tests/test_pws_qual_nested.py'),('incomplete','sympy/core/tests/test_pws_qual_incomplete.py')]:
    results[name]=execute({'argv':[config['public_python'],'bin/test',target]},root=checkout,environment=env,timeout_seconds=60)
base=load_base(root);reparsed={}
for name,value in results.items():
    retained=value['test_evidence']['retained_journal'];receipt=json.loads(Path(retained['binding_receipt']).read_text())
    raw=Path(receipt['journal']['path']).read_bytes();stdout=Path(receipt['stdout']['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==receipt['journal']['sha256']==retained['journal_sha256']
    assert hashlib.sha256(stdout).hexdigest()==receipt['stdout']['sha256']
    reparsed[name]=base.parse_test_evidence(raw,framework='sympy',token=receipt['observer_token'],process_group=receipt['process_group'],returncode=receipt['returncode'],timed_out=receipt['timed_out'])
    assert reparsed[name]['validation_status']==value['validation_status']
p=results['pass'];n=results['nested'];u=results['incomplete'];public_result=results['public']
children=[v for v in n['test_evidence']['sessions'] if not v['root']]
passed=(p['passed'] is True and p['counts']['passed']==1 and n['passed'] is True
    and n['counts']['passed']==1 and n['counts']['failed']==0 and len(children)==1
    and children[0]['counts']['failed']==1 and u['passed'] is False and u['validation_status']=='unknown_collection'
    and public_result['test_evidence']['report_count']>=1)
result={'passed':passed,'instance_id':config['instance_id'],'task_interpreter':sys.version,'task_python_executable':sys.executable,
    'actual_native_frontend':'bin/test','pytest_installed_for_repair':False,'source_public_file':{'path':public,'sha256':public_hash},
    'results':results,'raw_reparse_statuses':{k:v['validation_status'] for k,v in reparsed.items()},
    'synthetic_files_only_in_disposable_qualification_container':True,'repository_suite_pass_claimed':False,'model_calls':0}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'passed':passed,'statuses':result['raw_reparse_statuses']}))
if not passed:raise RuntimeError('Sympy native controls failed')
'''


def payload(config,cref):
    files={'runner.py':runner().encode(),'config.json':json.dumps({'instance_id':TASK,'configuration':cref,
        'public_python':config['public_test_entry']['public_python']}).encode()}
    for rel in SOURCE_FILES[2:]:files[rel.removeprefix('src/')]=(scope.ROOT/rel).read_bytes()
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as archive:
        for name,raw in files.items():
            info=tarfile.TarInfo('pws-public-qualification/'+name);info.size=len(raw);info.mode=0o444
            archive.addfile(info,io.BytesIO(raw))
    return buffer.getvalue()


def main():
    if os.getuid()==0 or os.geteuid()==0:raise PermissionError('Ordinary user only')
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'intent.json').exists():raise PermissionError('Never replay a consumed native qualification identity')
    plan=scope.load(reference(scope.PLAN_FILE));cref=plan['environments'][TASK]['configuration'];config=scope.load(cref)
    sources=[]
    for name in SOURCE_FILES:
        path=scope.ROOT/name;dest=OUT/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            if dest.read_bytes()!=path.read_bytes():raise PermissionError('Prepared native source changed')
        else:shutil.copyfile(path,dest)
        sources.append({'source':reference(path),'snapshot':reference(dest)})
    source=scope.retain(OUT/'sources.json',{'version':VERSION,'files':sources})
    proposal={'version':VERSION,'status':'approved','plan':reference(scope.PLAN_FILE),'source_index':source,'configuration':cref,
        'uid':os.getuid(),'instance_id':TASK,'maximum_containers':1,'maximum_concurrency':1,'CPU':2,'memory_bytes':8*scope.GIB,
        'cpuset_cpus':scope.cpu_set('public_qualification'),'network':'none','cap_drop':['ALL'],'host_binds':[],
        'API_calls_allowed':0,'maximum_named_volumes':0,'root_host_operations':False,'additional_cash_CNY':'0.00',
        'authority_source':'Existing user noninterfering Docker authorization covers one necessary native-runner correction; old pytest-mismatch evidence remains unchanged.'}
    auth=scope.retain(OUT/'authorization.json',proposal)
    name='pws-v20323-native-'+auth['sha256'][:20];labels={'proworksim.native_qualification':auth['sha256']}
    from proworksim.software_benchmark_scorer_v054 import install_offline_guard
    socket=config['scorer_request_base']['docker_socket'];install_offline_guard(Path(socket))
    import docker
    client=docker.DockerClient(base_url='unix://'+socket,timeout=300)
    try:client.containers.get(name)
    except docker.errors.NotFound:pass
    else:raise PermissionError('Native qualification object already exists')
    capacity=scope.dispatch_view().physical_capacity()
    if not capacity['passed'] or capacity['memory_available_bytes']<72*scope.GIB:
        raise scope.ResourceBusy('Shared-host headroom prevents native qualification')
    owned=None;result=None;error=None;removed=False
    write_new(OUT/'intent.json',{'authorization':auth,'name':name,'unix':time.time()})
    try:
        owned=client.containers.create(image=plan['environments'][TASK]['actor_image_id'],name=name,entrypoint=[],command=['sleep','600'],
            network_mode='none',cap_drop=['ALL'],security_opt=['no-new-privileges:true'],nano_cpus=2_000_000_000,
            mem_limit=8*scope.GIB,memswap_limit=8*scope.GIB,pids_limit=256,cpuset_cpus=proposal['cpuset_cpus'],labels=labels,user='0:0',detach=True)
        owned.reload();attrs=owned.attrs;h=attrs['HostConfig']
        if (h['NetworkMode']!='none' or h.get('Binds') or attrs.get('Mounts') or h.get('Privileged') or h.get('CapAdd')
                or h.get('CapDrop')!=['ALL'] or h['NanoCpus']!=2_000_000_000 or h['Memory']!=8*scope.GIB):
            raise PermissionError('Actual native qualification resource settings changed')
        write_new(OUT/'created.json',{'id':owned.id,'host_config':h,'authorization':auth})
        owned.start()
        if not owned.put_archive('/tmp',payload(config,cref)):raise RuntimeError('Native payload upload failed')
        r=owned.exec_run([config['public_test_entry']['public_python'],'/tmp/pws-public-qualification/runner.py'],environment={
            'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':'/tmp/pws-public-qualification','HTTP_PROXY':'','HTTPS_PROXY':'','ALL_PROXY':''})
        write_new(OUT/'execution.json',{'exit_code':r.exit_code,'output':r.output.decode('utf-8','replace')})
        result,raw=helper().collect_archive(owned,OUT);result['retained_archive']=raw
        if r.exit_code or result.get('passed') is not True:raise RuntimeError('Native task interpreter controls did not pass')
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if owned is not None:
            owned.reload()
            if any(owned.attrs['Config']['Labels'].get(k)!=v for k,v in labels.items()):raise PermissionError('Foreign native container')
            if owned.attrs['State']['Running']:owned.stop(timeout=10)
            owned.remove(v=True)
            try:client.containers.get(owned.id)
            except docker.errors.NotFound:removed=True
        else:
            try:client.containers.get(name)
            except docker.errors.NotFound:removed=True
        write_new(OUT/'cleanup.json',{'removed':removed,'other_objects_touched':False,'authorization':auth})
        if not removed:raise PermissionError('Native qualification cleanup not proven')
    value={'version':VERSION,'passed':error is None,'result':result,'error':error,'model_calls':0,'API_calls':0,
        'authorization':auth,'cleanup':reference(OUT/'cleanup.json'),'previous_pytest_mismatch_preserved':True}
    write_new(OUT/'summary.json',value)
    print(json.dumps({'passed':value['passed'],'error':error,'summary':reference(OUT/'summary.json')}))
    return value


if __name__=='__main__':main()
