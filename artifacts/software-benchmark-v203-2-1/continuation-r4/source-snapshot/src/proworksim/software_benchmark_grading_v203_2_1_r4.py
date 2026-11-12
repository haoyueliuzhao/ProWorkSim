"""Ten unused original tasks: strict r2/r3 environment reuse, zero new controls.

Nine tasks retain their qualified r2 scoring environment. Requests2317 uses its
separately qualified r3 CA environment. Candidates, official tests, scoring and
fixed-member delivery rules are unchanged; old source/state is never rewritten.
"""
from functools import lru_cache
import inspect
from pathlib import Path
import textwrap
from types import FunctionType

from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v203_2_1_r2 as ordinary_grading
from . import software_benchmark_grading_passive_v203_2_1_r3 as ca_grading
from . import software_benchmark_environment_passive_v203_2_1_r2 as ordinary_environment
from . import software_benchmark_environment_passive_v203_2_1_r3 as ca_environment
from . import software_benchmark_scope_v203_2_1_r4 as scope
from . import software_benchmark_project_closure_v203_2_1 as closure
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_delivery_reuse_v175 import bind_host
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function
from .software_benchmark_grading_v131 import _lane_validator

VERSION = 'v203.2.1-r4-ten-original-tasks-strict-scoring-reuse'
REUSE_VERSION = 'v203.2.1-r4-exact-qualified-environment-reuse'
MODULE = 'proworksim.software_benchmark_grading_v203_2_1_r4'
REQUESTS = ca_environment.TASK
PYLINT = ordinary_environment.PYLINT_TASK
_ns = clone_namespace(base, scope=scope, VERSION=VERSION, MODULE=MODULE, __file__=__file__)
_parent_scorer, _parent_host, _parent_environment = _ns['scorer'], _ns['host'], _ns['private_environment']
RUNTIME_FIELDS = ('parent', 'archive_adapter', 'diagnostic_decode_adapter', 'diagnostic_upstream_sha256',
    'limits', 'cap_add', 'cap_drop', 'no_new_privileges', 'official_tests_and_scoring_rules_changed',
    'host_poll_adapter', 'scorer_interpreter_profile', 'public_network', 'maximum_real_tls_sessions')


def private_environment(policy):
    ordinary = ordinary_environment.private_environment(policy, scope, _parent_environment)
    ca = ca_environment.private_environment(policy, scope, _parent_environment)
    namespace = ordinary.provider.__globals__
    namespace['offline'] = ca.offline
    def prepare():
        folder = scope.GRADING_ROOT / 'environments'
        return scope.retain(folder / 'bindings.json', {
            'offline': scope.retain(folder / 'requests2317-offline-ca-r3.json', ca.offline.environment_manifest()),
            'pylint_wheel': scope.retain(folder / 'pylint4661-appdirs.json', ordinary_environment.wheel_manifest()),
            'tls': None, 'network_resolutions': {}})
    def request_fields(task):
        binding = scope.load(reference(scope.GRADING_ROOT / 'environments/bindings.json'))
        ref = binding['offline'] if task == REQUESTS else binding['pylint_wheel'] if task == PYLINT else None
        return {'environment_revision': ref, 'network_resolution': None}
    def validate_request(request, task):
        expected = request_fields(task)
        if any(request.get(key) != value for key, value in expected.items()):
            raise ValueError('The exact task-specific r4 environment binding changed')
        if task == REQUESTS:
            ca.offline.validate_environment(expected['environment_revision'])
            return ca.offline
        if task == PYLINT and scope.load(expected['environment_revision']) != ordinary_environment.wheel_manifest():
            raise ValueError('The qualified Pylint wheel environment changed')
        return None
    namespace.update(prepare=prepare, request_fields=request_fields, validate_request=validate_request)
    ordinary.__dict__.update(namespace)
    ordinary.__file__ = __file__
    return ordinary


