"""Continue only four original slots that have never called the model."""
from . import software_benchmark_scope_v114 as scope
from .software_benchmark_episode_v113 import build_episode as original


def build_episode():
    def guard(operation='v066.run',**identity):
        auth=scope.require_allowed(operation,**identity)
        slot=identity.get('slot_id')
        if slot is not None:
            plan=scope.load(auth['plan'])
            if slot not in {row['slot_id'] for row in plan['generation_rows']}:
                raise PermissionError('Previously called generations cannot be resampled')
        return auth
    return original(scope=scope,guard=guard)
