"""Seal a host-only handoff while v181's valid in-flight work continues."""
import importlib.util
import json
from pathlib import Path
from proworksim.software_context_continuation_v182 import scope,original_scope,STATE,VERSION,startup_recovery_proof
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_alignment_contract_v181 import VERSION as ALIGNMENT_VERSION


def main():
    if scope.AUTH_FILE.exists():raise ValueError('Do not reseal active handoff')
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    row=next(r for r in plan['rows'] if r['instance_id']==plan['rows'][0]['instance_id'] and r['group_id']=='M3-R')
    proof=startup_recovery_proof(row)
    out=scope.ROOT/'artifacts/software-benchmark-v182/host-continuation-r1'
    evidence=scope.retain(out/'zero-call-proof.json',proof)
    proposal=scope.retain(out/'proposal.json',{'version':VERSION,'same_plan':reference(scope.PLAN_FILE),
        'same_model_runtime':reference(scope.ROOT/'runs/software-benchmark-v181/sdk-bundle-r3/manifest.json'),
        'new_model_attempts_beyond_original_plan':0,'same_cumulative_cash_CNY':250,
        'additional_user_coordinator':scope.API_UNIT,'combined_cpu_upper':48,'combined_memory_GiB_upper':296,
        'shared_generation_pairs':4,'shared_graders':2,'no_old_requests_interrupted':True,
        'standing_nondisruptive_API_Docker_authority':True,'shared_host_changes':0,'zero_call_proof':evidence})
    spec=importlib.util.spec_from_file_location('closure182',scope.ROOT/'tools/seal_role_pilot_v143.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    roots=[p for folder in ('src/proworksim','tools','tests') for p in (scope.ROOT/folder).glob('*v182.py')]
    files=mod.source_closure(roots=roots)
    files.extend([reference(original_scope.SOURCE_FILE),reference(scope.PLAN_FILE),proposal,evidence,
        reference(scope.ROOT/'docs/experiments/software-benchmark-v182-startup-continuation.md')])
    sources=scope.retain(scope.SOURCE_FILE,{'version':VERSION,'files':files,'old_sources_unmodified':True})
    auth=scope.retain(scope.AUTH_FILE,{'version':VERSION,'status':'approved','plan':reference(scope.PLAN_FILE),
        'source_index':sources,'execution_alignment_version':ALIGNMENT_VERSION,'constraints':scope.CONSTRAINTS,
        'cash_cap_CNY':'250.00','coexistence':proposal,'standing_user_request':'按照审计继续实验；非干扰实验API/Docker可使用',
        'shared_host_configuration_changes':0})
    scope.require_allowed();print(json.dumps({'authorization':auth,'source_files':len(files),'zero_model_recovery':row['slot_id']}))


if __name__=='__main__':main()
