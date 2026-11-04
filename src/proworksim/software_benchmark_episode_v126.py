"""Two independently authorized REF attempts, with the original strategy intact."""
from types import FunctionType

from . import software_benchmark_episode_v113 as original
from . import software_benchmark_sdk_bundle_v126 as bundle

VERSION = 'v126-original-ref-rejected-history-episode-r1'


def build_episode():
    from . import software_benchmark_scope_v126 as scope

    def guard(operation='v066.run', **identity):
        authority = scope.require_allowed(operation, **identity)
        slot = identity.get('slot_id')
        if slot is not None:
            plan = scope.load(authority['plan'])
            if slot not in {row['slot_id'] for row in plan['generation_rows']}:
                raise PermissionError('Only the explicitly authorized two new REF attempts may run')
        return authority

    builder = FunctionType(original.build_episode.__code__,
        {**vars(original), 'bundle': bundle, 'VERSION': VERSION},
        'build_episode', original.build_episode.__defaults__)
    builder.__kwdefaults__ = original.build_episode.__kwdefaults__
    return builder(scope=scope, guard=guard)
