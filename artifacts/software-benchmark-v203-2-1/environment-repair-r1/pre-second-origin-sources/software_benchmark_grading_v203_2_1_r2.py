"""Four fresh scoring controls plus explicit reuse of ten unchanged r1 pairs.

Only Requests2317 and Pylint4661 receive new scorer-only environment inputs.
Official patch/test bytes and scoring predicates stay unchanged. This module
prepares metadata locally; the separately sealed r2 scope owns actual execution.
"""
from functools import lru_cache
import inspect
import json
from pathlib import Path
import textwrap
from types import FunctionType

from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v203_2_1 as previous
from . import software_benchmark_scope_v203_2_1_r2 as scope
from . import software_benchmark_environment_passive_v203_2_1_r2 as repair
from . import software_benchmark_project_closure_v203_2_1 as closure
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_delivery_reuse_v175 import bind_host
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function
from .software_benchmark_grading_v131 import _lane_validator

VERSION = 'v203.2.1-r2-two-environment-repair-official-score-r1'
REUSE_VERSION = 'v203.2.1-r2-explicit-unchanged-r1-qualification-reuse'
MODULE = 'proworksim.software_benchmark_grading_v203_2_1_r2'
OLD_ROOT = scope.ROOT / 'runs/software-benchmark-v203-2-1/passive-pilot12-r1'
_ns = clone_namespace(base, scope=scope, VERSION=VERSION, MODULE=MODULE, __file__=__file__)
_parent_scorer, _parent_host, _parent_environment = _ns['scorer'], _ns['host'], _ns['private_environment']


def private_environment(policy):
    return repair.private_environment(policy, scope, _parent_environment)


def reused_qualification(task, config, plan_ref):
    if task in repair.REPAIR_TASKS:
        raise ValueError('A repaired environment cannot reuse its failed r1 control')
    plan = scope.load(plan_ref)
    reuse = plan.get('qualification_reuse_from_previous', {})
    if (plan_ref != reference(scope.PLAN_FILE) or task not in reuse.get('tasks', [])
            or reuse.get('required_strict_environment_equivalence') is not True
            or reuse.get('source_qualification_directory') != str(OLD_ROOT / 'grading-coordinator/qualifications')
            or set(reuse.get('current_pending_tasks', [])) != repair.REPAIR_TASKS
            or reuse.get('previous_passed_flag_alone_is_not_authority') is not True):
        raise ValueError('The sealed r2 plan does not authorize this exact old qualification reuse')
    old_plan_ref = reference(OLD_ROOT / 'execution-plan.json')
    old_plan = scope.load(old_plan_ref)
    old_config_ref = old_plan['environments'][task]['configuration']
    old_config = scope.load(old_config_ref)
    if base.environment_identity(config) != base.environment_identity(old_config):
        raise ValueError('The original environment identity changed; fresh controls are required')
    old_qualification_ref = reference(OLD_ROOT / 'grading-coordinator/qualifications' / (task + '.json'))
    validator = previous.scorer(previous.scope.dispatch_view())
    qualified = validator.validate_qualification(old_qualification_ref, old_config, old_plan_ref)
    if qualified.get('passed') is not True:
        raise ValueError('Only a fully qualified original pair can be reused')
    return {'version': REUSE_VERSION, 'instance_id': task, 'passed': True, 'plan': plan_ref,
            'original_qualification': old_qualification_ref, 'original_configuration': old_config_ref,
            'original_plan': old_plan_ref, 'unchanged_environment_identity': base.environment_identity(config),
            'original_scorer_manifest': reference(OLD_ROOT / 'grading-coordinator/scorer-manifest.json'),
            'new_scorer_adapter': reference(__file__), 'repair_adapter': reference(repair.__file__),
            'repair_tasks_excluded_from_reuse': sorted(repair.REPAIR_TASKS),
            'task_environment_changed': False, 'official_tests_or_scoring_rules_changed': False,
            'new_private_capabilities': [], 'old_resource_authority_reopened': False,
            'original_controls': qualified['controls'], 'new_controls': 0, 'model_calls': 0}


