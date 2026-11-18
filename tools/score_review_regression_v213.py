"""One offline official score, fresh identity, only newly owned restricted container."""
from __future__ import annotations
import argparse,json,os,time,traceback,uuid
from pathlib import Path
from types import SimpleNamespace
from proworksim.storage import json_bytes,digest
from proworksim.software_benchmark_candidates_v054 import checked,reference,read_episode_candidates
from proworksim import software_benchmark_scorer_v054 as base
from proworksim.software_benchmark_scorer_r4_v054 import MappedObservedContainer
from proworksim.software_benchmark_baseline_v054 import validate_mapping
ROOT=Path(__file__).resolve().parents[1]
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(json_bytes(v))

def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 rows=json.loads((ROOT/'artifacts/software-benchmark-v213/targeted-regression-plan-r1/candidate-tasks.json').read_text())['rows']
 row=next(r for r in rows if r["index"]==a.index);cfg=json.loads(checked(row['configuration']).read_bytes());s=cfg['scorer_request_base']
 receipt={'version':'v203.3.3-official-score-r1','instance_id':row['instance_id'],'kind':a.kind,'status':'technical_unknown','resolved':None,'model_calls':0,'feedback_to_solver':False}
 client=None;owned=[];token=uuid.uuid4().hex;labels={'proworksim.v213.score':token}
 try:
  instance=base.read_local_dataset(s['dataset'])[row['instance_id']]
  mapping=validate_mapping(json.loads(checked(s['baseline_mapping']).read_bytes()),instance=instance,image=s['image'])
  manifest=base.installation_manifest();save(out/'scorer-manifest.json',manifest)
  if a.kind in ('gold','empty'):
   patch=(instance['patch'] if a.kind=='gold' else '').encode();save(out/'control-kind.json',{'kind':a.kind,'hidden_material_only_in_scorer':True})
  else:
   ep=a.episode.resolve();generation=json.loads((ep/'result.json').read_text())
   if generation['instance_id']!=row['instance_id'] or generation['status']!='closed':raise ValueError('Only normally closed, same-task candidate')
   lock_ref=json.loads((ep/'candidate-lock.json').read_text());pair=read_episode_candidates(lock_ref)
   endpoint='terminal_code' if a.kind=='code' else 'last_legal_delivery';candidate=pair[endpoint]
   if candidate is None:
    receipt.update(status='no_legal_delivery',resolved=False,official_scoring_performed=False);save(out/'receipt.json',receipt);return
   # Read the frozen complete baseline; re-encode exactly the unique locked tree.
   baseline=json.loads((ep/'actor/initial-tree.json').read_text())
   from proworksim.software_benchmark_snapshot_recovery_v061 import export_utf8_patch
   exported=export_utf8_patch(baseline,candidate,out/'prediction.patch',policy=baseline['file_policy'])
   endpoint_lock=json.loads(checked(pair['lock'][endpoint]).read_bytes())
   if exported['candidate_tree_sha256']!=endpoint_lock['tree_sha256']:raise ValueError('Export differs from fixed candidate')
   save(out/'patch-receipt.json',exported);patch=checked(exported['patch']).read_bytes()
   receipt.update(episode_lock=lock_ref,endpoint_lock=pair['lock'][endpoint],candidate_tree_sha256=endpoint_lock['tree_sha256'],patch=exported['patch'])
  # No actor/test feedback is accepted by this process; actual hidden tests are grader-only.
  socket=Path(s['docker_socket']).resolve();base.install_offline_guard(socket)
  import docker
  from docker.errors import NotFound
  from swebench.harness.run_evaluation import run_instance
  from swebench.harness.utils import make_test_spec
  spec=make_test_spec(instance)
  if any(spec.image_assets.values()):raise ValueError('External assets not admitted')
  spec.image=s['image']['image_id'];run_id='v213-'+a.kind+'-'+token
  receipt.update(run_id=run_id,official_image=spec.image,official_version=manifest['official_version'])
  save(out/'identity.json',{**receipt,'configuration':row['configuration'],'dataset':s['dataset'],'mapping':s['baseline_mapping'],'patch_sha256':digest(patch),'scorer_manifest':reference(out/'scorer-manifest.json')})
  os.chdir(out);os.environ['DOCKER_HOST']='unix://'+str(socket)
  for name in ('DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):os.environ.pop(name,None)
  os.environ['PATH']=str(checked(s['docker_cli']).parent)+':/usr/bin:/bin'
  client=docker.DockerClient(base_url=os.environ['DOCKER_HOST'],timeout=1800)
  class Containers:
   def get(self,name):
    for container in owned:
     if name in (container.id,container.name):return container
    raise NotFound('No pre-existing scoring object in this run')
   def create(self,**kw):
    if owned:raise ValueError('One container per score')
    if kw.get('image')!=spec.image:raise ValueError('Unfrozen image')
    if any(kw.get(k) for k in ('volumes','mounts','devices','device_requests','ports','network','networking_config','volumes_from','links')):raise ValueError('Forbidden scorer attachment')
    kw.update(name='pws-v213-score-'+token,labels=labels,network_mode='none',cap_drop=['ALL'],cap_add=[],privileged=False,
     security_opt=['no-new-privileges:true'],mem_limit=16*1024**3,memswap_limit=16*1024**3,nano_cpus=4*10**9,pids_limit=512,
     ipc_mode='private',auto_remove=False)
    container=client.containers.create(**kw);owned.append(container)
    save(out/'created.json',{'id':container.id,'labels':labels,'no_host_mounts':True,'network':'none','cap_drop':['ALL']})
    return MappedObservedContainer(container,{'path':str(out/'initial-container.json'),'base_commit':mapping['official_head'],'mapping':mapping,'mapping_reference':s['baseline_mapping']})
  restricted=SimpleNamespace(images=base.LocalImages(client.images,spec.image),containers=Containers());restricted.images.get(spec.image)
  prediction={'instance_id':row['instance_id'],'model_name_or_path':run_id,'model_patch':patch.decode('utf-8')}
  result=run_instance(spec,prediction,restricted,run_id,timeout=1800,rewrite_reports=False,skip_patch=not patch,task_repo=None)
  report=result[1].get(row['instance_id'],{}) if result else {}
  known=result is not None and report.get('patch_successfully_applied') is True and not report.get('infra_failure',False) and type(report.get('resolved'))is bool
  receipt.update(status='official_report' if known else 'technical_unknown',resolved=report['resolved'] if known else None,official_result=result)
 except Exception as e:
  receipt.update(error_type=type(e).__name__,error=str(e));(out/'traceback.txt').write_text(traceback.format_exc())
 finally:
  errors=[]
  if client:
   for c in owned:
    try:
     c.reload()
     if c.labels.get('proworksim.v213.score')!=token:raise ValueError('Another owner: refuse cleanup')
     if c.status=='running':c.stop(timeout=10)
     c.remove(force=False,v=True)
    except Exception as e:
     if type(e).__name__!='NotFound':errors.append(str(e))
   client.close()
  receipt['cleanup_errors']=errors;receipt['finished']=time.time();save(out/'receipt.json',receipt)
 print(json.dumps({k:receipt.get(k) for k in ('instance_id','kind','status','resolved','error')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--index',type=int,required=True)
 p.add_argument('--kind',choices=['gold','empty','code','delivery'],required=True);p.add_argument('--episode',type=Path)
 a=p.parse_args()
 if a.kind in ('code','delivery') and not a.episode:p.error('Candidate endpoint requires unique closed episode')
 main(a)