def bind_environment(scorer):
    """Retain the r3 CA implementation, applying its lifecycle only to Requests.

    Its initial r2 binder already supports ordinary/Pylint scorers. Remove only
    the single-task creation restriction and bypass CA teardown for other tasks;
    CA staging, TLS/path/hash checks and the original evaluator stay byte-for-byte
    in the imported implementation.
    """
    source = inspect.getsource(ca_environment.bind_scorer_environment)
    before = '''            if self.observation['mapping']['instance_id'] != TASK:
                raise ValueError('Independent Requests2317 scorer cannot create another task')
            result = super().create(**options)
            self.tracking['requests2317_CA_wrapper'] = result'''
    after = '''            result = super().create(**options)
            if self.observation['mapping']['instance_id'] == TASK:
                self.tracking['requests2317_CA_wrapper'] = result'''
    cleanup = "    def cleanup(request, tracking):\n"
    if source.count(before) != 1 or source.count(cleanup) != 1:
        raise ValueError('The qualified CA binding changed; no broad source replacement')
    source = source.replace(before, after).replace(cleanup, cleanup +
        "        if tracking.get('requests2317_CA_wrapper') is None:\n            return prior_cleanup(request, tracking)\n")
    source = source.replace("'Requests2317_CA_measured_before_original_cleanup': True",
                            "'Requests2317_CA_pre_cleanup_hook_installed': True")
    namespace = dict(ca_environment.bind_scorer_environment.__globals__)
    exec(compile(source, __file__ + ':task-scoped-qualified-CA-binding', 'exec'), namespace)
    return namespace['bind_scorer_environment'](scorer)


def identity(config):
    return {**base.environment_identity(config), 'repo': config['repo'],
            'public_task': config['public_task'], 'public_test_entry': config['public_test_entry'],
            'official_image_descriptor': config['scorer_request_base']['image']}


def reused_qualification(config, plan_ref):
    plan = scope.validate_plan(scope.load(plan_ref))
    task = config.get('instance_id')
    if (plan_ref != reference(scope.PLAN_FILE) or task not in plan['environments']
            or len(plan['rows']) != 10 or any(r['role'] == 'control' for r in plan['resources'].values())
            or config != scope.load(plan['environments'][task]['configuration'])):
        raise ValueError('Reuse requires the exact ten-task plan, with no new control identities')
    source = ca_grading if task == REQUESTS else ordinary_grading
    old_scope = source.scope
    old_plan_ref = reference(old_scope.PLAN_FILE)
    old_plan = old_scope.validate_plan(old_scope.load(old_plan_ref))
    old_config_ref = old_plan['environments'][task]['configuration']
    old_config = old_scope.load(old_config_ref)
    if identity(config) != identity(old_config):
        raise ValueError('Original task, image, dataset, baseline or test binding changed')
    old_qualification_ref = reference(old_scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json'))
    old_scorer = source.scorer(old_scope.dispatch_view())
    verified = old_scorer.validate_qualification(old_qualification_ref, old_config, old_plan_ref)
    controls = verified.get('controls', verified.get('original_controls'))
    if verified.get('passed') is not True or not isinstance(controls, list) or len(controls) != 2:
        raise ValueError('Original gold/empty evidence did not pass its exact historical validator')
    old_manifest_ref = reference(old_scope.COORDINATOR_ROOT / 'scorer-manifest.json')
    new_manifest_ref = reference(scope.COORDINATOR_ROOT / 'scorer-manifest.json')
    old_manifest, new_manifest = scope.load(old_manifest_ref), scope.load(new_manifest_ref)
    if any(old_manifest.get(key) != new_manifest.get(key) for key in RUNTIME_FIELDS):
        raise ValueError('The original official scoring runtime changed')
    if task == REQUESTS and new_manifest.get('private_CA_revision') != old_manifest.get('private_CA_revision'):
        raise ValueError('Qualified Requests CA/TLS semantics changed')
    if task == PYLINT and new_manifest.get('pylint_appdirs_wheel') != old_manifest.get('pylint_appdirs_wheel'):
        raise ValueError('Qualified Pylint dependency semantics changed')
    old_environment = old_scorer.environment.request_fields(task)
    new_environment = private_environment(scope.dispatch_view()).request_fields(task)
    if old_environment['network_resolution'] != new_environment['network_resolution']:
        raise ValueError('External network resolution cannot be added during reuse')
    old_ref, new_ref = old_environment['environment_revision'], new_environment['environment_revision']
    if old_ref is None or new_ref is None:
        if old_ref != new_ref:
            raise ValueError('An ordinary task acquired an unqualified environment modification')
    else:
        old_value, new_value = scope.load(old_ref), scope.load(new_ref)
        ignored = {'dispatch_guard'} if task == REQUESTS else set()
        if ({k: v for k, v in old_value.items() if k not in ignored}
                != {k: v for k, v in new_value.items() if k not in ignored}):
            raise ValueError('Only the Requests environment guard owner may differ')
        if task == REQUESTS and (old_value.get('dispatch_guard') != reference(old_scope.__file__)
                                or new_value.get('dispatch_guard') != reference(scope.__file__)):
            raise ValueError('Qualified/new environment guard owners were not explicitly bound')
    return {'version': REUSE_VERSION, 'instance_id': task, 'passed': True, 'plan': plan_ref,
            'configuration': plan['environments'][task]['configuration'], 'source_qualification': old_qualification_ref,
            'source_plan': old_plan_ref, 'source_configuration': old_config_ref, 'original_controls': controls,
            'source_scorer_manifest': old_manifest_ref, 'current_scorer_manifest': new_manifest_ref,
            'source_environment': old_environment, 'current_environment': new_environment,
            'task_environment_identity': identity(config), 'runtime_equivalence_fields': list(RUNTIME_FIELDS),
            'original_strict_qualification_validator_executed': True,
            'CA_witnesses_verified': task == REQUESTS, 'dependency_witnesses_verified': task == PYLINT,
            'effective_environment_semantics_changed': False, 'official_tests_or_candidate_bytes_changed': False,
            'new_controls': 0, 'model_calls': 0, 'old_resource_authority_reopened': False,
            'source': reference(__file__)}


def scorer(policy, *, manifest_provider=None):
    value = _parent_scorer(policy, manifest_provider=manifest_provider)
    namespace = value.validate_request.__globals__
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence, MAX_GRADERS=scope.MAX_GRADERS)
    namespace['validate_request'] = _lane_validator(namespace)
    from .software_namespace_witness_v183 import bind_scorer
    bind_scorer(value)
    bind_environment(value)
    def validate_qualification(ref, config, plan_ref):
        if Path(ref['path']).resolve() != scope.COORDINATOR_ROOT / 'qualifications' / (config['instance_id'] + '.json'):
            raise ValueError('The r4 qualification must retain its own exact metadata identity')
        supplied = scope.load(ref)
        if supplied.get('version') != REUSE_VERSION or supplied != reused_qualification(config, plan_ref):
            raise ValueError('Strict r4 qualification reuse proof changed')
        return supplied
    prior_manifest = namespace['installation_manifest']
    def installation_manifest():
        result = prior_manifest()
        if manifest_provider is not None:
            return result
        return {**result, 'managed_delivery_validator': reference(closure.__file__),
                'r4_scorer': reference(__file__), 'private_CA_revision': ca_environment.manifest(),
                'pylint_appdirs_wheel': ordinary_environment.wheel_manifest(),
                'public_network': 'none', 'maximum_real_tls_sessions': 0, 'maximum_control_containers': 0,
                'maximum_graders': scope.MAX_GRADERS, 'qualified_task_profiles': {
                    REQUESTS: reference(ca_environment.__file__), PYLINT: reference(ordinary_environment.__file__)},
                'other_tasks_have_no_new_environment_modification': True,
                'same_tree_delivery_reuse_adapter': reference(scope.ROOT / 'src/proworksim/software_benchmark_delivery_reuse_v175.py')}
    namespace.update(validate_qualification=validate_qualification, installation_manifest=installation_manifest)
    for name in ('validate_request', 'validate_qualification', 'installation_manifest', 'validate_delivery_evidence'):
        setattr(value, name, namespace[name])
    return value


