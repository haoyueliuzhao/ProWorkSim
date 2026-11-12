"""Private API-only episode bindings for the nonthinking comparison.

The owned-container and immutable-candidate machinery is reused without a
system parent slice. Every guard resolves to the new 100-attempt authority.
"""
from __future__ import annotations

from . import software_benchmark_scope_v105 as scope
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_deepseek_contract_v105 import validate_condition

VERSION = 'v105-private-nonthinking-episode-bindings-r1'


def build_episode(*, guard=scope.require_allowed):
    from .software_benchmark_episodes_v075 import episode
    from .software_benchmark_io_v088 import bind_episode as bind_io
    from .software_benchmark_failure_scope_v088 import bind_episode as bind_failure
    from .software_benchmark_api_bridge_v094 import bind_episode as bind_bridge
    from . import software_benchmark_sdk_bundle_v105 as bundle
    policy = scope.dispatch_view(guard)
    value = episode(policy)
    value = bind_bridge(bind_failure(bind_io(value)), scope_guard=guard)
    namespace = value._run.__globals__

    def row_and_config(row, diagnostic):
        auth = guard('v066.run', slot_id=row['slot_id'], instance_id=row['instance_id'])
        plan = scope.load(auth['plan'])
        if ([r for r in plan['rows'] if r['slot_index'] == row['slot_index']] != [row]
                or row['model_key'] != 'DEEPSEEK' or row.get('thinking') is not False
                or row['measurement_kind'] != 'full_verified_comparison'):
            raise ValueError('Only a sealed nonthinking paired row may run')
        if diagnostic and not any(spec.get('diagnostic') is True and spec['role'] == 'actor'
                and spec.get('slot_id') == row['slot_id'] for spec in plan['resources'].values()):
            raise ValueError('No exact zero-model diagnostic object identity')
        config = scope.load(row['configuration'])
        condition = scope.load(config['configuration'])
        limits = validate_condition(condition)
        if (limits['input_plus_output_tokens'] != row['generation_token_upper_bound']
                or any(config.get(key) != row[key] for key in
                       ('slot_id', 'slot_index', 'seed', 'execution_arm', 'source_slot_id', 'replicate'))
                or condition['condition_id'] != row['condition_id']
                or config['public_task']['instance_id'] != row['instance_id']
                or config['public_task']['repo'] != row['repo']):
            raise ValueError('Task, initial state, seed or nonthinking mode changed')
        return config, condition, limits

    namespace.update(ROOT=scope.ROOT, BATCH=scope.BATCH_ROOT, runtime=bundle,
                     _row_and_config=row_and_config, validate_condition=validate_condition)
    for key in ('ROOT', 'BATCH', 'runtime', '_row_and_config', 'validate_condition'):
        value.__dict__[key] = namespace[key]
    value.deployment_revision = VERSION
    return value


def diagnostic(index):
    """Run one declared zero-generation pair; authorization precedes all creation."""
    scope.require_allowed()
    plan = scope.load(reference(scope.PLAN_FILE))
    binding = next((r for r in plan['diagnostics'] if r['index'] == index), None)
    if binding is None:
        raise PermissionError('Unknown zero-model diagnostic index')
    row = next(r for r in plan['rows'] if r['slot_id'] == binding['slot_id'])
    impl = build_episode()
    return impl._run(row, None, diagnostic=True, diagnostic_index=index)
