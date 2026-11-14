"""New batch official scoring and strict original gold/empty qualification reuse.

All resource creation is delegated through this batch's sealed scope. Old
qualifications are read and fully validated; no old grant or ledger is reopened.
"""
from functools import lru_cache
import inspect
import os
from pathlib import Path
import textwrap
from types import FunctionType

from . import software_benchmark_grading_v105 as base
from . import software_benchmark_scope_v203_2_3 as scope
from . import software_benchmark_environment_v203_2_3 as environment_adapter
from . import software_benchmark_project_closure_v203_2_3 as closure
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_delivery_reuse_v175 import bind_host
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function
from .software_benchmark_grading_v131 import _lane_validator

if os.environ.get('PWS_V20323_PREPARATION_GRADING') == '1':
    if scope.AUTH_FILE.exists():
        raise PermissionError('Preparation authority cannot replace a sealed formal runtime')
    from .software_benchmark_preparation_grading_v203_2_3 import preparation_scope
    scope = preparation_scope()

VERSION = 'v203.2.3-role-context-official-scoring-r1'
REUSE_VERSION = 'v203.2.3-exact-v066-qualification-reuse-r1'
MODULE = 'proworksim.software_benchmark_grading_v203_2_3'
OLD_ROOT = scope.ROOT / 'runs/software-benchmark-v066/v064-continuation-r3'
FRESH_EXTERNAL_CONTROL_TASKS = frozenset({environment_adapter.TLS_TASK})
RUNTIME_FIELDS = ('parent', 'archive_adapter', 'diagnostic_decode_adapter',
                  'diagnostic_upstream_sha256', 'lossless_archive_storage', 'limits',
                  'cap_add', 'cap_drop', 'no_new_privileges',
                  'official_tests_and_scoring_rules_changed', 'host_namespace_mount_or_daemon_operations')
_ns = clone_namespace(base, scope=scope, VERSION=VERSION, MODULE=MODULE, __file__=__file__)
_parent_scorer, _parent_host, _parent_environment = _ns['scorer'], _ns['host'], _ns['private_environment']


def private_environment(policy):
    return environment_adapter.private_environment(policy, scope, _parent_environment)


def _original_controls(qualified):
    # validate_qualification has already run the historical recursive validator.
    # Following its bound provenance is only for recording/strict task-env checks.
    for _ in range(4):
        if 'controls' in qualified:
            controls = qualified['controls']
            if len(controls) != 2 or {x['patch_kind'] for x in controls} != {'gold', 'empty'}:
                raise ValueError('Original qualification has no unique gold/empty pair')
            return controls
        qualified = scope.load(qualified['original_qualification'])
    raise ValueError('Unexpected qualification provenance depth')


