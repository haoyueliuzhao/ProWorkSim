"""Wait for the previous owner to close, then launch the already-approved batch once.

This ordinary-user preparation process is not an API owner. While waiting it
only reads existing completion files, and never cancels or changes the old run.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time

from proworksim import software_benchmark_scope_v121 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_host_api_v121 import budget_status
from proworksim.software_benchmark_prior_completion_v121 import (
    PriorStageIncomplete, inspect_prior_completion, prepare_prior_completion,
)
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment
from proworksim.storage import atomic_write, json_bytes
from launch_project_recovery_v121 import launch
from seal_project_recovery_v121 import seal

STATUS = scope.BATCH_ROOT/'authorized-start-wait.json'
INTENT = scope.BATCH_ROOT/'authorized-start-intent.json'
RESULT = scope.BATCH_ROOT/'authorized-start-result.json'


def service_inactive():
    query = subprocess.run(['systemctl', '--user', 'show', scope.API_UNIT,
        '--property=ActiveState,MainPID', '--no-pager'], env=user_manager_environment(),
        capture_output=True, text=True, timeout=20, check=False)
    state = dict(line.split('=', 1) for line in query.stdout.splitlines() if '=' in line)
    return query.returncode == 0 and state.get('ActiveState') == 'inactive' and state.get('MainPID') == '0'


def run(wait_seconds):
    if type(wait_seconds) is not int or not 1 <= wait_seconds <= 21600:
        raise ValueError('Waiting must be bounded to at most six hours')
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only the ordinary project user may run this launcher')
    grant = scope.load(reference(scope.USER_GRANT_FILE))
    if (grant.get('status') != 'approved' or grant.get('explicit_user_reply') != '授权27题独立恢复'
            or grant.get('proposal') != reference(scope.USER_PROPOSAL_FILE)):
        raise PermissionError('The explicit27-task grant is required before waiting')
    if INTENT.exists() or RESULT.exists():
        raise PermissionError('Do not automatically repeat a consumed waiting-launch identity')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (16*1024**3, 16*1024**3))
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    os.nice(19)
    write_new(INTENT, {'user_grant': reference(scope.USER_GRANT_FILE),
        'source': reference(__file__), 'pid': os.getpid(), 'created_unix': time.time(),
        'maximum_wait_seconds': wait_seconds, 'poll_seconds': 30,
        'API_owner': False, 'host_configuration_changes': 0})
    deadline = time.monotonic()+wait_seconds
    try:
        while True:
            complete = False
            try:
                inspect_prior_completion()
                complete = service_inactive()
                reason = 'Previous user service is still returning' if not complete else None
            except PriorStageIncomplete as error:
                reason = str(error)
            atomic_write(STATUS, json_bytes({'unix': time.time(), 'pid': os.getpid(),
                'phase': 'ready_to_seal' if complete else 'waiting_for_prior_cleanup',
                'reason': reason, 'API_owner': False, 'resources_created': 0}))
            if complete:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Prior stage did not fully close within the bounded waiting window')
            time.sleep(min(30, max(0, deadline-time.monotonic())))
        proof = prepare_prior_completion()
        cash = budget_status()
        if cash.get('inflight_count') != 0 or cash.get('state') != 'ready':
            raise RuntimeError('Final prior cash state does not admit this authorized new stage: '+str(cash))
        scope.retain(scope.BUDGET_BASELINE_FILE, {'version': scope.VERSION,
            'recorded_unix': time.time(), 'prior_completion': proof, 'cash': cash,
            'additional_cash': 0, 'old_uncertain_reservations_retained': True})
        sealed = seal()
        proposal = scope.load(sealed['proposal'])
        authorization = {**proposal, 'status': 'approved', 'runtime_authorized': True,
            'proposal': sealed['proposal'], 'explicit_user_reply': grant['explicit_user_reply'],
            'approval_basis': 'Previously received exact independent-recovery user grant',
            'approved_unix': time.time()}
        write_new(scope.AUTH_FILE, authorization)
        result = launch()
        receipt = {'status': 'launched', 'unix': time.time(), 'prior_completion': proof,
                   'authorization': reference(scope.AUTH_FILE), 'launch': result}
        write_new(RESULT, receipt)
        atomic_write(STATUS, json_bytes({'phase': 'launched', 'unix': time.time(),
                                       'result': reference(RESULT)}))
        return receipt
    except Exception as error:
        failure = {'status': 'review_required', 'unix': time.time(),
                   'error': {'type': type(error).__name__, 'message': str(error)},
                   'automatic_retry': False}
        write_new(RESULT, failure)
        atomic_write(STATUS, json_bytes(failure))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-approved', action='store_true', required=True)
    parser.add_argument('--maximum-wait-seconds', type=int, default=21600)
    args = parser.parse_args()
    if not 1 <= args.maximum_wait_seconds <= 21600:
        parser.error('Waiting must be bounded to at most six hours')
    print(json.dumps(run(args.maximum_wait_seconds), ensure_ascii=False))
    sys.stdout.flush()
