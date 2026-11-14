"""Exact v114 task scope for the already tested per-path official test reset.

Only the scorer sees these original official test paths. Model candidates and
the official test patch remain byte-identical; the host acquires no authority.
"""
from __future__ import annotations

from types import FunctionType

from . import software_benchmark_test_reset_v099 as mechanism

VERSION = 'v114-official-test-preimage-reset-r1'
TASKS = frozenset(('sphinx-doc__sphinx-10614', 'pylint-dev__pylint-6528'))

# Explicit ordinary function bodies, all sharing this fresh namespace. Do not
# clone an lru/decorator wrapper or retain an old task-selection closure.
_namespace = {**vars(mechanism), '__name__': __name__, '__file__': __file__,
              'VERSION': VERSION, 'TASKS': TASKS}
for _name in ('digest', 'test_paths', 'reset_command', 'repair_eval_script', 'diagnostics_adapter'):
    _original = getattr(mechanism, _name)
    if not isinstance(_original, FunctionType) or _original.__closure__:
        raise ValueError('The reviewed reset mechanism must remain a plain function')
    _bound = FunctionType(_original.__code__, _namespace, _name, _original.__defaults__)
    _bound.__kwdefaults__ = _original.__kwdefaults__
    _namespace[_name] = _bound
    globals()[_name] = _bound
