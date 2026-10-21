"""Check only the new r6 integration links; frozen hashes were checked by prepare."""
import json
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_episode_v054 import DEFAULT_CLAIMS
from proworksim.software_benchmark_gpu_lease_v054 import ROOT as LEASE_ROOT
from proworksim.software_benchmark_service_factory_v054 import condition_reference
from proworksim.software_benchmark_resident_pool_v054 import KERNEL_POLICY_VERSION

base = Path('/data0/zhuxinrui/projects/ProWorkSim')
k = base / 'runs/software-benchmark-v054/kernel-optimization-r1'
output = k / 'deployment-r6'
def read(path):
    return json.loads(Path(path).read_bytes())
d = read(output / 'deployment.json')
sr = Path(d['source_root'])
b = read(d['bindings']['path'])
old = read(d['original_bindings']['path'])
spec = read(d['spec']['path'])
p = read(spec['previous_failed_preparation']['path'])
assert d['kernel_plan']['sha256'] == 'e94c6e1e02b9ddca95d5814401afd4b21b2fe40198018d4efdc20f4c33155e0d'
assert p['preparation_audit']['sha256'] == 'aa674c80f5b6bf4456063df690c4239076a1734b4ffe2f53ddf006a5067abf8e'
assert DEFAULT_CLAIMS == base / 'runs/software-benchmark-v054/episode-claims'
assert LEASE_ROOT == base
changed = {'source_manifest', 'conditions', 'resident_pool_policy', 'frozen_files'}
for key, value in old.items():
    if key not in changed:
        assert b[key] == value, key
for arm in ('REF', 'MATCH', 'PROJECT'):
    assert condition_reference(arm) == b['conditions'][arm]
    condition = read(b['conditions'][arm]['path'])
    previous = read(old['conditions'][arm]['path'])
    for key, value in previous.items():
        if key != 'source_manifest':
            assert condition[key] == value, (arm, key)
manifest = read(d['source_manifest']['path'])
paths = {x['path'] for x in manifest['files']}
for relative in ('tools/kernel_queue_bridge_v054.py', 'tools/run_benchmark_controller_v054.py',
                 'tools/prepare_kernel_deployment_v054.py', 'tools/guard_kernel_owner_v054.py'):
    assert str(sr / relative) in paths, relative
runner = (sr / 'src/proworksim/software_benchmark_runner_v054.py').read_text()
assert str(sr / 'tools/run_benchmark_controller_v054.py') in runner
assert 'ROOT / "tools/run_benchmark_controller_v054.py"' not in runner
pool = (sr / 'src/proworksim/software_benchmark_resident_pool_v054.py').read_text()
assert KERNEL_POLICY_VERSION == 'v054-resident-pool-policy-v5-g6-fp32-distribution'
assert 'qualifier.get("version") != "v054-kernel-model-diagnostic-r2"' in pool
assert 'qualifier.get("original_gate_is_diagnostic") is not True' in pool
assert spec['kernel_runtime_revision'] == b['numerical_runtime_revision'] == 'FP32-recurrent-distribution-v2'
assert p['version'] == 'v054-kernel-previous-failed-preparation-r3'
assert p['prior_completed_generation_requests'] == 2 and p['prior_known_actual_tokens'] == 384
assert p['all_prior_completed_generation_requests'] == 6 and p['all_prior_known_actual_tokens'] == 1920
assert p['original_failure_reclassified_as_pass'] is False
assert p['cumulative_preparation_generation_upper_bound'] == 97792
bound = {x['reference']['path']: x['reference'] for x in b['frozen_files']}
dependency = read(spec['dependencies_manifest']['path'])
for item in dependency['files']:
    assert bound[item['path']] == {key: item[key] for key in ('path', 'sha256', 'bytes')}
for key in ('failure', 'preparation_audit', 'preparation_closure', 'launcher', 'preloaded', 'unit_evidence'):
    assert bound[p[key]['path']] == p[key]
assert not Path(spec['root']).exists()
result = dict(version='v054-distribution-v2-deployment-wiring-control-r1', passed=True,
    deployment=reference(output / 'deployment.json'),
    metadata_control=reference(Path('/tmp/v054-kernel-rollout-r1/distribution-metadata-control-r1.json')),
    exact_plan_and_r5_audit_bound=True, common_bindings_and_conditions_preserved=True,
    shared_claims_and_leases_original=True, new_controller_and_bridge_source_bound=True,
    distribution_v2_static_registration_bound=True, previous_r5_failure_preserved=True,
    dependency_small_files_bound=len(dependency['files']), preparation_evidence_bound=True,
    source_and_deployment_built_once=True, model_loads=0, GPU_operations=0,
    model_requests=0, services_launched=0)
print(json.dumps(write_new(output / 'cpu-wiring-control.json', result)))