def reused_qualification(task, config, plan_ref):
    plan = scope.validate_plan(scope.load(plan_ref))
    if (plan_ref != reference(scope.PLAN_FILE) or task not in plan['environments']
            or config != scope.load(plan['environments'][task]['configuration'])):
        raise ValueError('Qualification must bind this exact new task configuration')
    old_plan_ref = reference(OLD_ROOT / 'plan.json')
    old_plan = scope.load(old_plan_ref)
    old_config_ref = old_plan['environments'][task]['configuration']
    old_config = scope.load(old_config_ref)
    if base.environment_identity(config) != base.environment_identity(old_config):
        raise ValueError('Official image, dataset, baseline, or scorer input identity changed')
    old_qualification_ref = reference(OLD_ROOT / 'coordinator/qualifications' / (task + '.json'))
    qualified = base.original.validate_qualification(old_qualification_ref, old_config, old_plan_ref)
    controls = _original_controls(qualified)
    old_manifest_ref = reference(OLD_ROOT / 'coordinator/scorer-manifest.json')
    new_manifest_ref = reference(scope.COORDINATOR_ROOT / 'scorer-manifest.json')
    old_manifest, new_manifest = scope.load(old_manifest_ref), scope.load(new_manifest_ref)
    changed = [key for key in RUNTIME_FIELDS if old_manifest.get(key) != new_manifest.get(key)]
    if changed:
        raise ValueError('Official scoring runtime differs: ' + ', '.join(changed))
    old_cap = old_manifest['requests_capabilities_by_task'].get(task, [])
    new_cap = new_manifest['requests_capabilities_by_task'].get(task, [])
    if old_cap != new_cap:
        raise ValueError('Task-specific container capabilities changed')
    current = private_environment(scope.dispatch_view(scope.require_grading_allowed)).request_fields(task)
    identities = []
    for control in controls:
        receipt = scope.load(control['receipt'])
        identity = scope.load(receipt['identity'])
        if identity['limits'] != base.original.LIMITS or len(base.original.cpus(identity['cpuset_cpus'])) != 4:
            raise ValueError('Original actual scoring resources differ')
        bound = environment_adapter.compare_task_environment(identity, current, task=task, load=scope.load)
        identities.append({'patch_kind': control['patch_kind'], 'identity': receipt['identity'],
                           'environment_equivalence': bound})
    return {'version': REUSE_VERSION, 'instance_id': task, 'passed': True, 'plan': plan_ref,
            'configuration': plan['environments'][task]['configuration'],
            'original_plan': old_plan_ref, 'original_configuration': old_config_ref,
            'original_qualification': old_qualification_ref, 'original_controls': controls,
            'original_scorer_manifest': old_manifest_ref, 'current_scorer_manifest': new_manifest_ref,
            'environment_identity': base.environment_identity(config),
            'exact_runtime_fields': list(RUNTIME_FIELDS), 'control_environment_checks': identities,
            'original_strict_validator_executed': True, 'new_controls': 0, 'model_calls': 0,
            'old_scope_authority_reopened': False, 'old_results_modified': False,
            'current_external_endpoint_health_claimed': False, 'source': reference(__file__)}


def scorer(policy, *, manifest_provider=None):
    value = _parent_scorer(policy, manifest_provider=manifest_provider)
    namespace = value.validate_request.__globals__
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence, MAX_GRADERS=scope.MAX_GRADERS)
    namespace['validate_request'] = _lane_validator(namespace)
    from .software_namespace_witness_v183 import bind_scorer
    bind_scorer(value)
    source = inspect.getsource(base.original.validate_qualification)
    importer = 'from .software_benchmark_grading_qualification_v060 import validate_transport_evidence'
    if source.count(importer) != 1:
        raise ValueError('The exact original TLS qualification seam changed')
    source = source.replace(importer,
        'from .software_benchmark_environment_v203_2_3 import validate_transport_evidence')
    compiled = {}
    exec(compile(source, __file__ + ':current-CA-control-qualification', 'exec'), namespace, compiled)
    native_validate = compiled['validate_qualification']

    def validate_qualification(ref, config, plan_ref):
        supplied = scope.load(ref)
        if supplied.get('version') != REUSE_VERSION:
            return native_validate(ref, config, plan_ref)
        task = config['instance_id']
        if task in FRESH_EXTERNAL_CONTROL_TASKS:
            raise ValueError('Current-batch gold/empty controls are required for the external TLS endpoint')
        if Path(ref['path']).resolve() != scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json'):
            raise ValueError('Qualification must have its own exact new batch identity')
        if supplied != reused_qualification(task, config, plan_ref):
            raise ValueError('Strict original-control reuse proof changed')
        return supplied

    prior_manifest = namespace['installation_manifest']
    def installation_manifest():
        result = prior_manifest()
        if manifest_provider is not None:
            return result
        return {**result, 'managed_delivery_validator': reference(closure.__file__),
                'role_context_scoring_adapter': reference(__file__),
                'scoring_environment_adapter': reference(environment_adapter.__file__),
                'maximum_graders': scope.MAX_GRADERS,
                'public_network': 'Requests1766 scoring only: frozen numeric httpbin HTTP/TLS; solver network none',
                'scoring_CA_profile': reference(scope.CA_PROFILE_FILE),
                'scoring_CA_effective_trust_changed': True,
                'scoring_CA_tasks': sorted(FRESH_EXTERNAL_CONTROL_TASKS),
                'original_repository_CA_and_candidate_bytes_unchanged': True,
                'TLS_lifecycle_binding': reference(scope.ROOT / 'src/proworksim/software_benchmark_requests_tls_v068.py'),
                'old_resource_authority_reopened': False,
                'solver_public_test_admission_is_separate': True}
    namespace.update(validate_qualification=validate_qualification, installation_manifest=installation_manifest)
    for name in ('validate_request', 'validate_qualification', 'installation_manifest', 'validate_delivery_evidence'):
        setattr(value, name, namespace[name])
    return value


