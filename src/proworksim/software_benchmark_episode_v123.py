"""Independent recovery using the already tested v120 execution layer."""
from types import FunctionType
from . import software_benchmark_episode_v117 as previous
from . import software_benchmark_sdk_bundle_v120 as bundle
from .software_benchmark_runtime_inputs_v119 import validate_actor_selection

VERSION = 'v123-nine-API-independent-recovery-episode-r1'
bound_start = previous.bound_start
validate_actor_ready = FunctionType(previous.validate_actor_ready.__code__,
    {**previous.validate_actor_ready.__globals__, 'validate_actor_selection': validate_actor_selection},
    'validate_actor_ready', previous.validate_actor_ready.__defaults__)
validate_actor_ready.__kwdefaults__ = previous.validate_actor_ready.__kwdefaults__
build_episode = FunctionType(previous.build_episode.__code__,
    {**previous.build_episode.__globals__, 'bundle': bundle,
     'validate_actor_ready': validate_actor_ready, 'VERSION': VERSION},
    'build_episode', previous.build_episode.__defaults__)
build_episode.__kwdefaults__ = previous.build_episode.__kwdefaults__
