"""Run the two fresh fixed-current-IP controls; zero model calls, no replay."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.pop('PWS_V20323_PREPARATION_GRADING',None)
os.environ['PWS_V20323_GRADING_REVISION_R2']='1'
from proworksim import software_benchmark_grading_v203_2_3_r2 as grading
from proworksim import software_benchmark_preparation_grading_v203_2_3_r2 as guard
from proworksim.software_benchmark_candidates_v054 import reference

ROOT=grading.scope.ROOT
RESULT=grading.scope.ARTIFACT_ROOT/'grading-current-endpoint-controls-r2/result.json'


def seal():
    policy=guard.dispatch_view()
    grading.host(policy,grading.scorer(policy))
    paths={Path(__file__).resolve(),ROOT/'tools/run_offline_scorer_v096.py',
           ROOT/'tools/run_offline_scorer_v058.py',ROOT/'tools/run_capability_grading_v066.py'}
    for module in list(sys.modules.values()):
        source=getattr(module,'__file__',None)
        if source:
            path=Path(source).resolve()
            if path.suffix=='.py' and path.is_relative_to(ROOT/'src'):paths.add(path)
    sources=grading.scope.retain(guard.AUTH_FILE.parent/'sources.json',{
        'version':'v203.2.3-current-endpoint-control-sources-r2',
        'files':[reference(path) for path in sorted(paths)]})
    return grading.scope.retain(guard.AUTH_FILE,{'version':guard.VERSION,'status':'approved',
        'plan':reference(guard.CONTROL_PLAN_FILE),'formal_plan':reference(guard.original.PLAN_FILE),
        'source_index':sources,'API_calls_allowed':0,'resource_keys':sorted(guard.KEYS),'uid':os.getuid(),
        'maximum_containers':2,'maximum_concurrency':1,
        'profile':reference(grading.environment_adapter.RESOLUTION),
        'CA_profile':reference(guard.original.CA_PROFILE_FILE),
        'old_control_identities_not_reused':True,'shared_single_grader_lane':True,
        'formal_authority_may_coexist_but_no_formal_slots_admitted':True,
        'user_authority':'Current task explicitly authorizes two new controls after the failed old endpoint and successful bounded current probe'})


def run():
    guard.require_allowed()
    if RESULT.exists():raise PermissionError('Never replay entered controls or overwrite terminal qualification')
    owner=grading.Grading(guard.dispatch_view())
    outcomes=[];qualification=None;problem=None;cleanup_complete=True
    try:
        for kind in ('gold','empty'):
            key='control-r2-psf__requests-1766-'+kind
            ref=reference(guard.GRADING_ROOT/key/'request.json')
            if grading.scope.load(ref)['resource_key']!=key:raise ValueError('Foreign prepared control')
            outcome=owner.run_request(ref)
            outcomes.append(outcome)
            if not owner.trustworthy_cleanup(ref):
                cleanup_complete=False
                raise RuntimeError('Owned control cleanup is not established; no further control may start')
            receipt=grading.scope.load(reference(guard.GRADING_ROOT/key/'receipt.json'))
            print(json.dumps({'control':key,'status':receipt.get('status'),'resolved':receipt.get('resolved'),
                              'cleanup_complete':True}),flush=True)
            if receipt.get('status')!='official_report':
                raise RuntimeError('Current endpoint control is technical_unknown; do not spend a second identical diagnostic')
            if kind=='gold' and receipt.get('resolved') is not True:
                raise RuntimeError('Official gold did not qualify the environment; empty is unnecessary')
        qualification=owner.qualify('psf__requests-1766')
    except (ValueError,KeyError,OSError,RuntimeError,PermissionError,TypeError) as error:
        problem=type(error).__name__+': '+str(error)
    report={'version':'v203.2.3-current-endpoint-gold-empty-result-r2',
        'passed':qualification is not None,'qualification':qualification,'error':problem,
        'outcomes':outcomes,'cleanup_complete':cleanup_complete,'model_calls':0,
        'profile':reference(grading.environment_adapter.RESOLUTION),
        'authority':reference(guard.AUTH_FILE),'old_scoring_or_model_attempts_replayed':0}
    grading.scope.retain(RESULT,report)
    print(json.dumps(report),flush=True)
    if problem:raise RuntimeError(problem)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal',action='store_true');parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if args.seal:print(json.dumps({'authority':seal()}),flush=True)
    if args.run:run()
    if not args.seal and not args.run:parser.error('Choose --seal and/or --run')
