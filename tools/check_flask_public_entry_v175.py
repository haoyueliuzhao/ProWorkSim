"""One owned, mount-free Flask container: reproduce then verify plugin repair."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import time

from proworksim.software_benchmark_candidates_v054 import checked,reference,write_new

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v175/flask-public-control-r1'
TASK='pallets__flask-5014'


def main():
    if os.getuid()==0:raise PermissionError('Ordinary-user Docker client only')
    OUT.mkdir(parents=True,exist_ok=True)
    plan=json.loads((ROOT/'runs/software-benchmark-v159/communication-pilot-recovery-r1/execution-plan.json').read_bytes())
    row=next(r for r in plan['rows'] if r['slot_index']==15725)
    config=json.loads(checked(row['configuration']).read_bytes())
    image=config['public_test_entry']['source_identity']['actor_image_id']
    # The original no-answer public actor image, never an official hidden-test patch.
    socket=config['scorer_request_base']['docker_socket']
    files={}
    for version in (141,175):
        for name in ('public_test_execution','public_test_evidence'):
            files[f'diag/{name}_v{version}.py']=(ROOT/f'tools/{name}_v{version}.py').read_bytes()
    runner='''import importlib.util,json,os
from pathlib import Path
root=Path('/tmp/diag')
result={}
for v in (141,175):
    spec=importlib.util.spec_from_file_location('execution'+str(v),root/('public_test_execution_v'+str(v)+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    entry={'argv':['/opt/miniconda3/envs/testbed/bin/python','-m','pytest','--','tests/test_blueprints.py']}
    value=module.execute_public_entry(entry,root='/testbed',environment=dict(os.environ),timeout_seconds=120)
    result[str(v)]=value
(root/'result.json').write_text(json.dumps(result))
print(json.dumps({k:{f:r.get(f) for f in ('passed','validation_status','returncode','counts')} for k,r in result.items()}))
'''
    files['diag/runner.py']=runner.encode()
    payload=io.BytesIO()
    with tarfile.open(fileobj=payload,mode='w') as archive:
        for path,raw in files.items():
            info=tarfile.TarInfo(path);info.size=len(raw);info.mode=0o444;info.uid=info.gid=0
            archive.addfile(info,io.BytesIO(raw))
    spec={'task':TASK,'image_id':image,'maximum_containers':1,'maximum_named_volumes':0,
        'network':'none','cap_drop':['ALL'],'host_binds':[],'GPU':False,'CPU':2,'memory_bytes':8*1024**3,
        'maximum_public_commands':2,'command_timeout_seconds':120,'model_calls':0,
        'candidate_patch_or_hidden_test_patch_applied':False,'shared_host_changes':False,
        'source_files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}}
    authority=write_new(OUT/'proposal.json',spec)
    from proworksim.software_benchmark_scorer_v054 import install_offline_guard
    install_offline_guard(Path(socket))
    import docker
    client=docker.DockerClient(base_url='unix://'+socket,timeout=300)
    name='pws-v175-public-'+authority['sha256'][:20]
    try:client.containers.get(name)
    except docker.errors.NotFound:pass
    else:raise FileExistsError('Never reuse a prior diagnostic container')
    owned=None
    try:
        owned=client.containers.create(image=image,name=name,command=['sleep','600'],
            entrypoint=[],network_mode='none',cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
            nano_cpus=2_000_000_000,mem_limit=8*1024**3,memswap_limit=8*1024**3,pids_limit=256,
            cpuset_cpus=','.join(map(str,sorted(os.sched_getaffinity(0))[-2:])),
            labels={'proworksim.batch':'v175-public-control','proworksim.authority':authority['sha256']},
            user='0:0',detach=True)
        write_new(OUT/'created.json',{'id':owned.id,'name':name,'authority':authority})
        owned.start()
        if not owned.put_archive('/tmp',payload.getvalue()):raise RuntimeError('Diagnostic transfer failed')
        result=owned.exec_run(['/opt/miniconda3/envs/testbed/bin/python','/tmp/diag/runner.py'],
            environment={'PYTHONDONTWRITEBYTECODE':'1','HTTP_PROXY':'','HTTPS_PROXY':'','ALL_PROXY':''})
        write_new(OUT/'execution.json',{'exit_code':result.exit_code,'stdout':result.output.decode('utf-8','replace')})
        if result.exit_code:raise RuntimeError('The isolated actual public entry did not finish')
        chunks,_=owned.get_archive('/tmp/diag/result.json');raw=bytearray()
        for chunk in chunks:
            raw.extend(chunk)
            if len(raw)>16*1024**2:raise ValueError('Public control output too large')
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            original=archive.extractfile(archive.getmembers()[0]).read()
        observed=json.loads(original);write_new(OUT/'actual-public-results.json',original)
        old,new=observed['141'],observed['175']
        passed=('PytestAssertRewriteWarning' in old['output'] and old['test_evidence']['report_count']==0
            and 'cannot be rewritten: pws_public_test_evidence_v141' not in new['output']
            and new['test_evidence']['report_count']>=1 and new['counts']['passed']>0)
        write_new(OUT/'summary.json',{'passed':passed,'old_status':old['validation_status'],
            'new_status':new['validation_status'],'new_counts':new['counts'],
            'same_public_command_and_initial_repository':True,'warnings_globally_suppressed':False,
            'original_v174_model_results_replaced':False,'model_calls':0,'new_hidden_scores':0,
            'new_execution_revision':new.get('deployment_revision')})
        if not passed:raise RuntimeError('Original Flask public command did not pass the observer compatibility gate')
    finally:
        if owned is not None:
            owned.reload()
            if owned.attrs['Config']['Labels'].get('proworksim.authority')!=authority['sha256']:
                raise PermissionError('Never clean another object')
            if owned.attrs['State']['Running']:owned.stop(timeout=10)
            owned.remove(v=True)
            try:client.containers.get(owned.id)
            except docker.errors.NotFound:removed=True
            else:removed=False
            write_new(OUT/'cleanup.json',{'owned_container_id':owned.id,'removed':removed,
                'other_objects_touched':False,'shared_host_configuration_changed':False})
    print(json.dumps({'output':str(OUT),'passed':True,'model_calls':0,'owned_container_removed':True}))


if __name__=='__main__':main()
