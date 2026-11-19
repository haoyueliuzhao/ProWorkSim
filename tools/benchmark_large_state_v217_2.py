"""Bounded zero-model benchmark on an immutable closed 704 MiB state."""
import argparse,json,time,resource,hashlib,shutil,gc,os
from pathlib import Path
from proworksim import software_organization_performance_v214 as old
from proworksim import software_runtime_performance_v217_2 as new
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline-summary',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
resource.setrlimit(resource.RLIMIT_AS,(20*1024**3,20*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(600,600));os.nice(10)
R=Path(__file__).resolve().parents[1];src=R/'runs/software-benchmark-v217/confirmation-resume-r1/task-10/PREFIX/final-world.json';original_hash=hashlib.sha256(src.read_bytes()).hexdigest();results={'baseline':json.loads(a.baseline_summary.read_text())['baseline']} if a.baseline_summary else {}
for name,module in [('baseline',old),('optimized',new)]:
 if name=='baseline' and a.baseline_summary:continue
 root=a.output/name;(root/'control').mkdir(parents=True);shutil.copyfile(src,root/'control/state.json');store=module.CachedStore(root,module.EncoderCache());timing={}
 t=time.perf_counter();value=store.load();timing['cold_load']=time.perf_counter()-t;hashes=[]
 t=time.perf_counter()
 for _ in range(3):hashes.append(store.encoder.digest(value))
 timing['three_canonical_hashes']=time.perf_counter()-t
 t=time.perf_counter();store.encoder.validate(value);timing['finite_validation']=time.perf_counter()-t
 t=time.perf_counter();store.save(value);timing['atomic_save']=time.perf_counter()-t
 t=time.perf_counter();loaded=store.load();timing['warm_load']=time.perf_counter()-t;assert loaded==value
 with (root/'control/state.json').open('rb') as f:output=hashlib.file_digest(f,'sha256').hexdigest()
 results[name]={'timing':timing,'total_seconds':sum(timing.values()),'canonical_hashes':hashes,'bytes_sha256':output,'encoding_hits':store.encoder.hits,'encoding_misses':store.encoder.misses,'encoding_cache_bytes':store.encoder.size}
 print(name,json.dumps(results[name]),flush=True);del loaded,value,store;gc.collect()
assert results['baseline']['canonical_hashes']==results['optimized']['canonical_hashes'];assert results['baseline']['bytes_sha256']==results['optimized']['bytes_sha256']==original_hash
results.update(passed=True,source=str(src),source_bytes=src.stat().st_size,byte_equivalent=True,model_calls=0,source_unchanged=hashlib.sha256(src.read_bytes()).hexdigest()==original_hash,speedup=results['baseline']['total_seconds']/results['optimized']['total_seconds'],not_end_to_end=True)
(a.output/'summary.json').write_text(json.dumps(results,indent=2)+'\n');print('passed speedup',results['speedup'],flush=True)
