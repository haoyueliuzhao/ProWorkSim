"""Bounded read-only diagnostics inside three new, owned offline containers."""
from __future__ import annotations

import argparse
import json
import secrets
import time

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim import software_benchmark_dispatch_v066 as original

ROOT = original.ROOT
OUTPUT = ROOT/'runs/software-benchmark-v100/environment-diagnostics-r1'
TASKS = ('psf__requests-1142', 'pylint-dev__pylint-8898', 'django__django-10097')
PROBE = r'''import os,sys,json,sqlite3
value={'python':sys.version,'executable':sys.executable,'path':sys.path,'sqlite':sqlite3.sqlite_version,'has_affinity':hasattr(os,'sched_getaffinity')}
for name in ('django','pylint','requests'):
 try:
  module=__import__(name);value[name]={'file':getattr(module,'__file__',None),'version':str(getattr(module,'__version__',None))}
 except Exception as error:value[name]={'error':repr(error)}
paths=['/testbed/django/contrib/admin/templates/registration/password_reset_form.html','/testbed/tests/auth_tests/templates/registration/password_reset_form.html','/testbed/tests/templates/registration/password_reset_form.html']
value['template_paths']={p:os.path.exists(p) for p in paths}
value['kernel_cpu_allowed']=[line.strip() for line in open('/proc/self/status') if line.startswith('Cpus_allowed_list:')]
print(json.dumps(value))
'''


def load(ref):
    return json.loads(checked(ref).read_bytes())


def prepare():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    jobs=[]
    for task in TASKS:
        request=reference(original.GRADING_ROOT/('control-'+task+'-gold')/'request.json')
        configuration=load(request)['configuration']
        config=load(configuration)
        base=config['scorer_request_base']
        mapping=load(base['baseline_mapping'])
        jobs.append({'task':task,'original_control_request':request,'configuration':configuration,
                     'image_id':base['image']['image_id'],'socket':base['docker_socket'],
                     'baseline_mapping':base['baseline_mapping'],'python':mapping['public_python'],
                     'name':'proworksim-v100-diag-'+task.replace('__','-'),
                     'ownership_token':secrets.token_hex(16)})
    return write_new(OUTPUT/'plan.json',{'version':'v100-three-owned-offline-readonly-diagnostics-r1',
        'source':reference(__file__),'jobs':jobs,'maximum_created_containers':3,
        'maximum_concurrency':1,'cpu':2,'memory_bytes':2*1024**3,'lifecycle_seconds':90,
        'network':'none','cap_drop':['ALL'],'host_mounts':False,'ports':False,'new_volumes':0,
        'root_host_operations':0,'model_calls':0,'candidate_patch_or_official_tests_applied':False,
        'host_configuration_changes':0,'only_readonly_commands_inside_new_owned_containers':True})


def execute():
    import docker
    plan_ref=reference(OUTPUT/'plan.json')
    plan=load(plan_ref)
    if plan['source']!=reference(__file__) or tuple(j['task'] for j in plan['jobs'])!=TASKS:
        raise ValueError('Diagnostic source or exact task scope changed')
    cpuset=','.join(map(str,original.host_cpu_pool()[76:78]))
    results=[]
    for job in plan['jobs']:
        folder=OUTPUT/job['task']
        folder.mkdir()
        client=docker.DockerClient(base_url='unix://'+job['socket'],timeout=20)
        container=None
        result={'task':job['task'],'plan':plan_ref,'commands':[], 'create_attempted':False,
                               'model_calls':0,'other_objects_modified':False,'cleanup_proven':False}
        labels={'proworksim.scope':'v100-readonly-environment-diagnostic',
                'proworksim.task':job['task'],'proworksim.ownership':job['ownership_token']}
        try:
            # Immutable IDs only; the SDK does not pull a missing image here.
            image=client.images.get(job['image_id'])
            if image.attrs.get('Config',{}).get('Volumes'):
                raise PermissionError('An image declaring automatic volumes is outside this diagnostic scope')
            options=dict(image=job['image_id'],name=job['name'],
                entrypoint=['/bin/sh','-c'],command=['sleep 90'],network_mode='none',
                cap_drop=['ALL'],cap_add=[],security_opt=['no-new-privileges:true'],
                nano_cpus=2_000_000_000,cpuset_cpus=cpuset,mem_limit=2*1024**3,
                memswap_limit=2*1024**3,pids_limit=128,labels=labels,
                environment={'PYTHONDONTWRITEBYTECODE':'1'},detach=True)
            write_new(folder/'create-intent.json',{'plan':plan_ref,'options':options,'unix':time.time()})
            result['create_attempted']=True
            container=client.containers.create(**options)
            result['container_id']=container.id
            container.reload()
            attrs=container.attrs
            host=attrs['HostConfig']
            if (attrs['Image']!=job['image_id'] or any(attrs['Config'].get('Labels',{}).get(k)!=v for k,v in labels.items())
                    or host['NetworkMode']!='none' or attrs.get('Mounts')
                    or host.get('Privileged') or host.get('Binds') or host.get('DeviceRequests')
                    or host.get('PortBindings') or host.get('CapDrop')!=['ALL']
                    or host.get('CapAdd') not in (None,[])
                    or host.get('NanoCpus')!=2_000_000_000 or host.get('Memory')!=2*1024**3
                    or host.get('MemorySwap')!=2*1024**3 or host.get('CpusetCpus')!=cpuset):
                raise PermissionError('New diagnostic container has unexpected authority')
            container.start()
            commands=[['/usr/bin/git','-c','safe.directory=/testbed','-C','/testbed','rev-parse','HEAD','HEAD^{tree}'],
                      ['/usr/bin/git','-c','safe.directory=/testbed','-C','/testbed','status','--porcelain=v1'],
                      [job['python'],'-c',PROBE]]
            for number,command in enumerate(commands):
                response=container.exec_run(command,demux=True)
                stdout,stderr=response.output
                stdout,stderr=stdout or b'',stderr or b''
                if len(stdout)+len(stderr)>1024*1024:
                    raise ValueError('Diagnostic output exceeded its one-MiB bound')
                out=write_new(folder/('command-%d.stdout'%number),stdout)
                err=write_new(folder/('command-%d.stderr'%number),stderr)
                result['commands'].append({'argv':command,'exit_code':response.exit_code,'stdout':out,'stderr':err})
        except Exception as error:
            result['error']={'type':type(error).__name__,'message':str(error)}
        finally:
            if container is not None:
                try:
                    container.reload()
                    if any(container.attrs['Config'].get('Labels',{}).get(k)!=v for k,v in labels.items()) or container.id!=result['container_id']:
                        raise PermissionError('Only this newly created exact diagnostic object may be cleaned')
                    if container.attrs['State']['Running']:
                        container.stop(timeout=3)
                    container.remove(v=False,force=False)
                    try:
                        client.containers.get(container.id)
                    except docker.errors.NotFound:
                        result['cleanup_proven']=True
                except Exception as error:
                    result['cleanup_error']={'type':type(error).__name__,'message':str(error)}
            else:
                result['creation_outcome_must_be_reviewed']=result['create_attempted']
                result['cleanup_proven']=not result['create_attempted']
            client.close()
            results.append(write_new(folder/'result.json',result))
        if not result['cleanup_proven']:
            break
    return write_new(OUTPUT/'summary.json',{'version':plan['version'],'plan':plan_ref,'results':results,
        'model_calls':0,'host_configuration_changes':0,'no_preexisting_container_modified':True})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--prepare',action='store_true')
    choice.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    print(json.dumps(prepare() if args.prepare else execute()))