def host(policy, scoring):
    value = bind_host(_parent_host(policy, scoring))
    def qualify(task):
        plan_ref = reference(scope.PLAN_FILE)
        plan = scope.validate_plan(scope.load(plan_ref))
        ref = reference(scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json'))
        scoring.validate_qualification(ref, scope.load(plan['environments'][task]['configuration']), plan_ref)
        return ref
    value.qualify = qualify
    return value


def prepare_environment_qualifications_local():
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(scope.load(plan_ref))
    scoring = scorer(scope.dispatch_view())
    scoring.environment.prepare()
    scope.retain(scope.COORDINATOR_ROOT / 'scorer-manifest.json', scoring.installation_manifest())
    qualifications = {}
    for task, item in plan['environments'].items():
        proof = reused_qualification(scope.load(item['configuration']), plan_ref)
        ref = scope.retain(scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json'), proof)
        qualifications[task] = {'status': 'qualified', 'qualification': ref, 'reused_controls': True, 'new_controls': 0}
    if len(qualifications) != 10 or REQUESTS not in qualifications:
        raise ValueError('r4 requires all ten unchanged original tasks including qualified Requests')
    result = {'controls': [], 'qualifications': qualifications, 'new_controls': 0,
              'reused_control_pairs': 10, 'model_calls': 0, 'old_results_and_control_receipts_preserved': True}
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
exec(compile(_source, __file__ + ':r4-scoring-child', 'exec'), _ns, _local)
_methods['run_request'] = _local['run_request']
_ns['Grading'] = type('Grading', (base.Grading,), _methods)
globals().update({key: value for key, value in _ns.items() if not key.startswith('__')})

if __name__ == '__main__':
    _ns['main']()
