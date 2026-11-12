"""One original Requests task: reuse verified CA controls without replaying them.

A new leaf qualification binds the exact task/image/dataset and unchanged
scoring/CA semantics to the original completed gold/empty receipts. It conveys
no authority to reopen the old controls or generate any replacement model run.
"""
from functools import lru_cache
import inspect
from pathlib import Path
import textwrap
from types import FunctionType

from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_passive_v203_2_1_r3 as ca_grading
from . import software_benchmark_scope_passive_leaf_v203_2_1_r3 as scope
from . import software_benchmark_environment_passive_v203_2_1_r3 as repair
from . import software_benchmark_project_closure_v203_2_1 as closure
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_delivery_reuse_v175 import bind_host
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function
from .software_benchmark_grading_v131 import _lane_validator

VERSION = 'v203.2.1-requests-original-leaf-official-scoring-r3'
REUSE_VERSION = 'v203.2.1-leaf-exact-private-CA-qualification-reuse-r3'
MODULE = 'proworksim.software_benchmark_grading_passive_leaf_v203_2_1_r3'
TASK = repair.TASK
_ns = clone_namespace(base, scope=scope, VERSION=VERSION, MODULE=MODULE, __file__=__file__)
_parent_scorer, _parent_host, _parent_environment = _ns['scorer'], _ns['host'], _ns['private_environment']

# These fields bind the actual official evaluator/runtime and all effective CA
# and fixture assets. New ownership paths and grader lane count are independent.
RUNTIME_EQUIVALENCE_FIELDS = (
    'parent', 'archive_adapter', 'diagnostic_decode_adapter', 'diagnostic_upstream_sha256',
    'limits', 'cap_add', 'cap_drop', 'no_new_privileges', 'official_tests_and_scoring_rules_changed',
    'host_poll_adapter', 'scorer_interpreter_profile', 'environment_router',
    'offline_requests_adapter', 'real_tls_requests_adapter', 'requests_capabilities_by_task',
    'private_CA_revision', 'public_network', 'maximum_real_tls_sessions',
)


def private_environment(policy):
    return repair.private_environment(policy, scope, _parent_environment)


def task_environment_identity(config):
    return {**base.environment_identity(config), 'repo': config['repo'],
            'public_task': config['public_task'],
            'official_image_descriptor': config['scorer_request_base']['image'],
            'public_test_entry': config['public_test_entry']}


def reused_qualification(config, plan_ref):
    """Validate real old evidence before constructing the new exact binding."""
    if config.get('instance_id') != TASK or plan_ref != reference(scope.PLAN_FILE):
        raise ValueError('The leaf qualification is exclusive to this exact Requests plan')
    plan = scope.validate_plan(scope.load(plan_ref))
    if (set(plan.get('environments', {})) != {TASK} or len(plan.get('rows', [])) != 1
            or any(item.get('role') == 'control' for item in plan['resources'].values())):
        raise ValueError('The leaf must contain one original task and no new controls')
    configured = scope.load(plan['environments'][TASK]['configuration'])
    if config != configured:
        raise ValueError('Leaf grading configuration differs from its declared environment')
    ca_scope = ca_grading.scope
    old_plan_ref = reference(ca_scope.PLAN_FILE)
    old_plan = ca_scope.validate_plan(ca_scope.load(old_plan_ref))
    old_config_ref = old_plan['environments'][TASK]['configuration']
    old_config = ca_scope.load(old_config_ref)
    if task_environment_identity(config) != task_environment_identity(old_config):
        raise ValueError('Task, image, dataset, original baseline or public test binding changed')
    old_qualification_ref = reference(ca_scope.COORDINATOR_ROOT / 'qualifications' / (TASK + '.json'))
    old_scorer = ca_grading.scorer(ca_scope.dispatch_view())
    qualified = old_scorer.validate_qualification(old_qualification_ref, old_config, old_plan_ref)
    if qualified.get('passed') is not True:
        raise ValueError('Original CA gold/empty qualification did not pass its strict validator')

    old_manifest_ref = reference(ca_scope.COORDINATOR_ROOT / 'scorer-manifest.json')
    new_manifest_ref = reference(scope.COORDINATOR_ROOT / 'scorer-manifest.json')
    old_manifest, new_manifest = scope.load(old_manifest_ref), scope.load(new_manifest_ref)
    if any(old_manifest.get(key) != new_manifest.get(key) for key in RUNTIME_EQUIVALENCE_FIELDS):
        raise ValueError('The leaf official runtime or CA/fixture semantics differ from the qualified controls')
    old_environment_ref = old_scorer.environment.request_fields(TASK)['environment_revision']
    new_environment = private_environment(scope.dispatch_view())
    new_environment_ref = new_environment.request_fields(TASK)['environment_revision']
    old_environment = scope.load(old_environment_ref)
    new_environment_value = scope.load(new_environment_ref)
    # This one field names the new scope's guard. Every actual fixture/profile,
    # certificate, wheel, native loader and verification setting stays exact.
    if ({key: value for key, value in old_environment.items() if key != 'dispatch_guard'}
            != {key: value for key, value in new_environment_value.items() if key != 'dispatch_guard'}):
        raise ValueError('Only the environment guard owner may differ from the successful CA controls')
    if (old_environment.get('dispatch_guard') != reference(ca_scope.__file__)
            or new_environment_value.get('dispatch_guard') != reference(scope.__file__)):
        raise ValueError('The old/new environment guard owners are not explicitly bound')
    return {'version': REUSE_VERSION, 'instance_id': TASK, 'passed': True, 'plan': plan_ref,
            'leaf_configuration': plan['environments'][TASK]['configuration'],
            'original_plan': old_plan_ref, 'original_configuration': old_config_ref,
            'original_qualification': old_qualification_ref, 'original_controls': qualified['controls'],
            'exact_task_environment_identity': task_environment_identity(config),
            'original_scorer_manifest': old_manifest_ref, 'leaf_scorer_manifest': new_manifest_ref,
            'runtime_equivalence_fields': list(RUNTIME_EQUIVALENCE_FIELDS),
            'original_environment': old_environment_ref, 'leaf_environment': new_environment_ref,
            'only_environment_metadata_difference': 'dispatch_guard',
            'actual_original_qualification_validator_executed': True,
            'gold_empty_cleanup_and_CA_witnesses_verified': True,
            'effective_CA_and_native_SSL_semantics_changed': False,
            'official_test_or_candidate_bytes_changed': False,
            'old_resource_authority_reopened': False, 'new_controls': 0, 'model_calls': 0,
            'reused_physical_control_pairs': 1, 'source': reference(__file__)}