def host(policy, scoring):
    return bind_host(_parent_host(policy, scoring))


def prepare_environment_qualifications_local():
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(scope.load(plan_ref))
    scoring = scorer(scope.dispatch_view(scope.require_grading_allowed))
    scoring.environment.prepare()
    manifest = scope.retain(scope.COORDINATOR_ROOT / 'scorer-manifest.json', scoring.installation_manifest())
    controls, qualifications, failures = [], {}, {}
    for task, environment in plan['environments'].items():
        try:
            if task in FRESH_EXTERNAL_CONTROL_TASKS:
                old_plan_ref = reference(OLD_ROOT / 'plan.json')
                old_plan = scope.load(old_plan_ref)
                old_ref = reference(OLD_ROOT / 'coordinator/qualifications' / (task + '.json'))
                base.original.validate_qualification(old_ref,
                    scope.load(old_plan['environments'][task]['configuration']), old_plan_ref)
                scope.retain(scope.COORDINATOR_ROOT / 'qualification-reuse-evidence' / (task + '.json'), {
                    'original_qualification': old_ref, 'original_strict_validator_executed': True,
                    'qualified_for_current_environment': False, 'scoring_CA_profile': reference(scope.CA_PROFILE_FILE),
                    'reason': 'Effective CA trust and current external endpoint require new gold/empty controls'})
                raise ValueError('Historical identity passed; new scoring CA/current endpoint gold/empty controls required')
            proof = reused_qualification(task, scope.load(environment['configuration']), plan_ref)
            ref = scope.retain(scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json'), proof)
            qualifications[task] = {'status': 'qualified', 'qualification': ref, 'reused_controls': True}
        except (ValueError, KeyError, OSError) as error:
            failures[task] = {'status': 'requires_new_controls', 'error': type(error).__name__ + ': ' + str(error)}
            for kind in ('gold', 'empty'):
                key = 'control-' + task + '-' + kind
                request = {'version': VERSION, 'resource_key': key, 'instance_id': task, 'slot_id': None,
                    'plan': plan_ref, 'configuration': environment['configuration'], 'patch_kind': kind,
                    'limits': scoring.LIMITS, 'scorer_manifest': manifest, 'cpuset_cpus': None,
                    'directory': str(scope.GRADING_ROOT / key), 'candidate_lock': None,
                    **scoring.environment.request_fields(task)}
                controls.append(scope.retain(scope.GRADING_ROOT / key / 'request.json', request))
    result = {'controls': controls, 'qualifications': qualifications, 'reuse_failures': failures,
              'model_calls': 0, 'new_control_requests': len(controls), 'Docker_operations': 0,
              'solver_public_test_admission_is_separate': True,
              'fresh_external_control_tasks': sorted(FRESH_EXTERNAL_CONTROL_TASKS),
              'current_external_endpoint_health_claimed': False}
    scope.retain(scope.COORDINATOR_ROOT / 'qualification-reuse-decisions.json', result)
    return result


_ns.update(REUSE_VERSION=REUSE_VERSION, private_environment=private_environment, scorer=scorer, host=host,
           prepare_environment_qualifications_local=prepare_environment_qualifications_local)
for _name in ('score_request', 'main'):
    _source = inspect.getsource(getattr(base, _name)).replace("'v105.run'", "'v203.2.3.run'")
    exec(compile(_source, __file__ + ':' + _name, 'exec'), _ns)
_ns['cold_manifest'] = lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__, _ns))
_methods = {key: clone_function(value, _ns) for key, value in vars(base.Grading).items() if isinstance(value, FunctionType)}
_source = textwrap.dedent(inspect.getsource(base.Grading.run_request)).replace("'v105.run'", "'v203.2.3.run'")
_local = {}
exec(compile(_source, __file__ + ':scoring-child', 'exec'), _ns, _local)
_methods['run_request'] = _local['run_request']
_ns['Grading'] = type('Grading', (base.Grading,), _methods)
globals().update({key: value for key, value in _ns.items() if not key.startswith('__')})

if __name__ == '__main__':
    _ns['main']()
