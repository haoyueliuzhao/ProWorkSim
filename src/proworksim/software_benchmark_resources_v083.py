"""API startup-eight policy with private tolerant status reads, not Qwen policy."""
from __future__ import annotations

from types import ModuleType

from . import software_benchmark_resources_v076 as original
from . import software_benchmark_resources_v079 as previous
from .software_benchmark_resources_v080 import safe_pending_pairs
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_deepseek_runtime_v069 import private_function

VERSION = 'v083-API-eight-startup-tolerant-status-r1'
_safe_previous = ModuleType(__name__+'.private_v076')
_namespace = clone_namespace(original)
# clone_namespace rebinds original functions after applying overrides. Replace
# this function afterwards, in the same dictionary captured by private policy.
_namespace['pending_pairs'] = safe_pending_pairs
_safe_previous.__dict__.update(_namespace)
policy = private_function(previous.policy, previous=_safe_previous, VERSION=VERSION,
                          __file__=__file__, __name__=__name__)
