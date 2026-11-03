"""Keep the v106 actor/controller and closure; bind only the new owner lease."""
from . import software_benchmark_scope_v108 as scope
from .software_benchmark_episode_v106 import build_episode as previous
from . import software_benchmark_sdk_bundle_v108 as bundle
from .software_benchmark_expansion_episode_v069 import clone_function


def build_episode(*, guard=scope.require_allowed):
    builder = clone_function(previous, {**previous.__globals__, 'scope': scope, 'bundle': bundle})
    value = builder(guard=guard)
    value.deployment_revision = 'v108-new-owner-original-formal-episode-r1'
    return value
