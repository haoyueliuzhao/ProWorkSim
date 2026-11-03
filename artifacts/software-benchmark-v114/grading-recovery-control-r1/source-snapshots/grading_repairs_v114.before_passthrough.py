"""Opt-in repair at the actual private official scorer dispatch point.

The caller supplies its new candidate/resource authorization. This adapter
grants none, starts no process, changes no dependency, and reselects no patch.
"""
from __future__ import annotations

import copy
from types import FunctionType, ModuleType

from . import software_benchmark_test_reset_v114 as reset
from .software_benchmark_candidates_v054 import reference

VERSION = 'v114-two-task-official-test-reset-binding-r1'


def _bind(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__,
                          function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def bind_scorer(existing, instances):
    """Only change _score -> diagnostics -> run_instance -> copied TestSpec."""
    rows = [copy.deepcopy(row) for row in instances]
    if len(rows) != 2 or {row.get('instance_id') for row in rows} != reset.TASKS:
        raise ValueError('Freeze exactly the two original v113 reset-failure tasks')
    for row in rows:
        reset.repair_eval_script(row)
    old_namespace = existing.score_request.__globals__
    if existing._score.__globals__ is not old_namespace:
        raise ValueError('The official scorer must have a single actual private namespace')
    namespace = {**old_namespace, **vars(existing)}
    for name, value in list(namespace.items()):
        if isinstance(value, FunctionType) and value.__globals__ is old_namespace:
            namespace[name] = _bind(value, namespace)
    namespace['diagnostics'] = reset.diagnostics_adapter(existing.diagnostics, rows)
    inherited_manifest = existing.installation_manifest

    def installation_manifest():
        return {**inherited_manifest(), 'test_reset_binding_revision': VERSION,
            'test_reset_binding_source': reference(__file__),
            'test_reset_source': reference(reset.__file__),
            'unchanged_reset_mechanism_source': reference(reset.mechanism.__file__),
            'reset_tasks': sorted(reset.TASKS),
            'official_test_patch_and_test_commands_changed': False,
            'test_reset_executor_changed': True,
            'candidate_patch_changed': False, 'runtime_qualified_by_CPU_control': False}

    namespace['installation_manifest'] = installation_manifest
    bound = ModuleType(__name__+'.private_official_scorer')
    bound.__dict__.update(namespace)
    if bound._score.__globals__['diagnostics'] is not bound.diagnostics:
        raise ValueError('The actual official scorer lost its new reset dispatch binding')
    return bound
