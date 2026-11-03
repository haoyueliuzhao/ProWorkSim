"""Explicit future host binding for aligned controllers, with no default grant.

A separately frozen scope/plan must be supplied before this can construct an
episode binding. Old v105/v108 grants do not authorize the new implementation.
"""
from __future__ import annotations

import ast
import inspect
from types import FunctionType

from . import software_benchmark_episode_v105 as base
from . import software_benchmark_episode_v106 as preflight
from . import software_benchmark_sdk_bundle_v110 as bundle
from .software_benchmark_alignment_contract_v110 import (
    VERSION as CONTRACT_VERSION, validate_condition, validate_plan_identity,
)
from .software_benchmark_runtime_inputs_v110 import validate_actor_selection

VERSION = 'v113-aligned-effective-deadline-binding-r1'



def bound_start(start):
    """Respect the shorter real container lifetime; never extend either bound."""
    import math
    value = dict(start)
    if any(type(value.get(key)) not in (int, float) or not math.isfinite(value[key])
           for key in ('started', 'soft_at', 'hard_at')):
        raise ValueError('Absolute start and deadline values must be finite')
    value['soft_at'] = min(value['soft_at'], value['hard_at'])
    if not value['started'] < value['soft_at'] <= value['hard_at']:
        raise ValueError('No positive episode lifetime remains')
    return value


def validate_actor_ready(ready, *, actor_config, arm='REF', **kwargs):
    selected = validate_actor_selection(ready, actor_config)
    if arm == 'REF' and ready.get('public_test_launcher_is_permission_boundary') is not False:
        raise ValueError('A native convenience entry cannot claim managed permission or delivery authority')
    proof = preflight.validate_actor_ready(ready, arm=arm, **kwargs)
    return {**proof, **selected, 'native_terminal_permission_equivalence_claimed': False}


def validate_controller_result(child, output, row, baseline, relocate):
    from .software_benchmark_alignment_contract_v110 import shared_strategy
    if child.get('execution_alignment') != shared_strategy():
        raise ValueError('The actual controller did not use the common execution strategy')
    if row['arm'] == 'PROJECT':
        return preflight.validate_preflight_receipt(child, output, row, baseline, relocate)
    return None


def build_episode(*, scope=None, guard=None):
    if scope is None or guard is None:
        raise PermissionError('v110 is implementation-only; a new separately approved plan/scope is required')
    authority = guard('v066.run')
    if (authority.get('status') != 'approved'
            or authority.get('execution_alignment_version') != CONTRACT_VERSION
            or not authority.get('source_index')):
        raise PermissionError('An earlier experiment grant cannot activate the v110 strategy')
    # Reuse only the tested, explicit old builder body with its authority and
    # condition validator supplied. No process-wide function/class is patched.
    builder = FunctionType(base.build_episode.__code__, {**base.build_episode.__globals__,
        'scope': scope, 'validate_condition': validate_condition}, 'build_episode', base.build_episode.__defaults__)
    value = builder(guard=guard)
    namespace = value._run.__globals__
    original_row_and_config = namespace['_row_and_config']

    def row_and_config(row, diagnostic):
        validate_plan_identity(row)
        return original_row_and_config(row, diagnostic)

    namespace['_row_and_config'] = row_and_config
    value._row_and_config = row_and_config
    parsed = ast.parse(inspect.getsource(value._run))
    counts = {'closure': 0, 'actor_binding': 0, 'actor_upload': 0,
              'ready': 0, 'controller_inputs': 0, 'controller_result': 0, 'effective_deadline': 0}
    for node in ast.walk(parsed):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'start'):
            node.value = ast.Call(func=ast.Name(id='bound_start', ctx=ast.Load()), args=[node.value], keywords=[])
            counts['effective_deadline'] += 1
        if isinstance(node, ast.ImportFrom) and node.module == 'software_benchmark_project_closure_v064':
            node.module = 'software_benchmark_project_closure_v110'
            counts['closure'] += 1
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'validate_actor_ready':
                node.keywords.append(ast.keyword(arg='actor_config', value=ast.Name(id='actor_config', ctx=ast.Load())))
                counts['ready'] += 1
            if (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'runtime' and node.func.attr == 'controller_inputs'):
                node.keywords.append(ast.keyword(arg='actor_config', value=ast.Name(id='actor_config', ctx=ast.Load())))
                counts['controller_inputs'] += 1
    # These three precise insertion points are asserted so a changed underlying
    # provider cannot silently omit an actor contract or candidate check.
    for parent in ast.walk(parsed):
        for _, block in ast.iter_fields(parent):
            if not isinstance(block, list):
                continue
            for node in list(block):
                index = block.index(node)
                if (isinstance(node, ast.Assign) and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'actor_tool'):
                    block[index:index] = ast.parse(
                        "actor_binding = runtime.actor_inputs(actor_config, public_test_entry=public_entry)\n"
                        "actor_config = actor_binding['config']\n").body
                    counts['actor_binding'] += 1
                if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Attribute)
                        and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == 'pair'
                        and node.value.func.attr == 'upload_file'
                        and any(isinstance(arg, ast.Constant) and arg.value == '/pws/control/actor-config.json'
                                for arg in node.value.args)):
                    block[index+1:index+1] = ast.parse(
                        "pair.upload_file('actor', '/pws/control/public-test-contract.json', "
                        "actor_binding['files']['public-test-contract.json'], mode=0o444)\n").body
                    counts['actor_upload'] += 1
                if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Attribute)
                        and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == 'result'
                        and node.value.func.attr == 'update'
                        and {'controller_result', 'controller_exit_code'} <= {x.arg for x in node.value.keywords}):
                    block[index+1:index+1] = ast.parse(
                        "if child.get('status') == 'closed':\n"
                        "    aligned_preflight = validate_controller_result(child, output, row, baseline, controller_ref)\n"
                        "    if aligned_preflight is not None:\n"
                        "        result['initial_sync_preflight'] = aligned_preflight\n").body
                    counts['controller_result'] += 1
    if any(number != 1 for number in counts.values()):
        raise ValueError('The exact new deployment insertion points changed: ' + str(counts))
    namespace.update(runtime=bundle, bound_start=bound_start, validate_condition=validate_condition,
                     validate_actor_ready=validate_actor_ready,
                     validate_controller_result=validate_controller_result)
    exec(compile(ast.fix_missing_locations(parsed), __file__, 'exec'), namespace)
    value._run = namespace['_run']
    value.runtime = bundle
    value.deployment_revision = VERSION
    value.integration_points = counts
    if value.run_episode.__globals__['_run'] is not value._run:
        raise RuntimeError('The actual episode entry did not retain the aligned implementation')
    return value
