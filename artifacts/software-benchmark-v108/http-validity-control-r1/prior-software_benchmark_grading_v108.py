"""Restore the actual TLS cleanup binding for the unchanged v105 resource pool.

The official grader, test bytes, candidates and original control evidence stay
unchanged. This private binding admits the exact new PROJECT closure identity,
enumerates two grading lanes, separates physical cleanup from CA measurement, and seals new administrative
manifests without overwriting the v105 preparation or consuming new controls.
"""
from __future__ import annotations

import ast
from functools import lru_cache
import inspect
from types import FunctionType, ModuleType

from . import software_benchmark_grading_v105 as previous
from . import software_benchmark_scope_v108 as scope
from . import software_benchmark_project_closure_v106 as closure
from .software_benchmark_candidates_v054 import reference
from . import software_benchmark_requests_tls_v068 as lifecycle
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function

VERSION = 'v108-v105-pool-tls-lifecycle-physical-cleanup-r1'
_namespace = clone_namespace(previous, scope=scope, VERSION=VERSION,
    REUSE_VERSION='v108-reused-v062-control-qualification-r1',
    EQUIVALENCE_VERSION='v108-explicit-v062-official-environment-equivalence-r1',
    MODULE=__name__, __file__=__file__)


def _lane_validator(namespace):
    """Change exactly the CPU-set enumeration; preserve every other check."""
    source = inspect.getsource(previous.original.validate_request)
    needle = 'range(4)'
    if source.count(needle) != 1:
        raise ValueError('Unexpected original grading-lane validator source')
    revised = source.replace(needle, 'range(MAX_GRADERS)')
    before, after = ast.parse(source), ast.parse(revised)
    changed = 0
    for node in ast.walk(after):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'range':
            if len(node.args) == 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == 'MAX_GRADERS':
                node.args[0] = ast.Constant(value=4)
                changed += 1
    if changed != 1 or ast.dump(before, include_attributes=False) != ast.dump(after, include_attributes=False):
        raise ValueError('Only the grading CPU-set enumeration may change')
    compiled = {}
    exec(compile(revised, __file__ + ':two-lane-validator', 'exec'), namespace, compiled)
    return compiled['validate_request']


_parent_environment = _namespace['private_environment']


def private_environment(policy):
    # Provider records are administrative metadata; leave old v105 records
    # intact while preserving the actual score directories/resource identities.
    private = ModuleType(__name__ + '.environment_policy')
    private.__dict__.update(vars(policy))
    private.GRADING_ROOT = scope.COORDINATOR_ROOT / 'provider-bindings'
    environment = _parent_environment(private)
    environment.tls.run_official = lifecycle.run_official
    return environment


_parent_scorer = _namespace['scorer']


def bind_physical_cleanup(namespace):
    """CA measurements remain unknown without pretending a removed object is live."""
    environment, original_scorer, policy = (
        namespace[name] for name in ('environment', 'original_scorer', 'policy'))

    def cleanup(request, tracking):
        transport_errors = (environment.tls.cleanup_transport(tracking)
                            if tracking.get('environment_container') else [])
        measurement_errors = [error for error in transport_errors
                              if isinstance(error, str) and error.startswith('CA final identity: ')]
        physical_errors = [error for error in transport_errors if error not in measurement_errors]
        timer = tracking.get('deadline_timer')
        if timer:
            timer.cancel()
            timer.join(timeout=10)
        # This original routine still verifies/removes exact owned IDs and
        # rejects unknown creates; no CA error can substitute for its proof.
        proof = original_scorer.cleanup_scoring(request, tracking)
        proof.update(version=VERSION, resource_key=request['resource_key'],
                     deadline_reached=tracking.get('deadline_reached', False))
        proof['cleanup_errors'].extend(tracking.get('watchdog_errors', []))
        proof['cleanup_errors'].extend(physical_errors)
        proof['measurement_errors'] = measurement_errors
        proof['transport_result'] = tracking.get('transport_result')
        proof['TLS_lifecycle'] = tracking.get('tls_lifecycle')
        if timer and timer.is_alive():
            proof['cleanup_errors'].append('Container deadline timer remains alive')
        proof['quiescent'] = proof['quiescent'] and not proof['cleanup_errors']
        if tracking.get('claim'):
            policy.release_resource(tracking['claim'], quiescent=proof['quiescent'])
        return proof

    return cleanup


def scorer(policy, *, manifest_provider=None):
    value = _parent_scorer(policy, manifest_provider=manifest_provider)
    namespace = value.validate_request.__globals__
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence,
                     MAX_GRADERS=scope.MAX_GRADERS)
    validator = _lane_validator(namespace)
    native_manifest = namespace['installation_manifest']

    def installation_manifest():
        manifest = native_manifest()
        if manifest_provider is not None:
            return manifest
        return {**manifest, 'managed_delivery_validator': reference(closure.__file__),
            'deployment_repair_adapter': reference(__file__),
            'original_scoring_adapter': reference(previous.original.__file__),
            'grading_lane_count': scope.MAX_GRADERS,
            'grading_validation_change': 'Exactly range(4) -> range(MAX_GRADERS); MAX_GRADERS=2',
            'official_scoring_function_changed': False,
            'TLS_lifecycle_binding': reference(lifecycle.__file__),
            'physical_cleanup_measurement_separation': reference(__file__),
            'managed_closure_identity_change': 'Only frozen v105 PROJECT task/seed identities accepted'}

    cleanup = bind_physical_cleanup(namespace)
    namespace.update(validate_request=validator, installation_manifest=installation_manifest, cleanup=cleanup)
    value.__dict__.update(validate_request=validator, installation_manifest=installation_manifest,
                          validate_delivery_evidence=closure.validate_delivery_evidence, cleanup=cleanup)
    return value


_namespace.update(private_environment=private_environment, scorer=scorer)
# The original lru wrapper closes over the old function; create a fresh wrapper
# around its cloned body so cold subprocesses import this deployment revision.
_namespace['cold_manifest'] = lru_cache(maxsize=1)(
    clone_function(previous.cold_manifest.__wrapped__, _namespace))
_namespace['Grading'] = type('Grading', (previous.Grading,), {
    key: clone_function(value, _namespace) for key, value in vars(previous.Grading).items()
    if isinstance(value, FunctionType)})
main = _namespace['main']
globals().update({key: value for key, value in _namespace.items() if not key.startswith('__')})


if __name__ == '__main__':
    main()
