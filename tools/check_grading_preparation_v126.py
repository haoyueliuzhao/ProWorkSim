"""Real fixed-interpreter local grading preparation, with execution forbidden."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
attempts = []


def deny(event, args):
    if (event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto', 'socket.bind',
                  'subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'}):
        attempts.append(event)
        raise RuntimeError('No network, Docker socket, or subprocess in local qualification preparation')


sys.addaudithook(deny)


def main():
    from proworksim import software_benchmark_grading_v126 as grading
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    authority_calls = []

    def no_execution_authority(*args, **kwargs):
        authority_calls.append(str(args[0] if args else kwargs))
        raise RuntimeError('Pure preparation cannot obtain execution authority')

    grading.scope.require_allowed = no_execution_authority
    grading.scope.require_grading_allowed = no_execution_authority
    result = grading.prepare_environment_qualifications_local()
    assert len(result['qualifications']) == 2 and result['controls'] == []
    assert set(result['qualifications']) == set(grading.scope.load(reference(grading.scope.PLAN_FILE))['environments'])
    assert set(result['reuse_failures']) == grading.FRESH_CONTROL_TASKS
    manifest_ref = reference(grading.scope.COORDINATOR_ROOT/'scorer-manifest.json')
    manifest = grading.scope.load(manifest_ref)
    assert manifest['old_model_attempts_replayed_in_place'] is False
    assert manifest['independent_new_REF_attempts_explicitly_authorized'] is True
    assert manifest['new_REF_independent_generation_candidates_only'] is True
    assert manifest['new_PROJECT_generation_candidates_only'] is False
    assert manifest['selective_reset_tasks'] == sorted(grading.reset_binding.reset.TASKS)
    assert not attempts and not authority_calls
    verification = grading.verify_prepared_identity()
    assert verification['passed'] and verification['artifacts_created_or_modified'] == 0
    original_scorer = grading.scorer
    def stale_scoring(*args, **kwargs):
        value = original_scorer(*args, **kwargs)
        prior = value.environment.offline.environment_manifest
        def changed():
            manifest = prior()
            return {**manifest, 'dispatch_guard': {**manifest['dispatch_guard'], 'sha256': '0'*64}}
        value.environment.offline.environment_manifest = changed
        return value
    grading.scorer = stale_scoring
    try:
        try:
            grading.verify_prepared_identity()
        except ValueError as error:
            assert 'Stale prepared identity before execution' in str(error) and 'dispatch_guard' in str(error)
        else:
            raise AssertionError('The old scope-digest drift must fail before execution')
    finally:
        grading.scorer = original_scorer
    output = grading.scope.ROOT/'artifacts/software-benchmark-v126/grading-transport-control-r1/preparation.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    write_new(output, {'version': 'v126-real-cold-local-grading-preparation-control-r1', 'passed': True,
        'source': reference(__file__), 'scorer_source': reference(grading.__file__),
        'manifest': manifest_ref,
        'qualification_decisions': reference(grading.scope.COORDINATOR_ROOT/'qualification-reuse-decisions.json'),
        'reused_unchanged_environments': sorted(result['qualifications']),
        'prepared_fresh_control_requests': result['controls'], 'fresh_controls_executed': 0,
        'forbidden_operation_attempts': attempts, 'execution_authority_calls': authority_calls,
        'Docker_operations': 0, 'model_calls': 0, 'live_network_connections': 0,
        'live_gold_empty_qualification_complete': False, 'fixed_python': sys.version,
        'ordinary_host_process_only': True, 'final_readonly_identity_verification': verification,
        'same_source_digest_drift_rejected_before_execution': True})
    print(json.dumps({'passed': True, 'reused_environments': 2, 'fresh_control_requests': 0,
                      'controls_executed': 0, 'summary': str(Path(output))}))


if __name__ == '__main__':
    main()
