"""Bounded zero-API benchmark on closed historical bytes; writes only new benchmark folder."""
import argparse,json,time,resource,hashlib,copy
from pathlib import Path
from proworksim import software_benchmark_state_storage_v141 as old
from proworksim import software_organization_performance_v214 as new
from proworksim.adapters.capabilities import read
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline-summary',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(300,300))
R=Path(__file__).resolve().parents[1];source=R/'runs/software-benchmark-v212/stage-a6-r1/task-02/COMBO/prepared/world';state_path=source/'control/state.json'
seed=json.loads(state_path.read_bytes());artifact=next(x for x in seed['artifacts'].values() if x.get('filename')=='member_001.json');bundle_path=source/'control/versions'/artifact['artifact_id']/artifact['current_version']/artifact['filename']
results={'baseline':json.loads(a.baseline_summary.read_text())['baseline']} if a.baseline_summary else {}
for kind,cls in [('baseline',old.StreamCachedStore),('optimized',new.CachedStore)]:
 if kind=='baseline' and a.baseline_summary:continue
 root=a.output/kind;(root/'control').mkdir(parents=True);store=cls(root);store.save(seed);bundle=new.BundleCache();rows=[];checks=[]
 for i in range(2):
  timings={};t=time.perf_counter();state=store.load();timings['load']=time.perf_counter()-t
  t=time.perf_counter();d=store.encoder.digest if kind=='optimized' else lambda v:old.streamed_digest(v,canonical=True)
  hashes=[d(state)];state['clock']+=1;hashes.extend([d(state),d(state)]);timings['three_canonical_digests']=time.perf_counter()-t
  t=time.perf_counter();store.save(state);timings['atomic_save']=time.perf_counter()-t
  t=time.perf_counter();store.load();store.load();timings['two_post_commit_loads']=time.perf_counter()-t
  t=time.perf_counter()
  for _ in range(2):
   value=bundle.get(bundle_path) if kind=='optimized' else read('json',bundle_path.read_bytes())
   count=len(value['files']);del value
  timings['two_bundle_reads']=time.perf_counter()-t
  checks.append({'digests':hashes,'file_count':count});rows.append(timings)
  print(kind,i,timings,flush=True)
 with (root/'control/state.json').open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 results[kind]={'encoding_cache_bytes':store.encoder.size if kind=='optimized' else None,'encoding_hits':store.encoder.hits if kind=='optimized' else None,'encoding_misses':store.encoder.misses if kind=='optimized' else None,'rounds':rows,'checks':checks,'final_bytes_sha256':h,'total_seconds':sum(sum(x.values()) for x in rows)}
assert results['baseline']['checks']==results['optimized']['checks'];assert results['baseline']['final_bytes_sha256']==results['optimized']['final_bytes_sha256']
results.update({'passed':True,'byte_and_digest_equivalent':True,'source_state':str(state_path),'state_bytes':state_path.stat().st_size,'bundle_bytes':bundle_path.stat().st_size,'speedup':results['baseline']['total_seconds']/results['optimized']['total_seconds'],'model_calls':0,'Docker_calls':0,'baseline_reused_from':str(a.baseline_summary) if a.baseline_summary else None,'not_end_to_end_speedup':True,'closed_source_not_modified':True})
(a.output/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
print('speedup',results['speedup'],flush=True)
