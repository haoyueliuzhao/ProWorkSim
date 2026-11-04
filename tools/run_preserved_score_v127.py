"""Verify or score exactly one preserved candidate, without a service or model."""
from __future__ import annotations

import argparse
import json
import signal
import threading
import time

from proworksim import software_benchmark_scope_v127 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

VERSION = 'v127-single-preserved-candidate-scoring-runner-r1'


def verify_preparation():
    from proworksim import software_benchmark_grading_v127 as grading
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    request_ref = reference(plan['score_request_path'])
    request = scope.load(request_ref)
    if (request.get('plan') != reference(scope.PLAN_FILE)
            or request.get('resource_key') != scope.RESOURCE_KEY
            or request.get('measurement_kind') != 'preserved_candidate_rescore'
            or request.get('rescore_of') != plan['original_score_request']
            or request.get('candidate_lock') != plan['preserved_candidate_lock']
            or request.get('generation_result') != plan['preserved_generation_result']
            or request.get('cpuset_cpus') is not None):
        raise ValueError('The new score request changed the preserved candidate or scope')
    identity = grading.verify_prepared_identity()
    if identity.get('passed') is not True:
        raise ValueError('The prepared scoring environment identity has not passed')
    return {'version': VERSION, 'passed': True, 'request': request_ref,
            'identity': identity, 'model_calls': 0, 'Docker_operations': 0}


def run():
    scope.require_grading_allowed('v127.run', instance_id=scope.TASK)
    from proworksim.software_benchmark_rescore_v095 import host_limits
    limits = host_limits(scope.cpu_set('grader'))
    from proworksim import software_benchmark_grading_v127 as grading
    prepared = verify_preparation()
    folder = scope.GRADING_ROOT/scope.RESOURCE_KEY
    if any((folder/name).exists() for name in ('capacity-claim.json', 'started.json', 'quiescence.json')):
        raise ValueError('A consumed scorer identity cannot be automatically replayed')
    scope.API_ROOT.mkdir(parents=True, exist_ok=True)
    write_new(scope.API_ROOT/'execution-started.json', {'version': VERSION,
        'request': prepared['request'], 'started_unix': time.time(), 'host_limits': limits,
        'model_calls': 0, 'new_services': 0})
    stop = threading.Event()
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous:
        signal.signal(sig, lambda *_args: stop.set())
    outcome = failure = None
    try:
        engine = grading.factory(watchdog_guard=lambda *_args, **_identity: None)
        outcome = engine.run_request(prepared['request'], stop_event=stop)
        if engine.trustworthy_cleanup(prepared['request']) is not True:
            raise RuntimeError('The consumed scorer lacks trustworthy cleanup')
        return outcome
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        write_new(scope.API_ROOT/'completion.json', {'version': VERSION,
            'request': prepared['request'], 'finished_unix': time.time(), 'outcome': outcome,
            'failure': failure, 'model_calls': 0, 'automatic_retry': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--verify-preparation', action='store_true')
    actions.add_argument('--execute', action='store_true')
    arguments = parser.parse_args()
    print(json.dumps(verify_preparation() if arguments.verify_preparation else run(), ensure_ascii=False))
