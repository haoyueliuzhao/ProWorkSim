"""Keep the v106 actor/controller and closure; bind only the new owner lease."""
from . import software_benchmark_scope_v107 as scope
from .software_benchmark_episode_v106 import build_episode as previous
from .software_benchmark_expansion_episode_v069 import clone_function


def build_episode(*, guard=scope.require_allowed):
    builder = clone_function(previous, {**previous.__globals__, 'scope': scope})
    value = builder(guard=guard)
    value.deployment_revision = 'v107-new-owner-original-v106-episode-r1'
    return value
