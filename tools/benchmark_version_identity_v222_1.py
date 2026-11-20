"""Two isolated copies of a closed real state, zero API, unchanged semantic checks."""
import argparse,copy,gc,hashlib,json,os,resource,shutil,time
from pathlib import Path
from types import SimpleNamespace
from proworksim import software_runtime_performance_v217_2 as old
from proworksim import software_runtime_performance_v222_1 as new
from proworksim.software_organization_world_v222 import World,Port,PROJECT
from proworksim.software_organization_performance_v214 import CachedStore,BundleCache
from proworksim.storage import json_bytes
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
resource.setrlimit(resource.RLIMIT_AS,(20*1024**3,20*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(600,600));os.nice(10)
source=R/'runs/software-benchmark-v222/paired4-r1/task-03/PREFIX';result=json.loads((source/'result.json').read_text());assert result['status']=='decision_checkpoint_ready'
src=source/'prepared/world';statefile=src/'control/state.json'
def filehash(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
source_hash=filehash(statefile);results={}
def normalized(v):
 if isinstance(v,dict):return {k:normalized(x) for k,x in v.items() if k not in ('wall_seconds','state_digests')}
 if isinstance(v,list):return [normalized(x) for x in v]
 return v
for label,module in [('baseline',old),('optimized',new)]:
 root=out/label;root.mkdir();(root/'control').mkdir()
 for name in ('state.json','world.lock'):
  if (src/'control'/name).exists():shutil.copyfile(src/'control'/name,root/'control'/name)
 shutil.copytree(src/'control/versions',root/'control/versions')
 w=World.__new__(World);w.store=CachedStore(root);w.state=w.store.load();w._reads=[];w._writes=[];w.fault_hook=None;w._operation_context={};w.bundle_cache=BundleCache();w.information_condition='L';w.fixed_candidates_closed=False
 w.test_budget=SimpleNamespace(snapshot=lambda:{'limit':512,'used':0,'remaining':512});w.public_test_entry=json.loads((R/'runs/software-benchmark-v064/full-verified-r1/configs/3348.json').read_text())['public_test_entry'];module.install(w)
 port=Port(w.session('member_001',PROJECT),'member_001');port.tools();times=[];signatures=[]
 for i in range(2):
  t=time.perf_counter();r=port.call('org_status',request_key='offline-identity-benchmark-'+str(i));view=port.observe();elapsed=time.perf_counter()-t;assert r['ok'];times.append(elapsed)
  signatures.append(hashlib.sha256(json_bytes(normalized({'result':r,'view':view}))).hexdigest())
 results[label]={'step_seconds':times,'response_and_observation_sha256':signatures,'metrics':module.metrics(w),'state_bytes':(root/'control/state.json').stat().st_size}
 print(label,json.dumps({'seconds':times,'identity':results[label]['metrics'].get('version_identity_cache')}),flush=True)
 del w,port;gc.collect()
assert results['baseline']['response_and_observation_sha256']==results['optimized']['response_and_observation_sha256']
assert filehash(statefile)==source_hash
results.update(source=str(statefile),source_sha256=source_hash,source_unchanged=True,passed=True,model_calls=0,cold_action_speedup=results['baseline']['step_seconds'][0]/results['optimized']['step_seconds'][0],warm_action_speedup=results['baseline']['step_seconds'][1]/results['optimized']['step_seconds'][1],scope='two repeated org_status plus complete observe calls, independent copied closed state; not full model episode',test_budget_snapshot='synthetic unchanged fixed observation; no test callback invoked')
(out/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print('PASSED',results['cold_action_speedup'],results['warm_action_speedup'])
