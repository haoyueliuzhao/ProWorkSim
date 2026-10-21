import ast,copy,json,time
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import checked,reference,write_new
from proworksim.software_benchmark_resident_pool_v054 import validate_pool_policy,read_pool
from proworksim.software_benchmark_episode_v054 import DEFAULT_CLAIMS
from proworksim.software_benchmark_gpu_lease_v054 import ROOT as LEASE_ROOT
from proworksim.software_benchmark_service_factory_v054 import condition_reference
from tools.kernel_queue_bridge_v054 import validate
started=time.monotonic()
base=Path('/data0/zhuxinrui/projects/ProWorkSim')
output=base/'runs/software-benchmark-v054/kernel-optimization-r1/deployment-r2'
d=json.loads((output/'deployment.json').read_bytes());sr=Path(d['source_root']);b=json.loads(checked(d['bindings']).read_bytes())
assert validate({'bindings':d['bindings'],'original_bindings':d['original_bindings'],'initial':True}) == b
assert DEFAULT_CLAIMS == base/'runs/software-benchmark-v054/episode-claims'
assert LEASE_ROOT == base
assert read_pool(d['pool_policy'])['active']=={}
for arm in ('REF','MATCH','PROJECT'): assert condition_reference(arm)==b['conditions'][arm]
p=json.loads(checked(d['pool_policy']).read_bytes());bad=copy.deepcopy(p);bad['physical_gpus']=[3]
negative=write_new(output/'rejected-wrong-device-policy.json',bad)
try: validate_pool_policy(negative)
except ValueError: pass
else: raise AssertionError('Other GPU admitted into singleton kernel policy')
manifest=json.loads(checked(d['source_manifest']).read_bytes());paths={x['path'] for x in manifest['files']}
assert str(sr/'tools/kernel_queue_bridge_v054.py') in paths
assert str(sr/'tools/run_benchmark_controller_v054.py') in paths
runner=(sr/'src/proworksim/software_benchmark_runner_v054.py').read_text()
assert str(sr/'tools/run_benchmark_controller_v054.py') in runner
assert 'ROOT / "tools/run_benchmark_controller_v054.py"' not in runner
for path in [*sr.joinpath('src').rglob('*.py'),*sr.joinpath('tools').glob('*v054*.py')]:ast.parse(path.read_bytes())
dependency=json.loads((base/'runs/software-benchmark-v054/kernel-optimization-r1/dependencies/overlay-manifest-r1.json').read_bytes())
bound={x['reference']['path']:x['reference'] for x in b['frozen_files']}
assert len(dependency['files'])==402
for item in dependency['files']: assert bound[item['path']]=={k:item[k] for k in ('path','sha256','bytes')}
result={'version':'v054-kernel-deployment-cpu-control-r1','passed':True,'deployment':reference(output/'deployment.json'),'common_bindings_unchanged':True,'shared_claims_and_leases_original':True,'singleton_wrong_GPU_rejected':True,'new_controller_source_routed':True,'new_bridge_source_frozen':True,'dependency_small_files_bound':402,'copied_python_AST_parse':True,'model_loads':0,'GPU_operations':0,'model_requests':0,'services_launched':0,'elapsed_seconds':time.monotonic()-started}
print(json.dumps(write_new(output/'cpu-control.json',result)))