def scorer(policy, *, manifest_provider=None):
    value = _parent_scorer(policy, manifest_provider=manifest_provider)
    namespace = value.validate_request.__globals__
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence, MAX_GRADERS=1)
    namespace['validate_request'] = _lane_validator(namespace)
    from .software_namespace_witness_v183 import bind_scorer
    bind_scorer(value)
    repair.bind_scorer_environment(value)

    def validate_qualification(ref, config, plan_ref):
        expected_path = scope.COORDINATOR_ROOT / 'qualifications' / (TASK + '.json')
        if Path(ref['path']).resolve() != expected_path:
            raise ValueError('Leaf qualification metadata must have its own exact new identity')
        supplied = scope.load(ref)
        if supplied.get('version') != REUSE_VERSION or supplied != reused_qualification(config, plan_ref):
            raise ValueError('The explicit CA qualification reuse binding changed')
        return supplied

    prior_manifest = namespace['installation_manifest']
    def installation_manifest():
        result = prior_manifest()
        if manifest_provider is not None:
            return result
        return {**result, 'managed_delivery_validator': reference(closure.__file__),
                'leaf_scorer': reference(__file__), 'private_CA_revision': repair.manifest(),
                'public_network': 'none', 'maximum_real_tls_sessions': 0,
                'maximum_control_containers': 0, 'maximum_graders': 1,
                'independent_capacity_lease_root': str(scope.BATCH_ROOT / 'resource-claims'),
                'active_r2_or_CA_control_state_modified': False,
                'strict_reused_qualification_source': reference(ca_grading.__file__),
                'original_official_tests_and_scoring_rules_changed': False,
                'same_tree_delivery_reuse_adapter': reference(scope.ROOT / 'src/proworksim/software_benchmark_delivery_reuse_v175.py')}
    namespace.update(validate_qualification=validate_qualification, installation_manifest=installation_manifest)
    for name in ('validate_request', 'validate_qualification', 'installation_manifest', 'validate_delivery_evidence'):
        setattr(value, name, namespace[name])
    return value


def host(policy, scoring):
    value = bind_host(_parent_host(policy, scoring))
    def qualify(task):
        if task != TASK:
            raise ValueError('The leaf cannot qualify another original task')
        ref = reference(scope.COORDINATOR_ROOT / 'qualifications' / (TASK + '.json'))
        plan_ref = reference(scope.PLAN_FILE)
        plan = scope.load(plan_ref)
        scoring.validate_qualification(ref, scope.load(plan['environments'][TASK]['configuration']), plan_ref)
        return ref
    value.qualify = qualify
    return value


def prepare_environment_qualifications_local():
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(scope.load(plan_ref))
    if set(plan['environments']) != {TASK}:
        raise ValueError('Only the one original Requests environment may be prepared')
    scoring = scorer(scope.dispatch_view())
    scoring.environment.prepare()
    scope.retain(scope.COORDINATOR_ROOT / 'scorer-manifest.json', scoring.installation_manifest())
    config = scope.load(plan['environments'][TASK]['configuration'])
    proof = reused_qualification(config, plan_ref)
    qualification = scope.retain(scope.COORDINATOR_ROOT / 'qualifications' / (TASK + '.json'), proof)
    result = {'controls': [], 'qualifications': {TASK: {'status': 'qualified',
              'qualification': qualification, 'reused_controls': True, 'new_controls': 0}},
              'new_controls': 0, 'reused_control_pairs': 1, 'model_calls': 0,
              'original_CA_control_bytes_and_receipts_preserved': True}
    scope.retain(scope.COORDINATOR_ROOT / 'qualification-reuse-decisions.json', result)
    return result


_ns.update(private_environment=private_environment, scorer=scorer, host=host,
           prepare_environment_qualifications_local=prepare_environment_qualifications_local)
for _name in ('score_request', 'main'):
    _source = inspect.getsource(getattr(base, _name)).replace("'v105.run'", "'v066.run'")
    exec(compile(_source, __file__ + ':' + _name, 'exec'), _ns)
_ns['cold_manifest'] = lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__, _ns))
_methods = {key: clone_function(value, _ns) for key, value in vars(base.Grading).items() if isinstance(value, FunctionType)}
_source = textwrap.dedent(inspect.getsource(base.Grading.run_request)).replace("'v105.run'", "'v066.run'")
_local = {}
exec(compile(_source, __file__ + ':leaf-scoring-child', 'exec'), _ns, _local)
_methods['run_request'] = _local['run_request']
_ns['Grading'] = type('Grading', (base.Grading,), _methods)
globals().update({key: value for key, value in _ns.items() if not key.startswith('__')})

if __name__ == '__main__':
    _ns['main']()
