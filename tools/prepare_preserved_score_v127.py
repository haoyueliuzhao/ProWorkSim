"""Prepare one unchanged Requests1921 candidate rescore, without execution."""
from __future__ import annotations

import copy
import json

from proworksim import software_benchmark_scope_v127 as scope
from proworksim.software_benchmark_candidates_v054 import reference


def prepare():
    original_ref = reference(scope.ORIGINAL_REQUEST_FILE)
    request = scope.load(original_ref)
    original_plan = scope.load(request['plan'])
    row = next(item for item in original_plan['rows'] if item['slot_id'] == request['slot_id'])
    folder = scope.ORIGINAL_REQUEST_FILE.parent
    receipt_ref, quiet_ref = reference(folder/'receipt.json'), reference(folder/'quiescence.json')
    receipt, quiet = scope.load(receipt_ref), scope.load(quiet_ref)
    transport = scope.load(receipt['transport_result'])
    report = receipt['official_result'][1][row['instance_id']]
    if (request['resource_key'] != 'score-7239' or row['slot_index'] != 7239
            or row['instance_id'] != 'psf__requests-1921' or row['arm'] != 'REF'
            or receipt.get('status') != 'technical_unknown'
            or report.get('patch_successfully_applied') is not True
            or report.get('infra_failure') is not False
            or report['tests_status']['FAIL_TO_PASS']['failure'] != []
            or len(report['tests_status']['FAIL_TO_PASS']['success']) != 6
            or report['tests_status']['PASS_TO_PASS']['failure'] != [
                'test_requests.py::RequestsTestCase::test_pyopenssl_redirect']
            or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or transport.get('status') != 'network_failed'
            or not any(item.get('outcome') == 'upstream_connect_error'
                       and item.get('bytes_to_upstream') == 0 and item.get('bytes_from_upstream') == 0
                       and item.get('upstream_connected') is False for item in transport.get('connections', []))):
        raise ValueError('Only the preserved candidate with the recorded unconnected upstream failure may be retried')
    release_ref = reference(scope.PRIOR_OWNER_RELEASE_FILE)
    if scope.load(release_ref).get('released') is not True:
        raise ValueError('The original API owner must already be released')
    key = scope.RESOURCE_KEY
    resource = copy.deepcopy(original_plan['resources'][request['resource_key']])
    plan = {'version': scope.VERSION, 'root': str(scope.BATCH_ROOT), 'rows': [copy.deepcopy(row)],
        'generation_rows': [], 'diagnostics': [], 'resources': {key: resource},
        'resource_role_counts': {'score': 1}, 'constraints': scope.CONSTRAINTS,
        'environments': {row['instance_id']: copy.deepcopy(original_plan['environments'][row['instance_id']])},
        'environment_sources': {row['instance_id']: copy.deepcopy(original_plan['environment_sources'][row['instance_id']])},
        'host_cpu_pool': reference(scope.CPU_POOL_FILE), 'prior_plan': request['plan'],
        'original_score_request': original_ref, 'original_score_receipt': receipt_ref,
        'original_score_quiescence': quiet_ref, 'original_transport_failure': receipt['transport_result'],
        'preserved_candidate_lock': request['candidate_lock'],
        'preserved_generation_result': request['generation_result'],
        'prior_v125_owner_release': release_ref,
        'score_request_path': str(scope.GRADING_ROOT/key/'request.json'),
        'new_generation_attempts': 0, 'new_controls': 0, 'new_volumes': 0,
        'maximum_new_score_containers': 1, 'maximum_new_TLS_sessions': 1,
        'candidate_or_original_results_changed': False, 'automatic_retry': False}
    scope.validate_plan(plan)
    plan_ref = scope.retain(scope.PLAN_FILE, plan)
    evidence = {'version': scope.VERSION, 'original_request': original_ref,
        'official_report': receipt_ref, 'transport': receipt['transport_result'],
        'cause': 'The original candidate applied and all F2P passed; one upstream 443 connection timed out before any payload, invalidating the real-network score.',
        'original_candidate_retained': True, 'new_model_calls': 0,
        'new_grading_attempts_prepared': 1, 'new_grading_attempts_executed': 0}
    scope.retain(scope.ROOT/'artifacts/software-benchmark-v127/preparation-r1/cause.json', evidence)
    return plan_ref


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
