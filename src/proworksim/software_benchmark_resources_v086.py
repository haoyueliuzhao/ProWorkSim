"""Sixteen shared API startups, with original actor/physical/FD limits retained."""
from __future__ import annotations

from types import ModuleType

from . import software_benchmark_resources_v076 as original
from . import software_benchmark_resources_v079 as previous
from .software_benchmark_resources_v080 import safe_pending_pairs
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_deepseek_runtime_v069 import private_function

VERSION = 'v086-API-sixteen-startup-tolerant-status-r1'
MAX_STARTING_PAIRS = 16
_evaluate_sixteen = private_function(original.evaluate, VERSION=VERSION,
                                    MAX_STARTING_PAIRS=MAX_STARTING_PAIRS)
evaluate = private_function(previous.evaluate, _evaluate_eight=_evaluate_sixteen)
_safe_previous = ModuleType(__name__+'.private_v076')
_namespace = clone_namespace(original, MAX_STARTING_PAIRS=MAX_STARTING_PAIRS)
_namespace['pending_pairs'] = safe_pending_pairs
_safe_previous.__dict__.update(_namespace)
policy = private_function(previous.policy, previous=_safe_previous, VERSION=VERSION,
    MAX_STARTING_PAIRS=MAX_STARTING_PAIRS, evaluate=evaluate,
    __file__=__file__, __name__=__name__)
