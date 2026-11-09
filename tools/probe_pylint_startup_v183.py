"""One short private image probe; no model, network, volumes or host changes."""
import json,os,time
from pathlib import Path
import docker
from proworksim.software_benchmark_candidates_v054 import reference,checked,write_new
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v183/pylint-startup-probe-r1'
plan=json.loads((ROOT/'runs/software-benchmark-v181/full-context-pilot-r1/execution-plan.json').read_bytes())
config=json.loads(checked(plan['environments']['pylint-dev__pylint-8898']['configuration']).read_bytes())
mapping=json.loads(checked(config['scorer_request_base']['baseline_mapping']).read_bytes())
name='pws-v183-pylint-startup-diagnostic-r1';label={'proworksim.scope':'v183-pylint-startup-probe-r1','proworksim.owner':str(os.getuid())}
client=docker.DockerClient(base_url='unix://'+config['scorer_request_base']['docker_socket'],timeout=20)
value={'image':config['scorer_request_base']['image']['image_id'],'public_python':mapping['public_python'],'commands':[],'API_calls':0,'host_changes':0}
container=None
try:
 image=client.images.get(value['image'])
 value['image_working_directory']=image.attrs['Config'].get('WorkingDir')
 container=client.containers.create(value['image'],command=['/bin/sleep','90'],name=name,labels=label,
  network_mode='none',cap_drop=['ALL'],security_opt=['no-new-privileges:true'],read_only=True,
  nano_cpus=2_000_000_000,mem_limit=4*1024**3,memswap_limit=4*1024**3,pids_limit=64,
  cpuset_cpus='44,45',user='0:0',working_dir='/testbed')
 write_new(OUT/'created.json',{'id':container.id,'name':name,'labels':label,'limits':'2CPU/4GiB/networknone/dropALL/read_only/no_bind/no_volume'})
 container.start()
 code="import os,json,sys; print(json.dumps({'executable':sys.executable,'json_file':getattr(json,'__file__',None),'cwd':os.getcwd(),'namespaces':{k:os.stat('/proc/self/ns/'+k).st_ino for k in ('net','mnt','pid','ipc')},'cpus':sorted(os.sched_getaffinity(0))}))"
 for command in [[mapping['public_python'],'-c',code],[mapping['public_python'],'-I','-c',code],['/bin/pwd']]:
  result=container.exec_run(command,demux=True)
  stdout,stderr=result.output
  value['commands'].append({'argv':command,'exit_code':result.exit_code,'stdout':(stdout or b'').decode(errors='replace')[:8192],'stderr':(stderr or b'').decode(errors='replace')[:8192]})
except Exception as error:value['error']={'type':type(error).__name__,'message':str(error)}
finally:
 if container is not None:
  container.reload()
  assert all(container.attrs['Config']['Labels'].get(k)==v for k,v in label.items())
  container.stop(timeout=2);container.remove();value['owned_container_removed']=True
 client.close()
 write_new(OUT/'result.json',value)
 print(json.dumps(value,ensure_ascii=False))
