"""Reuse original, single-use v131 scoring identities under the recovery grant.

The allocation lock, live grader leases and object names are unchanged. This
module grants no extra objects and adopts only the explicitly reserved 9000
claim. It never creates a container itself.
"""
from __future__ import annotations

from pathlib import Path

from . import software_benchmark_scope_v132 as scope
from .software_benchmark_candidates_v054 import checked, reference

HANDOFF = scope.ROOT/'runs/software-benchmark-v132/parent-handoff-r1/score-9000-reserved.json'
BLOCKED_TASK = 'psf__requests-1766'


def validate_handoff_claim():
    receipt = scope.load(reference(HANDOFF))
    intent = scope.load(receipt['intent'])
    ref = receipt['claim']
    value = scope.load(ref)
    directory = scope.BATCH_ROOT/'resource-claims'
    plan_ref = reference(scope.PLAN_FILE)
    spec = scope.load(plan_ref)['resources']['score-9000']
    if (receipt.get('original_parent_preserved_by_real_pending_grading_reservation') is not True
            or intent.get('resource_key') != 'score-9000' or intent.get('grading_lane') != 0
            or intent.get('user_grant') != reference(scope.USER_GRANT_FILE)
            or intent.get('original_plan') != plan_ref
            or intent.get('original_result') != reference(scope.BATCH_ROOT/'episodes/9000/result.json')
            or intent.get('new_containers') != 0 or intent.get('new_model_calls') != 0
            or Path(ref['path']).resolve() != directory/'score-9000.json'
            or value.get('version') != scope.prior.VERSION or value.get('key') != 'score-9000'
            or value.get('plan') != plan_ref or value.get('spec') != spec
            or value.get('lane') != 0 or value.get('lease') != str(directory/'active-grader-0.json')
            or value.get('authorization') != reference(scope.prior.AUTH_FILE)
            or (directory/'score-9000.released.json').exists()
            or not (directory/'active-grader-0.json').is_file()
            or (directory/'active-grader-0.json').read_bytes() != checked(ref).read_bytes()):
        raise ValueError('The exact original pending scoring handoff is absent or changed')
    for root in (scope.prior.GRADING_ROOT, scope.GRADING_ROOT):
        folder = root/'score-9000'
        if any((folder/name).exists() for name in ('started.json', 'completion.json', 'quiescence.json')):
            raise ValueError('A previously entered scorer cannot adopt the pending claim')
    return ref


def policy_view(watchdog_guard=None):
    def guard(operation='v066.run', **identity):
        if watchdog_guard is not None:
            watchdog_guard(operation, **identity)
        return scope.require_grading_allowed(operation, **identity)

    policy = scope.dispatch_view(guard)
    # Original object identity/version is retained, including the pre-handoff
    # claim. New authorization is still checked and recorded by the new guard.
    namespace = policy.claim_resource.__globals__
    namespace['VERSION'] = scope.prior.VERSION
    policy.VERSION = scope.prior.VERSION
    original_claim = policy.claim_resource

    def claim_resource(key, *, lane=None):
        plan = scope.load(reference(scope.PLAN_FILE))
        spec = plan['resources'].get(key, {})
        if (spec.get('role') not in {'score', 'delivery_score'}
                or spec.get('instance_id') == BLOCKED_TASK):
            raise PermissionError('Recovery scoring cannot create controls or use the unqualified environment')
        guard('v066.delivery.score' if spec['role'] == 'delivery_score' else 'v066.score',
              slot_id=spec['slot_id'], instance_id=spec['instance_id'])
        if key == 'score-9000':
            if lane not in (None, 0):
                raise ValueError('The pending original claim owns lane zero')
            return validate_handoff_claim()
        if lane is not None and (type(lane) is not int or lane not in range(scope.MAX_GRADERS)):
            raise ValueError('Only the two original grading lanes exist')
        for selected in range(scope.MAX_GRADERS) if lane is None else (lane,):
            try:
                return original_claim(key, lane=selected)
            except policy.ResourceBusy:
                continue
        raise policy.ResourceBusy('Both shared original grader lanes are occupied')

    policy.claim_resource = claim_resource
    # release_resource retains the exact original VERSION through the same
    # actual function namespace; another job's active lease is never removed.
    return policy
