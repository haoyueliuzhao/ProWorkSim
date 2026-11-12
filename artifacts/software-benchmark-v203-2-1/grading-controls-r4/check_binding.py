"""Only inert CPU task routing with actual new binding, never Docker calls."""
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src'))
ART=Path(__file__).parent
RUN=ART/'cpu-binding'
RUN.mkdir(exist_ok=False)
name='proworksim.software_benchmark_scope_v203_2_1_r4'
# The real plan is prepared independently. This CPU-only namespace cannot claim
# objects; only the actual scorer constructor and local fake delegate are used.
fake=ModuleType(name);fake.__file__=str(ROOT/'src/proworksim/software_benchmark_grading_v203_2_1_r4.py')
fake.ROOT=ROOT;fake.BATCH_ROOT=RUN;fake.GRADING_ROOT=RUN/'grading';fake.COORDINATOR_ROOT=RUN/'coordinator';fake.MAX_GRADERS=2
sys.modules[name]=fake
from proworksim import software_benchmark_grading_v203_2_1_r4 as g
from proworksim.software_benchmark_candidates_v054 import reference
policy=SimpleNamespace(require_v066_allowed=lambda *a,**kw:{},__file__=fake.__file__)
s=g.scorer(policy);ns=s.validate_request.__globals__
assert ns['MAX_GRADERS']==2 and s.validate_delivery_evidence is g.closure.validate_delivery_evidence
assert g.host(policy,s).delivery_reuse_revision=='v175-own-code-score-manifest-bound-delivery-r1'
class Timer:
 def __init__(self,*a,**k):pass
 def start(self):pass
ns['threading']=SimpleNamespace(Timer=Timer)
image='sha256:'+'a'*64
seen=[]
class Container:
 id='not-a-real-container'
 def __init__(self,opts):
  self.options=opts
  self.attrs={'Image':image,'Mounts':[],'Config':{'Labels':opts['labels'],'Env':[k+'='+v for k,v in opts.get('environment',{}).items()]},
   'HostConfig':{'NetworkMode':opts['network_mode'],'Privileged':False,'CapAdd':opts['cap_add'],'CapDrop':opts['cap_drop'],
    'SecurityOpt':opts['security_opt'],'CpusetCpus':opts['cpuset_cpus'],'Memory':opts['mem_limit'],'MemorySwap':opts['memswap_limit'],
    'NanoCpus':opts['nano_cpus'],'PidsLimit':opts['pids_limit'],'IpcMode':'private',
    'ExtraHosts':[k+':'+v for k,v in opts.get('extra_hosts',{}).items()]}}
 def reload(self):pass
class Delegate:
 def create(self,**opts):
  seen.append(opts);return Container(opts)
cases={}
for i,task in enumerate([g.REQUESTS,g.PYLINT,'django__django-15572']):
 claim=RUN/('claim-'+str(i)+'.json');claim.write_text(json.dumps({'key':'fake-'+str(i),'docker_name':'not-created-'+str(i),'plan':{'sha256':'b'*64}}))
 observation={'mapping':{'instance_id':task},'image_id':image,'cpuset_cpus':'0','capacity_claim':reference(claim)}
 tracking={'owned_container_ids':[]};wrapper=s.Containers(Delegate(),image,observation,tracking).create(image=image)
 opts=seen[-1]
 assert opts['network_mode']=='none' and opts['cap_drop']==['ALL']
 if task==g.REQUESTS:
  assert 'requests2317_CA_wrapper' in tracking
  assert opts['cap_add']==['NET_ADMIN','NET_BIND_SERVICE']
  assert opts['environment']['PYTHONPATH'].split(':')[0]==g.ca_environment.FIXTURE_ROOT
  assert hasattr(wrapper,'verify_final_CA')
 else:
  assert 'requests2317_CA_wrapper' not in tracking and opts['cap_add']==[] and not opts.get('extra_hosts')
  assert 'PYTHONPATH' not in opts.get('environment',{})
  if task==g.PYLINT:assert opts['environment']['PIP_NO_INDEX']=='1'
  else:assert 'PIP_NO_INDEX' not in opts.get('environment',{})
 cases[task]={'private_CA_tracking':task==g.REQUESTS,'caps':opts['cap_add'],'extra_hosts':opts.get('extra_hosts',{}),
              'Pylint_offline_wheel':task==g.PYLINT,'wrapper':type(wrapper).__name__}
# Same bound cleanup function must leave ordinary-task results untouched.
x=g._parent_scorer(policy);xn=x.validate_request.__globals__;sentinel={'physical_cleanup':'unchanged'}
xn['cleanup']=lambda request,tracking:sentinel
g.bind_environment(x)
assert x.cleanup({}, {}) is sentinel and sentinel=={'physical_cleanup':'unchanged'}
value={'passed':True,'actual_new_scorer_binding':True,'synthetic_scope_only':True,'cases':cases,
 'ordinary_task_cleanup_return_identity_preserved':True,'fixed_001_delivery_validator_preserved':True,
 'same_tree_delivery_reuse_preserved':True,'Docker_calls':0,'API_calls':0,
 'source_sha256':hashlib.sha256(Path(g.__file__).read_bytes()).hexdigest()}
(ART/'binding-summary.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({'passed':True,'task_routes':3,'cleanup_control':1}))
