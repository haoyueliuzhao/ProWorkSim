"""Run only two newly scoped Requests1724 gold/empty controls, serially."""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import shutil
from proworksim import software_benchmark_scope_v162 as scope
from proworksim import software_benchmark_grading_v162 as grading
from proworksim.software_benchmark_candidates_v054 import reference,write_new


def preflight():
    """Resolve the actual standard request/claim and validate without Docker."""
    scope.require_grading_allowed('v162.run')
    plan=scope.load(reference(scope.COORDINATOR_ROOT/'qualification-preparation.json'))
    worker=grading.factory();policy=scope.dispatch_view(scope.require_grading_allowed)
    output=scope.ARTIFACT_ROOT/'actual-request-preflight-r2';output.mkdir(parents=True,exist_ok=True)
    checks=[]
    for ref in plan['controls']:
        request=scope.load(ref);key=request['resource_key'];folder=Path(request['directory'])
        claim=policy.claim_resource(key,lane=0)
        scope.retain(folder/'capacity-claim.json',{'prepared_request':ref,'claim':claim})
        try:
            execution=worker.scorer.resolve_execution_request(request)
            worker.scorer.validate_request(execution)
            checks.append({'request':ref,'passed':True,'actual_validator':True,'Docker_operations':0})
        finally:
            policy.release_resource(claim,quiescent=True)
            destination=output/key;destination.mkdir(exist_ok=False)
            for path in (folder/'capacity-claim.json',Path(claim['path']),Path(claim['path']).with_name(key+'.released.json')):
                shutil.move(path,destination/('admission.json' if path.name=='capacity-claim.json' else path.name))
    return scope.retain(output/'summary.json',{'version':scope.VERSION,'passed':all(x['passed'] for x in checks),
        'controls':checks,'actual_container_creations':0,'model_API_calls':0,'claims_released':True})


def run():
    scope.require_grading_allowed('v162.run')
    admission=scope.load(reference(scope.ARTIFACT_ROOT/'actual-request-preflight-r2/summary.json'))
    if admission.get('passed') is not True:raise ValueError('Actual cold-scorer request preflight is mandatory')
    plan=scope.load(reference(scope.COORDINATOR_ROOT/'qualification-preparation.json'))
    worker=grading.factory();results=[]
    for ref in plan['controls']:
        completed=worker.run_request(ref)
        quiet=worker.trustworthy_cleanup(ref)
        results.append({'request':ref,'completion':completed,'trustworthy_cleanup':quiet})
        if quiet is not True:break
    try:
        qualification=worker.qualify('psf__requests-1724')
        outcome={'status':'qualified','qualification':qualification}
    except Exception as error:
        outcome={'status':'environment_unknown','error':{'type':type(error).__name__,'message':str(error)}}
    return scope.retain(scope.COORDINATOR_ROOT/'environment-result.json',{
        'version':scope.VERSION,'instance_id':'psf__requests-1724','controls':results,
        'qualification':outcome,'model_calls':0,'maximum_new_containers':2,'maximum_concurrent_graders':1,
        'shared_host_configuration_changes':0,'v157_source_or_queue_modified':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--preflight',action='store_true');group.add_argument('--execute',action='store_true')
    args=parser.parse_args();print(json.dumps(preflight() if args.preflight else run(),ensure_ascii=False))
