"""One offline control of the preserved-candidate rescore's actual bindings."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
attempts = []


def deny(event, _args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto', 'socket.bind',
                 'subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'}:
        attempts.append(event)
        raise RuntimeError('No network, Docker socket, or subprocess in this local control')


sys.addaudithook(deny)


def main():
    from proworksim import software_benchmark_grading_v127 as grading
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    scope = grading.scope
    authority_calls = []

    def forbidden(*args, **kwargs):
        authority_calls.append(str(args[0] if args else kwargs))
        raise RuntimeError('Preparation cannot obtain execution authority')

    scope.require_allowed = scope.require_grading_allowed = forbidden
    prepared = grading.prepare_environment_qualifications_local()
    assert set(prepared['qualifications']) == {scope.TASK}
    assert prepared['controls'] == [] and prepared['reuse_failures'] == {}
    request_ref = grading.prepare_preserved_request()
    request = scope.load(request_ref)
    policy = scope.dispatch_view(forbidden)
    scoring = grading.scorer(policy)
    plan, resource, config = scoring._planned(request)
    lock = scoring.validate_candidate_request(request, resource, config, plan)
    assert lock == scope.load(plan['preserved_candidate_lock'])
    assert request['candidate_lock'] == plan['preserved_candidate_lock']
    assert request['generation_result'] == plan['preserved_generation_result']
    assert request['rescore_of'] == plan['original_score_request']
    assert request['measurement_kind'] == grading.MEASUREMENT
    assert request['cpuset_cpus'] is None
    assert scoring._planned.__globals__ is scoring.validate_request.__globals__ or (
        scoring.validate_request.__globals__['_planned'] is scoring._planned)
    assert scoring.validate_request.__globals__['validate_candidate_request'] is scoring.validate_candidate_request
    # Requests must use the concrete official evaluator with its real cleanup globals.
    concrete = scoring._v118_concrete_score
    assert concrete.__globals__['diagnostics'].make_repaired_run_instance is (
        grading.previous.original.diagnostics.make_repaired_run_instance)
    assert scoring._score.__closure__ is not None
    negatives = []
    for key, value in (
        ('candidate_lock', {**request['candidate_lock'], 'sha256': '0'*64}),
        ('generation_result', {**request['generation_result'], 'sha256': '0'*64}),
        ('configuration', {**request['configuration'], 'sha256': '0'*64}),
        ('resource_key', 'score-7239'),
        ('measurement_kind', 'full_verified_comparison'),
        ('delivery_evidence', {'submitted': True}),
    ):
        changed = copy.deepcopy(request)
        changed[key] = value
        try:
            scoring._planned(changed)
        except (ValueError, PermissionError):
            negatives.append(key)
        else:
            raise AssertionError('Substitution was admitted: '+key)
    command = grading.command(['--request', str(Path(request_ref['path']))])
    assert command[-4:] == ['-m', 'proworksim.software_benchmark_grading_v127',
                           '--request', str(Path(request_ref['path']))]
    verification = grading.verify_prepared_identity()
    assert verification['passed'] and verification['artifacts_created_or_modified'] == 0
    runner = scope.ROOT/'tools/run_preserved_score_v127.py'
    spec = importlib.util.spec_from_file_location('v127_control_runner', runner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.verify_preparation()['passed']
    assert not attempts and not authority_calls
    output = scope.ROOT/'artifacts/software-benchmark-v127/scoring-controls-r1/summary.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    write_new(output, {'version': 'v127-preserved-candidate-offline-control-r1', 'passed': True,
        'source': reference(__file__), 'scorer_source': reference(grading.__file__),
        'scope_source': reference(scope.__file__), 'runner_source': reference(runner),
        'request': request_ref, 'original_request': plan['original_score_request'],
        'preserved_candidate_lock': plan['preserved_candidate_lock'],
        'preserved_generation_result': plan['preserved_generation_result'],
        'original_closed_generation_validator_executed': True,
        'new_scope_candidate_substitution_rejected': negatives,
        'actual_scoring_globals_and_child_module_bound_to_v127': True,
        'Requests_concrete_evaluator_retained': True,
        'completed_v119_environments_reused': sorted(prepared['qualifications']),
        'new_controls': 0, 'new_model_calls': 0, 'Docker_operations': 0,
        'live_network_connections': 0, 'forbidden_operation_attempts': attempts,
        'execution_authority_calls': authority_calls,
        'final_readonly_identity_verification': verification})
    print(json.dumps({'passed': True, 'summary': str(output), 'request': request_ref}))


if __name__ == '__main__':
    main()
