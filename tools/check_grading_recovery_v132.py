#!/usr/bin/env python3
"""One real closed-candidate/claim binding control, with no runtime resources."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import socket
import sys

for key, value in {'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'OPENHANDS_SUPPRESS_BANNER': '1',
                   'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}.items():
    os.environ[key] = value
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
original_socket = socket.socket


class LocalSocket(original_socket):
    def __init__(self, family=socket.AF_INET, *args, **kwargs):
        if family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('CPU grading control forbids networking')
        super().__init__(family, *args, **kwargs)


socket.socket = LocalSocket

from proworksim import software_benchmark_candidate_recovery_v132 as recovery  # noqa: E402
from proworksim import software_benchmark_grading_recovery_v132 as grading  # noqa: E402
from proworksim import software_benchmark_scoring_registry_v132 as registry  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402


def main():
    scope = grading.scope
    output = ROOT/'artifacts/software-benchmark-v132/grading-recovery-controls-r1'
    output.mkdir(parents=True, exist_ok=True)
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.load(plan_ref)
    row = next(row for row in plan['rows'] if row['slot_index'] == 9000)
    original_ref = reference(scope.BATCH_ROOT/'episodes/9000/result.json')
    target = recovery.DEFAULT_OUTPUT/'9000'
    if (target/'result.json').exists():
        result_ref = reference(target/'result.json')
        recovery.validate_recovered_result(result_ref, original_plan_ref=plan_ref)
    else:
        result_ref = recovery.recover_closed_candidate(row, original_ref, target, original_plan_ref=plan_ref)
    engine = grading.factory()
    request_ref = engine.prepare_score(result_ref)
    request = scope.load(request_ref)
    claim_ref = registry.validate_handoff_claim()
    claim = scope.load(claim_ref)
    # Run the actual full request validator without pretending this CPU process
    # has entered the new runtime grant/cgroup. No claim or container is created.
    policy = registry.policy_view()
    policy.require_v066_allowed = lambda *_a, **_k: {'CPU_control_only': True}
    current = grading.scorer(policy)
    execution = {**request, 'prepared_request': request_ref, 'capacity_claim': claim_ref,
                 'cpuset_cpus': policy.cpu_set('grader', claim['lane'])}
    planned, resource, config = current.validate_request(execution)
    assert planned == plan and resource == plan['resources']['score-9000']
    assert current.validate_capacity_claim(execution) == claim
    assert current.diagnostics.make_repaired_run_instance is grading.prior.previous.original.diagnostics.make_repaired_run_instance
    assert current._v132_reset_scorer._generation_result is grading._generation_result
    assert current._v132_reset_scorer.validate_qualification is grading.validate_qualification
    assert current._v132_reset_scorer._planned is current._planned
    assert current.Containers.create.__globals__['aggregate_parent'].SLICE == scope.CONTAINER_PARENT
    rejected = []
    for label, mutated in [('wrong_group', {**request, 'group_id': 'REVIEW'}),
                           ('wrong_lock', {**request, 'candidate_lock': original_ref})]:
        try:
            _, candidate_resource, candidate_config = current._planned(mutated)
            current.validate_candidate_request(mutated, candidate_resource, candidate_config, plan)
        except (ValueError, KeyError, OSError):
            rejected.append(label)
        else:
            raise AssertionError('Foreign candidate accepted: '+label)
    blocked_config = copy.deepcopy(config)
    blocked_config['instance_id'] = registry.BLOCKED_TASK
    try:
        grading.validate_qualification(request['qualification'], blocked_config, plan_ref)
    except ValueError:
        rejected.append('unqualified_1766')
    else:
        raise AssertionError('Unqualified environment accepted')
    summary = {'version': 'v132-recovered-9000-actual-scoring-bindings-control-r1', 'passed': True,
        'sources': [reference(grading.__file__), reference(registry.__file__), reference(recovery.__file__)],
        'original_result': original_ref, 'recovered_result': result_ref, 'prepared_request': request_ref,
        'existing_handoff_claim': claim_ref, 'claim_adopted_or_mutated': False,
        'actual_original_validate_request_executed': True,
        'actual_original_controller_archive_members_verified': True,
        'original_concrete_non_reset_evaluator_retained': True,
        'reset_actual_namespace_uses_recovery_validators': True,
        'negative_cases_rejected': rejected,
        'runtime_authorization_bypassed_only_in_this_CPU_control': True,
        'new_model_calls': 0, 'Docker_operations': 0, 'network_connections': 0,
        'new_claims': 0, 'released_claims': 0}
    print(json.dumps(write_new(output/'summary.json', summary), ensure_ascii=False))


if __name__ == '__main__':
    main()
