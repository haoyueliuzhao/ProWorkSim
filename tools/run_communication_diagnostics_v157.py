"""Three serial real SDK/actor diagnostics, separately authorized for zero model calls."""
from __future__ import annotations
import argparse
import json
import os
import resource
from proworksim import software_benchmark_scope_v157 as scope
from proworksim import software_benchmark_alignment_contract_v157 as alignment
from proworksim.software_benchmark_episode_v157 import build_episode
from proworksim.software_benchmark_diagnostic_receipts_v143 import inspect_diagnostic,DiagnosticFailure
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_host_memory_v132 import HostMemoryGate

def run():
    scope.require_diagnostic_allowed()
    os.sched_setaffinity(0,set(scope.host_cpu_pool()[:4]))
    resource.setrlimit(resource.RLIMIT_AS,(16*scope.GIB,16*scope.GIB))
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    memory=HostMemoryGate(maximum=1)
    implementation=build_episode(scope=scope,guard=scope.require_diagnostic_allowed,host_memory=memory)
    records=[]
    try:
        for spec in plan['diagnostics']:
            row=next(r for r in plan['rows'] if r['slot_id']==spec['slot_id'])
            ref=implementation._run(row,{},diagnostic=True,diagnostic_index=spec['index'])
            try:
                record=inspect_diagnostic(ref,spec,load=scope.load,
                    condition=lambda _org:alignment.condition(spec['group_id']),shared_strategy=alignment.shared_strategy,
                    controller_memory_bytes=scope.CONSTRAINTS['controller_memory_bytes'],gib=scope.GIB)
            except DiagnosticFailure as error:
                scope.retain(scope.API_ROOT/'diagnostic-failures'/(str(spec['index'])+'.json'),error.report)
                raise
            records.append(record)
    finally:memory.close()
    return scope.retain(scope.PREPARATION_QUALIFICATION_FILE,{'version':scope.VERSION,'passed':True,
        'diagnostics':records,'API_calls':0,'all_planned_groups_checked':True,
        'formal_budget_binding_disabled_only_for_explicit_zero_model_diagnostic':True,
        'actual_host_cpu_affinity':sorted(os.sched_getaffinity(0)),
        'host_address_space_limit_bytes':16*scope.GIB})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true',required=True);p.parse_args()
    print(json.dumps(run(),ensure_ascii=False))