def scorer(policy, *, manifest_provider=None):
    value = _parent_scorer(policy, manifest_provider=manifest_provider)
    namespace = value.validate_request.__globals__
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence, MAX_GRADERS=2)
    namespace['validate_request'] = _lane_validator(namespace)
    from .software_namespace_witness_v183 import bind_scorer
    bind_scorer(value)
    repair.bind_scorer_environment(value)
    native_validate = clone_function(base.original.validate_qualification, namespace)

    def validate_qualification(ref, config, plan_ref):
        supplied = scope.load(ref)
        task = config['instance_id']
        if supplied.get('version') == REUSE_VERSION:
            if Path(ref['path']).resolve() != scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json'):
                raise ValueError('Reused qualification must have its own new r2 metadata identity')
            expected = reused_qualification(task, config, plan_ref)
            if supplied != expected:
                raise ValueError('Explicit original-control reuse proof changed')
            return supplied
        result = native_validate(ref, config, plan_ref)
        if task == repair.PYLINT_TASK:
            for item in result['controls']:
                path = Path(item['initial_container']['path']).parent / 'pylint4661-offline-wheel.json'
                proof = json.loads(checked(reference(path)).read_bytes())
                if (proof.get('manifest') != repair.wheel_manifest()
                        or proof.get('actual_environment') != repair.PIP_ENVIRONMENT
                        or proof.get('actual_interpreter_and_wheel') != {
                            'python': '3.9.20', 'wheel_sha256': repair.WHEEL_SHA256}
                        or proof.get('task_files_changed') is not False
                        or proof.get('official_command_unchanged') is not True):
                    raise ValueError('Pylint control lacks exact offline dependency evidence')
        return result

    original_manifest = namespace['installation_manifest']
    def manifest():
        result = original_manifest()
        if manifest_provider is not None:
            return result
        return {**result, 'managed_delivery_validator': reference(closure.__file__),
                'passive_score_adapter': reference(__file__), 'public_network': 'none',
                'namespace_witness_adapter': reference(scope.ROOT / 'src/proworksim/software_namespace_witness_v183.py'),
                'environment_repair_adapter': reference(repair.__file__),
                'pylint_appdirs_wheel': repair.wheel_manifest(),
                'requests_capabilities_by_task': {repair.REQUESTS_TASK: ['NET_ADMIN', 'NET_BIND_SERVICE']},
                'requests_extra_hosts_by_task': {repair.REQUESTS_TASK: {'httpbin.org': '127.0.0.1'}},
                'scorer_create_binding_sha256': value.passive_environment_create_sha256,
                'maximum_real_tls_sessions': 0, 'fresh_control_tasks': sorted(repair.REPAIR_TASKS),
                'prior_control_reuse_requires_exact_environment_identity': True}
    namespace.update(validate_qualification=validate_qualification, installation_manifest=manifest)
    for name in ('validate_request', 'validate_qualification', 'installation_manifest', 'validate_delivery_evidence'):
        setattr(value, name, namespace[name])
    return value


def host(policy, scoring):
    return bind_host(_parent_host(policy, scoring))


def prepare_environment_qualifications_local():
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(scope.load(plan_ref))
    scoring = scorer(scope.dispatch_view())
    scoring.environment.prepare()
    manifest = scope.retain(scope.COORDINATOR_ROOT / 'scorer-manifest.json', scoring.installation_manifest())
    controls, qualifications = [], {}
    for task, environment in plan['environments'].items():
        if task not in repair.REPAIR_TASKS:
            config = scope.load(environment['configuration'])
            proof = reused_qualification(task, config, plan_ref)
            ref = scope.retain(scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json'), proof)
            qualifications[task] = {'status': 'qualified', 'qualification': ref,
                                    'reused_controls': True, 'new_controls': 0}
            continue
        for kind in ('gold', 'empty'):
            key = 'control-' + task + '-' + kind
            request = {'version': VERSION, 'resource_key': key, 'instance_id': task, 'slot_id': None,
                'plan': plan_ref, 'configuration': environment['configuration'], 'patch_kind': kind,
                'limits': scoring.LIMITS, 'scorer_manifest': manifest, 'cpuset_cpus': None,
                'directory': str(scope.GRADING_ROOT / key), 'candidate_lock': None,
                **scoring.environment.request_fields(task)}
            controls.append(scope.retain(scope.GRADING_ROOT / key / 'request.json', request))
    if len(controls) != 4 or len(qualifications) != 10:
        raise ValueError('The revised panel requires exactly four new controls and ten reused pairs')
    result = {'controls': controls, 'qualifications': qualifications, 'model_calls': 0,
              'new_controls': 4, 'reused_control_pairs': 10,
              'old_qualification_results_preserved': True,
              'repaired_tasks_must_pass_fresh_gold_empty': sorted(repair.REPAIR_TASKS)}
    scope.retain(scope.COORDINATOR_ROOT / 'qualification-reuse-decisions.json', result)
    return result


_ns.update(private_environment=private_environment, scorer=scorer, host=host,
           prepare_environment_qualifications_local=prepare_environment_qualifications_local)
for _name in ('score_request', 'main'):
    _source = inspect.getsource(getattr(base, _name)).replace("'v105.run'", "'v203.2.1.run'")
    exec(compile(_source, __file__ + ':' + _name, 'exec'), _ns)
_ns['cold_manifest'] = lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__, _ns))
_methods = {key: clone_function(value, _ns) for key, value in vars(base.Grading).items() if isinstance(value, FunctionType)}
_source = textwrap.dedent(inspect.getsource(base.Grading.run_request)).replace("'v105.run'", "'v203.2.1.run'")
_local = {}
exec(compile(_source, __file__ + ':scoring-child', 'exec'), _ns, _local)
_methods['run_request'] = _local['run_request']
_ns['Grading'] = type('Grading', (base.Grading,), _methods)
globals().update({key: value for key, value in _ns.items() if not key.startswith('__')})

if __name__ == '__main__':
    _ns['main']()
