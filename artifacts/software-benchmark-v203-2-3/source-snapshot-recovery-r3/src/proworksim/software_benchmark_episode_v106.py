"""Private formal episode with the new closure validator at its real callsite."""
from __future__ import annotations

import ast
import inspect

from . import software_benchmark_scope_v106 as scope
from . import software_benchmark_sdk_bundle_v106 as bundle
from . import software_benchmark_docker_actor_v066 as actor_base
from .software_benchmark_episode_v105 import build_episode as prior_build
from .software_benchmark_expansion_episode_v069 import clone_function

VERSION = 'v106-v105-formal-pool-closure-binding-r1'
PREFLIGHT_VERSION = 'v106-initial-baseline-sync-preflight-r1'


def validate_actor_ready(ready, *, arm='REF', **kwargs):
    normalized = ready
    if arm == 'PROJECT':
        if (ready.get('managed_operations') != ['sync_preflight', 'managed_public_test', 'sync_terminal']
                or ready.get('preflight_revision') != PREFLIGHT_VERSION):
            raise ValueError('The managed actor lacks the new exact preflight protocol')
        normalized = {**ready, 'managed_operations': ['managed_public_test', 'sync_terminal']}
    proof = actor_base.validate_actor_ready(normalized, arm=arm, **kwargs)
    return {**proof, 'initial_sync_preflight_revision': PREFLIGHT_VERSION if arm == 'PROJECT' else None}


def validate_preflight_receipt(child, output, row, baseline, relocate):
    ref = relocate(child['initial_sync_preflight'], output/'controller-output')
    proof = scope.load(ref)
    if (proof.get('preflight_version') != PREFLIGHT_VERSION or proof.get('passed') is not True
            or proof.get('instance_id') != row['instance_id']
            or proof.get('tree_sha256') != baseline['tree']['tree_sha256']
            or proof.get('source_reference') != {'object_id': 'v106-initial-actor-baseline',
                                                'version_id': baseline['tree']['tree_sha256']}
            or proof.get('exact_complete_tree') is not True
            or type(proof.get('model_calls_before_preflight')) is not int
            or proof['model_calls_before_preflight'] != 0 or proof.get('public_test_calls') != 0
            or proof.get('terminal_locked') is not False or proof.get('delivery_test_evidence') is not False
            or proof.get('model_tools_added') is not False):
        raise ValueError('The formal PROJECT initialization did not preserve the exact zero-model baseline')
    return ref


def build_episode(*, guard=scope.require_allowed):
    private_builder = clone_function(prior_build, {**prior_build.__globals__, 'scope': scope})
    value = private_builder(guard=guard)
    namespace = value._run.__globals__
    parsed = ast.parse(inspect.getsource(value._run))
    changes, preflight_checks = 0, 0
    for node in ast.walk(parsed):
        if isinstance(node, ast.ImportFrom) and node.module == 'software_benchmark_project_closure_v064':
            if node.level != 1 or [(item.name, item.asname) for item in node.names] != [('validate_delivery_evidence', None)]:
                raise ValueError('Unexpected formal closure validation import')
            node.module = 'software_benchmark_project_closure_v106'
            changes += 1
    function = parsed.body[0]
    for parent in ast.walk(function):
        for key, block in ast.iter_fields(parent):
            if not isinstance(block, list):
                continue
            for index, node in enumerate(list(block)):
                if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Attribute)
                        and isinstance(node.value.func.value, ast.Name)
                        and node.value.func.value.id == 'result' and node.value.func.attr == 'update'
                        and any(keyword.arg == 'controller_result' for keyword in node.value.keywords)
                        and any(keyword.arg == 'controller_exit_code' for keyword in node.value.keywords)):
                    additions = ast.parse("if row['arm'] == 'PROJECT' and not diagnostic and child.get('status') == 'closed':\n"
                        "    result['initial_sync_preflight'] = validate_preflight_receipt(child, output, row, baseline, controller_ref)\n").body
                    block[index+1:index+1] = additions
                    preflight_checks += 1
    if changes != 1:
        raise ValueError('The one real in-function PROJECT validation callsite changed')
    if preflight_checks != 1:
        raise ValueError('The formal controller-result preflight verification callsite changed')
    namespace.update(validate_preflight_receipt=validate_preflight_receipt,
                     validate_actor_ready=validate_actor_ready)
    exec(compile(ast.fix_missing_locations(parsed), __file__, 'exec'), namespace)
    namespace['runtime'] = bundle
    namespace['policy'] = scope.dispatch_view(guard)
    value._run, value.runtime, value.policy = namespace['_run'], bundle, namespace['policy']
    value.deployment_revision = VERSION
    if value.run_episode.__globals__['_run'] is not value._run:
        raise RuntimeError('Formal execution did not retain the new closure validator')
    return value
