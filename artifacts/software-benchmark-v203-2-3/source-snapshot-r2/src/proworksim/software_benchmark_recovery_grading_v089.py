"""Original official scorer with separately authorized recovery identities."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType

from . import software_benchmark_scorer_v066 as original_scorer
from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_api_scope_v089 as scope
from . import software_benchmark_recovery_bindings_v089 as bindings
from .software_benchmark_candidates_v054 import reference, write_new
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v089-original-official-scoring-for-fresh-budget-recovery-r1'


def validate_qualification(ref, config, plan_ref):
    if plan_ref != reference(scope.PLAN_FILE):
        raise ValueError('Only this exact recovery plan may reuse its original environment')
    plan = scope.load(plan_ref)
    row = next((r for r in plan['rows'] if r['slot_id'] == config.get('slot_id')), None)
    if row is None or scope.load(row['configuration']) != config:
        raise ValueError('Recovery configuration differs from the planned candidate')
    original_plan = scope.load(plan['original_plan'])
    source = next(r for r in original_plan['rows'] if r['slot_id'] == row['original_slot_id'])
    source_config = scope.load(source['configuration'])
    scope.validate_mapping(row, source, config, source_config)
    qualification = scope.load(reference(scope.INVENTORY_FILE))['qualifications'][row['instance_id']]
    if qualification.get('status') != 'qualified' or ref != qualification.get('qualification'):
        raise ValueError('The selected environment has no original qualified control identity')
    # All original control/CA/baseline checks run against their original plan;
    # nothing is relabelled as a newly run control.
    return original_scorer.validate_qualification(ref, source_config, plan['original_plan'])


def scorer(policy):
    namespace = clone_namespace(original_scorer, policy=policy)
    namespace['validate_qualification'] = validate_qualification
    inherited_manifest = namespace['installation_manifest']

    def installation_manifest():
        # Manager capacity policy and bounded score child have different
        # wrappers, but the same sealed recovery-identity authority.
        return {**inherited_manifest(), 'guard': reference(bindings.__file__),
            'recovery_authority_adapter': reference(scope.__file__)}

    namespace['installation_manifest'] = installation_manifest

    class ObservedContainer(original_scorer.ObservedContainer):
        start = private_function(original_scorer.ObservedContainer.start, **namespace)

    class Containers(original_scorer.Containers):
        create = private_function(original_scorer.Containers.create,
                                  **{**namespace, 'ObservedContainer': ObservedContainer})

    namespace.update(ObservedContainer=ObservedContainer, Containers=Containers)
    result = ModuleType(__name__+'.private_official_scorer')
    result.__dict__.update(namespace)
    return result


def _base(policy, scoring):
    spec = importlib.util.spec_from_file_location('v089_original_grading_host',
        scope.ROOT/'tools/run_capability_grading_v066.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    namespace = clone_namespace(module, policy=policy, scorer=scoring,
        RUN_ROOT=scope.COORDINATOR_ROOT, BATCH_ROOT=original.BATCH_ROOT)

    def manifest():
        path = scope.COORDINATOR_ROOT/'scorer-manifest.json'
        value = scoring.installation_manifest()
        if path.exists():
            if scope.load(reference(path)) != value:
                raise ValueError('The private recovery scorer changed after its preparation')
            return reference(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return write_new(path, value)

    namespace['prepare_manifest'] = manifest
    original_prepare = namespace['prepare_score']

    def prepare_score(result_ref, *, endpoint='code'):
        result = scope.load(result_ref)
        plan = scope.load(reference(scope.PLAN_FILE))
        row = next((r for r in plan['rows'] if r['slot_id'] == result.get('slot_id')), None)
        if row is None:
            raise ValueError('Recovery grading cannot adopt an original first-attempt candidate')
        # The original preparer expects a per-task qualification file. An exact
        # original reference is supplied by a narrow reference-path adapter.
        expected_path = scope.COORDINATOR_ROOT/'qualifications'/(row['instance_id']+'.json')
        old_ref = scope.load(reference(scope.INVENTORY_FILE))['qualifications'][row['instance_id']]['qualification']

        def qualification_reference(path):
            if Path(path).resolve() == expected_path.resolve():
                return old_ref
            return reference(path)

        return private_function(original_prepare, reference=qualification_reference)(result_ref, endpoint=endpoint)

    namespace['prepare_score'] = prepare_score
    # delivery_disposition shares this dictionary, including the exact
    # preparation and original-control adapters above.
    result = ModuleType(__name__+'.private_grading_host')
    result.__dict__.update(namespace)
    return result


class Grading:
    def __init__(self, policy):
        self.policy = policy
        self.scorer = scorer(policy)
        self.base = _base(policy, self.scorer)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def run_request(self, request_ref, stop_event=None):
        request = scope.load(request_ref)
        scope.require_grading_allowed('v089.run', slot_id=request['slot_id'], instance_id=request['instance_id'])

        def fixed_python(arguments):
            if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
                raise ValueError('Only the originally bounded score child may be redirected')
            return self.base.fixed_python(['-m', 'proworksim.software_benchmark_recovery_grading_v089', *arguments[2:]])

        return private_function(self.base.run_request, fixed_python=fixed_python)(request_ref, stop_event=stop_event)


def factory(*, watchdog_guard):
    policy = bindings.policy(scope.require_grading_allowed, watchdog_guard=watchdog_guard,
        authorization_ref=reference(scope.AUTH_FILE), qwen_target=0)
    original_write = policy._write_claim

    def only_grading(path, value):
        if value.get('spec', {}).get('role') not in ('score', 'delivery_score'):
            raise PermissionError('The recovery scoring policy cannot create actors or controls')
        return original_write(path, value)

    policy.claim_resource.__globals__['_write_claim'] = only_grading
    policy._write_claim = only_grading
    return Grading(policy)


def score_request(request):
    scope.require_grading_allowed('v089.run', slot_id=request['slot_id'], instance_id=request['instance_id'])
    policy = bindings.dispatch_view(scope.require_grading_allowed)
    module = scorer(policy)
    folder = Path(request['directory'])
    if folder != original.GRADING_ROOT/request['resource_key'] or (folder/'quiescence.json').exists():
        raise ValueError('A foreign or already consumed scoring identity cannot run')
    write_new(folder/'recovery-runtime-v089.json', {'version': VERSION,
        'request': reference(folder/'request.json'), 'authority': reference(scope.AUTH_FILE),
        'original_official_scorer': reference(original_scorer.__file__), 'adapter': reference(__file__),
        'new_task_or_test_material': False, 'candidate_reselection': False, 'actor_feedback': False})
    return module.score_request(request)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    value = score_request(json.loads(parser.parse_args().request.read_bytes()))
    print(json.dumps({k: value[k] for k in ('resource_key', 'status', 'resolved')}))
