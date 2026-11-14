"""One explicitly authorized independent empty retry; reuse strictly valid gold."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.pop('PWS_V20323_PREPARATION_GRADING',None)
os.environ.pop('PWS_V20323_GRADING_REVISION_R2',None)
from proworksim import software_benchmark_grading_v203_2_3_r3 as grading
from proworksim import software_benchmark_preparation_grading_v203_2_3_r3 as guard
from proworksim import software_benchmark_requests_recovery_v203_2_3_r3 as recovery
from proworksim.software_benchmark_candidates_v054 import reference

ROOT=grading.scope.ROOT
RESULT=recovery.OUT/'result.json'


def seal():
    grading.host(guard.dispatch_view(),grading.scorer(guard.dispatch_view()))
    paths={Path(__file__).resolve(),ROOT/'tools/run_offline_scorer_v096.py',
           ROOT/'tools/run_offline_scorer_v058.py',ROOT/'tools/run_capability_grading_v066.py'}
    for module in list(sys.modules.values()):
        source=getattr(module,'__file__',None)
        if source:
            path=Path(source).resolve()
            if path.suffix=='.py' and path.is_relative_to(ROOT/'src'):paths.add(path)
    sources=grading.scope.retain(guard.AUTH_FILE.parent/'sources.json',{
        'version':'v203.2.3-single-empty-recovery-sources-r3',
        'files':[reference(path) for path in sorted(paths)]})
    return grading.scope.retain(guard.AUTH_FILE,{'version':guard.VERSION,'status':'approved',
        'plan':reference(guard.CONTROL_PLAN_FILE),'formal_plan':reference(guard.original.PLAN_FILE),
        'source_index':sources,'API_calls_allowed':0,'resource_keys':sorted(guard.KEYS),'uid':os.getuid(),
        'maximum_containers':1,'maximum_concurrency':1,
        'profile':reference(recovery.environment.RESOLUTION),
        'CA_profile':reference(guard.original.CA_PROFILE_FILE),
        'prior_unknown_reclassified':False,'gold_reexecuted':False,
        'model_attempts_replayed':0,'old_control_identity_reused':False,
        'shared_grader_lane_across_formal_and_control_batches':True,
        'user_authority':'Standing network-recovery queue and explicit current-task approval for one new-identity empty control under the original strict rules'})


def run():
    guard.require_allowed()
    if RESULT.exists():raise PermissionError('This recovery terminal result is immutable; no automatic retry')
    plan=guard.original.load(reference(guard.original.PLAN_FILE))
    config=guard.original.load(plan['environments'][recovery.TASK]['configuration'])
    gold_ref=guard.original.retain(recovery.OUT/'components/gold.json',recovery.component_document('gold'))
    recovery.validate_component('gold',gold_ref,config)
    owner=grading.Grading(guard.dispatch_view())
    key='control-r3-'+recovery.TASK+'-empty'
    request=reference(guard.GRADING_ROOT/key/'request.json')
    outcome=owner.run_request(request)
    cleanup=owner.trustworthy_cleanup(request)
    qualification=None;problem=None
    try:
        if not cleanup:raise RuntimeError('New empty container cleanup is not established')
        qualification=recovery.qualify()
        recovery.validate_qualification(qualification,config,reference(guard.original.PLAN_FILE))
    except (ValueError,KeyError,OSError,RuntimeError,TypeError) as error:
        problem=type(error).__name__+': '+str(error)
    report={'version':'v203.2.3-strict-single-empty-recovery-result-r3',
        'passed':qualification is not None and problem is None,'qualification':qualification,
        'error':problem,'new_control':request,'outcome':outcome,'cleanup_complete':cleanup,
        'reused_gold_component':gold_ref,'profile':reference(recovery.environment.RESOLUTION),
        'authority':reference(guard.AUTH_FILE),'model_calls':0,'gold_reexecuted':False,
        'previous_unknown_reclassified':False,'transport_gate_changed':False}
    guard.original.retain(RESULT,report)
    print(json.dumps(report),flush=True)
    if problem:raise RuntimeError(problem)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal',action='store_true');parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if args.seal:print(json.dumps({'authority':seal()}),flush=True)
    if args.run:run()
    if not args.seal and not args.run:parser.error('Choose --seal and/or --run')
