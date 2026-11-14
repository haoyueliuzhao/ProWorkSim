"""Seal and run exactly two new zero-model Requests grading controls."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ['PWS_V20323_PREPARATION_GRADING'] = '1'
from proworksim import software_benchmark_grading_v203_2_3 as grading
from proworksim import software_benchmark_preparation_grading_v203_2_3 as guard
from proworksim.software_benchmark_candidates_v054 import reference


def seal():
    if os.getuid() == 0 or grading.scope.AUTH_FILE != guard.AUTH_FILE:
        raise PermissionError('Only the independent ordinary-user preparation scope is allowed')
    # Enumerate actually imported project sources plus the cold child launcher.
    # Parallel SDK/public-control source edits cannot mutate this grading seal.
    policy = grading.scope.dispatch_view()
    grading.host(policy, grading.scorer(policy))
    paths = {Path(__file__).resolve(), ROOT/'tools/run_offline_scorer_v096.py',
             ROOT/'tools/run_capability_grading_v066.py'}
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path:
            path = Path(path).resolve()
            if path.suffix == '.py' and path.is_relative_to(ROOT/'src'):
                paths.add(path)
    folder = guard.AUTH_FILE.parent
    sources = grading.scope.retain(folder/'sources.json', {
        'version':'v203.2.3-two-control-preparation-sources-r1',
        'files':[reference(path) for path in sorted(paths)]})
    return grading.scope.retain(guard.AUTH_FILE, {
        'version':'v203.2.3-two-control-preparation-authority-r1', 'status':'approved',
        'plan':reference(grading.scope.PLAN_FILE), 'source_index':sources,
        'API_calls_allowed':0, 'resource_keys':sorted(guard.KEYS), 'uid':os.getuid(),
        'maximum_containers':2, 'maximum_concurrency':1,
        'network_scope':'Requests1766 scoring only; frozen numeric httpbin TCP80/443; no solver access',
        'scoring_CA_profile':reference(grading.scope.CA_PROFILE_FILE),
        'user_authority':'Current task explicitly authorizes new gold/empty controls and existing scoring-side CA fix',
        'old_scope_or_ledger_reopened':False})


def run():
    guard.require_allowed()
    policy = grading.scope.dispatch_view()
    owner = grading.Grading(policy)
    decisions = grading.scope.load(reference(grading.scope.COORDINATOR_ROOT/'qualification-reuse-decisions.json'))
    requests = decisions['controls']
    if {grading.scope.load(ref)['resource_key'] for ref in requests} != guard.KEYS:
        raise ValueError('Only the exact predeclared Requests gold/empty pair may run')
    outcomes = []
    for ref in requests:
        outcome = owner.run_request(ref)
        outcomes.append(outcome)
        print(json.dumps({'control_completed':grading.scope.load(ref)['resource_key'],
                          'outcome':outcome}),flush=True)
        if not owner.trustworthy_cleanup(ref):
            raise RuntimeError('Owned grader cleanup is unproven; do not start another control')
    qualification = None
    error = None
    try:
        qualification = owner.qualify('psf__requests-1766')
    except (ValueError, KeyError, OSError, TypeError) as problem:
        error = type(problem).__name__ + ': ' + str(problem)
    report = {'version':'v203.2.3-two-control-pregrading-result-r1',
              'passed':qualification is not None, 'qualification':qualification,
              'error':error, 'outcomes':outcomes, 'model_calls':0,
              'requests':requests, 'authority':reference(guard.AUTH_FILE)}
    grading.scope.retain(guard.AUTH_FILE.parent/'result.json',report)
    print(json.dumps(report),flush=True)
    if error:
        raise RuntimeError(error)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal',action='store_true')
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if args.seal:print(json.dumps({'authority':seal()}),flush=True)
    if args.run:run()
    if not args.seal and not args.run:parser.error('Choose --seal and/or --run')
