"""Private explicit physical identities, retaining frozen task execution code."""
from __future__ import annotations

from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_resources_v076 as capacity
from . import software_benchmark_resources_v079 as priority
from . import software_benchmark_api_scope_v089 as scope
from .software_benchmark_resources_v084 import safe_pending_pairs
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_candidates_v054 import reference

VERSION = 'v089-explicit-recovery-resource-identities-r1'


def dispatch_view(guard):
    limits = {**original.CONSTRAINTS, 'fresh_generation_slots': 44,
        'generation_token_upper_bound': 220_000_000, 'api_generation_token_upper_bound': 220_000_000,
        'api_total_budget_cny': '1700.00', 'maximum_actor_containers': 44,
        'maximum_controller_containers': 44, 'maximum_control_containers': 0,
        'maximum_code_score_containers': 44, 'maximum_delivery_score_containers': 23,
        'maximum_score_containers': 67, 'maximum_containers': 155,
        'maximum_named_volumes': 44, 'maximum_model_residents': 0}
    namespace = clone_namespace(original, VERSION=VERSION, CONSTRAINTS=limits, PLAN_FILE=scope.PLAN_FILE,
        AUTHORIZATION_FILE=scope.AUTH_FILE, RESUME_FILE=scope.INVENTORY_FILE,
        COORDINATOR_RUN_ROOT=scope.COORDINATOR_ROOT)

    def allowed(operation='v066.run', **identity):
        guard(operation, **identity)
        return {'version': VERSION, 'status': 'approved', 'plan': reference(scope.PLAN_FILE),
                'sources': reference(scope.SOURCE_FILE), 'constraints': namespace['CONSTRAINTS']}

    namespace['require_v066_allowed'] = allowed
    value = ModuleType(__name__+'.private_dispatch')
    value.__dict__.update(namespace)
    value.__file__ = __file__
    return value


def policy(guard, *, watchdog_guard, authorization_ref=None, qwen_target=0, capacity_probe=None):
    dispatch = dispatch_view(guard)
    namespace = clone_namespace(capacity, original=dispatch, MAX_STARTING_PAIRS=16)
    namespace['pending_pairs'] = safe_pending_pairs
    base = ModuleType(__name__+'.private_capacity')
    base.__dict__.update(namespace)
    evaluate = private_function(priority.evaluate,
        _evaluate_eight=private_function(capacity.evaluate, MAX_STARTING_PAIRS=16))
    factory = private_function(priority.policy, previous=base, MAX_STARTING_PAIRS=16, evaluate=evaluate)
    return factory(guard, watchdog_guard=watchdog_guard, authorization_ref=authorization_ref, capacity_probe=capacity_probe,
                   qwen_target=qwen_target)


def episode(policy):
    from .software_benchmark_episodes_v076 import api_episode
    from .software_benchmark_io_v088 import bind_episode as bind_io
    from .software_benchmark_failure_scope_v088 import bind_episode as bind_failure
    value = private_function(api_episode, parent=scope.parent_module())(policy)
    value = bind_failure(bind_io(value))
    value.run_episode.__globals__['capacity'] = policy.physical_capacity
    value.__dict__['capacity'] = policy.physical_capacity
    return value
