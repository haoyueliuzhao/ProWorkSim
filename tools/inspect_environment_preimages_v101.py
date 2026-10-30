"""Bounded read-only diagnostics inside three new, owned offline containers."""
from __future__ import annotations

import argparse
import json
import secrets
import time

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim import software_benchmark_dispatch_v066 as original

ROOT = original.ROOT
OUTPUT = ROOT/'runs/software-benchmark-v101/environment-preimages-r1'
TASKS = ('psf__requests-1142', 'django__django-10097')
REQUESTS_PROBE = r'''import os,sys,json,stat,hashlib,subprocess
os.chdir('/testbed')
def git(*args):
 return subprocess.check_output(['/usr/bin/git','-c','safe.directory=/testbed']+list(args))
value={'head':git('rev-parse','HEAD').decode().strip(),'tree':git('rev-parse','HEAD^{tree}').decode().strip(),'status':git('status','--porcelain=v1').decode(),'tracked_build':git('ls-files','-z','--','build').decode().split('\0'),'entries':[]}
total=0
if os.path.islink('build') or not os.path.isdir('build'):raise ValueError('Build is not an ordinary directory')
for parent,dirs,files in os.walk('build',followlinks=False):
 for name in sorted(dirs+files):
  path=os.path.join(parent,name);info=os.lstat(path);item={'path':path,'mode':stat.S_IMODE(info.st_mode),'bytes':info.st_size}
  if stat.S_ISLNK(info.st_mode):item['kind']='symlink';item['target']=os.readlink(path)
  elif stat.S_ISDIR(info.st_mode):item['kind']='directory'
  elif stat.S_ISREG(info.st_mode):
   item['kind']='regular';total+=info.st_size
   if total>256*1024*1024:raise ValueError('Build inspection exceeds 256MiB')
   h=hashlib.sha256()
   with open(path,'rb') as stream:
    for block in iter(lambda:stream.read(1048576),b''):h.update(block)
   item['sha256']=h.hexdigest();item['matches_tracked_source']=False
   if path.startswith('build/lib/'):
    source=path[len('build/lib/'):];item['possible_tracked_source']=source
    try:
     original=git('rev-parse','HEAD:'+source).decode().strip();actual=git('hash-object','--',path).decode().strip()
     item['git_head_blob']=original;item['git_build_blob']=actual;item['matches_tracked_source']=original==actual
    except subprocess.CalledProcessError:item['source_lookup_failed']=True
  else:item['kind']='special'
  value['entries'].append(item)
  if len(value['entries'])>10000:raise ValueError('Build entry count exceeds 10000')
value['total_regular_bytes']=total;value['all_files_match_tracked_sources']=all(x.get('matches_tracked_source') is True for x in value['entries'] if x['kind']!='directory');print(json.dumps(value,sort_keys=True))
'''
DJANGO_PROBE = r'''import os,sys,json,runpy
os.chdir('/testbed');sys.path[0]='/testbed/tests'
original=list(sys.path);sys.argv=['/testbed/tests/runtests.py','--help']
try:runpy.run_path('/testbed/tests/runtests.py',run_name='__main__')
except SystemExit as error:exitcode=error.code
except Exception as error:exitcode=repr(error)
else:exitcode=0
value={'script_help_exit':exitcode,'script_path_context':original,'actual_sys_path':sys.path,'environment_pythonpath':os.environ.get('PYTHONPATH'),'loaded_modules':{},'files':{}}
for name in ('django','django.template','django.template.loaders.app_directories','django.template.loaders.filesystem','django.template.utils'):
 try:
  module=__import__(name,fromlist=['*']);value['loaded_modules'][name]=getattr(module,'__file__',None)
 except Exception as error:value['loaded_modules'][name]=repr(error)
for path in ('tests/runtests.py','tests/auth_tests/test_views.py','tests/test_sqlite.py','django/template/loaders/app_directories.py','django/template/loaders/filesystem.py','django/template/utils.py','django/contrib/admin/templates/registration/password_reset_form.html','tests/auth_tests/templates/registration/password_reset_form.html'):
 try:
  body=open(path,'rb').read(65537)
  if len(body)>65536:value['files'][path]={'bytes_over_64KiB':True,'prefix':body[:65536].decode('utf-8','replace')}
  else:value['files'][path]={'bytes':len(body),'text':body.decode('utf-8','replace')}
 except Exception as error:value['files'][path]={'error':repr(error)}
module=sys.modules.get('django')
if module is not None:
 base=os.path.dirname(module.__file__);value['imported_admin_template']={'path':base+'/contrib/admin/templates/registration/password_reset_form.html','exists':os.path.isfile(base+'/contrib/admin/templates/registration/password_reset_form.html')}
print('PWS_V101_SCRIPT_CONTEXT:'+json.dumps(value,sort_keys=True))
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
                     'name':'proworksim-v101-diag-'+task.replace('__','-'),
                     'ownership_token':secrets.token_hex(16)})
    return write_new(OUTPUT/'plan.json',{'version':'v101-two-owned-offline-readonly-diagnostics-r1',
        'source':reference(__file__),'jobs':jobs,'maximum_created_containers':2,
        'maximum_concurrency':1,'cpu':2,'memory_bytes':2*1024**3,'lifecycle_seconds':90,
        'network':'none','cap_drop':['ALL'],'host_mounts':False,'ports':False,'new_volumes':0,
        'root_host_operations':0,'model_calls':0,'candidate_patch_or_official_tests_applied':False,
        'host_configuration_changes':0,'only_readonly_commands_inside_new_owned_containers':True,
        'diagnostic_sources':{'requests_build':REQUESTS_PROBE,'django_script_context':DJANGO_PROBE},
        'no_tests_installation_cleanup_or_candidate_access':True})


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
        labels={'proworksim.scope':'v101-readonly-environment-diagnostic',
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
                      [job['python'],'-c',REQUESTS_PROBE if job['task']=='psf__requests-1142' else DJANGO_PROBE]]
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
